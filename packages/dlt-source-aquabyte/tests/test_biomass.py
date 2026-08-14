"""Tests for the biomass resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    params_sent,
    run_source,
    serve,
)

RECORDS = load_mock("biomass.json")["biomass"]


def test_biomass_loads_into_duckdb(mock_rest_client):
    """Biomass resource loads mock data into DuckDB for a single pen."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, load_info = run_source("test_biomass", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(RECORDS))
    assert_pen_ids(pipeline, "biomass", ["pen-001"])


def test_biomass_defaults_to_all_pens(mock_rest_client):
    """Biomass resource fetches every pen with a single penId=all request by default."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(**DATE_RANGE)
    pipeline, load_info = run_source("test_biomass_all_pens", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(RECORDS) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "biomass", ACTIVE_PEN_IDS)


def test_biomass_from_date_always_present(mock_rest_client):
    """fromDate is always sent — from the explicit param or, failing that, the cursor."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    _, load_info = run_source("test_biomass_from_date", source, ["biomass"])

    assert load_info is not None
    assert params_sent(mock_rest_client, "/biomass") == [{"penId": "all", "fromDate": SOURCE_CONFIG["initial_date"]}]


def test_biomass_sends_bucket_size(mock_rest_client):
    """bucketSize is a biomass query param and is only sent when asked for."""
    mock_rest_client.paginate.side_effect = serve({"/biomass": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.biomass.bind(bucket_size=500, **DATE_RANGE)
    run_source("test_biomass_bucket_size", source, ["biomass"])

    assert params_sent(mock_rest_client, "/biomass")[0]["bucketSize"] == 500
