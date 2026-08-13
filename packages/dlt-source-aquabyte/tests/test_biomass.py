"""Tests for the biomass resource (v3.1 standalone with penId=all)."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_pen_ids,
    assert_row_count,
    load_mock,
    make_per_pen_data,
    run_source,
)


def test_biomass_loads_into_duckdb(mock_rest_client):
    """Biomass resource loads mock data into DuckDB standalone (no sites/pens dependency)."""
    biomass_records = load_mock("biomass.json")["biomass"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/biomass":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(biomass_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_biomass", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(biomass_records))
    assert_pen_ids(pipeline, "biomass", [pen_id])


def test_biomass_pen_id_all(mock_rest_client):
    """Biomass resource fetches data for all pens when pen_ids is None."""
    biomass_records = load_mock("biomass.json")["biomass"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/biomass":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(biomass_records, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(**DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_biomass_all_pens", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(biomass_records) * len(ACTIVE_PEN_IDS))
    assert_pen_ids(pipeline, "biomass", ACTIVE_PEN_IDS)


def test_biomass_from_date_always_present(mock_rest_client):
    """Biomass resource always includes fromDate in params (required in v3.1)."""
    biomass_records = load_mock("biomass.json")["biomass"]
    pen_id = "pen-001"

    def paginate_side_effect(url: str, **kwargs):
        if url == "/biomass":
            params = kwargs.get("params", {})
            # Verify fromDate is present
            assert "fromDate" in params, "fromDate must always be in params for v3.1"
            return iter([make_per_pen_data(biomass_records, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_biomass_from_date", source, ["biomass"])

    assert load_info is not None
    assert_row_count(pipeline, "biomass", len(biomass_records))
