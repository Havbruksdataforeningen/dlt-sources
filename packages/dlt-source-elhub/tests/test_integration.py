"""Integration tests against the real Elhub API.

Run with: uv run pytest -m integration

Credentials come from dlt's config — a `.dlt/secrets.toml` with `[sources.elhub.credentials]`,
or the environment:

    SOURCES__ELHUB__CREDENTIALS__CLIENT_ID
    SOURCES__ELHUB__CREDENTIALS__KID
    SOURCES__ELHUB__CREDENTIALS__PRIVATE_KEY
    SOURCES__ELHUB__CONSUMER_ORG      # optional: a company that delegated the scope

Missing credentials cause a hard error — not a skip. The tests read one day, never the
history: a bound window on one metering point, and the list call for the last 24 hours.
"""

from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import dlt
import pytest
from dlt.common import pendulum

from dlt_source_elhub import ALL_RETAINED_HISTORY, elhub_source
from tests.conftest import cursors, make_pipeline, query, row_count

pytestmark = [pytest.mark.integration]

OSLO = ZoneInfo("Europe/Oslo")


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    try:
        client_id = dlt.secrets.get("sources.elhub.credentials.client_id", str)
    except KeyError:
        client_id = None
    if not client_id:
        pytest.fail(
            "No Maskinporten client found. Provide credentials via either:\n"
            "  - SOURCES__ELHUB__CREDENTIALS__{CLIENT_ID,KID,PRIVATE_KEY} environment variables\n"
            "  - .dlt/secrets.toml  (see .dlt/secrets.toml.example)"
        )


def _yesterday() -> tuple[str, str]:
    """Yesterday in Oslo, as a half-open window of API dates."""
    today = pendulum.now(OSLO).start_of("day")
    return (today - timedelta(days=1)).isoformat(), today.isoformat()


def test_the_list_call_discovers_metering_points_with_values_in_the_last_24_hours():
    pipeline = make_pipeline("integ_points")
    pipeline.run(elhub_source(user_agent="dlt-source-elhub-tests").with_resources("metering_points"))

    assert row_count(pipeline, "metering_points") > 0
    (row,) = query(pipeline, "SELECT id FROM metering_points LIMIT 1")
    assert len(row[0]) == 18, "a metering point id is 18 digits"


def test_a_bound_window_on_one_point_loads_that_day_and_leaves_no_cursor():
    start, end = _yesterday()
    source: Any = elhub_source(user_agent="dlt-source-elhub-tests")
    source.metering_values_hour.bind(start_date=start, end_date=end, insert_date_time=ALL_RETAINED_HISTORY)
    pipeline = make_pipeline("integ_window")
    pipeline.run(source.with_resources("metering_values_hour"))

    assert cursors(pipeline) == {}
    (resolutions,) = query(pipeline, "SELECT STRING_AGG(DISTINCT resolution, ',') FROM metering_values_hour")
    assert set(resolutions[0].split(",")) <= {"PT60M", "PT15M"}
    per_point = query(
        pipeline,
        "SELECT metering_point_id, COUNT(*), MIN(start_time), MAX(start_time) FROM metering_values_hour GROUP BY 1",
    )
    assert per_point
    for _point, count, first, last in per_point:
        assert count in (24, 96), f"a whole day is 24 hourly or 96 quarter-hourly values, got {count}"
        assert first == start
        assert last < end
