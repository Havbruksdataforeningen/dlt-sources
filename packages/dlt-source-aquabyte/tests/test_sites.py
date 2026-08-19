"""Tests for the sites resource."""

import json

import pytest
from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    assert_row_count,
    calls_to,
    load_mock,
    make_pipeline,
    params_sent,
    query,
    run_source,
)


def _pens_by_version(pipeline):
    """The pens nested on every site-001 row, oldest version first."""
    rows = query(pipeline, "SELECT pens FROM sites WHERE id = 'site-001' ORDER BY _dlt_valid_from")
    return [json.loads(row[0]) for row in rows]


def _load(pipeline, mock_rest_client, sites_list, site_id=None):
    """Load one page of sites into an existing pipeline, optionally as a targeted read."""
    mock_rest_client.paginate.return_value = iter([sites_list])
    source = aquabyte_source(**SOURCE_CONFIG)
    if site_id is not None:
        source.sites.bind(site_id=site_id)
    pipeline.run(source.with_resources("sites"))


def test_sites_resource_loads_into_duckdb(mock_rest_client):
    """Sites resource loads mock data into DuckDB with correct row count."""
    sites_list = load_mock("sites.json")["sites"]

    mock_rest_client.paginate.return_value = iter([sites_list])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source("test_sites", source, ["sites"])

    assert load_info is not None
    assert_row_count(pipeline, "sites", len(sites_list))
    assert params_sent(mock_rest_client, "/sites") == [{}]


def test_sites_reads_one_site_when_site_id_is_bound(mock_rest_client):
    """A bound site_id switches the path to the API's per-site endpoint, same table."""
    single_site = [load_mock("sites.json")["sites"][0]]

    mock_rest_client.paginate.return_value = iter([single_site])

    source = aquabyte_source(**SOURCE_CONFIG)
    source.sites.bind(site_id="site-001")
    pipeline, load_info = run_source("test_sites_by_id", source, ["sites"])

    assert load_info is not None
    assert_row_count(pipeline, "sites", 1)
    (call,) = calls_to(mock_rest_client, "/sites/site-001")
    assert call["params"] == {}
    assert call["data_selector"] == "sites"
    assert isinstance(call["paginator"], SinglePagePaginator)


def test_sites_is_not_cursor_paginated(mock_rest_client):
    """/sites returns no nextToken, so it is read as a single page."""
    mock_rest_client.paginate.return_value = iter([load_mock("sites.json")["sites"]])

    source = aquabyte_source(**SOURCE_CONFIG)
    run_source("test_sites_paginator", source, ["sites"])

    (call,) = calls_to(mock_rest_client, "/sites")
    assert isinstance(call["paginator"], SinglePagePaginator)


def test_sites_keeps_nested_pens_untouched(mock_rest_client):
    """Sites land as the API returns them: pens stay nested, as one JSON column."""
    sites_list = load_mock("sites.json")["sites"]

    mock_rest_client.paginate.return_value = iter([sites_list])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, _ = run_source("test_sites_nesting", source, ["sites"])

    with pipeline.sql_client() as client:
        rows = client.execute_sql("SELECT pens FROM sites WHERE id = 'site-001'")
        assert rows is not None
        assert '"pen-002"' in rows[0][0], "the inactive pen must survive in the raw payload"


def test_backfilling_one_site_leaves_the_other_sites_current(mock_rest_client):
    """`merge_key` scopes scd2 retirement: a targeted read must not retire the rest.

    Without it dlt retires every active row absent from the load, so reading one site
    would retire all the others — the hazard `replace` had, in softer form.
    """
    sites_list = load_mock("sites.json")["sites"]
    pipeline = make_pipeline("test_sites_scd2_partial")

    _load(pipeline, mock_rest_client, sites_list)
    _load(pipeline, mock_rest_client, [sites_list[0]], site_id="site-001")

    current = query(pipeline, "SELECT id FROM sites WHERE _dlt_valid_to IS NULL ORDER BY id")
    assert [row[0] for row in current] == ["site-001", "site-002"]


def test_a_changed_site_is_versioned_rather_than_overwritten(mock_rest_client):
    """A renamed site retires its old version and lands a new current one."""
    site = load_mock("sites.json")["sites"][0]
    pipeline = make_pipeline("test_sites_scd2_history")

    _load(pipeline, mock_rest_client, [site])
    _load(pipeline, mock_rest_client, [{**site, "name": "Nordfjord Farm AS"}])

    versions = query(
        pipeline,
        "SELECT name, _dlt_valid_to IS NULL FROM sites WHERE id = 'site-001' ORDER BY _dlt_valid_from",
    )
    assert versions == [("Nordfjord Farm", False), ("Nordfjord Farm AS", True)]


