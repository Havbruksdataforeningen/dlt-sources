"""dlt source for the Aquabyte API v3.

Endpoints, params and record shapes: https://api.aquabyte.ai/v3/docs — committed as
`specs/openapi.json`, which `tests/test_param_surface.py` pins every signature against.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch
merged into the query string last. Bind them per resource or set them in config under
`[sources.aquabyte.<resource>]`; see the README. The window params are the exception:
they come from the resource's incremental, which is where a caller sets a window.
"""

from typing import Any

import dlt
from dlt.common.schema.typing import TScd2StrategyDict, TTableSchemaColumns
from dlt.sources.helpers.rest_client.auth import APIKeyAuth
from dlt.sources.helpers.rest_client.client import RESTClient
from dlt.sources.helpers.rest_client.paginators import (
    JSONResponseCursorPaginator,
    SinglePagePaginator,
)

SCD2: TScd2StrategyDict = {"disposition": "merge", "strategy": "scd2"}
"""Registry tables are versioned, never replaced: a row is retired, never deleted.

Always paired with `merge_key="id"`, which scopes retirement to the ids a load carried,
so reading one site does not retire the others. The trade-off, and how to take the other
side, are in `REFERENCE.md`. https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy
"""


# Column hints, one mapping per resource: the API's own field names, typed per
# `specs/openapi.json` and checked against it by `tests/test_mock_fidelity.py`.
#
# They buy one thing — a column keeps its type when the first page is all nulls, or the
# field is missing entirely. A field with no entry still lands, typed from the data, and
# nested fields have none, so `max_table_nesting` alone decides their shape.
# `nullable: False` marks the fields the spec requires and forbids to be null.

SITE_COLUMNS: TTableSchemaColumns = {
    "id": {"data_type": "text", "nullable": False},
    "name": {"data_type": "text", "nullable": False},
    "governmentSiteNumber": {"data_type": "bigint"},
    "external_site_id": {"data_type": "text"},
}

PEN_COLUMNS: TTableSchemaColumns = {
    "id": {"data_type": "text", "nullable": False},
    "name": {"data_type": "text", "nullable": False},
    "penCode": {"data_type": "text"},
    "isActive": {"data_type": "bool", "nullable": False},
    "external_id": {"data_type": "text"},
}

ENVIRONMENTAL_COLUMNS: TTableSchemaColumns = {
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

ENVIRONMENTAL_LATEST_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text"},
    "time": {"data_type": "text", "nullable": False},
    "temperature": {"data_type": "double"},
    "cameraDepth": {"data_type": "double"},
    "oxygenPct": {"data_type": "double"},
    "salinity": {"data_type": "double"},
}

BIOMASS_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double"},
    "avgWeight": {"data_type": "double"},
    "kFactor": {"data_type": "double"},
    "cv": {"data_type": "double"},
}

HARVEST_REPORT_COLUMNS: TTableSchemaColumns = {
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

LICE_COUNT_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "adultFemale": {"data_type": "double"},
    "adultFemaleConverted": {"data_type": "double"},
    "mobile": {"data_type": "double"},
    "mobileConverted": {"data_type": "double"},
    "caligus": {"data_type": "double"},
}

SWIM_SPEED_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "swimSpeedsampleSize": {"data_type": "double", "nullable": False},
    "swimSpeed": {"data_type": "double"},
    "swimTiltsampleSize": {"data_type": "double", "nullable": False},
    "swimTilt": {"data_type": "double"},
}

BREATHING_INDEX_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "breathingIndex": {"data_type": "double"},
}

