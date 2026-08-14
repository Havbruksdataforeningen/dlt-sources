# How we test, version and release

Read this when you join. It explains how this repo works and why. It should take about ten minutes.

The step-by-step rules are elsewhere, so this stays short:

| Read this | When |
|---|---|
| [`docs/agents/testing.md`](../agents/testing.md) | You are writing tests |
| [`docs/agents/releasing.md`](../agents/releasing.md) | You are cutting a release |
| [`ci-cd-evidence.md`](./ci-cd-evidence.md) | You want to challenge a decision below |
| [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md) | A word here is unfamiliar |

---

## Why we do it this way

We build **source packages**. Each one reads data from a supplier's API. Member companies install them from PyPI and run them in their own pipelines.

Two facts drive everything.

**The supplier's API is the risk, not our code.** A source package has little complex logic. It requests, reads, and hands data to dlt. Things go wrong when a supplier's response is not the shape we assumed. So our tests check that we handle real, documented responses correctly — not that our functions call each other.

We do *not* try to detect supplier changes automatically. That needs credentials, scheduled jobs, alerting and schema comparison — a lot of machinery for every contributor to learn. We accept that a member company might tell us about a change before a test does. See [testing.md](../agents/testing.md#live-tests-are-optional-and-per-package).

**Each package has its own version and its own users.** Someone installing `dlt-source-aquabyte` does not know the other packages exist, and must not be affected by them. We keep everything in one repo for our own convenience — the repo stays invisible to the consumer.

## What you get

These are promises. If a change breaks one, the change is wrong.

**You only deal with your own package.** Its own tests, its own config, its own version. You don't read the others or run their tests.

**You never write CI configuration.** Adding a source package means adding a folder. The workflows find it. The only manual step is one-time PyPI setup, in [releasing.md](../agents/releasing.md).

**The standards are identical everywhere.** Same formatter, linter and type checker in every package. Nothing to decide, nothing to argue about in review.

**You have working examples to copy.** Every package solves the same problem the same way, so you start by reading an existing one. This helps the agents too — they have real reference packages instead of inventing a structure.

**A green pull request means the package can be released.** CI builds every package on every PR, so packaging mistakes show up then, not on release day.

**A release is one tag.** Bump the version, write the changelog entry, push one tag, get an approval. That's it.

**You can run everything on your laptop.** `pytest` needs no credentials, no supplier account and no network.

---

## The decisions

### Testing

- **Tests are offline.** They replace HTTP with `requests-mock` and feed the source saved sample responses. → [why](./ci-cd-evidence.md#1-how-we-replace-http)
- **Sample responses come from the supplier's documented examples** — an OpenAPI/Swagger spec where one exists — otherwise from one real captured response, trimmed. They live in `tests/fixtures/`.
- **We mock HTTP, never dlt's `RESTClient`.** Mocking the client only proves your code calls your mock; the interesting logic never runs. → [why](./ci-cd-evidence.md#1-how-we-replace-http)
- **No recorded cassettes.** Nobody comparable uses them, and they go stale silently. → [why](./ci-cd-evidence.md#2-why-not-cassettes)
- **We assert on what lands in DuckDB**, not just on what a resource yields.
- **Coverage is measured and printed, never enforced.** → [why](./ci-cd-evidence.md#3-coverage)
- **Live tests are optional and per package**, excluded from the default run. There is no scheduled job. → [why](../agents/testing.md#live-tests-are-optional-and-per-package)
- **Format, lint, types and tests run in parallel**, as separate named jobs. → [why](./ci-cd-evidence.md#4-static-checks)

### Versioning

- **Each package versions independently.** A release of one says nothing about another.
- **The version is written in `pyproject.toml`.** Bump it with `uv version --package <name> --bump <part>`, so it shows up in the PR diff next to the changelog entry. → [why](./ci-cd-evidence.md#5-where-the-version-lives)
- **Tags are `<package-name>/vX.Y.Z`.** GitHub's `*` doesn't match `/`, so `dlt-source-aquabyte/v*` selects exactly one package. → [why](./ci-cd-evidence.md#6-the-tag-format)
- **Changelogs are written by hand**, per package. → [why](./ci-cd-evidence.md#7-changelogs)

### Releasing

- **CI checks the tag against the version in `pyproject.toml`** and stops if they disagree. PyPI never lets you reuse a version number, so a wrong tag is permanent. → [why](./ci-cd-evidence.md#8-two-bugs-we-fixed)
- **PyPI vs TestPyPI is decided by parsing the version**, not by looking for text in the tag. Text matching gets this wrong in both directions. → [why](./ci-cd-evidence.md#8-two-bugs-we-fixed)
- **Push one tag by name.** Never `git push --tags` — GitHub sends no event when more than three tags arrive at once, and the release silently doesn't run.
- **We publish with `pypa/gh-action-pypi-publish`**, not `uv publish`. → [why](./ci-cd-evidence.md#9-how-we-publish)
- **Trusted Publishing, no stored tokens.** Nothing to leak, nothing to rotate.

---

## One thing still to decide

**The release approval step doesn't work yet.** The org is on GitHub Free and this repo is private. On that plan, GitHub only offers required reviewers for public repositories.

Three options:

1. **Make the repo public.** Cheapest, works immediately, and matches comparable projects — pip, ruff, httpx and ordeq are all public. The packages go to public PyPI anyway.
2. **Upgrade the org plan.**
3. **Stay private and restrict who can create release tags.** Weaker: it controls who starts a release, not whether a second person checks it.

Details in [ci-cd-evidence.md](./ci-cd-evidence.md#10-the-approval-step).
