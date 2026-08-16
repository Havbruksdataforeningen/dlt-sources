"""dlt source for the Aquabyte API v3.

Endpoints, params and record shapes: https://api.aquabyte.ai/v3/docs — committed as
`specs/openapi.json`, which `tests/test_param_surface.py` pins every signature against.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch
merged into the query string last. Bind them per resource or set them in config under
`[sources.aquabyte.<resource>]`; see the README.
"""

import hashlib
import json
import logging
from collections.abc import Iterator
from typing import Any

import dlt
from dlt.common.schema.typing import TScd2StrategyDict
from dlt.sources.helpers.rest_client.auth import APIKeyAuth
from dlt.sources.helpers.rest_client.client import RESTClient
from dlt.sources.helpers.rest_client.paginators import (
    BasePaginator,
    JSONResponseCursorPaginator,
    SinglePagePaginator,
)

from dlt_source_aquabyte.schemas import (
    BehaviorBreathingIndex,
    BehaviorSwimSpeed,
    BiomassDailyModel,
    BiomassHarvestReport,
    EnvironmentalDataLive,
    EnvironmentalDataPoint,
    LiceCount,
    Pen,
    Site,
    WelfareScoresRecord,
)

logger = logging.getLogger(__name__)

PenId = str | list[str]
"""A single pen id or the literal `"all"`. A list is request fan-out — it filters nothing."""

SCD2: TScd2StrategyDict = {"disposition": "merge", "strategy": "scd2"}
"""Registry tables are versioned, never replaced: a row is retired, never deleted.

Always paired with `merge_key="id"`, which scopes retirement to the ids a load carried,
so reading one site does not retire the others. The trade-off, and how to take the other
side, are in the README. https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy
"""

SITE_VERSION_COLUMN = "_site_version"
SITES_SCD2: TScd2StrategyDict = {**SCD2, "row_version_column_name": SITE_VERSION_COLUMN}
"""As `SCD2`, but a site versions on its own fields only.

dlt's default row hash covers the whole record, nested data included, so a renamed pen
would otherwise version its site too. Pens have their own scd2 table for that.
"""


