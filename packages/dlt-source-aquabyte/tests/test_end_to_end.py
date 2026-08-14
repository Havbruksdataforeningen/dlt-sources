"""End-to-end test: every resource of aquabyte_source, one pipeline run."""

import dlt

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    ALL_PEN_IDS,
    SOURCE_CONFIG,
    assert_all_active_pens,
    assert_row_count,
    load_mock,
    query,
    serve,
)

ROUTES = {
    "/environmental": load_mock("environmental.json")["data"],
    "/biomass": load_mock("biomass.json")["biomass"],
    "/biomass/harvestReport": load_mock("harvest_report.json")["reports"],
    "/liceCount": load_mock("lice_count.json")["liceCount"],
    "/behaviour/swimSpeed": load_mock("swim_speed.json")["swimSpeed"],
    "/behaviour/breathingIndex": load_mock("breathing_index.json")["breathingIndex"],
    "/welfareScores": load_mock("welfare_scores.json")["welfareScores"],
}

PEN_TABLES = [
    "biomass",
    "environmental",
    "harvest_report",
    "lice_count",
    "behaviour_swim_speed",
    "behaviour_breathing_index",
    "welfare_scores",
]


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

    pipeline = dlt.pipeline(
        pipeline_name="test_e2e",
        destination="duckdb",
        dataset_name="test_e2e_data",
        dev_mode=True,
    )

    load_info = pipeline.run(aquabyte_source(**SOURCE_CONFIG))
    assert load_info is not None

    assert_row_count(pipeline, "sites", 2)
    assert_row_count(pipeline, "pens", len(ALL_PEN_IDS))

    rows = query(pipeline, "SELECT id FROM pens ORDER BY id")
    assert sorted(row[0] for row in rows) == sorted(ALL_PEN_IDS)

    for table in PEN_TABLES:
        assert_all_active_pens(pipeline, table)


def test_end_to_end_rerun_is_idempotent(mock_rest_client):
    """Running the same window twice merges on the primary keys instead of duplicating."""
    mock_rest_client.paginate.side_effect = serve(ROUTES)

    pipeline = dlt.pipeline(
        pipeline_name="test_e2e_rerun",
        destination="duckdb",
        dataset_name="test_e2e_rerun_data",
        dev_mode=True,
    )

    for _ in range(2):
        mock_rest_client.paginate.side_effect = serve(ROUTES)
        pipeline.run(aquabyte_source(**SOURCE_CONFIG).with_resources(*PEN_TABLES))

    expected = {
        "biomass": len(ROUTES["/biomass"]),
        "environmental": len(ROUTES["/environmental"]),
        "harvest_report": len(ROUTES["/biomass/harvestReport"]),
        "lice_count": len(ROUTES["/liceCount"]),
        "behaviour_swim_speed": len(ROUTES["/behaviour/swimSpeed"]),
        "behaviour_breathing_index": len(ROUTES["/behaviour/breathingIndex"]),
        "welfare_scores": len(ROUTES["/welfareScores"]),
    }
    for table, per_pen_rows in expected.items():
        assert_row_count(pipeline, table, per_pen_rows * len(ACTIVE_PEN_IDS))
