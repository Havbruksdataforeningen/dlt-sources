"""Behaviour every data resource shares, asserted once per endpoint.

These are the mechanics the source promises for all of them — pen fan-out, the window
start, the envelope key, the paginator, and the optional params. Behaviour peculiar to
one resource lives in that resource's own test module.
"""

from dataclasses import dataclass
from typing import Any

import dlt
import pytest
from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    TIME_RANGE,
    assert_pen_ids,
    assert_row_count,
    calls_to,
    load_mock,
    params_sent,
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
    cursor_path: str
    optional_param: tuple[str, str, Any] | None = None
    """(resource argument, the query param it becomes, a value to send)."""
    single_page: bool = False

    @property
    def records(self) -> list[dict]:
        return load_mock(self.mock_file)[self.selector]

    @property
    def window(self) -> dict[str, str]:
        return DATE_RANGE if self.window_param == "fromDate" else TIME_RANGE

    @property
    def configured_start(self) -> str:
        return SOURCE_CONFIG["initial_date" if self.window_param == "fromDate" else "initial_time"]


ENDPOINTS = [
    Endpoint(
        "environmental",
        "/environmental",
        "environmental.json",
        "data",
        "fromTime",
        "fromTime",
        optional_param=("period", "period", "15min"),
    ),
    Endpoint(
        "biomass",
        "/biomass",
        "biomass.json",
        "biomass",
        "fromDate",
        "date",
        optional_param=("bucket_size", "bucketSize", 500),
    ),
    Endpoint(
        "harvest_report",
        "/biomass/harvestReport",
        "harvest_report.json",
        "reports",
        "fromDate",
        "slaughterStartDate",
        single_page=True,
    ),
    Endpoint("lice_count", "/liceCount", "lice_count.json", "liceCount", "fromDate", "date"),
    Endpoint(
        "behaviour_swim_speed",
        "/behaviour/swimSpeed",
        "swim_speed.json",
        "swimSpeed",
        "fromTime",
        "fromTime",
        optional_param=("period", "period", "h"),
    ),
    Endpoint(
        "behaviour_breathing_index",
        "/behaviour/breathingIndex",
        "breathing_index.json",
        "breathingIndex",
        "fromTime",
        "fromTime",
    ),
    Endpoint("welfare_scores", "/welfareScores", "welfare_scores.json", "welfareScores", "fromDate", "date"),
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
    pipeline, load_info = _run(mock_rest_client, endpoint, "test_load", pen_id="pen-001", **endpoint.window)

    assert load_info is not None
    assert_row_count(pipeline, endpoint.resource, len(endpoint.records))
    assert_pen_ids(pipeline, endpoint.resource, ["pen-001"])

    (call,) = calls_to(mock_rest_client, endpoint.path)
    assert call["data_selector"] == endpoint.selector
    assert isinstance(call["paginator"], SinglePagePaginator) is endpoint.single_page


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_defaults_to_every_pen_in_one_request(mock_rest_client, endpoint):
    """`penId=all` is the default — one request covering every pen, not one request per pen."""
    pipeline, load_info = _run(mock_rest_client, endpoint, "test_all_pens", **endpoint.window)

    assert load_info is not None
    assert_row_count(pipeline, endpoint.resource, len(endpoint.records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, endpoint.resource, ACTIVE_PEN_IDS)
    assert [sent["penId"] for sent in params_sent(mock_rest_client, endpoint.path)] == ["all"]


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_always_sends_a_window_start(mock_rest_client, endpoint):
    """Nothing bound: the cursor's initial value is still sent, never an open window."""
    _, load_info = _run(mock_rest_client, endpoint, "test_window")

    assert load_info is not None
    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.window_param] == endpoint.configured_start


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_falls_back_to_the_configured_start_without_a_cursor_value(mock_rest_client, endpoint):
    """An incremental override carrying no initial value still sends the configured start."""
    mock_rest_client.paginate.reset_mock()
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.resources[endpoint.resource].apply_hints(incremental=dlt.sources.incremental(endpoint.cursor_path))
    _, load_info = run_source(f"test_no_cursor_{endpoint.resource}", source, [endpoint.resource])

    assert load_info is not None
    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.window_param] == endpoint.configured_start


@pytest.mark.parametrize("endpoint", WITH_OPTIONAL, ids=lambda endpoint: endpoint.resource)
def test_resource_sends_an_optional_param_only_when_it_is_bound(mock_rest_client, endpoint):
    """An optional param is absent unless asked for, so the API's own default applies."""
    argument, query_param, value = endpoint.optional_param

    _run(mock_rest_client, endpoint, "test_optional_unset", **endpoint.window)
    assert query_param not in params_sent(mock_rest_client, endpoint.path)[0]

    _run(mock_rest_client, endpoint, "test_optional_set", **{argument: value}, **endpoint.window)
    assert params_sent(mock_rest_client, endpoint.path)[0][query_param] == value
