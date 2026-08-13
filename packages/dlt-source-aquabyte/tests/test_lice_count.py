"""Tests for the lice_count resource (v3.1 standalone with penId=all)."""

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


def test_lice_count_loads_into_duckdb(mock_rest_client):
    """Lice count resource loads mock data into DuckDB standalone."""
    lice_records = load_mock("lice_count.json")["liceCount"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/liceCount":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(lice_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_lice_count", source, ["lice_count"])

    assert load_info is not None
    assert_row_count(pipeline, "lice_count", len(lice_records))
    assert_pen_ids(pipeline, "lice_count", [pen_id])

    # Verify nullable fields are handled correctly
    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT adult_female FROM lice_count WHERE date = '2026-01-12'")
        assert result is not None
        assert result[0][0] is None


def test_lice_count_pen_id_all(mock_rest_client):
    """Lice count resource fetches data for all pens when pen_ids is None."""
    lice_records = load_mock("lice_count.json")["liceCount"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/liceCount":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(lice_records, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_lice_all_pens", source, ["lice_count"])

    assert load_info is not None
    assert_row_count(pipeline, "lice_count", len(lice_records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "lice_count", ACTIVE_PEN_IDS)
