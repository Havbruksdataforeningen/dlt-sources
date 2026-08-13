"""Tests for the sites resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import SOURCE_CONFIG, assert_row_count, load_mock, run_source


def test_sites_resource_loads_into_duckdb(mock_rest_client):
    """Sites resource loads mock data into DuckDB with correct row count."""
    sites_list = load_mock("sites.json")["sites"]

    mock_rest_client.paginate.return_value = iter([sites_list])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source("test_sites", source, ["sites"])

    assert load_info is not None
    assert_row_count(pipeline, "sites", len(sites_list))

    mock_rest_client.paginate.assert_called_once_with("/sites", data_selector="sites")
