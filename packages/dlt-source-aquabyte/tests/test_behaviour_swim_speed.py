"""Tests for the behaviour_swim_speed resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    SOURCE_CONFIG,
    TIME_RANGE,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    params_sent,
    query,
    run_source,
    serve,
)

RECORDS = load_mock("swim_speed.json")["swimSpeed"]


def test_behaviour_swim_speed_loads_into_duckdb(mock_rest_client):
    """Behaviour swim speed resource loads mock data into DuckDB for a single pen."""
    mock_rest_client.paginate.side_effect = serve({"/behaviour/swimSpeed": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.behaviour_swim_speed.bind(pen_id="pen-001", **TIME_RANGE)
    pipeline, load_info = run_source("test_behaviour_swim_speed", source, ["behaviour_swim_speed"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_swim_speed", len(RECORDS))
    assert_pen_ids(pipeline, "behaviour_swim_speed", ["pen-001"])

    rows = query(
        pipeline,
        "SELECT swim_speed, swim_tilt FROM behaviour_swim_speed WHERE from_time = '2026-01-11T00:00:00Z'",
    )
    assert rows[0] == (None, None)


def test_behaviour_swim_speed_defaults_to_all_pens(mock_rest_client):
    """Behaviour swim speed resource fetches every pen with a single penId=all request."""
    mock_rest_client.paginate.side_effect = serve({"/behaviour/swimSpeed": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.behaviour_swim_speed.bind(**TIME_RANGE)
    pipeline, load_info = run_source("test_swim_all_pens", source, ["behaviour_swim_speed"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_swim_speed", len(RECORDS) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "behaviour_swim_speed", ACTIVE_PEN_IDS)


def test_behaviour_swim_speed_sends_period(mock_rest_client):
    """period is a swimSpeed query param and is only sent when asked for."""
    mock_rest_client.paginate.side_effect = serve({"/behaviour/swimSpeed": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.behaviour_swim_speed.bind(period="h", **TIME_RANGE)
    run_source("test_swim_period", source, ["behaviour_swim_speed"])

    assert params_sent(mock_rest_client, "/behaviour/swimSpeed")[0]["period"] == "h"
