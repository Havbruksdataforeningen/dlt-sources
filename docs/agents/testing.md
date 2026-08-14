# Testing

Target state. Every rule here is one a comparable project already follows — the precedent is named so nobody has to relitigate it. The reasoning and citations live in [`docs/research/ci-cd.md`](../research/ci-cd.md).

The risk these packages carry is **the upstream API changing shape, or the source mis-mapping it**. Not algorithmic complexity. The regime below points everything at that.

## The two tiers

- **`tests/unit/` — no network, no credentials, ever.** Runs on every PR, must stay fast. *Airbyte connectors, botocore and datadogpy all split by directory rather than by decorator.*
- **`tests/live/` — hits the real API.** Never runs on a PR. Runs on a schedule. *Meltano's SDK runs its live tier on a 4-hourly cron and nowhere else.*

- **Directory membership is the truth; the marker is stamped from it.** A `pytest_collection_modifyitems` hook in `conftest.py` applies the `live` marker based on the path. Nobody writes `@pytest.mark.live` by hand, so nobody forgets it. *This is `meltano/sdk:tests/conftest.py` verbatim.*
- **A bare `pytest` must never reach the network.** Put the deselection in `addopts`, not in the CI command, so a laptop and CI agree by construction. *Meltano again: `addopts = [..., "-m", "not external"]`.*
- **Markers are registered and strict** (`strict = true` / `--strict-markers`), and `xfail_strict = true`. An unregistered marker in a CI filter silently matches nothing — a real trap, visible today in `airbytehq/airbyte-python-cdk`.

## Faking HTTP

- **Fake at the HTTP transport boundary with `requests-mock`. Never mock dlt's `RESTClient`.** Replacing the framework's client proves only that your code calls a mock; pagination, auth, retry and response→record mapping — where connector bugs actually live — go untested. *dlt's own REST-source tests mock `requests`, not `RESTClient`. Airbyte's `HttpMocker` is a `requests_mock.Mocker` with assertions bolted on, precisely so the real retrievers and paginators run.*
- **No VCR cassettes.** *Not one of Airbyte's CDK, Meltano's SDK, dlt, stripe-python or botocore uses them.* Cassettes bind tests to exact URL/header/body matching, carry secrets that must be scrubbed, and rot invisibly. Use them only where a response is too intricate to hand-write.
- **Response bodies live in `tests/fixtures/*.json`, one per endpoint plus one per error status,** seeded from one real call and trimmed to the fields that matter. *Airbyte ships `400.json`, `401.json`, `429.json`, `500.json` per connector.*
- **Mocks are assertions.** An unmatched request fails the test; so does an unused mock. *Airbyte raises on any uncalled matcher; stripe-python raises on anything unstubbed; botocore's `Stubber` exposes `assert_no_pending_responses()`.*
- **Model the API's behaviour, not just its bodies.** Pagination, fan-out, cursor termination and error statuses belong in the route handlers, so traversal logic is genuinely under test. *dlt's test router implements five distinct pagination styles as live routes.*
- **Assert on what landed in the destination.** Load into DuckDB and query it — that is the only way schema inference and column typing are covered. *`dlt-hub/verified-sources` asserts exact table counts after a real load.*

## Catching upstream drift

- **Commit a golden dlt schema per resource** (`Schema.to_pretty_yaml()` → `tests/schemas/<resource>.schema.yaml`). The unit tier asserts the fixtures still produce it — that catches *our* regressions. The live tier asserts the real API still produces it — that catches *theirs*. *The commit-a-golden-artifact-and-diff pattern is how PyGithub tracks GitHub's OpenAPI spec and how Airbyte tracks its agent API spec; both fail the build on any diff.*
- **The nightly runs under a `freeze` column contract; the shipped source runs under `evolve`.** Same code, one parameter. Production must not break when a vendor adds a field; the nightly must shout when they do.
- **Bound the live run** — `add_limit(max_items=..., max_time=...)` on every resource, plus a per-test timeout. It is a canary, not a backfill.
- **Live tests fail loudly on missing credentials; they never skip.** A silently-skipping canary is worse than none. *stripe-python refuses to start rather than degrade.*
- **A failed nightly opens or updates a single GitHub issue.** A red X nobody is watching is not a signal, and `update_existing: true` is what stops it filing thirty duplicates a month. *Synapse and scikit-image both do exactly this.*

