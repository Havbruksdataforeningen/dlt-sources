"""The published parameter surface is checked against the committed OpenAPI spec.

These tests are what fails when the spec and the code drift apart; the README explains
which endpoints and params the source deliberately does not expose.
"""

import inspect
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    load_mock,
    params_sent,
    run_source,
    serve,
)

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# Resource → the endpoint it reads.
ENDPOINTS = {
    "sites": "/sites",
    "environmental": "/environmental",
    "environmental_latest": "/environmental/latest",
    "biomass": "/biomass",
    "harvest_report": "/biomass/harvestReport",
    "lice_count": "/liceCount",
    "behaviour_swim_speed": "/behaviour/swimSpeed",
    "behaviour_breathing_index": "/behaviour/breathingIndex",
    "welfare_scores": "/welfareScores",
}

# nextToken is pagination mechanics: the paginator owns it, so no resource exposes it.
PARAMS_OWNED_BY_MECHANICS = {"next_token"}

# Resource arguments that are not query params.
NON_QUERY_ARGS = {"params"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _spec_query_params(path: str) -> set[str]:
    parameters = SPEC["paths"][path]["get"].get("parameters", [])
    return {_snake(param["name"]) for param in parameters if param["in"] == "query"}


def _signature(resource_name: str) -> inspect.Signature:
    resource = aquabyte_source(**SOURCE_CONFIG).resources[resource_name]
    return inspect.signature(cast(Callable, resource._pipe.gen))


def _resource_params(resource_name: str) -> set[str]:
    names = _signature(resource_name).parameters
    return {name for name in names if name not in NON_QUERY_ARGS and not name.startswith("incremental")}


@pytest.mark.parametrize(("resource_name", "path"), ENDPOINTS.items())
def test_resource_offers_exactly_its_endpoints_query_params(resource_name, path):
    """Each resource's signature lists its endpoint's query params — no more, no fewer."""
    expected = _spec_query_params(path) - PARAMS_OWNED_BY_MECHANICS
    assert _resource_params(resource_name) == expected


@pytest.mark.parametrize("resource_name", ENDPOINTS)
def test_every_resource_takes_a_params_passthrough(resource_name):
    """A query param the API grows later can be sent without a release."""
    assert "params" in _signature(resource_name).parameters


def test_params_passthrough_reaches_the_request(mock_rest_client):
    """An unknown query param passed through lands on the request untouched."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": load_mock("biomass.json")["biomass"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(from_date="2026-01-01", params={"someFutureParam": "yes"})
    run_source("test_params_passthrough", source, ["biomass"])

    assert params_sent(mock_rest_client, "/biomass")[0]["someFutureParam"] == "yes"


def test_params_passthrough_wins_over_named_params(mock_rest_client):
    """The passthrough is merged last, so it can also override a named param."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": load_mock("biomass.json")["biomass"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(from_date="2026-01-01", params={"fromDate": "2025-06-01"})
    run_source("test_params_override", source, ["biomass"])

    assert params_sent(mock_rest_client, "/biomass")[0]["fromDate"] == "2025-06-01"


def test_pen_id_list_fans_out_one_request_per_pen(mock_rest_client):
    """A list of pen ids is request fan-out only — one request each, nothing filtered."""
    mock_rest_client.paginate.side_effect = serve({"/liceCount": load_mock("lice_count.json")["liceCount"]})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.lice_count.bind(pen_id=["pen-001", "pen-004"], from_date="2026-01-01")
    _, load_info = run_source("test_pen_fan_out", source, ["lice_count"])

    assert load_info is not None
    assert [p["penId"] for p in params_sent(mock_rest_client, "/liceCount")] == ["pen-001", "pen-004"]
