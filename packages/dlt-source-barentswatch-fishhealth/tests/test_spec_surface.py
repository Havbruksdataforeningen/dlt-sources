"""The endpoints the source reads are checked against the committed OpenAPI spec.

The source addresses two paths, one server and one token endpoint, all fixed as module
constants. These tests are what fails when a spec refresh moves any of them: a renamed
path, a new server, a token endpoint elsewhere. `specs/README.md` says how to refresh.
"""

import json
import re
from pathlib import Path

from dlt_source_barentswatch_fishhealth.barentswatch_fishhealth import (
    BASE_URL,
    LOCALITIES_PATH,
    LOCALITY_WEEK_PATH,
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


def _path_params(path: str) -> set[str]:
    return {param["name"] for param in SPEC["paths"][path]["get"].get("parameters", []) if param["in"] == "path"}


def test_localities_path_is_a_get_with_no_parameters():
    path = _spec_path(LOCALITIES_PATH)
    assert "get" in SPEC["paths"][path]
    assert _path_params(path) == set()
    assert not any(param["in"] == "query" for param in SPEC["paths"][path]["get"].get("parameters", []))


def test_locality_week_path_is_a_get_addressed_by_locality_year_and_week():
    path = _spec_path(LOCALITY_WEEK_PATH)
    assert "get" in SPEC["paths"][path]
    assert _path_params(path) == {"localityNo", "year", "week"}
    assert LOCALITY_WEEK_PATH.count("{") == 3, "the source fills exactly the three path values"


def test_locality_week_declares_400_as_a_documented_answer():
    """The source skips 400 on the strength of the spec saying it is an answer, not an accident."""
    path = _spec_path(LOCALITY_WEEK_PATH)
    assert "400" in SPEC["paths"][path]["get"]["responses"]


def test_base_url_is_the_specs_server():
    """`BASE_URL` is the spec's one server plus a trailing slash, which is what `RESTClient` joins paths onto."""
    (server,) = SPEC["servers"]
    assert server["url"] + "/" == BASE_URL


def test_token_url_and_scope_are_the_specs_client_credentials_flow():
    flow = SPEC["components"]["securitySchemes"]["oauth2"]["flows"]["clientCredentials"]
    assert flow["tokenUrl"] == TOKEN_URL
    assert SCOPE in flow["scopes"]
