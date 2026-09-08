"""End-to-end: the resources of barentswatch_fishhealth_source, through a DuckDB pipeline.

`locality` and `locality_week` are a pair — the transformer reads the resource — and most
tests run those two. `locality_week_summary` stands alone, and one test runs all three.
"""

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

# The locality list and the detailed weekly report, which is a transformer over it.
PAIR = ("locality", "locality_week")


def _serve_three_weeks(mock_api) -> int:
    """Two localities, three weeks, one of them unreported for the second locality. Returns the rows expected."""
    mock_api.localities()
    mock_api.weeks(LOCALITY_NOS, THREE_WEEKS)
    mock_api.week(90002, 2024, 2, json=load_mock("locality_week_fallow.json"))
    mock_api.no_report(90002, 2024, 3)
    return len(LOCALITY_NOS) * THREE_WEEKS.n_weeks - 1


def test_end_to_end_loads_both_tables(mock_api):
    """A default run leaves a `locality` snapshot and one `locality_week` row per reported week."""
    expected_weeks = _serve_three_weeks(mock_api)

    pipeline = make_pipeline("test_e2e")
    load_info = pipeline.run(make_source(locality_nos=LOCALITY_NOS, week_range=THREE_WEEKS).with_resources(*PAIR))
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
        pipeline.run(
            make_source(locality_nos=LOCALITY_NOS, week_range=THREE_WEEKS).with_resources(*PAIR)
        ).raise_on_failed_jobs()

    assert_row_count(pipeline, "locality", len(LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)


def test_nested_objects_land_as_json_columns_with_no_child_tables(mock_api):
    """`max_table_nesting=0`: the report's objects and arrays are JSON text in one row, not child tables."""
    mock_api.localities()
    mock_api.week(90001, 2024, 5)

    pipeline = make_pipeline("test_e2e_nesting")
    pipeline.run(make_source(locality_nos=[90001], week_range=WeekRange(2024, 5, 2024, 5)).with_resources(*PAIR))

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


def test_end_to_end_loads_all_three_tables(mock_api):
    """One run of every resource: the pair as before, and a `locality_week_summary` row per locality per week per area.

    The summary's `liceTreatments` is an array of category names; with `max_table_nesting=0`
    it lands as one JSON column, not a child table. `productionArea` is the integer asked for.
    """
    expected_weeks = _serve_three_weeks(mock_api)
    # A locality is in one area, so the two areas answer with disjoint localities, as the API does.
    summary_rows = load_mock("locality_week_summary.json")
    for year, week in THREE_WEEKS.weeks():
        mock_api.summary(year, week, summary_rows[:2], body={"productionArea": 7})
        mock_api.summary(year, week, summary_rows[2:], body={"productionArea": 8})

    pipeline = make_pipeline("test_e2e_all_three")
    load_info = pipeline.run(make_source(locality_nos=LOCALITY_NOS, week_range=THREE_WEEKS, production_areas=[7, 8]))
    load_info.raise_on_failed_jobs()

    assert set(pipeline.default_schema.data_table_names()) == {"locality", "locality_week", "locality_week_summary"}
    assert_row_count(pipeline, "locality", len(LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)
    assert_row_count(pipeline, "locality_week_summary", len(summary_rows) * THREE_WEEKS.n_weeks)

    columns = pipeline.default_schema.tables["locality_week_summary"]["columns"]
    assert columns["lice_treatments"]["data_type"] == "json"
    assert columns["production_area"]["data_type"] == "bigint"
    assert columns["locality_no"]["data_type"] == "bigint"

    landed = load_rows(pipeline, "locality_week_summary")
    assert {(row["locality_no"], row["year"], row["week"], row["production_area"]) for row in landed} == {
        (locality_no, year, week, area)
        for locality_no, area in ((90001, 7), (90002, 7), (90003, 8))
        for year, week in THREE_WEEKS.weeks()
    }
    (treated,) = [row for row in landed if row["locality_no"] == 90003 and row["week"] == 1]
    assert json.loads(treated["lice_treatments"]) == ["IKKE_MEDIKAMENTELL"]
    assert json.loads(treated["diseases"]) == ["PANKREASSYKDOM"]
    assert json.loads(treated["lice_report"])["hasReported"] is True
    assert treated["is_filtered"] is True


def test_end_to_end_summary_rerun_is_idempotent(mock_api):
    """Running the same weeks and areas twice merges on locality, year and week instead of duplicating."""
    mock_api.summaries(THREE_WEEKS)
    source = make_source(week_range=THREE_WEEKS, production_areas=[7]).with_resources("locality_week_summary")

    pipeline = make_pipeline("test_e2e_summary_rerun")
    for _ in range(2):
        pipeline.run(source).raise_on_failed_jobs()

    assert_row_count(
        pipeline, "locality_week_summary", len(load_mock("locality_week_summary.json")) * THREE_WEEKS.n_weeks
    )
    assert len(mock_api.requests_to(LOCALITIES_URL)) == 0


def test_selecting_only_locality_week_still_fetches_the_list_but_writes_no_locality_table(mock_api):
    """The transformer needs its parent's rows; selecting it alone loads them without landing them."""
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)

    pipeline = make_pipeline("test_e2e_week_only")
    source = make_source(week_range=THREE_WEEKS).with_resources("locality_week")
    pipeline.run(source).raise_on_failed_jobs()

    assert len(mock_api.requests_to(LOCALITIES_URL)) == 1
    assert "locality" not in pipeline.default_schema.data_table_names()
    assert_row_count(pipeline, "locality_week", len(ALL_LOCALITY_NOS) * THREE_WEEKS.n_weeks)


def test_selecting_only_locality_makes_no_weekly_request(mock_api):
    """`discover_localities.py` does this: one request, one table, no week range needed."""
    mock_api.localities()

    pipeline = make_pipeline("test_e2e_locality_only")
    pipeline.run(make_source().with_resources("locality")).raise_on_failed_jobs()

    assert len(mock_api.urls_requested()) == 1
    assert pipeline.default_schema.data_table_names() == ["locality"]
    assert_row_count(pipeline, "locality", len(ALL_LOCALITY_NOS))
