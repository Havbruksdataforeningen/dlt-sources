"""Splitting a window too wide for the API: `REFERENCE.md#windows-are-split-to-fit-the-apis-cap`.

The caps themselves are data (`MAX_WINDOW_DAYS`). What is asserted here is the arithmetic
around them, which a moved cap must keep working.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import dlt
import pytest

from dlt_source_aquabyte import MAX_WINDOW_DAYS, aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    Endpoint,
    endpoint,
    params_sent,
    resource_signature,
    run_source,
    serve,
)

# One time-based resource and one date-based one, which is the whole of the difference:
# the same arithmetic on `fromTime`/`toTime` and on `fromDate`/`toDate`.
ENVIRONMENTAL = endpoint("environmental")
BIOMASS = endpoint("biomass")


def _run(mock_rest_client, endpoint: Endpoint, name: str, **bound):
    """Serve the endpoint's mock, run its resource, and return the params of every request."""
    mock_rest_client.paginate.reset_mock()
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})
    source = aquabyte_source(**SOURCE_CONFIG)
    source.resources[endpoint.resource].bind(**bound)
    run_source(f"{name}_{endpoint.resource}", source, [endpoint.resource])
    return params_sent(mock_rest_client, endpoint.path)


def _window(endpoint: Endpoint, start: str, end: str | None = None):
    """The `incremental_*` binding that carries this window."""
    return {endpoint.incremental_argument: dlt.sources.incremental(initial_value=start, end_value=end)}


def test_a_window_at_exactly_the_cap_is_one_request(mock_rest_client):
    """The caps are inclusive, so the widest legal window must not be split."""
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        "test_at_cap",
        period="15min",
        **_window(ENVIRONMENTAL, "2026-01-01T00:00:00Z", "2026-01-08T00:00:00Z"),
    )

    assert [(one["fromTime"], one["toTime"]) for one in sent] == [("2026-01-01T00:00:00Z", "2026-01-08T00:00:00Z")]


def test_a_window_one_day_over_the_cap_is_two_contiguous_requests(mock_rest_client):
    """Oldest first, each ending where the next begins, and the caller's own edges kept."""
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        "test_over_cap",
        period="15min",
        **_window(ENVIRONMENTAL, "2026-01-01T00:00:00Z", "2026-01-09T00:00:00Z"),
    )

    assert [(one["fromTime"], one["toTime"]) for one in sent] == [
        ("2026-01-01T00:00:00Z", "2026-01-08T00:00:00Z"),
        ("2026-01-08T00:00:00Z", "2026-01-09T00:00:00Z"),
    ]


def test_a_date_window_splits_the_same_way(mock_rest_client):
    """`fromDate`/`toDate` take the same arithmetic, at the date resources' 366-day cap.

    `toDate` is inclusive where `toTime` is exclusive, so the next sub-window starts the day
    after the last one ended: contiguous, and no date asked for twice.
    """
    sent = _run(
        mock_rest_client,
        BIOMASS,
        "test_date_split",
        **_window(BIOMASS, "2026-01-01", "2027-01-03"),
    )

    assert [(one["fromDate"], one["toDate"]) for one in sent] == [
        ("2026-01-01", "2027-01-02"),
        ("2027-01-03", "2027-01-03"),
    ]


def test_a_date_window_at_exactly_the_cap_is_one_request(mock_rest_client):
    sent = _run(mock_rest_client, BIOMASS, "test_date_at_cap", **_window(BIOMASS, "2026-01-01", "2027-01-02"))

    assert [(one["fromDate"], one["toDate"]) for one in sent] == [("2026-01-01", "2027-01-02")]


@pytest.mark.parametrize(
    ("period", "expected_windows"),
    [("15min", 5), ("h", 2), ("D", 1), (None, 1)],
)
def test_the_period_decides_how_many_requests_a_window_becomes(mock_rest_client, period, expected_windows):
    """The cap is a property of (resource, grain): 7 days at `15min`, 31 at `h`, 366 at `D`.

    `period` unset resolves to the endpoint's own default grain, which is the daily one —
    so omitting it buys the widest cap, not the narrowest.
    """
    bound = {"period": period} if period is not None else {}
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        f"test_period_{period}",
        **bound,
        **_window(ENVIRONMENTAL, "2026-01-01T00:00:00Z", "2026-02-02T00:00:00Z"),
    )

    assert len(sent) == expected_windows
    assert sent[0]["fromTime"] == "2026-01-01T00:00:00Z"
    assert sent[-1]["toTime"] == "2026-02-02T00:00:00Z"


