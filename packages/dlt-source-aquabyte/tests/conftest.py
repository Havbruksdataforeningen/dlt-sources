"""Shared fixtures and helpers for Aquabyte pipeline tests."""

import copy
import inspect
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import dlt
import pytest
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext

from dlt_source_aquabyte import aquabyte_source

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

# A backfill window, as (initial_value, end_value) for a bound `dlt.sources.incremental`.
DATE_WINDOW = ("2026-01-01", "2026-01-31")
TIME_WINDOW = ("2026-01-01T00:00:00Z", "2026-01-31T00:00:00Z")


# --- Teardown ----------------------------------------------------------------
#
# A test run writes two things: a `<pipeline_name>.duckdb` file per pipeline in the
# working directory, and dlt's own state under `~/.dlt/pipelines/`, which is what
# `dlt pipeline <name> show` reads. Both are deleted when the session finishes, so a
# run leaves the working tree as it found it. `pytest --keep-db` keeps them, for when
# you want to open what a run actually ingested.
#
# Teardown removes what this session *touched*, never everything it finds: pipeline
# names are fixed per test, so a rerun reuses the same file rather than making another
# one. Artifacts of tests this session did not run keep their older timestamps and
# survive — so `pytest -k sites` leaves the rest alone, including anything kept from
# an earlier `--keep-db` run.


def pytest_addoption(parser):
    parser.addoption(
        "--keep-db",
        action="store_true",
        default=False,
        help="Keep the DuckDB files and dlt pipeline state this run touched, to inspect afterwards.",
    )


def _duckdb_files() -> list[Path]:
    return list(Path.cwd().glob("*.duckdb"))


def _pipeline_state_dirs() -> list[Path]:
    pipelines = Path(Container()[PluggableRunContext].context.data_dir) / "pipelines"
    return list(pipelines.iterdir()) if pipelines.is_dir() else []


def _touched_since(path: Path, cutoff: float) -> bool:
    candidates = [path, *path.rglob("*")] if path.is_dir() else [path]
    return any(p.stat().st_mtime >= cutoff for p in candidates if p.exists())


def pytest_sessionstart(session):
    if not session.config.getoption("--keep-db"):
        # A second of slack: filesystem timestamps are coarser than time.time().
        session.clean_db_cutoff = time.time() - 1  # type: ignore[attr-defined]


def pytest_sessionfinish(session, exitstatus):
    cutoff = getattr(session, "clean_db_cutoff", None)
    if cutoff is None:
        return

    for path in _duckdb_files():
        if _touched_since(path, cutoff):
            path.unlink(missing_ok=True)
            path.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    for path in _pipeline_state_dirs():
        if _touched_since(path, cutoff):
            shutil.rmtree(path, ignore_errors=True)


def load_mock(filename: str) -> dict:
    return json.loads((MOCK_DIR / filename).read_text())


def make_per_pen_data(template: list[dict], pen_id: str) -> list[dict]:
    return [{**copy.deepcopy(r), "penId": pen_id} for r in template]


@pytest.fixture
def without_configured_starts(tmp_path, monkeypatch):
    """Run with no config at all: no `.dlt/` files, no `SOURCES__*` variables.

    A maintainer's own `.dlt/config.toml` supplies `initial_date` and `initial_time`, which
    is what a test of the missing-start error needs gone.
    """
    for name in [name for name in os.environ if name.startswith("SOURCES__")]:
        monkeypatch.delenv(name, raising=False)

    run_context = Container()[PluggableRunContext]
    original_run_dir = run_context.context.run_dir
    run_context.reload(str(tmp_path))
    try:
        yield
    finally:
        run_context.reload(original_run_dir)


@pytest.fixture
def mock_rest_client():
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
    return [call.kwargs for call in mock_client.paginate.call_args_list if call.args and call.args[0] == path]


def params_sent(mock_client: Any, path: str) -> list[dict[str, Any]]:
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
    pipeline = make_pipeline(pipeline_name)
    load_info = pipeline.run(source.with_resources(*resources))
    return pipeline, load_info


def query(pipeline: Any, sql: str) -> list[tuple]:
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result


def assert_row_count(pipeline: Any, table: str, expected: int) -> None:
    rows = query(pipeline, f"SELECT COUNT(*) FROM {table}")
    assert rows[0][0] == expected, f"Expected {expected} rows in {table}, got {rows[0][0]}"


def assert_pen_ids(pipeline: Any, table: str, expected_pens: list[str], column: str = "pen_id") -> None:
    rows = query(pipeline, f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
    assert sorted(row[0] for row in rows) == sorted(expected_pens)


def assert_all_active_pens(pipeline: Any, table: str) -> None:
    assert_pen_ids(pipeline, table, ACTIVE_PEN_IDS)


# --- Endpoints ----------------------------------------------------------------


@dataclass(frozen=True)
class Endpoint:
    """A data resource and the endpoint it reads."""

    resource: str
    path: str
    mock_file: str
    selector: str
    """The API's envelope key, which is also dlt's `data_selector`."""
    window_param: str
    optional_param: tuple[str, str, Any] | None = None
    """(resource argument, the query param it becomes, a value to send)."""
    single_page: bool = False

    @property
    def records(self) -> list[dict]:
        return load_mock(self.mock_file)[self.selector]

    @property
    def window(self) -> tuple[str, str]:
        """A backfill window, as the `initial_value` and `end_value` to bind."""
        return DATE_WINDOW if self.window_param == "fromDate" else TIME_WINDOW

    @property
    def end_param(self) -> str:
        return self.window_param.replace("from", "to")

    @property
    def config_key(self) -> str:
        return "initial_date" if self.window_param == "fromDate" else "initial_time"

    @property
    def configured_start(self) -> str:
        return SOURCE_CONFIG[self.config_key]

    @property
    def incremental_argument(self) -> str:
        """The `incremental_*` argument a window is bound on, named after the cursor field."""
        signature = resource_signature(aquabyte_source(**SOURCE_CONFIG), self.resource)
        return next(name for name in signature.parameters if name.startswith("incremental_"))


ENDPOINTS = [
    Endpoint(
        "environmental",
        "/environmental",
        "environmental.json",
        "data",
        "fromTime",
        optional_param=("period", "period", "15min"),
    ),
    Endpoint(
        "biomass",
        "/biomass",
        "biomass.json",
        "biomass",
        "fromDate",
        optional_param=("bucket_size", "bucketSize", 500),
    ),
    Endpoint(
        "harvest_report",
        "/biomass/harvestReport",
        "harvest_report.json",
        "reports",
        "fromDate",
        single_page=True,
    ),
    Endpoint("lice_count", "/liceCount", "lice_count.json", "liceCount", "fromDate"),
    Endpoint(
        "behaviour_swim_speed",
        "/behaviour/swimSpeed",
        "swim_speed.json",
        "swimSpeed",
        "fromTime",
        optional_param=("period", "period", "h"),
    ),
    Endpoint(
        "behaviour_breathing_index", "/behaviour/breathingIndex", "breathing_index.json", "breathingIndex", "fromTime"
    ),
    Endpoint("welfare_scores", "/welfareScores", "welfare_scores.json", "welfareScores", "fromDate"),
]


def endpoint(resource: str) -> Endpoint:
    return next(one for one in ENDPOINTS if one.resource == resource)
