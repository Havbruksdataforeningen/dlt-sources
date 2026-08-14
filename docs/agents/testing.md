# Testing

How we test a source package. The reasoning is in [`docs/research/ci-cd.md`](../research/ci-cd.md); the evidence behind each rule is in [`ci-cd-evidence.md`](../research/ci-cd-evidence.md).

Vocabulary: [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md).

## The short version

Tests are offline. They replace the supplier's API with saved sample responses and check that the source turns them into the right tables. That is the whole idea.

## Rules

**Tests never use the network.** Every test in `tests/` runs offline, on any laptop, with no credentials and no supplier account. A new contributor can clone the repo and run the tests in one command.

**Replace HTTP with `requests-mock`. Do not mock dlt's `RESTClient`.** If you replace the client, you only prove that your code calls your own mock — pagination, authentication and the mapping from response to table never run, and that is where the bugs are. dlt's own tests mock `requests` for exactly this reason.

**Sample responses live in `tests/fixtures/*.json`.** One file per endpoint, plus one per error status you handle (401, 429, 500). Take them from the supplier's documented examples — an OpenAPI or Swagger specification if they publish one — otherwise from one real response, trimmed to the fields that matter. Prefer the documented example: it is what the supplier promises, and it can be checked against the spec.

**An unexpected request fails the test, and so does an unused mock.** An unused mock means the test is not doing what you think it is.

**Put the API's behaviour in the fake, not just its data.** Pagination, `penId=all` fan-out and error statuses belong in the mock routes, so the source's traversal logic actually runs.

**Assert on what lands in the destination.** Load into DuckDB and query it. That is the only way the dlt schema and column types are covered.

**Tests write nothing outside `tmp_path`.** Point DuckDB at a temp path and use `dev_mode=True`. Otherwise dlt leaves a `.duckdb` file in your working directory.

## Layout

- Tests live in `packages/<name>/tests/`. There is no root test suite and no root `conftest.py`.
- Each package configures pytest itself. One `pytest` run per package. A package can change its settings without affecting a sibling.
- Use `--import-mode=importlib` and put `__init__.py` in test folders. Two packages will eventually both have a `test_sites.py`, and the default import mode turns that into a collection error.
- Do not build a shared test-helper package before the third package needs one. Two copies of a fixture cost less than a dependency between packages.

## Coverage

Measure it, print it, do not gate on it: `--cov --cov-report=term-missing`.

A minimum percentage would measure how much mapping code you wrapped in a test, not whether the mapping is correct. Nobody comparable enforces one — dlt measures no coverage at all, and `pytest` itself sets `project: false`.

## Static checks

- Format, lint, types and tests are separate CI jobs that run at the same time. You see every problem after one push instead of four.
- Type-check `tests/` as well as `src/`. For a source package, the important statements about data shape are in the tests.
- Pin the pyright version. It releases weekly, and a new check can fail an unrelated pull request.
- Use pyright's default `standard` mode. `basic` is weaker than the tool's own default.

## Live tests are optional, and per package

We do **not** test against a live supplier API as standard, and we run no scheduled job.

If a supplier's API is public and open, and the package author wants live tests, put them in `tests/live/` and exclude that folder from the default run:

```toml
[tool.pytest.ini_options]
addopts = ["--ignore=tests/live"]
```

Run them by hand with `pytest tests/live`. That is the whole mechanism — no markers, no hooks, no credentials in CI.

This is a deliberate trade. Detecting supplier changes automatically needs credentials, scheduled jobs, alert routing and a schema-comparison step. That is a lot of machinery for every contributor to learn, and it does not pay for itself at our size. We accept that we may learn about a supplier change from a member company rather than from a test.

## Not adopted

Do not add these without a concrete reason:

- **A scheduled job that calls the supplier's API.** See above.
- **Recorded HTTP cassettes** (VCR and similar). None of dlt, Airbyte, Meltano, stripe-python or botocore use them. They hold secrets, break when a URL changes, and go stale without telling you.
- **CI that works out which packages changed.** A plain loop over `packages/*/` is correct here. Revisit when CI gets slow, not when the package count grows.
- **Coverage services, acceptance-test harnesses, snapshot-test libraries, schema fuzzers.** All solve problems we do not have.
