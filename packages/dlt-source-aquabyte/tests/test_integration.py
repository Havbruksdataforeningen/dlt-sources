"""Integration tests against the real Aquabyte API.

Run with: python -m pytest -m integration

dlt resolves the API key automatically (env vars first, then secrets.toml).
Missing credentials cause a hard error — not a skip.

Every resource runs for every pen (`penId=all`) over a short window, bound the way
`examples/backfill.py` binds one: a `dlt.sources.incremental` carrying the window, so the
stored cursor is neither consulted nor advanced.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import dlt
import pytest

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import DATE_CURSOR, TIME_CURSOR, WINDOWED_ENDPOINTS, make_pipeline, query

pytestmark = [pytest.mark.integration]

# Three days: enough for every resource to have something, small enough to be quick.
_NOW = datetime.now(tz=UTC)
_THREE_DAYS_AGO = _NOW - timedelta(days=3)
LIVE_WINDOW = {
    DATE_CURSOR: (_THREE_DAYS_AGO.strftime("%Y-%m-%d"), _NOW.strftime("%Y-%m-%d")),
    TIME_CURSOR: (_THREE_DAYS_AGO.strftime("%Y-%m-%dT%H:%M:%SZ"), _NOW.strftime("%Y-%m-%dT%H:%M:%SZ")),
}


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    try:
        api_key = dlt.secrets.get("sources.aquabyte.api_key", str)
    except KeyError:
        api_key = None
    if not api_key:
        pytest.fail(
            "No Aquabyte API key found. Provide credentials via either:\n"
            "  - SOURCES__AQUABYTE__API_KEY environment variable\n"
            "  - .dlt/secrets.toml  (see .dlt/secrets.toml.example)"
        )


def _live_source() -> Any:
    """The source, with the live window bound on every resource that takes one."""
    source = aquabyte_source()
    for endpoint in WINDOWED_ENDPOINTS:
        start, end = LIVE_WINDOW[endpoint.cursor]
        window = dlt.sources.incremental(initial_value=start, end_value=end)
        source.resources[endpoint.resource].bind(**{endpoint.incremental_argument: window})
    return source


def _load(resource: str) -> Any:
    pipeline = make_pipeline(f"integ_{resource}")
    pipeline.run(_live_source().with_resources(resource))
    return pipeline


def _count(pipeline: Any, sql: str) -> int:
    return query(pipeline, sql)[0][0]


def test_sites_land_with_their_pens_nested():
    pipeline = _load("sites")

    assert _count(pipeline, "SELECT COUNT(*) FROM sites") > 0
    assert _count(pipeline, "SELECT COUNT(*) FROM sites WHERE json_array_length(pens) > 0") > 0


@pytest.mark.parametrize(
    "resource",
    [
        "environmental",
        "environmental_latest",
        "biomass",
        "lice_count",
        "behaviour_swim_speed",
        "behaviour_breathing_index",
    ],
)
def test_resource_loads_rows(resource):
    pipeline = _load(resource)

    assert _count(pipeline, f"SELECT COUNT(*) FROM {resource}") > 0


def test_harvest_report_is_answered():
    """Harvest reports are rare, so a window with no slaughter in it holds none. A refusal raises."""
    _load("harvest_report")


def test_welfare_scores_land_as_raw_records():
    """One row per pen and date, with the API's nested categories intact."""
    pipeline = _load("welfare_scores")

    duplicates = "SELECT pen_id, date FROM welfare_scores GROUP BY 1, 2 HAVING COUNT(*) > 1"
    assert _count(pipeline, f"SELECT COUNT(*) FROM ({duplicates})") == 0
    assert _count(pipeline, "SELECT COUNT(*) FROM welfare_scores WHERE welfare_scores IS NOT NULL") > 0


def test_every_resource_loads_in_one_run():
    pipeline = make_pipeline("integ_full_pipeline")
    pipeline.run(_live_source())

    assert _count(pipeline, "SELECT COUNT(*) FROM sites") > 0
    assert _count(pipeline, "SELECT COUNT(*) FROM biomass WHERE avg_weight > 0") > 0
