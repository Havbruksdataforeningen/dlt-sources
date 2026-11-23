"""The published parameter surface is checked against the committed OpenAPI spec.

These tests are what fails when the spec and the code drift apart; `REFERENCE.md` explains
which endpoints and params the source deliberately does not expose.
"""

import inspect
import json
import re
from pathlib import Path

import pytest

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ENDPOINTS,
    SOURCE_CONFIG,
    Endpoint,
    load_mock,
    params_sent,
    resource_signature,
    run_source,
    serve,
)

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# `sites` reads a second endpoint, switching on `site_id`, so its surface is the union of
# the two — which is how the per-site endpoint's path param gets checked.
ALSO_READS = {"sites": ["/sites/{siteId}"]}

# Params no resource exposes, because a mechanism owns them: `nextToken` belongs to the
# paginator, and the window params to the resource's incremental, which is where a caller
# sets a window.
PARAMS_OWNED_BY_MECHANICS = {"next_token", "from_date", "to_date", "from_time", "to_time"}

# Resource arguments that are not API params.
NON_API_ARGS = {"params", "max_window_days"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _spec_params(endpoint: Endpoint) -> set[str]:
    """Every query and path param the spec documents for the resource's endpoints, snake_cased."""
    paths = [endpoint.path, *ALSO_READS.get(endpoint.resource, [])]
    return {
        _snake(param["name"])
        for path in paths
        for param in SPEC["paths"][path]["get"].get("parameters", [])
        if param["in"] in {"query", "path"}
    }


def _signature(resource_name: str) -> inspect.Signature:
    return resource_signature(aquabyte_source(**SOURCE_CONFIG), resource_name)


def _resource_params(resource_name: str) -> set[str]:
    names = _signature(resource_name).parameters
    return {name for name in names if name not in NON_API_ARGS and not name.startswith("incremental")}


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_resource_offers_exactly_its_endpoints_params(endpoint):
    """Each resource's signature lists its endpoints' params — no more, no fewer."""
    expected = _spec_params(endpoint) - PARAMS_OWNED_BY_MECHANICS
    assert _resource_params(endpoint.resource) == expected


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda endpoint: endpoint.resource)
def test_params_passthrough_reaches_the_request(mock_rest_client, endpoint):
    """A query param the API grows later can be sent without a release, on every resource."""
    mock_rest_client.paginate.side_effect = serve({})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.resources[endpoint.resource].bind(params={"someFutureParam": "yes"})
    run_source(f"test_params_passthrough_{endpoint.resource}", source, [endpoint.resource])

    sent = params_sent(mock_rest_client, endpoint.path)
    assert sent, "the resource must reach its endpoint"
    assert all(one["someFutureParam"] == "yes" for one in sent)


def test_params_passthrough_wins_over_named_params(mock_rest_client):
    """The passthrough is merged last, so it can also override a named param."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": load_mock("biomass.json")["biomass"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(pen_id="pen-001", params={"fromDate": "2025-06-01", "penId": "pen-004"})
    run_source("test_params_override", source, ["biomass"])

    sent = params_sent(mock_rest_client, "/biomass")[0]
    assert sent["fromDate"] == "2025-06-01"
    assert sent["penId"] == "pen-004"
