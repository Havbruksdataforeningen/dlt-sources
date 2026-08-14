# Testing, versioning and releasing a multi-package Python monorepo

Researched 2026-08-14 against primary sources only: project source repositories read directly, official tool documentation, PEPs, PyPA specifications, GitHub's own Actions documentation, and PyPI's own docs. Secondary write-ups were deliberately excluded. Four connector/SDK codebases were read end to end — **Airbyte's Python CDK and connector monorepo**, **Meltano's Singer SDK**, **dlt itself and dlt-hub/verified-sources**, and **stripe-python / botocore** as HTTP-client reference points.

This is the *why*. The rules distilled from it are in [`docs/agents/testing.md`](../agents/testing.md) and [`docs/agents/releasing.md`](../agents/releasing.md); the automation is in [`.github/workflows/`](../../.github/workflows/).

## TL;DR

Split tests by **directory** (`unit/` never touches the network, `live/` never runs on a PR) and stamp the marker from the path so nobody can forget it. Fake HTTP at the **transport** boundary with `requests-mock` — not by mocking dlt's `RESTClient`, which tests nothing but your own call sites. **No cassettes and no coverage floor**: neither is used by any comparable project. Catch upstream drift with a **committed golden schema plus a nightly diff**, run under a `freeze` contract while production stays on `evolve`. Run lint, format, types and tests as **parallel named jobs** behind a single aggregate required check. Version each package **independently**, tag `<package>/vX.Y.Z`, keep the version **static in `pyproject.toml`**, and guard in CI that the tag agrees with it. Build with `uv build --no-sources`, publish with **`pypa/gh-action-pypi-publish`** (not `uv publish` — no attestations, and it swallows OIDC failures by default), via **Trusted Publishing** with no stored tokens.

**One blocker.** The maintainer-approval gate cannot work today: the org is on GitHub Free and the repo is private, and required reviewers are public-repo-only on that plan. See §9.

---

## 1. Five findings that should reset expectations

These are the results most likely to contradict what a reasonable engineer would assume going in.

1. **No connector framework of note uses VCR-style cassettes.** Airbyte's CDK, Meltano's SDK, dlt, stripe-python and botocore all use `requests-mock` or an equivalent transport-level fake driven by hand-written JSON. Zero of the five have a `cassettes/` directory.
2. **No connector framework of note enforces a coverage threshold.** dlt and dlt-hub/verified-sources measure no coverage at all. Airbyte's CDK measures and prints it without a gate. The hard-100% projects (httpx, attrs, structlog, FastAPI) get there by counting their own test files as covered source — a different game.
3. **"Integration" in these projects usually still means offline.** dlt's [`tests/sources/rest_api/integration/test_offline.py`](https://github.com/dlt-hub/dlt/blob/devel/tests/sources/rest_api/integration/test_offline.py) is 55 tests through the full source→pipeline stack with no network. It means *components wired together*, not *real API*.
4. **Scheduled live-API runs are rarer than assumed.** dlt, verified-sources, stripe-python, botocore and airbyte-python-cdk have **no scheduled test workflow at all**. Meltano is the exception. A nightly canary is justified here by our specific risk, not by industry default.
5. **Type checking is universally a separate CI job, never inside pytest** — in all five projects, without exception.

---

## 2. The unit / live split

| Project | How the split is made |
|---|---|
| Airbyte connectors | **Directories** — `unit_tests/` and `integration_tests/` per connector |
| botocore | **Directories** — `tests/unit/`, `functional/`, `integration/`, `acceptance/` |
| datadogpy | **Directories** — `tests/unit/` vs `tests/integration/` |
| Meltano SDK | Markers, but **applied automatically from the directory name** |
| dlt core | Directories plus markers for orthogonal concerns (`serial`, `forked`) |

Meltano's hook, [`meltano/sdk:tests/conftest.py`](https://github.com/meltano/sdk/blob/main/tests/conftest.py):

```python
def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]):
    for item in items:
        rel_path = pathlib.Path(item.fspath).relative_to(config.rootpath)
        test_dir = rel_path.parts[1]
        if test_dir.startswith("external"):
            item.add_marker("external")
```

This is the pattern worth copying: directory membership is the single source of truth, and the marker — which is what CI selects on — is derived from it. There is no way to forget a decorator.

