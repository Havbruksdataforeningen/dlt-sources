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


def _run_values(api: FakeElhub, name: str, src=None):
    pipeline = make_pipeline(name)
    run(pipeline, src or source(), "metering_values_hour")
    return pipeline


def test_one_row_per_value_stamped_with_its_metering_point(api_with_fixtures: FakeElhub):
    """Every value of every listed point lands flat, with the point's id first on the row."""
    pipeline = _run_values(api_with_fixtures, "test_values_flat")

    listing = load_mock("metering_points_hour_all.json")
    assert row_count(pipeline, "metering_values_hour") == len(values_of(listing))
    per_point = query(pipeline, "SELECT metering_point_id, COUNT(*) FROM metering_values_hour GROUP BY 1 ORDER BY 1")
    assert [row[0] for row in per_point] == point_ids(listing)
    columns = [
        row[0]
        for row in query(
            pipeline,
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'metering_values_hour' ORDER BY ordinal_position",
        )
    ]
    assert columns[0] == "metering_point_id"
    assert "resolution" in columns
    assert query(pipeline, "SELECT DISTINCT resolution FROM metering_values_hour ORDER BY 1") == [
        ("PT15M",),
        ("PT60M",),
    ]


def test_only_the_values_table_is_written_when_only_it_is_selected(api_with_fixtures: FakeElhub):
    """The parent is read to find the ids, but a consumer who did not ask for it gets no table."""
    pipeline = _run_values(api_with_fixtures, "test_values_only")

    assert "metering_points" not in pipeline.default_schema.data_table_names()
    assert len(api_with_fixtures.calls(API_PATH)) == 1


def test_first_contact_asks_for_everything_since_the_initial_instant(api_with_fixtures: FakeElhub):
    """A point with no cursor is asked for the whole retained history: insertDateTime and no dates."""
    _run_values(api_with_fixtures, "test_values_first")

    (call,) = api_with_fixtures.calls_to_point(POINT)
    assert call.params == {"dataset": "METERING_VALUES_HOUR_RESTRICTED", "insertDateTime": ALL_RETAINED_HISTORY}


def test_the_initial_instant_is_configurable(api_with_fixtures: FakeElhub):
    _run_values(api_with_fixtures, "test_values_initial", source(initial_insert_date_time="2026-10-01T00:00:00+02:00"))

    (call,) = api_with_fixtures.calls_to_point(POINT)
    assert call.params["insertDateTime"] == "2026-10-01T00:00:00+02:00"


