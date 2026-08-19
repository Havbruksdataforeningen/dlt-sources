"""dlt source for the Aquabyte API v3.

Endpoints, params and record shapes: https://api.aquabyte.ai/v3/docs — committed as
`specs/openapi.json`, which `tests/test_param_surface.py` pins every signature against.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch
merged into the query string last. Bind them per resource or set them in config under
`[sources.aquabyte.<resource>]`; see the README.
"""

import logging
from collections.abc import Iterator
from typing import Any

import dlt
from dlt.common.schema.typing import TColumnSchema, TScd2StrategyDict
from dlt.sources.helpers.rest_client.auth import APIKeyAuth
from dlt.sources.helpers.rest_client.client import RESTClient
from dlt.sources.helpers.rest_client.paginators import (
    BasePaginator,
    JSONResponseCursorPaginator,
    SinglePagePaginator,
)

logger = logging.getLogger(__name__)

PenId = str | list[str]
"""A single pen id or the literal `"all"`. A list is request fan-out — it filters nothing."""

SCD2: TScd2StrategyDict = {"disposition": "merge", "strategy": "scd2"}
"""Registry tables are versioned, never replaced: a row is retired, never deleted.

Always paired with `merge_key="id"`, which scopes retirement to the ids a load carried,
so reading one site does not retire the others. The trade-off, and how to take the other
side, are in `REFERENCE.md`. https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy
"""


Columns = dict[str, TColumnSchema]
"""Column hints for one resource: the API's own field names, typed per `specs/openapi.json`.

They buy one thing — a column keeps its type when the first page is all nulls, or the
field is missing entirely. A field with no entry still lands, typed from the data.
Nested fields have no entry, so `max_table_nesting` alone decides their shape.
`nullable: False` marks the fields the spec requires and forbids to be null.
"""

SITE_COLUMNS: Columns = {
    "id": {"data_type": "text", "nullable": False},
    "name": {"data_type": "text", "nullable": False},
    "governmentSiteNumber": {"data_type": "bigint"},
    "external_site_id": {"data_type": "text"},
}

PEN_COLUMNS: Columns = {
    "id": {"data_type": "text", "nullable": False},
    "name": {"data_type": "text", "nullable": False},
    "penCode": {"data_type": "text"},
    "isActive": {"data_type": "bool", "nullable": False},
    "external_id": {"data_type": "text"},
}

ENVIRONMENTAL_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "temperatureAvg": {"data_type": "double"},
    "cameraDepthAvg": {"data_type": "double"},
    "cameraDepthMin": {"data_type": "double"},
    "cameraDepthMax": {"data_type": "double"},
    "oxygenPct": {"data_type": "double"},
    "salinity": {"data_type": "double"},
    "fishDensity": {"data_type": "double"},
}

ENVIRONMENTAL_LATEST_COLUMNS: Columns = {
    "penId": {"data_type": "text"},
    "time": {"data_type": "text", "nullable": False},
    "temperature": {"data_type": "double"},
    "cameraDepth": {"data_type": "double"},
    "oxygenPct": {"data_type": "double"},
    "salinity": {"data_type": "double"},
}

BIOMASS_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double"},
    "avgWeight": {"data_type": "double"},
    "kFactor": {"data_type": "double"},
    "cv": {"data_type": "double"},
}

HARVEST_REPORT_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "mainReport": {"data_type": "bool", "nullable": False},
    "asOfDate": {"data_type": "text", "nullable": False},
    "lastFeedingDate": {"data_type": "text", "nullable": False},
    "slaughterStartDate": {"data_type": "text", "nullable": False},
    "slaughterEndDate": {"data_type": "text", "nullable": False},
    "temperature": {"data_type": "double", "nullable": False},
    "lossFactor": {"data_type": "double", "nullable": False},
    "packingMethod": {"data_type": "text"},
    "fishType": {"data_type": "text"},
    "measurementCount": {"data_type": "bigint", "nullable": False},
    "coefficientOfVariation": {"data_type": "double", "nullable": False},
    "avgPackedWeightGrams": {"data_type": "double", "nullable": False},
    "avgRoundWeightGrams": {"data_type": "double", "nullable": False},
    "superiorRate": {"data_type": "double", "nullable": False},
    "createdAt": {"data_type": "text", "nullable": False},
}

LICE_COUNT_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "adultFemale": {"data_type": "double"},
    "adultFemaleConverted": {"data_type": "double"},
    "mobile": {"data_type": "double"},
    "mobileConverted": {"data_type": "double"},
    "caligus": {"data_type": "double"},
}

