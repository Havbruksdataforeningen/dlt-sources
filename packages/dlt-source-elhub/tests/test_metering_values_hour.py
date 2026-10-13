"""The `metering_values_hour` transformer: flattening, the per-metering-point cursor, and backfills."""

import pytest

from dlt_source_elhub import ALL_RETAINED_HISTORY
from tests.conftest import (
    API_PATH,
    FakeElhub,
    cursors,
    load_mock,
    make_pipeline,
    payload_for,
    point_ids,
    query,
    row_count,
    run,
    source,
    values_of,
)

POINT = "707057500000000001"
OTHER = "707057500000000002"
NEWEST = "2026-10-13T02:04:25+02:00"


def _value(start: str, inserted: str, **extra) -> dict:
    return {
        "startTime": start,
        "endTime": start,
        "quantityKwh": 1.0,
        "resolution": "PT60M",
        "measurementName": "EH.ELECTRIC.KWH.1.3",
        "productCode": 8716867000030,
        "direction": "Out",
        "endUserId": "999999991",
        "insertDateTime": inserted,
        **extra,
    }


def _listing(*ids: str) -> dict:
    return {"data": [{"type": "metering-points", "id": p, "attributes": {}} for p in ids]}


def _one_point_with_one_value(api: FakeElhub) -> None:
    api.route(API_PATH, _listing(POINT))
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", NEWEST)]))


def test_one_row_per_value_stamped_with_its_metering_point(api_with_fixtures: FakeElhub):
    pipeline = make_pipeline("test_values_flat")
    run(pipeline, source(), "metering_values_hour")

    listing = load_mock("metering_points_hour_all.json")
    assert row_count(pipeline, "metering_values_hour") == len(values_of(listing))
    per_point = query(pipeline, "SELECT metering_point_id, COUNT(*) FROM metering_values_hour GROUP BY 1 ORDER BY 1")
    assert [row[0] for row in per_point] == point_ids(listing)
    columns = query(
        pipeline,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'metering_values_hour' ORDER BY ordinal_position",
    )
    assert columns[0] == ("metering_point_id",)
    assert query(pipeline, "SELECT DISTINCT resolution FROM metering_values_hour ORDER BY 1") == [
        ("PT15M",),
        ("PT60M",),
    ]


@pytest.mark.parametrize(("initial", "expected"), [(None, ALL_RETAINED_HISTORY), ("2026-10-01", "2026-10-01")])
def test_first_contact_asks_for_everything_since_the_initial_instant(api_with_fixtures: FakeElhub, initial, expected):
    src = source() if initial is None else source(initial_insert_date_time=initial)
    run(make_pipeline("test_values_first"), src, "metering_values_hour")

    (call,) = api_with_fixtures.calls_to_point(POINT)
    assert call.params == {"dataset": "METERING_VALUES_HOUR_RESTRICTED", "insertDateTime": expected}