def test_an_open_ended_incremental_still_sends_an_end(mock_rest_client):
    """No `end_value` means "up to now", and now is sent rather than left to the API."""
    start = (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = _run(mock_rest_client, ENVIRONMENTAL, "test_open_end", **_window(ENVIRONMENTAL, start))

    (one,) = sent
    assert one["fromTime"] == start
    ended_at = datetime.fromisoformat(one["toTime"])
    assert timedelta(0) <= datetime.now(tz=UTC) - ended_at < timedelta(minutes=5)


def test_an_open_ended_date_incremental_ends_today(mock_rest_client):
    """The date resources get today rather than a timestamp, in the spelling they cursor on."""
    start = (datetime.now(tz=UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    sent = _run(mock_rest_client, BIOMASS, "test_open_end_date", **_window(BIOMASS, start))

    (one,) = sent
    assert one["toDate"] == datetime.now(tz=UTC).strftime("%Y-%m-%d")


def test_an_open_ended_catch_up_wider_than_the_cap_splits(mock_rest_client):
    """The case that made this a correctness bug: a cursor left far behind still loads."""
    start = (datetime.now(tz=UTC) - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = _run(mock_rest_client, ENVIRONMENTAL, "test_catch_up", period="15min", **_window(ENVIRONMENTAL, start))

    assert len(sent) == 3, "20 days at a 7-day cap is three requests"
    assert sent[0]["fromTime"] == start
    assert [one["fromTime"] for one in sent] == sorted(one["fromTime"] for one in sent), "oldest first"
    assert [one["toTime"] for one in sent[:-1]] == [one["fromTime"] for one in sent[1:]], "contiguous"


def test_a_window_sent_through_params_is_left_alone(mock_rest_client):
    """The passthrough wins over every named param, so a caller who sends a window owns it."""
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        "test_params_window",
        period="15min",
        params={"fromTime": "2020-01-01T00:00:00Z", "toTime": "2026-01-01T00:00:00Z"},
    )

    assert len(sent) == 1


def test_date_sub_windows_use_the_whole_cap_without_overlapping(mock_rest_client):
    """The API measures `toDate - fromDate`, confirmed at the boundary on 2026-08-28.

    So a sub-window may be a full 366 wide. `toDate` is inclusive, so the next one starts
    the day after — which costs a day of width nowhere, and asks for no date twice.
    """
    sent = _run(mock_rest_client, BIOMASS, "test_whole_cap", **_window(BIOMASS, "2026-01-01", "2029-01-05"))

    cap = 366
    edges = [(date.fromisoformat(one["fromDate"]), date.fromisoformat(one["toDate"])) for one in sent]

    assert len(sent) == 3, "1100 days at a 366-day cap is three requests, not four"
    assert all((to - since).days <= cap for since, to in edges), "no request may exceed the cap"
    assert max((to - since).days for since, to in edges) == cap, "and the cap must be used in full"
    assert all(later[0] - earlier[1] == timedelta(days=1) for earlier, later in pairwise(edges)), (
        "each sub-window starts the day after the last one ended"
    )


def test_a_period_sent_through_params_sizes_the_windows(mock_rest_client):
    """`params` wins over the named `period` on the wire, so it must pick the cap too."""
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        "test_params_period",
        params={"period": "15min"},
        **_window(ENVIRONMENTAL, "2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z"),
    )

    assert all(one["period"] == "15min" for one in sent)
    assert len(sent) == 9, "59 days at the 15min cap of 7, not the daily cap of 366"


def test_a_cursor_spelled_with_a_space_is_still_a_time(mock_rest_client):
    """`2026-01-01 00:00:00` is valid ISO 8601 and must not be read as a date.

    The seams keep the cursor's spelling, so one load does not mix two."""
    sent = _run(
        mock_rest_client,
        ENVIRONMENTAL,
        "test_space_cursor",
        period="15min",
        **_window(ENVIRONMENTAL, "2026-01-01 00:00:00", "2026-01-09 00:00:00"),
    )

    assert [(one["fromTime"], one["toTime"]) for one in sent] == [
        ("2026-01-01 00:00:00", "2026-01-08 00:00:00"),
        ("2026-01-08 00:00:00", "2026-01-09 00:00:00"),
    ]


def test_a_start_and_an_end_of_different_kinds_are_passed_through(mock_rest_client, caplog):
    """A date against a timestamp cannot be measured, so the window goes out as it came.

    With a warning: the API would refuse this one, and dlt hides the reason by default.
    """
    with caplog.at_level(logging.WARNING, logger="dlt_source_aquabyte.windows"):
        sent = _run(
            mock_rest_client,
            BIOMASS,
            "test_mismatched_window",
            **_window(BIOMASS, "2020-01-01", "2026-01-01T00:00:00Z"),
        )

    assert [(one["fromDate"], one["toDate"]) for one in sent] == [("2020-01-01", "2026-01-01T00:00:00Z")]
    assert "biomass" in caplog.text
    assert "366" in caplog.text, "the warning names the cap the request may break"


def test_a_cursor_that_is_not_a_date_is_passed_through(mock_rest_client, caplog):
    """A start no reader can parse is the API's to refuse; the warning names the value."""
    with caplog.at_level(logging.WARNING, logger="dlt_source_aquabyte.windows"):
        sent = _run(mock_rest_client, BIOMASS, "test_unreadable_cursor", **_window(BIOMASS, "not-a-date"))

    assert [(one["fromDate"], one.get("toDate")) for one in sent] == [("not-a-date", None)]
    assert "not-a-date" in caplog.text


def test_a_window_the_source_can_measure_logs_nothing(mock_rest_client, caplog):
    """The warning is for the windows it gave up on, not for every run."""
    with caplog.at_level(logging.WARNING, logger="dlt_source_aquabyte.windows"):
        _run(mock_rest_client, BIOMASS, "test_quiet", **_window(BIOMASS, "2026-01-01", "2029-01-05"))

    assert caplog.text == ""


def test_every_windowed_resource_has_a_published_cap():
    """A consumer sizing its own chunks reads the cap from the package, not from a failed run.

    So a resource that takes an `incremental_*` argument must have an entry, and every
    entry must name such a resource.
    """
    source = aquabyte_source(**SOURCE_CONFIG)
    windowed = {
        name
        for name in source.resources
        if any(argument.startswith("incremental_") for argument in resource_signature(source, name).parameters)
    }

    assert windowed, "the source must have windowed resources for this test to mean anything"
    assert {resource for resource, _ in MAX_WINDOW_DAYS} == windowed
