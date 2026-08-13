import dlt
from dlt.sources.helpers.rest_client.auth import APIKeyAuth
from dlt.sources.helpers.rest_client.client import RESTClient
from dlt.sources.helpers.rest_client.paginators import JSONResponseCursorPaginator

from dlt_source_aquabyte.schemas import (
    BehaviorBreathingIndex,
    BehaviorSwimSpeed,
    BiomassDailyModel,
    BiomassHarvestReport,
    EnvironmentalDataLive,
    EnvironmentalDataPoint,
    LiceCount,
    Pen,
    Site,
    WelfareScoreDetail,
    WelfareScoreRow,
)


@dlt.resource(write_disposition="replace", columns=Site)
def site_by_id(
    site_id: str,
    base_url: str = dlt.config.value,
    api_key: str = dlt.secrets.value,
):
    """Load a single site by ID from GET /sites/{siteId}."""
    auth = APIKeyAuth(name="apikey", api_key=api_key, location="header")
    client = RESTClient(
        base_url=base_url,
        auth=auth,
        paginator=JSONResponseCursorPaginator(cursor_path="nextToken", cursor_param="nextToken"),
    )

    yield from client.paginate(f"/sites/{site_id}", data_selector="sites")


WELFARE_CATEGORIES = [
    "bodyWound",
    "scaleLoss",
    "snoutWound",
    "maturation",
    "eyeBleeding",
    "eyeClouding",
    "exophthalmos",
    "opercularDamage",
    "backDeformity",
    "pelvicFin",
    "pectoralFin",
    "caudalFin",
    "analFin",
    "dorsalFin",
    "upperJawDeformity",
    "lowerJawDeformity",
    "breathingMouth",
    "mechHeadWound",
]


def _unpivot_welfare_scores(record: dict) -> list[dict]:
    """Unpivot a single WelfareScoresRecord into flat rows (one per category with data)."""
    pen_id = record["penId"]
    date = record["date"]
    scores_detail = record.get("welfareScores", {})
    rows = []

    for category in WELFARE_CATEGORIES:
        detail_raw = scores_detail.get(category)
        if detail_raw is None:
            continue

        detail = WelfareScoreDetail(**detail_raw)
        row = {
            "penId": pen_id,
            "date": date,
            "category": category,
            "activeScore1": detail.active.score_1,
            "activeScore2": detail.active.score_2,
            "activeScore3": detail.active.score_3,
            "healedScore1": detail.healed.score_1 if detail.healed else None,
            "healedScore2": detail.healed.score_2 if detail.healed else None,
            "healedScore3": detail.healed.score_3 if detail.healed else None,
            "nothing": detail.nothing,
            "sampleSize": detail.sampleSize,
        }
        rows.append(row)

    return rows


