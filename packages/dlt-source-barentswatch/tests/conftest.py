"""Shared fixtures and helpers for BarentsWatch Fish Health pipeline tests.

The offline suite talks HTTP to a `requests_mock` server that answers the token endpoint and
whichever of the four API routes a test registers. Nothing inside the package is patched, so
the OAuth2 flow, dlt's retry session and the source's own status handling all run for real.
"""

import inspect
import json
import os
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import dlt
import pytest
import requests
import requests_mock
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext

from dlt_source_barentswatch import WeekRange, fishhealth_source
from dlt_source_barentswatch.fishhealth import BASE_URL, TOKEN_URL

MOCK_DIR = Path(__file__).parent / "mock_responses"

# The locality numbers `localitieswithsalmonoids.json` lists — a subset of `localities.json`'s;
# `test_mock_fidelity.py` keeps them in step.
ALL_LOCALITY_NOS = [90001, 90002, 90003, 90004, 90005]

# Everything fishhealth_source() itself needs. Resource arguments — the weeks
# to load and the summary's body — live on the resources; bind them there.
SOURCE_CONFIG: dict[str, Any] = {"client_id": "test-id", "client_secret": "test-secret"}

# The four paths the source requests, spelled the way the spec spells them. The mocked tests
# answer only these, so a source that asked for anything else would find no mock; and
# `test_spec_surface.py` checks they are still in `specs/fishhealth.json`.
LOCALITIES_PATH = "v1/geodata/fishhealth/localities"
LOCALITIES_WITH_SALMONOIDS_PATH = "v1/geodata/fishhealth/localitieswithsalmonoids"
LOCALITY_WEEK_PATH = "v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}"
LOCALITY_WEEK_SUMMARY_PATH = "v2/geodata/fishhealth/locality/{year}/{week}"

LOCALITIES_URL = BASE_URL + LOCALITIES_WITH_SALMONOIDS_PATH
LOCALITIES_ALL_URL = BASE_URL + LOCALITIES_PATH

# A short range for tests that need more than one week: three weeks, in one year.
THREE_WEEKS = WeekRange(2024, 1, 2024, 3)


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
# survive — so `pytest -k locality` leaves the rest alone, including anything kept from
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


# --- Isolation ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_run_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run with no config at all: no `.dlt/` files, no `SOURCES__*` variables.

    A maintainer's own `.dlt/config.toml` may set `locality_week_summary.body`, and dlt would
    inject it into every summary resource a test builds — changing the bodies the tests assert
    on. So each offline test gets an empty dlt project directory instead; a test that wants
    config read writes it in here and reloads. `test_integration.py` overrides this fixture,
    since the live tests need the real `secrets.toml`.

    Yields the project directory, whose `.dlt/` is where a test puts config it wants read.
    """
    for name in [name for name in os.environ if name.startswith("SOURCES__")]:
        monkeypatch.delenv(name, raising=False)
    # The maintainer's global config may switch dlt's telemetry off; an empty project does
    # not, and the ping would show up in the mock API's request history.
    monkeypatch.setenv("RUNTIME__DLTHUB_TELEMETRY", "false")

    # `reload` swaps a process-global, so the restore has to cover the reload itself.
    run_context = Container()[PluggableRunContext]
    original_run_dir = run_context.context.run_dir
    try:
        run_context.reload(str(tmp_path))
        yield tmp_path
    finally:
        run_context.reload(original_run_dir)


@pytest.fixture(autouse=True)
def zero_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry 5xx and connection errors as many times as dlt would, but without waiting between them.

    dlt's session retries five times with exponential backoff, which is right in production
    and a twenty-second wait in a test of a 500. The attempts are kept — a test can count
    them — and only the delays go.
    """
    import dlt.sources.helpers.requests.retry as retry_module

    original = retry_module._make_retry
    monkeypatch.setattr(
        retry_module,
        "_make_retry",
        lambda **kwargs: original(**{**kwargs, "backoff_factor": 0, "max_delay": 0}),
    )


# --- The mock API -------------------------------------------------------------


def load_mock(filename: str) -> Any:
    return json.loads((MOCK_DIR / filename).read_text())


def week_url(locality_no: int, year: int, week: int) -> str:
    return BASE_URL + LOCALITY_WEEK_PATH.format(localityNo=locality_no, year=year, week=week)


def summary_url(year: int, week: int) -> str:
    return BASE_URL + LOCALITY_WEEK_SUMMARY_PATH.format(year=year, week=week)


