"""Tests for the pens transformer."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ALL_PEN_IDS,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    run_source,
)


def _run_pens_test(mock_rest_client, pen_ids, pipeline_suffix=""):
    """Shared helper: load sites mock, run pens resource standalone, return pipeline."""
    sites_data = load_mock("sites.json")["sites"]
    mock_rest_client.paginate.return_value = iter([sites_data])

    source = aquabyte_source(pen_ids=pen_ids, **SOURCE_CONFIG)
    pipeline, load_info = run_source(f"test_pens{pipeline_suffix}", source, ["sites", "pens"])
    assert load_info is not None
    return pipeline


def test_pens_extracts_all_pens(mock_rest_client):
    """Pens transformer yields all pens (active and inactive) when pen_ids is None."""
    pipeline = _run_pens_test(mock_rest_client, pen_ids=None, pipeline_suffix="_all")

    assert_row_count(pipeline, "pens", 5)

    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT id FROM pens ORDER BY id")
        assert result is not None
        pen_ids = sorted(row[0] for row in result)
        assert pen_ids == sorted(ALL_PEN_IDS)


def test_pens_filters_by_pen_ids(mock_rest_client):
    """Pens transformer yields only specified pen_ids when provided."""
    requested_pens = ["pen-001", "pen-004"]
    pipeline = _run_pens_test(mock_rest_client, pen_ids=requested_pens, pipeline_suffix="_filter")

    assert_row_count(pipeline, "pens", 2)
    assert_pen_ids(pipeline, "pens", requested_pens, column="id")


def test_pens_includes_inactive_when_specified(mock_rest_client):
    """When pen_ids explicitly includes an inactive pen, it should still be yielded."""
    requested_pens = ["pen-001", "pen-002"]
    pipeline = _run_pens_test(mock_rest_client, pen_ids=requested_pens, pipeline_suffix="_inactive")

    assert_row_count(pipeline, "pens", 2)
    assert_pen_ids(pipeline, "pens", requested_pens, column="id")