WELFARE_SCORES_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
}


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    """Drop unset named params, then merge the caller's passthrough last so it wins."""
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _windowed_query(resource: str, start_param: str, extra: dict[str, Any] | None, **named: Any) -> dict[str, Any]:
    """`_query`, plus the one guarantee the windowed resources keep: a window start is sent.

    Without one the API serves its own default window, which nothing here chose.
    """
    query = _query(extra, **named)
    if query.get(start_param) is None:
        config_key = "initial_time" if start_param == "fromTime" else "initial_date"
        raise ValueError(
            f"{resource}: the request carries no {start_param}. Set {config_key} under [sources.aquabyte] "
            f"to start the cursor, bind a window on the resource's incremental_* argument to backfill "
            f"(see REFERENCE.md), or send {start_param} yourself through params."
        )
    return query


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
        pen_id: str = "all",
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Environmental readings from `GET /environmental`."""
        start = incremental_from_time.last_value if incremental_from_time is not None else None
        end = incremental_from_time.end_value if incremental_from_time is not None else None
        yield from client.paginate(
            "/environmental",
            params=_windowed_query(
                "environmental", "fromTime", params, penId=pen_id, fromTime=start, toTime=end, period=period
            ),
            data_selector="data",
        )

    @dlt.resource(write_disposition="replace", columns=ENVIRONMENTAL_LATEST_COLUMNS)
    def environmental_latest(pen_id: str = "all", params: dict[str, Any] | None = None):
        """The latest environmental reading per pen from `GET /environmental/latest`."""
        yield from client.paginate(
            "/environmental/latest",
            params=_query(params, penId=pen_id),
            data_selector="data",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=BIOMASS_COLUMNS)
    def biomass(
        pen_id: str = "all",
        bucket_size: int | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Daily biomass from `GET /biomass`."""
        start = incremental_date.last_value if incremental_date is not None else None
        end = incremental_date.end_value if incremental_date is not None else None
        yield from client.paginate(
            "/biomass",
            params=_windowed_query(
                "biomass", "fromDate", params, penId=pen_id, fromDate=start, toDate=end, bucketSize=bucket_size
            ),
            data_selector="biomass",
        )

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "slaughterStartDate", "mainReport", "asOfDate"],
        columns=HARVEST_REPORT_COLUMNS,
    )
    def harvest_report(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_slaughter_start_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "slaughterStartDate", initial_value=initial_date
        ),
    ):
        """Harvest reports from `GET /biomass/harvestReport`."""
        start = incremental_slaughter_start_date.last_value if incremental_slaughter_start_date is not None else None
        end = incremental_slaughter_start_date.end_value if incremental_slaughter_start_date is not None else None
        yield from client.paginate(
            "/biomass/harvestReport",
            params=_windowed_query("harvest_report", "fromDate", params, penId=pen_id, fromDate=start, toDate=end),
            data_selector="reports",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=LICE_COUNT_COLUMNS)
    def lice_count(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Lice counts from `GET /liceCount`."""
        start = incremental_date.last_value if incremental_date is not None else None
        end = incremental_date.end_value if incremental_date is not None else None
        yield from client.paginate(
            "/liceCount",
            params=_windowed_query("lice_count", "fromDate", params, penId=pen_id, fromDate=start, toDate=end),
            data_selector="liceCount",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime", "toTime"], columns=SWIM_SPEED_COLUMNS)
    def behaviour_swim_speed(
        pen_id: str = "all",
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Swim speed and tilt from `GET /behaviour/swimSpeed`."""
        start = incremental_from_time.last_value if incremental_from_time is not None else None
        end = incremental_from_time.end_value if incremental_from_time is not None else None
        yield from client.paginate(
            "/behaviour/swimSpeed",
            params=_windowed_query(
                "behaviour_swim_speed", "fromTime", params, penId=pen_id, fromTime=start, toTime=end, period=period
            ),
            data_selector="swimSpeed",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=BREATHING_INDEX_COLUMNS)
    def behaviour_breathing_index(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Breathing index from `GET /behaviour/breathingIndex`, which documents no `period`."""
        start = incremental_from_time.last_value if incremental_from_time is not None else None
        end = incremental_from_time.end_value if incremental_from_time is not None else None
        yield from client.paginate(
            "/behaviour/breathingIndex",
            params=_windowed_query(
                "behaviour_breathing_index", "fromTime", params, penId=pen_id, fromTime=start, toTime=end
            ),
            data_selector="breathingIndex",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=WELFARE_SCORES_COLUMNS)
    def welfare_scores(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Welfare scores from `GET /welfareScores` — one row per pen and date, categories nested."""
        start = incremental_date.last_value if incremental_date is not None else None
        end = incremental_date.end_value if incremental_date is not None else None
        yield from client.paginate(
            "/welfareScores",
            params=_windowed_query("welfare_scores", "fromDate", params, penId=pen_id, fromDate=start, toDate=end),
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
