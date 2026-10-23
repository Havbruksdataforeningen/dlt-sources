"""dlt source for Elhub's Energy Data API: metering points and their hourly metering values.

Endpoints and params: `specs/`. Only `METERING_VALUES_HOUR_RESTRICTED` is read, the one dataset the
`elhub:enduser` scope answers. Each resource takes its endpoint's params in snake_case, plus a `params`
escape hatch merged into the query string last.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import dlt
from dlt.sources.helpers.rest_client.client import RESTClient

from dlt_source_elhub.columns import METERING_POINT_COLUMNS, METERING_VALUES_HOUR_COLUMNS
from dlt_source_elhub.maskinporten import MaskinportenAuth, MaskinportenCredentials

logger = logging.getLogger(__name__)

DATASET = "METERING_VALUES_HOUR_RESTRICTED"
VALUES_KEY = "meteringValuesHour"

ALL_RETAINED_HISTORY = "2000-01-01T00:00:00+01:00"
"""An `insertDateTime` older than anything Elhub holds: with an id and no dates, the API then answers
with everything it retains, 3 years and 41 days."""


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _items(client: RESTClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """An empty result is `204 No Content` with no body, not `[]`."""
    response = client.get(path, params={"dataset": DATASET, **params})
    if response.status_code == 204:
        return []
    data = response.json()["data"]
    return data if isinstance(data, list) else [data]


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
    """
    client = RESTClient(
        base_url=base_url,
        headers={"Accept": "application/json", "User-Agent": user_agent, **(headers or {})},
        auth=MaskinportenAuth(credentials, scope, consumer_org),
    )

    @dlt.resource(write_disposition="merge", primary_key="id", columns=METERING_POINT_COLUMNS)
    def metering_points(
        metering_point_ids: Sequence[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """Every metering point the token reads: the ones `GET /metering-points` lists, and the ones it
        listed for this `consumer_org` on an earlier run.

        The API has no list endpoint: this is the dataset call without an id, which returns every
        point with values in the window (the last 24 hours by default). A point whose values are late
        or missing drops out of it, so each listed point is remembered in the resource state under its
        `consumer_org`, and yielded on later runs whether listed or not. The values are left to
        `metering_values_hour`; `metering_point_ids` limits both.
        """
        wanted = set(metering_point_ids) if metering_point_ids is not None else None
        owners: dict[str, str | None] = dlt.current.resource_state().setdefault("consumer_org", {})
        listed: set[str] = set()
        for item in _items(client, "/metering-points", _query(params, startDate=start_date, endDate=end_date)):
            listed.add(item["id"])
            owners[item["id"]] = consumer_org
            if wanted is not None and item["id"] not in wanted:
                continue
            attributes = {key: value for key, value in item.get("attributes", {}).items() if key != VALUES_KEY}
            record = {key: value for key, value in item.items() if key != "attributes"}
            yield {**record, "attributes": attributes} if attributes else record
        for point_id, owner in owners.items():
            if owner != consumer_org or point_id in listed or (wanted is not None and point_id not in wanted):
                continue
            logger.info("metering point %s: not listed, asked anyway", point_id)
            yield {"type": "metering-points", "id": point_id}

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
            for item in _items(client, f"/metering-points/{point_id}", query)
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
