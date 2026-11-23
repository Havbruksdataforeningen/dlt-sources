"""End-to-end test: every resource of aquabyte_source, one pipeline run."""

import json

import dlt

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    ALL_PEN_IDS,
    SOURCE_CONFIG,
    WINDOWED_ENDPOINTS,
    assert_all_active_pens,
    assert_row_count,
    load_mock,
    make_pipeline,
    query,
    serve,
)

ROUTES = {endpoint.path: endpoint.records for endpoint in WINDOWED_ENDPOINTS}
PEN_TABLES = [endpoint.resource for endpoint in WINDOWED_ENDPOINTS]


def test_end_to_end_all_resources(mock_rest_client):
    """A default run loads every resource for every pen the API reports."""
    routes = {
        **ROUTES,
        "/sites": load_mock("sites.json")["sites"],
        "/environmental/latest": load_mock("environmental_latest.json")["data"],
    }

    def paginate(url, **kwargs):
        if url in ("/sites", "/environmental/latest"):
            return iter([routes[url]])
        return serve(ROUTES)(url, **kwargs)

    mock_rest_client.paginate.side_effect = paginate

    pipeline = make_pipeline("test_e2e")
    pipeline.run(aquabyte_source(**SOURCE_CONFIG))

    assert_row_count(pipeline, "sites", 2)

    # No pen is filtered on the way in: every pen the fixture holds is on a current site row.
    rows = query(pipeline, "SELECT pens FROM sites WHERE _dlt_valid_to IS NULL")
    loaded = [pen["id"] for row in rows for pen in json.loads(row[0])]
    assert sorted(loaded) == sorted(ALL_PEN_IDS)

    for table in PEN_TABLES:
        assert_all_active_pens(pipeline, table)


def test_end_to_end_rerun_is_idempotent(mock_rest_client):
    """Loading the same window twice merges on the primary keys instead of duplicating.

    The second run is a backfill of that window. Run from the stored cursor instead, its
    rows would be dropped as already seen and never reach the merge.
    """
    mock_rest_client.paginate.side_effect = serve(ROUTES)
    pipeline = make_pipeline("test_e2e_rerun")

    pipeline.run(aquabyte_source(**SOURCE_CONFIG).with_resources(*PEN_TABLES))

    backfill = aquabyte_source(**SOURCE_CONFIG)
    for endpoint in WINDOWED_ENDPOINTS:
        start, end = endpoint.cursor.window
        window = dlt.sources.incremental(initial_value=start, end_value=end)
        backfill.resources[endpoint.resource].bind(**{endpoint.incremental_argument: window})
    pipeline.run(backfill.with_resources(*PEN_TABLES))

    for endpoint in WINDOWED_ENDPOINTS:
        assert_row_count(pipeline, endpoint.resource, len(endpoint.records) * len(ACTIVE_PEN_IDS))
