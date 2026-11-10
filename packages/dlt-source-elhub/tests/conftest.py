"""Shared fixtures: a fake transport under `requests`, so the whole real stack runs and only the socket is gone."""

import inspect
import json
import math
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import dlt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
from requests.adapters import HTTPAdapter
from requests.exceptions import Timeout
from requests.models import PreparedRequest, Response

from dlt_source_elhub import MaskinportenCredentials, elhub_source, maskinporten

MOCK_DIR = Path(__file__).parent / "mock_responses"

API_PATH = "/energy-data/v0/metering-points"
TOKEN_PATH = "/token"  # noqa: S105  # a URL path, not a password

TOKEN_LIFETIME = 120
REQUEST_TIMEOUT = 60
"""dlt's default, how long a request waits for an answer."""
"""`expires_in` the fake Maskinporten answers: Digdir's default, set per client in the self-service portal."""

ELHUB_RATE_LIMITED = (
    "This is a public service, we're experimenting with rate limits, so everybody can utilize it.\n"
    "Please see our 'Terms of Service' on https://api.elhub.no/\n"
)
"""Elhub's `429` body, verbatim (2026-11-10): plain text, no `Retry-After`."""

ELHUB_TOKEN_EXPIRED = {
    "errors": [
        {
            "status": "401",
            "title": "The provided access token has expired. Please obtain a new token for continued access.",
        }
    ]
}
"""Elhub's answer to an expired token, as of 2026-11-10."""


Payload = dict[str, Any] | None
Route = Payload | Callable[[dict[str, str]], Payload]


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
    """The source with test credentials, so no `.dlt/` or environment is consulted."""
    return elhub_source(credentials=credentials(), **kwargs)


