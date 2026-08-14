"""Tests for the harvest_report resource."""

from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    calls_to,
    load_mock,
    query,
    run_source,
    serve,
)

RECORDS = load_mock("harvest_report.json")["reports"]


def test_harvest_report_loads_into_duckdb(mock_rest_client):
    """Harvest report resource loads mock data into DuckDB for a single pen."""
    mock_rest_client.paginate.side_effect = serve({"/biomass/harvestReport": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.harvest_report.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, load_info = run_source("test_harvest_report", source, ["harvest_report"])

    assert load_info is not None
    assert_row_count(pipeline, "harvest_report", len(RECORDS))
    assert_pen_ids(pipeline, "harvest_report", ["pen-001"])

    rows = query(pipeline, "SELECT slaughter_start_date FROM harvest_report ORDER BY slaughter_start_date")
    assert len(rows) == len(RECORDS)

    (call,) = calls_to(mock_rest_client, "/biomass/harvestReport")
    assert call["params"] == {"penId": "pen-001", "fromDate": "2026-01-01", "toDate": "2026-01-31"}
    assert call["data_selector"] == "reports"
    assert isinstance(call["paginator"], SinglePagePaginator), "/biomass/harvestReport returns no nextToken"


def test_harvest_report_defaults_to_all_pens(mock_rest_client):
    """Harvest report resource fetches every pen with a single penId=all request by default."""
    mock_rest_client.paginate.side_effect = serve({"/biomass/harvestReport": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.harvest_report.bind(**DATE_RANGE)
    pipeline, load_info = run_source("test_harvest_all_pens", source, ["harvest_report"])

    assert load_info is not None
    assert_row_count(pipeline, "harvest_report", len(RECORDS) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "harvest_report", ACTIVE_PEN_IDS)
