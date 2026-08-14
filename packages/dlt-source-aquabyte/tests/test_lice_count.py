"""Tests for the lice_count resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    query,
    run_source,
    serve,
)

RECORDS = load_mock("lice_count.json")["liceCount"]


def test_lice_count_loads_into_duckdb(mock_rest_client):
    """Lice count resource loads mock data into DuckDB for a single pen."""
    mock_rest_client.paginate.side_effect = serve({"/liceCount": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.lice_count.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, load_info = run_source("test_lice_count", source, ["lice_count"])

    assert load_info is not None
    assert_row_count(pipeline, "lice_count", len(RECORDS))
    assert_pen_ids(pipeline, "lice_count", ["pen-001"])

    rows = query(pipeline, "SELECT adult_female FROM lice_count WHERE date = '2026-01-12'")
    assert rows[0][0] is None


def test_lice_count_defaults_to_all_pens(mock_rest_client):
    """Lice count resource fetches every pen with a single penId=all request by default."""
    mock_rest_client.paginate.side_effect = serve({"/liceCount": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.lice_count.bind(**DATE_RANGE)
    pipeline, load_info = run_source("test_lice_all_pens", source, ["lice_count"])

    assert load_info is not None
    assert_row_count(pipeline, "lice_count", len(RECORDS) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "lice_count", ACTIVE_PEN_IDS)
