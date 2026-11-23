"""Tests for the welfare_scores resource.

welfare_scores is the resource the "stay true to the API" rule bites hardest on: the
API returns one record per pen and date with every welfare category nested inside it,
and that is exactly what must land. Unpivoting is the consumer's transform.
"""

import copy
import json

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
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
    source.welfare_scores.bind(pen_id="pen-001")
    pipeline, _ = run_source("test_welfare_scores", source, ["welfare_scores"])

    rows = query(pipeline, "SELECT date FROM welfare_scores ORDER BY date")
    assert [str(row[0]) for row in rows] == ["2026-01-15", "2026-01-16"]


def test_welfare_scores_keeps_the_nested_object_intact(mock_rest_client):
    """The nested welfareScores object lands as one JSON column, verbatim."""
    mock_rest_client.paginate.side_effect = serve({"/welfareScores": RECORDS})

    source = aquabyte_source(**SOURCE_CONFIG)
    source.welfare_scores.bind(pen_id="pen-001")
    pipeline, _ = run_source("test_welfare_nested", source, ["welfare_scores"])

    rows = query(pipeline, "SELECT welfare_scores FROM welfare_scores ORDER BY date")
    assert [json.loads(row[0]) for row in rows] == [record["welfareScores"] for record in RECORDS]


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
    source.welfare_scores.bind(pen_id="pen-001")
    pipeline, _ = run_source("test_welfare_new_category", source, ["welfare_scores"])

    rows = query(pipeline, "SELECT welfare_scores FROM welfare_scores WHERE date = '2026-01-15'")
    assert json.loads(rows[0][0])["gillDamage"]["active"]["1"] == 0.07
