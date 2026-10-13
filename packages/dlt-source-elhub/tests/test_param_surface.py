"""Every named param a resource takes is a query param the OpenAPI document lists for its endpoint."""

import re
from pathlib import Path

import pytest

from tests.conftest import resource_signature, source

SPEC = Path(__file__).parent.parent / "specs" / "openapi.yaml"

NOT_QUERY_PARAMS = {"params", "metering_point_ids", "metering_point", "meta"}
"""The escape hatch, the id filter, the transformer's item, and the `meta` argument dlt adds to every transformer."""


def _documented_query_params(path: str) -> set[str]:
    text = SPEC.read_text()
    start = text.index(f"\n  {path}:\n")
    end = text.find("\n  /", start + 1)
    section = text[start : end if end > 0 else None]
    names = re.findall(r"- name: (\w[\w-]*)\n\s+in: query", section)
    return set(names)


def _snake(name: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), name)


@pytest.mark.parametrize(
    ("resource", "path"),
    [
        ("metering_points", "/energy-data/v0/metering-points"),
        ("metering_values_hour", "/energy-data/v0/metering-points/{id}"),
    ],
)
def test_named_params_are_the_endpoints_own(resource: str, path: str):
    documented = {_snake(name) for name in _documented_query_params(path)}
    assert documented, f"no query params found for {path} in {SPEC.name}"

    named = set(resource_signature(source(), resource).parameters) - NOT_QUERY_PARAMS
    assert named <= documented, f"{resource} takes {named - documented}, which {path} does not document"
