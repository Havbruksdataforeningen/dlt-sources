"""The API caps how wide a window may be, so a resource splits its own requests.

Why, and what it means for a load: `REFERENCE.md#windows-are-split-to-fit-the-window-cap`.
Where the numbers come from: `specs/README.md#api-quirks-worth-knowing`.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import dlt

logger = logging.getLogger(__name__)

MAX_WINDOW_DAYS: dict[tuple[str, str | None], int] = {
    ("environmental", "15min"): 7,
    ("environmental", "h"): 31,
    ("environmental", "D"): 366,
    ("behaviour_swim_speed", "h"): 31,
    ("behaviour_swim_speed", "D"): 366,
    ("behaviour_breathing_index", "D"): 366,
    ("biomass", None): 366,
    ("lice_count", None): 366,
    ("welfare_scores", None): 366,
    ("harvest_report", None): 366,
}
"""Widest window per `(resource, period)`, in days.

Writable on purpose: a window cap that has moved can be corrected without waiting for a
release, and `max_window_days` reads the correction. Read a window cap through that rather than
from here — a `period` this is not keyed on still has one.
`REFERENCE.md#windows-are-split-to-fit-the-window-cap`.
"""

Window = tuple[Any, Any]
"""One request's window: the value to send as the start param, and the one for the end."""


@dataclass(frozen=True)
class WindowParams:
    """The query params that carry a window, and the config key its cursor starts from."""

    start: str
    end: str
    config_key: str


DATE_PARAMS = WindowParams("fromDate", "toDate", "initial_date")
TIME_PARAMS = WindowParams("fromTime", "toTime", "initial_time")

DEFAULT_PERIOD = "D"
"""The `period` the API computes when none is sent."""

_WINDOWLESS_RESOURCES = frozenset({"sites", "environmental_latest"})
"""Resources the source loads whole: no cursor, so no window and no window cap.

Kept next to the table so `max_window_days` can tell a resource with no window from a name the
source does not load. `tests/test_window_splitting.py` pins both sets to the source's resources.
"""

_FALLBACK_MAX_WINDOW_DAYS = 366
"""What a resource with no window cap of its own gets: the one every endpoint has at its default period."""


def max_window_days(resource: str, period: str | None = None) -> int:
    """The widest window `resource` accepts at `period`, in days — the width the source splits at.

    A `period` with no window cap of its own gets the one the API's default period carries, since
    that is the period the API computes when a request sends none. A resource with no window,
    `sites` or `environmental_latest`, takes none at all, so it answers the widest value quietly:
    a number that must not narrow a chunk size, not a cap the resource has. A resource this does
    not load gets the same answer and a warning, a name it has never seen
    being likelier a typo than a new endpoint. `REFERENCE.md#windows-are-split-to-fit-the-window-cap`.
    """
    if (resource, period) in MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS[(resource, period)]
    is_loaded = resource in _WINDOWLESS_RESOURCES or any(known == resource for known, _ in MAX_WINDOW_DAYS)
    if not is_loaded:
        logger.warning(
            "%r is not a resource this package loads, so its window cap is the widest one, %s days. "
            "Check the spelling: too wide a window is refused as a bare 400 that explains nothing.",
            resource,
            _FALLBACK_MAX_WINDOW_DAYS,
        )
    return MAX_WINDOW_DAYS.get((resource, DEFAULT_PERIOD), _FALLBACK_MAX_WINDOW_DAYS)


def windows_to_request(
    resource: str,
    window_params: WindowParams,
    incremental: dlt.sources.incremental[str] | None,
    params: dict[str, Any] | None,
    period: str | None = None,
) -> list[Window]:
    """The window of every request `resource` must make, oldest first.

    One window when the timespan fits the window cap, several when it does not, and always with an
    end: `end_value` if the incremental carries one, otherwise now. A caller who sends a
    window param through `params` owns the window and gets it back unmeasured.
    """
    start = incremental.last_value if incremental is not None else None
    end = incremental.end_value if incremental is not None else None
    caller_owns_window = bool(params) and (window_params.start in params or window_params.end in params)
    if start is None or caller_owns_window:
        return [(start, end)]

    period = (params or {}).get("period", period)  # `params` wins here as it does on the wire
    window_cap_days = max_window_days(resource, period)
    try:
        return _split(start, end, timedelta(days=window_cap_days))
    except _UnmeasurableWindow as why:
        # dlt hides the API's `detail` by default, so the refusal this may cause arrives as a
        # bare `400 Client Error` that explains nothing. `REFERENCE.md#logging`.
        logger.warning(
            "%s: cannot measure the window %r to %r because %s, so it goes out as one request. "
            "The API refuses one wider than the %s-day window cap.",
            resource,
            start,
            end,
            why,
            window_cap_days,
        )
        return [(start, end)]


class _UnmeasurableWindow(Exception):
    """The start and end cannot be subtracted; the message says why."""


def _split(start: Any, end: Any, window_cap: timedelta) -> list[Window]:
    if not isinstance(start, str) or not isinstance(end, str | None):
        raise _UnmeasurableWindow("they are not both strings")
    try:
        span_start = _as_date_or_time(start)
        span_end = _as_date_or_time(end) if end is not None else _today_or_now(span_start)
        width = span_end - span_start
    except ValueError:
        raise _UnmeasurableWindow("one of them is not ISO 8601") from None
    except TypeError:
        raise _UnmeasurableWindow("they are different kinds of value") from None

    end_text = end if end is not None else _written_like(span_end, start)
    if width <= window_cap:
        return [(start, end_text)]

    # The API measures a window end to end, so every sub-window may be a full `window_cap` wide.
    # `toDate` is inclusive though, so the next one starts a day later than it ends, or the
    # seam day is fetched twice. `toTime` is exclusive and needs no such gap.
    gap_between_windows = timedelta(0) if isinstance(span_start, datetime) else timedelta(days=1)
    edges = [span_start]
    while span_end - edges[-1] > window_cap:
        edges.append(edges[-1] + window_cap + gap_between_windows)

    starts = [start, *(_written_like(edge, start) for edge in edges[1:])]
    ends = [*(_written_like(edge - gap_between_windows, start) for edge in edges[1:]), end_text]
    return list(zip(starts, ends, strict=True))


def _as_date_or_time(cursor: str) -> date:
    has_time = "T" in cursor or " " in cursor
    return datetime.fromisoformat(cursor) if has_time else date.fromisoformat(cursor)


def _today_or_now(cursor: date) -> date:
    """Now, shaped like `cursor`. A cursor with no zone is treated as UTC, as the API means it."""
    now = datetime.now(tz=UTC).replace(microsecond=0)
    if not isinstance(cursor, datetime):
        return now.date()
    return now if cursor.tzinfo is not None else now.replace(tzinfo=None)


def _written_like(value: date, cursor: str) -> str:
    """Keeps the cursor's spelling, so one load does not mix two."""
    text = value.isoformat(sep=" ") if isinstance(value, datetime) and " " in cursor else value.isoformat()
    return text.replace("+00:00", "Z") if cursor.endswith("Z") else text
