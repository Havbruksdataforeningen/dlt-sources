"""The `locality_week` transformer: one request per locality and week, and what each status means.

The API has one answer for "no report" — HTTP 400 — and the source skips it. Everything
else that is not a 200 with a JSON object is an error and stops the run: a week silently
dropped would look exactly like a week with no report.

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
    LOCALITIES_URL,
    THREE_WEEKS,
    http_status,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    week_url,
)

LOGGER = "dlt_source_barentswatch_fishhealth.barentswatch_fishhealth"
ONE_WEEK = WeekRange(2024, 1, 2024, 1)


def _one_locality(mock_api, locality_no: int = 90001) -> None:
    mock_api.localities(rows=[{"localityNo": locality_no, "name": "Testholmen"}])


# --- Status handling -----------------------------------------------------------


def test_400_is_skipped(mock_api, caplog):
    """A week the API has no report for is left out; the weeks around it still land."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1)
    mock_api.no_report(90001, 2024, 2)
    mock_api.week(90001, 2024, 3)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rows = list(make_source(week_range=THREE_WEEKS).locality_week)

    assert [(row["year"], row["week"]) for row in rows] == [(2024, 1), (2024, 3)]

    debug = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert debug == ["Locality 90001 2024-W2: HTTP 400, no report."]
    info = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
    assert info == ["Locality 90001: no report for 1 of 3 weeks (HTTP 400)."]


def test_all_weeks_400_yields_nothing_without_error(mock_api, caplog):
    """A locality with no report in the whole range is a 0-row load, not a failure."""
    _one_locality(mock_api)
    for year, week in THREE_WEEKS.weeks():
        mock_api.no_report(90001, year, week)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        rows = list(make_source(week_range=THREE_WEEKS).locality_week)

    assert rows == []
    assert [record.getMessage() for record in caplog.records if record.name == LOGGER] == [
        "Locality 90001: no report for 3 of 3 weeks (HTTP 400)."
    ]


def test_no_summary_when_every_week_reported(mock_api, caplog):
    _one_locality(mock_api)
    mock_api.weeks([90001], THREE_WEEKS)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        list(make_source(week_range=THREE_WEEKS).locality_week)

    assert not [record for record in caplog.records if record.name == LOGGER]


def test_500_raises_after_retries(mock_api):
    """A server error is retried by dlt's session, then stops the run — a week is never dropped quietly."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1)
    failing = mock_api.week(90001, 2024, 2, status_code=500, text="Internal Server Error")

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=THREE_WEEKS).locality_week)

    assert http_status(excinfo.value.__cause__) == 500
    assert failing.call_count > 1, "dlt's session retries a 500"
    assert week_url(90001, 2024, 3) not in mock_api.urls_requested(), "the run stops at the failure"


def test_404_raises(mock_api):
    """404 is not what the API says for an unknown locality — that is 400 — so it is an error."""
    _one_locality(mock_api)
    failing = mock_api.week(90001, 2024, 1, status_code=404, text="Not Found")

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    assert http_status(excinfo.value.__cause__) == 404
    assert failing.call_count == 1, "a 404 is not retried"


def test_401_raises(mock_api):
    """An expired or revoked token is an error to fix, not a week to skip."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1, status_code=401, text="Unauthorized")

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    assert http_status(excinfo.value.__cause__) == 401


def test_connection_error_raises(mock_api):
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1, exc=requests.exceptions.ConnectionError)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    assert isinstance(excinfo.value.__cause__, requests.exceptions.ConnectionError)