class MockApi:
    """The BarentsWatch API as `requests_mock` serves it: a token endpoint and the four routes.

    The token endpoint is registered on construction, because every request needs it. The
    four data routes are registered by the test, so a request for a route the test did not
    expect fails as `NoMockAddress` rather than being answered with something plausible.
    """

    def __init__(self, mocker: requests_mock.Mocker) -> None:
        self.mocker = mocker
        self.token = mocker.post(
            TOKEN_URL, json={"access_token": "test-token", "expires_in": 3600, "token_type": "Bearer", "scope": "api"}
        )

    def localities(self, rows: list[dict[str, Any]] | None = None, **kwargs: Any) -> Any:
        """Answer the salmonoid locality list with `rows`, by default the fixture; `kwargs` go to `requests_mock`.

        This is the list `locality_week` iterates over, so it is the one most tests need.
        """
        if rows is not None:
            kwargs.setdefault("json", rows)
        elif not kwargs:
            kwargs["json"] = load_mock("localitieswithsalmonoids.json")
        return self.mocker.get(LOCALITIES_URL, **kwargs)

    def all_localities(self, rows: list[dict[str, Any]] | None = None, **kwargs: Any) -> Any:
        """Answer the full locality list with `rows`, by default the fixture; `kwargs` go to `requests_mock`."""
        if rows is not None:
            kwargs.setdefault("json", rows)
        elif not kwargs:
            kwargs["json"] = load_mock("localities.json")
        return self.mocker.get(LOCALITIES_ALL_URL, **kwargs)

    def week(self, locality_no: int, year: int, week: int, **kwargs: Any) -> Any:
        """Answer one locality-week with a lice report, unless `kwargs` say otherwise."""
        if not kwargs:
            kwargs["json"] = load_mock("locality_week_reported.json")
        return self.mocker.get(week_url(locality_no, year, week), **kwargs)

    def no_report(self, locality_no: int, year: int, week: int) -> Any:
        """Answer one locality-week the way the API answers a week it has no report for: 400."""
        return self.mocker.get(
            week_url(locality_no, year, week), status_code=400, json=load_mock("problem_details_400.json")
        )

    def weeks(self, locality_nos: list[int], week_range: WeekRange, **kwargs: Any) -> None:
        """Answer every locality-week in the range, for every locality given."""
        for locality_no in locality_nos:
            for year, week in week_range.weeks():
                self.week(locality_no, year, week, **kwargs)

    def summary(
        self,
        year: int,
        week: int,
        rows: list[dict[str, Any]] | None = None,
        *,
        body: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Answer the weekly summary `POST` with `rows`, by default the fixture; `kwargs` go to `requests_mock`.

        With `body`, only a request whose JSON body equals it is answered, so a test can serve
        different rows per filter value and be sure the source asked for each. Without it, any
        body gets the same answer; the bodies actually sent are on `bodies_posted()`.
        """
        if rows is not None:
            kwargs.setdefault("json", rows)
        elif not kwargs:
            kwargs["json"] = load_mock("locality_week_summary.json")
        if body is not None:
            kwargs["additional_matcher"] = lambda request: request.json() == body
        return self.mocker.post(summary_url(year, week), **kwargs)

    def summaries(self, week_range: WeekRange, **kwargs: Any) -> None:
        """Answer the weekly summary for every week in the range, whatever the body."""
        for year, week in week_range.weeks():
            self.summary(year, week, **kwargs)

    def bodies_posted(self, year: int, week: int) -> list[dict[str, Any]]:
        """The JSON bodies of every summary request for one week, in order."""
        return [request.json() for request in self.requests_to(summary_url(year, week))]

    @property
    def requests(self) -> list[Any]:
        """Every request received, token requests included, in order."""
        return list(self.mocker.request_history)

    def requests_to(self, url: str) -> list[Any]:
        return [request for request in self.mocker.request_history if request.url == url]

    def urls_requested(self) -> list[str]:
        """The API URLs requested, in order, without the token endpoint."""
        return [request.url for request in self.mocker.request_history if request.url.startswith(BASE_URL)]


@pytest.fixture
def mock_api() -> Iterator[MockApi]:
    with requests_mock.Mocker() as mocker:
        yield MockApi(mocker)


def make_source(week_range: WeekRange | None = None, *, body: dict[str, Any] | None = None) -> Any:
    """A source with test credentials, and the resource arguments bound when given.

    `week_range` binds to both weekly resources: a load asks for the same weeks from each.
    `body` is `locality_week_summary`'s request body. dlt lets a resource be bound once, so
    everything for the summary goes in one call.
    """
    source = fishhealth_source(**SOURCE_CONFIG)
    if week_range is not None:
        source.locality_week.bind(week_range=week_range)
    summary_args = {"week_range": week_range, "body": body}
    bound = {name: value for name, value in summary_args.items() if value is not None}
    if bound:
        source.locality_week_summary.bind(**bound)
    return source


def http_status(error: BaseException | None) -> int:
    """The status code behind an `HTTPError` — typically the `__cause__` of a `ResourceExtractionError`."""
    assert isinstance(error, requests.HTTPError), f"expected an HTTPError, got {error!r}"
    assert error.response is not None
    return error.response.status_code


# --- Pipelines and tables -----------------------------------------------------


def make_pipeline(pipeline_name: str) -> Any:
    """A DuckDB pipeline in a throwaway dataset, for tests that load more than once."""
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="duckdb",
        dataset_name=f"{pipeline_name}_data",
        dev_mode=True,
    )


def query(pipeline: Any, sql: str) -> list[tuple]:
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result


def load_rows(pipeline: Any, table: str) -> list[dict[str, Any]]:
    """Every row of a table, as dicts keyed by column name."""
    with (
        pipeline.sql_client() as client,
        client.execute_query(f"SELECT * FROM {client.make_qualified_table_name(table)}") as cursor,
    ):
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def assert_row_count(pipeline: Any, table: str, expected: int) -> None:
    rows = query(pipeline, f"SELECT COUNT(*) FROM {table}")
    assert rows[0][0] == expected, f"Expected {expected} rows in {table}, got {rows[0][0]}"


def resource_signature(source: Any, resource_name: str) -> inspect.Signature:
    """The signature of the function behind a resource.

    Reaching through `_pipe.gen` is dlt's private shape, so it is spelled out once here
    rather than in each test that needs a resource's declared arguments.
    """
    return inspect.signature(cast(Callable, source.resources[resource_name]._pipe.gen))
