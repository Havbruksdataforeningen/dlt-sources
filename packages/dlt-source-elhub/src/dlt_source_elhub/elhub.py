"""dlt source for Elhub's Energy Data API: metering points and their hourly metering values.

Endpoints and params: `specs/`. Only `METERING_VALUES_HOUR_RESTRICTED` is read, the one dataset the
`elhub:enduser` scope answers. Each resource takes its endpoint's params in snake_case, plus a `params`
escape hatch merged into the query string last.
"""

import logging
import time
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

import dlt
from dlt.sources.helpers.requests import Client
from dlt.sources.helpers.rest_client.client import RESTClient
from requests import HTTPError, Response
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

from dlt_source_elhub.columns import METERING_POINT_COLUMNS, METERING_VALUES_HOUR_COLUMNS
from dlt_source_elhub.maskinporten import MaskinportenAuth, MaskinportenCredentials

logger = logging.getLogger(__name__)

DATASET = "METERING_VALUES_HOUR_RESTRICTED"
VALUES_KEY = "meteringValuesHour"

OSLO = ZoneInfo("Europe/Oslo")
"""How the API reads a date without an offset."""

ALL_RETAINED_HISTORY = "2000-01-01T00:00:00+01:00"
"""An `insertDateTime` older than anything Elhub holds: with an id and no dates, the API then answers
with everything it retains, 3 years and 41 days."""


RETRIED = frozenset({429, *range(500, 600)})
UNANSWERED = (ConnectionError, Timeout, ChunkedEncodingError)


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _items(
    client: RESTClient, path: str, params: dict[str, Any], max_attempts: int, max_retry_delay: float
) -> list[dict[str, Any]]:
    """An empty result is `204 No Content` with no body, not `[]`."""
    response = _get(client, path, {"dataset": DATASET, **params}, max_attempts, max_retry_delay)
    if response.status_code == 204:
        return []
    if not response.ok:
        raise HTTPError(f"{response.status_code} {response.reason} from Elhub: {response.text}", response=response)
    data = response.json()["data"]
    return data if isinstance(data, list) else [data]


def _get(client: RESTClient, path: str, params: dict[str, Any], max_attempts: int, max_retry_delay: float) -> Response:
    """A `429`, a `5xx` or no answer is asked anew, not re-sent, so each attempt carries a token renewed
    when due: Elhub's rate limit, or a request left hanging, can outlast one (specs/README.md). A `401` is
    asked once more with a new token: one prepared before a laptop slept arrives expired."""
    renewed = False
    for attempt in range(1, max_attempts):
        try:
            response = client.get(path, params=params)
        except UNANSWERED as error:
            logger.warning("Elhub did not answer (%s), asking again shortly", type(error).__name__)
        else:
            if response.status_code == 401 and not renewed and isinstance(client.auth, MaskinportenAuth):
                logger.warning("Elhub refused the token (401), asking again with a new one")
                client.auth.renew()
                renewed = True
                continue
            if response.status_code not in RETRIED:
                return response
            if response.status_code == 429:
                logger.warning("Elhub rate limit: 429, asking again shortly")
            else:
                logger.warning("Elhub answered %d, asking again shortly", response.status_code)
        time.sleep(min(2 ** (attempt - 1), max_retry_delay))
    return client.get(path, params=params)


def _instant(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=OSLO)


def _days(start_date: str | None, end_date: str | None) -> Iterator[tuple[str | None, str | None]]:
    """The list call takes at most one day, so a wider window is walked a day at a time.

    A step is a calendar day in Europe/Oslo, so a boundary stays at midnight across daylight saving.
    """
    if start_date is None or end_date is None:
        yield start_date, end_date
        return
    day, end = _instant(start_date).astimezone(OSLO), _instant(end_date)
    if day + timedelta(days=1) >= end:
        yield start_date, end_date
        return
    as_dates = "T" not in start_date and "T" not in end_date
    while day < end:
        following = min(day + timedelta(days=1), end)
        if as_dates:
            yield day.date().isoformat(), following.date().isoformat()
        else:
            yield day.isoformat(), following.isoformat()
        day = following


def _newest(cursor: str | None, values: list[dict[str, Any]]) -> str | None:
    """Compared as instants: the Oslo offset changes with daylight saving, so text order is not time order."""
    candidates = [cursor, *(value["insertDateTime"] for value in values)]
    known = [text for text in candidates if text is not None]
    return max(known, key=datetime.fromisoformat) if known else None


