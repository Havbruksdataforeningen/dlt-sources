"""Shared fixtures and helpers for the Elhub source tests.

Every test talks to a fake transport mounted under `requests`, so the whole real stack runs —
the RESTClient, the Maskinporten token exchange, the headers, the query string — and only the
socket is gone. What a test asserts on is what went over the wire and what landed in DuckDB.
"""

import inspect
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import dlt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
from requests.adapters import HTTPAdapter
from requests.models import PreparedRequest, Response

from dlt_source_elhub import MaskinportenCredentials, elhub_source

MOCK_DIR = Path(__file__).parent / "mock_responses"

API_PATH = "/energy-data/v0/metering-points"
TOKEN_PATH = "/token"  # noqa: S105  # a URL path, not a password

TOKEN_LIFETIME = 1200
"""`expires_in` the fake Maskinporten answers, the value the live client is configured with."""


def load_mock(filename: str) -> dict[str, Any]:
    return json.loads((MOCK_DIR / filename).read_text())


def point_ids(payload: dict[str, Any]) -> list[str]:
    return [item["id"] for item in payload["data"]]


def values_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for item in payload["data"] for value in item["attributes"]["meteringValuesHour"]]


def payload_for(point_id: str, values: list[dict[str, Any]]) -> dict[str, Any]:
    """A by-id response carrying exactly `values`."""
    return {"data": [{"type": "metering-points", "id": point_id, "attributes": {"meteringValuesHour": values}}]}


_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PRIVATE_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
PUBLIC_PEM = (
    _KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
)

CLIENT_ID = "client-0001"
KID = "kid-0001"


def credentials(private_key: str = PRIVATE_PEM) -> MaskinportenCredentials:
    return MaskinportenCredentials(client_id=CLIENT_ID, kid=KID, private_key=private_key)


def source(**kwargs: Any) -> Any:
    """The source with test credentials, so no `.dlt/` or environment is consulted for them."""
    return elhub_source(credentials=credentials(), **kwargs)


@pytest.fixture(autouse=True)
def dlt_writes_to_tmp_path(tmp_path, monkeypatch):
    """Each test's DuckDB file and dlt pipeline state land in its own `tmp_path`."""
    monkeypatch.setenv("DLT_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("RUNTIME__DLTHUB_TELEMETRY", "false")


@contextmanager
def dlt_project(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make the `.dlt/` files in `run_dir` dlt's only config: no other project, no `SOURCES__*` variables."""
    for name in [name for name in os.environ if name.startswith("SOURCES__")]:
        monkeypatch.delenv(name, raising=False)

    run_context = Container()[PluggableRunContext]
    original_run_dir = run_context.context.run_dir
    try:
        run_context.reload(str(run_dir))
        yield
    finally:
        run_context.reload(original_run_dir)


@dataclass(frozen=True)
class Recorded:
    """One request as it left the session."""

    method: str
    path: str
    params: dict[str, str]
    headers: dict[str, str]
    form: dict[str, str]


@dataclass
class FakeElhub:
    """Routes `path -> payload` and records every request the session sends.

    A payload is the JSON body of a `200`, or `None` for `204 No Content`. A path that is not
    routed answers `404`, which the RESTClient raises, so a test fails loudly instead of
    silently loading nothing. The Maskinporten token endpoint is routed from the start.
    """

    routes: dict[str, Any] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    token_responses: int = 0

    def route(self, path: str, payload: dict[str, Any] | None) -> None:
        self.routes[path] = payload

    def route_point(self, point_id: str, payload: dict[str, Any] | None) -> None:
        self.route(f"{API_PATH}/{point_id}", payload)

    def calls(self, path: str) -> list[Recorded]:
        return [one for one in self.requests if one.path == path]

    def calls_to_point(self, point_id: str) -> list[Recorded]:
        return self.calls(f"{API_PATH}/{point_id}")

    @property
    def grants(self) -> list[str]:
        return [one.form["assertion"] for one in self.requests if one.path == TOKEN_PATH]

    def send(self, prepared: PreparedRequest) -> Response:
        parts = urlsplit(prepared.url or "")
        body = prepared.body.decode() if isinstance(prepared.body, bytes) else (prepared.body or "")
        self.requests.append(
            Recorded(
                method=prepared.method or "GET",
                path=parts.path,
                params={key: value[0] for key, value in parse_qs(parts.query).items()},
                headers=dict(prepared.headers),
                form={key: value[0] for key, value in parse_qs(body).items()},
            )
        )
        if parts.path == TOKEN_PATH:
            self.token_responses += 1
            token = {"access_token": f"token-{self.token_responses}", "expires_in": TOKEN_LIFETIME}
            return _response(prepared, 200, token)
        if parts.path not in self.routes:
            return _response(prepared, 404, {"errors": [{"status": "404", "title": f"no route for {parts.path}"}]})
        payload = self.routes[parts.path]
        return _response(prepared, 204, None) if payload is None else _response(prepared, 200, payload)


def _response(prepared: PreparedRequest, status: int, payload: dict[str, Any] | None) -> Response:
    response = Response()
    response.status_code = status
    response.reason = {200: "OK", 204: "No Content", 404: "Not Found"}[status]
    response._content = b"" if payload is None else json.dumps(payload).encode()
    if payload is not None:
        response.headers["Content-Type"] = "application/json"
    response.encoding = "utf-8"
    response.url = prepared.url or ""
    response.request = prepared
    return response


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeElhub:
    """Swap the HTTP transport under `requests` for the fake, for every session in the process."""
    fake = FakeElhub()

    def send(self: HTTPAdapter, request: PreparedRequest, **kwargs: Any) -> Response:
        return fake.send(request)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    return fake


@pytest.fixture
def api_with_fixtures(api: FakeElhub) -> FakeElhub:
    """The fake serving the two anonymised responses: the list, and each listed point by id."""
    listing = load_mock("metering_points_hour_all.json")
    api.route(API_PATH, listing)
    for item in listing["data"]:
        api.route_point(item["id"], {"data": [item]})
    return api


def make_pipeline(pipeline_name: str) -> Any:
    """A DuckDB pipeline in a throwaway dataset, for tests that load more than once."""
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="duckdb",
        dataset_name=f"{pipeline_name}_data",
        dev_mode=True,
    )


def run(pipeline: Any, source_: Any, *resources: str) -> Any:
    selected = source_.with_resources(*resources) if resources else source_
    load_info = pipeline.run(selected)
    load_info.raise_on_failed_jobs()
    return load_info


def query(pipeline: Any, sql: str) -> list[tuple]:
    with pipeline.sql_client() as client:
        result = client.execute_sql(sql)
        assert result is not None
        return result


def row_count(pipeline: Any, table: str) -> int:
    return query(pipeline, f"SELECT COUNT(*) FROM {table}")[0][0]


def cursors(pipeline: Any) -> dict[str, str]:
    """The per-metering-point cursors the source stored, by metering point id."""
    sources = pipeline.state.get("sources", {})
    (state,) = sources.values() if sources else ({},)
    return dict(state.get("resources", {}).get("metering_values_hour", {}).get("insert_date_time", {}))


def resource_signature(source_: Any, resource_name: str) -> Any:
    """The signature of the function behind a resource.

    Reaching through `_pipe.gen` is dlt's private shape, so it is spelled out once here
    rather than in each test that needs a resource's declared arguments.
    """
    return inspect.signature(source_.resources[resource_name]._pipe.gen)
