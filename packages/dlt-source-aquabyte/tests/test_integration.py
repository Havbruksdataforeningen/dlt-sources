"""Integration tests against the real Aquabyte API.

Run with: python -m pytest -m integration

dlt resolves the API key automatically (env vars first, then secrets.toml).
Missing credentials cause a hard error — not a skip.
"""

from datetime import UTC, datetime, timedelta

import dlt
import pytest

from dlt_source_aquabyte import aquabyte_source

# ---------------------------------------------------------------------------
# Credential check — fail loudly if missing
# ---------------------------------------------------------------------------


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

# Date/time ranges — keep tight to minimise API calls and runtime.
_NOW = datetime.now(tz=UTC)
_TO_DATE = _NOW.strftime("%Y-%m-%d")
_TO_TIME = _NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

# Discovery window (7 days) — just enough to find pens with fish.
_DISCOVERY_FROM_DATE = (_NOW - timedelta(days=7)).strftime("%Y-%m-%d")

# Per-resource test window (3 days) — keeps data volume small.
_FROM_DATE = (_NOW - timedelta(days=3)).strftime("%Y-%m-%d")
_FROM_TIME = (_NOW - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

_REQUIRED_LIVE_PENS = 2


def _make_pipeline(name: str) -> dlt.Pipeline:
    """Create a disposable DuckDB pipeline for a single integration test."""
    return dlt.pipeline(
        pipeline_name=f"integ_{name}",
        destination="duckdb",
        dataset_name=f"integ_{name}_data",
        dev_mode=True,
    )


# ---------------------------------------------------------------------------
# Discover live pens (pens with fish = recent biomass where avg_weight > 0)
# ---------------------------------------------------------------------------
_cached_live_pens: list[str] | None = None


def _discover_live_pens() -> list[str]:
    """Find pens that currently have fish by checking recent biomass data.

    Runs the biomass resource for all active pens over the last 7 days,
    then picks the first N pens where avg_weight > 0.
    """
    global _cached_live_pens
    if _cached_live_pens is not None:
        return _cached_live_pens

    pipeline = _make_pipeline("pen_discovery")
    source = aquabyte_source(from_date=_DISCOVERY_FROM_DATE, to_date=_TO_DATE)
    load_info = pipeline.run(source.with_resources("biomass"))
    assert load_info is not None

    with pipeline.sql_client() as client:
        rows = client.execute_sql(
            f"SELECT DISTINCT pen_id FROM biomass WHERE avg_weight > 0 LIMIT {_REQUIRED_LIVE_PENS}"
        )
        assert rows and len(rows) >= _REQUIRED_LIVE_PENS, (
            f"Need {_REQUIRED_LIVE_PENS} pens with fish (avg_weight > 0) in the last 7 days, "
            f"found {len(rows) if rows else 0}"
        )
        _cached_live_pens = [row[0] for row in rows]

    return _cached_live_pens


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Ensure credentials exist before any test in this module runs."""
    _require_credentials()


@pytest.fixture(scope="module")
def live_pen_ids(require_credentials) -> list[str]:
    """Two pen IDs that currently have fish (discovered via 7-day biomass window)."""
    return _discover_live_pens()


# ---------------------------------------------------------------------------
# Individual resource tests
# ---------------------------------------------------------------------------


class TestSites:
    def test_sites_loads(self):
        pipeline = _make_pipeline("sites")
        source = aquabyte_source()
        load_info = pipeline.run(source.with_resources("sites"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM sites")
            assert result and result[0][0] > 0, "Expected at least 1 site"


class TestPens:
    def test_pens_loads(self):
        """Verify the pens resource populates the pens table."""
        pipeline = _make_pipeline("pens")
        source = aquabyte_source()
        load_info = pipeline.run(source.with_resources("sites", "pens"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM pens")
            assert result and result[0][0] > 0, "Expected at least 1 active pen"


class TestEnvironmental:
    def test_environmental_loads(self, live_pen_ids):
        pipeline = _make_pipeline("environmental")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_time=_FROM_TIME,
            to_time=_TO_TIME,
        )
        load_info = pipeline.run(source.with_resources("environmental"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM environmental")
            assert result and result[0][0] > 0, f"Expected environmental data for live pens {live_pen_ids}"
            # Verify both pens are represented
            pen_result = client.execute_sql("SELECT DISTINCT pen_id FROM environmental ORDER BY pen_id")
            assert pen_result is not None
            loaded_pens = [row[0] for row in pen_result]
            assert len(loaded_pens) == len(live_pen_ids), (
                f"Expected data for {len(live_pen_ids)} pens, got {len(loaded_pens)}: {loaded_pens}"
            )


class TestEnvironmentalLatest:
    def test_environmental_latest_loads(self):
        pipeline = _make_pipeline("env_latest")
        source = aquabyte_source()
        load_info = pipeline.run(source.with_resources("environmental_latest"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM environmental_latest")
            assert result and result[0][0] > 0, "Expected at least 1 latest environmental reading"


class TestBiomass:
    def test_biomass_loads(self, live_pen_ids):
        pipeline = _make_pipeline("biomass")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_date=_FROM_DATE,
            to_date=_TO_DATE,
        )
        load_info = pipeline.run(source.with_resources("biomass"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM biomass WHERE avg_weight > 0")
            assert result and result[0][0] > 0, (
                f"Expected biomass rows with avg_weight > 0 for live pens {live_pen_ids}"
            )


class TestHarvestReport:
    def test_harvest_report_loads(self, live_pen_ids):
        pipeline = _make_pipeline("harvest_report")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_date=_FROM_DATE,
            to_date=_TO_DATE,
        )
        load_info = pipeline.run(source.with_resources("harvest_report"))
        assert load_info is not None
        # Harvest reports are rare — pens with fish haven't been harvested yet.
        # Just verify no errors.


class TestLiceCount:
    def test_lice_count_loads(self, live_pen_ids):
        pipeline = _make_pipeline("lice_count")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_date=_FROM_DATE,
            to_date=_TO_DATE,
        )
        load_info = pipeline.run(source.with_resources("lice_count"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM lice_count")
            assert result and result[0][0] > 0, f"Expected lice count data for live pens {live_pen_ids}"


class TestBehaviourSwimSpeed:
    def test_behaviour_swim_speed_loads(self, live_pen_ids):
        pipeline = _make_pipeline("behaviour_swim_speed")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_time=_FROM_TIME,
            to_time=_TO_TIME,
        )
        load_info = pipeline.run(source.with_resources("behaviour_swim_speed"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM behaviour_swim_speed")
            assert result and result[0][0] > 0, f"Expected swim speed data for live pens {live_pen_ids}"


class TestBehaviourBreathingIndex:
    def test_behaviour_breathing_index_loads(self, live_pen_ids):
        pipeline = _make_pipeline("behaviour_breathing_index")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_time=_FROM_TIME,
            to_time=_TO_TIME,
        )
        load_info = pipeline.run(source.with_resources("behaviour_breathing_index"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM behaviour_breathing_index")
            assert result and result[0][0] > 0, f"Expected breathing index data for live pens {live_pen_ids}"


class TestWelfareScores:
    def test_welfare_scores_loads(self, live_pen_ids):
        pipeline = _make_pipeline("welfare_scores")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_date=_FROM_DATE,
            to_date=_TO_DATE,
        )
        load_info = pipeline.run(source.with_resources("welfare_scores"))
        assert load_info is not None

        with pipeline.sql_client() as client:
            result = client.execute_sql("SELECT COUNT(*) FROM welfare_scores")
            assert result and result[0][0] > 0, f"Expected welfare scores for live pens {live_pen_ids}"


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_full_pipeline_with_live_pens(self, live_pen_ids):
        """Run the full aquabyte_source with 2 live pens over a 3-day window."""
        pipeline = _make_pipeline("full_pipeline")
        source = aquabyte_source(
            pen_ids=live_pen_ids,
            from_date=_FROM_DATE,
            to_date=_TO_DATE,
            from_time=_FROM_TIME,
            to_time=_TO_TIME,
        )
        load_info = pipeline.run(source)
        assert load_info is not None

        with pipeline.sql_client() as client:
            # Sites always has data
            result = client.execute_sql("SELECT COUNT(*) FROM sites")
            assert result and result[0][0] > 0, "Expected sites data"

            # Pens table should contain exactly our 2 live pens
            result = client.execute_sql("SELECT DISTINCT id FROM pens ORDER BY id")
            assert result is not None
            loaded_pens = sorted(row[0] for row in result)
            assert loaded_pens == sorted(live_pen_ids), f"Expected pens {sorted(live_pen_ids)}, got {loaded_pens}"

            # Biomass must have data (that's how we discovered these pens)
            result = client.execute_sql("SELECT COUNT(*) FROM biomass WHERE avg_weight > 0")
            assert result and result[0][0] > 0, "Expected biomass data for live pens"
