"""Behaviour every data resource shares, asserted once per endpoint.

These are the mechanics the source promises for all of them — the pen, the window params
the incremental drives, the envelope key, the paginator, and the optional params. How a
window too wide for the API becomes several requests is in `test_window_splitting.py`.
Behaviour peculiar to one resource lives in that resource's own test module.
"""

from typing import Any

import dlt
import pytest
from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    SOURCE_CONFIG,
    WINDOWED_ENDPOINTS,
    WindowedEndpoint,
    assert_pen_ids,
    assert_row_count,
    calls_to,
    load_mock,
    params_sent,
    run_source,
    serve,
)

WITH_OPTIONAL = [endpoint for endpoint in WINDOWED_ENDPOINTS if endpoint.optional_param]


def _run(mock_rest_client, endpoint: WindowedEndpoint, name: str, **bound: Any):
    """Serve the endpoint's mock and run its resource, returning (pipeline, load_info)."""
    mock_rest_client.paginate.reset_mock()
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})
    source = aquabyte_source(**SOURCE_CONFIG)
    if bound:
        source.resources[endpoint.resource].bind(**bound)
    return run_source(f"{name}_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_loads_the_records_of_the_pen_it_was_bound_to(mock_rest_client, endpoint):
    """One pen bound: that pen's records land, read from the endpoint's own envelope key."""
    pipeline, _ = _run(mock_rest_client, endpoint, "test_load", pen_id="pen-001")

    assert_row_count(pipeline, endpoint.resource, len(endpoint.records))
    assert_pen_ids(pipeline, endpoint.resource, ["pen-001"])

    calls = calls_to(mock_rest_client, endpoint.path)
    assert calls, "the resource must reach its endpoint"
    for call in calls:
        assert call["data_selector"] == endpoint.selector
        # Only a single-page endpoint names a paginator; the rest take the client's own.
        assert isinstance(call.get("paginator"), SinglePagePaginator) is endpoint.single_page


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_defaults_to_every_pen(mock_rest_client, endpoint):
    """`penId=all` is the default: every request covers every pen, never one request per pen.

    A run makes one request per window rather than exactly one — see
    `test_window_splitting.py` — but the pen is not what decides how many.
    """
    pipeline, _ = _run(mock_rest_client, endpoint, "test_all_pens")

    assert_row_count(pipeline, endpoint.resource, len(endpoint.records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, endpoint.resource, ACTIVE_PEN_IDS)
    sent = params_sent(mock_rest_client, endpoint.path)
    assert sent, "the resource must reach its endpoint"
    assert {one["penId"] for one in sent} == {"all"}


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_always_sends_a_window_start(mock_rest_client, endpoint):
    """Nothing bound: the cursor's initial value is still sent, never an open window."""
    _run(mock_rest_client, endpoint, "test_window")

    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.cursor.start_param] == endpoint.configured_start


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_requests_the_window_a_backfill_incremental_carries(mock_rest_client, endpoint):
    """A bound backfill incremental drives both window params — start from its
    `initial_value`, end from its `end_value` — so the API is asked for exactly the
    rows dlt will keep. A window inside the window cap is one request."""
    start, end = endpoint.cursor.window
    window = dlt.sources.incremental(initial_value=start, end_value=end)
    _run(mock_rest_client, endpoint, "test_backfill", **{endpoint.incremental_argument: window})

    (sent,) = params_sent(mock_rest_client, endpoint.path)
    assert sent[endpoint.cursor.start_param] == start
    assert sent[endpoint.cursor.end_param] == end


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_splits_its_window_at_a_bound_max_window_days(mock_rest_client, endpoint):
    """The window caps are measured, not documented, so a consumer can replace one per resource:
    lower it when a window the API accepts is too slow to answer, or correct it when a cap has moved.
    """
    start, end = endpoint.cursor.window
    window = dlt.sources.incremental(initial_value=start, end_value=end)
    _run(mock_rest_client, endpoint, "test_bound_cap", max_window_days=10, **{endpoint.incremental_argument: window})

    sent = params_sent(mock_rest_client, endpoint.path)
    assert len(sent) == 3, "a 30-day window at a 10-day window cap is three requests"
    assert (sent[0][endpoint.cursor.start_param], sent[-1][endpoint.cursor.end_param]) == (start, end)


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_refuses_to_run_without_a_window_start(mock_rest_client, endpoint, without_configured_starts):
    """No cursor value and no start in `params`: an error naming the config key, never a
    request the API answers with a default window of its own."""
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})

    source = aquabyte_source(base_url=SOURCE_CONFIG["base_url"], api_key=SOURCE_CONFIG["api_key"])

    with pytest.raises(Exception, match=endpoint.cursor.config_key):
        run_source(f"test_no_window_start_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_refuses_a_disabled_incremental_with_no_window_start(mock_rest_client, endpoint):
    """`incremental_*=None` switches the cursor off, so nothing is left to send a start."""
    mock_rest_client.paginate.side_effect = serve({endpoint.path: endpoint.records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.resources[endpoint.resource].bind(**{endpoint.incremental_argument: None})

    with pytest.raises(Exception, match=endpoint.cursor.start_param):
        run_source(f"test_disabled_cursor_{endpoint.resource}", source, [endpoint.resource])


@pytest.mark.parametrize("endpoint", WINDOWED_ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_runs_cursorless_on_a_window_start_from_params(mock_rest_client, endpoint):
    """`incremental_*=None` plus a start in `params` is a valid run: no cursor, one window."""
    start = endpoint.cursor.window[0]
    _run(
        mock_rest_client,
        endpoint,
        "test_cursorless",
        **{endpoint.incremental_argument: None},
        params={endpoint.cursor.start_param: start},
    )

    assert params_sent(mock_rest_client, endpoint.path)[0][endpoint.cursor.start_param] == start


def test_cursor_starts_are_not_required_by_resources_that_take_no_cursor(mock_rest_client, without_configured_starts):
    """`sites` loads with only base_url and api_key — the cursor starts are not its business."""
    sites = load_mock("sites.json")["sites"]
    mock_rest_client.paginate.side_effect = serve({"/sites": sites})

    source = aquabyte_source(base_url=SOURCE_CONFIG["base_url"], api_key=SOURCE_CONFIG["api_key"])
    pipeline, _ = run_source("test_sites_without_cursor_starts", source, ["sites"])

    assert_row_count(pipeline, "sites", len(sites))


@pytest.mark.parametrize("endpoint", WITH_OPTIONAL, ids=lambda endpoint: endpoint.resource)
def test_resource_sends_an_optional_param_only_when_it_is_bound(mock_rest_client, endpoint):
    """An optional param is absent unless asked for, so the API's own default applies."""
    argument, query_param, value = endpoint.optional_param

    _run(mock_rest_client, endpoint, "test_optional_unset")
    assert query_param not in params_sent(mock_rest_client, endpoint.path)[0]

    _run(mock_rest_client, endpoint, "test_optional_set", **{argument: value})
    assert params_sent(mock_rest_client, endpoint.path)[0][query_param] == value