def test_the_next_run_resumes_each_point_from_its_own_cursor(api: FakeElhub):
    api.route(API_PATH, _listing(POINT, OTHER))
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", NEWEST)]))
    api.route_point(OTHER, payload_for(OTHER, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:01:13+02:00")]))
    pipeline = make_pipeline("test_values_resume")

    run(pipeline, source(), "metering_values_hour")
    assert cursors(pipeline) == {POINT: NEWEST, OTHER: "2026-10-13T02:01:13+02:00"}

    run(pipeline, source(), "metering_values_hour")
    assert api.calls_to_point(POINT)[-1].params["insertDateTime"] == NEWEST
    assert api.calls_to_point(OTHER)[-1].params["insertDateTime"] == "2026-10-13T02:01:13+02:00"


def test_the_cursor_is_the_latest_instant_not_the_latest_text(api: FakeElhub):
    """Oslo offsets change with daylight saving: `+01:00` at 02:30 is later than `+02:00` at 02:45."""
    api.route(API_PATH, _listing(POINT))
    api.route_point(
        POINT,
        payload_for(
            POINT,
            [
                _value("2026-10-25T00:00:00+02:00", "2026-10-25T02:30:00+01:00"),
                _value("2026-10-25T01:00:00+02:00", "2026-10-25T02:45:00+02:00"),
            ],
        ),
    )
    pipeline = make_pipeline("test_values_cursor_instant")
    run(pipeline, source(), "metering_values_hour")

    assert cursors(pipeline) == {POINT: "2026-10-25T02:30:00+01:00"}


@pytest.mark.parametrize(
    "second_response",
    [None, payload_for(POINT, [_value("2026-10-11T00:00:00+02:00", "2026-10-12T02:04:25+02:00")])],
    ids=["204", "only older inserts"],
)
def test_the_cursor_never_moves_backwards(api: FakeElhub, second_response):
    _one_point_with_one_value(api)
    pipeline = make_pipeline("test_values_monotonic")
    run(pipeline, source(), "metering_values_hour")

    api.route_point(POINT, second_response)
    run(pipeline, source(), "metering_values_hour")

    assert cursors(pipeline) == {POINT: NEWEST}


@pytest.mark.parametrize(
    "bound",
    [
        {"start_date": "2026-10-01", "end_date": "2026-10-03"},
        {"insert_date_time": "2026-10-01T00:00:00+02:00"},
        {"end_date": "2026-10-03"},
    ],
)
def test_a_bound_window_is_sent_as_given_and_the_cursor_is_neither_read_nor_advanced(api: FakeElhub, bound):
    _one_point_with_one_value(api)
    pipeline = make_pipeline("test_values_backfill")
    run(pipeline, source(), "metering_values_hour")
    stored = cursors(pipeline)

    api.route_point(POINT, payload_for(POINT, [_value("2026-10-01T00:00:00+02:00", "2026-10-20T02:04:25+02:00")]))
    src = source()
    src.metering_values_hour.bind(**bound)
    run(pipeline, src, "metering_values_hour")

    call = api.calls_to_point(POINT)[-1]
    wire = {"start_date": "startDate", "end_date": "endDate", "insert_date_time": "insertDateTime"}
    assert call.params == {"dataset": "METERING_VALUES_HOUR_RESTRICTED", **{wire[k]: v for k, v in bound.items()}}
    assert cursors(pipeline) == stored
    assert row_count(pipeline, "metering_values_hour") == 2


def test_params_are_merged_last(api: FakeElhub):
    api.route(API_PATH, _listing(POINT))
    api.route_point(POINT, None)
    src = source()
    src.metering_values_hour.bind(params={"insertDateTime": "mine", "includeAllMeasurements": "Y"})
    run(make_pipeline("test_values_params"), src, "metering_values_hour")

    (call,) = api.calls_to_point(POINT)
    assert call.params["insertDateTime"] == "mine"
    assert call.params["includeAllMeasurements"] == "Y"


def test_a_corrected_value_overwrites_the_old_row(api_with_fixtures: FakeElhub):
    pipeline = make_pipeline("test_values_merge")
    run(pipeline, source(), "metering_values_hour")
    before = row_count(pipeline, "metering_values_hour")

    corrected = load_mock("metering_points_hour_all.json")
    for value in values_of(corrected):
        value["quantityKwh"] = 0.0
        value["insertDateTime"] = "2026-10-14T02:00:00+02:00"
    for item in corrected["data"]:
        api_with_fixtures.route_point(item["id"], {"data": [item]})
    run(pipeline, source(), "metering_values_hour")

    assert row_count(pipeline, "metering_values_hour") == before
    assert query(pipeline, "SELECT DISTINCT quantity_kwh FROM metering_values_hour") == [(0.0,)]


def test_production_and_consumption_in_one_hour_are_two_rows(api: FakeElhub):
    api.route(API_PATH, _listing(POINT))
    hour = "2026-10-12T00:00:00+02:00"
    api.route_point(POINT, payload_for(POINT, [_value(hour, NEWEST), _value(hour, NEWEST, direction="In")]))
    pipeline = make_pipeline("test_values_direction")
    run(pipeline, source(), "metering_values_hour")

    assert query(pipeline, "SELECT direction FROM metering_values_hour ORDER BY 1") == [("In",), ("Out",)]


def test_two_companies_share_a_pipeline(api: FakeElhub):
    _one_point_with_one_value(api)
    pipeline = make_pipeline("test_values_companies")
    run(pipeline, source(consumer_org="999999991"), "metering_values_hour")

    api.route(API_PATH, _listing(OTHER))
    api.route_point(OTHER, payload_for(OTHER, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:01:13+02:00")]))
    run(pipeline, source(consumer_org="999999992"), "metering_values_hour")

    assert set(cursors(pipeline)) == {POINT, OTHER}
    assert row_count(pipeline, "metering_values_hour") == 2
