"""Behaviour every data resource shares, asserted once per endpoint.

These are the mechanics the source promises for all of them — the pen, the window params
the incremental drives, the envelope key, the paginator, and the optional params. How a
window too wide for the API becomes several requests is in `test_window_splitting.py`.
Behaviour peculiar to one resource lives in that resource's own test module.
"""

from dataclasses import dataclass
from typing import Any

import dlt
import pytest
from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_WINDOW,
    SOURCE_CONFIG,
    TIME_WINDOW,
    assert_pen_ids,
    assert_row_count,
    calls_to,
    load_mock,
    params_sent,
    resource_signature,
    run_source,
    serve,
)


@dataclass(frozen=True)
class Endpoint:
    """A data resource and the endpoint it reads."""

    resource: str
    path: str
    mock_file: str
    selector: str
    """The API's envelope key, which is also dlt's `data_selector`."""
    window_param: str
    optional_param: tuple[str, str, Any] | None = None
    """(resource argument, the query param it becomes, a value to send)."""
    single_page: bool = False

    @property
    def records(self) -> list[dict]:
        return load_mock(self.mock_file)[self.selector]

    @property
    def window(self) -> tuple[str, str]:
        """A backfill window, as the `initial_value` and `end_value` to bind."""
        return DATE_WINDOW if self.window_param == "fromDate" else TIME_WINDOW

    @property
    def end_param(self) -> str:
        return self.window_param.replace("from", "to")

    @property
    def config_key(self) -> str:
        return "initial_date" if self.window_param == "fromDate" else "initial_time"

    @property
    def configured_start(self) -> str:
        return SOURCE_CONFIG[self.config_key]

    @property
    def incremental_argument(self) -> str:
        """The `incremental_*` argument a window is bound on, named after the cursor field."""
        signature = resource_signature(aquabyte_source(**SOURCE_CONFIG), self.resource)
        return next(name for name in signature.parameters if name.startswith("incremental_"))


ENDPOINTS = [
    Endpoint(
        "environmental",
        "/environmental",
        "environmental.json",
        "data",
        "fromTime",
        optional_param=("period", "period", "15min"),
    ),
    Endpoint(
        "biomass",
        "/biomass",
        "biomass.json",
        "biomass",
        "fromDate",
        optional_param=("bucket_size", "bucketSize", 500),
    ),
    Endpoint(
        "harvest_report",
        "/biomass/harvestReport",
        "harvest_report.json",
        "reports",
        "fromDate",
        single_page=True,
    ),
    Endpoint("lice_count", "/liceCount", "lice_count.json", "liceCount", "fromDate"),
    Endpoint(
        "behaviour_swim_speed",
        "/behaviour/swimSpeed",
        "swim_speed.json",
        "swimSpeed",
        "fromTime",
        optional_param=("period", "period", "h"),
    ),
    Endpoint(
        "behaviour_breathing_index", "/behaviour/breathingIndex", "breathing_index.json", "breathingIndex", "fromTime"
    ),
    Endpoint("welfare_scores", "/welfareScores", "welfare_scores.json", "welfareScores", "fromDate"),
]

WITH_OPTIONAL = [endpoint for endpoint in ENDPOINTS if endpoint.optional_param]


