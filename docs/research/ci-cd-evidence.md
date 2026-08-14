# Evidence for the CI/CD decisions

Background reading for [`ci-cd.md`](./ci-cd.md). You don't need this to work here — read it when you want to challenge a decision or check we didn't make something up.

Researched 2026-08-14 against primary sources only: project source code read directly, official tool docs, PEPs, and GitHub's and PyPI's own documentation. Four code bases were read end to end — **Airbyte's Python CDK** and connector repo, **Meltano's Singer SDK**, **dlt** and **dlt-hub/verified-sources**, and **stripe-python** and **botocore**.

Two results are worth knowing up front, because they contradict what most people assume:

- **None of those projects use recorded HTTP cassettes.**
- **None of them enforce a minimum coverage percentage.**

---

## 1. How we replace HTTP

dlt is built on the `requests` library. `requests-mock` replaces the transport layer underneath it ([docs](https://requests-mock.readthedocs.io/en/latest/overview.html)).

The clearest example is dlt's own test fixture, [`dlt-hub/dlt:tests/sources/rest_api/conftest.py`](https://github.com/dlt-hub/dlt/blob/devel/tests/sources/rest_api/conftest.py):

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

About 45 routes, covering five different pagination styles. Note what dlt mocks: `requests`, not its own client. Airbyte does the same — its `HttpMocker` is a `requests_mock.Mocker` with extra checks ([source](https://github.com/airbytehq/airbyte-python-cdk/blob/main/airbyte_cdk/test/mock_http/mocker.py)):

```python
def _validate_all_matchers_called(self) -> None:
    for matcher in self._get_matchers():
        if not matcher.has_expected_match_count():
            raise ValueError(f"Invalid number of matches for `{matcher}`")
```

That method is where our "an unused mock fails the test" rule comes from. stripe-python and botocore's `Stubber` behave the same way.

Airbyte keeps sample responses as files and includes error cases: [`400.json`, `401.json`, `429.json`, `500.json`](https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-stripe/unit_tests/resource/http/response).

**Why not mock the client.** If you replace dlt's `RESTClient` with a `MagicMock`, the test proves your code calls your mock. Pagination, authentication, retries and the mapping from response to table never execute — and that's where source-package bugs live.

## 2. Why not cassettes

| Project | HTTP replacement | Cassettes? |
|---|---|---|
| `airbytehq/airbyte-python-cdk` | `requests-mock` | No |
| `meltano/sdk` | `requests-mock` | No |
| `dlt-hub/dlt` | `requests-mock` | No |
| `stripe/stripe-python` | a local mock server | No |
| `boto/botocore` | its own stubber | No |
| `DataDog/datadogpy` | `vcrpy` | Yes — 66 |
| `PyGithub/PyGithub` | its own record/replay | Yes — 1000+ |

The two that do use them show the cost. datadogpy has to strip headers and query parameters from every file, and needs an extra file per cassette to freeze time so requests still match ([conftest](https://github.com/DataDog/datadogpy/blob/master/tests/integration/conftest.py)). PyGithub maintains over a thousand replay files and a custom `--record` flag.

Cassettes also match on exact URL, headers and body, so they break on harmless changes — and they hold whatever secrets were in the original traffic.

## 3. Coverage

coverage.py's `fail_under` has a trap worth knowing: at the default precision, 99.6% displays as "100%" and still fails a threshold of 100 ([config docs](https://coverage.readthedocs.io/en/latest/config.html)).

| Project | Minimum coverage |
|---|---|
| `dlt-hub/dlt` | None — measures no coverage at all |
| `dlt-hub/verified-sources` | None |
| `stripe/stripe-python` | None |
| `boto/botocore` | Measures it, no threshold |
| `airbytehq/airbyte-python-cdk` | Measures and prints it, no threshold |
| `pytest-dev/pytest` | `project: false` |
| `apache/airflow` | `informational: true` |
| httpx, attrs, structlog | 100% — but they count their own test files as source |

Airbyte's setup says it best: a coverage task exists, and `test-all` doesn't call it ([source](https://github.com/airbytehq/airbyte/blob/master/poe-tasks/poetry-connector-tasks.toml)).

**Warning for future readers:** `attrs` and `structlog` contain `fail-under = 100` under `[tool.interrogate]`. That's *docstring* coverage, not test coverage. Don't cite them as evidence.

## 4. Static checks

| Project | Type checker |
|---|---|
| `dlt-hub/dlt` | Own job, blocks the test jobs. Checks `dlt tests tools`. |
| `airbytehq/airbyte-python-cdk` | Own job, parallel to tests |
| `meltano/sdk` | Own job |
| `stripe/stripe-python` | Own job, parallel to tests, version pinned |
| `boto/botocore` | None |

No project runs the type checker inside pytest.

We run checks in parallel, like stripe-python and Meltano. dlt runs lint first and tests afterwards, which is the minority choice and costs an extra round trip for every typo.

Two details from [pyright's docs](https://github.com/microsoft/pyright/blob/main/docs/configuration.md): the default mode is `standard`, so setting `basic` is *weaker than the default*; and its [CI guide](https://github.com/microsoft/pyright/blob/main/docs/ci-integration.md) shows an explicit version pin, because pyright ships weekly and new checks can fail unrelated PRs.

## 5. Where the version lives

`setuptools-scm` can derive the version from the tag, and it does work with our tag format — its docs document `tag.prefix` for exactly this ([config](https://setuptools-scm.readthedocs.io/en/latest/config/)). We tested it: a throwaway two-package workspace tagged `pkg-a/v0.3.0` and `pkg-b/v1.5.0` built both correctly, with no file leakage between packages.

We chose the written version anyway. It's visible in the PR diff next to the changelog entry, `uv version --package <name> --bump <part>` does the edit for you, and the one real benefit of `setuptools-scm` — that tag and version can't disagree — we get from a three-line CI check instead, without needing full-history checkouts.

## 6. The tag format

[`ing-bank/ordeq`](https://github.com/ing-bank/ordeq) is almost exactly our situation: a uv workspace with several packages, published to PyPI. Its tags are `ordeq-yaml/v1.0.2`, `ordeq-viz/v1.3.1`, and its release workflow:

```yaml
on:
  push:
    tags:
      - ordeq-*/v*
...
      - run: echo "PACKAGE_NAME=${GITHUB_REF_NAME%%/*}" >> $GITHUB_ENV
```

There's a technical reason to prefer `/` too. GitHub's docs: "`*`: Matches zero or more characters, but does not match the `/` character" ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet)). So `dlt-source-aquabyte/v*` matches one package and nothing else.

## 7. Changelogs

Keep a Changelog explains why not to generate one from commits: commit logs "are full of noise. Things like merge commits, commits with obscure titles, documentation changes", whereas "a changelog entry is to document the noteworthy difference, often across multiple commits" ([keepachangelog.com](https://keepachangelog.com/en/1.1.0/)).

With few packages, automation would buy little and would require a commit-message convention from everyone.

## 8. Two bugs we fixed

The earlier release proposal, [Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20), had two real bugs. Both are fixed in `release.yml`.

**Bug 1 — wrong index.** The proposal looked for `-rc` or `-dev` in the tag. `contains()` examines the whole tag, and the tag starts with the package name ([expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions)).

| Tag | Should go to | Proposal sent it to |
|---|---|---|
| `dlt-source-devices/v2.0.0` | PyPI | **TestPyPI** — name contains `-dev` |
| `dlt-source-y/v1.0.0b2` | TestPyPI | **PyPI** — a real pre-release, but no `-rc`/`-dev` |

The second row is the dangerous one: a test version published permanently to the real index.

**Bug 2 — nothing compared the tag with the version.** The workflow publishes whatever `pyproject.toml` says; the tag only selects the package. So tagging `v0.3.0` while the file said `0.1.0` published the wrong version. `encode/httpx` guards this in `scripts/publish`:

```sh
if [ "refs/tags/${VERSION}" != "${GITHUB_REF}" ] ; then
  echo "GitHub Ref '${GITHUB_REF}' did not match package version '${VERSION}'"
  exit 1
fi
```

**And one more, in the instructions rather than the file:** `git push --tags`. GitHub sends no push event when more than three tags arrive together, so the release just doesn't run, with no error. Push one tag by name.

## 9. How we publish

From PyPI's docs ([adding a publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/), [using one](https://docs.pypi.org/trusted-publishers/using-a-publisher/)):

- A publisher is identified by repo owner, repo name, **workflow filename** and **environment name**.
- `id-token: write` is required, at **job** level — PyPI calls workflow level "discouraged".
- A pending publisher "does **not** create a project or reserve a project's name **until** it is actually used to publish".
- TestPyPI is a separate service with its own account and its own publisher registration.

**Why not `uv publish`.** uv's own docs: "`uv publish` does not currently generate attestations; attestations must be created separately before publishing" ([package guide](https://github.com/astral-sh/uv/blob/main/docs/guides/package.md)). The PyPA action creates and uploads them automatically ([attestations](https://docs.pypi.org/attestations/producing-attestations/)).

There's a second reason. `--trusted-publishing` defaults to `automatic`, which uv's source describes as: "Attempt trusted publishing when we're in a supported environment, **continue if that fails**." A broken setup fails silently.

**Why environment names are fixed text.** An expression works, but GitHub creates an environment that doesn't exist yet "with no protection rules or secrets" — so a new package name would publish with no approval at all.

**Action versions**, checked against the GitHub API on 2026-08-14:

| Action | Tag |
|---|---|
| `actions/checkout` | v7.0.1 |
| `astral-sh/setup-uv` | v10.0.1 |
| `actions/upload-artifact` | v7.0.1 |
| `actions/download-artifact` | v8.0.1 |
| `pypa/gh-action-pypi-publish` | v1.14.2 |

Pin the publish action to a commit SHA rather than a tag — its own docs ask for this, and it holds our PyPI identity.

## 10. The approval step

We checked via the GitHub API: the org is on the **Free** plan and this repo is **private**. GitHub's docs ([environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)):

> "If you are on a GitHub Free, GitHub Pro, or GitHub Team plan, required reviewers are only available for public repositories."
> "If you are using GitHub Free, environment secrets are only available in public repositories."

The approval step is the safety control for the whole release process, and it currently doesn't function. The three options are in [ci-cd.md](./ci-cd.md#one-thing-still-to-decide).

## 11. What we didn't verify

Read this before treating anything above as settled.

1. **Branch protection settings.** These live in repo settings, not in code. We can only prove a check blocks something when a workflow says `needs:`.
2. **Changelog tooling.** We didn't confirm how `python-semantic-release`, `commitizen` or `towncrier` handle per-package versions in a monorepo. Our choice rests on the Keep a Changelog reasoning and team size, not a completed comparison.
3. **A broad tag-format survey.** One agent didn't finish. Section 6 rests on `ing-bank/ordeq` plus release-please's default.
4. **CI structure.** The agent researching matrices, path filters, merge queues and dependency tooling stopped early. Those choices rest on GitHub's docs and the other two studies. Revisit if you disagree with the CI design.
5. **GitHub's behaviour on Free + private.** We don't know whether it refuses to create an environment or creates an unprotected one. Check Settings → Environments before choosing an option in section 10.
6. **dlt test fixtures.** Published `dlt` 1.30.0 declares no `pytest11` entry point, so it ships no pytest fixtures. Write your own.
