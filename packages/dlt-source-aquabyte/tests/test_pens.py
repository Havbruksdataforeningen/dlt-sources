"""Tests for the pens transformer."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ALL_PEN_IDS,
    SOURCE_CONFIG,
    assert_row_count,
    load_mock,
    query,
    run_source,
)


def _run_pens(mock_rest_client, pipeline_name: str):
    """Load the sites mock and run sites + pens, returning the pipeline."""
    mock_rest_client.paginate.return_value = iter([load_mock("sites.json")["sites"]])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source(pipeline_name, source, ["sites", "pens"])
    assert load_info is not None
    return pipeline


def test_pens_yields_every_pen(mock_rest_client):
    """The transformer unwraps every nested pen — active and inactive alike."""
    pipeline = _run_pens(mock_rest_client, "test_pens_all")

    assert_row_count(pipeline, "pens", len(ALL_PEN_IDS))
    rows = query(pipeline, "SELECT id FROM pens ORDER BY id")
    assert sorted(row[0] for row in rows) == sorted(ALL_PEN_IDS)


def test_pens_keeps_api_fields_verbatim(mock_rest_client):
    """A pen row carries the API's own fields, with nothing added or renamed."""
    pipeline = _run_pens(mock_rest_client, "test_pens_fields")

    rows = query(pipeline, "SELECT name, pen_code, is_active, external_id FROM pens WHERE id = 'pen-002'")
    assert rows[0] == ("Pen B", "PB", False, None)
