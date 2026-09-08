"""The ISO week arithmetic behind the locality-week endpoint's `{year}/{week}` path.

No API here. What is checked is the calendar: 53-week years, the year boundary, that "this
week" is decided on the Norwegian date, and that a range the API would refuse is refused
before a request is made.
"""

import datetime

import pytest

from dlt_source_barentswatch import (
    FIRST_YEAR,
    WeekRange,
    current_iso_week,
    last_n_weeks,
    weeks_in_year,
)
from dlt_source_barentswatch import weeks as weeks_module

# --- weeks_in_year -----------------------------------------------------------


@pytest.mark.parametrize(("year", "expected"), [(2014, 52), (2015, 53), (2020, 53), (2024, 52)])
def test_weeks_in_year(year, expected):
    assert weeks_in_year(year) == expected


# --- WeekRange.validate ------------------------------------------------------


@pytest.mark.parametrize(
    "week_range",
    [
        WeekRange(2024, 1, 2024, 5),
        WeekRange(FIRST_YEAR, 1, FIRST_YEAR, 1),
        WeekRange(2015, 53, 2015, 53),
    ],
    ids=["plain", "first-year", "week-53-of-a-53-week-year"],
)
def test_validate_accepts(week_range):
    assert week_range.validate() is None


@pytest.mark.parametrize(
    ("week_range", "message"),
    [
        (WeekRange(FIRST_YEAR - 1, 1, FIRST_YEAR - 1, 1), f"out of range.*{FIRST_YEAR}"),
        (WeekRange(2014, 53, 2014, 53), "ISO week out of range"),
        (WeekRange(2020, 0, 2020, 1), "ISO week out of range"),
        (WeekRange(2024, 1, 2024, 53), "ISO week out of range"),
        (WeekRange(2024, 10, 2024, 5), "inverted week range"),
        (WeekRange(2025, 1, 2024, 52), "inverted week range"),
    ],
    ids=[
        "before-first-year",
        "week-53-of-a-52-week-year",
        "week-zero",
        "end-of-range",
        "inverted",
        "inverted-across-years",
    ],
)
def test_validate_rejects(week_range, message):
    """The API answers 400 for all of these; the source says why before asking."""
    with pytest.raises(ValueError, match=message):
        week_range.validate()


# --- WeekRange.weeks and len -------------------------------------------------


@pytest.mark.parametrize(
    ("week_range", "expected"),
    [
        (WeekRange(2024, 3, 2024, 3), [(2024, 3)]),
        (WeekRange(2024, 52, 2025, 2), [(2024, 52), (2025, 1), (2025, 2)]),
        (WeekRange(2020, 52, 2021, 1), [(2020, 52), (2020, 53), (2021, 1)]),
    ],
    ids=["single-week-inclusive", "across-year-boundary", "across-53-week-year"],
)
def test_weeks_and_n_weeks(week_range, expected):
    assert list(week_range.weeks()) == expected
    assert week_range.n_weeks == len(expected)


def test_weeks_of_a_whole_year_count_its_weeks():
    assert WeekRange(2020, 1, 2020, 53).n_weeks == weeks_in_year(2020)


def test_a_week_range_is_still_a_four_tuple():
    """`len` and truthiness are the tuple's: an inverted range must not be falsy, or `if week_range:` hides it."""
    assert len(WeekRange(2024, 10, 2024, 5)) == 4
    assert WeekRange(2024, 10, 2024, 5)


# --- current_iso_week --------------------------------------------------------


def test_current_iso_week_with_fixed_today():
    assert current_iso_week(datetime.date(2025, 1, 1)) == (2025, 1)
    assert current_iso_week(datetime.date(2023, 1, 1)) == (2022, 52)


def test_current_iso_week_anchors_on_europe_oslo(monkeypatch):
    """Sunday 23:30 UTC is already Monday in Norway, so it is the next ISO week."""
    monkeypatch.setattr(weeks_module, "_now", lambda: datetime.datetime(2024, 6, 23, 23, 30, tzinfo=datetime.UTC))
    assert current_iso_week() == (2024, 26)


# --- last_n_weeks ------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "today", "expected"),
    [
        (3, datetime.date(2024, 1, 15), WeekRange(2023, 52, 2024, 2)),
        (1, datetime.date(2024, 1, 15), WeekRange(2024, 2, 2024, 2)),
        (2, datetime.date(2021, 1, 4), WeekRange(2020, 52, 2020, 53)),
    ],
    ids=["ends-on-previous-week", "single-week", "spans-a-53-week-year"],
)
def test_last_n_weeks(n, today, expected):
    """The current week is left out: it is still being reported."""
    assert last_n_weeks(n, today) == expected


def test_last_n_weeks_anchors_on_europe_oslo(monkeypatch):
    """The same instant, and the "previous week" is one later than a UTC clock would say."""
    monkeypatch.setattr(weeks_module, "_now", lambda: datetime.datetime(2024, 6, 23, 23, 30, tzinfo=datetime.UTC))
    assert last_n_weeks(1) == WeekRange(2024, 25, 2024, 25)


def test_last_n_weeks_rejects_non_positive_n():
    with pytest.raises(ValueError, match="must be >= 1"):
        last_n_weeks(0)
