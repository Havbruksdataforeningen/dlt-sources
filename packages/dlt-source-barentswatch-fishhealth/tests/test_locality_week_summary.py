"""The `locality_week_summary` resource: one `POST` per week per filter value, and what each answer means.

The filter is the request body, and the API takes one production area and one organization
per request, so the lists fan out: every test on requests made asserts the exact bodies sent,
in order, because a body the API does not accept (a list where it wants one integer) is a
400 the source would skip as "no report".

Errors raised inside a resource reach the caller wrapped in dlt's `ResourceExtractionError`;
the assertions look through it at `__cause__`, which is what the source actually raised.
"""

import logging

import pytest
import requests
from dlt.extract.exceptions import ResourceExtractionError

from dlt_source_barentswatch_fishhealth import WeekRange
from dlt_source_barentswatch_fishhealth.barentswatch_fishhealth import TOKEN_URL
from tests.conftest import (
    THREE_WEEKS,
    http_status,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    summary_url,
)

LOGGER = "dlt_source_barentswatch_fishhealth.barentswatch_fishhealth"
ONE_WEEK = WeekRange(2024, 1, 2024, 1)
ORG = "999999999"

# A single-row answer whose locality says which request it came from, for the fan-out tests.
FIRST_ROW = load_mock("locality_week_summary.json")[0]
SECOND_ROW = load_mock("locality_week_summary.json")[1]


def _rows(week_range: WeekRange, **summary_args) -> list:
    return list(make_source(week_range=week_range, **summary_args).locality_week_summary)


# --- Requests made ---------------------------------------------------------------


def test_no_filter_is_one_request_per_week_with_an_empty_body(mock_api):
    """Unfiltered is the whole country: `{}`, once per week, oldest first, and nothing beyond the range."""
    mock_api.summaries(WeekRange(2023, 51, 2024, 4))  # wider than the range asked for

    rows = _rows(WeekRange(2023, 52, 2024, 1))

    assert len(rows) == 2 * len(load_mock("locality_week_summary.json"))
    assert mock_api.urls_requested() == [summary_url(2023, 52), summary_url(2024, 1)]
    assert mock_api.bodies_posted(2023, 52) == [{}]
    assert mock_api.bodies_posted(2024, 1) == [{}]


def test_each_production_area_is_its_own_request(mock_api):
    """`[7, 8]` is two requests per week, one integer each — never a list, which the API refuses."""
    for year, week in THREE_WEEKS.weeks():
        mock_api.summary(year, week, [FIRST_ROW], body={"productionArea": 7})
        mock_api.summary(year, week, [SECOND_ROW], body={"productionArea": 8})

    rows = _rows(THREE_WEEKS, production_areas=[7, 8])

    for year, week in THREE_WEEKS.weeks():
        assert mock_api.bodies_posted(year, week) == [{"productionArea": 7}, {"productionArea": 8}]
    assert len(mock_api.urls_requested()) == 6
    assert [(row["year"], row["week"], row["productionArea"], row["localityNo"]) for row in rows] == [
        (2024, 1, 7, 90001),
        (2024, 1, 8, 90002),
        (2024, 2, 7, 90001),
        (2024, 2, 8, 90002),
        (2024, 3, 7, 90001),
        (2024, 3, 8, 90002),
    ]


def test_each_organization_is_its_own_request(mock_api):
    """One organization number per body: a comma-separated string matches nothing at the API."""
    mock_api.summary(2024, 1)

    _rows(ONE_WEEK, organizations=[ORG, "888888888"])

    assert mock_api.bodies_posted(2024, 1) == [{"organization": ORG}, {"organization": "888888888"}]


def test_areas_and_organizations_fan_out_into_their_product_with_and_bodies(mock_api):
    """Both lists given: one request per (area, organization) pair, area-major, each body carrying both."""
    mock_api.summary(2024, 1)

    _rows(ONE_WEEK, production_areas=[7, 8], organizations=[ORG, "888888888"])

    assert mock_api.bodies_posted(2024, 1) == [
        {"productionArea": 7, "organization": ORG},
        {"productionArea": 7, "organization": "888888888"},
        {"productionArea": 8, "organization": ORG},
        {"productionArea": 8, "organization": "888888888"},
    ]


