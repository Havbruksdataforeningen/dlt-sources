"""The `metering_points` resource: how metering points are discovered, and what a row holds."""

import json

from tests.conftest import API_PATH, FakeElhub, load_mock, make_pipeline, point_ids, query, run, source


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
