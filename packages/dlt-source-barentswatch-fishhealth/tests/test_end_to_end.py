"""End-to-end: both resources of barentswatch_fishhealth_source, through a DuckDB pipeline."""

import json

from dlt_source_barentswatch_fishhealth import WeekRange
from tests.conftest import (
    ALL_LOCALITY_NOS,
    LOCALITIES_URL,
    THREE_WEEKS,
    assert_row_count,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    query,
)

# A subset of the fixture's localities, so the filtered path is what the default run exercises.
LOCALITY_NOS = [90001, 90002]


def _serve_three_weeks(mock_api) -> int:
    """Two localities, three weeks, one of them unreported for the second locality. Returns the rows expected."""
    mock_api.localities()
    mock_api.weeks(LOCALITY_NOS, THREE_WEEKS)
    mock_api.week(90002, 2024, 2, json=load_mock("locality_week_fallow.json"))
    mock_api.no_report(90002, 2024, 3)
    return len(LOCALITY_NOS) * len(THREE_WEEKS) - 1


def test_end_to_end_loads_both_tables(mock_api):
    """A default run leaves a `locality` snapshot and one `locality_week` row per reported week."""
    expected_weeks = _serve_three_weeks(mock_api)

    pipeline = make_pipeline("test_e2e")
    load_info = pipeline.run(make_source(locality_nos=LOCALITY_NOS, week_range=THREE_WEEKS))
    load_info.raise_on_failed_jobs()

    assert_row_count(pipeline, "locality", len(LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)

    localities = {row["locality_no"]: row["name"] for row in load_rows(pipeline, "locality")}
    assert localities == {90001: "Testholmen", 90002: "Prøvevika"}

    weeks = {(row["locality_no"], row["year"], row["week"]) for row in load_rows(pipeline, "locality_week")}
    assert weeks == {(90001, 2024, 1), (90001, 2024, 2), (90001, 2024, 3), (90002, 2024, 1), (90002, 2024, 2)}

    fallow = query(pipeline, "SELECT lice_report FROM locality_week WHERE locality_no = 90002 AND week = 2")
    assert json.loads(fallow[0][0])["isFallow"] is True


def test_end_to_end_rerun_is_idempotent(mock_api):
    """Running the same range twice merges on the key instead of duplicating, and replaces the snapshot."""
    expected_weeks = _serve_three_weeks(mock_api)

    pipeline = make_pipeline("test_e2e_rerun")
    for _ in range(2):
        pipeline.run(make_source(locality_nos=LOCALITY_NOS, week_range=THREE_WEEKS)).raise_on_failed_jobs()

    assert_row_count(pipeline, "locality", len(LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)


def test_nested_objects_land_as_json_columns_with_no_child_tables(mock_api):
    """`max_table_nesting=0`: the report's objects and arrays are JSON text in one row, not child tables."""
    mock_api.localities()
    mock_api.week(90001, 2024, 5)

    pipeline = make_pipeline("test_e2e_nesting")
    pipeline.run(make_source(locality_nos=[90001], week_range=WeekRange(2024, 5, 2024, 5)))

    assert not any(name.startswith("locality_week__") for name in pipeline.default_schema.data_table_names())
    assert not any(name.startswith("locality__") for name in pipeline.default_schema.data_table_names())

    (row,) = load_rows(pipeline, "locality_week")
    payload = load_mock("locality_week_reported.json")
    assert {name for name in row if not name.startswith("_dlt")} == {
        "locality_no",
        "year",
        "week",
        "locality",
        "geometry",
        "municipality",
        "production_area",
        "aqua_culture_register",
        "control_areas",
        "export_restriction_areas",
        "pd_zone_id",
        "diseases",
        "farmed_fish_escapes",
        "lice_report",
        "lice_treatments",
    }
    assert json.loads(row["lice_report"]) == payload["liceReport"]
    assert json.loads(row["aqua_culture_register"]) == payload["aquaCultureRegister"]
    assert json.loads(row["control_areas"]) == []
    assert row["pd_zone_id"] == "surveillance"


def test_selecting_only_locality_week_still_fetches_the_list_but_writes_no_locality_table(mock_api):
    """The transformer needs its parent's rows; selecting it alone loads them without landing them."""
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)

    pipeline = make_pipeline("test_e2e_week_only")
    source = make_source(week_range=THREE_WEEKS).with_resources("locality_week")
    pipeline.run(source).raise_on_failed_jobs()

    assert len(mock_api.requests_to(LOCALITIES_URL)) == 1
    assert "locality" not in pipeline.default_schema.data_table_names()
    assert_row_count(pipeline, "locality_week", len(ALL_LOCALITY_NOS) * len(THREE_WEEKS))


def test_selecting_only_locality_makes_no_weekly_request(mock_api):
    """`discover_localities.py` does this: one request, one table, no week range needed."""
    mock_api.localities()

    pipeline = make_pipeline("test_e2e_locality_only")
    pipeline.run(make_source().with_resources("locality")).raise_on_failed_jobs()

    assert len(mock_api.urls_requested()) == 1
    assert pipeline.default_schema.data_table_names() == ["locality"]
    assert_row_count(pipeline, "locality", len(ALL_LOCALITY_NOS))
