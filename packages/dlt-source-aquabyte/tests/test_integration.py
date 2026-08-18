"""Integration tests against the real Aquabyte API.

Run with: python -m pytest -m integration

dlt resolves the API key automatically (env vars first, then secrets.toml).
Missing credentials cause a hard error — not a skip.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import dlt
import pytest
import requests

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

_DATE_WINDOW = {"from_date": _FROM_DATE, "to_date": _TO_DATE}
_TIME_WINDOW = {"from_time": _FROM_TIME, "to_time": _TO_TIME}


def _make_pipeline(name: str) -> dlt.Pipeline:
    """Create a disposable DuckDB pipeline for a single integration test."""
    return dlt.pipeline(
        pipeline_name=f"integ_{name}",
        destination="duckdb",
        dataset_name=f"integ_{name}_data",
        dev_mode=True,
    )


def _source_with(resource_name: str, **bound: Any):
    """A source with `resource_name`'s query params bound, since params live per resource."""
    source = aquabyte_source()
    source.resources[resource_name].bind(**bound)
    return source


def _raw_get(path: str, params: dict[str, Any]):
    """One unmediated request, for asserting on status codes the source never surfaces.

    The source drops unset params and always sends a window, so a malformed or empty
    value cannot be produced through it — but the API's handling of one is still a claim
    the report makes, and claims about the API get checked against the API.

    Plain `requests`, deliberately, rather than `dlt.sources.helpers.requests`: that
    wrapper raises on a 4xx and retries first, and here the 4xx *is* the observation.
    """
    base_url = dlt.config["sources.aquabyte.base_url"].rstrip("/")
    api_key = dlt.secrets["sources.aquabyte.api_key"]
    return requests.get(f"{base_url}{path}", params=params, headers={"apikey": api_key}, timeout=120)


def _count(pipeline: dlt.Pipeline, sql: str) -> int:
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result[0][0]


# ---------------------------------------------------------------------------
# Discover live pens (pens with fish = recent biomass where avg_weight > 0)
# ---------------------------------------------------------------------------
_cached_live_pens: list[str] | None = None


