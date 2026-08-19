"""Record shapes written by hand are checked against `specs/openapi.json`.

Two things here describe what a record looks like, and neither is generated: the fixtures
under `mock_responses/`, and the column hints in `aquabyte.py`. The spec is the authority
for both. A fixture in a shape the API could not produce makes the whole offline suite
blind to the real one, and a column hint naming a field the API does not send is a hint
that silently does nothing.

The spec is validated as the JSON Schema it is, with two relaxations applied first:

- **A required field that may be null may also be absent.** The API omits such fields
  rather than sending nulls — see "API quirks worth knowing" in `specs/README.md`.
- **A record may carry no field the spec does not declare.** JSON Schema allows extras by
  default; here an extra means an invented fixture, which is the thing worth catching.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import ALL_PEN_IDS, MOCK_DIR, SOURCE_CONFIG, load_mock

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# endpoint -> the fixture standing in for its response, and the resource that reads it.
# `pens` is absent: it has no endpoint, and unwraps the `pens` list nested in a site.
ENDPOINTS = {
    "/sites": ("sites.json", "sites"),
    "/environmental": ("environmental.json", "environmental"),
    "/environmental/latest": ("environmental_latest.json", "environmental_latest"),
    "/biomass": ("biomass.json", "biomass"),
    "/biomass/harvestReport": ("harvest_report.json", "harvest_report"),
    "/liceCount": ("lice_count.json", "lice_count"),
    "/behaviour/swimSpeed": ("swim_speed.json", "behaviour_swim_speed"),
    "/behaviour/breathingIndex": ("breathing_index.json", "behaviour_breathing_index"),
    "/welfareScores": ("welfare_scores.json", "welfare_scores"),
}

RESOURCE_ENDPOINTS = {resource: path for path, (_, resource) in ENDPOINTS.items()}

# OpenAPI type -> the dlt data type a column hint gives it. Dates and timestamps stay text:
# the source declares them as the API sends them and leaves parsing to the consumer.
DLT_DATA_TYPES = {"string": "text", "number": "double", "integer": "bigint", "boolean": "bool"}


def _permits_null(schema: dict[str, Any]) -> bool:
    return any(branch.get("type") == "null" for branch in schema.get("anyOf", []))


def _tightened(node: Any) -> Any:
    """The spec with the two relaxations of the module docstring applied, recursively."""
    if isinstance(node, list):
        return [_tightened(item) for item in node]
    if not isinstance(node, dict):
        return node
    schema = {key: _tightened(value) for key, value in node.items()}
    if "properties" in schema:
        schema.setdefault("additionalProperties", False)
        schema["required"] = [
            name for name in schema.get("required", []) if not _permits_null(schema["properties"][name])
        ]
    return schema


TIGHTENED_SPEC = _tightened(SPEC)


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    """Follow a `$ref` into `components.schemas`."""
    while "$ref" in schema:
        schema = SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _response_schema(path: str) -> dict[str, Any]:
    """The schema of the 200 response body of `GET path`, envelope included."""
    return _resolve(SPEC["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"])


def _records_key(envelope: dict[str, Any]) -> str:
    """The envelope key holding the records — the one array in the response body."""
    (key,) = [name for name, prop in envelope["properties"].items() if prop.get("type") == "array"]
    return key


def _record_schema(resource_name: str) -> dict[str, Any]:
    """The spec's schema for one record a resource loads."""
    if resource_name == "pens":
        return _resolve(_record_schema("sites")["properties"]["pens"]["items"])
    envelope = _response_schema(RESOURCE_ENDPOINTS[resource_name])
    return _resolve(envelope["properties"][_records_key(envelope)]["items"])


@pytest.mark.parametrize(("path", "fixture_and_resource"), ENDPOINTS.items())
def test_fixture_matches_its_endpoints_response_schema(path, fixture_and_resource):
    filename, _ = fixture_and_resource
    body = SPEC["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator = Draft202012Validator({**TIGHTENED_SPEC, **body})
    problems = [
        f"{filename}.{error.json_path}: {error.message}" for error in validator.iter_errors(load_mock(filename))
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("path", "fixture_and_resource"), ENDPOINTS.items())
def test_fixture_has_records(path, fixture_and_resource):
    """An empty envelope would satisfy the schema and prove nothing downstream."""
    filename, _ = fixture_and_resource
    assert load_mock(filename)[_records_key(_response_schema(path))]


@pytest.mark.parametrize("resource_name", [*RESOURCE_ENDPOINTS, "pens"])
def test_column_hints_match_the_spec(resource_name):
    """A hint is worth having only on a field the API sends, typed and nulled as declared."""
    record = _record_schema(resource_name)
    properties = record["properties"]
    hinted = _hinted_columns(resource_name)

    unknown = set(hinted) - set(properties)
    assert not unknown, f"{resource_name} hints {sorted(unknown)}, which the API does not send"

    for name, column in hinted.items():
        declared = properties[name]
        assert column.get("data_type") == _dlt_data_type(declared), f"{resource_name}.{name}: wrong data type"
        mandatory = name in record.get("required", []) and not _permits_null(declared)
        assert column.get("nullable", True) is not mandatory, f"{resource_name}.{name}: wrong nullability"


def _hinted_columns(resource_name: str) -> dict[str, dict[str, Any]]:
    """The declared columns of a resource's table, minus the ones dlt adds itself."""
    table = aquabyte_source(**SOURCE_CONFIG).resources[resource_name].compute_table_schema()
    return {name: dict(column) for name, column in table.get("columns", {}).items() if not name.startswith("_dlt")}


def _dlt_data_type(declared: dict[str, Any]) -> str:
    """The dlt data type for a spec property, looking through its nullable wrapper."""
    branches = [branch for branch in declared.get("anyOf", [declared]) if branch.get("type") != "null"]
    return DLT_DATA_TYPES[_resolve(branches[0])["type"]]


def test_sites_fixture_matches_the_pen_constants():
    """`conftest` hardcodes the pen ids; the fixture is where they actually come from."""
    sites = load_mock("sites.json")["sites"]
    pens = [pen for site in sites for pen in site["pens"]]
    assert sorted(pen["id"] for pen in pens) == sorted(ALL_PEN_IDS)


def test_no_fixture_carries_an_external_identifier():
    """These two fields are declared by the API and were never sent — see `specs/README.md`.

    An earlier fixture invented them, which made the suite assert a shape the live API
    has not produced. They most likely arrive once an account populates them, so if that
    happens, re-record from live and delete this test; do not add them back by hand.
    """
    for path in sorted(MOCK_DIR.glob("*.json")):
        payload = json.dumps(json.loads(path.read_text()))
        for field in ("external_site_id", "external_id"):
            assert field not in payload, f"{path.name} carries {field}, which the API does not return"
