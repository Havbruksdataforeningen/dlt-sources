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

**The supplier's API is the risk, not our code.** A source package has little complex logic. It requests, reads, and hands data to dlt. Things go wrong when a supplier's response is not the shape we assumed. A test that proves our functions call each other is not worth much; a test that proves we handle a realistic response is.

How to do that is each package's decision — one supplier publishes an OpenAPI spec, another has a public sandbox, another gives you nothing but a sample payload. We do not impose one method. What we do impose is that CI has no supplier credentials, so the default test run has to work without them. See [testing.md](../agents/testing.md).

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

- **Each package owns its test setup.** We document how tests are *run*, not how they are written. `dlt-source-aquabyte` is the worked example to copy from. → [testing.md](../agents/testing.md)
- **Tests live in `packages/<name>/tests/`** and each package configures pytest itself. No repo-level suite, no repo-level `conftest.py`.
- **Every package's suite runs on every pull request**, via a plain loop. Simple, needs no configuration, and catches one package breaking another. Make it smarter when CI gets slow, not before.
- **CI has no supplier credentials.** Whatever the default `pytest` run does, it has to pass without them. Anything needing real access stays out of that run and is run by hand.
- **Coverage is measured and printed, never enforced.** → [why](./ci-cd-evidence.md#3-coverage)
- **Format, lint, types and tests run in parallel**, as separate named jobs. → [why](./ci-cd-evidence.md#4-static-checks)

The evidence doc also records what comparable projects do about [faking HTTP](./ci-cd-evidence.md#1-how-we-replace-http) and [recorded cassettes](./ci-cd-evidence.md#2-why-not-cassettes). That is background for a package author making these choices, not a repo-wide rule.

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

**The release approval step doesn't gate anything yet.** The org is on GitHub Free and this repo is private, and on that plan GitHub only offers required reviewers for public repositories. The release workflow runs and publishes without waiting for anyone.

Tracked in [#8](https://github.com/Havbruksdataforeningen/dlt-sources/issues/8), with the three options and their trade-offs. It has to be resolved before the first real release.