def _site_version(site: dict[str, Any]) -> str:
    """Digest of everything the API returns for a site except `pens`."""
    own = {key: value for key, value in site.items() if key != "pens"}
    return hashlib.sha256(json.dumps(own, sort_keys=True, default=str).encode()).hexdigest()


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    """Drop unset named params, then merge the caller's passthrough last so it wins."""
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _window_start(resource: str, param: str, explicit: str | None, cursor_value: str | None, fallback: str) -> str:
    """An explicit override, else the incremental cursor, else config — never nothing.

    A window start is always sent, so a run cannot silently inherit the API's own default
    window. dlt logs the requests; what it cannot know is *why* a window was asked for.
    """
    if explicit is not None:
        logger.info("%s: %s=%s passed explicitly; the incremental cursor is ignored.", resource, param, explicit)
        return explicit
    if cursor_value is None:
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
    initial_date: str = dlt.config.value,
    initial_time: str = dlt.config.value,
):
    """Aquabyte API v3 dlt source. All resources share one RESTClient.

    Args:
        base_url: API base URL, from config.
        api_key: API key, from secrets.
        initial_date: Cursor start for the date-based resources (YYYY-MM-DD).
        initial_time: Cursor start for the time-based resources (ISO 8601).
    """
    client = RESTClient(
        base_url=base_url,
        auth=APIKeyAuth(name="apikey", api_key=api_key, location="header"),
        paginator=JSONResponseCursorPaginator(cursor_path="nextToken", cursor_param="nextToken"),
    )

    @dlt.resource(write_disposition=SITES_SCD2, merge_key="id", columns=Site)
    def sites(site_id: str | None = None, params: dict[str, Any] | None = None):
        """Every site from `GET /sites`, or one from `GET /sites/{siteId}` when `site_id` is bound.

        Both endpoints write the same table. Pens stay nested as the API nests them, but
        do not version the site — see `SITES_SCD2`.
        """
        pages = client.paginate(
            f"/sites/{site_id}" if site_id is not None else "/sites",
            params=_query(params),
            data_selector="sites",
            paginator=SinglePagePaginator(),
        )
        for page in pages:
            yield [{**site, SITE_VERSION_COLUMN: _site_version(site)} for site in page]

    # `dlt.transformer` types write_disposition as the literals only, unlike `dlt.resource`;
    # both hand it to the same hint machinery, so the dict is fine at runtime.
    @dlt.transformer(data_from=sites, write_disposition=SCD2, merge_key="id", columns=Pen)  # type: ignore[arg-type]
    def pens(sites_page: list[dict[str, Any]]):
        """Every pen the `/sites` response nests, unwrapped into its own table — none filtered.

        Versioned because a pen leaves `/sites` once it is emptied, and its history has to
        outlive it.
        """
        for site in sites_page:
            yield from site.get("pens") or []

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=EnvironmentalDataPoint)
    def environmental(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Environmental readings from `GET /environmental`."""
        window_start = _window_start(
            "environmental", "fromTime", from_time, incremental_from_time.last_value, initial_time
        )
        yield from _paginate_per_pen(
            client,
            "/environmental",
            pen_id=pen_id,
            params=_query(params, fromTime=window_start, toTime=to_time, period=period),
            data_selector="data",
        )

    @dlt.resource(write_disposition="replace", columns=EnvironmentalDataLive)
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

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=BiomassDailyModel)
    def biomass(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        bucket_size: int | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Daily biomass from `GET /biomass`."""
        window_start = _window_start("biomass", "fromDate", from_date, incremental_date.last_value, initial_date)
        yield from _paginate_per_pen(
            client,
            "/biomass",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date, bucketSize=bucket_size),
            data_selector="biomass",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "slaughterStartDate"], columns=BiomassHarvestReport)
    def harvest_report(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_slaughter_start_date: dlt.sources.incremental[str] = dlt.sources.incremental(
            "slaughterStartDate", initial_value=initial_date
        ),
    ):
        """Harvest reports from `GET /biomass/harvestReport`."""
        window_start = _window_start(
            "harvest_report", "fromDate", from_date, incremental_slaughter_start_date.last_value, initial_date
        )
        yield from _paginate_per_pen(
            client,
            "/biomass/harvestReport",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date),
            data_selector="reports",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=LiceCount)
    def lice_count(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Lice counts from `GET /liceCount`."""
        window_start = _window_start("lice_count", "fromDate", from_date, incremental_date.last_value, initial_date)
        yield from _paginate_per_pen(
            client,
            "/liceCount",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date),
            data_selector="liceCount",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=BehaviorSwimSpeed)
    def behaviour_swim_speed(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        period: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Swim speed and tilt from `GET /behaviour/swimSpeed`."""
        window_start = _window_start(
            "behaviour_swim_speed", "fromTime", from_time, incremental_from_time.last_value, initial_time
        )
        yield from _paginate_per_pen(
            client,
            "/behaviour/swimSpeed",
            pen_id=pen_id,
            params=_query(params, fromTime=window_start, toTime=to_time, period=period),
            data_selector="swimSpeed",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=BehaviorBreathingIndex)
    def behaviour_breathing_index(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Breathing index from `GET /behaviour/breathingIndex`, which documents no `period`."""
        window_start = _window_start(
            "behaviour_breathing_index", "fromTime", from_time, incremental_from_time.last_value, initial_time
        )
        yield from _paginate_per_pen(
            client,
            "/behaviour/breathingIndex",
            pen_id=pen_id,
            params=_query(params, fromTime=window_start, toTime=to_time),
            data_selector="breathingIndex",
        )

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=WelfareScoresRecord)
    def welfare_scores(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Welfare scores from `GET /welfareScores` — one row per pen and date, categories nested."""
        window_start = _window_start("welfare_scores", "fromDate", from_date, incremental_date.last_value, initial_date)
        yield from _paginate_per_pen(
            client,
            "/welfareScores",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date),
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
