"""dlt source for the Aquabyte API v3 (https://api.aquabyte.ai/v3/docs).

Each resource takes exactly the params its endpoint documents in
`specs/openapi.json`, plus a `params` escape hatch; see the README.
"""

import logging
from collections.abc import Iterator
from typing import Any

import dlt
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
"""The API's `penId` query param: a single pen id, or the literal `"all"`.

A list is a source-side convenience only — it issues one request sequence per pen id
and yields every record the API returns for each. It filters nothing.
"""


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    """Build a query dict: drop unset named params, then merge the caller's passthrough last.

    `extra` is the per-endpoint escape hatch, so it wins over the named params and can
    carry query params this release does not know about.
    """
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _window_start(resource: str, param: str, explicit: str | None, cursor_value: str | None, fallback: str) -> str:
    """Choose a window start: an explicit override, else the incremental cursor, else config.

    A window start is always sent, so a run never silently inherits the API's own
    default window. dlt logs the requests and the row counts; what it cannot know is
    *why* a given window was asked for, which is what a failed or short run needs
    explaining.
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
    """Yield pages for each requested pen id.

    `penId` always comes from the `pen_id` argument; putting it in a resource's
    `params` passthrough has no effect.
    """
    pen_ids = [pen_id] if isinstance(pen_id, str) else list(pen_id)
    if len(pen_ids) > 1:
        logger.info("%s: fanning out over %d pen ids.", path, len(pen_ids))
    for pid in pen_ids:
        yield from client.paginate(
            path,
            params={**params, "penId": pid},
            data_selector=data_selector,
            paginator=paginator,
        )


@dlt.source(max_table_nesting=0)
def aquabyte_source(
    base_url: str = dlt.config.value,
    api_key: str = dlt.secrets.value,
    initial_date: str = dlt.config.value,
    initial_time: str = dlt.config.value,
):
    """Aquabyte API v3 dlt source.

    All resources share one RESTClient. Query params live on the resources, not here —
    bind them per resource, e.g. `source.biomass.bind(from_date="2026-01-01")`, or set
    them in config under `[sources.aquabyte.biomass]`.

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

    @dlt.resource(write_disposition="replace", columns=Site)
    def sites(site_id: str | None = None, params: dict[str, Any] | None = None):
        """Every site from `GET /sites`, or one from `GET /sites/{siteId}`.

        Pens stay nested inside each site, as the API nests them.

        Both endpoints write the same `sites` table, which is replaced on every run — so
        binding `site_id` leaves the table holding that one site. Bind it only when that
        is what you want stored.

        Args:
            site_id: `siteId`, the path param of the per-site endpoint. Omitted means every site.
            params: Query params passed through verbatim, merged last.
        """
        yield from client.paginate(
            f"/sites/{site_id}" if site_id is not None else "/sites",
            params=_query(params),
            data_selector="sites",
            paginator=SinglePagePaginator(),
        )

    @dlt.transformer(data_from=sites, write_disposition="replace", columns=Pen)
    def pens(sites_page: list[dict[str, Any]]):
        """Every pen the `/sites` response nests, unwrapped into its own table.

        Envelope unwrapping only: each pen object is yielded exactly as the API
        returned it, and no pen is filtered out.
        """
        for site in sites_page:
            yield from site.get("pens") or []

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=EnvironmentalDataPoint,
    )
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
        """Environmental readings from `GET /environmental`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_time: `fromTime` (ISO 8601). Defaults to the incremental cursor.
            to_time: `toTime` (ISO 8601, exclusive). Omitted means the API's default (today).
            period: `period` aggregation — `"15min"`, `"h"` or `"D"`. Omitted means the API's default (`"D"`).
            params: Query params passed through verbatim, merged last.
            incremental_from_time: Incremental cursor on `fromTime`.
        """
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
        """The latest environmental reading per pen from `GET /environmental/latest`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            params: Query params passed through verbatim, merged last.
        """
        yield from _paginate_per_pen(
            client,
            "/environmental/latest",
            pen_id=pen_id,
            params=_query(params),
            data_selector="data",
            paginator=SinglePagePaginator(),
        )

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date"],
        columns=BiomassDailyModel,
    )
    def biomass(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        bucket_size: int | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Daily biomass from `GET /biomass`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_date: `fromDate` (YYYY-MM-DD). Defaults to the incremental cursor.
            to_date: `toDate` (YYYY-MM-DD, inclusive). Omitted means the API's default (today).
            bucket_size: `bucketSize` in grams for `weightDist`. Omitted means the API's default (1000).
            params: Query params passed through verbatim, merged last.
            incremental_date: Incremental cursor on `date`.
        """
        window_start = _window_start("biomass", "fromDate", from_date, incremental_date.last_value, initial_date)
        yield from _paginate_per_pen(
            client,
            "/biomass",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date, bucketSize=bucket_size),
            data_selector="biomass",
        )

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "slaughterStartDate"],
        columns=BiomassHarvestReport,
    )
    def harvest_report(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_slaughter_start_date: dlt.sources.incremental[str] = dlt.sources.incremental(
            "slaughterStartDate", initial_value=initial_date
        ),
    ):
        """Harvest reports from `GET /biomass/harvestReport`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_date: `fromDate` (YYYY-MM-DD). Defaults to the incremental cursor.
            to_date: `toDate` (YYYY-MM-DD, inclusive). Omitted means the API's default (today).
            params: Query params passed through verbatim, merged last.
            incremental_slaughter_start_date: Incremental cursor on `slaughterStartDate`.
        """
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

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date"],
        columns=LiceCount,
    )
    def lice_count(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Lice counts from `GET /liceCount`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_date: `fromDate` (YYYY-MM-DD). Defaults to the incremental cursor.
            to_date: `toDate` (YYYY-MM-DD, inclusive). Omitted means the API's default (today).
            params: Query params passed through verbatim, merged last.
            incremental_date: Incremental cursor on `date`.
        """
        window_start = _window_start("lice_count", "fromDate", from_date, incremental_date.last_value, initial_date)
        yield from _paginate_per_pen(
            client,
            "/liceCount",
            pen_id=pen_id,
            params=_query(params, fromDate=window_start, toDate=to_date),
            data_selector="liceCount",
        )

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=BehaviorSwimSpeed,
    )
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
        """Swim speed and tilt from `GET /behaviour/swimSpeed`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_time: `fromTime` (ISO 8601). Defaults to the incremental cursor.
            to_time: `toTime` (ISO 8601, exclusive). Omitted means the API's default (today).
            period: `period` aggregation — `"h"` or `"D"`. Omitted means the API's default (`"D"`).
            params: Query params passed through verbatim, merged last.
            incremental_from_time: Incremental cursor on `fromTime`.
        """
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

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=BehaviorBreathingIndex,
    )
    def behaviour_breathing_index(
        pen_id: PenId = "all",
        from_time: str | None = None,
        to_time: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Breathing index from `GET /behaviour/breathingIndex`.

        The endpoint documents no `period` param, unlike `/behaviour/swimSpeed`.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_time: `fromTime` (ISO 8601). Defaults to the incremental cursor.
            to_time: `toTime` (ISO 8601, exclusive). Omitted means the API's default (today).
            params: Query params passed through verbatim, merged last.
            incremental_from_time: Incremental cursor on `fromTime`.
        """
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

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date"],
        columns=WelfareScoresRecord,
    )
    def welfare_scores(
        pen_id: PenId = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Welfare scores from `GET /welfareScores`, one row per pen and date.

        The nested `welfareScores` object lands as a single JSON column, categories and
        all — including any category added after this release. Flattening it into one
        row per category belongs in the consumer's transform layer.

        Args:
            pen_id: `penId`; `"all"` for every pen, or a list to fan out per pen.
            from_date: `fromDate` (YYYY-MM-DD). Defaults to the incremental cursor.
            to_date: `toDate` (YYYY-MM-DD, inclusive). Omitted means the API's default (today).
            params: Query params passed through verbatim, merged last.
            incremental_date: Incremental cursor on `date`.
        """
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
