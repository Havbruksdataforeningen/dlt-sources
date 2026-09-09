"""The two locality lists: plain `GET`s that yield the API's array as it comes."""

import pytest
from dlt.extract.exceptions import ResourceExtractionError

from tests.conftest import (
    ALL_LOCALITY_NOS,
    LOCALITIES_ALL_URL,
    LOCALITIES_URL,
    THREE_WEEKS,
    assert_row_count,
    http_status,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    week_url,
)

# resource name -> (its fixture, how `MockApi` serves it, its URL)
ROUTES = {
    "localities": ("localities.json", "all_localities", LOCALITIES_ALL_URL),
    "localities_with_salmonoids": ("localitieswithsalmonoids.json", "localities", LOCALITIES_URL),
}


@pytest.mark.parametrize("resource_name", list(ROUTES))
def test_yields_the_apis_rows_as_is_and_lands_them_as_snake_case_columns(mock_api, resource_name):
    """Every locality the API lists, with exactly the fields it sent; in DuckDB, one snake_case column per field."""
    fixture, serve, url = ROUTES[resource_name]
    getattr(mock_api, serve)()

    assert list(make_source().resources[resource_name]) == load_mock(fixture)
    assert mock_api.urls_requested() == [url]

    pipeline = make_pipeline(f"test_{resource_name}_columns")
    pipeline.run(make_source().with_resources(resource_name)).raise_on_failed_jobs()

    rows = load_rows(pipeline, resource_name)
    assert {row["locality_no"]: row["name"] for row in rows} == {
        row["localityNo"]: row["name"] for row in load_mock(fixture)
    }
    columns = pipeline.default_schema.tables[resource_name]["columns"]
    assert columns["locality_no"]["data_type"] == "bigint"
    if resource_name == "localities":
        assert columns["municipality_no"]["data_type"] == "text", "a municipality number is a string in the API"


def test_rerun_replaces_the_snapshot(mock_api):
    """`replace`: a second run with fewer localities leaves only those, not the union."""
    rows = load_mock("localities.json")
    pipeline = make_pipeline("test_localities_replace")

    mock_api.all_localities(rows=rows)
    pipeline.run(make_source().with_resources("localities")).raise_on_failed_jobs()
    assert_row_count(pipeline, "localities", len(rows))

    mock_api.all_localities(rows=rows[:2])
    pipeline.run(make_source().with_resources("localities")).raise_on_failed_jobs()
    assert {row["locality_no"] for row in load_rows(pipeline, "localities")} == {90001, 90002}


@pytest.mark.parametrize(
    ("resource_name", "status_code"),
    [("localities", 400), ("localities_with_salmonoids", 404), ("localities", 503)],
)
def test_non_200_raises(mock_api, resource_name, status_code):
    """A list has no "no data" answer; anything but 200 is an error, 400 included. Both routes share the one GET."""
    _, serve, _ = ROUTES[resource_name]
    getattr(mock_api, serve)(status_code=status_code, json={"title": "Error", "status": status_code})

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().resources[resource_name])

    assert http_status(excinfo.value.__cause__) == status_code


def test_add_filter_on_the_salmonoid_list_narrows_what_locality_week_requests(mock_api):
    """Filtering the parent narrows the transformer: the mock serves every locality-week, so a leak lands rows rather than failing."""
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)
    keep = {90002, 90004}

    source = make_source(week_range=THREE_WEEKS).with_resources("localities_with_salmonoids", "locality_week")
    source.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in keep)

    pipeline = make_pipeline("test_add_filter_narrows_weeks")
    pipeline.run(source).raise_on_failed_jobs()

    assert {row["locality_no"] for row in load_rows(pipeline, "localities_with_salmonoids")} == keep
    assert {row["locality_no"] for row in load_rows(pipeline, "locality_week")} == keep
    assert_row_count(pipeline, "locality_week", len(keep) * THREE_WEEKS.n_weeks)
    weekly_urls = [url for url in mock_api.urls_requested() if url != LOCALITIES_URL]
    assert sorted(weekly_urls) == sorted(
        week_url(locality_no, year, week) for locality_no in keep for year, week in THREE_WEEKS.weeks()
    )
