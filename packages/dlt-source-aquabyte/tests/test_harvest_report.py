"""Tests for the harvest_report resource (v3.1 standalone with penId=all)."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    make_per_pen_data,
    run_source,
)


def test_harvest_report_loads_into_duckdb(mock_rest_client):
    """Harvest report resource loads mock data into DuckDB standalone."""
    report_records = load_mock("harvest_report.json")["reports"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/biomass/harvestReport":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(report_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_harvest_report", source, ["harvest_report"])

    assert load_info is not None
    assert_row_count(pipeline, "harvest_report", len(report_records))
    assert_pen_ids(pipeline, "harvest_report", [pen_id])

    # Verify slaughter_start_date values
    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT slaughter_start_date FROM harvest_report ORDER BY slaughter_start_date")
        assert result is not None
        dates = [str(row[0]) for row in result]
        assert len(dates) == 2

    mock_rest_client.paginate.assert_called_once_with(
        "/biomass/harvestReport",
        params={"penId": pen_id, "fromDate": "2026-01-01", "toDate": "2026-01-31"},
        data_selector="reports",
    )


def test_harvest_report_pen_id_all(mock_rest_client):
    """Harvest report resource fetches data for all pens when pen_ids is None."""
    report_records = load_mock("harvest_report.json")["reports"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/biomass/harvestReport":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(report_records, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_harvest_all_pens", source, ["harvest_report"])

    assert load_info is not None
    assert_row_count(pipeline, "harvest_report", len(report_records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "harvest_report", ACTIVE_PEN_IDS)
