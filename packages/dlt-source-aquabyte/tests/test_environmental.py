"""Tests for the environmental resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    SOURCE_CONFIG,
    TIME_RANGE,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    make_per_pen_data,
    params_sent,
    run_source,
    serve,
)

DATA = load_mock("environmental.json")["data"]


def test_environmental_loads_into_duckdb(mock_rest_client):
    """Environmental resource loads mock data into DuckDB with correct row count."""
    mock_rest_client.paginate.side_effect = serve({"/environmental": DATA})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental.bind(pen_id="pen-001", **TIME_RANGE)
    pipeline, load_info = run_source("test_environmental", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(DATA))
    assert_pen_ids(pipeline, "environmental", ["pen-001"])


def test_environmental_pagination_with_next_token(mock_rest_client):
    """Environmental resource handles nextToken pagination across multiple pages."""
    page1 = make_per_pen_data(DATA[:1], "pen-001")
    page2 = make_per_pen_data(DATA[1:], "pen-001")

    mock_rest_client.paginate.side_effect = lambda url, **kwargs: (
        iter([page1, page2]) if url == "/environmental" else iter([])
    )

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental.bind(pen_id="pen-001", **TIME_RANGE)
    pipeline, load_info = run_source("test_env_pagination", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(DATA))


def test_environmental_defaults_to_all_pens(mock_rest_client):
    """The endpoint's penId=all is the default: one request, every pen."""
    mock_rest_client.paginate.side_effect = serve({"/environmental": DATA})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental.bind(**TIME_RANGE)
    pipeline, load_info = run_source("test_env_all_pens", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(DATA) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "environmental", ACTIVE_PEN_IDS)
    assert [p["penId"] for p in params_sent(mock_rest_client, "/environmental")] == ["all"]


def test_environmental_sends_period(mock_rest_client):
    """period is an environmental query param and is only sent when asked for."""
    mock_rest_client.paginate.side_effect = serve({"/environmental": DATA})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental.bind(period="15min", **TIME_RANGE)
    run_source("test_env_period", source, ["environmental"])

    assert params_sent(mock_rest_client, "/environmental")[0]["period"] == "15min"
