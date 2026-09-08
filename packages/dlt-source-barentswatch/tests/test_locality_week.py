"""The `locality_week` transformer: one request per locality and week, and what each status means.

400 is the API's only answer for "no report" and is skipped; anything else non-200 stops the run.
"""

import logging

import pytest
import requests
from dlt.extract.exceptions import ResourceExtractionError

from dlt_source_barentswatch import WeekRange
from dlt_source_barentswatch.fishhealth import TOKEN_URL
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

LOGGER = "dlt_source_barentswatch.fishhealth"
ONE_WEEK = WeekRange(2024, 1, 2024, 1)


def _one_locality(mock_api, locality_no: int = 90001) -> None:
    mock_api.localities(rows=[{"localityNo": locality_no, "name": "Testholmen"}])


# --- Status handling -----------------------------------------------------------


def test_400_is_skipped_with_a_debug_line(mock_api, caplog):
    """A week the API has no report for is left out; the weeks around it still land, and nothing above DEBUG is said."""
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1)
    mock_api.no_report(90001, 2024, 2)
    mock_api.week(90001, 2024, 3)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rows = list(make_source(week_range=THREE_WEEKS).locality_week)

    assert [(row["year"], row["week"]) for row in rows] == [(2024, 1), (2024, 3)]
    assert [(record.levelno, record.getMessage()) for record in caplog.records if record.name == LOGGER] == [
        (logging.DEBUG, "Locality 90001 2024-W2: HTTP 400, no report.")
    ]


def test_all_weeks_400_yields_nothing_without_error(mock_api):
    """A locality with no report in the whole range is a 0-row load, not a failure."""
    _one_locality(mock_api)
    for year, week in THREE_WEEKS.weeks():
        mock_api.no_report(90001, year, week)

    assert list(make_source(week_range=THREE_WEEKS).locality_week) == []


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


@pytest.mark.parametrize("status_code", [401, 404])
def test_other_4xx_raises_without_retry(mock_api, status_code):
    """Only 400 means "no report"; an expired token or a moved route is an error to fix, not a week to skip."""
    _one_locality(mock_api)
    failing = mock_api.week(90001, 2024, 1, status_code=status_code, text="Error")

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    assert http_status(excinfo.value.__cause__) == status_code
    assert failing.call_count == 1, "a 4xx is not retried"


def test_connection_error_raises(mock_api):
    _one_locality(mock_api)
    mock_api.week(90001, 2024, 1, exc=requests.exceptions.ConnectionError)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(week_range=ONE_WEEK).locality_week)

    assert isinstance(excinfo.value.__cause__, requests.exceptions.ConnectionError)


# --- The week range ------------------------------------------------------------


def test_unbound_week_range_raises(mock_api):
    """There is no default range: a load has to say which weeks it wants."""
    _one_locality(mock_api)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().locality_week)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "week_range" in str(excinfo.value.__cause__)
    assert mock_api.urls_requested() == [LOCALITIES_URL], "no weekly request was made"


def test_invalid_week_range_raises_before_any_weekly_request(mock_api):
    """The range is validated before a request goes out; `WeekRange.validate` itself is `test_weeks.py`'s business."""
    week_range = WeekRange(2024, 10, 2024, 5)  # inverted
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
    """The token endpoint is asked once, with the client credentials, and every API request carries what it answered."""
    _one_locality(mock_api)
    mock_api.weeks([90001], THREE_WEEKS)

    list(make_source(week_range=THREE_WEEKS).locality_week)

    assert mock_api.token.call_count == 1
    token_request = mock_api.requests_to(TOKEN_URL)[0]
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
