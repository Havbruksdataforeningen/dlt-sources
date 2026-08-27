"""dlt source for the Aquabyte API v3.

Endpoints, params and record shapes: https://api.aquabyte.ai/v3/docs — committed as
`specs/openapi.json`, which `tests/test_param_surface.py` pins every signature against.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch
merged into the query string last. Bind them per resource or set them in config under
`[sources.aquabyte.<resource>]`; see the README. The window params are the exception:
they come from the resource's incremental, which is where a caller sets a window.

Column hints live in `columns.py`, and the window arithmetic in `windows.py`.
"""

from typing import Any

import dlt
from dlt.common.schema.typing import TScd2StrategyDict
from dlt.sources.helpers.rest_client.auth import APIKeyAuth
from dlt.sources.helpers.rest_client.client import RESTClient
from dlt.sources.helpers.rest_client.paginators import (
    JSONResponseCursorPaginator,
    SinglePagePaginator,
)

from dlt_source_aquabyte.columns import (
    BIOMASS_COLUMNS,
    BREATHING_INDEX_COLUMNS,
    ENVIRONMENTAL_COLUMNS,
    ENVIRONMENTAL_LATEST_COLUMNS,
    HARVEST_REPORT_COLUMNS,
    LICE_COUNT_COLUMNS,
    SITE_COLUMNS,
    SWIM_SPEED_COLUMNS,
    WELFARE_SCORES_COLUMNS,
)
from dlt_source_aquabyte.windows import windows

SCD2: TScd2StrategyDict = {"disposition": "merge", "strategy": "scd2"}
"""Registry tables are versioned, never replaced. Why, and how to take the other side:
`REFERENCE.md#the-site-registry-is-versioned`."""


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    """Drop unset named params, then merge the caller's passthrough last so it wins."""
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _windowed_queries(
    resource: str,
    start_param: str,
    incremental: dlt.sources.incremental[str] | None,
    extra: dict[str, Any] | None,
    **named: Any,
) -> list[dict[str, Any]]:
    """The query params of every request a windowed resource makes, oldest window first.

    A window start is the one thing a request may not go out without: the API would answer
    with a default window of its own, which nothing here chose.
    """
    end_param = start_param.replace("from", "to")
    spans = windows(resource, start_param, incremental, extra, named.get("period"))
    queries = [_query(extra, **named, **{start_param: start, end_param: end}) for start, end in spans]
    if any(query.get(start_param) is None for query in queries):
        config_key = "initial_time" if start_param == "fromTime" else "initial_date"
        raise ValueError(
            f"{resource}: the request carries no {start_param}. Set {config_key} under [sources.aquabyte] "
            f"to start the cursor, bind a window on the resource's incremental_* argument to backfill "
            f"(see REFERENCE.md), or send {start_param} yourself through params."
        )
    return queries


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
        for query in _windowed_queries(
            "environmental", "fromTime", incremental_from_time, params, penId=pen_id, period=period
        ):
            yield from client.paginate("/environmental", params=query, data_selector="data")

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
        for query in _windowed_queries(
            "biomass", "fromDate", incremental_date, params, penId=pen_id, bucketSize=bucket_size
        ):
            yield from client.paginate("/biomass", params=query, data_selector="biomass")

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
        for query in _windowed_queries(
            "harvest_report", "fromDate", incremental_slaughter_start_date, params, penId=pen_id
        ):
            yield from client.paginate(
                "/biomass/harvestReport",
                params=query,
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
        for query in _windowed_queries("lice_count", "fromDate", incremental_date, params, penId=pen_id):
            yield from client.paginate("/liceCount", params=query, data_selector="liceCount")

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
        for query in _windowed_queries(
            "behaviour_swim_speed", "fromTime", incremental_from_time, params, penId=pen_id, period=period
        ):
            yield from client.paginate("/behaviour/swimSpeed", params=query, data_selector="swimSpeed")

    @dlt.resource(write_disposition="merge", primary_key=["penId", "fromTime"], columns=BREATHING_INDEX_COLUMNS)
    def behaviour_breathing_index(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_from_time: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Breathing index from `GET /behaviour/breathingIndex`, which documents no `period`."""
        for query in _windowed_queries(
            "behaviour_breathing_index", "fromTime", incremental_from_time, params, penId=pen_id
        ):
            yield from client.paginate("/behaviour/breathingIndex", params=query, data_selector="breathingIndex")

    @dlt.resource(write_disposition="merge", primary_key=["penId", "date"], columns=WELFARE_SCORES_COLUMNS)
    def welfare_scores(
        pen_id: str = "all",
        params: dict[str, Any] | None = None,
        incremental_date: dlt.sources.incremental[str] | None = dlt.sources.incremental(
            "date", initial_value=initial_date
        ),
    ):
        """Welfare scores from `GET /welfareScores` — one row per pen and date, categories nested."""
        for query in _windowed_queries("welfare_scores", "fromDate", incremental_date, params, penId=pen_id):
            yield from client.paginate("/welfareScores", params=query, data_selector="welfareScores")

    return (
        sites,
        environmental,
        environmental_latest,
        biomass,
        harvest_report,
        lice_count,
        behaviour_swim_speed,
        behaviour_breathing_index,
        welfare_scores,
    )
