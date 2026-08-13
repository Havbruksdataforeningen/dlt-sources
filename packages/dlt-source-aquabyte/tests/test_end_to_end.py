"""End-to-end test validating multi-pen data flow through aquabyte_source."""

import dlt

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    ALL_PEN_IDS,
    DATE_RANGE,
    INACTIVE_PEN_ID,
    SOURCE_CONFIG,
    TIME_RANGE,
    assert_all_active_pens,
    assert_row_count,
    load_mock,
    make_per_pen_data,
)


def _build_paginate_side_effect(
    sites_data: list[dict],
    environmental_latest_data: list[dict],
    bulk_endpoints: dict[str, list[dict]],
):
    """Build a side_effect function for client.paginate that routes by URL.

    Args:
        sites_data: Response data for /sites endpoint.
        environmental_latest_data: Response data for /environmental/latest.
        bulk_endpoints: Mapping of URL path → template records for penId=all endpoints.
    """

    def paginate(url: str, **kwargs):
        if url == "/sites":
            return iter([sites_data])
        if url == "/environmental/latest":
            return iter([environmental_latest_data])

        # All bulk endpoints use penId=all
        if url in bulk_endpoints:
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pen_id in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(bulk_endpoints[url], pen_id))
                return iter([all_records])

        return iter([])

    return paginate


def test_end_to_end_multi_pen(mock_rest_client):
    """Full aquabyte_source pipeline loads data for all 4 active pens into DuckDB."""
    paginate_side_effect = _build_paginate_side_effect(
        sites_data=load_mock("sites.json")["sites"],
        environmental_latest_data=load_mock("environmental_latest.json")["data"],
        bulk_endpoints={
            "/environmental": load_mock("environmental.json")["data"],
            "/biomass": load_mock("biomass.json")["biomass"],
            "/biomass/harvestReport": load_mock("harvest_report.json")["reports"],
            "/liceCount": load_mock("lice_count.json")["liceCount"],
            "/behaviour/swimSpeed": load_mock("swim_speed.json")["swimSpeed"],
            "/behaviour/breathingIndex": load_mock("breathing_index.json")["breathingIndex"],
            "/welfareScores": load_mock("welfare_scores.json")["welfareScores"],
        },
    )

    mock_rest_client.paginate.side_effect = paginate_side_effect

    pipeline = dlt.pipeline(
        pipeline_name="test_e2e",
        destination="duckdb",
        dataset_name="test_e2e_data",
        dev_mode=True,
    )

    source = aquabyte_source(
        pen_ids=None,
        **DATE_RANGE,
        **TIME_RANGE,
        **SOURCE_CONFIG,
    )

    load_info = pipeline.run(source)

    assert load_info is not None

    # Sites: 2 sites
    assert_row_count(pipeline, "sites", 2)

    # Pens: all 5 pens (active and inactive)
    assert_row_count(pipeline, "pens", 5)

    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT id FROM pens ORDER BY id")
        assert result is not None
        pens_ids = sorted(row[0] for row in result)
        assert pens_ids == sorted(ALL_PEN_IDS)

    # All per-pen tables have data for all 4 active pens
    data_tables = [
        "biomass",
        "environmental",
        "harvest_report",
        "lice_count",
        "behaviour_swim_speed",
        "behaviour_breathing_index",
        "welfare_scores",
    ]
    for table in data_tables:
        assert_all_active_pens(pipeline, table)

    # Inactive pen has no data in any per-pen table
    with pipeline.sql_client() as client:
        for table in data_tables:
            result = client.execute_sql(f"SELECT COUNT(*) FROM {table} WHERE pen_id = '{INACTIVE_PEN_ID}'")
            assert result is not None
            assert result[0][0] == 0, f"Inactive {INACTIVE_PEN_ID} should have no data in {table}"
