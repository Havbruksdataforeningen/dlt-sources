"""The `locality_week_summary` resource: one `POST` per week, the body sent as given, and what each answer means.

The filter is the request body — `LocalityReportQueryV2` in the spec — and the source has
no opinion about it: `None` is `{}`, every locality; anything else goes on the wire
verbatim. What matters is that exactly that lands at the API, because a body it does not
accept is a 400 the source would skip as "no report".

Errors raised inside a resource reach the caller wrapped in dlt's `ResourceExtractionError`;
the assertions look through it at `__cause__`, which is what the source actually raised.
"""

import logging
from pathlib import Path

import pytest
import requests
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
from dlt.extract.exceptions import ResourceExtractionError

from dlt_source_barentswatch import WeekRange
from dlt_source_barentswatch.fishhealth import TOKEN_URL
from tests.conftest import (
    THREE_WEEKS,
    http_status,
    load_mock,
    load_rows,
    make_pipeline,
    make_source,
    summary_url,
)

LOGGER = "dlt_source_barentswatch.fishhealth"
ONE_WEEK = WeekRange(2024, 1, 2024, 1)
BODY = {"productionArea": 7, "onlyWithSalmonoidLicense": True}

FIRST_ROW = load_mock("locality_week_summary.json")[0]


def _rows(week_range: WeekRange, **summary_args) -> list:
    return list(make_source(week_range=week_range, **summary_args).locality_week_summary)


# --- Requests made ---------------------------------------------------------------


def test_no_body_is_one_request_per_week_with_an_empty_body(mock_api):
    """Unfiltered is the whole country: `{}`, once per week, oldest first, and nothing beyond the range."""
    mock_api.summaries(WeekRange(2023, 51, 2024, 4))  # wider than the range asked for

    rows = _rows(WeekRange(2023, 52, 2024, 1))

    assert len(rows) == 2 * len(load_mock("locality_week_summary.json"))
    assert mock_api.urls_requested() == [summary_url(2023, 52), summary_url(2024, 1)]
    assert mock_api.bodies_posted(2023, 52) == [{}]
    assert mock_api.bodies_posted(2024, 1) == [{}]


def test_a_bound_body_is_posted_verbatim_every_week(mock_api):
    """The body goes on the wire as given — every key, nothing added, nothing renamed — once per week."""
    for year, week in THREE_WEEKS.weeks():
        mock_api.summary(year, week, body=BODY)

    rows = _rows(THREE_WEEKS, body=BODY)

    assert len(rows) == 3 * len(load_mock("locality_week_summary.json"))
    for year, week in THREE_WEEKS.weeks():
        assert mock_api.bodies_posted(year, week) == [BODY]


def test_a_body_from_config_reaches_the_wire(mock_api, isolated_run_context: Path):
    """`[sources.fishhealth.locality_week_summary.body]` in config.toml is what the API is sent.

    The one block `.dlt/config.toml.example` documents, written here into the empty project
    the autouse fixture pointed dlt at, and reloaded so dlt reads it.
    """
    settings = isolated_run_context / ".dlt"
    settings.mkdir()
    (settings / "config.toml").write_text(
        "[sources.fishhealth.locality_week_summary.body]\nproductionArea = 7\nonlyWithSalmonoidLicense = true\n"
    )
    Container()[PluggableRunContext].reload(str(isolated_run_context))
    mock_api.summary(2024, 1, body=BODY)

    rows = _rows(ONE_WEEK)

    assert len(rows) == len(load_mock("locality_week_summary.json"))
    assert mock_api.bodies_posted(2024, 1) == [BODY]


def test_token_is_fetched_once_and_sent_as_bearer_on_the_post(mock_api):
    """A `POST` goes through the same client: one token, sent on every request, with a JSON body."""
    mock_api.summaries(THREE_WEEKS)

    _rows(THREE_WEEKS, body=BODY)

    assert mock_api.token.call_count == 1
    api_requests = [request for request in mock_api.requests if request.url != TOKEN_URL]
    assert len(api_requests) == 3
    assert all(request.method == "POST" for request in api_requests)
    assert all(request.headers["Authorization"] == "Bearer test-token" for request in api_requests)
    assert all(request.headers["Content-Type"] == "application/json" for request in api_requests)


def test_selecting_the_summary_alone_requests_neither_locality_list(mock_api):
    """`production_areas.py` does this: the summary depends on nothing else."""
    mock_api.summary(2024, 1)

    source = make_source(week_range=ONE_WEEK, body=BODY).with_resources("locality_week_summary")
    assert len(list(source)) == 3
    assert mock_api.urls_requested() == [summary_url(2024, 1)]


