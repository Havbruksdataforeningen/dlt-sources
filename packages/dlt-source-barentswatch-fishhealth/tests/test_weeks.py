"""The ISO week arithmetic behind the locality-week endpoint's `{year}/{week}` path.

No API here. What is checked is the calendar: 53-week years, the year boundary, that "this
week" is decided on the Norwegian date, and that a range the API would refuse is refused
before a request is made.
"""

import datetime

import pytest

from dlt_source_barentswatch_fishhealth import (
    FIRST_YEAR,
    WeekRange,
    current_iso_week,
    last_n_weeks,
    weeks_in_year,
)
from dlt_source_barentswatch_fishhealth import weeks as weeks_module

# --- weeks_in_year -----------------------------------------------------------


@pytest.mark.parametrize(("year", "expected"), [(2014, 52), (2015, 53), (2020, 53), (2024, 52), (2026, 53)])
def test_weeks_in_year(year, expected):
    assert weeks_in_year(year) == expected


# --- WeekRange.validate ------------------------------------------------------


def test_validate_accepts_valid_range():
    assert WeekRange(2024, 1, 2024, 5).validate() is None


def test_validate_rejects_year_before_first_year():
    """The API answers 400 for 2011; the source says why before asking."""
    with pytest.raises(ValueError, match=f"out of range.*{FIRST_YEAR}"):
        WeekRange(FIRST_YEAR - 1, 1, FIRST_YEAR - 1, 1).validate()


def test_validate_accepts_first_year():
    assert WeekRange(FIRST_YEAR, 1, FIRST_YEAR, 1).validate() is None


def test_validate_rejects_week_above_year_length():
    with pytest.raises(ValueError, match="ISO week out of range"):
        WeekRange(2014, 53, 2014, 53).validate()


def test_validate_accepts_week_53_in_a_53_week_year():
    assert WeekRange(2015, 53, 2015, 53).validate() is None


def test_validate_rejects_week_zero():
    with pytest.raises(ValueError, match="ISO week out of range"):
        WeekRange(2020, 0, 2020, 1).validate()


def test_validate_checks_the_end_of_the_range_too():
    with pytest.raises(ValueError, match="ISO week out of range"):
        WeekRange(2024, 1, 2024, 53).validate()


def test_validate_rejects_inverted_range():
    with pytest.raises(ValueError, match="inverted week range"):
        WeekRange(2024, 10, 2024, 5).validate()


def test_validate_rejects_inverted_range_across_years():
    with pytest.raises(ValueError, match="inverted week range"):
        WeekRange(2025, 1, 2024, 52).validate()


# --- WeekRange.weeks and len -------------------------------------------------


def test_weeks_iterates_across_year_boundary():
    assert list(WeekRange(2024, 52, 2025, 2).weeks()) == [(2024, 52), (2025, 1), (2025, 2)]


def test_weeks_iterates_across_53_week_year():
    assert list(WeekRange(2020, 52, 2021, 1).weeks()) == [(2020, 52), (2020, 53), (2021, 1)]


def test_weeks_single_week_is_inclusive():
    assert list(WeekRange(2024, 3, 2024, 3).weeks()) == [(2024, 3)]


def test_weeks_of_a_whole_year_count_its_weeks():
    assert len(list(WeekRange(2020, 1, 2020, 53).weeks())) == weeks_in_year(2020)


def test_len_counts_the_weeks():
    assert len(WeekRange(2024, 3, 2024, 3)) == 1
    assert len(WeekRange(2024, 52, 2025, 2)) == 3
    assert len(WeekRange(2020, 1, 2020, 53)) == 53


# --- current_iso_week --------------------------------------------------------


def test_current_iso_week_with_fixed_today():
    assert current_iso_week(datetime.date(2025, 1, 1)) == (2025, 1)
    assert current_iso_week(datetime.date(2023, 1, 1)) == (2022, 52)


def test_current_iso_week_anchors_on_europe_oslo(monkeypatch):
    """Sunday 23:30 UTC is already Monday in Norway, so it is the next ISO week."""
    monkeypatch.setattr(weeks_module, "_now", lambda: datetime.datetime(2024, 6, 23, 23, 30, tzinfo=datetime.UTC))
    assert current_iso_week() == (2024, 26)


# --- last_n_weeks ------------------------------------------------------------


def test_last_n_weeks_ends_on_previous_week():
    """The current week is left out: it is still being reported."""
    assert last_n_weeks(3, datetime.date(2024, 1, 15)) == WeekRange(2023, 52, 2024, 2)


def test_last_n_weeks_single_week():
    assert last_n_weeks(1, datetime.date(2024, 1, 15)) == WeekRange(2024, 2, 2024, 2)


def test_last_n_weeks_spans_a_53_week_year():
    assert last_n_weeks(2, datetime.date(2021, 1, 4)) == WeekRange(2020, 52, 2020, 53)


def test_last_n_weeks_is_valid():
    last_n_weeks(4, datetime.date(2024, 1, 15)).validate()


def test_last_n_weeks_anchors_on_europe_oslo(monkeypatch):
    """The same instant, and the "previous week" is one later than a UTC clock would say."""
    monkeypatch.setattr(weeks_module, "_now", lambda: datetime.datetime(2024, 6, 23, 23, 30, tzinfo=datetime.UTC))
    assert last_n_weeks(1) == WeekRange(2024, 25, 2024, 25)


@pytest.mark.parametrize("n", [0, -1])
def test_last_n_weeks_rejects_non_positive_n(n):
    with pytest.raises(ValueError, match="must be >= 1"):
        last_n_weeks(n)
