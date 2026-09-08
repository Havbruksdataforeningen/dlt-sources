"""dlt source for the BarentsWatch Fish Health API.

Endpoints and record shapes: https://www.barentswatch.no/bwapi/openapi/fishhealth/openapi.json,
committed as `specs/openapi.json`. This package reads three of its endpoints: the list of
localities with a salmonoid licence, the detailed weekly report for one locality, and the
weekly summary of every locality matching a filter.

Both weekly endpoints are addressed by ISO year and ISO week, so each takes a `WeekRange`
and makes one request per week — per locality for the detailed report, per filter value for
the summary. The week arithmetic lives in `weeks.py`.
"""

import itertools
import logging
from collections.abc import Iterator
from typing import Any

import dlt
from dlt.sources.helpers.rest_client.auth import OAuth2ClientCredentials
from dlt.sources.helpers.rest_client.client import RESTClient

from dlt_source_barentswatch_fishhealth.weeks import WeekRange

logger = logging.getLogger(__name__)

BASE_URL = "https://www.barentswatch.no/bwapi/"
"""The one server `specs/openapi.json` lists."""

TOKEN_URL = "https://id.barentswatch.no/connect/token"  # noqa: S105 — a URL, not a secret
"""The client-credentials token endpoint from the spec's `securitySchemes`."""

SCOPE = "api"

LOCALITIES_PATH = "v1/geodata/fishhealth/localitieswithsalmonoids"
LOCALITY_WEEK_PATH = "v2/geodata/fishhealth/locality/{locality_no}/{year}/{week}"
LOCALITY_WEEK_SUMMARY_PATH = "v2/geodata/fishhealth/locality/{year}/{week}"
"""A POST, but a read: the filter travels as a JSON body because it is too rich for a query string."""

WEEK_KEY = ["localityNo", "year", "week"]
"""The merge key of both weekly tables, injected from the request rather than read from the body."""


