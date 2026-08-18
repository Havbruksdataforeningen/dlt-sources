"""The claims the live-comparison report makes about the OpenAPI document, asserted.

`specs/api-observations-2026-08-17.md` says things like "the schema marks these five
fields required" and sends them to Aquabyte as statements about *their* document. Those
sentences were checked by hand once. Refreshing `specs/openapi.json` could quietly make
any of them false, and nothing would notice — a report that misquotes the document it
is about is worse than no report.

So each claim is pinned here. A failure does not necessarily mean the code is wrong: it
means the document changed and the report needs re-reading before it is sent again.
"""

import json
import re
from pathlib import Path

SPEC = json.loads((Path(__file__).parent.parent / "specs" / "openapi.json").read_text())
SCHEMAS = SPEC["components"]["schemas"]

WINDOW_PARAMS = {"fromDate", "toDate", "fromTime", "toTime"}


def _is_nullable(schema: dict) -> bool:
    return any(branch.get("type") == "null" for branch in schema.get("anyOf", []))


def _optional_window_params():
    """Every optional date/time window parameter, as (path, name, schema)."""
    for path, operations in SPEC["paths"].items():
        for param in operations.get("get", {}).get("parameters", []):
            if param["name"] in WINDOW_PARAMS and not param.get("required"):
                yield path, param["name"], param["schema"]


def test_lice_count_marks_the_five_count_fields_required_and_nullable():
    """Report finding 1: required, yet the API omits them on a zero-sample record.

    Both halves matter. Required is what makes the omission a violation; nullable is
    what makes `null` an available fix that needs no schema change.
    """
    lice_count = SCHEMAS["LiceCount"]
    counts = ["adultFemale", "adultFemaleConverted", "mobile", "mobileConverted", "caligus"]
    for field in counts:
        assert field in lice_count["required"], f"{field} is no longer required"
        assert _is_nullable(lice_count["properties"][field]), f"{field} is no longer nullable"


def test_behaviour_endpoints_declare_their_timestamps_as_date_time():
    """Report finding 2: declared `date-time`, returned without a zone.

    `date-time` is what makes the missing offset a conformance break rather than a
    stylistic choice, so the declaration is the half worth pinning.
    """
    for schema_name in ("BehaviorSwimSpeed", "BehaviorBreathingIndex", "EnvironmentalDataPoint"):
        for field in ("fromTime", "toTime"):
            declared = SCHEMAS[schema_name]["properties"][field]
            assert declared == {"type": "string", "format": "date-time"}, (
                f"{schema_name}.{field} is no longer a plain date-time string: {declared}"
            )


def test_harvest_report_from_date_is_the_only_non_nullable_window_param():
    """Report finding 5: one parameter typed unlike every comparable one.

    The finding is a claim about *every other* window parameter, so it is asserted that
    way rather than by checking the odd one alone.
    """
    non_nullable = {(path, name) for path, name, schema in _optional_window_params() if not _is_nullable(schema)}
    assert non_nullable == {("/biomass/harvestReport", "fromDate")}, (
        f"The set of non-nullable optional window params has changed: {sorted(non_nullable)}"
    )


def test_the_document_still_says_nothing_about_result_ordering():
    """Report finding 4: ordering is undocumented.

    A claim of absence, so this is a heuristic rather than a proof — it looks for the
    words the document would plausibly use if Aquabyte documented ordering.
    """
    blob = json.dumps(SPEC).lower()
    found = [word for word in ("sorted", "sorting", "ordered", "ordering", "ascending", "descending") if word in blob]
    assert not found, f"The document may now describe result ordering ({found}); report finding 4 may be stale"


def test_the_external_identifiers_are_declared_nullable_strings():
    """Report findings 8 and 9: declared nullable, absent altogether from responses."""
    for schema_name, field in (("Site", "external_site_id"), ("Pen", "external_id")):
        declared = SCHEMAS[schema_name]["properties"][field]
        assert _is_nullable(declared), f"{schema_name}.{field} is no longer declared nullable"


def test_the_document_describes_the_record_cap_and_next_token():
    """Report finding 7: pagination is documented but was never triggered."""
    description = SPEC["info"]["description"]
    assert re.search(r"10[,.]?000", description), "The documented record cap has moved or gone"
    assert "nextToken" in description, "The document no longer describes nextToken pagination"
