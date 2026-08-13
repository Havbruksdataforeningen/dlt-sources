"""Tests for the welfare scores standalone resource."""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    ACTIVE_PEN_IDS,
    DATE_RANGE,
    SOURCE_CONFIG,
    assert_all_active_pens,
    assert_pen_ids,
    load_mock,
    make_per_pen_data,
    run_source,
)


def test_welfare_scores_loads_into_duckdb(mock_rest_client):
    """Welfare scores resource unpivots and loads mock data into DuckDB with correct row count."""
    welfare_data = load_mock("welfare_scores.json")["welfareScores"]
    pen_id = "pen-001"

    # Count expected rows: non-null categories per record
    # Record 1 (2026-01-15): bodyWound, scaleLoss, snoutWound, maturation, opercularDamage, dorsalFin = 6
    # Record 2 (2026-01-16): bodyWound, scaleLoss = 2
    expected_rows = 8

    def paginate_side_effect(url: str, **kwargs):
        if url == "/welfareScores":
            params = kwargs.get("params", {})
            if params.get("penId") == pen_id:
                return iter([make_per_pen_data(welfare_data, pen_id)])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=[pen_id], **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_welfare_scores", source, ["welfare_scores"])

    assert load_info is not None

    with pipeline.sql_client() as client:
        result = client.execute_sql("SELECT COUNT(*) FROM welfare_scores")
        assert result is not None
        assert result[0][0] == expected_rows, f"Expected {expected_rows} rows, got {result[0][0]}"

    assert_pen_ids(pipeline, "welfare_scores", [pen_id])

    with pipeline.sql_client() as client:
        # Verify categories are correct for first date
        result = client.execute_sql("SELECT category FROM welfare_scores WHERE date = '2026-01-15' ORDER BY category")
        assert result is not None
        categories = [row[0] for row in result]
        assert categories == ["bodyWound", "dorsalFin", "maturation", "opercularDamage", "scaleLoss", "snoutWound"]

        # Verify healed scores are null for categories without healed data
        result = client.execute_sql(
            "SELECT healed_score1 FROM welfare_scores WHERE date = '2026-01-15' AND category = 'snoutWound'"
        )
        assert result is not None
        assert result[0][0] is None

        # Verify active scores are populated
        result = client.execute_sql(
            "SELECT active_score1, active_score2, active_score3 FROM welfare_scores "
            "WHERE date = '2026-01-15' AND category = 'bodyWound'"
        )
        assert result is not None
        assert result[0] == (0.05, 0.02, 0.01)


def test_welfare_scores_pen_id_all(mock_rest_client):
    """welfare_scores with penId=all returns data for all active pens."""
    welfare_data = load_mock("welfare_scores.json")["welfareScores"]

    def paginate_side_effect(url: str, **kwargs):
        if url == "/welfareScores":
            params = kwargs.get("params", {})
            if params.get("penId") == "all":
                all_records: list[dict] = []
                for pid in ACTIVE_PEN_IDS:
                    all_records.extend(make_per_pen_data(welfare_data, pid))
                return iter([all_records])
        return iter([])

    mock_rest_client.paginate.side_effect = paginate_side_effect

    source = aquabyte_source(pen_ids=None, **DATE_RANGE, **SOURCE_CONFIG)
    pipeline, load_info = run_source("test_welfare_scores_all", source, ["welfare_scores"])

    assert load_info is not None
    assert_all_active_pens(pipeline, "welfare_scores")
