"""Shared fixtures: `requests_mock` answers the token endpoint and the routes a test registers, with nothing inside the package patched."""

import inspect
import json
import os
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

# Invented numbers, the ones `localitieswithsalmonoids.json` lists.
ALL_LOCALITY_NOS = [90001, 90002, 90003, 90004, 90005]

SOURCE_CONFIG: dict[str, Any] = {"client_id": "test-id", "client_secret": "test-secret"}

# The only paths the mocks answer: a request for anything else finds no mock.
LOCALITIES_PATH = "v1/geodata/fishhealth/localities"
LOCALITIES_WITH_SALMONOIDS_PATH = "v1/geodata/fishhealth/localitieswithsalmonoids"
LOCALITY_WEEK_PATH = "v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}"
LOCALITY_WEEK_SUMMARY_PATH = "v2/geodata/fishhealth/locality/{year}/{week}"

LOCALITIES_URL = BASE_URL + LOCALITIES_WITH_SALMONOIDS_PATH
LOCALITIES_ALL_URL = BASE_URL + LOCALITIES_PATH

THREE_WEEKS = WeekRange(2024, 1, 2024, 3)


# --- Isolation ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_run_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An empty dlt project per test, pipeline state included: a maintainer's own `.dlt/config.toml` would otherwise bind `body` into every source built here, and `~/.dlt/pipelines` is shared with live loads."""
    for name in [name for name in os.environ if name.startswith("SOURCES__")]:
        monkeypatch.delenv(name, raising=False)
    # An empty project does not inherit telemetry being off, and the ping would show up in the request history.
    monkeypatch.setenv("RUNTIME__DLTHUB_TELEMETRY", "false")
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "data"))

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
    """dlt's five retries with the backoff removed: the attempts are kept, the twenty seconds are not."""
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
    """The API as `requests_mock` serves it. A route the test did not register fails as `NoMockAddress` rather than answering."""

    def __init__(self, mocker: requests_mock.Mocker) -> None:
        self.mocker = mocker
        self.token = mocker.post(
            TOKEN_URL, json={"access_token": "test-token", "expires_in": 3600, "token_type": "Bearer", "scope": "api"}
        )

    def localities(self, rows: list[dict[str, Any]] | None = None, **kwargs: Any) -> Any:
        """Answer the salmonoid locality list with `rows`, by default the fixture; `kwargs` go to `requests_mock`."""
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
        """Answer the summary `POST` with `rows`; with `body`, only a request carrying exactly that body is answered."""
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
    """A source with test credentials, and the resource arguments bound when given."""
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
    """The signature of the function behind a resource, reached through dlt's private `_pipe.gen`."""
    return inspect.signature(cast(Callable, source.resources[resource_name]._pipe.gen))
