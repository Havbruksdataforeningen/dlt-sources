"""The `localities` resource: the full locality register list, from `GET /v1/geodata/fishhealth/localities`.

Every locality the API knows, salmonoid or not — number, name, municipality and register
version — landed as a `replace` snapshot. It takes no arguments and nothing reads from it:
`locality_week` iterates over the shorter salmonoid list, so selecting the weekly report
alone does not request this one.

Errors raised inside a resource reach the caller wrapped in dlt's `ResourceExtractionError`;
the assertions look through it at `__cause__`, which is what the source actually raised.
"""

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
)


def test_yields_the_apis_rows_as_is(mock_api):
    """Every locality the API lists, with exactly the fields the API sent."""
    mock_api.all_localities()

    assert list(make_source().localities) == load_mock("localities.json")
    assert mock_api.urls_requested() == [LOCALITIES_ALL_URL]


def test_rows_land_with_every_field_as_snake_case_columns(mock_api):
    """All five fields reach DuckDB, camelCase turned into snake_case, with the types the API sends."""
    mock_api.all_localities()

    pipeline = make_pipeline("test_localities_columns")
    pipeline.run(make_source().with_resources("localities")).raise_on_failed_jobs()

    rows = load_rows(pipeline, "localities")
    assert {name for row in rows for name in row if not name.startswith("_dlt")} == {
        "aqua_culture_registry_version",
        "locality_no",
        "name",
        "municipality_no",
        "municipality",
    }
    by_number = {row["locality_no"]: row for row in rows}
    assert sorted(by_number) == ALL_LOCALITY_NOS
    assert by_number[90001]["name"] == "Testholmen"
    assert by_number[90001]["municipality_no"] == "9901"
    assert by_number[90001]["municipality"] == "Fiktivdal"
    assert by_number[90003]["aqua_culture_registry_version"] == 1

    columns = pipeline.default_schema.tables["localities"]["columns"]
    assert columns["locality_no"]["data_type"] == "bigint"
    assert columns["aqua_culture_registry_version"]["data_type"] == "bigint"
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
    assert_row_count(pipeline, "localities", 2)
    assert {row["locality_no"] for row in load_rows(pipeline, "localities")} == {90001, 90002}


def test_selecting_locality_week_alone_does_not_request_the_full_list(mock_api):
    """The transformer's parent is the salmonoid list; the register list is not fetched for it."""
    mock_api.localities()
    mock_api.weeks(ALL_LOCALITY_NOS, THREE_WEEKS)

    pipeline = make_pipeline("test_localities_not_for_weeks")
    pipeline.run(make_source(week_range=THREE_WEEKS).with_resources("locality_week")).raise_on_failed_jobs()

    assert len(mock_api.requests_to(LOCALITIES_URL)) == 1
    assert mock_api.requests_to(LOCALITIES_ALL_URL) == []
    assert "localities" not in pipeline.default_schema.data_table_names()


@pytest.mark.parametrize("status_code", [400, 404, 503])
def test_non_200_raises(mock_api, status_code):
    """The list has no "no data" answer; anything but 200 is an error."""
    mock_api.all_localities(status_code=status_code, json={"title": "Error", "status": status_code})

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities)

    assert http_status(excinfo.value.__cause__) == status_code


def test_empty_array_raises(mock_api):
    """An API that lists no localities at all is broken, and a `replace` load of 0 rows would erase the table."""
    mock_api.all_localities(rows=[])

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "no localities" in str(excinfo.value.__cause__)


@pytest.mark.parametrize(
    "body",
    [
        {"localities": [{"localityNo": 90001, "name": "Testholmen"}]},
        [{"name": "Testholmen", "municipality": "Fiktivdal"}],
        [90001, 90002],
        "not json at all",
    ],
    ids=["object-envelope", "no-localityNo", "bare-numbers", "text"],
)
def test_non_array_body_raises(mock_api, body):
    """A 200 whose body is not an array of `{localityNo, ...}` is malformed, not "no data"."""
    if isinstance(body, str):
        mock_api.all_localities(text=body)
    else:
        mock_api.all_localities(json=body)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities)

    # `requests.JSONDecodeError` is a `ValueError` too, so the text case lands here as well.
    assert isinstance(excinfo.value.__cause__, ValueError)