@pytest.fixture(autouse=True)
def dlt_writes_to_tmp_path(tmp_path, monkeypatch):
    """Each test's DuckDB file and dlt pipeline state land in its own `tmp_path`."""
    monkeypatch.setenv("DLT_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("RUNTIME__DLTHUB_TELEMETRY", "false")


@contextmanager
def dlt_project(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The `.dlt/` files in `run_dir` as dlt's only config: no other project, no `SOURCES__*` variables."""
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
    """Routes `path -> payload` (`None` for `204`, a callable for one that depends on the query), answers the
    token endpoint, and records every request.

    An unrouted path is `404`, which the source raises, so a test fails loudly rather than loading nothing.
    Time passes only when the client sleeps: `slept` is that clock, and a token older than `TOKEN_LIFETIME`
    on it is `401`, as Elhub answers an expired one.
    """

    routes: dict[str, Route] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    token_responses: int = 0
    refusal: tuple[int, dict[str, Any] | str] | None = None
    """What the token endpoint answers instead of a token: a status with Maskinporten's JSON, or a raw body."""
    slept: float = 0.0
    rate_limited_until: float = 0.0
    issued_at: dict[str, float] = field(default_factory=dict)
    unanswered: int = 0

    def leave_unanswered(self, times: int) -> None:
        """The next `times` API calls time out, each after dlt's timeout on the clock."""
        self.unanswered = times

    def rate_limit(self, seconds: float = math.inf) -> None:
        """Answer every API call `429`, as Elhub does past its limit, until the client has slept `seconds`."""
        self.rate_limited_until = self.slept + seconds

    def sleep(self, seconds: float) -> None:
        self.slept += seconds

    def route(self, path: str, payload: Route) -> None:
        self.routes[path] = payload

    def route_point(self, point_id: str, payload: dict[str, Any] | None) -> None:
        self.route(f"{API_PATH}/{point_id}", payload)

    def calls(self, path: str) -> list[Recorded]:
        return [one for one in self.requests if one.path == path]

    def refuse_tokens(self, status: int, body: dict[str, Any] | str) -> None:
        self.refusal = (status, body)

    def calls_to_point(self, point_id: str) -> list[Recorded]:
        return self.calls(f"{API_PATH}/{point_id}")

    @property
    def grants(self) -> list[str]:
        return [one.form["assertion"] for one in self.requests if one.path == TOKEN_PATH]

    def send(self, prepared: PreparedRequest) -> Response:
        parts = urlsplit(prepared.url or "")
        body = prepared.body.decode() if isinstance(prepared.body, bytes) else str(prepared.body or "")
        self.requests.append(
            Recorded(
                method=prepared.method or "GET",
                path=parts.path,
                params={key: value[0] for key, value in parse_qs(parts.query).items()},
                headers={key: str(value) for key, value in prepared.headers.items()},
                form={key: value[0] for key, value in parse_qs(body).items()},
            )
        )
        if parts.path == TOKEN_PATH:
            if self.refusal is not None:
                return _response(prepared, *self.refusal)
            self.token_responses += 1
            token = f"token-{self.token_responses}"
            self.issued_at[token] = self.slept
            return _response(prepared, 200, {"access_token": token, "expires_in": TOKEN_LIFETIME})
        if self.unanswered:
            self.unanswered -= 1
            self.slept += REQUEST_TIMEOUT
            raise Timeout(f"no answer from {parts.path}")
        bearer = str(prepared.headers.get("Authorization", "")).removeprefix("Bearer ")
        if bearer in self.issued_at and self.slept >= self.issued_at[bearer] + TOKEN_LIFETIME:
            return _response(prepared, 401, ELHUB_TOKEN_EXPIRED)
        if self.slept < self.rate_limited_until:
            return _response(prepared, 429, ELHUB_RATE_LIMITED)
        if parts.path not in self.routes:
            return _response(prepared, 404, {"errors": [{"status": "404", "title": f"no route for {parts.path}"}]})
        payload = self.routes[parts.path]
        if callable(payload):
            payload = payload(self.requests[-1].params)
        return _response(prepared, 204, None) if payload is None else _response(prepared, 200, payload)


def _response(prepared: PreparedRequest, status: int, payload: dict[str, Any] | str | None) -> Response:
    """A `str` payload is a raw body, as a proxy in front of Maskinporten would send one."""
    response = Response()
    response.status_code = status
    response.reason = HTTPStatus(status).phrase
    if isinstance(payload, str):
        response._content = payload.encode()
    else:
        response._content = b"" if payload is None else json.dumps(payload).encode()
    if isinstance(payload, dict):
        response.headers["Content-Type"] = "application/json"
    response.encoding = "utf-8"
    response.url = prepared.url or ""
    response.request = prepared
    return response


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeElhub:
    """The fake transport, for every `requests` session in the process, and a clock only sleeping moves,
    which the token's expiry follows too."""
    fake = FakeElhub()
    start = time.time()

    def send(self: HTTPAdapter, request: PreparedRequest, **kwargs: Any) -> Response:
        return fake.send(request)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    monkeypatch.setattr(maskinporten, "time", SimpleNamespace(time=lambda: start + fake.slept))
    return fake


@pytest.fixture
def api_with_fixtures(api: FakeElhub) -> FakeElhub:
    """The fake serving the anonymised list response, and each listed point by id."""
    listing = load_mock("metering_points_hour_all.json")
    api.route(API_PATH, listing)
    for item in listing["data"]:
        api.route_point(item["id"], {"data": [item]})
    return api


def make_pipeline(pipeline_name: str) -> Any:
    """A DuckDB pipeline in a throwaway dataset."""
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
    """The per-metering-point cursors the source stored."""
    sources = pipeline.state.get("sources", {})
    (state,) = sources.values() if sources else ({},)
    return dict(state.get("resources", {}).get("metering_values_hour", {}).get("insert_date_time", {}))


def resource_signature(source_: Any, resource_name: str) -> Any:
    """`_pipe.gen` is dlt's private shape, spelled out once here."""
    return inspect.signature(source_.resources[resource_name]._pipe.gen)
