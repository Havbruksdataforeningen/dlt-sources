"""Tests for the behaviour_breathing_index resource."""

import pytest

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

RECORDS = load_mock("breathing_index.json")["breathingIndex"]


def test_behaviour_breathing_index_loads_into_duckdb(mock_rest_client):
    """Behaviour breathing index resource loads mock data into DuckDB for a single pen."""
    mock_rest_client.paginate.side_effect = serve({"/behaviour/breathingIndex": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.behaviour_breathing_index.bind(pen_id="pen-001", **TIME_RANGE)
    pipeline, load_info = run_source("test_behaviour_breathing", source, ["behaviour_breathing_index"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_breathing_index", len(RECORDS))
    assert_pen_ids(pipeline, "behaviour_breathing_index", ["pen-001"])
    assert "period" not in params_sent(mock_rest_client, "/behaviour/breathingIndex")[0]

    rows = query(
        pipeline,
        "SELECT breathing_index FROM behaviour_breathing_index WHERE from_time = '2026-01-11T00:00:00Z'",
    )
    assert rows[0][0] is None


def test_behaviour_breathing_index_has_no_period_param():
    """The endpoint documents no period, so the resource does not offer one."""
    source = aquabyte_source(**SOURCE_CONFIG)
    with pytest.raises(TypeError):
        source.behaviour_breathing_index.bind(period="h")


def test_behaviour_breathing_index_defaults_to_all_pens(mock_rest_client):
    """Behaviour breathing index resource fetches every pen with a single penId=all request."""
    mock_rest_client.paginate.side_effect = serve({"/behaviour/breathingIndex": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.behaviour_breathing_index.bind(**TIME_RANGE)
    pipeline, load_info = run_source("test_breathing_all_pens", source, ["behaviour_breathing_index"])

    assert load_info is not None
    assert_row_count(pipeline, "behaviour_breathing_index", len(RECORDS) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "behaviour_breathing_index", ACTIVE_PEN_IDS)
