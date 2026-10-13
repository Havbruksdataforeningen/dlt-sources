"""Against the real Elhub API: `uv run pytest -m integration`.

Credentials come from dlt's config: `[sources.elhub.credentials]` in `.dlt/secrets.toml`, or
`SOURCES__ELHUB__CREDENTIALS__{CLIENT_ID,KID,PRIVATE_KEY}` and optionally `SOURCES__ELHUB__CONSUMER_ORG`.
Missing credentials fail, not skip. The tests read one day, never the history.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import dlt
import pytest

from dlt_source_elhub import elhub_source
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
    """Yesterday in Oslo as `[start, end)`."""
    today = datetime.now(OSLO).replace(hour=0, minute=0, second=0, microsecond=0)
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
    source.metering_values_hour.bind(start_date=start, end_date=end)
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
