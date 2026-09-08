"""The `localities_with_salmonoids` resource: the salmonoid locality list, whole or filtered by `locality_nos`.

Named after its endpoint, `GET /v1/geodata/fishhealth/localitieswithsalmonoids`, to tell it
from `localities`, the full register list. This is the list `locality_week` iterates over.

Errors raised inside a resource reach the caller wrapped in dlt's `ResourceExtractionError`;
the assertions look through it at `__cause__`, which is what the source actually raised.
"""

import logging

import pytest
from dlt.extract.exceptions import ResourceExtractionError

from tests.conftest import ALL_LOCALITY_NOS, LOCALITIES_URL, http_status, load_mock, make_source

LOGGER = "dlt_source_barentswatch_fishhealth.barentswatch_fishhealth"


def test_discovery_yields_the_apis_rows_as_is(mock_api):
    """Every locality the API lists, with exactly the fields the API sent."""
    mock_api.localities()

    assert list(make_source().localities_with_salmonoids) == load_mock("localitieswithsalmonoids.json")
    assert mock_api.urls_requested() == [LOCALITIES_URL]


def test_locality_nos_filters_and_keeps_the_apis_fields(mock_api):
    """A filtered load still fetches the list, so the rows are the API's, not stubs."""
    mock_api.localities()

    rows = list(make_source(locality_nos=[90002, 90004]).localities_with_salmonoids)

    assert rows == [{"localityNo": 90002, "name": "Prøvevika"}, {"localityNo": 90004, "name": "Eksempelbukta"}]
    assert len(mock_api.urls_requested()) == 1


def test_unknown_locality_no_is_warned_about_and_skipped(mock_api, caplog):
    """A number that is not a salmonoid locality is dropped with a warning, not sent to the weekly endpoint.

    The weekly endpoint answers 400 for an unknown number — the same 400 it gives a week
    with no report — so the warning is the only place a typo would show.
    """
    mock_api.localities()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        rows = list(make_source(locality_nos=[90001, 12345, 90003, 67890]).localities_with_salmonoids)

    assert [row["localityNo"] for row in rows] == [90001, 90003]
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "[12345, 67890]" in warnings[0].getMessage()


def test_known_locality_nos_do_not_warn(mock_api, caplog):
    mock_api.localities()

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        list(make_source(locality_nos=ALL_LOCALITY_NOS).localities_with_salmonoids)

    assert not [record for record in caplog.records if record.name == LOGGER]


def test_all_unknown_locality_nos_raises(mock_api):
    """No locality means no weekly requests: a 0-row load is refused rather than loaded."""
    mock_api.localities()

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(locality_nos=[12345, 67890]).localities_with_salmonoids)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "None of the requested locality_nos" in str(excinfo.value.__cause__)


def test_empty_locality_nos_raises_before_any_request(mock_api):
    """An empty list is a mistake, not "every locality" — that is what `None` means."""
    mock_api.localities()

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source(locality_nos=[]).localities_with_salmonoids)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "empty list" in str(excinfo.value.__cause__)
    assert mock_api.requests == []


@pytest.mark.parametrize("status_code", [400, 404, 503])
def test_non_200_raises(mock_api, status_code):
    """The locality list has no "no data" answer; anything but 200 is an error."""
    mock_api.localities(status_code=status_code, json={"title": "Error", "status": status_code})

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities_with_salmonoids)

    assert http_status(excinfo.value.__cause__) == status_code


def test_empty_array_raises(mock_api):
    """An API that lists no salmonoid localities is broken, and a `replace` load of 0 rows would erase the table."""
    mock_api.localities(rows=[])

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities_with_salmonoids)

    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "no localities" in str(excinfo.value.__cause__)


@pytest.mark.parametrize(
    "body",
    [
        {"localities": [{"localityNo": 90001, "name": "Testholmen"}]},
        [{"name": "Testholmen"}],
        [90001, 90002],
        "not json at all",
    ],
    ids=["object-envelope", "no-localityNo", "bare-numbers", "text"],
)
def test_non_array_body_raises(mock_api, body):
    """A 200 whose body is not an array of `{localityNo, ...}` is malformed, not "no data"."""
    if isinstance(body, str):
        mock_api.localities(text=body)
    else:
        mock_api.localities(json=body)

    with pytest.raises(ResourceExtractionError) as excinfo:
        list(make_source().localities_with_salmonoids)

    # `requests.JSONDecodeError` is a `ValueError` too, so the text case lands here as well.
    assert isinstance(excinfo.value.__cause__, ValueError)
