"""Shared fixtures and helpers for Aquabyte pipeline tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import dlt
import pytest

MOCK_DIR = Path(__file__).parent / "mock_responses"

ACTIVE_PEN_IDS = ["pen-001", "pen-003", "pen-004", "pen-005"]
INACTIVE_PEN_ID = "pen-002"
ALL_PEN_IDS = ["pen-001", "pen-002", "pen-003", "pen-004", "pen-005"]

SOURCE_CONFIG: dict[str, Any] = {
    "environmental_period": "D",
    "behavior_period": "D",
    "initial_date": "2020-01-01",
    "initial_time": "2020-01-01T00:00:00Z",
    "base_url": "https://test.api/v3/",
    "api_key": "test-key",
}

DATE_RANGE = {"from_date": "2026-01-01", "to_date": "2026-01-31"}
TIME_RANGE = {"from_time": "2026-01-01T00:00:00Z", "to_time": "2026-01-31T00:00:00Z"}


def load_mock(filename: str) -> dict:
    """Load a JSON mock response file."""
    return json.loads((MOCK_DIR / filename).read_text())


def make_per_pen_data(template: list[dict], pen_id: str) -> list[dict]:
    """Clone template records and stamp them with the given pen_id."""
    return [{**copy.deepcopy(r), "penId": pen_id} for r in template]


@pytest.fixture
def mock_rest_client():
    """Patch RESTClient and yield the mock instance."""
    with patch("dlt_source_aquabyte.aquabyte.RESTClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


def run_source(
    pipeline_name: str,
    source: Any,
    resources: list[str],
) -> tuple[Any, Any]:
    """Run a dlt source into DuckDB and return (pipeline, load_info)."""
    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="duckdb",
        dataset_name=f"{pipeline_name}_data",
        dev_mode=True,
    )
    load_info = pipeline.run(source.with_resources(*resources))
    return pipeline, load_info


def assert_row_count(pipeline: Any, table: str, expected: int) -> None:
    """Assert the row count of a table matches expected."""
    with pipeline.sql_client() as client:
        result = client.execute_sql(f"SELECT COUNT(*) FROM {table}")
        assert result is not None
        assert result[0][0] == expected, f"Expected {expected} rows in {table}, got {result[0][0]}"


def assert_pen_ids(pipeline: Any, table: str, expected_pens: list[str], column: str = "pen_id") -> None:
    """Assert the distinct pen IDs in a table match expected."""
    with pipeline.sql_client() as client:
        result = client.execute_sql(f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
        assert result is not None
        pens = sorted(row[0] for row in result)
        assert pens == sorted(expected_pens)


def assert_all_active_pens(pipeline: Any, table: str) -> None:
    """Assert all 4 active pens have data in a table."""
    assert_pen_ids(pipeline, table, ACTIVE_PEN_IDS)