SWIM_SPEED_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "swimSpeedsampleSize": {"data_type": "double", "nullable": False},
    "swimSpeed": {"data_type": "double"},
    "swimTiltsampleSize": {"data_type": "double", "nullable": False},
    "swimTilt": {"data_type": "double"},
}

BREATHING_INDEX_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "breathingIndex": {"data_type": "double"},
}

WELFARE_SCORES_COLUMNS: Columns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
}


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    """Drop unset named params, then merge the caller's passthrough last so it wins."""
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _window_start(
    resource: str,
    param: str,
    explicit: str | None,
    incremental: dlt.sources.incremental[str] | None,
    fallback: str | None,
) -> str:
    """An explicit override, else the incremental cursor, else config — never nothing.

    A window start is always sent, so a run cannot silently inherit the API's own default
    window. dlt logs the requests; what it cannot know is *why* a window was asked for.
    """
    cursor_value = incremental.last_value if incremental is not None else None
    if explicit is not None:
        if cursor_value is not None and explicit < cursor_value:
            # With the cursor active, dlt's incremental filter drops every fetched row
            # below it — the backfill would request the window and then load nothing.
            raise ValueError(
                f"{resource}: {param}={explicit} reaches back before the incremental cursor "
                f"({cursor_value}), whose filter would drop every row below it. Backfill by "
                f"binding the window on the resource's incremental_* argument instead — see REFERENCE.md."
            )
        logger.info("%s: %s=%s passed explicitly; the incremental cursor is ignored.", resource, param, explicit)
        return explicit
    if cursor_value is None:
        if fallback is None:
            config_key = "initial_time" if param == "fromTime" else "initial_date"
            raise ValueError(
                f"{resource}: no {param} bound, no incremental cursor value, and no configured "
                f"start. Set {config_key} under [sources.aquabyte], or bind a window — see the README."
            )
        logger.warning(
            "%s: no %s and no incremental cursor value, so the configured start applies, %s=%s.",
            resource,
            param,
            param,
            fallback,
        )
        return fallback
    logger.debug("%s: resuming from the incremental cursor, %s=%s.", resource, param, cursor_value)
    return cursor_value


def _window_end(explicit: str | None, incremental: dlt.sources.incremental[str] | None) -> str | None:
    """An explicit override, else the incremental's `end_value`, else nothing.

    `end_value` is set when a backfill window is bound (see `REFERENCE.md`), and sending it
    as the request's window end keeps the API asked for exactly the rows dlt will keep.
    """
    if explicit is not None:
        return explicit
    return incremental.end_value if incremental is not None else None


def _paginate_per_pen(
    client: RESTClient,
    path: str,
    *,
    pen_id: PenId,
    params: dict[str, Any],
    data_selector: str,
    paginator: BasePaginator | None = None,
) -> Iterator[list[dict[str, Any]]]:
    """Yield pages per requested pen id. `penId` comes from `pen_id`; `params` cannot set it."""
    pen_ids = [pen_id] if isinstance(pen_id, str) else list(pen_id)
    if len(pen_ids) > 1:
        logger.info("%s: fanning out over %d pen ids.", path, len(pen_ids))
    for pid in pen_ids:
        yield from client.paginate(
            path, params={**params, "penId": pid}, data_selector=data_selector, paginator=paginator
        )


