"""Tests for the pens transformer."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ALL_PEN_IDS,
    SOURCE_CONFIG,
    assert_row_count,
    load_mock,
    make_pipeline,
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


def _load(pipeline, mock_rest_client, sites_list):
    """Load one page of sites into an existing pipeline, running sites + pens."""
    mock_rest_client.paginate.return_value = iter([sites_list])
    pipeline.run(aquabyte_source(**SOURCE_CONFIG).with_resources("sites", "pens"))


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


def test_an_emptied_pen_survives_dropping_out_of_the_response(mock_rest_client):
    """A pen leaves `/sites` once it is emptied; its history has to outlive it.

    This is the reason `pens` is versioned rather than replaced.
    """
    sites_list = load_mock("sites.json")["sites"]
    emptied = [{**site, "pens": [pen for pen in site["pens"] if pen["id"] != "pen-002"]} for site in sites_list]
    pipeline = make_pipeline("test_pens_scd2_emptied")

    _load(pipeline, mock_rest_client, sites_list)
    _load(pipeline, mock_rest_client, emptied)

    rows = query(pipeline, "SELECT name FROM pens WHERE id = 'pen-002'")
    assert [row[0] for row in rows] == ["Pen B"], "the emptied pen must still be in the table"
    assert_row_count(pipeline, "pens", len(ALL_PEN_IDS))


def test_a_pen_going_inactive_is_a_new_version(mock_rest_client):
    """`isActive` flipping lands a new version instead of overwriting the old one."""
    sites_list = load_mock("sites.json")["sites"]
    deactivated = [
        {**site, "pens": [{**pen, "isActive": False} if pen["id"] == "pen-001" else pen for pen in site["pens"]]}
        for site in sites_list
    ]
    pipeline = make_pipeline("test_pens_scd2_inactive")

    _load(pipeline, mock_rest_client, sites_list)
    _load(pipeline, mock_rest_client, deactivated)

    versions = query(
        pipeline,
        "SELECT is_active, _dlt_valid_to IS NULL FROM pens WHERE id = 'pen-001' ORDER BY _dlt_valid_from",
    )
    assert versions == [(True, False), (False, True)]
