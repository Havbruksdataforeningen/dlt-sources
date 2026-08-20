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
    SOURCE_CONFIG,
    load_mock,
    params_sent,
    resource_signature,
    run_source,
    serve,
)

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# Resource → the endpoints it reads. `sites` reads two, switching on `site_id`, so its
# surface is the union — which is how the per-site endpoint's path param gets checked.
ENDPOINTS = {
    "sites": ("/sites", "/sites/{siteId}"),
    "environmental": ("/environmental",),
    "environmental_latest": ("/environmental/latest",),
    "biomass": ("/biomass",),
    "harvest_report": ("/biomass/harvestReport",),
    "lice_count": ("/liceCount",),
    "behaviour_swim_speed": ("/behaviour/swimSpeed",),
    "behaviour_breathing_index": ("/behaviour/breathingIndex",),
    "welfare_scores": ("/welfareScores",),
}

# Params no resource exposes, because a mechanism owns them: `nextToken` belongs to the
# paginator, and the window params to the resource's incremental, which is where a caller
# sets a window.
PARAMS_OWNED_BY_MECHANICS = {"next_token", "from_date", "to_date", "from_time", "to_time"}

# Resource arguments that are not API params.
NON_API_ARGS = {"params"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _spec_params(paths: tuple[str, ...]) -> set[str]:
    """Every query and path param the given endpoints document, snake_cased."""
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


@pytest.mark.parametrize(("resource_name", "paths"), ENDPOINTS.items())
def test_resource_offers_exactly_its_endpoints_params(resource_name, paths):
    """Each resource's signature lists its endpoints' params — no more, no fewer."""
    expected = _spec_params(paths) - PARAMS_OWNED_BY_MECHANICS
    assert _resource_params(resource_name) == expected


@pytest.mark.parametrize("resource_name", ENDPOINTS)
def test_every_resource_takes_a_params_passthrough(resource_name):
    """A query param the API grows later can be sent without a release."""
    assert "params" in _signature(resource_name).parameters


def test_params_passthrough_reaches_the_request(mock_rest_client):
    """An unknown query param passed through lands on the request untouched."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": load_mock("biomass.json")["biomass"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(params={"someFutureParam": "yes"})
    run_source("test_params_passthrough", source, ["biomass"])

    assert params_sent(mock_rest_client, "/biomass")[0]["someFutureParam"] == "yes"


def test_params_passthrough_wins_over_named_params(mock_rest_client):
    """The passthrough is merged last, so it can also override a named param."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": load_mock("biomass.json")["biomass"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(pen_id="pen-001", params={"fromDate": "2025-06-01", "penId": "pen-004"})
    run_source("test_params_override", source, ["biomass"])

    sent = params_sent(mock_rest_client, "/biomass")[0]
    assert sent["fromDate"] == "2025-06-01"
    assert sent["penId"] == "pen-004"
