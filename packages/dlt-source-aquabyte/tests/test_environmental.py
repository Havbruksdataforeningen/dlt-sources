"""Tests for the environmental resource (v3.1 standalone with penId=all)."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    SOURCE_CONFIG,
    TIME_RANGE,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    make_per_pen_data,
    run_source,
)


def test_environmental_loads_into_duckdb(mock_rest_client):
    """Environmental resource loads mock data into DuckDB with correct row count."""
    data_points = load_mock("environmental.json")["data"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/environmental":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(data_points, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_environmental", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(data_points))
    assert_pen_ids(pipeline, "environmental", [pen_id])


def test_environmental_pagination_with_next_token(mock_rest_client):
    """Environmental resource handles nextToken pagination across multiple pages."""
    data_points = load_mock("environmental.json")["data"]
    pen_id = "pen-001"
    page1 = make_per_pen_data(data_points[:1], pen_id)
    page2 = make_per_pen_data(data_points[1:], pen_id)

    def paginate_side_effect(url: str, **kwargs):
        if url == "/environmental":
            # RESTClient handles nextToken pagination internally;
            # paginate() yields pages, so we simulate 2 pages
            return iter([page1, page2])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_env_pagination", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(data_points))


def test_environmental_pen_id_all(mock_rest_client):
    """Environmental resource fetches data for all pens when pen_ids is None."""
    data_points = load_mock("environmental.json")["data"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/environmental":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                # Return data for all active pens
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(data_points, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_env_all_pens", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(data_points) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "environmental", ACTIVE_PEN_IDS)
