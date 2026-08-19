"""Record shapes written by hand are checked against `specs/openapi.json`.

Two things here describe what a record looks like, and neither is generated: the fixtures
under `mock_responses/`, and the column hints in `aquabyte.py`. The spec is the authority
for both. A fixture in a shape the API could not produce makes the whole offline suite
blind to the real one, and a column hint naming a field the API does not send is a hint
that silently does nothing.

Presence is asserted only for fields the spec both requires and forbids to be null. The
API omits nullable fields it declares required — see "API quirks worth knowing" in
`specs/README.md`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import ALL_PEN_IDS, MOCK_DIR, SOURCE_CONFIG, load_mock

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# fixture file -> the endpoint whose response it stands in for. The response schema in the
# spec covers the envelope key too, so the fixture's own top-level shape is checked with it.
FIXTURES = {
    "sites.json": "/sites",
    "environmental.json": "/environmental",
    "environmental_latest.json": "/environmental/latest",
    "biomass.json": "/biomass",
    "harvest_report.json": "/biomass/harvestReport",
    "lice_count.json": "/liceCount",
    "swim_speed.json": "/behaviour/swimSpeed",
    "breathing_index.json": "/behaviour/breathingIndex",
    "welfare_scores.json": "/welfareScores",
}

# resource -> the endpoint it reads. `pens` reads none: it unwraps the `pens` list nested
# in a `/sites` record, so its records are that list's items.
RESOURCE_ENDPOINTS = {
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

# OpenAPI type -> the dlt data type a column hint gives it. Dates and timestamps stay text:
# the source declares them as the API sends them and leaves parsing to the consumer.
DLT_DATA_TYPES = {"string": "text", "number": "double", "integer": "bigint", "boolean": "bool"}

JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    """Follow a `$ref` into `components.schemas`."""
    while "$ref" in schema:
        schema = SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _response_schema(path: str) -> dict[str, Any]:
    """The schema of the 200 response body of `GET path`, envelope included."""
    return _resolve(SPEC["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"])


def _records_key(path: str) -> str:
    """The envelope key holding the records — the one array in the response body."""
    properties = _response_schema(path)["properties"]
    (key,) = [name for name, prop in properties.items() if prop.get("type") == "array"]
    return key


def _record_schema(path: str) -> dict[str, Any]:
    """The schema of one record inside that response's envelope."""
    envelope = _response_schema(path)
    return _resolve(envelope["properties"][_records_key(path)]["items"])


def _nullable(schema: dict[str, Any]) -> bool:
    return any(branch.get("type") == "null" for branch in schema.get("anyOf", []))


def _problems(value: Any, schema: dict[str, Any], where: str) -> list[str]:
    """Every way `value` departs from `schema`, as messages naming where it happened."""
    schema = _resolve(schema)

    if "anyOf" in schema:
        branches = [_problems(value, branch, where) for branch in schema["anyOf"]]
        return [] if any(not found for found in branches) else [f"{where} matches no branch of anyOf"]

    declared = schema.get("type")
    if declared is None:
        return []
    expected = JSON_TYPES[declared]
    if isinstance(value, bool) != (declared == "boolean") or not isinstance(value, expected):
        return [f"{where} is {type(value).__name__}, not {declared}"]

    if declared == "array":
        return [p for i, item in enumerate(value) for p in _problems(item, schema["items"], f"{where}[{i}]")]

    if declared == "object":
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        found = [
            f"{where}.{key} is not a field of {schema.get('title', 'the record')}"
            for key in value
            if key not in properties and not extra
        ]
        found += [
            f"{where}.{key} is required and cannot be null, but is missing"
            for key in schema.get("required", [])
            if key not in value and not _nullable(properties[key])
        ]
        for key, item in value.items():
            found += _problems(item, properties.get(key) or extra or {}, f"{where}.{key}")
        return found

    return []


@pytest.mark.parametrize(("filename", "path"), FIXTURES.items())
def test_fixture_matches_its_endpoints_response_schema(filename, path):
    problems = _problems(load_mock(filename), _response_schema(path), filename)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("filename", "path"), FIXTURES.items())
def test_fixture_has_records(filename, path):
    """An empty envelope would satisfy the schema and prove nothing downstream."""
    assert load_mock(filename)[_records_key(path)]


@pytest.mark.parametrize(("resource_name", "path"), RESOURCE_ENDPOINTS.items())
def test_column_hints_name_fields_the_api_sends(resource_name, path):
    """A hint is only worth having on a field the spec declares, typed the way it declares it."""
    properties = _record_schema(path)["properties"]
    hinted = _hinted_columns(resource_name)

    unknown = set(hinted) - set(properties)
    assert not unknown, f"{resource_name} hints {sorted(unknown)}, which /{path.lstrip('/')} does not send"

    for name, data_type in hinted.items():
        assert data_type == _expected_data_type(properties[name]), f"{resource_name}.{name} is typed against the spec"


def test_pens_column_hints_name_fields_the_api_sends():
    """`pens` has no endpoint of its own — its records are the `pens` list on a site."""
    properties = _resolve(_record_schema("/sites")["properties"]["pens"]["items"])["properties"]
    hinted = _hinted_columns("pens")

    assert not set(hinted) - set(properties)
    for name, data_type in hinted.items():
        assert data_type == _expected_data_type(properties[name]), f"pens.{name} is typed against the spec"


def _hinted_columns(resource_name: str) -> dict[str, str]:
    """The declared columns of a resource's table, minus the ones dlt adds itself."""
    table = aquabyte_source(**SOURCE_CONFIG).resources[resource_name].compute_table_schema()
    hinted = {}
    for name, column in table.get("columns", {}).items():
        data_type = column.get("data_type")
        if data_type and not name.startswith("_dlt"):
            hinted[name] = data_type
    return hinted


def _expected_data_type(prop: dict[str, Any]) -> str:
    """The dlt data type for a spec property, looking through its nullable wrapper."""
    declared = [branch for branch in prop.get("anyOf", [prop]) if branch.get("type") != "null"]
    return DLT_DATA_TYPES[_resolve(declared[0])["type"]]


def test_sites_fixture_matches_the_pen_constants():
    """`conftest` hardcodes the pen ids; the fixture is where they actually come from."""
    sites = load_mock("sites.json")["sites"]
    pens = [pen for site in sites for pen in site["pens"]]
    assert sorted(pen["id"] for pen in pens) == sorted(ALL_PEN_IDS)


def test_no_fixture_carries_an_external_identifier():
    """These two fields are declared by the API and were never sent — see the README.

    An earlier fixture invented them, which made the suite assert a shape the live API
    has not produced. They most likely arrive once an account populates them, so if that
    happens, re-record from live and delete this test; do not add them back by hand.
    """
    for path in sorted(MOCK_DIR.glob("*.json")):
        payload = json.dumps(json.loads(path.read_text()))
        for field in ("external_site_id", "external_id"):
            assert field not in payload, f"{path.name} carries {field}, which the API does not return"
