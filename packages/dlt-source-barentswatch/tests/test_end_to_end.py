"""End-to-end: the four resources of fishhealth_source, through a DuckDB pipeline.

`localities_with_salmonoids` and `locality_week` are a pair — the transformer reads the
resource. `localities` and `locality_week_summary` stand alone.
"""

import json

from dlt_source_barentswatch import WeekRange
from tests.conftest import (
    ALL_LOCALITY_NOS,
    LOCALITIES_ALL_URL,
    LOCALITIES_URL,
    THREE_WEEKS,
    assert_row_count,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    query,
)

BODY = {"productionArea": 7}
PAIR = ("localities_with_salmonoids", "locality_week")


def _serve_everything(mock_api) -> int:
    """All five localities over three weeks, one of them fallow and one unreported for the second locality;
    the register list; the summary for every week. Returns the `locality_week` rows expected."""
    mock_api.all_localities()
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)
    mock_api.week(90002, 2024, 2, json=load_mock("locality_week_fallow.json"))
    mock_api.no_report(90002, 2024, 3)
    mock_api.summaries(THREE_WEEKS, body=BODY)
    return len(ALL_LOCALITY_NOS) * THREE_WEEKS.n_weeks - 1


def test_end_to_end_loads_all_four_tables(mock_api):
    """One run of every resource: two snapshots, one `locality_week` row per reported week, one summary row per locality per week."""
    expected_weeks = _serve_everything(mock_api)
    summary_rows = load_mock("locality_week_summary.json")

    pipeline = make_pipeline("test_e2e_all_four")
    pipeline.run(make_source(week_range=THREE_WEEKS, body=BODY)).raise_on_failed_jobs()

    assert set(pipeline.default_schema.data_table_names()) == {
        "localities",
        "localities_with_salmonoids",
        "locality_week",
        "locality_week_summary",
    }
    assert len(mock_api.requests_to(LOCALITIES_ALL_URL)) == 1
    assert len(mock_api.requests_to(LOCALITIES_URL)) == 1
    assert_row_count(pipeline, "localities", len(ALL_LOCALITY_NOS))
    assert_row_count(pipeline, "localities_with_salmonoids", len(ALL_LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)
    assert_row_count(pipeline, "locality_week_summary", len(summary_rows) * THREE_WEEKS.n_weeks)

    weeks = {(row["locality_no"], row["year"], row["week"]) for row in load_rows(pipeline, "locality_week")}
    assert (90002, 2024, 3) not in weeks
    assert (90002, 2024, 2) in weeks
    fallow = query(pipeline, "SELECT lice_report FROM locality_week WHERE locality_no = 90002 AND week = 2")
    assert json.loads(fallow[0][0])["isFallow"] is True

    landed = load_rows(pipeline, "locality_week_summary")
    assert {(row["locality_no"], row["year"], row["week"]) for row in landed} == {
        (row["locality"]["no"], year, week) for row in summary_rows for year, week in THREE_WEEKS.weeks()
    }
    (treated,) = [row for row in landed if row["locality_no"] == 90003 and row["week"] == 1]
    assert json.loads(treated["lice_treatments"]) == ["IKKE_MEDIKAMENTELL"]
    assert json.loads(treated["lice_report"])["hasReported"] is True


def test_end_to_end_rerun_is_idempotent(mock_api):
    """Running the same weeks twice merges both weekly tables on the key instead of duplicating, and replaces the snapshots."""
    expected_weeks = _serve_everything(mock_api)

    pipeline = make_pipeline("test_e2e_rerun")
    for _ in range(2):
        pipeline.run(make_source(week_range=THREE_WEEKS, body=BODY)).raise_on_failed_jobs()

    assert_row_count(pipeline, "localities", len(ALL_LOCALITY_NOS))
    assert_row_count(pipeline, "localities_with_salmonoids", len(ALL_LOCALITY_NOS))
    assert_row_count(pipeline, "locality_week", expected_weeks)
    assert_row_count(
        pipeline, "locality_week_summary", len(load_mock("locality_week_summary.json")) * THREE_WEEKS.n_weeks
    )


def test_nested_objects_land_as_json_columns_with_no_child_tables(mock_api):
    """`max_table_nesting=0`: the report's objects and arrays are JSON text in one row, not child tables."""
    mock_api.localities(rows=[{"localityNo": 90001, "name": "Testholmen"}])
    mock_api.week(90001, 2024, 5)

    pipeline = make_pipeline("test_e2e_nesting")
    pipeline.run(make_source(week_range=WeekRange(2024, 5, 2024, 5)).with_resources(*PAIR)).raise_on_failed_jobs()

    assert not any("__" in name for name in pipeline.default_schema.data_table_names())

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


def test_selecting_only_locality_week_still_fetches_the_list_but_writes_no_list_table(mock_api):
    """The transformer needs its parent's rows; selecting it alone loads them without landing them."""
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)

    pipeline = make_pipeline("test_e2e_week_only")
    pipeline.run(make_source(week_range=THREE_WEEKS).with_resources("locality_week")).raise_on_failed_jobs()

    assert len(mock_api.requests_to(LOCALITIES_URL)) == 1
    assert mock_api.requests_to(LOCALITIES_ALL_URL) == []
    assert "localities_with_salmonoids" not in pipeline.default_schema.data_table_names()
    assert "localities" not in pipeline.default_schema.data_table_names()
    assert_row_count(pipeline, "locality_week", len(ALL_LOCALITY_NOS) * THREE_WEEKS.n_weeks)