## Coverage

- **No coverage floor. Not `fail_under`, not `--cov-fail-under`.** On connector code a floor measures how much mapping boilerplate you wrapped in a test, not whether the mapping is right, and it turns every honest refactor into a chore. *None of dlt, verified-sources, stripe-python, boto3, botocore or Airbyte's CDK sets one. `pytest` itself sets `project: false`.*
- **Measure it and print it every run** (`--cov=<pkg> --cov-report=term-missing`). A number you look at costs nothing; a number that blocks costs a lot.
- **Don't model the 100%-coverage projects.** httpx, attrs and structlog hit 100% by counting their own test files as covered source. Different game.

## Layout

- **Tests live in `packages/<name>/tests/`. No root suite, no root `conftest.py`.** Fixtures are only found by searching *upward*, so a root conftest silently couples every package to a file no package's version pins.
- **Each package is its own pytest rootdir with its own config.** One `pytest` invocation per package. This is what makes packages independent: markers, warning filters and plugins can change without touching a sibling. *Each Airbyte connector carries its own test manifest.*
- **`--import-mode=importlib`, and `__init__.py` in test packages.** Two packages will eventually both have `tests/test_sites.py`; under the default `prepend` mode that is a collection error waiting to happen. *pytest's own recommendation for new projects.*
- **Tests write nothing outside `tmp_path`.** Point DuckDB at a temp path, use `dev_mode=True` and unique dataset names, drop pipeline data in an autouse teardown. Otherwise dlt drops a `<pipeline_name>.duckdb` in the working directory.
- **No shared test-utils package until the third package needs one** — and when it comes, it ships as a pytest plugin via a `pytest11` entry point, wired in through `[dependency-groups]` + `[tool.uv.sources]`. That combination provably never reaches a published wheel. Until then, duplicate the helper; two copies of a fixture cost less than a premature shared dependency. *Meltano and Airbyte both distribute their test machinery this way.*
- **Shared fixtures may be a plugin; shared fixture *data* must not be.** Response JSON belongs to the package whose API it describes.

## Static checks

- **The type checker is its own CI job — never inside pytest.** *Unanimous across dlt, Airbyte, Meltano, stripe-python and botocore.*
- **Lint, format, types and tests are parallel required jobs with `fail-fast: false`.** A contributor should learn about a type error and a test failure in one round trip, not two. *stripe-python and Meltano both run them in parallel; dlt chains them and pays a full round trip per typo.*
- **Type-check `tests/` too.** For a connector the mapping assertions live in the tests; leaving them unchecked leaves the most schema-sensitive code in the repo unchecked. *dlt runs `mypy dlt tests tools`.*
- **Pin the type checker version and bump it deliberately.** Pyright ships weekly and each release can add diagnostics — unpinned, it turns an unrelated PR red. *stripe-python pins `pyright == 1.1.336`.*
- **Use pyright's default `standard` mode.** `basic` is weaker than the tool's own default, which is a silent downgrade if a config predates the change.

## Deliberately not adopted

Each of these is a real practice that a much larger project needs and this one does not — yet.

- **Changed-package CI matrices.** A flat loop over `packages/*/` is correct. *Airbyte and verified-sources both compute affected packages because they have 37–300+ connectors.* The trigger to change is CI wall-clock, not package count.
- **An acceptance-test harness.** Airbyte's is a governance tool for hundreds of third-party contributions, not a testing tool for a team that reads every PR.
- **A spec-derived mock server** (stripe-mock style). It validates *request* shape — the half a connector cares least about — and by its own README returns hardcoded responses and can't produce error cases.
- **Schemathesis.** It generates inputs to find bugs in the *provider*. Wrong direction for a consumer.
- **Snapshot-testing frameworks.** For one golden schema per resource, a plain comparison plus an update flag is enough. Adopt a plugin when the golden files outnumber the tests.
- **Blanket `filterwarnings = ["error"]`.** dlt ships its own `DeprecationWarning` noise, which a dependent package inherits. Strict *markers* yes; warnings-as-errors no.