def test_filters_are_merged_into_every_body(mock_api):
    """The escape hatch rides along with each fanned-out request."""
    mock_api.summary(2024, 1)

    _rows(ONE_WEEK, production_areas=[7, 8], filters={"allWithReport": True})

    assert mock_api.bodies_posted(2024, 1) == [
        {"productionArea": 7, "allWithReport": True},
        {"productionArea": 8, "allWithReport": True},
    ]


def test_filters_win_over_the_named_arguments(mock_api):
    """`filters` is merged last, so a key it repeats overrides `production_areas` — and the rows say so."""
    mock_api.summary(2024, 1)

    rows = _rows(ONE_WEEK, production_areas=[7], organizations=[ORG], filters={"productionArea": 9})

    assert mock_api.bodies_posted(2024, 1) == [{"productionArea": 9, "organization": ORG}]
    assert {row["productionArea"] for row in rows} == {9}


def test_filters_alone_is_one_request_per_week(mock_api):
    mock_api.summary(2024, 1)

    rows = _rows(ONE_WEEK, filters={"allWithReport": True})

    assert mock_api.bodies_posted(2024, 1) == [{"allWithReport": True}]
    assert len(rows) == 3


def test_token_is_fetched_once_and_sent_as_bearer_on_the_post(mock_api):
    """A `POST` goes through the same client: one token, sent on every request, with a JSON body."""
    mock_api.summaries(THREE_WEEKS)

    _rows(THREE_WEEKS, production_areas=[7])

    assert mock_api.token.call_count == 1
    api_requests = [request for request in mock_api.requests if request.url != TOKEN_URL]
    assert len(api_requests) == 3
    assert all(request.method == "POST" for request in api_requests)
    assert all(request.headers["Authorization"] == "Bearer test-token" for request in api_requests)
    assert all(request.headers["Content-Type"] == "application/json" for request in api_requests)


# --- Records --------------------------------------------------------------------


def test_record_is_the_row_plus_the_key_and_the_area_asked_for(mock_api):
    """Each record is the response row with `localityNo`, `year`, `week` and `productionArea` added — nothing renamed."""
    mock_api.summary(2024, 5)

    rows = _rows(WeekRange(2024, 5, 2024, 5), production_areas=[7])

    assert rows == [
        {**row, "localityNo": row["locality"]["no"], "year": 2024, "week": 5, "productionArea": 7}
        for row in load_mock("locality_week_summary.json")
    ]


@pytest.mark.parametrize(
    "summary_args",
    [{}, {"organizations": [ORG]}, {"filters": {"allWithReport": True}}],
    ids=["unfiltered", "organization-only", "filters-only"],
)
def test_production_area_is_absent_when_the_request_did_not_carry_one(mock_api, summary_args):
    """A row does not say which area it came from, and the source does not guess: no area filter, no column."""
    mock_api.summary(2024, 1)

    rows = _rows(ONE_WEEK, **summary_args)

    assert rows
    assert all("productionArea" not in row for row in rows)


def test_injected_keys_cannot_be_overridden_by_the_payload(mock_api):
    """The merge key and the area come from the request that was made, whatever the row claims."""
    row = {**FIRST_ROW, "localityNo": 999, "year": 1900, "week": 53, "productionArea": 1}
    mock_api.summary(2024, 1, [row])

    (tagged,) = _rows(ONE_WEEK, production_areas=[7])

    assert (tagged["localityNo"], tagged["year"], tagged["week"], tagged["productionArea"]) == (90001, 2024, 1, 7)


