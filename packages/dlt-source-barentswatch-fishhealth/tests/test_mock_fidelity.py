"""Record shapes written by hand are checked against `specs/openapi.json`.

The fixtures under `mock_responses/` describe what a record looks like, and nothing
generates them. The spec is the authority. A fixture in a shape the API could not produce
makes the whole offline suite blind to the real one.

The spec is OpenAPI 3.0. It is validated as the JSON Schema it nearly is, with two
relaxations applied first — both of them the API's own departures from the document, listed
under ["API quirks worth knowing"](../specs/README.md#api-quirks-worth-knowing):

- **A field marked `nullable: true` may be null.** OpenAPI 3.0 spells "may be null" that way,
  and JSON Schema does not read it, so `null` is added to the schema's `type` (or `enum`, or
  an `anyOf` when it has neither).
- **A property whose schema is a bare `$ref` may be null even though the spec does not say
  so.** `productionArea.color`, every `trend`, `cleanerFishTreatment` and
  `mechanicalRemovalTreatment` arrive null. Reference properties are the one place the spec
  cannot carry `nullable`, so the allowance is made for all of them rather than for a list
  that would go stale.

And one tightening: **a record may carry no field the spec does not declare.** JSON Schema
allows extras by default; here an extra means an invented fixture, which is the thing worth
catching. `ProblemDetails` declares `additionalProperties` itself and keeps it — the API's
400 body carries `message` and `bwErrorCode` on top of the standard fields.

Both live samples the fixtures were modelled on validate with 0 errors under this
translation, so a fixture that fails here is wrong, not the translation.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.conftest import ALL_LOCALITY_NOS, MOCK_DIR, load_mock

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())

# (method, path): the operations the source calls, as the spec keys them.
LOCALITIES = ("get", "/v1/geodata/fishhealth/localitieswithsalmonoids")
LOCALITY_WEEK = ("get", "/v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}")
LOCALITY_WEEK_SUMMARY = ("post", "/v2/geodata/fishhealth/locality/{year}/{week}")

# fixture -> the operation and status code whose response it stands in for.
FIXTURES = {
    "localitieswithsalmonoids.json": (LOCALITIES, "200"),
    "locality_week_reported.json": (LOCALITY_WEEK, "200"),
    "locality_week_fallow.json": (LOCALITY_WEEK, "200"),
    "problem_details_400.json": (LOCALITY_WEEK, "400"),
    "locality_week_summary.json": (LOCALITY_WEEK_SUMMARY, "200"),
}


def _as_json_schema(node: Any) -> Any:
    """The spec translated from OpenAPI 3.0 to JSON Schema, with the module docstring's relaxations, recursively."""
    if isinstance(node, list):
        return [_as_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    schema = {key: _as_json_schema(value) for key, value in node.items()}
    nullable = schema.pop("nullable", False)
    if isinstance(schema.get("properties"), dict):
        schema.setdefault("additionalProperties", False)
        for name, prop in schema["properties"].items():
            if isinstance(prop, dict) and "$ref" in prop:
                schema["properties"][name] = {"anyOf": [prop, {"type": "null"}]}
    if nullable is True:
        if "type" in schema:
            declared = schema["type"]
            schema["type"] = [declared, "null"] if isinstance(declared, str) else [*declared, "null"]
            if "enum" in schema and None not in schema["enum"]:
                schema["enum"] = [*schema["enum"], None]
        else:
            schema = {"anyOf": [schema, {"type": "null"}]}
    return schema


JSON_SCHEMA_SPEC = _as_json_schema(SPEC)


def _response_validator(operation: tuple[str, str], status: str) -> Draft202012Validator:
    """A validator for the JSON body the spec declares for `(method, path)` answering `status`."""
    method, path = operation
    body = JSON_SCHEMA_SPEC["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    return Draft202012Validator({**body, "components": JSON_SCHEMA_SPEC["components"]})


@pytest.mark.parametrize(("filename", "endpoint"), FIXTURES.items())
def test_fixture_matches_its_endpoints_response_schema(filename, endpoint):
    operation, status = endpoint
    validator = _response_validator(operation, status)
    problems = [
        f"{filename}{error.json_path[1:]}: {error.message}" for error in validator.iter_errors(load_mock(filename))
    ]
    assert not problems, "\n".join(problems)


def test_locality_list_fixture_has_rows():
    """An empty array would satisfy the schema and prove nothing downstream."""
    assert load_mock("localitieswithsalmonoids.json")


def test_locality_list_fixture_matches_the_locality_constants():
    """`conftest` hardcodes the locality numbers; the fixture is where they actually come from."""
    assert [row["localityNo"] for row in load_mock("localitieswithsalmonoids.json")] == ALL_LOCALITY_NOS


def test_the_two_weekly_fixtures_differ_where_they_should():
    """One reported week and one fallow week — the two shapes a consumer has to read."""
    reported = load_mock("locality_week_reported.json")["liceReport"]
    fallow = load_mock("locality_week_fallow.json")["liceReport"]
    assert reported["hasReported"] is True and reported["isFallow"] is False
    assert fallow["hasReported"] is False and fallow["isFallow"] is True
    assert reported["adultFemaleLice"]["average"] is not None
    assert fallow["adultFemaleLice"]["average"] is None
    assert load_mock("locality_week_reported.json")["liceTreatments"]["nonMedicinalTreatments"]
    assert not load_mock("locality_week_fallow.json")["liceTreatments"]["nonMedicinalTreatments"]


def test_the_summary_fixture_covers_the_three_shapes():
    """A reported week, a fallow week, and a week with a disease and a treatment category — in that order.

    The summary's `liceTreatments` is category names, not the detailed report's object of
    treatment lists; a fixture that carried the object would validate nothing about it.
    """
    reported, fallow, treated = load_mock("locality_week_summary.json")
    assert [row["locality"]["no"] for row in (reported, fallow, treated)] == [90001, 90002, 90003]
    assert reported["liceReport"]["hasReported"] is True and reported["liceReport"]["isFallow"] is False
    assert fallow["liceReport"]["hasReported"] is False and fallow["liceReport"]["isFallow"] is True
    assert fallow["liceReport"]["adultFemaleLice"]["average"] is None
    assert reported["diseases"] == [] and reported["liceTreatments"] == []
    assert treated["diseases"] == ["PANKREASSYKDOM"]
    assert treated["liceTreatments"] == ["IKKE_MEDIKAMENTELL"]
    assert all(row["isFiltered"] is True for row in (reported, fallow, treated)), "every row of a filtered request"


def test_no_fixture_carries_a_real_locality_number():
    """Locality numbers are invented, in a range the Aquaculture Register does not issue."""
    for path in sorted(MOCK_DIR.glob("*.json")):
        payload = json.loads(path.read_text())
        for number in _locality_numbers(payload):
            assert number in ALL_LOCALITY_NOS, (
                f"{path.name} carries locality number {number}, not one of the invented ones"
            )


def _locality_numbers(node: Any) -> list[int]:
    if isinstance(node, list):
        return [number for item in node for number in _locality_numbers(item)]
    if not isinstance(node, dict):
        return []
    found = [value for key, value in node.items() if key in ("localityNo", "no") and isinstance(value, int)]
    return found + [number for value in node.values() for number in _locality_numbers(value)]


def test_an_invented_field_fails_validation():
    """The tightening is what makes the check worth having; this is it working."""
    payload = load_mock("locality_week_reported.json")
    payload["liceReport"]["averageLice"] = 1.0
    problems = list(_response_validator(LOCALITY_WEEK, "200").iter_errors(payload))
    assert any("averageLice" in error.message for error in problems)
