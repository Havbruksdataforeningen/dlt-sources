"""dlt source for the BarentsWatch Fish Health API.

Four of the endpoints in https://www.barentswatch.no/bwapi/openapi/fishhealth/openapi.json,
committed as `specs/openapi.json`. Resources are named after their endpoints and yield the
response bodies as they arrive; the two weekly endpoints are addressed by ISO year and week,
so those resources take a `WeekRange` from `weeks.py` and make one request per week.
"""

import logging
from collections.abc import Iterator
from typing import Any

import dlt
from dlt.sources.helpers.rest_client.auth import OAuth2ClientCredentials
from dlt.sources.helpers.rest_client.client import RESTClient

from dlt_source_barentswatch_fishhealth.weeks import WeekRange

logger = logging.getLogger(__name__)

BASE_URL = "https://www.barentswatch.no/bwapi/"
TOKEN_URL = "https://id.barentswatch.no/connect/token"  # noqa: S105 — a URL, not a secret
SCOPE = "api"

LOCALITIES_PATH = "v1/geodata/fishhealth/localities"
LOCALITIES_WITH_SALMONOIDS_PATH = "v1/geodata/fishhealth/localitieswithsalmonoids"
LOCALITY_WEEK_PATH = "v2/geodata/fishhealth/locality/{locality_no}/{year}/{week}"
LOCALITY_WEEK_SUMMARY_PATH = "v2/geodata/fishhealth/locality/{year}/{week}"

WEEK_KEY = ["localityNo", "year", "week"]
"""The merge key of both weekly tables: the request's own values, since neither response repeats them."""


@dlt.source(max_table_nesting=0)
def barentswatch_fishhealth_source(
    client_id: str = dlt.secrets.value,
    client_secret: str = dlt.secrets.value,
):
    """BarentsWatch Fish Health API dlt source. All resources share one authenticated client."""
    auth = OAuth2ClientCredentials(
        access_token_url=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        access_token_request_data={"scope": SCOPE},
    )
    client = RESTClient(base_url=BASE_URL, auth=auth)

    def get_list(path: str) -> list[dict[str, Any]]:
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    @dlt.resource(write_disposition="replace")
    def localities() -> Iterator[dict[str, Any]]:
        """`GET /v1/geodata/fishhealth/localities`."""
        yield from get_list(LOCALITIES_PATH)

    @dlt.resource(write_disposition="replace")
    def localities_with_salmonoids() -> Iterator[dict[str, Any]]:
        """`GET /v1/geodata/fishhealth/localitieswithsalmonoids`. What `locality_week` iterates over."""
        yield from get_list(LOCALITIES_WITH_SALMONOIDS_PATH)

    @dlt.transformer(data_from=localities_with_salmonoids, write_disposition="merge", primary_key=WEEK_KEY)
    def locality_week(item: dict[str, Any], week_range: WeekRange | None = None) -> Iterator[dict[str, Any]]:
        """`GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}`, once per locality and week.

        A 400 is the API's answer for a week it has no report for, and is skipped.
        """
        if week_range is None:
            raise ValueError("locality_week needs a week_range: bind one with .bind(week_range=...)")
        week_range.validate()
        locality_no = item["localityNo"]
        for year, week in week_range.weeks():
            response = client.get(LOCALITY_WEEK_PATH.format(locality_no=locality_no, year=year, week=week))
            if response.status_code == 400:
                logger.debug("Locality %s %s-W%s: HTTP 400, no report.", locality_no, year, week)
                continue
            response.raise_for_status()
            yield {**response.json(), "localityNo": locality_no, "year": year, "week": week}

    @dlt.resource(write_disposition="merge", primary_key=WEEK_KEY)
    def locality_week_summary(
        week_range: WeekRange | None = None, body: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """`POST /v2/geodata/fishhealth/locality/{year}/{week}`, once per week — a read whose filter is the body.

        `body` is the spec's `LocalityReportQueryV2`, sent as given; `None` is every locality.
        A 400 is skipped as above.
        """
        if week_range is None:
            raise ValueError("locality_week_summary needs a week_range: bind one with .bind(week_range=...)")
        week_range.validate()
        for year, week in week_range.weeks():
            response = client.post(LOCALITY_WEEK_SUMMARY_PATH.format(year=year, week=week), json=body or {})
            if response.status_code == 400:
                logger.debug("Summary %s-W%s: HTTP 400, no report.", year, week)
                continue
            response.raise_for_status()
            for row in response.json():
                yield {**row, "localityNo": row["locality"]["no"], "year": year, "week": week}

    return (localities, localities_with_salmonoids, locality_week, locality_week_summary)
