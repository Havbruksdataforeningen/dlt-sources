"""Tests for the sites resource."""

from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    assert_row_count,
    calls_to,
    load_mock,
    params_sent,
    run_source,
)


def test_sites_resource_loads_into_duckdb(mock_rest_client):
    """Sites resource loads mock data into DuckDB with correct row count."""
    sites_list = load_mock("sites.json")["sites"]

    mock_rest_client.paginate.return_value = iter([sites_list])

    source = aquabyte_source(**SOURCE_CONFIG)
    pipeline, load_info = run_source("test_sites", source, ["sites"])

    assert load_info is not None
    assert_row_count(pipeline, "sites", len(sites_list))
    assert params_sent(mock_rest_client, "/sites") == [{}]


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


def test_a_consumer_can_override_the_nesting_default(mock_rest_client):
    """`max_table_nesting=0` is a default, not a lock: raising it gives child tables.

    The models must therefore not declare nested fields — a column hint would win over
    the setting and silently ignore the consumer.
    """
    mock_rest_client.paginate.return_value = iter([load_mock("sites.json")["sites"]])

    source = aquabyte_source(**SOURCE_CONFIG)
    source.sites.max_table_nesting = 1
    pipeline, _ = run_source("test_sites_nesting_override", source, ["sites"])

    assert "sites__pens" in pipeline.default_schema.tables
