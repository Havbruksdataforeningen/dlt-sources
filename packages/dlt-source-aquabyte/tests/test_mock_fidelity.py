"""Every committed fixture validates against the model its resource loads with.

The fixtures are hand-written (see `mock_responses/README.md`), so nothing otherwise
stops one drifting into a shape the API could not produce — and because they are the
input to almost every other test, a wrong shape here is a shape the whole offline suite
is blind to. This is the cheap guard: if a record does not satisfy its own model, the
fixture is wrong.
"""

import json

import pytest
from pydantic import BaseModel, ValidationError

from dlt_source_aquabyte.schemas import (
    BehaviorBreathingIndex,
    BehaviorSwimSpeed,
    BiomassDailyModel,
    BiomassHarvestReport,
    EnvironmentalDataLive,
    EnvironmentalDataPoint,
    LiceCount,
    Pen,
    Site,
    WelfareScoresRecord,
)
from tests.conftest import ALL_PEN_IDS, MOCK_DIR, load_mock

# fixture file -> (envelope key, model). `sites` is checked separately: its pens are
# nested, and the `pens` transformer loads them with their own model.
FIXTURES = {
    "environmental.json": ("data", EnvironmentalDataPoint),
    "environmental_latest.json": ("data", EnvironmentalDataLive),
    "biomass.json": ("biomass", BiomassDailyModel),
    "harvest_report.json": ("reports", BiomassHarvestReport),
    "lice_count.json": ("liceCount", LiceCount),
    "swim_speed.json": ("swimSpeed", BehaviorSwimSpeed),
    "breathing_index.json": ("breathingIndex", BehaviorBreathingIndex),
    "welfare_scores.json": ("welfareScores", WelfareScoresRecord),
}


def _validate(records: list[dict], model: type[BaseModel], where: str) -> None:
    for index, record in enumerate(records):
        try:
            model.model_validate(record)
        except ValidationError as invalid:
            pytest.fail(f"{where} record {index} does not satisfy {model.__name__}:\n{invalid}")


@pytest.mark.parametrize(("filename", "spec"), FIXTURES.items())
def test_fixture_records_satisfy_their_model(filename, spec):
    envelope_key, model = spec
    records = load_mock(filename)[envelope_key]
    assert records, f"{filename} has no records"
    _validate(records, model, filename)


def test_sites_fixture_satisfies_the_site_and_pen_models():
    """`sites.json` feeds two resources, so both models have to accept it."""
    sites = load_mock("sites.json")["sites"]
    _validate(sites, Site, "sites.json")
    _validate([pen for site in sites for pen in site["pens"]], Pen, "sites.json pens")


def test_sites_fixture_matches_the_pen_constants():
    """`conftest` hardcodes the pen ids; the fixture is where they actually come from."""
    sites = load_mock("sites.json")["sites"]
    pens = [pen for site in sites for pen in site["pens"]]
    assert sorted(pen["id"] for pen in pens) == sorted(ALL_PEN_IDS)


def test_no_fixture_carries_an_external_identifier():
    """The API declares `external_site_id` and `external_id` but returns neither.

    They were invented in an earlier fixture, which made the suite assert a shape the
    API has never produced. If Aquabyte starts sending them, delete this test and
    re-record — do not add them back by hand.
    """
    for path in sorted(MOCK_DIR.glob("*.json")):
        payload = json.dumps(json.loads(path.read_text()))
        for field in ("external_site_id", "external_id"):
            assert field not in payload, f"{path.name} carries {field}, which the API does not return"