@dlt.source
def aquabyte_source(
    pen_ids: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    environmental_period: str = dlt.config.value,
    behavior_period: str = dlt.config.value,
    initial_date: str = dlt.config.value,
    initial_time: str = dlt.config.value,
    base_url: str = dlt.config.value,
    api_key: str = dlt.secrets.value,
):
    """Aquabyte API v3 dlt source.

    Creates a single RESTClient shared by all resources.

    Args:
        pen_ids: List of pen IDs to fetch. None for auto-discovery.
        from_date: Manual start date (YYYY-MM-DD) for date-based endpoints.
        to_date: Manual end date (YYYY-MM-DD) for date-based endpoints.
        from_time: Manual start time (ISO 8601) for time-based endpoints.
        to_time: Manual end time (ISO 8601) for time-based endpoints.
        environmental_period: Aggregation period for environmental data ('15min', 'h', 'D').
        behavior_period: Aggregation period for behavior data ('h', 'D').
        initial_date: Start date for date-based incremental endpoints (YYYY-MM-DD).
        initial_time: Start time for time-based incremental endpoints (ISO 8601).
        base_url: API base URL from config.
        api_key: API key from secrets.
    """
    auth = APIKeyAuth(name="apikey", api_key=api_key, location="header")
    client = RESTClient(
        base_url=base_url,
        auth=auth,
        paginator=JSONResponseCursorPaginator(cursor_path="nextToken", cursor_param="nextToken"),
    )

    @dlt.resource(write_disposition="replace", columns=Site, max_table_nesting=0)
    def sites():
        """Load all sites from GET /sites."""
        yield from client.paginate("/sites", data_selector="sites")

    @dlt.transformer(data_from=sites, write_disposition="replace", columns=Pen)
    def pens(sites_page: list[dict]):
        """Extract pens from site data."""
        for site in sites_page:
            for pen in site.get("pens", []):
                if pen_ids is None or pen["id"] in pen_ids:
                    yield pen

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=EnvironmentalDataPoint,
    )
    def environmental(
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Load environmental data from GET /environmental?penId=all."""
        params: dict[str, str] = {"period": environmental_period}
        if from_time is not None:
            params["fromTime"] = from_time
        elif incremental_from_time.last_value is not None:
            params["fromTime"] = incremental_from_time.last_value
        if to_time is not None:
            params["toTime"] = to_time

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/environmental", params=params, data_selector="data"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/environmental", params=params, data_selector="data"):
                yield page

    @dlt.resource(write_disposition="replace", columns=EnvironmentalDataLive)
    def environmental_latest(pen_id: str = "all"):
        """Load latest environmental readings from GET /environmental/latest."""
        params: dict[str, str] = {"penId": pen_id}
        yield from client.paginate("/environmental/latest", params=params, data_selector="data")

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date"],
        columns=BiomassDailyModel,
    )
    def biomass(
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Load biomass data from GET /biomass?penId=all."""
        params: dict[str, str] = {}
        if from_date is not None:
            params["fromDate"] = from_date
        elif incremental_date.last_value is not None:
            params["fromDate"] = incremental_date.last_value
        else:
            params["fromDate"] = initial_date
        if to_date is not None:
            params["toDate"] = to_date

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/biomass", params=params, data_selector="biomass"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/biomass", params=params, data_selector="biomass"):
                yield page

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "slaughterStartDate"],
        columns=BiomassHarvestReport,
    )
    def harvest_report(
        incremental_slaughter_start_date: dlt.sources.incremental[str] = dlt.sources.incremental(
            "slaughterStartDate", initial_value=initial_date
        ),
    ):
        """Load harvest reports from GET /biomass/harvestReport?penId=all."""
        params: dict[str, str] = {}
        if from_date is not None:
            params["fromDate"] = from_date
        elif incremental_slaughter_start_date.last_value is not None:
            params["fromDate"] = incremental_slaughter_start_date.last_value
        if to_date is not None:
            params["toDate"] = to_date

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/biomass/harvestReport", params=params, data_selector="reports"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/biomass/harvestReport", params=params, data_selector="reports"):
                yield page

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date"],
        columns=LiceCount,
    )
    def lice_count(
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Load lice count data from GET /liceCount?penId=all."""
        params: dict[str, str] = {}
        if from_date is not None:
            params["fromDate"] = from_date
        elif incremental_date.last_value is not None:
            params["fromDate"] = incremental_date.last_value
        if to_date is not None:
            params["toDate"] = to_date

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/liceCount", params=params, data_selector="liceCount"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/liceCount", params=params, data_selector="liceCount"):
                yield page

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=BehaviorSwimSpeed,
    )
    def behaviour_swim_speed(
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Load swim speed data from GET /behaviour/swimSpeed?penId=all."""
        params: dict[str, str] = {"period": behavior_period}
        if from_time is not None:
            params["fromTime"] = from_time
        elif incremental_from_time.last_value is not None:
            params["fromTime"] = incremental_from_time.last_value
        if to_time is not None:
            params["toTime"] = to_time

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/behaviour/swimSpeed", params=params, data_selector="swimSpeed"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/behaviour/swimSpeed", params=params, data_selector="swimSpeed"):
                yield page

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "fromTime"],
        columns=BehaviorBreathingIndex,
    )
    def behaviour_breathing_index(
        incremental_from_time: dlt.sources.incremental[str] = dlt.sources.incremental(
            "fromTime", initial_value=initial_time
        ),
    ):
        """Load breathing index data from GET /behaviour/breathingIndex?penId=all."""
        params: dict[str, str] = {}
        if from_time is not None:
            params["fromTime"] = from_time
        elif incremental_from_time.last_value is not None:
            params["fromTime"] = incremental_from_time.last_value
        if to_time is not None:
            params["toTime"] = to_time

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/behaviour/breathingIndex", params=params, data_selector="breathingIndex"):
                    yield page
        else:
            params["penId"] = "all"
            for page in client.paginate("/behaviour/breathingIndex", params=params, data_selector="breathingIndex"):
                yield page

    @dlt.resource(
        write_disposition="merge",
        primary_key=["penId", "date", "category"],
        columns=WelfareScoreRow,
    )
    def welfare_scores(
        incremental_date: dlt.sources.incremental[str] = dlt.sources.incremental("date", initial_value=initial_date),
    ):
        """Load welfare scores from GET /welfareScores?penId=all.

        Unpivots nested welfare categories into flat rows (one per pen+date+category).
        """
        params: dict[str, str] = {}
        if from_date is not None:
            params["fromDate"] = from_date
        elif incremental_date.last_value is not None:
            params["fromDate"] = incremental_date.last_value
        if to_date is not None:
            params["toDate"] = to_date

        if pen_ids:
            for pid in pen_ids:
                params["penId"] = pid
                for page in client.paginate("/welfareScores", params=params, data_selector="welfareScores"):
                    unpivoted_rows: list[dict] = []
                    for record in page:
                        unpivoted_rows.extend(_unpivot_welfare_scores(record))
                    if unpivoted_rows:
                        yield unpivoted_rows
        else:
            params["penId"] = "all"
            for page in client.paginate("/welfareScores", params=params, data_selector="welfareScores"):
                unpivoted_rows_all: list[dict] = []
                for record in page:
                    unpivoted_rows_all.extend(_unpivot_welfare_scores(record))
                if unpivoted_rows_all:
                    yield unpivoted_rows_all

    return (
        sites,
        pens,
        environmental,
        environmental_latest,
        biomass,
        harvest_report,
        lice_count,
        behaviour_swim_speed,
        behaviour_breathing_index,
        welfare_scores,
    )
