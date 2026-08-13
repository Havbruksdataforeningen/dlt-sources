"""Tests for the behaviour_breathing_index resource (v3.1 standalone with penId=all)."""

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


def test_behaviour_breathing_index_loads_into_duckdb(mock_rest_client):
    """Behaviour breathing index resource loads mock data into DuckDB standalone."""
    breathing_records = load_mock("breathing_index.json")["breathingIndex"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/behaviour/breathingIndex":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                # Verify period is NOT in params (v3.1 breaking change)
                assert "period" not in params, "period must not be passed for breathingIndex in v3.1"
                return iter([make_per_pen_data(breathing_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_behaviour_breathing", source, ["behaviour_breathing_index"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_breathing_index", len(breathing_records))
    assert_pen_ids(pipeline, "behaviour_breathing_index", [pen_id])

    # Verify nullable breathing_index field is handled correctly
    with pipeline.sql_client() as client:
        result = client.execute_sql(
            "SELECT breathing_index FROM behaviour_breathing_index WHERE from_time = '2026-01-11T00:00:00Z'"
        )
        assert result is not None
        assert result[0][0] is None


def test_behaviour_breathing_index_pen_id_all(mock_rest_client):
    """Behaviour breathing index resource fetches data for all pens when pen_ids is None."""
    breathing_records = load_mock("breathing_index.json")["breathingIndex"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/behaviour/breathingIndex":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(breathing_records, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_breathing_all_pens", source, ["behaviour_breathing_index"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_breathing_index", len(breathing_records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "behaviour_breathing_index", ACTIVE_PEN_IDS)
