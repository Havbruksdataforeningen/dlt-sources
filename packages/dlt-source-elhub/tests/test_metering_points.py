"""The `metering_points` resource: how metering points are discovered, and what a row holds."""

import json

from tests.conftest import (
    API_PATH,
    FakeElhub,
    load_mock,
    make_pipeline,
    payload_for,
    point_ids,
    query,
    run,
    source,
    values_of,
)


def test_one_row_per_metering_point_without_its_values(api_with_fixtures: FakeElhub):
    pipeline = make_pipeline("test_points")
    run(pipeline, source(), "metering_points")

    listing = load_mock("metering_points_hour_all.json")
    assert query(pipeline, "SELECT id, type FROM metering_points ORDER BY id") == [
        (point_id, "metering-points") for point_id in point_ids(listing)
    ]
    columns = query(pipeline, "SELECT column_name FROM information_schema.columns WHERE table_name = 'metering_points'")
    assert not {name for (name,) in columns if "attributes" in name or "metering_values" in name}


def test_an_attribute_other_than_the_values_is_kept(api: FakeElhub):
    item = {"type": "metering-points", "id": "1", "attributes": {"status": "Active", "meteringValuesHour": []}}
    api.route(API_PATH, {"data": [item]})
    pipeline = make_pipeline("test_points_attributes")
    run(pipeline, source(), "metering_points")

    (row,) = query(pipeline, "SELECT attributes FROM metering_points")
    assert json.loads(row[0]) == {"status": "Active"}


def test_metering_point_ids_keeps_only_those_points_and_what_they_feed(api_with_fixtures: FakeElhub):
    kept, dropped = point_ids(load_mock("metering_points_hour_all.json"))[:2]
    src = source()
    src.metering_points.bind(metering_point_ids=[kept])
    pipeline = make_pipeline("test_points_filter")
    run(pipeline, src, "metering_points", "metering_values_hour")

    assert query(pipeline, "SELECT id FROM metering_points") == [(kept,)]
    assert query(pipeline, "SELECT DISTINCT metering_point_id FROM metering_values_hour") == [(kept,)]
    assert api_with_fixtures.calls_to_point(kept) and not api_with_fixtures.calls_to_point(dropped)


def test_the_dataset_is_always_named_and_dates_are_passed_as_given(api: FakeElhub):
    api.route(API_PATH, None)
    src = source()
    src.metering_points.bind(start_date="2026-10-12", end_date="2026-10-13T00:00:00+02:00")
    run(make_pipeline("test_points_window"), src, "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.params == {
        "dataset": "METERING_VALUES_HOUR_RESTRICTED",
        "startDate": "2026-10-12",
        "endDate": "2026-10-13T00:00:00+02:00",
    }


def test_a_window_wider_than_a_day_finds_the_points_the_end_user_has_since_lost(api: FakeElhub):
    """Elhub lists a point for the days it belonged to the end user, and by id returns that period."""
    listed = {"2026-02-27": ["kept", "lost"], "2026-02-28": ["kept", "lost"], "2026-03-01": ["kept", "new"]}
    api.route(API_PATH, lambda params: {"data": [{"id": point} for point in listed[params["startDate"]]]})
    value = values_of(load_mock("metering_points_hour_by_id.json"))[0]
    for point in ["kept", "lost", "new"]:
        api.route_point(point, payload_for(point, [value]))
    src = source()
    src.metering_points.bind(start_date="2026-02-27", end_date="2026-03-02")
    pipeline = make_pipeline("test_points_days")
    run(pipeline, src, "metering_points", "metering_values_hour")

    assert [(call.params["startDate"], call.params["endDate"]) for call in api.calls(API_PATH)] == [
        ("2026-02-27", "2026-02-28"),
        ("2026-02-28", "2026-03-01"),
        ("2026-03-01", "2026-03-02"),
    ]
    assert query(pipeline, "SELECT id FROM metering_points ORDER BY id") == [("kept",), ("lost",), ("new",)]
    assert [len(api.calls_to_point(point)) for point in ["kept", "lost", "new"]] == [1, 1, 1]
    assert query(pipeline, "SELECT DISTINCT metering_point_id FROM metering_values_hour ORDER BY 1") == [
        ("kept",),
        ("lost",),
        ("new",),
    ]


def test_the_days_of_a_window_stay_at_oslo_midnight_across_daylight_saving(api: FakeElhub):
    api.route(API_PATH, None)
    src = source()
    src.metering_points.bind(start_date="2026-03-28T00:00:00+01:00", end_date="2026-03-31T00:00:00+02:00")
    run(make_pipeline("test_points_dst"), src, "metering_points")

    assert [(call.params["startDate"], call.params["endDate"]) for call in api.calls(API_PATH)] == [
        ("2026-03-28T00:00:00+01:00", "2026-03-29T00:00:00+01:00"),
        ("2026-03-29T00:00:00+01:00", "2026-03-30T00:00:00+02:00"),
        ("2026-03-30T00:00:00+02:00", "2026-03-31T00:00:00+02:00"),
    ]


def test_no_content_is_no_rows(api: FakeElhub):
    api.route(API_PATH, None)
    pipeline = make_pipeline("test_points_empty")
    run(pipeline, source(), "metering_points")

    assert "metering_points" not in pipeline.default_schema.data_table_names()


def test_the_headers_elhub_requires_and_the_ones_a_caller_adds(api: FakeElhub):
    api.route(API_PATH, None)
    run(make_pipeline("test_points_headers"), source(), "metering_points")
    src = source(user_agent="acme-pipeline", headers={"X-Elhub-GLN": "7080000000000"})
    run(make_pipeline("test_points_headers_custom"), src, "metering_points")

    default, custom = api.calls(API_PATH)
    assert default.headers["Accept"] == "application/json" and default.headers["User-Agent"]
    assert custom.headers["User-Agent"] == "acme-pipeline"
    assert custom.headers["X-Elhub-GLN"] == "7080000000000"
