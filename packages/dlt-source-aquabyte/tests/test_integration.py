"""Integration tests against the real Aquabyte API.

Run with: python -m pytest -m integration

dlt resolves the API key automatically (env vars first, then secrets.toml).
Missing credentials cause a hard error — not a skip.

Every resource runs for every pen (`penId=all`) over a short window, bound the way
`examples/backfill.py` binds one: a `dlt.sources.incremental` carrying the window, so the
stored cursor is neither consulted nor advanced. The assertion is that rows landed.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import dlt
import pytest

from dlt_source_aquabyte import aquabyte_source


def _require_credentials() -> None:
    """Fail fast if dlt cannot resolve the API key from any provider."""
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


pytestmark = [pytest.mark.integration]

# A three-day window — enough for every resource to have something, small enough to be quick.
_NOW = datetime.now(tz=UTC)
_DATE_WINDOW = ((_NOW - timedelta(days=3)).strftime("%Y-%m-%d"), _NOW.strftime("%Y-%m-%d"))
_TIME_WINDOW = ((_NOW - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"), _NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))

# Resource → the `incremental_*` argument its window is bound on, as in examples/backfill.py.
_DATE_BASED = {
    "biomass": "incremental_date",
    "harvest_report": "incremental_slaughter_start_date",
    "lice_count": "incremental_date",
    "welfare_scores": "incremental_date",
}
_TIME_BASED = {
    "environmental": "incremental_from_time",
    "behaviour_swim_speed": "incremental_from_time",
    "behaviour_breathing_index": "incremental_from_time",
}


def _make_pipeline(name: str) -> dlt.Pipeline:
    """Create a disposable DuckDB pipeline for a single integration test."""
    return dlt.pipeline(
        pipeline_name=f"integ_{name}",
        destination="duckdb",
        dataset_name=f"integ_{name}_data",
        dev_mode=True,
    )


def _window_for(resource_name: str) -> dict[str, Any]:
    """The bound backfill window for a resource, ready to pass to `bind`."""
    if resource_name in _DATE_BASED:
        argument, (start, end) = _DATE_BASED[resource_name], _DATE_WINDOW
    else:
        argument, (start, end) = _TIME_BASED[resource_name], _TIME_WINDOW
    return {argument: dlt.sources.incremental(initial_value=start, end_value=end)}


def _source_with_window(resource_name: str):
    """A source whose named resource reads the test window for every pen."""
    source = aquabyte_source()
    source.resources[resource_name].bind(**_window_for(resource_name))
    return source


def _count(pipeline: dlt.Pipeline, sql: str) -> int:
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result[0][0]


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Ensure credentials exist before any test in this module runs."""
    _require_credentials()


class TestSites:
    def test_sites_loads(self):
        pipeline = _make_pipeline("sites")
        load_info = pipeline.run(aquabyte_source().with_resources("sites"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM sites") > 0, "Expected at least 1 site"


class TestPens:
    def test_pens_loads(self):
        """Verify the pens resource populates the pens table."""
        pipeline = _make_pipeline("pens")
        load_info = pipeline.run(aquabyte_source().with_resources("sites", "pens"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM pens") > 0, "Expected at least 1 pen"


class TestEnvironmental:
    def test_environmental_loads(self):
        pipeline = _make_pipeline("environmental")
        load_info = pipeline.run(_source_with_window("environmental").with_resources("environmental"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM environmental") > 0, "Expected environmental data"


class TestEnvironmentalLatest:
    def test_environmental_latest_loads(self):
        pipeline = _make_pipeline("env_latest")
        load_info = pipeline.run(aquabyte_source().with_resources("environmental_latest"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM environmental_latest") > 0, (
            "Expected at least 1 latest environmental reading"
        )


class TestBiomass:
    def test_biomass_loads(self):
        pipeline = _make_pipeline("biomass")
        load_info = pipeline.run(_source_with_window("biomass").with_resources("biomass"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM biomass WHERE avg_weight > 0") > 0, (
            "Expected biomass rows with avg_weight > 0"
        )


class TestHarvestReport:
    def test_harvest_report_loads(self):
        pipeline = _make_pipeline("harvest_report")
        load_info = pipeline.run(_source_with_window("harvest_report").with_resources("harvest_report"))
        assert load_info is not None
        # Harvest reports are rare — a window with no slaughter in it holds none.
        # Just verify no errors.


class TestLiceCount:
    def test_lice_count_loads(self):
        pipeline = _make_pipeline("lice_count")
        load_info = pipeline.run(_source_with_window("lice_count").with_resources("lice_count"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM lice_count") > 0, "Expected lice count data"


class TestBehaviourSwimSpeed:
    def test_behaviour_swim_speed_loads(self):
        pipeline = _make_pipeline("behaviour_swim_speed")
        load_info = pipeline.run(_source_with_window("behaviour_swim_speed").with_resources("behaviour_swim_speed"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM behaviour_swim_speed") > 0, "Expected swim speed data"


class TestBehaviourBreathingIndex:
    def test_behaviour_breathing_index_loads(self):
        pipeline = _make_pipeline("behaviour_breathing_index")
        source = _source_with_window("behaviour_breathing_index")
        load_info = pipeline.run(source.with_resources("behaviour_breathing_index"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM behaviour_breathing_index") > 0, "Expected breathing index data"


class TestWelfareScores:
    def test_welfare_scores_loads(self):
        pipeline = _make_pipeline("welfare_scores")
        load_info = pipeline.run(_source_with_window("welfare_scores").with_resources("welfare_scores"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM welfare_scores") > 0, "Expected welfare scores"

    def test_welfare_scores_land_as_raw_records(self):
        """One row per pen and date, with the API's nested categories intact."""
        pipeline = _make_pipeline("welfare_scores_raw")
        assert pipeline.run(_source_with_window("welfare_scores").with_resources("welfare_scores")) is not None

        duplicates = _count(
            pipeline,
            "SELECT COUNT(*) FROM (SELECT pen_id, date FROM welfare_scores GROUP BY 1, 2 HAVING COUNT(*) > 1)",
        )
        assert duplicates == 0, "welfare_scores must hold one row per pen and date"

        with pipeline.sql_client() as client:
            rows = client.execute_sql("SELECT welfare_scores FROM welfare_scores WHERE welfare_scores IS NOT NULL")
            assert rows, "Expected at least one row carrying the nested welfareScores object"


class TestFullPipeline:
    def test_full_pipeline(self):
        """Run the full aquabyte_source over the test window."""
        pipeline = _make_pipeline("full_pipeline")
        source = aquabyte_source()
        for resource_name in (*_DATE_BASED, *_TIME_BASED):
            source.resources[resource_name].bind(**_window_for(resource_name))

        load_info = pipeline.run(source)
        assert load_info is not None

        assert _count(pipeline, "SELECT COUNT(*) FROM sites") > 0, "Expected sites data"
        assert _count(pipeline, "SELECT COUNT(*) FROM pens") > 0, "Expected pens data"
        assert _count(pipeline, "SELECT COUNT(*) FROM biomass WHERE avg_weight > 0") > 0, "Expected biomass data"
