"""Tests for the behaviour_swim_speed resource (v3.1 standalone with penId=all)."""

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


def test_behaviour_swim_speed_loads_into_duckdb(mock_rest_client):
    """Behaviour swim speed resource loads mock data into DuckDB standalone."""
    swim_records = load_mock("swim_speed.json")["swimSpeed"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/behaviour/swimSpeed":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(swim_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_behaviour_swim_speed", source, ["behaviour_swim_speed"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_swim_speed", len(swim_records))
    assert_pen_ids(pipeline, "behaviour_swim_speed", [pen_id])

    # Verify nullable fields are handled correctly
    with pipeline.sql_client() as client:
        result = client.execute_sql(
            "SELECT swim_speed, swim_tilt FROM behaviour_swim_speed WHERE from_time = '2026-01-11T00:00:00Z'"
        )
        assert result is not None
        assert result[0][0] is None
        assert result[0][1] is None


def test_behaviour_swim_speed_pen_id_all(mock_rest_client):
    """Behaviour swim speed resource fetches data for all pens when pen_ids is None."""
    swim_records = load_mock("swim_speed.json")["swimSpeed"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/behaviour/swimSpeed":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(swim_records, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**TIME_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_swim_all_pens", source, ["behaviour_swim_speed"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_swim_speed", len(swim_records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "behaviour_swim_speed", ACTIVE_PEN_IDS)
