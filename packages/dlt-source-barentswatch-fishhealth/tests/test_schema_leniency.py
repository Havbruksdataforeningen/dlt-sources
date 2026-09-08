"""The source loads what the API sends, including what the spec does not know about."""

import copy

from dlt_source_barentswatch_fishhealth import WeekRange
from tests.conftest import assert_row_count, load_mock, load_rows, make_pipeline, make_source, query

ONE_WEEK = WeekRange(2024, 1, 2024, 1)
PAIR = ("localities_with_salmonoids", "locality_week")


def test_unknown_field_lands_as_a_new_column(mock_api):
    """A field the API adds after this release is loaded, not rejected."""
    payload = copy.deepcopy(load_mock("locality_week_reported.json"))
    payload["hasReportedBiomass"] = True

    mock_api.localities()
    mock_api.week(90001, 2024, 1, json=payload)

    pipeline = make_pipeline("test_leniency_extra_field")
    pipeline.run(make_source(locality_nos=[90001], week_range=ONE_WEEK).with_resources(*PAIR)).raise_on_failed_jobs()

    assert_row_count(pipeline, "locality_week", 1)
    assert [row[0] for row in query(pipeline, "SELECT has_reported_biomass FROM locality_week")] == [True]


def test_missing_nullable_field_does_not_fail_the_load(mock_api):
    """A nullable field the API stops sending is absent, not fatal."""
    payload = copy.deepcopy(load_mock("locality_week_reported.json"))
    del payload["pdZoneId"]
    del payload["productionArea"]

    mock_api.localities()
    mock_api.week(90001, 2024, 1, json=payload)

    pipeline = make_pipeline("test_leniency_missing_field")
    pipeline.run(make_source(locality_nos=[90001], week_range=ONE_WEEK).with_resources(*PAIR)).raise_on_failed_jobs()

    assert_row_count(pipeline, "locality_week", 1)
    (row,) = load_rows(pipeline, "locality_week")
    assert row.get("pd_zone_id") is None
    assert row.get("production_area") is None
