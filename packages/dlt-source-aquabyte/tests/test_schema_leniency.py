"""The column hints type the known columns without the source rejecting what it does not know."""

import copy

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    assert_row_count,
    load_mock,
    query,
    run_source,
    serve,
)


def test_unknown_field_lands_in_the_destination(mock_rest_client):
    """A field the API adds after this release is loaded, not rejected."""
    records = copy.deepcopy(load_mock("lice_count.json")["liceCount"])
    for record in records:
        record["adultMale"] = 0.25

    mock_rest_client.paginate.side_effect = serve({"/liceCount": records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.lice_count.bind(pen_id="pen-001")
    pipeline, load_info = run_source("test_leniency_extra_field", source, ["lice_count"])

    assert load_info is not None
    assert_row_count(pipeline, "lice_count", len(records))
    rows = query(pipeline, "SELECT DISTINCT adult_male FROM lice_count")
    assert [row[0] for row in rows] == [0.25]


def test_known_fields_keep_their_types(mock_rest_client):
    """A column of nulls is typed by its hint, not guessed at from the data."""
    records = copy.deepcopy(load_mock("biomass.json")["biomass"])
    for record in records:
        record["kFactor"] = None

    mock_rest_client.paginate.side_effect = serve({"/biomass": records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(pen_id="pen-001")
    pipeline, _ = run_source("test_leniency_types", source, ["biomass"])

    rows = query(pipeline, "SELECT data_type FROM information_schema.columns WHERE column_name = 'k_factor'")
    assert rows[0][0] == "DOUBLE"


def test_missing_nullable_field_does_not_fail_the_load(mock_rest_client):
    """A nullable field the API stops sending is absent, not fatal."""
    records = copy.deepcopy(load_mock("biomass.json")["biomass"])
    for record in records:
        del record["cv"]

    mock_rest_client.paginate.side_effect = serve({"/biomass": records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(pen_id="pen-001")
    pipeline, load_info = run_source("test_leniency_missing_field", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(records))
