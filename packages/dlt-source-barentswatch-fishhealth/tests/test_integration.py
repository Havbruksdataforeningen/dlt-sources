"""Integration tests against the real BarentsWatch API.

Run with: uv run pytest -m integration

dlt resolves the credentials itself (environment variables first, then `.dlt/secrets.toml`).
Missing credentials cause a hard error — not a skip.

Two public localities over three fixed weeks, the full locality list, then one production
area for one week: ten requests, a few seconds. The assertion is that rows landed in the shape the offline suite
assumes.
"""

import json

import dlt
import pytest

from dlt_source_barentswatch_fishhealth import WeekRange, barentswatch_fishhealth_source
from tests.conftest import assert_row_count, load_rows, make_pipeline

pytestmark = [pytest.mark.integration]

# Two locality numbers from the public Aquaculture Register, both reporting through 2025.
LOCALITY_NOS = [11340, 45072]
# Fixed rather than "the last few weeks", so a rerun a year from now asks for the same thing.
WEEK_RANGE = WeekRange(2025, 30, 2025, 32)


@pytest.fixture(autouse=True)
def isolated_run_context():
    """Overrides the offline suite's isolation: the live tests need the real `.dlt/secrets.toml`."""
    yield


@pytest.fixture(scope="module", autouse=True)
def require_credentials():
    """Fail fast if dlt cannot resolve the credentials from any provider."""
    try:
        client_id = dlt.secrets.get("sources.barentswatch_fishhealth.client_id", str)
    except KeyError:
        client_id = None
    if not client_id:
        pytest.fail(
            "No BarentsWatch client id found. Provide credentials via either:\n"
            "  - SOURCES__BARENTSWATCH_FISHHEALTH__CLIENT_ID and ..__CLIENT_SECRET environment variables\n"
            "  - .dlt/secrets.toml  (see .dlt/secrets.toml.example)"
        )


def test_two_localities_three_weeks_land():
    """Both tables land, and every weekly row carries the report as one JSON object."""
    source = barentswatch_fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
    source.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in LOCALITY_NOS)
    source.locality_week.bind(week_range=WEEK_RANGE)

    pipeline = make_pipeline("integ_barentswatch_fishhealth")
    pipeline.run(source).raise_on_failed_jobs()

    assert_row_count(pipeline, "localities_with_salmonoids", len(LOCALITY_NOS))
    assert {row["locality_no"] for row in load_rows(pipeline, "localities_with_salmonoids")} == set(LOCALITY_NOS)

    weeks = load_rows(pipeline, "locality_week")
    assert 0 < len(weeks) <= len(LOCALITY_NOS) * WEEK_RANGE.n_weeks, "Expected at least one reported week"
    for row in weeks:
        assert row["locality_no"] in LOCALITY_NOS
        assert (row["year"], row["week"]) in set(WEEK_RANGE.weeks())
        report = json.loads(row["lice_report"])
        assert {"hasReported", "isFallow", "adultFemaleLice"} <= set(report)


def test_the_full_locality_list_lands():
    """One request: every locality in the register, well over two thousand, each with its five fields."""
    source = barentswatch_fishhealth_source().with_resources("localities")

    pipeline = make_pipeline("integ_barentswatch_fishhealth_localities")
    pipeline.run(source).raise_on_failed_jobs()

    rows = load_rows(pipeline, "localities")
    assert len(rows) > 2000, f"Expected the register to list more than 2 000 localities, got {len(rows)}"
    assert len({row["locality_no"] for row in rows}) == len(rows), "one row per locality"
    assert {"aqua_culture_registry_version", "locality_no", "name", "municipality_no", "municipality"} <= set(rows[0])
    assert set(LOCALITY_NOS) <= {row["locality_no"] for row in rows}, "the salmonoid localities are in the register"


def test_one_production_area_one_week_lands_the_summary():
    """Every locality in production area 7 for one week: well over a hundred rows, each filtered by the body sent."""
    source = barentswatch_fishhealth_source().with_resources("locality_week_summary")
    source.locality_week_summary.bind(week_range=WeekRange(2025, 35, 2025, 35), body={"productionArea": 7})

    pipeline = make_pipeline("integ_barentswatch_fishhealth_summary")
    pipeline.run(source).raise_on_failed_jobs()

    rows = load_rows(pipeline, "locality_week_summary")
    assert len(rows) > 100, f"Expected area 7 to hold more than 100 localities, got {len(rows)}"
    assert len({row["locality_no"] for row in rows}) == len(rows), "one row per locality"
    for row in rows:
        assert (row["year"], row["week"]) == (2025, 35)
        assert row["is_filtered"] is True
        assert {"hasReported", "isFallow", "adultFemaleLice"} <= set(json.loads(row["lice_report"]))
        assert isinstance(json.loads(row["lice_treatments"]), list)