def test_injected_keys_survive_normalization(mock_api):
    """After dlt's snake_casing the columns are `locality_no`, `year`, `week` and `production_area`."""
    row = {**FIRST_ROW, "localityNo": 999, "year": 1900, "week": 53}
    mock_api.summary(2024, 1, [row])

    pipeline = make_pipeline("test_summary_injected_keys")
    source = make_source(week_range=ONE_WEEK, production_areas=[7]).with_resources("locality_week_summary")
    pipeline.run(source).raise_on_failed_jobs()

    (landed,) = load_rows(pipeline, "locality_week_summary")
    assert (landed["locality_no"], landed["year"], landed["week"], landed["production_area"]) == (90001, 2024, 1, 7)


# --- Status handling -----------------------------------------------------------


def test_400_is_skipped(mock_api, caplog):
    """A week the API has no summary for is left out with a DEBUG line naming the body; the weeks around it land."""
    mock_api.summary(2024, 1)
    mock_api.summary(2024, 2, status_code=400, json=load_mock("problem_details_400.json"))
    mock_api.summary(2024, 3)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rows = _rows(THREE_WEEKS, production_areas=[7])

    assert sorted({(row["year"], row["week"]) for row in rows}) == [(2024, 1), (2024, 3)]
    assert [(record.levelno, record.getMessage()) for record in caplog.records if record.name == LOGGER] == [
        (logging.DEBUG, "Summary 2024-W2 {'productionArea': 7}: HTTP 400, no report.")
    ]


def test_400_for_one_filter_value_does_not_stop_the_others(mock_api, caplog):
    """The skip is per request: area 7 answering 400 still lets area 8 land the same week."""
    mock_api.summary(2024, 1, status_code=400, json=load_mock("problem_details_400.json"), body={"productionArea": 7})
    mock_api.summary(2024, 1, [SECOND_ROW], body={"productionArea": 8})

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rows = _rows(ONE_WEEK, production_areas=[7, 8])

    assert [(row["productionArea"], row["localityNo"]) for row in rows] == [(8, 90002)]
    assert mock_api.bodies_posted(2024, 1) == [{"productionArea": 7}, {"productionArea": 8}]
    assert [record.getMessage() for record in caplog.records if record.name == LOGGER] == [
        "Summary 2024-W1 {'productionArea': 7}: HTTP 400, no report."
    ]


def test_all_weeks_400_yields_nothing_without_error(mock_api):
    mock_api.summaries(THREE_WEEKS, status_code=400, json=load_mock("problem_details_400.json"))

    assert _rows(THREE_WEEKS, production_areas=[7]) == []


def test_empty_array_is_a_0_row_week_not_an_error(mock_api):
    """`[]` is the API's answer for a filter that matches nothing — an unknown organization, say."""
    mock_api.summary(2024, 1, [])

    assert _rows(ONE_WEEK, organizations=["000000000"]) == []


def test_500_raises_after_retries(mock_api):
    """A server error is retried by dlt's session, then stops the run — a week is never dropped quietly."""
    mock_api.summary(2024, 1)
    failing = mock_api.summary(2024, 2, status_code=500, text="Internal Server Error")

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(THREE_WEEKS, production_areas=[7])

    assert http_status(excinfo.value.__cause__) == 500
    assert failing.call_count > 1, "dlt's session retries a 500"
    assert summary_url(2024, 3) not in mock_api.urls_requested(), "the run stops at the failure"


def test_404_raises(mock_api):
    """404 is not what the API says for "no report" — that is 400 — so it is an error."""
    failing = mock_api.summary(2024, 1, status_code=404, text="Not Found")

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK, production_areas=[7])

    assert http_status(excinfo.value.__cause__) == 404
    assert failing.call_count == 1, "a 404 is not retried"


def test_401_raises(mock_api):
    mock_api.summary(2024, 1, status_code=401, text="Unauthorized")

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    assert http_status(excinfo.value.__cause__) == 401


def test_connection_error_raises(mock_api):
    mock_api.summary(2024, 1, exc=requests.exceptions.ConnectionError)

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    assert isinstance(excinfo.value.__cause__, requests.exceptions.ConnectionError)