@pytest.mark.parametrize(
    "response",
    [{"text": "<html>not json</html>"}, {"json": None}, {"json": [{"liceReport": {}}]}, {"json": "a string"}],
    ids=["html", "null", "array", "string"],
)
def test_non_object_200_body_raises(mock_api, response):
    """A 200 whose body is not a JSON object is malformed, not "no data"."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1, **response)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    # `requests.JSONDecodeError` is a `ValueError` too, so the html case lands here as well.
    assert isinstance(excinfo.value.__cause__, ValueError)


# --- The week range ------------------------------------------------------------


def test_unbound_week_range_raises(mock_api):
    """There is no default range: a load has to say which weeks it wants."""
    _one_locality(mock_api)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().locality_week)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "week_range" in str(excinfo.value.__cause__)
    assert mock_api.urls_requested() == [LOCALITIES_URL], "no weekly request was made"


@pytest.mark.parametrize(
    "week_range",
    [WeekRange(2011, 1, 2011, 1), WeekRange(2024, 1, 2024, 53), WeekRange(2024, 10, 2024, 5)],
    ids=["before-first-year", "week-53-of-a-52-week-year", "inverted"],
)
def test_invalid_week_range_raises_before_any_weekly_request(mock_api, week_range):
    """A range the API would answer 400 for is refused here, where the message can say why."""
    _one_locality(mock_api)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=week_range).locality_week)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert mock_api.urls_requested() == [LOCALITIES_URL]


# --- Requests made ---------------------------------------------------------------


def test_one_request_per_locality_per_week_and_none_outside_the_range(mock_api):
    """Every locality gets every week in the range, oldest first, and nothing beyond it."""
    mock_api.localities(rows=[{"localityNo": 90001, "name": "Testholmen"}, {"localityNo": 90002, "name": "Prøvevika"}])
    mock_api.weeks([90001, 90002], WeekRange(2023, 51, 2024, 2))  # wider than the range asked for

    rows = list(make_source(week_range=WeekRange(2023, 52, 2024, 1)).locality_week)

    assert len(rows) == 4
    requested = mock_api.urls_requested()
    assert requested[0] == LOCALITIES_URL
    # dlt interleaves the per-locality generators, so only the order within a locality is fixed.
    for locality_no in (90001, 90002):
        assert [url for url in requested if f"/{locality_no}/" in url] == [
            week_url(locality_no, 2023, 52),
            week_url(locality_no, 2024, 1),
        ]
    assert len(requested) == 5


def test_token_is_fetched_once_and_sent_as_bearer(mock_api):
    """The token endpoint is asked once, and every API request carries what it answered."""
    _one_locality(mock_api)
    mock_api.weeks([90001], THREE_WEEKS)

    list(make_source(week_range=THREE_WEEKS).locality_week)

    assert mock_api.token.call_count == 1
    token_request = mock_api.requests_to(TOKEN_URL)[0]
    assert token_request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert token_request.text is not None
    sent = dict(pair.split("=") for pair in token_request.text.split("&"))
    assert sent == {
        "client_id": "test-id",
        "client_secret": "test-secret",
        "grant_type": "client_credentials",
        "scope": "api",
    }
    api_requests = [request for request in mock_api.requests if request.url != TOKEN_URL]
    assert len(api_requests) == 4
    assert all(request.headers["Authorization"] == "Bearer test-token" for request in api_requests)


def test_token_endpoint_error_raises(mock_api):
    """Wrong credentials fail at the token endpoint, before any API request."""
    mock_api.mocker.post(TOKEN_URL, status_code=400, json={"error": "invalid_client"})
    mock_api.localities()

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities_with_salmonoids)

    assert isinstance(excinfo.value.__cause__, requests.HTTPError)
    assert mock_api.urls_requested() == []


# --- Records --------------------------------------------------------------------


def test_record_is_the_body_plus_the_path_values(mock_api):
    """Each record is the response body with `localityNo`, `year` and `week` added — nothing renamed or dropped."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 5)

    (row,) = list(make_source(week_range=WeekRange(2024, 5, 2024, 5)).locality_week)

    assert row == {**load_mock("locality_week_reported.json"), "localityNo": 90001, "year": 2024, "week": 5}


def test_injected_keys_cannot_be_overridden_by_the_payload(mock_api):
    """The merge key comes from the request that was made, whatever the body claims."""
    _one_locality(mock_api, locality_no=90003)
    mock_api.week(90003, 2024, 1, json={"localityNo": 999, "year": 1900, "week": 53, "liceReport": {}})

    (row,) = list(make_source(week_range=ONE_WEEK).locality_week)

    assert (row["localityNo"], row["year"], row["week"]) == (90003, 2024, 1)


def test_injected_keys_survive_normalization(mock_api):
    """After dlt's snake_casing the key columns are `locality_no`, `year` and `week`, and hold the path values."""
    _one_locality(mock_api, locality_no=90003)
    mock_api.week(90003, 2024, 1, json={"localityNo": 999, "year": 1900, "week": 53, "liceReport": {}})

    pipeline = make_pipeline("test_injected_keys")
    pipeline.run(make_source(week_range=ONE_WEEK).with_resources("locality_week"))

    (row,) = load_rows(pipeline, "locality_week")
    assert (row["locality_no"], row["year"], row["week"]) == (90003, 2024, 1)


# --- Resource settings -----------------------------------------------------------


def test_resource_settings():
    """Both locality lists are snapshots; `locality_week` merges on the three path values."""
    source = make_source()
    assert source.localities.write_disposition == "replace"
    assert source.localities_with_salmonoids.write_disposition == "replace"
    assert source.locality_week.write_disposition == "merge"

    columns = source.locality_week.compute_table_schema().get("columns", {})
    assert [name for name, column in columns.items() if column.get("primary_key")] == ["localityNo", "year", "week"]

    normalized = source.discover_schema().tables["locality_week"]["columns"]
    assert [name for name, column in normalized.items() if column.get("primary_key")] == ["locality_no", "year", "week"]
