"""The endpoints the source reads are checked against the committed OpenAPI spec.

The source addresses four paths, one server and one token endpoint, all fixed as module
constants. These tests are what fails when a spec refresh moves any of them: a renamed
path, a new server, a token endpoint elsewhere, a renamed filter in the summary's request
body. `specs/README.md` says how to refresh.
"""

import json
import re
from pathlib import Path

from dlt_source_barentswatch_fishhealth.barentswatch_fishhealth import (
    BASE_URL,
    LOCALITIES_PATH,
    LOCALITIES_WITH_SALMONOIDS_PATH,
    LOCALITY_WEEK_PATH,
    LOCALITY_WEEK_SUMMARY_PATH,
    SCOPE,
    TOKEN_URL,
)

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# The path templates use the source's own placeholder names; the spec's are camelCase.
# Compare them with the placeholders blanked, and check the names separately below.
_PLACEHOLDER = re.compile(r"\{\w+\}")


def _spec_path(source_path: str) -> str:
    """The spec's key for one of the source's path templates."""
    wanted = "/" + _PLACEHOLDER.sub("{}", source_path)
    matches = [path for path in SPEC["paths"] if _PLACEHOLDER.sub("{}", path) == wanted]
    assert matches, f"{source_path} is not a path in specs/openapi.json"
    (path,) = matches
    return path


def _path_params(path: str, method: str = "get") -> set[str]:
    return {param["name"] for param in SPEC["paths"][path][method].get("parameters", []) if param["in"] == "path"}


def test_localities_path_is_a_get_with_no_path_parameters_and_only_an_optional_query():
    """The full list is addressed by nothing. The spec's one query parameter, a name search, is optional and unused."""
    path = _spec_path(LOCALITIES_PATH)
    assert "get" in SPEC["paths"][path]
    assert _path_params(path) == set()
    query = [param for param in SPEC["paths"][path]["get"].get("parameters", []) if param["in"] == "query"]
    assert [param["name"] for param in query] == ["query"]
    assert not any(param.get("required") for param in query), "the source sends no query string"
    assert "?" not in LOCALITIES_PATH


def test_localities_response_is_an_array_of_the_five_register_fields():
    """What `localities` lands: a rename here shows up as a renamed column downstream."""
    path = _spec_path(LOCALITIES_PATH)
    body = SPEC["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert body["type"] == "array"
    item = SPEC["components"]["schemas"][body["items"]["$ref"].removeprefix("#/components/schemas/")]
    assert set(item["properties"]) == {
        "aquaCultureRegistryVersion",
        "localityNo",
        "name",
        "municipalityNo",
        "municipality",
    }
    assert item["properties"]["localityNo"]["type"] == "integer"
    assert item["properties"]["municipalityNo"]["type"] == "string"


def test_localities_with_salmonoids_path_is_a_get_with_no_parameters():
    path = _spec_path(LOCALITIES_WITH_SALMONOIDS_PATH)
    assert "get" in SPEC["paths"][path]
    assert _path_params(path) == set()
    assert not any(param["in"] == "query" for param in SPEC["paths"][path]["get"].get("parameters", []))


def test_locality_week_path_is_a_get_addressed_by_locality_year_and_week():
    path = _spec_path(LOCALITY_WEEK_PATH)
    assert "get" in SPEC["paths"][path]
    assert _path_params(path) == {"localityNo", "year", "week"}
    assert LOCALITY_WEEK_PATH.count("{") == 3, "the source fills exactly the three path values"


def test_summary_path_is_a_post_addressed_by_year_and_week():
    """A `POST`, but a read: the path is the week and the body is the filter."""
    path = _spec_path(LOCALITY_WEEK_SUMMARY_PATH)
    assert set(SPEC["paths"][path]) == {"post"}
    assert _path_params(path, "post") == {"year", "week"}
    assert LOCALITY_WEEK_SUMMARY_PATH.count("{") == 2, "the source fills exactly the two path values"
    assert not any(param["in"] == "query" for param in SPEC["paths"][path]["post"].get("parameters", []))


def test_summary_request_body_declares_the_two_filters_the_source_names():
    """`productionArea` (one integer, 1 to 13) and `organization` (one string) are what the source's arguments become.

    A refresh that renames either, or turns one into a list, fails here rather than as a
    silent 400 the source would skip as "no report".
    """
    path = _spec_path(LOCALITY_WEEK_SUMMARY_PATH)
    body = SPEC["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
    query = SPEC["components"]["schemas"][body["$ref"].removeprefix("#/components/schemas/")]
    assert query["additionalProperties"] is False, "the API rejects a body field it does not declare"

    area = query["properties"]["productionArea"]
    assert area["type"] == "integer"
    assert (area["minimum"], area["maximum"]) == (1, 13)
    organization = query["properties"]["organization"]
    assert organization["type"] == "string"


def test_base_url_is_the_specs_server():
    """`BASE_URL` is the spec's one server plus a trailing slash, which is what `RESTClient` joins paths onto."""
    (server,) = SPEC["servers"]
    assert server["url"] + "/" == BASE_URL


def test_token_url_and_scope_are_the_specs_client_credentials_flow():
    flow = SPEC["components"]["securitySchemes"]["oauth2"]["flows"]["clientCredentials"]
    assert flow["tokenUrl"] == TOKEN_URL
    assert SCOPE in flow["scopes"]
