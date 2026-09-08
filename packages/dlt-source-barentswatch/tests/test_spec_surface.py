"""The paths, server and token endpoint the source hard-codes, checked against the committed spec: this is what fails when a refresh moves one."""

import json
from pathlib import Path

import pytest

from dlt_source_barentswatch.fishhealth import BASE_URL, SCOPE, TOKEN_URL
from tests.conftest import (
    LOCALITIES_PATH,
    LOCALITIES_WITH_SALMONOIDS_PATH,
    LOCALITY_WEEK_PATH,
    LOCALITY_WEEK_SUMMARY_PATH,
)

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "fishhealth.json").read_text())


def _spec_path(path: str) -> str:
    """The spec's key for one of the paths the source requests."""
    assert "/" + path in SPEC["paths"], f"{path} is not a path in specs/fishhealth.json"
    return "/" + path


def _path_params(path: str, method: str) -> set[str]:
    return {param["name"] for param in SPEC["paths"][path][method].get("parameters", []) if param["in"] == "path"}


@pytest.mark.parametrize(
    ("source_path", "method", "path_params"),
    [
        (LOCALITIES_PATH, "get", set()),
        (LOCALITIES_WITH_SALMONOIDS_PATH, "get", set()),
        (LOCALITY_WEEK_PATH, "get", {"localityNo", "year", "week"}),
        (LOCALITY_WEEK_SUMMARY_PATH, "post", {"year", "week"}),
    ],
    ids=["localities", "localities_with_salmonoids", "locality_week", "locality_week_summary"],
)
def test_path_exists_with_the_method_and_path_parameters_the_source_uses(source_path, method, path_params):
    """The source fills exactly the path values the spec declares, and calls the method it declares."""
    path = _spec_path(source_path)
    assert method in SPEC["paths"][path]
    assert _path_params(path, method) == path_params
    assert source_path.count("{") == len(path_params)
    assert not any(
        param.get("required") for param in SPEC["paths"][path][method].get("parameters", []) if param["in"] == "query"
    ), "the source sends no query string"


def test_summary_request_body_is_locality_report_query_v2_with_production_area_and_organization():
    """The body `locality_week_summary` sends verbatim is this schema; a refresh that renames a filter fails here."""
    path = _spec_path(LOCALITY_WEEK_SUMMARY_PATH)
    body = SPEC["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
    schema_name = body["$ref"].removeprefix("#/components/schemas/")
    assert schema_name.endswith("LocalityReportQueryV2"), schema_name
    query = SPEC["components"]["schemas"][schema_name]
    assert query["additionalProperties"] is False
    assert query["properties"]["productionArea"]["type"] == "integer"
    assert query["properties"]["organization"]["type"] == "string"


def test_base_url_is_the_specs_server():
    """`BASE_URL` is the spec's one server plus a trailing slash, which is what `RESTClient` joins paths onto."""
    (server,) = SPEC["servers"]
    assert server["url"] + "/" == BASE_URL


def test_token_url_and_scope_are_the_specs_client_credentials_flow():
    flow = SPEC["components"]["securitySchemes"]["oauth2"]["flows"]["clientCredentials"]
    assert flow["tokenUrl"] == TOKEN_URL
    assert SCOPE in flow["scopes"]