def _run(mock_rest_client, endpoint: Endpoint, name: str, **bound: Any):
    """Serve the endpoint's mock and run its resource, returning (pipeline, load_info)."""
    mock_rest_client.paginate.reset_mock()
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})
    source = aquabyte_source(**SOURCE_CONFIG)
    if bound:
        source.resources[endpoint.resource].bind(**bound)
    return run_source(f"{name}_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_loads_the_records_of_the_pen_it_was_bound_to(mock_rest_client, endpoint):
    """One pen bound: that pen's records land, read from the endpoint's own envelope key."""
    pipeline, load_info = _run(mock_rest_client, endpoint, "test_load", pen_id="pen-001")

    assert load_info is not None
    assert_row_count(pipeline, endpoint.resource, len(endpoint.records))
    assert_pen_ids(pipeline, endpoint.resource, ["pen-001"])

    for call in calls_to(mock_rest_client, endpoint.path):
        assert call["data_selector"] == endpoint.selector
        # Only a single-page endpoint names a paginator; the rest take the client's own.
        assert isinstance(call.get("paginator"), SinglePagePaginator) is endpoint.single_page


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_defaults_to_every_pen(mock_rest_client, endpoint):
    """`penId=all` is the default: every request covers every pen, never one request per pen.

    A run makes one request per window rather than exactly one — see
    `test_window_splitting.py` — but the pen is not what decides how many.
    """
    pipeline, load_info = _run(mock_rest_client, endpoint, "test_all_pens")

    assert load_info is not None
    assert_row_count(pipeline, endpoint.resource, len(endpoint.records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, endpoint.resource, ACTIVE_PEN_IDS)
    assert {sent["penId"] for sent in params_sent(mock_rest_client, endpoint.path)} == {"all"}


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_always_sends_a_window_start(mock_rest_client, endpoint):
    """Nothing bound: the cursor's initial value is still sent, never an open window."""
    _, load_info = _run(mock_rest_client, endpoint, "test_window")

    assert load_info is not None
    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.window_param] == endpoint.configured_start


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_requests_the_window_a_backfill_incremental_carries(mock_rest_client, endpoint):
    """A bound backfill incremental drives both window params — start from its
    `initial_value`, end from its `end_value` — so the API is asked for exactly the
    rows dlt will keep."""
    start, end = endpoint.window
    window = dlt.sources.incremental(initial_value=start, end_value=end)
    _, load_info = _run(mock_rest_client, endpoint, "test_backfill", **{endpoint.incremental_argument: window})

    assert load_info is not None
    sent = params_sent(mock_rest_client, endpoint.path)[0]
    assert sent[endpoint.window_param] == start
    assert sent[endpoint.end_param] == end


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_refuses_to_run_without_a_window_start(mock_rest_client, endpoint, without_configured_starts):
    """No cursor value and no start in `params`: an error naming the config key, never a
    request the API answers with a default window of its own."""
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})

    source = aquabyte_source(base_url=SOURCE_CONFIG["base_url"], api_key=SOURCE_CONFIG["api_key"])

    with pytest.raises(Exception, match=endpoint.config_key):
        run_source(f"test_no_window_start_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_refuses_a_disabled_incremental_with_no_window_start(mock_rest_client, endpoint):
    """`incremental_*=None` switches the cursor off, so nothing is left to send a start."""
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.resources[endpoint.resource].bind(**{endpoint.incremental_argument: None})

    with pytest.raises(Exception, match=endpoint.window_param):
        run_source(f"test_disabled_cursor_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_runs_cursorless_on_a_window_start_from_params(mock_rest_client, endpoint):
    """`incremental_*=None` plus a start in `params` is a valid run: no cursor, one window."""
    start = endpoint.window[0]
    _, load_info = _run(
        mock_rest_client,
        endpoint,
        "test_cursorless",
        **{endpoint.incremental_argument: None},
        params={endpoint.window_param: start},
    )

    assert load_info is not None
    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.window_param] == start


def test_cursor_starts_are_not_required_by_resources_that_take_no_cursor(mock_rest_client):
    """`sites` loads with only base_url and api_key — the cursor starts are not its business."""
    mock_rest_client.paginate.side_effect = serve({"/sites": load_mock("sites.json")["sites"]})

    source = aquabyte_source(base_url=SOURCE_CONFIG["base_url"], api_key=SOURCE_CONFIG["api_key"])
    _, load_info = run_source("test_sites_without_cursor_starts", source, ["sites"])

    assert load_info is not None


@pytest.mark.parametrize("endpoint", WITH_OPTIONAL, ids=lambda endpoint: endpoint.resource)
def test_resource_sends_an_optional_param_only_when_it_is_bound(mock_rest_client, endpoint):
    """An optional param is absent unless asked for, so the API's own default applies."""
    argument, query_param, value = endpoint.optional_param

    _run(mock_rest_client, endpoint, "test_optional_unset")
    assert query_param not in params_sent(mock_rest_client, endpoint.path)[0]

    _run(mock_rest_client, endpoint, "test_optional_set", **{argument: value})
    assert params_sent(mock_rest_client, endpoint.path)[0][query_param] == value
