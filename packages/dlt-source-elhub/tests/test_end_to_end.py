"""Both resources in one run, and a run that finds nothing new."""

from tests.conftest import (
    API_PATH,
    FakeElhub,
    cursors,
    load_mock,
    make_pipeline,
    point_ids,
    query,
    row_count,
    run,
    source,
    values_of,
)


def test_a_default_run_loads_every_point_and_every_value(api_with_fixtures: FakeElhub):
    listing = load_mock("metering_points_hour_all.json")
    pipeline = make_pipeline("test_e2e")
    run(pipeline, source())

    assert row_count(pipeline, "metering_points") == len(point_ids(listing))
    assert row_count(pipeline, "metering_values_hour") == len(values_of(listing))
    assert set(cursors(pipeline)) == set(point_ids(listing))
    assert len(api_with_fixtures.calls(API_PATH)) == 1, "the list call is made once, not once per resource"


def test_a_run_with_nothing_new_changes_nothing(api_with_fixtures: FakeElhub):
    pipeline = make_pipeline("test_e2e_nothing_new")
    run(pipeline, source())
    stored = cursors(pipeline)
    points, values = row_count(pipeline, "metering_points"), row_count(pipeline, "metering_values_hour")

    for point_id in stored:
        api_with_fixtures.route_point(point_id, None)
    second = run(pipeline, source())

    assert cursors(pipeline) == stored
    assert (row_count(pipeline, "metering_points"), row_count(pipeline, "metering_values_hour")) == (points, values)
    # The load id on a point's row is when it was last listed.
    assert query(pipeline, "SELECT DISTINCT _dlt_load_id FROM metering_points") == [(second.loads_ids[0],)]