Meltano then makes a bare `pytest` safe by deselecting the expensive tiers in config rather than on the CI command line, so a laptop and CI agree by construction ([`pyproject.toml`](https://github.com/meltano/sdk/blob/main/pyproject.toml)):

```toml
addopts = ["--durations=10", "-m", "not contrib and not external and not packages", "-ra"]
strict = true
```

pytest's own documentation prescribes only the mechanism, not the taxonomy — register markers so `pytest --markers` is meaningful, and note that "typos in function markers are treated as an error if you use the `strict_markers` configuration option" ([docs](https://docs.pytest.org/en/stable/example/markers.html)).

**Trap worth recording:** [`airbytehq/airbyte-python-cdk:pytest.ini`](https://github.com/airbytehq/airbyte-python-cdk/blob/main/pytest.ini) filters CI on `flaky`, `super_slow` and `linting` — none of which are declared. Without strict markers those filters silently match nothing.

---

## 3. Faking HTTP

### The libraries, from their own documentation

- **`requests-mock`** — "at its core is simply a transport adapter that can be preloaded with responses" ([docs](https://requests-mock.readthedocs.io/en/latest/overview.html)). Ships a pytest fixture needing no import. **`requests` only** — which is what dlt's REST client uses.
- **`responses`** — a `requests` mocker ([repo](https://github.com/getsentry/responses)). Also records, via an underscore-prefixed API.
- **`respx`** — **httpx only**, therefore irrelevant here.
- **`vcrpy` / `pytest-recording`** — record and replay. `pytest-recording` "uses the `none` VCR recording mode by default to prevent unintentional network requests" ([repo](https://github.com/kiwicom/pytest-recording)).

### Who actually uses what

| Project | HTTP fake | Cassettes? |
|---|---|---|
| `airbytehq/airbyte-python-cdk` | `requests-mock`, wrapped in a public `HttpMocker` | **No** |
| `airbytehq/airbyte` connectors | `requests-mock` via `HttpMocker` + `find_template` | **No** — 25 JSON templates for source-stripe |
| `meltano/sdk` | `requests-mock`, plus `responses` for ordered retry tests | **No** |
| `dlt-hub/dlt` | `requests-mock` + a hand-rolled `APIRouter` | **No** |
| `stripe/stripe-python` | `stripe-mock`, a local server from the OpenAPI spec | **No** |
| `boto/botocore` | Hand-rolled stubber on the `before-send` event | **No** |
| `DataDog/datadogpy` | `pytest-vcr` + `vcrpy` | Yes — 66 |
| `PyGithub/PyGithub` | Hand-rolled record/replay | Yes — 1000+ |

The single most on-point precedent is dlt's own REST-source fixture, [`dlt-hub/dlt:tests/sources/rest_api/conftest.py`](https://github.com/dlt-hub/dlt/blob/devel/tests/sources/rest_api/conftest.py):

```python
MOCK_BASE_URL = "https://api.example.com"
router = APIRouter(MOCK_BASE_URL)

@pytest.fixture(scope="function")
def mock_api_server():
    with requests_mock.Mocker() as m:
        @router.get(r"/posts(\?.*)?$")
        def posts(request, context):
            return paginate_by_page_number(request, generate_posts())
        router.register_routes(m)
        yield m
```

~45 route handlers covering every pagination style — page-number, offset/limit, cursor, header-`Link`, relative next-url — and every auth style. Note that the data is **generated**, not recorded.

Airbyte's `HttpMocker` is literally `requests_mock.Mocker` with assertions added ([source](https://github.com/airbytehq/airbyte-python-cdk/blob/main/airbyte_cdk/test/mock_http/mocker.py)):

```python
class HttpMocker(contextlib.ContextDecorator):
    def __init__(self) -> None:
        self._mocker = requests_mock.Mocker()

    def _validate_all_matchers_called(self) -> None:
        for matcher in self._get_matchers():
            if not matcher.has_expected_match_count():
                raise ValueError(f"Invalid number of matches for `{matcher}`")
```

That last method is the point: **an unused mock fails the test**. stripe-python raises on anything unstubbed; botocore's `Stubber` exposes `assert_no_pending_responses()` ([docs](https://docs.aws.amazon.com/botocore/latest/reference/stubber.html)).

Airbyte resolves fixture data by convention rather than by import, so one shared helper serves every connector ([`response_builder.py`](https://github.com/airbytehq/airbyte-python-cdk/blob/main/airbyte_cdk/test/mock_http/response_builder.py)) — and the committed files include [`400.json`, `401.json`, `429.json`, `500.json`](https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-stripe/unit_tests/resource/http/response).

### Why not to mock the framework's client

Replacing dlt's `RESTClient` with a `MagicMock` proves only that your code calls a mock. Pagination, auth, retry and response→record mapping — where connector bugs actually live — never execute. dlt mocks `requests`; Airbyte mocks `requests` so the real retrievers and paginators run; botocore hooks `before-send` specifically so the request is fully built *and signed* first.

### Why not cassettes

Cassettes bind tests to exact URL, query, header and body matching; they carry secrets requiring scrubbing; and they rot invisibly. The maintenance tax is visible in the projects that do use them: datadogpy needs `filter_headers`/`filter_query_parameters` config plus a `freezegun` `.frozen` sidecar per cassette so time-dependent requests still match ([conftest](https://github.com/DataDog/datadogpy/blob/master/tests/integration/conftest.py)); PyGithub maintains 1000+ replay files and a bespoke `--record` flag.

---

## 4. Catching upstream drift

The mechanism used everywhere is **commit a golden artifact, diff it on a schedule, fail on any difference.**

[`PyGithub:.github/workflows/openapi.yml`](https://github.com/PyGithub/PyGithub/blob/main/.github/workflows/openapi.yml) fetches GitHub's live OpenAPI spec daily and fails on changes:

```yaml
on:
  schedule: [{cron: '10 8 * * *'}]
  workflow_dispatch:
...
      - name: Fail on changes
        run: |
          if ! git diff --quiet openapi/main; then
            echo "Changes exist, please investigate"
            exit 1
          fi
```

[`airbytehq/airbyte`](https://github.com/airbytehq/airbyte/blob/master/.github/workflows/regenerate-agent-engine-api-spec.yml) does the same against a committed spec snapshot; [`huggingface_hub`](https://github.com/huggingface/huggingface_hub/blob/main/.github/workflows/update-inference-types.yaml) opens a PR instead of failing.

Meltano runs its live tier on a cron and guards against forks ([`test.yml`](https://github.com/meltano/sdk/blob/main/.github/workflows/test.yml)):

```yaml
  tests-external:
    if: ${{ !github.event.pull_request.head.repo.fork }}
    env:
      NOXSESSION: test-external
```

`langchain`'s integration workflow triggers on *only* `workflow_dispatch` + `schedule` ([source](https://github.com/langchain-ai/langchain/blob/master/.github/workflows/integration_tests.yml)), with `environment: "Scheduled testing"` and a repo-owner guard.

### Making failures actionable

[`element-hq/synapse`](https://github.com/element-hq/synapse/blob/develop/.github/workflows/twisted_trunk.yml):

```yaml
  open-issue:
    if: failure() && needs.check_repo.outputs.should_run_workflow == 'true'
      - uses: JasonEtco/create-an-issue@... # v2.9.2
        with:
          update_existing: true
```

`update_existing: true` is what stops a nightly filing thirty duplicate issues a month. scikit-image uses the same action; dbt-adapters uses Slack with an on-call mention group instead.

### Constraints from GitHub's own docs

All from [events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) and [secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets):

- Scheduled workflows run **only on the latest commit of the default branch** — hence `workflow_dispatch` is mandatory, not a convenience: without it a change to a cron workflow cannot be tested on a branch.
- The shortest interval is 5 minutes, and schedules "can be delayed during periods of high loads" — so pick a time off the hour.
- In a public repo, **schedules auto-disable after 60 days of inactivity**.
- "With the exception of `GITHUB_TOKEN`, secrets are not passed to the runner when a workflow is triggered from a forked repository."

### dlt's own drift primitives

- **Schema contracts** — modes `evolve`, `freeze`, `discard_row`, `discard_value`, over `tables` / `columns` / `data_type`. `freeze` raises `DataValidationError` naming the schema, table, column and offending item ([docs](https://dlthub.com/docs/general-usage/schema-contracts)). This is what makes "production absorbs new fields, the nightly shouts about them" a one-parameter difference.
- **`Schema.version_hash`** and **`Schema.to_pretty_yaml()`** ([source](https://github.com/dlt-hub/dlt/blob/devel/dlt/common/schema/schema.py)) — the golden artifact.
- **`add_limit(max_items, max_time)`** ([docs](https://dlthub.com/docs/general-usage/resource)) — bounds the canary.

**Honest limit.** Across PyGithub, huggingface_hub, airbyte, sentry, googleapis, stripe, openai-python, httpx, requests and others, **no well-known Python project was found that nightly fetches a third-party API's live response payloads, infers a schema, and alerts on drift.** Every real example diffs a *published spec* or *generated code*. The golden-schema approach is a synthesis of that pattern with dlt's first-party contract primitives — road-tested in its parts, not copied wholesale.

---

## 5. Coverage

coverage.py's own docs on `fail_under`: "A target coverage percentage. If the total coverage measurement is under this value, then exit with a status code of 2… **A setting of 100 will fail any value under 100, regardless of the number of decimal places of precision.**" And `precision` "also affects the interpretation of the `fail_under` setting" ([config docs](https://coverage.readthedocs.io/en/latest/config.html)) — so at the default `precision = 0`, 99.6% *displays* as 100% and still fails a `fail_under = 100`.

| Project | Policy |
|---|---|
| `dlt-hub/dlt` | **No coverage measured at all** |
| `dlt-hub/verified-sources` | **None** |
| `stripe/stripe-python` | **None** |
| `boto/boto3` | Collects none in CI |
| `airbytehq/airbyte-python-cdk` | Measured, printed, HTML artifact — **no gate** |
| `boto/botocore` | `--cov` + codecov upload, **no threshold** |
| `meltano/sdk` | No `fail_under`; codecov **patch** target 100% |
| `pytest-dev/pytest` | patch 100%, **`project: false`** |
| `apache/airflow` | `informational: true` |
| httpx, attrs, structlog, fastapi | Hard 100% — by counting test files as source |
| flask, requests, pydantic, pip, sqlalchemy, django | No gate |

Airbyte's coverage task is emblematic — it exists, and `test-all` does not call it ([source](https://github.com/airbytehq/airbyte/blob/master/poe-tasks/poetry-connector-tasks.toml)).

The conclusion: on connector code a project-wide floor measures how much mapping boilerplate you wrapped in a test, not whether the mapping is right. If a gate is ever wanted, gate the **diff** (a Codecov `patch` status), not the project — though at 1–5 packages the setup and flaky-upload failure mode outweigh the signal.

**Grep warning:** both `python-attrs/attrs` and `hynek/structlog` contain `fail-under = 100` under **`[tool.interrogate]`** — that is *docstring* coverage. Anyone auditing precedent by grepping `fail_under` will misread those two repos.

---

## 6. Layout and shared fixtures

From pytest's own documentation:

- "Generally, but especially if you use the default import mode `prepend`, it is strongly suggested to use a src layout"; and for new projects, "we recommend to use importlib import mode" ([good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)).
- Under `prepend`, "each test file needs to have a unique name compared to the other test files, otherwise pytest will raise an error" ([pythonpath](https://docs.pytest.org/en/stable/explanation/pythonpath.html)) — two packages will eventually both have `tests/test_sites.py`.
- "Tests are allowed to search upward… for fixtures, but can never go down" ([fixtures](https://docs.pytest.org/en/stable/reference/fixtures.html)) — which is exactly why a root `conftest.py` silently couples every package to a file no package's version pins.
- "Options from multiple `configfiles` candidates are never merged - the first match wins" ([customize](https://docs.pytest.org/en/stable/reference/customize.html)).

Airbyte gives each connector its own test manifest ([source-stripe](https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/unit_tests/pyproject.toml)). Shared machinery ships as an **importable plugin**, not a copied conftest — Meltano via an entry point:

```toml
[project.entry-points."pytest11"]
singer_testing = "singer_sdk.testing.pytest_plugin"
```

That approach provably never leaks into a published wheel: PEP 735 states "Build backends MUST NOT include Dependency Group data in built distributions as package metadata" ([PEP 735](https://peps.python.org/pep-0735/)), and uv states "Sources are only respected by uv" ([docs](https://docs.astral.sh/uv/concepts/projects/dependencies/)).

**Counter-example, deliberately:** `dlt-hub/verified-sources` puts 37 sources' tests in one root tree with three conftests and a shared `tests/utils.py` — and its own rules file warns "Avoid adding source-specific code to the shared `tests/utils.py`". That works because those sources are *not independently versioned or published*. It is the wrong model here.

**Isolation is a written rule in both dlt repos.** dlt's own testing rules: "Tests run in parallel! ALWAYS use test storage… unique pipeline names… Isolate pipelines with `dev_mode` or random `dataset_name`." verified-sources pins the destination with `DuckDbCredentials.database = ":pipeline:"` plus an autouse `drop_pipeline` fixture. This matters because dlt's DuckDB destination otherwise "creates a DuckDB database in the current working directory" named after the pipeline ([docs](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb)).

---

## 7. Static checks

| Project | Where the type checker sits |
|---|---|
| `dlt-hub/dlt` | Separate `lint` workflow that **gates** every test job; `mypy dlt tests tools` |
| `airbytehq/airbyte-python-cdk` | Separate `mypy-check` job, **parallel** to pytest; excludes `unit_tests/` |
| `meltano/sdk` | Separate `typing` job; runs both `mypy` and `ty` (pinned) |
| `stripe/stripe-python` | Separate `lint` job parallel to tests; **pyright is the gate**, pinned `1.1.336` |
| `boto/botocore` | **No type checker at all** |

stripe-python's `publish` job declares `needs: [build, test, lint]` — the checks are provably blocking. Meltano and airbyte-python-cdk run typing parallel to tests; dlt chains them, which is the minority position and costs a full CI round trip per typo.

Pyright's own docs: `typeCheckingMode` "default value for this setting is **`standard`**" ([configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)) — so a config saying `basic` is *weaker than the tool's default*, a silent downgrade if it predates the change. Its CI guide shows an explicit `version:` pin ([ci-integration](https://github.com/microsoft/pyright/blob/main/docs/ci-integration.md)); pyright ships weekly and new diagnostics turn unrelated PRs red.

---

## 8. Versioning and release

### Trusted Publishing

From [PyPI's own docs](https://docs.pypi.org/trusted-publishers/adding-a-publisher/):

- Publisher fields are repo owner, repo name, **workflow filename**, and optional **environment name**. Environment is "optional, but **strongly** recommended: with a GitHub environment, you can apply additional restrictions… such as requiring manual approval on each run by a trusted subset of repository maintainers."
- `id-token: write` "is mandatory for Trusted Publishing… you must provide this permission at either the job level (**strongly recommended**) or workflow level (**discouraged**)" ([using a publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)).
- A pending publisher "does **not** create a project or reserve a project's name **until** it is actually used to publish" ([creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)).
- Reusable workflows cannot be the trusted workflow; the minted token lives 15 minutes ([troubleshooting](https://docs.pypi.org/trusted-publishers/troubleshooting/)).
- TestPyPI is a **separate service** with its own account and its own registration ([packaging guide](https://packaging.python.org/en/latest/guides/using-testpypi/)).

**On dynamic environment names:** mechanically they work — `needs` is an allowed context in `jobs.<job_id>.environment` — but GitHub *implicitly creates* an unknown environment "with no protection rules or secrets", so a new package name silently yields an **ungated** publish path. Use static `pypi` / `testpypi` environments.

### `uv publish` vs `pypa/gh-action-pypi-publish`

From uv's own source, `--trusted-publishing` takes:

- `automatic` — "Attempt trusted publishing when we're in a supported environment, **continue if that fails**." This is the **default**, so passing it explicitly is a no-op. In `check_trusted_publishing`, a hard OIDC failure under `Automatic` returns `Ok(TrustedPublishResult::Ignored(err))` — **swallowed**.
- `always` — forces it; the error propagates.
- `never`.

On attestations, uv's docs say plainly: *"`uv publish` does not currently generate attestations; attestations must be created separately before publishing."* ([package guide](https://github.com/astral-sh/uv/blob/main/docs/guides/package.md)). The PyPA action does: *"attestations are generated and uploaded automatically by default, with no additional configuration necessary"* ([producing attestations](https://docs.pypi.org/attestations/producing-attestations/)).

**Verdict:** build with `uv build --package <pkg> --no-sources`, publish with the PyPA action. PEP 740 attestations plus metadata verification in one step, and the `automatic`-swallows-errors footgun disappears.

### Tag format

The strongest evidence is a near-exact peer: **[`ing-bank/ordeq`](https://github.com/ing-bank/ordeq)**, a real, actively published Python **uv-workspace monorepo** on PyPI. Its tags are `ordeq-yaml/v1.0.2`, `ordeq-viz/v1.3.1`, and its release workflow:

```yaml
on:
  push:
    tags:
      - ordeq-*/v*
...
      - run: echo "PACKAGE_NAME=${GITHUB_REF_NAME%%/*}" >> $GITHUB_ENV
```

A functional advantage of `/`: GitHub's filter-pattern docs state "`*`: Matches zero or more characters, but does not match the `/` character" ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet)) — so `dlt-source-aquabyte/v*` is an exact per-package selector.

Counterweight: `release-please` manifest mode defaults to `<component>-v<version>` ([docs](https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md)), and JS tooling uses `pkg@1.2.3`.

### Where the version lives

**`setuptools-scm` works cleanly with prefixed tags — verified two ways.** Its docs document `tag.prefix` as "A literal prefix that version tags must start with… Use this for monorepos or multi-package repositories where each package has its own tag namespace" ([config](https://setuptools-scm.readthedocs.io/en/latest/config/)). A throwaway two-package uv workspace was built with tags `pkg-a/v0.3.0` and `pkg-b/v1.5.0`: it produced `pkg_a-0.3.0` and `pkg_b-1.5.1.dev1+g…` with correct per-package isolation and no cross-package file leakage. `ing-bank/ordeq` does this in production.

**Recommendation is nonetheless the static version.** It stays visible in the PR diff next to the changelog entry, it is what nearly every large Python project does, and `uv version --package <pkg> --bump <part>` automates the edit (verified working, including `--short --frozen` to read it without a network round trip). setuptools-scm's real prize — eliminating tag/metadata drift — is obtainable with a three-line CI guard, without requiring `fetch-depth: 0`.

### Changelogs

Keep a Changelog's own rationale against generating from commits: they "are full of noise. Things like merge commits, commits with obscure titles, documentation changes", whereas "a changelog entry is to document the noteworthy difference, often across multiple commits" ([keepachangelog.com](https://keepachangelog.com/en/1.1.0/)). With a small package count, commit-derived changelogs buy little and cost a Conventional Commits mandate across shared history.

### Two confirmed defects in the earlier draft

Both issues in the [Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20) sketch are real.

**(a) Prerelease routing.** `contains()` is a plain, case-insensitive substring test over the whole ref ([expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions)):

| tag | correct | draft routes to |
|---|---|---|
| `dlt-source-devices/v2.0.0` | PyPI | **TestPyPI** — name contains `-dev` |
| `dlt-source-y/v1.0.0b2` | TestPyPI | **PyPI** — valid PEP 440 prerelease, no `-rc`/`-dev` |

The second is the dangerous one: a genuine prerelease published irrevocably to production.

**(b) No tag-vs-version guard.** Nothing stops tagging `v0.3.0` while `pyproject.toml` says `0.1.0`. `encode/httpx` guards exactly this in `scripts/publish`:

```sh
if [ "refs/tags/${VERSION}" != "${GITHUB_REF}" ] ; then
  echo "GitHub Ref '${GITHUB_REF}' did not match package version '${VERSION}'"
  exit 1
fi
```

**A third, unrelated to the draft:** `git push --tags` is unsafe as a documented step — GitHub creates no push event when more than three tags are pushed at once, so the release silently never runs. Push the one tag by name.

### Action versions, verified 2026-08-14

Verified via the GitHub API, each SHA corroborated by two endpoints.

| Action | Tag | SHA |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `astral-sh/setup-uv` | v10.0.1 | `20cfd1bf945f4377ade1205e4dbc17946fc9a30d` |
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |
| `pypa/gh-action-pypi-publish` | v1.14.2 | `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` |

`download-artifact` v8 makes digest mismatches **fatal** where they were previously a warning. The PyPA action's README advises pinning "to tagged versions or sha1 commit identifiers" rather than branch pointers — it holds the publishing identity, so pin the SHA.

---

## 9. Blocker: the approval gate cannot work today

Verified via the GitHub API: the `Havbruksdataforeningen` org is on the **Free** plan and `dlt-sources` is **private**. GitHub's documentation is unambiguous ([deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)):

> "If you are on a GitHub Free, GitHub Pro, or GitHub Team plan, required reviewers are only available for public repositories."
> "If you are using GitHub Free, environment secrets are only available in public repositories."

So the maintainer-approval gate — the safety mechanism the whole release design leans on — does not function as written. Three ways out:

1. **Make the repo public.** Cheapest, immediate, and matches every precedent cited here: pip, ruff, httpx and ordeq are all public. The packages go to public PyPI regardless.
2. **Upgrade the org plan.**
3. **Stay private and gate on tag creation** — restrict who may create tags matching the release pattern. PyPI's own security model suggests this: "if you use a tag-based publishing workflow… you can limit tag creation and modification to maintainers and higher" ([security model](https://docs.pypi.org/trusted-publishers/security-model/)). Weaker: it gates *who tags*, not a second pair of eyes at publish time.

This also affects the nightly canary, which needs credentials: on Free + private, environment secrets are unavailable, so it must use repository secrets.

---

## 10. What is deliberately not adopted

Each is a real practice that a much larger project needs and this one does not — yet.

- **Changed-package CI matrices.** Airbyte computes affected connectors with `dorny/paths-filter`; verified-sources with a `git diff | sed` pipeline. Both have 37–300+ connectors. A flat loop over `packages/*/` is correct here; the trigger to change is CI wall-clock, not package count.
- **An acceptance-test harness.** Airbyte's CAT is a governance tool for hundreds of third-party contributions.
- **A spec-derived mock server.** stripe-mock is elegant, but its own README concedes it is stateless, that responses are "hardcoded, and will not necessarily represent realistic responses", and that testing specific errors "is currently not supported. It will return a success response instead". It validates *request* shape — the half a connector cares least about.
- **Schemathesis.** It generates inputs from a schema to find bugs in the *provider*. Wrong direction for a consumer.
- **Snapshot-testing frameworks.** For one golden schema per resource, a plain comparison plus an update flag suffices.
- **A shared test-utils package before the third package.**
- **Blanket `filterwarnings = ["error"]`.** dlt ships its own `DeprecationWarning` noise which a dependent inherits.
- **Codecov.** Setup cost and flaky-upload failures outweigh the signal at this size.

---

## What could not be verified

1. **Branch-protection state anywhere.** Required-check configuration is a repo setting, not in-tree. Blocking-ness is only provable where encoded as `needs:` — dlt's lint→tests edge, stripe's `publish: needs: [build, test, lint]`.
2. **Whether a nightly response-payload drift job exists in any well-known Python project.** Extensive search found only spec-diff and codegen-diff jobs. §4's golden-schema approach is flagged as a synthesis.
3. **Per-package monorepo support in `python-semantic-release`, `commitizen` and `towncrier`** — the fetched docs did not contain the needed statements. The hand-written-changelog recommendation rests on Keep a Changelog's rationale and team size, not a completed comparison.
4. **A broad tag-format survey** across `googleapis/google-cloud-python`, `Azure/azure-sdk-for-python`, `apache/airflow` and the JS exemplars — that sub-investigation did not return. §8's tag recommendation rests on `ing-bank/ordeq` plus the release-please default.
5. **The Go modules spec sentence** on `sub/dir/vX.Y.Z` tagging — the page truncated on fetch.
6. **Whether GitHub refuses to create an environment at all on Free + private, or creates an unprotected one.** Worth a two-minute check in Settings → Environments before choosing between the §9 options.
7. **CI orchestration research is thinner than the rest.** The agent covering matrix-vs-loop, path filtering, required checks, merge queues and dependency automation terminated on a session limit. §10's first bullet and the workflow shapes rest on what the other two investigations surfaced plus GitHub's own docs, not on a completed survey. **Worth revisiting** if the CI design is questioned.
8. **`dlt-plus-tests`.** A dlt+ pytest plugin appears to exist; its docs page 404'd. What *was* verified: published open-source `dlt` 1.30.0 declares **no `pytest11` entry point**, so it ships no pytest fixtures — plan on writing your own.