@pytest.mark.parametrize(("kind", "change"), [("renamed", {"name": "Renamed"}), ("deactivated", {"isActive": False})])
def test_a_changed_pen_versions_its_site(mock_rest_client, kind, change):
    """A site versions on its whole record, the nested pens included.

    dlt's default row hash covers nested data, so any pen change lands a new site
    version rather than leaving the site row — and its `pens` snapshot — behind. The
    site's own fields version it too, as they always did.
    """
    site = load_mock("sites.json")["sites"][0]
    pens = [{**pen, **change} if pen["id"] == "pen-001" else pen for pen in site["pens"]]
    pipeline = make_pipeline(f"test_sites_scd2_pen_{kind}")

    _load(pipeline, mock_rest_client, [site])
    _load(pipeline, mock_rest_client, [{**site, "pens": pens}])
    assert_row_count(pipeline, "sites", 2)

    _load(pipeline, mock_rest_client, [{**site, "pens": pens, "name": "Nordfjord Farm AS"}])
    assert_row_count(pipeline, "sites", 3)


def test_each_site_version_lists_the_pens_it_was_loaded_with(mock_rest_client):
    """The nested `pens` snapshot cannot go stale, on the current row or a retired one.

    A JSON column of pens invites unnesting, so it must not disagree with the `pens`
    table next to it. It used to: while a site versioned on its own fields only, the
    snapshot froze at whenever those fields last changed, which for a site is rarely.
    Reading a version's pens is only meaningful if they are the pens of that version.
    """
    site = load_mock("sites.json")["sites"][0]
    renamed = [{**pen, "name": "Renamed"} if pen["id"] == "pen-001" else pen for pen in site["pens"]]
    pipeline = make_pipeline("test_sites_scd2_nested_pens")

    _load(pipeline, mock_rest_client, [site])
    _load(pipeline, mock_rest_client, [{**site, "pens": renamed}])

    retired, current = _pens_by_version(pipeline)
    assert [pen["name"] for pen in current] == ["Renamed", "Pen B", "Pen C"]
    assert [pen["name"] for pen in retired] == ["Pen A", "Pen B", "Pen C"]


def test_a_pen_dropped_from_the_response_versions_its_site(mock_rest_client):
    """A pen emptied and gone from `/sites` retires the site version that still listed it.

    Only the site side is asserted here; that the pen itself survives in `pens` is
    `test_an_emptied_pen_survives_dropping_out_of_the_response`.
    """
    site = load_mock("sites.json")["sites"][0]
    remaining = [pen for pen in site["pens"] if pen["id"] != "pen-002"]
    pipeline = make_pipeline("test_sites_scd2_pen_dropped")

    _load(pipeline, mock_rest_client, [site])
    _load(pipeline, mock_rest_client, [{**site, "pens": remaining}])

    assert_row_count(pipeline, "sites", 2)
    _, current = _pens_by_version(pipeline)
    assert [pen["id"] for pen in current] == ["pen-001", "pen-003"]


def test_an_unchanged_site_does_not_grow_a_version(mock_rest_client):
    """Re-reading identical data is a no-op — scd2 versions on change, not on run."""
    site = load_mock("sites.json")["sites"][0]
    pipeline = make_pipeline("test_sites_scd2_idempotent")

    _load(pipeline, mock_rest_client, [site])
    _load(pipeline, mock_rest_client, [site])

    assert_row_count(pipeline, "sites", 1)


def test_a_consumer_can_override_the_nesting_default(mock_rest_client):
    """`max_table_nesting=0` is a default, not a lock: raising it gives child tables.

    No column hint names `pens`, so nothing outranks the setting: a hint on a nested
    field would win over it and silently ignore the consumer.
    """
    mock_rest_client.paginate.return_value = iter([load_mock("sites.json")["sites"]])

    source = aquabyte_source(**SOURCE_CONFIG)
    source.sites.max_table_nesting = 1
    pipeline, _ = run_source("test_sites_nesting_override", source, ["sites"])

    assert "sites__pens" in pipeline.default_schema.tables
