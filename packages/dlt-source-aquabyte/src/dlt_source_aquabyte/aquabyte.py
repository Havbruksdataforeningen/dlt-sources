"""dlt source for the Aquabyte API v3.

Endpoints, params and record shapes: https://api.aquabyte.ai/v3/docs — committed as
`specs/openapi.json`, which `tests/test_param_surface.py` pins every signature against.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch
merged into the query string last. Bind them per resource or set them in config under
`[sources.aquabyte.<resource>]`; see the README. The window params are the exception:
they come from the resource's incremental, which is where a caller sets a window.
"""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
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


MAX_WINDOW_DAYS: dict[tuple[str, str | None], int] = {
    ("environmental", "15min"): 7,
    ("environmental", "h"): 31,
    ("environmental", "D"): 366,
    ("behaviour_swim_speed", "h"): 31,
    ("behaviour_swim_speed", "D"): 366,
    ("behaviour_breathing_index", "D"): 366,
    ("biomass", None): 366,
    ("lice_count", None): 366,
    ("welfare_scores", None): 366,
    ("harvest_report", None): 366,
}
"""How wide a window each resource accepts, in days, keyed by resource and `period`.

The resources split their own requests to stay inside these, so nothing here has to be
read to use the package. It is published for the caller who sizes chunks of its own — a
`--chunk-days` can be checked against it before spending a request.

The API refuses a wider window with `400 Requested time range is larger than N days`
rather than truncating it, and documents none of this: the numbers were measured against
the live API on 2026-08-27, boundaries inclusive. See `specs/README.md#api-quirks-worth-knowing`.
"""

DEFAULT_PERIOD = "D"
"""The grain the API computes when `period` is omitted, and so the cap an omitted one buys."""

# A resource or grain missing from the table gets the widest cap seen anywhere, which is
# also the one every endpoint has at its default grain. Guessing narrower would cost
# requests on a resource that never needed splitting.
_UNKNOWN_MAX_WINDOW_DAYS = 366


def _max_window_days(resource: str, period: str | None) -> int:
    """The cap for one resource at one grain."""
    if (resource, period) in MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS[(resource, period)]
    return MAX_WINDOW_DAYS.get((resource, DEFAULT_PERIOD), _UNKNOWN_MAX_WINDOW_DAYS)


def _parse_cursor(value: str) -> date:
    """A cursor value as the kind of point it is: a date, or a datetime for the time resources."""
    return datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)


def _now_like(sample: date) -> date:
    """Now, shaped like the cursor it will sit beside.

    The two behaviour endpoints report times with no zone, so a cursor read off their rows
    is naive; treat it as UTC, which is what the zoned endpoints use.
    """
    now = datetime.now(tz=UTC).replace(microsecond=0)
    if not isinstance(sample, datetime):
        return now.date()
    return now if sample.tzinfo is not None else now.replace(tzinfo=None)


def _format_like(value: date, sample: str) -> str:
    """`value`, spelled the way the cursor spells it — `Z` rather than `+00:00` where it uses one."""
    text = value.isoformat()
    return text.replace("+00:00", "Z") if sample.endswith("Z") else text


def _windows(
    resource: str,
    start_param: str,
    incremental: dlt.sources.incremental[str] | None,
    extra: dict[str, Any] | None,
    period: str | None = None,
) -> list[tuple[Any, Any]]:
    """The window of every request this resource must make, oldest first.

    Two things the API does make this arithmetic the resource's job. It refuses an over-wide
    window rather than truncating it, and it measures an open-ended one to today — so a
    pipeline that misses more days than its cap allows fails every night afterwards, wider
    each time, and cannot recover without a person. Only this layer knows both the endpoint
    and the resolved `period`, which is what the cap is keyed on.

    So every request carries an explicit end, and a span wider than the cap becomes several
    requests. Oldest first, because dlt advances the cursor as rows arrive: a run interrupted
    part-way resumes from the last row loaded rather than leaving a hole behind it.

    A caller sending a window param through `params` has taken the window over — that wins
    over every named param — so it is passed through as one request, unmeasured.
    """
    start = incremental.last_value if incremental is not None else None
    end = incremental.end_value if incremental is not None else None
    if extra and (start_param in extra or start_param.replace("from", "to") in extra):
        return [(start, end)]
    if not isinstance(start, str) or not isinstance(end, str | None):
        # Nothing this can measure. A missing start may still be fatal, but that is
        # `_windowed_query`'s call, after `params` has had its chance to supply one.
        return [(start, end)]

    first = _parse_cursor(start)
    last = _parse_cursor(end) if end is not None else _now_like(first)
    step = timedelta(days=_max_window_days(resource, period))
    end_text = end if end is not None else _format_like(last, start)

    try:
        inside_the_cap = last - first <= step
    except TypeError:
        # A start and an end of different kinds — a date against a timestamp, or a naive
        # time against a zoned one. Nothing to measure, so the window goes out as it came.
        return [(start, end)]
    # The caller's own edges are kept verbatim, so a window inside the cap is the request it
    # always was; only the edges this invents are spelled by `_format_like`.
    if inside_the_cap:
        return [(start, end_text)]

    edges: list[date] = [first]
    while edges[-1] + step < last:
        edges.append(edges[-1] + step)
    texts = [start, *(_format_like(edge, start) for edge in edges[1:]), end_text]
    return list(pairwise(texts))


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
        for start, end in _windows("environmental", "fromTime", incremental_from_time, params, period):
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
        for start, end in _windows("biomass", "fromDate", incremental_date, params):
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
        for start, end in _windows("harvest_report", "fromDate", incremental_slaughter_start_date, params):
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
        for start, end in _windows("lice_count", "fromDate", incremental_date, params):
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
        for start, end in _windows("behaviour_swim_speed", "fromTime", incremental_from_time, params, period):
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
        for start, end in _windows("behaviour_breathing_index", "fromTime", incremental_from_time, params):
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
        for start, end in _windows("welfare_scores", "fromDate", incremental_date, params):
            yield from client.paginate(
                "/welfareScores",
                params=_windowed_query("welfare_scores", "fromDate", params, penId=pen_id, fromDate=start, toDate=end),
                data_selector="welfareScores",
            )

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