def test_the_next_run_resumes_each_point_from_its_own_cursor(api: FakeElhub):
    """The cursor is the latest insertDateTime the point returned, kept per point."""
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": p, "attributes": {}} for p in (POINT, OTHER)]})
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:04:25+02:00")]))
    api.route_point(OTHER, payload_for(OTHER, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:01:13+02:00")]))
    pipeline = make_pipeline("test_values_resume")

    run(pipeline, source(), "metering_values_hour")
    assert cursors(pipeline) == {POINT: "2026-10-13T02:04:25+02:00", OTHER: "2026-10-13T02:01:13+02:00"}

    run(pipeline, source(), "metering_values_hour")
    assert api.calls_to_point(POINT)[-1].params["insertDateTime"] == "2026-10-13T02:04:25+02:00"
    assert api.calls_to_point(OTHER)[-1].params["insertDateTime"] == "2026-10-13T02:01:13+02:00"


def test_the_cursor_is_the_latest_instant_not_the_latest_text(api: FakeElhub):
    """Oslo offsets change with daylight saving: `+01:00` at 02:30 is later than `+02:00` at 02:30."""
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
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


def test_nothing_new_leaves_the_cursor_where_it_was(api: FakeElhub):
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:04:25+02:00")]))
    pipeline = make_pipeline("test_values_204")
    run(pipeline, source(), "metering_values_hour")

    api.route_point(POINT, None)
    run(pipeline, source(), "metering_values_hour")

    assert cursors(pipeline) == {POINT: "2026-10-13T02:04:25+02:00"}
    assert row_count(pipeline, "metering_values_hour") == 1


def test_a_cursor_never_moves_backwards(api: FakeElhub):
    """A response holding only older inserts than the cursor, as a bound window can, leaves it alone."""
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:04:25+02:00")]))
    pipeline = make_pipeline("test_values_monotonic")
    run(pipeline, source(), "metering_values_hour")

    api.route_point(POINT, payload_for(POINT, [_value("2026-10-11T00:00:00+02:00", "2026-10-12T02:04:25+02:00")]))
    run(pipeline, source(), "metering_values_hour")

    assert cursors(pipeline) == {POINT: "2026-10-13T02:04:25+02:00"}


@pytest.mark.parametrize(
    "bound",
    [
        {"start_date": "2026-10-01T00:00:00+02:00", "end_date": "2026-10-03T00:00:00+02:00"},
        {"insert_date_time": "2026-10-01T00:00:00+02:00"},
        {"end_date": "2026-10-03T00:00:00+02:00"},
    ],
)
def test_a_bound_window_is_sent_as_given_and_the_cursor_is_neither_read_nor_advanced(api: FakeElhub, bound):
    """Binding any window param makes the request a backfill: the API's own default fills the rest."""
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:04:25+02:00")]))
    pipeline = make_pipeline("test_values_backfill")
    run(pipeline, source(), "metering_values_hour")
    stored = cursors(pipeline)

    api.route_point(POINT, payload_for(POINT, [_value("2026-10-01T00:00:00+02:00", "2026-10-20T02:04:25+02:00")]))
    src = source()
    src.metering_values_hour.bind(**bound)
    run(pipeline, src, "metering_values_hour")

    call = api.calls_to_point(POINT)[-1]
    expected = {"dataset": "METERING_VALUES_HOUR_RESTRICTED"}
    for key, value in bound.items():
        expected[{"start_date": "startDate", "end_date": "endDate", "insert_date_time": "insertDateTime"}[key]] = value
    assert call.params == expected
    assert cursors(pipeline) == stored
    assert row_count(pipeline, "metering_values_hour") == 2


def test_params_are_merged_last(api: FakeElhub):
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
    api.route_point(POINT, None)
    src = source()
    src.metering_values_hour.bind(params={"insertDateTime": "mine", "includeAllMeasurements": "Y"})
    run(make_pipeline("test_values_params"), src, "metering_values_hour")

    (call,) = api.calls_to_point(POINT)
    assert call.params["insertDateTime"] == "mine"
    assert call.params["includeAllMeasurements"] == "Y"


def test_the_same_value_reported_twice_is_one_row(api_with_fixtures: FakeElhub):
    """A corrected value, and the boundary rows every run re-fetches, overwrite rather than duplicate."""
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


def test_the_key_is_metering_point_start_time_and_direction(api_with_fixtures: FakeElhub):
    """Production (`In`) and consumption (`Out`) of one point in one hour are two rows, as the API reports them."""
    pipeline = make_pipeline("test_values_key")
    run(pipeline, source(), "metering_values_hour")

    columns = pipeline.default_schema.tables["metering_values_hour"]["columns"]
    assert [name for name, column in columns.items() if column.get("primary_key")] == [
        "metering_point_id",
        "start_time",
        "direction",
    ]


def test_two_companies_share_a_pipeline(api: FakeElhub):
    """Ids are unique across Elhub, so one cursor table serves a source per company."""
    api.route(API_PATH, {"data": [{"type": "metering-points", "id": POINT, "attributes": {}}]})
    api.route_point(POINT, payload_for(POINT, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:04:25+02:00")]))
    pipeline = make_pipeline("test_values_companies")
    run(pipeline, source(consumer_org="977106206"), "metering_values_hour")

    api.route(API_PATH, {"data": [{"type": "metering-points", "id": OTHER, "attributes": {}}]})
    api.route_point(OTHER, payload_for(OTHER, [_value("2026-10-12T00:00:00+02:00", "2026-10-13T02:01:13+02:00")]))
    run(pipeline, source(consumer_org="976543718"), "metering_values_hour")

    assert set(cursors(pipeline)) == {POINT, OTHER}
    assert row_count(pipeline, "metering_values_hour") == 2
