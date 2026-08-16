"""Tests for the environmental_latest resource."""

from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    assert_row_count,
    calls_to,
    load_mock,
    query,
    run_source,
)

DATA = load_mock("environmental_latest.json")["data"]


def test_environmental_latest_loads_into_duckdb(mock_rest_client):
    """Environmental latest resource loads mock data into DuckDB with penId=all by default."""
    mock_rest_client.paginate.return_value = iter([DATA])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source("test_env_latest", source, ["environmental_latest"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental_latest", len(DATA))

    rows = query(pipeline, "SELECT DISTINCT pen_id FROM environmental_latest ORDER BY pen_id")
    assert [row[0] for row in rows] == ["pen-001", "pen-003"]

    (call,) = calls_to(mock_rest_client, "/environmental/latest")
    assert call["params"] == {"penId": "all"}
    assert call["data_selector"] == "data"
    assert isinstance(call["paginator"], SinglePagePaginator)
