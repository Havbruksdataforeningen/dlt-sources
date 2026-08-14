# How we test, version and release

Written 2026-08-14.

This document tells you how we work, and why we chose to work this way. Read it when you join the team. Read it again before you change the build system.

The short rules are in two other files. Read them when you do the work:

- [`docs/agents/testing.md`](../agents/testing.md) — the testing rules.
- [`docs/agents/releasing.md`](../agents/releasing.md) — the release rules.

This document uses the words defined in [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md). If a word here is new to you, look there first. Use the same words when you write code, tests and issues.

This document has three parts:

1. [Why we made these choices](#1-why-we-made-these-choices)
2. [What you get](#2-what-you-get)
3. [Our decisions](#3-our-decisions)
4. [The evidence](#4-the-evidence) — read this only if you want to challenge a decision.

---

## 1. Why we made these choices

We build **source packages**. Each source package reads data from one supplier API. Our member companies install these packages from PyPI. They use them in their own data pipelines.

Two facts control every decision in this document.

**Fact 1. The risk is the supplier API. It is not our code.**

A source package contains little complex logic. It sends a request. It reads the response. It gives the data to dlt. The usual failure is different: the supplier changes the API, and our package reads it incorrectly. Our tests must find this failure. Tests that only check our own logic do not help much.

**Fact 2. Each source package has its own version and its own users.**

A member company installs `dlt-source-aquabyte`. That company does not know that other packages exist in the same repository. It must not see them. A new version of one package must not force a new version of a different package.

We keep all packages in one repository. But the repository must stay invisible to the consumer.

---

## 2. What you get

These are the promises this system makes to you. If a change breaks one of these promises, the change is wrong.

**You work on one source package only.**
You do not read the other packages. You do not run their tests. You do not know their versions. Each package has its own tests, its own configuration, and its own version number.

**You do not write CI configuration.**
To add a new source package, you add a folder. The workflows find it. You do not edit a workflow file. You do not add a job. The only manual step is the one-time PyPI setup, in [`releasing.md`](../agents/releasing.md).

**The standards are the same everywhere.**
All packages use the same formatter, the same linter, and the same type checker. You do not decide these things for each package. You do not argue about them in a review.

**You get examples to copy.**
Every package solves the same problem in the same way. When you build a new source package, you read an existing one first. This also helps the agents: they have working reference packages in the same repository, so they do not invent a new structure.

**A green pull request means the package is ready to release.**
CI builds every package on every pull request. A packaging error appears in the pull request, not on release day.

**A release is one tag.**
You change the version, you write the changelog entry, you push one tag. A maintainer approves. There are no other steps.

---

## 3. Our decisions

Each decision is short. Each links to the evidence for it.

### 3.1 Testing

| Decision | Why |
|---|---|
| Tests are in two folders: `tests/unit/` and `tests/live/`. `unit/` must never use the network. `live/` uses the real supplier API. | A folder is easy to see and hard to forget. [Evidence](#41-the-two-test-groups) |
| A hook in `conftest.py` adds the marker from the folder name. You never write the marker by hand. | You cannot forget a marker that you do not write. [Evidence](#41-the-two-test-groups) |
| The command `pytest` alone must never use the network. The setting is in the package configuration, not in the CI command. | Your computer and CI then behave the same way. [Evidence](#41-the-two-test-groups) |
| We replace HTTP with `requests-mock`. We do **not** replace the dlt `RESTClient` object. | If you replace the client, you only test that your code calls your own mock. Pagination, authentication and data mapping do not run. That is where the errors are. [Evidence](#42-how-we-replace-http) |
| We do not record HTTP traffic to cassette files. | Cassettes hold secrets, they break when a URL changes, and they become incorrect without a signal. [Evidence](#42-how-we-replace-http) |
| Test data is in `tests/fixtures/*.json`. There is one file for each endpoint, and one file for each error status. | The files are easy to read and easy to correct. [Evidence](#42-how-we-replace-http) |
| A request that no mock expects fails the test. A mock that no request uses also fails the test. | An unused mock shows that the test does not do what you think. [Evidence](#42-how-we-replace-http) |
| Tests load data into DuckDB and then query it. | This is the only way to test the schema that dlt creates. [Evidence](#42-how-we-replace-http) |
| We do not set a minimum coverage percentage. We measure coverage and print it. | On this kind of code, a percentage shows how much mapping code you put in a test. It does not show if the mapping is correct. [Evidence](#44-coverage) |
| The type checker runs as its own CI job. Format, lint, types and tests run at the same time. | You then see all the problems after one push, not after four. [Evidence](#45-static-checks) |
| We check the types of `tests/` and `src/`. | For a source package, the important statements about data shape are in the tests. [Evidence](#45-static-checks) |

### 3.2 Finding supplier API changes

This is the most important part of the system, because of Fact 1.

| Decision | Why |
|---|---|
| We save the dlt schema of each resource to a file in `tests/schemas/`. | The file shows the agreed shape of the data. [Evidence](#43-how-we-find-supplier-api-changes) |
| The unit tests compare the test data against this file. This finds **our** errors. | A change in our code that changes the schema then fails the pull request. [Evidence](#43-how-we-find-supplier-api-changes) |
| A daily job compares the **real** API against this file. This finds **the supplier's** changes. | We learn about a change before a member company does. [Evidence](#43-how-we-find-supplier-api-changes) |
| The daily job uses the dlt `freeze` contract. The released package uses `evolve`. | A new field must not stop a member company's pipeline. But it must produce a message for us. This is one parameter. [Evidence](#43-how-we-find-supplier-api-changes) |
| The live tests fail if the credentials are absent. They do not skip. | A test that skips without a message gives false confidence. [Evidence](#43-how-we-find-supplier-api-changes) |
| If the daily job fails, it opens one GitHub issue. If the issue is open, it updates that issue. | A failed job that nobody looks at is not a warning. One issue is a warning. Thirty issues are noise. [Evidence](#43-how-we-find-supplier-api-changes) |

### 3.3 Versioning

| Decision | Why |
|---|---|
| Each source package has its own version number. | See Fact 2. A consumer of one package must not get a new version because a different package changed. |
| The version is a fixed value in `pyproject.toml`. Change it with `uv version --package <name> --bump <part>`. | You then see the version in the pull request, next to the changelog entry. [Evidence](#46-where-the-version-number-is) |
| The tag format is `<package-name>/vX.Y.Z`. | The character `/` does not match the `*` character in a GitHub filter. The tag is therefore an exact selector for one package. [Evidence](#47-the-tag-format) |
| Changelogs are written by a person, in each package. | A commit list contains merge commits and unclear titles. A changelog entry describes one change for the consumer. [Evidence](#48-changelogs) |

### 3.4 Releasing

| Decision | Why |
|---|---|
| CI compares the tag against the version in `pyproject.toml`. If they are different, the release stops. | PyPI never permits you to use a version number a second time. A wrong tag is permanent. [Evidence](#49-two-errors-we-corrected) |
| The choice between PyPI and TestPyPI uses the PEP 440 version, not the text of the tag. | Text matching is incorrect in both directions. See the table in [4.9](#49-two-errors-we-corrected). |
| Push one tag by name. Do not use `git push --tags`. | GitHub sends no event if more than three tags arrive together. The release then does not start, and there is no error. [Evidence](#49-two-errors-we-corrected) |
| We publish with `pypa/gh-action-pypi-publish`. We do not publish with `uv publish`. | `uv publish` does not make attestations. Its default setting also hides authentication failures. [Evidence](#410-how-we-publish) |
| We use PyPI Trusted Publishing. We store no PyPI tokens. | There is no secret to steal, and no secret to rotate. [Evidence](#410-how-we-publish) |
| The environment names `pypi` and `testpypi` are fixed text. They do not contain a package name. | GitHub creates an unknown environment automatically, **with no protection**. A new package name would then publish without approval. [Evidence](#410-how-we-publish) |

### 3.5 One decision you must make

**The approval step does not work today.** The organization uses the GitHub Free plan, and this repository is private. On that plan, GitHub gives required reviewers only to public repositories.

You have three options:

1. **Make the repository public.** This is the cheapest option. It gives us the approval step immediately. The packages go to public PyPI, so the code is not secret.
2. **Change the organization plan.**
3. **Keep the repository private, and control who can create a release tag.** This is weaker. It controls who starts a release. It does not give a second person a check before the release.

More detail is in [4.11](#411-the-approval-step).

---

## 4. The evidence

Read this part only if you want to challenge a decision. Each section gives the source.

We read four code bases completely for this: the **Airbyte Python CDK** and its connector repository, the **Meltano Singer SDK**, **dlt** and **dlt-hub/verified-sources**, and **stripe-python** and **botocore**.

Three results are different from what most people expect:

- **No comparable project uses cassette files.** Not one of those five.
- **No comparable project sets a minimum coverage percentage.** dlt measures no coverage at all.
- **Most comparable projects have no daily test job.** We have one because of Fact 1, not because it is usual.

### 4.1 The two test groups

Airbyte, botocore and datadogpy all divide their tests by folder. Meltano uses markers, but it adds the marker from the folder name automatically. This is the useful part, from [`meltano/sdk:tests/conftest.py`](https://github.com/meltano/sdk/blob/main/tests/conftest.py):

```python
def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]):
    for item in items:
        rel_path = pathlib.Path(item.fspath).relative_to(config.rootpath)
        test_dir = rel_path.parts[1]
        if test_dir.startswith("external"):
            item.add_marker("external")
```

Meltano also removes the slow tests in the package configuration, not in the CI command ([`pyproject.toml`](https://github.com/meltano/sdk/blob/main/pyproject.toml)):

```toml
addopts = ["--durations=10", "-m", "not contrib and not external and not packages", "-ra"]
strict = true
```

Set `strict = true`. If you do not, pytest accepts a marker that does not exist. [`airbytehq/airbyte-python-cdk`](https://github.com/airbytehq/airbyte-python-cdk/blob/main/pytest.ini) selects on three markers that it never declares. Those filters select nothing, and nobody sees a message.

### 4.2 How we replace HTTP

dlt uses the `requests` library. `requests-mock` replaces the transport layer of `requests` ([documentation](https://requests-mock.readthedocs.io/en/latest/overview.html)).

The most useful example is the dlt test fixture, [`dlt-hub/dlt:tests/sources/rest_api/conftest.py`](https://github.com/dlt-hub/dlt/blob/devel/tests/sources/rest_api/conftest.py):

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

This fixture has approximately 45 routes. They give five different types of pagination. dlt replaces `requests`. dlt does not replace its own client.

The Airbyte `HttpMocker` is a `requests_mock.Mocker` with additional checks ([source](https://github.com/airbytehq/airbyte-python-cdk/blob/main/airbyte_cdk/test/mock_http/mocker.py)):

```python
def _validate_all_matchers_called(self) -> None:
    for matcher in self._get_matchers():
        if not matcher.has_expected_match_count():
            raise ValueError(f"Invalid number of matches for `{matcher}`")
```

This method is the reason for our rule: a mock that no request uses fails the test. stripe-python and the botocore `Stubber` do the same.

Airbyte keeps the test data in files, and it includes error responses: [`400.json`, `401.json`, `429.json`, `500.json`](https://github.com/airbytehq/airbyte/tree/master/airbyte-integrations/connectors/source-stripe/unit_tests/resource/http/response).

Which projects use cassette files:

| Project | HTTP replacement | Cassettes? |
|---|---|---|
| `airbytehq/airbyte-python-cdk` | `requests-mock` | No |
| `meltano/sdk` | `requests-mock` | No |
| `dlt-hub/dlt` | `requests-mock` | No |
| `stripe/stripe-python` | a local server | No |
| `boto/botocore` | its own stubber | No |
| `DataDog/datadogpy` | `vcrpy` | Yes — 66 |
| `PyGithub/PyGithub` | its own record system | Yes — more than 1000 |

The two projects that use cassettes show the cost. datadogpy must remove headers and query parameters from each file, and it needs an additional file for each cassette to control the time ([conftest](https://github.com/DataDog/datadogpy/blob/master/tests/integration/conftest.py)).

### 4.3 How we find supplier API changes

The usual method is: save a file, compare it on a schedule, and fail if it is different.

[`PyGithub:.github/workflows/openapi.yml`](https://github.com/PyGithub/PyGithub/blob/main/.github/workflows/openapi.yml) reads the GitHub API specification each day:

```yaml
      - name: Fail on changes
        run: |
          if ! git diff --quiet openapi/main; then
            echo "Changes exist, please investigate"
            exit 1
          fi
```

[`airbytehq/airbyte`](https://github.com/airbytehq/airbyte/blob/master/.github/workflows/regenerate-agent-engine-api-spec.yml) uses the same method with a saved specification file.

For the GitHub issue, we use the method from [`element-hq/synapse`](https://github.com/element-hq/synapse/blob/develop/.github/workflows/twisted_trunk.yml):

```yaml
      - uses: JasonEtco/create-an-issue@... # v2.9.2
        with:
          update_existing: true
```

The setting `update_existing: true` gives one issue instead of thirty.

Three rules come from the GitHub documentation ([events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)):

- A scheduled workflow runs only on the default branch. You therefore cannot test a change to it on a branch. For this reason, `workflow_dispatch` is necessary, not optional.
- GitHub can delay a scheduled workflow when the load is high. Do not use the exact hour.
- In a public repository, GitHub stops a schedule after 60 days with no activity.

dlt gives us the parts we need:

- **Schema contracts** — the modes are `evolve`, `freeze`, `discard_row` and `discard_value`. The mode `freeze` raises `DataValidationError`, and the message gives the table, the column and the data ([documentation](https://dlthub.com/docs/general-usage/schema-contracts)).
- **`Schema.to_pretty_yaml()`** — this makes the file we save ([source](https://github.com/dlt-hub/dlt/blob/devel/dlt/common/schema/schema.py)).
- **`add_limit(max_items, max_time)`** — this keeps the daily job short ([documentation](https://dlthub.com/docs/general-usage/resource)).

**Be careful with this section.** We found no well-known Python project that reads a supplier's live data each day, makes a schema, and reports a difference. Every example we found compares a *published specification* or *generated code*. Our method joins that pattern with the dlt contract modes. The parts are proven. The combination is ours.

### 4.4 Coverage

The coverage.py documentation explains `fail_under` ([configuration](https://coverage.readthedocs.io/en/latest/config.html)). Note one detail: with the default precision, 99.6% is shown as 100% and still fails a limit of 100.

What comparable projects do:

| Project | Minimum coverage |
|---|---|
| `dlt-hub/dlt` | None. It measures no coverage. |
| `dlt-hub/verified-sources` | None. |
| `stripe/stripe-python` | None. |
| `boto/botocore` | Measures it. No minimum. |
| `airbytehq/airbyte-python-cdk` | Measures it and prints it. No minimum. |
| `pytest-dev/pytest` | `project: false` |
| `apache/airflow` | `informational: true` |
| httpx, attrs, structlog | 100%, but they count their own test files as source code. |

The Airbyte task shows the position clearly. The coverage task exists, and the `test-all` task does not call it ([source](https://github.com/airbytehq/airbyte/blob/master/poe-tasks/poetry-connector-tasks.toml)).

**A warning for a future reader.** The projects `attrs` and `structlog` contain the text `fail-under = 100`. It is in the `[tool.interrogate]` section. That is *docstring* coverage. It is not test coverage. Do not use those two projects as evidence.

### 4.5 Static checks

| Project | Position of the type checker |
|---|---|
| `dlt-hub/dlt` | Its own job. It blocks the test jobs. It checks `dlt tests tools`. |
| `airbytehq/airbyte-python-cdk` | Its own job, at the same time as the tests. |
| `meltano/sdk` | Its own job. |
| `stripe/stripe-python` | Its own job, at the same time as the tests. The version is fixed. |
| `boto/botocore` | No type checker. |

No project runs the type checker inside pytest.

We run the checks at the same time, like stripe-python and Meltano. dlt runs the type check first and the tests after it. That is the minority choice, and it costs one more push for each small error.

Two details from the pyright documentation ([configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)): the default mode is `standard`, so a setting of `basic` is *weaker than the default*. And fix the version ([CI guide](https://github.com/microsoft/pyright/blob/main/docs/ci-integration.md)) — pyright has a new release each week, and a new check can fail a pull request that is not related to it.

### 4.6 Where the version number is

`setuptools-scm` can read the version from the tag. It works correctly with our tag format. Its documentation describes `tag.prefix` for this purpose ([configuration](https://setuptools-scm.readthedocs.io/en/latest/config/)). We tested it: we made a workspace with two packages, we added the tags `pkg-a/v0.3.0` and `pkg-b/v1.5.0`, and we built both. The versions were correct, and no files moved between the packages.

We chose the fixed version anyway. You then see the version in the pull request, next to the changelog entry. The command `uv version --package <name> --bump <part>` makes the change for you. The one advantage of `setuptools-scm` — that the tag and the version cannot disagree — we get instead from a three-line check in CI.

### 4.7 The tag format

[`ing-bank/ordeq`](https://github.com/ing-bank/ordeq) is almost the same as our repository. It is a uv workspace with many packages, and it publishes them to PyPI. Its tags are `ordeq-yaml/v1.0.2` and `ordeq-viz/v1.3.1`. Its release workflow:

```yaml
on:
  push:
    tags:
      - ordeq-*/v*
...
      - run: echo "PACKAGE_NAME=${GITHUB_REF_NAME%%/*}" >> $GITHUB_ENV
```

The GitHub documentation gives a technical reason to prefer `/`: "`*`: Matches zero or more characters, but does not match the `/` character" ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#filter-pattern-cheat-sheet)). The pattern `dlt-source-aquabyte/v*` therefore selects one package only.

### 4.8 Changelogs

The Keep a Changelog documentation gives the reason not to make a changelog from commits. Commit lists "are full of noise. Things like merge commits, commits with obscure titles, documentation changes", but "a changelog entry is to document the noteworthy difference, often across multiple commits" ([keepachangelog.com](https://keepachangelog.com/en/1.1.0/)).

We have few packages. An automatic changelog would give us little, and it would need a commit message standard for all of us.

### 4.9 Two errors we corrected

The earlier release proposal, [Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20), has two errors. Both are real. Both are corrected in `release.yml`.

**Error 1. The choice of PyPI or TestPyPI was incorrect.** The proposal looks for the text `-rc` or `-dev` in the tag. The function `contains()` examines the complete tag, and the tag starts with the package name ([expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions)).

| Tag | Correct index | The proposal used |
|---|---|---|
| `dlt-source-devices/v2.0.0` | PyPI | **TestPyPI** — the name contains `-dev` |
| `dlt-source-y/v1.0.0b2` | TestPyPI | **PyPI** — a real pre-release, but no `-rc` or `-dev` |

The second row is the dangerous one. A test version goes to the real index, and you cannot remove it.

**Error 2. Nothing compared the tag with the version.** The workflow publishes the version in `pyproject.toml`. The tag only selects the package. You could therefore tag `v0.3.0` when `pyproject.toml` contained `0.1.0`. `encode/httpx` makes this comparison in `scripts/publish`:

```sh
if [ "refs/tags/${VERSION}" != "${GITHUB_REF}" ] ; then
  echo "GitHub Ref '${GITHUB_REF}' did not match package version '${VERSION}'"
  exit 1
fi
```

**One more problem, not in the proposal file.** The instructions said `git push --tags`. GitHub sends no push event when more than three tags arrive together. The release then does not start, and GitHub gives no error. Push one tag by name.

### 4.10 How we publish

From the PyPI documentation ([add a publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/), [use a publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)):

- A publisher has four fields: the repository owner, the repository name, the **workflow file name**, and the **environment name**.
- The permission `id-token: write` is necessary. Give it at **job** level. PyPI calls workflow level "discouraged".
- A pending publisher "does **not** create a project or reserve a project's name **until** it is actually used to publish".
- TestPyPI is a separate service. It needs its own account and its own publisher.

**Why not `uv publish`.** The uv documentation says: "`uv publish` does not currently generate attestations; attestations must be created separately before publishing" ([package guide](https://github.com/astral-sh/uv/blob/main/docs/guides/package.md)). The PyPA action makes and sends them automatically ([attestations](https://docs.pypi.org/attestations/producing-attestations/)).

There is a second reason. The uv option `--trusted-publishing` has three values. The value `automatic` is the default, and the uv source describes it as: "Attempt trusted publishing when we're in a supported environment, **continue if that fails**." A failure is therefore hidden.

**Why the environment names are fixed text.** An expression works, but GitHub creates an environment that does not exist, "with no protection rules or secrets". A new package name would then publish with no approval.

**Action versions**, checked on 2026-08-14 with the GitHub API:

| Action | Tag |
|---|---|
| `actions/checkout` | v7.0.1 |
| `astral-sh/setup-uv` | v10.0.1 |
| `actions/upload-artifact` | v7.0.1 |
| `actions/download-artifact` | v8.0.1 |
| `pypa/gh-action-pypi-publish` | v1.14.2 |

Give the publish action a commit SHA, not a tag. Its own documentation asks for this. That action holds our identity on PyPI.

### 4.11 The approval step

We checked the GitHub API. The organization uses the **Free** plan, and this repository is **private**. The GitHub documentation is clear ([environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)):

> "If you are on a GitHub Free, GitHub Pro, or GitHub Team plan, required reviewers are only available for public repositories."
> "If you are using GitHub Free, environment secrets are only available in public repositories."

The approval step is the safety control for the complete release system. Today it does not operate. Section [3.5](#35-one-decision-you-must-make) gives the three options.

The daily job has the same problem. It needs credentials, and environment secrets do not work on this plan. For this reason `live.yml` uses repository secrets.

### 4.12 What we do not build

Each item below is a real practice. A larger project needs it. We do not need it yet.

- **A CI system that finds the changed packages.** Airbyte and verified-sources both build one. They have 37 and more than 300 packages. We use a simple loop over `packages/*/`. Change this when CI becomes slow, not when the number of packages increases.
- **An acceptance test system.** The Airbyte system controls hundreds of packages from outside contributors. We read every pull request.
- **A mock server from an API specification.** The stripe-mock documentation says that it is stateless, that its responses are "hardcoded", and that error responses are "currently not supported". It checks the shape of the *request*. A source package cares most about the *response*.
- **Schemathesis.** It makes inputs to find errors in the *supplier*. We are the consumer.
- **A snapshot test library.** We have one saved schema for each resource. A comparison and an update option are sufficient.
- **A shared test library.** Do not build one before the third package needs it.
- **Codecov.** The setup cost and the upload failures are larger than the benefit at our size.

---

## 5. What we did not confirm

Read this before you use this document as proof of something.

1. **Branch protection settings.** These are repository settings. They are not in the code. We can only prove that a check blocks a release when a workflow file says `needs:`.
2. **A daily schema check in another project.** We found none. Section [4.3](#43-how-we-find-supplier-api-changes) joins two proven ideas. It does not copy one project.
3. **Changelog tools.** We did not confirm how `python-semantic-release`, `commitizen` and `towncrier` support one version for each package. Our choice uses the Keep a Changelog reason and our team size.
4. **A wide survey of tag formats.** One agent did not complete this work. Section [4.7](#47-the-tag-format) uses `ing-bank/ordeq` and the release-please default.
5. **CI structure.** The agent that examined matrices, path filters, merge queues and dependency tools stopped early. That work uses the GitHub documentation and the other two studies. Examine it again if you disagree with the CI design.
6. **GitHub behaviour on the Free plan.** We do not know if GitHub refuses to make an environment, or makes one with no protection. Look at Settings → Environments before you choose an option in [3.5](#35-one-decision-you-must-make).
7. **dlt test fixtures.** The published `dlt` 1.30.0 package declares no `pytest11` entry point. It gives you no pytest fixtures. Write your own.