@dlt.source(max_table_nesting=0)
def aquabyte_source(
    base_url: str = dlt.config.value,
    api_key: str = dlt.secrets.value,
    initial_date: str | None = None,
    initial_time: str | None = None,
):
    """Aquabyte API v3 dlt source. All resources share one RESTClient.

    Args:
        base_url: API base URL, from config.
        api_key: API key, from secrets.
        initial_date: Cursor start for the date-based resources (YYYY-MM-DD). Needed only
            when such a resource runs without a bound window; erroring then, not before.
        initial_time: As `initial_date`, for the time-based resources (ISO 8601).
    """
    client = RESTClient(
        base_url=base_url,
        auth=APIKeyAuth(name="apikey", api_key=api_key, location="header"),
        paginator=JSONResponseCursorPaginator(cursor_path="nextToken", cursor_param="nextToken"),
    )

    @dlt.resource(write_disposition=SCD2, merge_key="id", columns=SITE_COLUMNS)
    def sites(site_id: str | None = None, params: dict[str, Any] | None = None):
        """Every site from `GET /sites`, or one from `GET /sites/{siteId}` when `site_id` is bound.

        Both endpoints write the same table.
        """
        pages = client.paginate(
            f"/sites/{site_id}" if site_id is not None else "/sites",
            params=_query(params),
            data_selector="sites",
            paginator=SinglePagePaginator(),
        )
        yield from pages

    # `dlt.transformer` types write_disposition as the literals only, unlike `dlt.resource`;
    # both hand it to the same hint machinery, so the dict is fine at runtime.
    @dlt.transformer(data_from=sites, write_disposition=SCD2, merge_key="id", columns=PEN_COLUMNS)  # type: ignore[arg-type]
    def pens(sites_page: list[dict[str, Any]]):
        """Every pen the `/sites` response nests, unwrapped into its own table — none filtered.

        Versioned because a pen leaves `/sites` once it is emptied, and its history has to
        outlive it.
        """
        for site in sites_page:
            yield from site.get("pens") or []

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime", "toTime"], columns=ENVIRONMENTAL_COLUMNS)
    def environmental(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Environmental readings from `GET /environmental`."""
        window_start = _window_start("environmental", "fromTime", from_time, incremental_from_time, initial_time)
        yield from _paginate_per_pen(
            client,
            "/environmental",
            pen_id=pen_id,
            params=_query(
                params, fromTime=window_start, toTime=_window_end(to_time, incremental_from_time), period=period
            ),
            data_selector="data",
        )

    @dlt.resource(write_disposition="replace", columns=ENVIRONMENTAL_LATEST_COLUMNS)
    def environmental_latest(pen_id: PenId = "all", params: dict[str, Any] | None = None):
        """The latest environmental reading per pen from `GET /environmental/latest`."""
        yield from _paginate_per_pen(
            client,
            "/environmental/latest",
            pen_id=pen_id,
            params=_query(params),
            data_selector="data",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=BIOMASS_COLUMNS)
    def biomass(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        bucket_size: int | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Daily biomass from `GET /biomass`."""
        window_start = _window_start("biomass", "fromDate", from_date, incremental_date, initial_date)
        yield from _paginate_per_pen(
            client,
            "/biomass",
            pen_id=pen_id,
            params=_query(
                params, fromDate=window_start, toDate=_window_end(to_date, incremental_date), bucketSize=bucket_size
            ),
            data_selector="biomass",
        )

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "slaughterStartDate", "mainReport", "asOfDate"],
        columns=HARVEST_REPORT_COLUMNS,
    )
    def harvest_report(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_slaughter_start_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "slaughterStartDate", initial_value=initial_date
        ),
    ):
        """Harvest reports from `GET /biomass/harvestReport`."""
        window_start = _window_start(
            "harvest_report", "fromDate", from_date, incremental_slaughter_start_date, initial_date
        )
        yield from _paginate_per_pen(
            client,
            "/biomass/harvestReport",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=_window_end(to_date, incremental_slaughter_start_date)),
            data_selector="reports",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=LICE_COUNT_COLUMNS)
    def lice_count(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Lice counts from `GET /liceCount`."""
        window_start = _window_start("lice_count", "fromDate", from_date, incremental_date, initial_date)
        yield from _paginate_per_pen(
            client,
            "/liceCount",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=_window_end(to_date, incremental_date)),
            data_selector="liceCount",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime", "toTime"], columns=SWIM_SPEED_COLUMNS)
    def behaviour_swim_speed(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Swim speed and tilt from `GET /behaviour/swimSpeed`."""
        window_start = _window_start("behaviour_swim_speed", "fromTime", from_time, incremental_from_time, initial_time)
        yield from _paginate_per_pen(
            client,
            "/behaviour/swimSpeed",
            pen_id=pen_id,
            params=_query(
                params, fromTime=window_start, toTime=_window_end(to_time, incremental_from_time), period=period
            ),
            data_selector="swimSpeed",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=BREATHING_INDEX_COLUMNS)
    def behaviour_breathing_index(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Breathing index from `GET /behaviour/breathingIndex`, which documents no `period`."""
        window_start = _window_start(
            "behaviour_breathing_index", "fromTime", from_time, incremental_from_time, initial_time
        )
        yield from _paginate_per_pen(
            client,
            "/behaviour/breathingIndex",
            pen_id=pen_id,
            params=_query(params, fromTime=window_start, toTime=_window_end(to_time, incremental_from_time)),
            data_selector="breathingIndex",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=WELFARE_SCORES_COLUMNS)
    def welfare_scores(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Welfare scores from `GET /welfareScores` — one row per pen and date, categories nested."""
        window_start = _window_start("welfare_scores", "fromDate", from_date, incremental_date, initial_date)
        yield from _paginate_per_pen(
            client,
            "/welfareScores",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=_window_end(to_date, incremental_date)),
            data_selector="welfareScores",
        )

    return (
        sites,
        pens,
        environmental,
        environmental_latest,
        biomass,
        harvest_report,
        lice_count,
        behaviour_swim_speed,
        behaviour_breathing_index,
        welfare_scores,
    )