@pytest.mark.parametrize(
    "response",
    [
        {"text": "<html>not json</html>"},
        {"json": None},
        {"json": {"localities": [FIRST_ROW]}},
        {"json": "a string"},
        {"json": [90001, 90002]},
    ],
    ids=["html", "null", "object-envelope", "string", "bare-numbers"],
)
def test_non_array_200_body_raises(mock_api, response):
    """A 200 whose body is not a JSON array of objects is malformed, not "no data"."""
    mock_api.summary(2024, 1, **response)

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    # `requests.JSONDecodeError` is a `ValueError` too, so the html case lands here as well.
    assert isinstance(excinfo.value.__cause__, ValueError)


@pytest.mark.parametrize(
    "row",
    [
        {**FIRST_ROW, "locality": {"name": "Testholmen", "isOnLand": False}},
        {**FIRST_ROW, "locality": None},
        {key: value for key, value in FIRST_ROW.items() if key != "locality"},
    ],
    ids=["no-number", "null-locality", "no-locality"],
)
def test_row_without_a_locality_number_raises(mock_api, row):
    """There is nothing to key such a row on, and a merge without a key would duplicate on every run."""
    mock_api.summary(2024, 1, [FIRST_ROW, row])

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "locality.no" in str(excinfo.value.__cause__)


# --- Arguments ------------------------------------------------------------------


@pytest.mark.parametrize(
    "summary_args", [{"production_areas": []}, {"organizations": []}], ids=["areas", "organizations"]
)
def test_empty_filter_list_raises_before_any_request(mock_api, summary_args):
    """An empty list is a mistake, not "unfiltered" — that is what `None` means."""
    mock_api.summary(2024, 1)

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK, **summary_args)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "empty list" in str(excinfo.value.__cause__)
    assert mock_api.requests == []


def test_unbound_week_range_raises(mock_api):
    """There is no default range: a load has to say which weeks it wants."""
    mock_api.summary(2024, 1)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(production_areas=[7]).locality_week_summary)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "week_range" in str(excinfo.value.__cause__)
    assert mock_api.requests == []


@pytest.mark.parametrize(
    "week_range",
    [WeekRange(2011, 1, 2011, 1), WeekRange(2024, 1, 2024, 53), WeekRange(2024, 10, 2024, 5)],
    ids=["before-first-year", "week-53-of-a-52-week-year", "inverted"],
)
def test_invalid_week_range_raises_before_any_request(mock_api, week_range):
    """A range the API would answer 400 for is refused before a request goes out.

    By `WeekRange.validate()` inside the resource, wrapped by dlt — the range is a plain
    4-tuple to everything before that, so nothing measures it earlier.
    """
    mock_api.summaries(WeekRange(2024, 1, 2024, 10))

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(week_range, production_areas=[7])

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert mock_api.requests == []


# --- Resource settings -----------------------------------------------------------


def test_resource_settings():
    """`locality_week_summary` merges on the same three values as `locality_week`, and depends on nothing."""
    source = make_source()
    assert source.locality_week_summary.write_disposition == "merge"
    assert source.locality_week_summary._pipe.parent is None

    columns = source.locality_week_summary.compute_table_schema().get("columns", {})
    assert [name for name, column in columns.items() if column.get("primary_key")] == ["localityNo", "year", "week"]

    normalized = source.discover_schema().tables["locality_week_summary"]["columns"]
    assert [name for name, column in normalized.items() if column.get("primary_key")] == ["locality_no", "year", "week"]


def test_selecting_the_summary_alone_makes_no_other_request(mock_api):
    """`production_areas.py` does this: the summary needs neither the locality list nor the detailed report."""
    mock_api.summary(2024, 1)

    source = make_source(week_range=ONE_WEEK, production_areas=[7]).with_resources("locality_week_summary")
    assert len(list(source)) == 3
    assert mock_api.urls_requested() == [summary_url(2024, 1)]
