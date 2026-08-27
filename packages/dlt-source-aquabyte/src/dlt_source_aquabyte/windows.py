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

DEFAULT_PERIOD = "D"
"""The grain the API computes when `period` is omitted."""

_WIDEST_CAP_DAYS = 366
"""What an unrecognised resource gets: the cap every endpoint has at its default grain."""


def windows(
    resource: str,
    start_param: str,
    incremental: dlt.sources.incremental[str] | None,
    extra: dict[str, Any] | None,
    period: str | None = None,
) -> list[tuple[Any, Any]]:
    """The window of every request `resource` must make, oldest first.

    One window when the span fits the cap, several when it does not, and always with an
    end: `end_value` if the incremental carries one, otherwise now. A caller who sends a
    window param through `params` owns the window and gets it back unmeasured.
    """
    start = incremental.last_value if incremental is not None else None
    end = incremental.end_value if incremental is not None else None
    grain = (extra or {}).get("period", period)  # `params` wins here as it does on the wire
    if extra and (start_param in extra or start_param.replace("from", "to") in extra):
        return [(start, end)]
    if start is None:
        # No cursor value at all. Whether that is fatal is the caller's check.
        return [(start, end)]
    if not isinstance(start, str) or not isinstance(end, str | None):
        return _unmeasured(resource, grain, start, end, "they are not both strings")

    first = _parse(start)
    last = _parse(end) if end is not None else _now_like(first)
    step = timedelta(days=_cap_days(resource, grain))
    end_text = end if end is not None else _spell(last, start)

    try:
        fits = last - first <= step
    except TypeError:
        return _unmeasured(resource, grain, start, end, "they are different kinds of value")
    if fits:
        return [(start, end_text)]

    # The API measures a window end to end, so every sub-window may be a full `step` wide.
    # `toDate` is inclusive though, so the next one starts a day later than it ends, or the
    # seam day is fetched twice. `toTime` is exclusive and needs no such gap.
    trim = timedelta(0) if isinstance(first, datetime) else timedelta(days=1)
    edges = [first]
    while last - edges[-1] > step:
        edges.append(edges[-1] + step + trim)

    starts = [start, *(_spell(edge, start) for edge in edges[1:])]
    ends = [*(_spell(edge - trim, start) for edge in edges[1:]), end_text]
    return list(zip(starts, ends, strict=True))


def _unmeasured(resource: str, grain: str | None, start: Any, end: Any, why: str) -> list[tuple[Any, Any]]:
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
        why,
        _cap_days(resource, grain),
    )
    return [(start, end)]


def _cap_days(resource: str, period: str | None) -> int:
    """The cap for one resource at one grain; an unknown grain resolves to the default one."""
    if (resource, period) in MAX_WINDOW_DAYS:
        return MAX_WINDOW_DAYS[(resource, period)]
    return MAX_WINDOW_DAYS.get((resource, DEFAULT_PERIOD), _WIDEST_CAP_DAYS)


def _parse(value: str) -> date:
    """A cursor value as the kind of point it is: a date, or a datetime for the time resources."""
    has_time = "T" in value or " " in value
    return datetime.fromisoformat(value) if has_time else date.fromisoformat(value)


def _now_like(sample: date) -> date:
    """Now, shaped like `sample`. A cursor with no zone is treated as UTC, as the API means it."""
    now = datetime.now(tz=UTC).replace(microsecond=0)
    if not isinstance(sample, datetime):
        return now.date()
    return now if sample.tzinfo is not None else now.replace(tzinfo=None)


def _spell(value: date, sample: str) -> str:
    """`value`, written the way `sample` writes it — `Z` rather than `+00:00` where it uses one."""
    text = value.isoformat()
    return text.replace("+00:00", "Z") if sample.endswith("Z") else text
