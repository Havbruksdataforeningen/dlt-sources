"""Shared fixtures and helpers for Aquabyte pipeline tests."""

import copy
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import dlt
import pytest

MOCK_DIR = Path(__file__).parent / "mock_responses"

ACTIVE_PEN_IDS = ["pen-001", "pen-003", "pen-004", "pen-005"]
INACTIVE_PEN_ID = "pen-002"
ALL_PEN_IDS = ["pen-001", "pen-002", "pen-003", "pen-004", "pen-005"]

# Everything aquabyte_source() itself needs: connection details and cursor starts.
# Query params live on the resources — bind them there.
SOURCE_CONFIG: dict[str, Any] = {
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


def serve(routes: dict[str, list[dict]]):
    """Build a `paginate` side effect serving one page per route.

    A request for `penId=all` is answered with the route's records stamped onto every
    active pen, and a request for a single pen with the records stamped onto that pen —
    which is how the real API behaves. A route asked for without `penId` is served
    as-is.
    """

    def paginate(url: str, **kwargs):
        if url not in routes:
            return iter([])
        records = routes[url]
        pen_id = kwargs.get("params", {}).get("penId")
        if pen_id is None:
            return iter([records])
        pen_ids = ACTIVE_PEN_IDS if pen_id == "all" else [pen_id]
        page: list[dict] = []
        for pid in pen_ids:
            page.extend(make_per_pen_data(records, pid))
        return iter([page])

    return paginate


def resource_signature(source: Any, resource_name: str) -> inspect.Signature:
    """The signature of the function behind a resource.

    Reaching through `_pipe.gen` is dlt's private shape, so it is spelled out once here
    rather than in each test that needs a resource's declared arguments.
    """
    return inspect.signature(cast(Callable, source.resources[resource_name]._pipe.gen))


def calls_to(mock_client: Any, path: str) -> list[dict[str, Any]]:
    """Every `paginate` call made against `path`, as kwargs dicts."""
    return [call.kwargs for call in mock_client.paginate.call_args_list if call.args and call.args[0] == path]


def params_sent(mock_client: Any, path: str) -> list[dict[str, Any]]:
    """The query params of every `paginate` call made against `path`."""
    return [kwargs.get("params", {}) for kwargs in calls_to(mock_client, path)]


def make_pipeline(pipeline_name: str) -> Any:
    """A DuckDB pipeline in a throwaway dataset, for tests that load more than once."""
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="duckdb",
        dataset_name=f"{pipeline_name}_data",
        dev_mode=True,
    )


def run_source(
    pipeline_name: str,
    source: Any,
    resources: list[str],
) -> tuple[Any, Any]:
    """Run a dlt source into DuckDB and return (pipeline, load_info)."""
    pipeline = make_pipeline(pipeline_name)
    load_info = pipeline.run(source.with_resources(*resources))
    return pipeline, load_info


def query(pipeline: Any, sql: str) -> list[tuple]:
    """Run a SQL query against the pipeline's destination and return its rows."""
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result


def assert_row_count(pipeline: Any, table: str, expected: int) -> None:
    """Assert the row count of a table matches expected."""
    rows = query(pipeline, f"SELECT COUNT(*) FROM {table}")
    assert rows[0][0] == expected, f"Expected {expected} rows in {table}, got {rows[0][0]}"


def assert_pen_ids(pipeline: Any, table: str, expected_pens: list[str], column: str = "pen_id") -> None:
    """Assert the distinct pen IDs in a table match expected."""
    rows = query(pipeline, f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
    assert sorted(row[0] for row in rows) == sorted(expected_pens)


def assert_all_active_pens(pipeline: Any, table: str) -> None:
    """Assert all 4 active pens have data in a table."""
    assert_pen_ids(pipeline, table, ACTIVE_PEN_IDS)
