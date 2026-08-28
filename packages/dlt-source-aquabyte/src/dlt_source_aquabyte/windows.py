"""The API caps how wide a window may be, so a resource splits its own requests.

Why, and what it means for a load: `REFERENCE.md#windows-are-split-to-fit-the-apis-cap`.
Where the numbers come from: `specs/README.md#api-quirks-worth-knowing`.
"""

import logging
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

Public and writable on purpose: a consumer can size chunks of its own from it, or correct a
cap that has moved without waiting for a release. `REFERENCE.md#windows-are-split-to-fit-the-apis-cap`.
"""

Window = tuple[Any, Any]
"""One request's window: the value to send as the start param, and the one for the end."""

DEFAULT_PERIOD = "D"
"""The `period` the API computes when none is sent."""

_FALLBACK_MAX_WINDOW_DAYS = 366
"""What an unrecognised resource gets: the cap every endpoint has at its default period."""


def windows_to_request(
    resource: str,
    start_param: str,
    incremental: dlt.sources.incremental[str] | None,
    params: dict[str, Any] | None,
    period: str | None = None,
) -> list[Window]:
    """The window of every request `resource` must make, oldest first.

    One window when the span fits the cap, several when it does not, and always with an
    end: `end_value` if the incremental carries one, otherwise now. A caller who sends a
    window param through `params` owns the window and gets it back unmeasured.
    """
    start = incremental.last_value if incremental is not None else None
    end = incremental.end_value if incremental is not None else None
    period = (params or {}).get("period", period)  # `params` wins here as it does on the wire
    if params and (start_param in params or start_param.replace("from", "to") in params):
        return [(start, end)]
    if start is None:
        # No cursor value at all. Whether that is fatal is the caller's check.
        return [(start, end)]
    if not isinstance(start, str) or not isinstance(end, str | None):
        return _unsplit_with_warning(resource, period, start, end, "they are not both strings")

    try:
        span_start = _as_date_or_time(start)
        span_end = _as_date_or_time(end) if end is not None else _today_or_now(span_start)
    except ValueError:
        return _unsplit_with_warning(resource, period, start, end, "one of them is not ISO 8601")
    cap = timedelta(days=_max_window_days(resource, period))
    end_text = end if end is not None else _written_like(span_end, start)

    try:
        fits = span_end - span_start <= cap
    except TypeError:
        return _unsplit_with_warning(resource, period, start, end, "they are different kinds of value")
    if fits:
        return [(start, end_text)]

    # The API measures a window end to end, so every sub-window may be a full `cap` wide.
    # `toDate` is inclusive though, so the next one starts a day later than it ends, or the
    # seam day is fetched twice. `toTime` is exclusive and needs no such gap.
    gap_between_windows = timedelta(0) if isinstance(span_start, datetime) else timedelta(days=1)
    edges = [span_start]
    while span_end - edges[-1] > cap:
        edges.append(edges[-1] + cap + gap_between_windows)

    starts = [start, *(_written_like(edge, start) for edge in edges[1:])]
    ends = [*(_written_like(edge - gap_between_windows, start) for edge in edges[1:]), end_text]
    return list(zip(starts, ends, strict=True))


def _unsplit_with_warning(resource: str, period: str | None, start: Any, end: Any, reason: str) -> list[Window]:
    """Send a window this cannot measure, and say so — the 400 it may cause explains nothing.

    dlt hides the API's `detail` unless `RUNTIME__HTTP_SHOW_ERROR_BODY` is set, so a refusal
    arrives as a bare `400 Client Error` with no way to tell an over-wide window from a bad
    parameter. `REFERENCE.md#logging`.
    """
    logger.warning(
        "%s: cannot measure the window %r to %r because %s, so it goes out as one request. "
        "The API refuses one wider than %s days.",
        resource,
        start,
        end,
        reason,
        _max_window_days(resource, period),
    )
    return [(start, end)]


def _max_window_days(resource: str, period: str | None) -> int:
    if (resource, period) in MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS[(resource, period)]
    return MAX_WINDOW_DAYS.get((resource, DEFAULT_PERIOD), _FALLBACK_MAX_WINDOW_DAYS)


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