def _discover_live_pens() -> list[str]:
    """Find pens that currently have fish by checking recent biomass data.

    Runs the biomass resource for all pens over the last 7 days, then picks the
    first N pens where avg_weight > 0.
    """
    global _cached_live_pens
    if _cached_live_pens is not None:
        return _cached_live_pens

    pipeline = _make_pipeline("pen_discovery")
    source = _source_with("biomass", from_date=_DISCOVERY_FROM_DATE, to_date=_TO_DATE)
    load_info = pipeline.run(source.with_resources("biomass"))
    assert load_info is not None

    with pipeline.sql_client() as client:
        # ORDER BY, because an unordered LIMIT picks a different pair of pens on each
        # run — which made the environmental assertion below fail intermittently and
        # left the failure impossible to reproduce.
        rows = client.execute_sql(
            f"SELECT DISTINCT pen_id FROM biomass WHERE avg_weight > 0 ORDER BY pen_id LIMIT {_REQUIRED_LIVE_PENS}"
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
    def test_environmental_loads(self, live_pen_ids):
        pipeline = _make_pipeline("environmental")
        source = _source_with("environmental", pen_id=live_pen_ids, **_TIME_WINDOW)
        load_info = pipeline.run(source.with_resources("environmental"))
        assert load_info is not None

        assert _count(pipeline, "SELECT COUNT(*) FROM environmental") > 0, (
            f"Expected environmental data for live pens {live_pen_ids}"
        )

        # Carrying biomass does not oblige a pen to have environmental readings in this
        # tighter window, so requiring every pen to return rows is not a claim the API
        # makes. What must hold is that the fan-out asked only for the pens we bound.
        with pipeline.sql_client() as client:
            rows = client.execute_sql("SELECT DISTINCT pen_id FROM environmental")
            assert rows is not None
            loaded_pens = {row[0] for row in rows}
        assert loaded_pens <= set(live_pen_ids), f"Got data for pens we did not ask for: {loaded_pens}"


class TestParameterNullability:
    """Does the API tell a nullable window parameter from a non-nullable one?

    `/biomass/harvestReport` declares `fromDate` as a bare string and `toDate` as
    `anyOf: [string, null]`, while every comparable parameter elsewhere is nullable.
    Both sit on one handler, which makes them the cleanest control available: if the
    declaration meant anything, it would show up here.

    Omitting a parameter cannot tell them apart — both are `required: false` — so this
    probes the cases that could: an empty value and a literal `null`.
    """

    @pytest.mark.parametrize("param", ["fromDate", "toDate"])
    @pytest.mark.parametrize("value", ["", "null"])
    def test_neither_declaration_accepts_an_empty_or_null_window(self, param, value):
        """Report finding 5: the nullable declaration does not describe the behaviour."""
        response = _raw_get("/biomass/harvestReport", {"penId": "all", param: value})
        assert response.status_code == 422, (
            f"{param}={value!r} returned {response.status_code}; the report says every "
            "window parameter rejects an empty or null value regardless of its declaration"
        )

    @pytest.mark.parametrize("param", ["fromDate", "toDate"])
    def test_both_declarations_accept_the_parameter_being_omitted(self, param):
        """The half that does work: omit it and the documented default window applies."""
        other = "toDate" if param == "fromDate" else "fromDate"
        fixed = _TO_DATE if other == "toDate" else _DISCOVERY_FROM_DATE
        response = _raw_get("/biomass/harvestReport", {"penId": "all", other: fixed})
        assert response.status_code == 200, f"omitting {param} returned {response.status_code}"


class TestEnvironmentalLatest:
    def test_environmental_latest_loads(self):
        pipeline = _make_pipeline("env_latest")
        load_info = pipeline.run(aquabyte_source().with_resources("environmental_latest"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM environmental_latest") > 0, (
            "Expected at least 1 latest environmental reading"
        )


class TestBiomass:
    def test_biomass_loads(self, live_pen_ids):
        pipeline = _make_pipeline("biomass")
        source = _source_with("biomass", pen_id=live_pen_ids, **_DATE_WINDOW)
        load_info = pipeline.run(source.with_resources("biomass"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM biomass WHERE avg_weight > 0") > 0, (
            f"Expected biomass rows with avg_weight > 0 for live pens {live_pen_ids}"
        )


class TestHarvestReport:
    def test_harvest_report_loads(self, live_pen_ids):
        pipeline = _make_pipeline("harvest_report")
        source = _source_with("harvest_report", pen_id=live_pen_ids, **_DATE_WINDOW)
        load_info = pipeline.run(source.with_resources("harvest_report"))
        assert load_info is not None
        # Harvest reports are rare — pens with fish haven't been harvested yet.
        # Just verify no errors.


class TestLiceCount:
    def test_lice_count_loads(self, live_pen_ids):
        pipeline = _make_pipeline("lice_count")
        source = _source_with("lice_count", pen_id=live_pen_ids, **_DATE_WINDOW)
        load_info = pipeline.run(source.with_resources("lice_count"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM lice_count") > 0, (
            f"Expected lice count data for live pens {live_pen_ids}"
        )


class TestBehaviourSwimSpeed:
    def test_behaviour_swim_speed_loads(self, live_pen_ids):
        pipeline = _make_pipeline("behaviour_swim_speed")
        source = _source_with("behaviour_swim_speed", pen_id=live_pen_ids, **_TIME_WINDOW)
        load_info = pipeline.run(source.with_resources("behaviour_swim_speed"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM behaviour_swim_speed") > 0, (
            f"Expected swim speed data for live pens {live_pen_ids}"
        )


class TestBehaviourBreathingIndex:
    def test_behaviour_breathing_index_loads(self, live_pen_ids):
        pipeline = _make_pipeline("behaviour_breathing_index")
        source = _source_with("behaviour_breathing_index", pen_id=live_pen_ids, **_TIME_WINDOW)
        load_info = pipeline.run(source.with_resources("behaviour_breathing_index"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM behaviour_breathing_index") > 0, (
            f"Expected breathing index data for live pens {live_pen_ids}"
        )


class TestWelfareScores:
    def test_welfare_scores_loads(self, live_pen_ids):
        pipeline = _make_pipeline("welfare_scores")
        source = _source_with("welfare_scores", pen_id=live_pen_ids, **_DATE_WINDOW)
        load_info = pipeline.run(source.with_resources("welfare_scores"))
        assert load_info is not None
        assert _count(pipeline, "SELECT COUNT(*) FROM welfare_scores") > 0, (
            f"Expected welfare scores for live pens {live_pen_ids}"
        )

    def test_welfare_scores_land_as_raw_records(self, live_pen_ids):
        """One row per pen and date, with the API's nested categories intact."""
        pipeline = _make_pipeline("welfare_scores_raw")
        source = _source_with("welfare_scores", pen_id=live_pen_ids, **_DATE_WINDOW)
        assert pipeline.run(source.with_resources("welfare_scores")) is not None

        duplicates = _count(
            pipeline,
            "SELECT COUNT(*) FROM (SELECT pen_id, date FROM welfare_scores GROUP BY 1, 2 HAVING COUNT(*) > 1)",
        )
        assert duplicates == 0, "welfare_scores must hold one row per pen and date"

        with pipeline.sql_client() as client:
            rows = client.execute_sql("SELECT welfare_scores FROM welfare_scores WHERE welfare_scores IS NOT NULL")
            assert rows, "Expected at least one row carrying the nested welfareScores object"


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_full_pipeline_with_live_pens(self, live_pen_ids):
        """Run the full aquabyte_source with 2 live pens over a 3-day window."""
        pipeline = _make_pipeline("full_pipeline")
        source = aquabyte_source()
        for resource_name in ("biomass", "harvest_report", "lice_count", "welfare_scores"):
            source.resources[resource_name].bind(pen_id=live_pen_ids, **_DATE_WINDOW)
        for resource_name in ("environmental", "behaviour_swim_speed", "behaviour_breathing_index"):
            source.resources[resource_name].bind(pen_id=live_pen_ids, **_TIME_WINDOW)

        load_info = pipeline.run(source)
        assert load_info is not None

        assert _count(pipeline, "SELECT COUNT(*) FROM sites") > 0, "Expected sites data"

        # pens is unfiltered — every pen the API reports lands, including our live ones.
        with pipeline.sql_client() as client:
            rows = client.execute_sql("SELECT DISTINCT id FROM pens")
            assert rows is not None
            loaded_pens = {row[0] for row in rows}
        assert set(live_pen_ids) <= loaded_pens, f"Expected {live_pen_ids} among the loaded pens"

        assert _count(pipeline, "SELECT COUNT(*) FROM biomass WHERE avg_weight > 0") > 0, (
            "Expected biomass data for live pens"
        )
