"""The API may add a field or stop sending a nullable one; neither fails a load."""

from tests.conftest import FakeElhub, load_mock, make_pipeline, query, run, source


def _listing_with(change) -> dict:
    listing = load_mock("metering_points_hour_all.json")
    for item in listing["data"]:
        for value in item["attributes"]["meteringValuesHour"]:
            change(value)
    return listing


def _serve(api: FakeElhub, listing: dict) -> None:
    api.route("/energy-data/v0/metering-points", listing)
    for item in listing["data"]:
        api.route_point(item["id"], {"data": [item]})


def test_a_field_the_api_adds_lands_as_a_column(api: FakeElhub):
    _serve(api, _listing_with(lambda value: value.__setitem__("quality", "Estimated")))
    pipeline = make_pipeline("test_lenient_extra")
    run(pipeline, source(), "metering_values_hour")

    assert query(pipeline, "SELECT DISTINCT quality FROM metering_values_hour") == [("Estimated",)]


def test_a_nullable_field_the_api_stops_sending_is_null(api: FakeElhub):
    _serve(api, _listing_with(lambda value: value.pop("quantityKwh")))
    pipeline = make_pipeline("test_lenient_missing")
    run(pipeline, source(), "metering_values_hour")

    (row,) = query(pipeline, "SELECT COUNT(*) FROM metering_values_hour WHERE quantity_kwh IS NULL")
    assert row[0] == len(_listing_with(lambda value: None)["data"]) * 4
