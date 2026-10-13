"""The `metering_points` resource: how metering points are discovered, and what a row holds."""

import json

from tests.conftest import (
    API_PATH,
    FakeElhub,
    load_mock,
    make_pipeline,
    point_ids,
    query,
    row_count,
    run,
    source,
)


def test_one_row_per_metering_point_without_its_values(api_with_fixtures: FakeElhub):
    """The list call is a values call; the values go to `metering_values_hour`, the point stays."""
    pipeline = make_pipeline("test_points")
    run(pipeline, source(), "metering_points")

    listing = load_mock("metering_points_hour_all.json")
    rows = query(pipeline, "SELECT id, type FROM metering_points ORDER BY id")
    assert rows == [(point_id, "metering-points") for point_id in point_ids(listing)]
    columns = {
        row[0]
        for row in query(
            pipeline, "SELECT column_name FROM information_schema.columns WHERE table_name = 'metering_points'"
        )
    }
    assert "attributes" not in columns
    assert not {name for name in columns if "metering_values" in name}


def test_an_attribute_other_than_the_values_is_kept(api: FakeElhub):
    """Elhub may add attributes to a metering point; only the values list is the other table's."""
    item = {"type": "metering-points", "id": "1", "attributes": {"status": "Active", "meteringValuesHour": []}}
    api.route(API_PATH, {"data": [item]})
    pipeline = make_pipeline("test_points_attributes")
    run(pipeline, source(), "metering_points")

    (row,) = query(pipeline, "SELECT attributes FROM metering_points")
    assert json.loads(row[0]) == {"status": "Active"}


def test_metering_point_ids_keeps_only_those_points_and_what_they_feed(api_with_fixtures: FakeElhub):
    """The filter sits on the list, so the values transformer reads only the kept points."""
    listing = point_ids(load_mock("metering_points_hour_all.json"))
    kept, dropped = listing[0], listing[1]
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
    src.metering_points.bind(start_date="2026-10-12T00:00:00+02:00", end_date="2026-10-13T00:00:00+02:00")
    run(make_pipeline("test_points_window"), src, "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.params == {
        "dataset": "METERING_VALUES_HOUR_RESTRICTED",
        "startDate": "2026-10-12T00:00:00+02:00",
        "endDate": "2026-10-13T00:00:00+02:00",
    }


def test_params_are_merged_last(api: FakeElhub):
    """The escape hatch for a param the API grows later wins over the named ones."""
    api.route(API_PATH, None)
    src = source()
    src.metering_points.bind(start_date="2026-10-12T00:00:00+02:00", params={"startDate": "later", "usageDate": "x"})
    run(make_pipeline("test_points_params"), src, "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.params["startDate"] == "later"
    assert call.params["usageDate"] == "x"


def test_no_content_is_no_rows(api: FakeElhub):
    """A company with no metering points is `204` with no body, which lands nothing and fails nothing."""
    api.route(API_PATH, None)
    pipeline = make_pipeline("test_points_empty")
    run(pipeline, source(), "metering_points")

    assert "metering_points" not in pipeline.default_schema.data_table_names()


def test_rereading_the_same_points_merges_on_id(api_with_fixtures: FakeElhub):
    pipeline = make_pipeline("test_points_merge")
    run(pipeline, source(), "metering_points")
    run(pipeline, source(), "metering_points")

    assert row_count(pipeline, "metering_points") == 2


def test_the_two_headers_elhub_requires_and_the_ones_a_caller_adds(api: FakeElhub):
    api.route(API_PATH, None)
    src = source(user_agent="acme-pipeline", headers={"X-Elhub-GLN": "7080000000000"})
    run(make_pipeline("test_points_headers"), src, "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.headers["Accept"] == "application/json"
    assert call.headers["User-Agent"] == "acme-pipeline"
    assert call.headers["X-Elhub-GLN"] == "7080000000000"


def test_the_default_user_agent_names_the_package(api: FakeElhub):
    api.route(API_PATH, None)
    run(make_pipeline("test_points_ua"), source(), "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.headers["User-Agent"] == "dlt-source-elhub"
