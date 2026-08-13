"""Tests for the environmental_latest resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import SOURCE_CONFIG, assert_row_count, load_mock, run_source


def test_environmental_latest_loads_into_duckdb(mock_rest_client):
    """Environmental latest resource loads mock data into DuckDB with penId=all by default."""
    data_points = load_mock("environmental_latest.json")["data"]

    mock_rest_client.paginate.return_value = iter([data_points])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source("test_env_latest", source, ["environmental_latest"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental_latest", len(data_points))

    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT DISTINCT pen_id FROM environmental_latest ORDER BY pen_id")
        assert result is not None
        pen_ids = [row[0] for row in result]
        assert pen_ids == ["pen-001", "pen-003"]

    mock_rest_client.paginate.assert_called_once_with(
        "/environmental/latest",
        params={"penId": "all"},
        data_selector="data",
    )


def test_environmental_latest_with_pen_id_filter(mock_rest_client):
    """Environmental latest resource passes penId query param when pen_id is provided."""
    single_pen = [load_mock("environmental_latest.json")["data"][0]]

    mock_rest_client.paginate.return_value = iter([single_pen])

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental_latest.bind(pen_id="pen-001")
    pipeline, load_info = run_source("test_env_latest_filtered", source, ["environmental_latest"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental_latest", 1)

    mock_rest_client.paginate.assert_called_once_with(
        "/environmental/latest",
        params={"penId": "pen-001"},
        data_selector="data",
    )