# --- Records --------------------------------------------------------------------


def test_record_is_the_row_plus_the_key(mock_api):
    """Each record is the response row with `localityNo` (from `locality.no`), `year` and `week` added — nothing else."""
    mock_api.summary(2024, 5)

    rows = _rows(WeekRange(2024, 5, 2024, 5), body=BODY)

    assert rows == [
        {**row, "localityNo": row["locality"]["no"], "year": 2024, "week": 5}
        for row in load_mock("locality_week_summary.json")
    ]


def test_injected_keys_cannot_be_overridden_by_the_payload(mock_api):
    """The merge key comes from `locality.no` and the request made, whatever top-level keys the row claims."""
    row = {**FIRST_ROW, "localityNo": 999, "year": 1900, "week": 53}
    mock_api.summary(2024, 1, [row])

    (stamped,) = _rows(ONE_WEEK)

    assert (stamped["localityNo"], stamped["year"], stamped["week"]) == (90001, 2024, 1)


def test_injected_keys_survive_normalization(mock_api):
    """After dlt's snake_casing the key columns are `locality_no`, `year` and `week`."""
    row = {**FIRST_ROW, "localityNo": 999, "year": 1900, "week": 53}
    mock_api.summary(2024, 1, [row])

    pipeline = make_pipeline("test_summary_injected_keys")
    source = make_source(week_range=ONE_WEEK, body=BODY).with_resources("locality_week_summary")
    pipeline.run(source).raise_on_failed_jobs()

    (landed,) = load_rows(pipeline, "locality_week_summary")
    assert (landed["locality_no"], landed["year"], landed["week"]) == (90001, 2024, 1)


# --- Status handling -----------------------------------------------------------


def test_400_is_skipped_with_a_debug_line(mock_api, caplog):
    """A week the API has no summary for is left out; the weeks around it land, and nothing above DEBUG is said."""
    mock_api.summary(2024, 1)
    mock_api.summary(2024, 2, status_code=400, json=load_mock("problem_details_400.json"))
    mock_api.summary(2024, 3)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        rows = _rows(THREE_WEEKS, body=BODY)

    assert sorted({(row["year"], row["week"]) for row in rows}) == [(2024, 1), (2024, 3)]
    assert [(record.levelno, record.getMessage()) for record in caplog.records if record.name == LOGGER] == [
        (logging.DEBUG, "Summary 2024-W2: HTTP 400, no report.")
    ]


def test_empty_array_is_a_0_row_week_not_an_error(mock_api):
    """`[]` is the API's answer for a filter that matches nothing — an unknown organization, say."""
    mock_api.summary(2024, 1, [])

    assert _rows(ONE_WEEK, body={"organization": "000000000"}) == []


def test_500_raises_after_retries(mock_api):
    """A server error is retried by dlt's session, then stops the run — a week is never dropped quietly."""
    mock_api.summary(2024, 1)
    failing = mock_api.summary(2024, 2, status_code=500, text="Internal Server Error")

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(THREE_WEEKS)

    assert http_status(excinfo.value.__cause__) == 500
    assert failing.call_count > 1, "dlt's session retries a 500"
    assert summary_url(2024, 3) not in mock_api.urls_requested(), "the run stops at the failure"


@pytest.mark.parametrize("status_code", [401, 404])
def test_other_4xx_raises_without_retry(mock_api, status_code):
    """Only 400 means "no report"; anything else is an error to fix."""
    failing = mock_api.summary(2024, 1, status_code=status_code, text="Error")

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    assert http_status(excinfo.value.__cause__) == status_code
    assert failing.call_count == 1, "a 4xx is not retried"


def test_connection_error_raises(mock_api):
    mock_api.summary(2024, 1, exc=requests.exceptions.ConnectionError)

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(ONE_WEEK)

    assert isinstance(excinfo.value.__cause__, requests.exceptions.ConnectionError)


# --- The week range ------------------------------------------------------------


def test_unbound_week_range_raises(mock_api):
    """There is no default range: a load has to say which weeks it wants."""
    mock_api.summary(2024, 1)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(body=BODY).locality_week_summary)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "week_range" in str(excinfo.value.__cause__)
    assert mock_api.requests == []


def test_invalid_week_range_raises_before_any_request(mock_api):
    """A range the API would answer 400 for is refused before a request goes out.

    `WeekRange.validate` itself is `test_weeks.py`'s business; this is that it runs first.
    """
    week_range = WeekRange(2024, 10, 2024, 5)  # inverted
    mock_api.summaries(WeekRange(2024, 1, 2024, 10))

    with pytest.raises(ResourceExtractionError) as excinfo:
        _rows(week_range)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert mock_api.requests == []