@dlt.source(max_table_nesting=0)
def barentswatch_fishhealth_source(
    client_id: str = dlt.secrets.value,
    client_secret: str = dlt.secrets.value,
):
    """BarentsWatch Fish Health API dlt source. Both resources share one authenticated client.

    Args:
        client_id: OAuth2 client id, from secrets. Registered at https://www.barentswatch.no/minside/.
        client_secret: OAuth2 client secret, from secrets.
    """
    auth = OAuth2ClientCredentials(
        access_token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        access_token_request_data={"scope": SCOPE},
    )
    client = RESTClient(base_url=BASE_URL, auth=auth)

    @dlt.resource(write_disposition="replace")
    def locality(locality_nos: list[int] | None = None) -> Iterator[dict[str, Any]]:
        """Every locality with a salmonoid licence, from `GET /v1/geodata/fishhealth/localitieswithsalmonoids`.

        Bind `locality_nos` to keep a subset. The list is still fetched, so the rows keep the
        API's fields and a number that is not a salmonoid locality is reported rather than
        silently sent to the weekly endpoint, which answers 400 for it — the same 400 it
        gives a week with no data.
        """
        if locality_nos is not None and not locality_nos:
            raise ValueError("locality_nos is an empty list; pass None to load every salmonoid locality, or some.")
        response = client.get(LOCALITIES_PATH)
        response.raise_for_status()
        discovered = response.json()
        if not isinstance(discovered, list) or not all(
            isinstance(item, dict) and "localityNo" in item for item in discovered
        ):
            raise ValueError(f"{LOCALITIES_PATH}: expected a JSON array of objects with a localityNo.")
        if not discovered:
            raise ValueError(f"{LOCALITIES_PATH}: the API returned no localities; refusing a 0-row load.")
        if locality_nos is None:
            yield from discovered
            return
        wanted = set(locality_nos)
        selected = [item for item in discovered if item["localityNo"] in wanted]
        missing = wanted - {item["localityNo"] for item in selected}
        if missing:
            logger.warning("locality_nos not among the salmonoid localities, skipping: %s", sorted(missing))
        if not selected:
            raise ValueError("None of the requested locality_nos are salmonoid localities; refusing a 0-row load.")
        yield from selected

    @dlt.transformer(data_from=locality, write_disposition="merge", primary_key=WEEK_KEY)
    def locality_week(item: dict[str, Any], week_range: WeekRange | None = None) -> Iterator[dict[str, Any]]:
        """The detailed weekly report for one locality, from
        `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}`, once per week in `week_range`.

        Each record is the response body plus the three path values it was requested with —
        `localityNo`, `year` and `week` — which are the merge key. A week the API has no report
        for answers 400 and is skipped; every other non-200 raises.
        """
        if week_range is None:
            raise ValueError(
                "locality_week needs a week_range: bind one with "
                "source.locality_week.bind(week_range=last_n_weeks(4)) or a WeekRange of your own."
            )
        week_range.validate()
        locality_no = item["localityNo"]
        skipped = 0
        for year, week in week_range.weeks():
            response = client.get(LOCALITY_WEEK_PATH.format(locality_no=locality_no, year=year, week=week))
            if response.status_code == 400:
                # The API's answer for "no report": a week before the locality existed, after
                # the newest report, or a number it does not know. Not an error.
                logger.debug("Locality %s %s-W%s: HTTP 400, no report.", locality_no, year, week)
                skipped += 1
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Locality {locality_no} {year}-W{week}: the 200 response body is not a JSON object.")
            yield {**payload, "localityNo": locality_no, "year": year, "week": week}
        if skipped:
            logger.info(
                "Locality %s: no report for %s of %s weeks (HTTP 400).", locality_no, skipped, week_range.n_weeks
            )

    @dlt.resource(write_disposition="merge", primary_key=WEEK_KEY)
    def locality_week_summary(
        week_range: WeekRange | None = None,
        production_areas: list[int] | None = None,
        organizations: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """The weekly summary of every locality matching a filter, from
        `POST /v2/geodata/fishhealth/locality/{year}/{week}`, once per week in `week_range` and per filter value.

        A summary row carries the same `liceReport` as the detailed report, but `diseases` and
        `liceTreatments` as names only where the detailed report has full case and treatment
        records, and none of the register, zone or escape fields.
        The API takes one production area and one organization per request, so each list fans out
        into one request per value, and the two combine with AND: `production_areas=[7, 8]` with
        `organizations=["921668236"]` is that organization's localities in area 7, then in area 8.
        No filter at all is every locality in Norway for the week.

        `filters` is the escape hatch for the other body fields the spec lists under
        `LocalityReportQueryV2`, merged into the body last, so it wins over the named arguments.

        Each record is the response row plus `localityNo` (from `locality.no`), `year` and `week`,
        the merge key, and `productionArea` when the request was filtered by one — the row does not
        say which area it came from, and a comparison across areas needs to know.
        """
        if week_range is None:
            raise ValueError(
                "locality_week_summary needs a week_range: bind one with "
                "source.locality_week_summary.bind(week_range=last_n_weeks(4)) or a WeekRange of your own."
            )
        week_range.validate()
        if production_areas is not None and not production_areas:
            raise ValueError("production_areas is an empty list; pass None to leave the area unfiltered, or some.")
        if organizations is not None and not organizations:
            raise ValueError("organizations is an empty list; pass None to leave the organization unfiltered, or some.")
        bodies = [
            _summary_body(production_area, organization, filters)
            for production_area, organization in itertools.product(production_areas or [None], organizations or [None])
        ]
        for year, week in week_range.weeks():
            for body in bodies:
                response = client.post(LOCALITY_WEEK_SUMMARY_PATH.format(year=year, week=week), json=body)
                if response.status_code == 400:
                    logger.debug("Summary %s-W%s %s: HTTP 400, no report.", year, week, body)
                    continue
                response.raise_for_status()
                rows = response.json()
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    raise ValueError(f"Summary {year}-W{week}: the 200 response body is not a JSON array of objects.")
                for row in rows:
                    if not isinstance(row.get("locality"), dict) or "no" not in row["locality"]:
                        raise ValueError(f"Summary {year}-W{week}: a row has no locality.no to key on.")
                    tagged: dict[str, Any] = {**row, "localityNo": row["locality"]["no"], "year": year, "week": week}
                    if "productionArea" in body:
                        tagged["productionArea"] = body["productionArea"]
                    yield tagged

    return (locality, locality_week, locality_week_summary)


def _summary_body(
    production_area: int | None, organization: str | None, filters: dict[str, Any] | None
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if production_area is not None:
        body["productionArea"] = production_area
    if organization is not None:
        body["organization"] = organization
    if filters:
        body.update(filters)
    return body
