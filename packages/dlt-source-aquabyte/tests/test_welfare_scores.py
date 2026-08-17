"""Tests for the welfare_scores resource.

welfare_scores is the resource the "stay true to the API" rule bites hardest on: the
API returns one record per pen and date with every welfare category nested inside it,
and that is exactly what must land. Unpivoting is the consumer's transform.
"""

import copy
import json

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_row_count,
    load_mock,
    query,
    run_source,
    serve,
)

RECORDS = load_mock("welfare_scores.json")["welfareScores"]


def test_welfare_scores_lands_one_row_per_pen_and_date(mock_rest_client):
    """Rows match raw API records — one per pen and date, not one per category."""
    mock_rest_client.paginate.side_effect = serve({"/welfareScores": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.welfare_scores.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, _ = run_source("test_welfare_scores", source, ["welfare_scores"])

    rows = query(pipeline, "SELECT date FROM welfare_scores ORDER BY date")
    assert [str(row[0]) for row in rows] == ["2026-01-15", "2026-01-16"]


def test_welfare_scores_keeps_the_nested_object_intact(mock_rest_client):
    """The nested welfareScores object lands as one JSON column, verbatim."""
    mock_rest_client.paginate.side_effect = serve({"/welfareScores": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.welfare_scores.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, _ = run_source("test_welfare_nested", source, ["welfare_scores"])

    rows = query(pipeline, "SELECT welfare_scores FROM welfare_scores WHERE date = '2026-01-15'")
    landed = json.loads(rows[0][0])
    assert landed == RECORDS[0]["welfareScores"], "the nested payload must survive untouched"
    assert landed["bodyWound"]["active"].keys() == {"1", "2", "3"}, "score bands keep the API's own keys"
    assert "healed" not in landed["snoutWound"], "the API sends `healed` for some categories only"

    # A category with no data is absent from the object rather than reported as null,
    # which is why the second record carries fewer categories than the first.
    second = json.loads(query(pipeline, "SELECT welfare_scores FROM welfare_scores WHERE date = '2026-01-16'")[0][0])
    assert "caudalFin" in landed and "caudalFin" not in second
    assert all(value is not None for value in landed.values()), "the API omits a category, it does not null it"


def test_welfare_scores_passes_through_an_unknown_category(mock_rest_client):
    """A category added to the API after this release lands untouched."""
    records = copy.deepcopy(RECORDS)
    records[0]["welfareScores"]["gillDamage"] = {
        "active": {"1": 0.07, "2": 0.02, "3": 0.0},
        "nothing": 0.91,
        "sampleSize": 200,
    }

    mock_rest_client.paginate.side_effect = serve({"/welfareScores": records})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.welfare_scores.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, load_info = run_source("test_welfare_new_category", source, ["welfare_scores"])

    assert load_info is not None
    rows = query(pipeline, "SELECT welfare_scores FROM welfare_scores WHERE date = '2026-01-15'")
    assert json.loads(rows[0][0])["gillDamage"]["active"]["1"] == 0.07


def test_welfare_scores_merges_on_pen_and_date(mock_rest_client):
    """Re-running the same window replaces rows rather than duplicating them."""
    mock_rest_client.paginate.side_effect = serve({"/welfareScores": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.welfare_scores.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline, _ = run_source("test_welfare_merge", source, ["welfare_scores"])

    mock_rest_client.paginate.side_effect = serve({"/welfareScores": RECORDS})
    rerun = aquabyte_source(**SOURCE_CONFIG)
    rerun.welfare_scores.bind(pen_id="pen-001", **DATE_RANGE)
    pipeline.run(rerun.with_resources("welfare_scores"))

    assert_row_count(pipeline, "welfare_scores", len(RECORDS))
