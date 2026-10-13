"""dlt source for Elhub's Energy Data API: metering points and their hourly metering values.

Endpoints, params and record shapes: https://api.elhub.no/energy-data-api/metering-points, with a
dated copy under `specs/`. Only `METERING_VALUES_HOUR_RESTRICTED` is read; it is the one dataset the
`elhub:enduser` scope answers.

Each resource takes its endpoint's params in snake_case, plus a `params` escape hatch merged into the
query string last. Bind them per resource or set them in config under `[sources.elhub.<resource>]`.
Dates are `YYYY-MM-DD` (midnight, Europe/Oslo) or ISO 8601 with an offset.
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
"""The attribute the dataset's values are nested under."""

ALL_RETAINED_HISTORY = "2000-01-01T00:00:00+01:00"
"""An `insertDateTime` older than anything Elhub holds. With a metering point id and no dates, the API
then answers with its widest window, 3 years and 41 days, which is everything it retains."""


def _query(extra: dict[str, Any] | None = None, **named: Any) -> dict[str, Any]:
    params = {key: value for key, value in named.items() if value is not None}
    if extra:
        params.update(extra)
    return params


def _items(client: RESTClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """The `data` of one call, as a list. An empty result is `204 No Content` with no body, not `[]`."""
    response = client.get(path, params={"dataset": DATASET, **params})
    if response.status_code == 204:
        return []
    data = response.json()["data"]
    return data if isinstance(data, list) else [data]


def _newest(cursor: str | None, values: list[dict[str, Any]]) -> str | None:
    """The latest `insertDateTime` of `values` and `cursor`, compared as instants: the strings carry the
    Oslo offset, which changes with daylight saving, so text order is not time order."""
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
    """Elhub Energy Data API dlt source. The two resources share one RESTClient and one token.

    Args:
        credentials: The Maskinporten client; from `[sources.elhub.credentials]` when not passed.
        consumer_org: Organisation number of a company that delegated `scope` to the client's
            organisation in Altinn. The source then reads that company's metering points. One
            source per company; they can share a pipeline, because a metering point id is unique.
        initial_insert_date_time: Where a metering point the source has not seen before starts:
            values inserted at or after this instant, ISO 8601 with offset. The default is all
            the history Elhub retains. `REFERENCE.md#the-cursor-is-per-metering-point`.
        scope: `elhub:enduser`, the scope this package is verified against.
        user_agent: Elhub answers 403 to a request without one. Set it to something that names you.
        headers: Sent on every request, after the two Elhub requires. The escape hatch for
            `X-Elhub-GLN` and `On-Behalf-Of` under another scope.
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
        """Every metering point the token reads, from `GET /metering-points`.

        The API has no list endpoint: this is the dataset call without an id, which returns every
        metering point with values in the window, the last 24 hours when no dates are sent. The
        values themselves are left to `metering_values_hour`, which reads each point with a cursor.
        `metering_point_ids` keeps only those points, and so limits what `metering_values_hour` reads.
        """
        wanted = set(metering_point_ids) if metering_point_ids is not None else None
        for item in _items(client, "/metering-points", _query(params, startDate=start_date, endDate=end_date)):
            if wanted is not None and item["id"] not in wanted:
                continue
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
        """Hourly (or quarter-hourly) values of one metering point, from `GET /metering-points/{id}`.

        One row per value, with the point's id as `meteringPointId`. The request asks for values
        inserted since the point's own cursor, which is how a first contact loads the whole history
        and a daily run loads yesterday plus any corrections. Bind `insert_date_time`, `start_date`
        or `end_date` and the request carries that instead: the stored cursor is neither read nor
        advanced, which is what a backfill wants. `REFERENCE.md#the-cursor-is-per-metering-point`.
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
        # dlt reports nothing for a point that returned nothing, so this is the one line that says so.
        logger.info("metering point %s: %d values since %s", point_id, len(values), since)
        yield values

    return metering_points, metering_values_hour