@dlt.source(max_table_nesting=0)
def elhub_source(
    credentials: MaskinportenCredentials = dlt.secrets.value,
    consumer_org: str | None = None,
    initial_insert_date_time: str = ALL_RETAINED_HISTORY,
    base_url: str = "https://api.elhub.no/energy-data/v0/",
    scope: str = "elhub:enduser",
    user_agent: str = "dlt-source-elhub",
    headers: dict[str, str] | None = None,
    request_max_attempts: int = 15,
    request_max_retry_delay: float = 30,
):
    """Elhub Energy Data API dlt source; the two resources share one client and one token.

    Args:
        credentials: The Maskinporten client, from `[sources.elhub.credentials]` when not passed.
        consumer_org: Organisation number of a company that delegated `scope` to the client's
            organisation; the source then reads that company. One source per company.
        initial_insert_date_time: Where an unseen metering point starts: values inserted at or
            after this instant. Default: everything Elhub retains.
        user_agent: Elhub answers 403 without one. Name yourself.
        headers: Added to every request, e.g. `X-Elhub-GLN` and `On-Behalf-Of` under another scope.
        request_max_attempts: Attempts per request before a `429`, a `5xx` or no answer is raised.
        request_max_retry_delay: Longest pause between attempts, in seconds; they start at one
            second and double. The defaults outlast Elhub's rate limit as measured in
            specs/README.md; change them if Elhub changes it.
    """
    client = RESTClient(
        base_url=base_url,
        headers={"Accept": "application/json", "User-Agent": user_agent, **(headers or {})},
        auth=MaskinportenAuth(credentials, scope, consumer_org),
        # dlt's own retry re-sends the prepared request, expired token and all: retrying is left to `_get`.
        session=Client(raise_for_status=False, status_codes=(), exceptions=()).session,
    )
    items = partial(_items, client, max_attempts=request_max_attempts, max_retry_delay=request_max_retry_delay)

    @dlt.resource(write_disposition="merge", primary_key="id", columns=METERING_POINT_COLUMNS)
    def metering_points(
        metering_point_ids: Sequence[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """Every metering point the token reads, from `GET /metering-points`.

        The API has no list endpoint: this is the dataset call without an id, which returns every
        point with values in the window (the last 24 hours by default). A window wider than a day
        lists each day in it, so a point the end user had then and has since lost is found too.
        The values are left to `metering_values_hour`; `metering_point_ids` limits both.
        """
        wanted = set(metering_point_ids) if metering_point_ids is not None else None
        seen: set[str] = set()
        for day_start, day_end in _days(start_date, end_date):
            for item in items("/metering-points", _query(params, startDate=day_start, endDate=day_end)):
                if item["id"] in seen or (wanted is not None and item["id"] not in wanted):
                    continue
                seen.add(item["id"])
                attributes = {key: value for key, value in item.get("attributes", {}).items() if key != VALUES_KEY}
                record = {key: value for key, value in item.items() if key != "attributes"}
                yield {**record, "attributes": attributes} if attributes else record

    @dlt.transformer(
        data_from=metering_points,
        write_disposition="merge",
        primary_key=["meteringPointId", "startTime", "direction"],
        columns=METERING_VALUES_HOUR_COLUMNS,
    )
    def metering_values_hour(
        metering_point: dict[str, Any],
        start_date: str | None = None,
        end_date: str | None = None,
        insert_date_time: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """One row per value of one metering point, from `GET /metering-points/{id}`.

        Asks for values inserted since the point's own cursor: a first contact loads the whole
        history, a daily run yesterday plus corrections. A bound `insert_date_time`, `start_date`
        or `end_date` is sent instead, and the cursor is neither read nor advanced.
        """
        point_id = metering_point["id"]
        caller_owns_window = any(value is not None for value in (insert_date_time, start_date, end_date))
        cursors: dict[str, str] = dlt.current.resource_state().setdefault("insert_date_time", {})
        since = insert_date_time if caller_owns_window else cursors.get(point_id, initial_insert_date_time)

        query = _query(params, insertDateTime=since, startDate=start_date, endDate=end_date)
        values = [
            {"meteringPointId": item["id"], **value}
            for item in items(f"/metering-points/{point_id}", query)
            for value in item.get("attributes", {}).get(VALUES_KEY, [])
        ]
        if not caller_owns_window:
            newest = _newest(cursors.get(point_id), values)
            if newest is not None:
                cursors[point_id] = newest
        # dlt says nothing about a point that returned nothing.
        logger.info("metering point %s: %d values since %s", point_id, len(values), since)
        yield values

    return metering_points, metering_values_hour
