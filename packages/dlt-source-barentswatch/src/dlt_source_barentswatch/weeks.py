"""ISO week arithmetic for the locality-week endpoint, which is addressed by year and week.

The API has no window parameters: one request is one locality in one ISO week, so a load
is a set of weeks the caller chooses. `WeekRange` names such a set, and the two helpers
below build the ranges a scheduled load and a backfill need.
"""

import datetime
import zoneinfo
from collections.abc import Iterator
from typing import NamedTuple

FIRST_YEAR = 2012
"""The first ISO year the API answers for. Verified live: 2011 is refused, 2012 week 1 is served."""

REPORTING_TIMEZONE = zoneinfo.ZoneInfo("Europe/Oslo")
"""Reports are filed in Norway, so "this week" is decided on the Norwegian date, not UTC."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _today() -> datetime.date:
    return _now().astimezone(REPORTING_TIMEZONE).date()


def weeks_in_year(year: int) -> int:
    """52 or 53. The 28th of December is always in the last ISO week of its year."""
    return datetime.date(year, 12, 28).isocalendar()[1]


def _validate_week(year: int, week: int) -> None:
    if year < FIRST_YEAR:
        raise ValueError(f"ISO year out of range: {year} (BarentsWatch fish health data starts at {FIRST_YEAR})")
    max_week = weeks_in_year(year)
    if not 1 <= week <= max_week:
        raise ValueError(f"ISO week out of range: {year}-W{week} (year {year} has weeks 1..{max_week})")


class WeekRange(NamedTuple):
    """An inclusive span of ISO weeks, from `(start_year, start_week)` to `(end_year, end_week)`."""

    start_year: int
    start_week: int
    end_year: int
    end_week: int

    def validate(self) -> None:
        """Raise `ValueError` if either end is not a real ISO week, or the range runs backwards."""
        _validate_week(self.start_year, self.start_week)
        _validate_week(self.end_year, self.end_week)
        if (self.start_year, self.start_week) > (self.end_year, self.end_week):
            raise ValueError(
                f"inverted week range: start {self.start_year}-W{self.start_week} "
                f"is after end {self.end_year}-W{self.end_week}"
            )

    def weeks(self) -> Iterator[tuple[int, int]]:
        """Every `(year, week)` in the range, oldest first, 53-week years included."""
        cur = datetime.date.fromisocalendar(self.start_year, self.start_week, 1)
        end = datetime.date.fromisocalendar(self.end_year, self.end_week, 1)
        while cur <= end:
            iso = cur.isocalendar()
            yield (iso.year, iso.week)
            cur += datetime.timedelta(weeks=1)

    @property
    def n_weeks(self) -> int:
        """How many weeks the range spans. Not `__len__`: a `WeekRange` is a 4-tuple, and it stays one."""
        return sum(1 for _ in self.weeks())


def current_iso_week(today: datetime.date | None = None) -> tuple[int, int]:
    """The ISO `(year, week)` of `today`, by default the current date in Norway."""
    iso = (today or _today()).isocalendar()
    return (iso.year, iso.week)


def last_n_weeks(n: int, today: datetime.date | None = None) -> WeekRange:
    """The `n` complete ISO weeks before the current one, as a `WeekRange`.

    The current week is left out because it is still being reported: the API is updated
    nightly from reports that arrive through the week. A load that wants the current week
    too builds the range itself with `current_iso_week()`.
    """
    if n < 1:
        raise ValueError(f"last_n_weeks: n must be >= 1, got {n}")
    end_date = (today or _today()) - datetime.timedelta(weeks=1)
    start_date = end_date - datetime.timedelta(weeks=n - 1)
    start_year, start_week, _ = start_date.isocalendar()
    end_year, end_week, _ = end_date.isocalendar()
    return WeekRange(start_year, start_week, end_year, end_week)
