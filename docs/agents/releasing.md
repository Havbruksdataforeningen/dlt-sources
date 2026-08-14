# Releasing

How to release a source package. The reasoning is in [`docs/research/ci-cd.md`](../research/ci-cd.md), the citations in [`ci-cd-evidence.md`](../research/ci-cd-evidence.md), and the automation in [`.github/workflows/release.yml`](../../.github/workflows/release.yml).

Vocabulary: [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md).

The goal is that **adding a source is adding a folder**. No workflow edit, no release ceremony beyond a tag.

## How to release

1. **In a PR**: `uv version --package <pkg> --bump minor`, and move the package's CHANGELOG entry out of `Unreleased`. Merge.
2. **Tag the one package**, annotated:
   ```
   git tag -a dlt-source-aquabyte/v0.2.0 -m 'dlt-source-aquabyte 0.2.0'
   git push origin dlt-source-aquabyte/v0.2.0
   ```
3. **A maintainer approves** the run on the `pypi` environment. Done.

Rehearsal: tag `…/v0.2.0rc1` instead — same build, goes to TestPyPI, no approval. Each rehearsal needs its own version; both indexes refuse to re-upload one that exists.

## Rules

- **Each package has its own version.** Releasing one says nothing about the others. A consumer never sees this repo.
- **Tags are `<package>/vX.Y.Z`.** GitHub's `*` does not match `/`, so `dlt-source-aquabyte/v*` selects exactly one package, and `${REF_NAME%%/*}` always gives the package name. `ing-bank/ordeq`, a uv workspace publishing to PyPI, uses the same scheme.
- **Push the tag by name. Never `git push --tags`.** GitHub sends **no push event at all** when more than three tags arrive at once, so the release silently does not run.
- **The version is written in `pyproject.toml`.** Bump it with `uv version --package <pkg> --bump <part>`. Keeping it in the file means you see it in the PR diff, next to the changelog entry. (`setuptools-scm` can derive it from the tag instead, and does work with our tag format — but the only real gain is that tag and version cannot disagree, and the CI check below gives us that for three lines.)
- **CI checks the tag against the version in the file**, comparing them as PEP 440 values so `v0.2.0-rc1` equals `0.2.0rc1`. Without it, tagging `v0.3.0` while the file says `0.1.0` publishes the wrong version **permanently** — PyPI never lets a version number be reused. `encode/httpx` checks this the same way.
- **PyPI or TestPyPI is decided by parsing the version**, never by looking for text in the tag. Text matching is wrong in both directions: a package called `dlt-source-devices` looks like a dev release, and `v1.0.0b2` — a real pre-release — looks final and would go to production PyPI.
- **Trusted Publishing only. No stored PyPI tokens.** Put `id-token: write` at **job** level, never workflow level.
- **Publish with `pypa/gh-action-pypi-publish`, not `uv publish`.** uv's own docs say it does not generate PEP 740 attestations; the PyPA action creates and uploads them by default, and checks the metadata first. Also, `uv publish` defaults to `--trusted-publishing automatic`, which **hides authentication failures**. If you ever do use uv, pass `always`.
- **Build with `uv build --package <pkg> --no-sources`.** `--no-sources` builds the package the way a consumer gets it, so a dependency that would not resolve from PyPI fails here instead of downstream.
- **Pin the publish action to a commit SHA, not a tag.** It holds our PyPI identity, and its own README asks for this.
- **Environment names are fixed text — `pypi` and `testpypi`.** If you build the name from an expression, GitHub creates any environment that does not exist yet **with no protection rules**, so a new package would publish with no approval.
- **Changelogs are written by hand**, per package, in Keep a Changelog format, in the same PR as the version bump. Consider `release-please` only when this becomes tedious.
- **Being pre-1.0 is not permission to break things quietly.** While at 0.x, a breaking change gets a minor bump and says so at the top of the changelog entry.

## One-time setup per package

- A **pending publisher** on PyPI (`owner=Havbruksdataforeningen`, `repo=dlt-sources`, `workflow=release.yml`, `environment=pypi`) and a matching one on TestPyPI (`environment=testpypi`). A pending publisher does **not** reserve the project name until it is first used to publish.
- Nothing else. The environments are shared across all packages and created once.

## Blocked: the approval gate needs a plan decision

**The maintainer-approval gate does not work today.** The org is on **GitHub Free** and this repo is **private**; GitHub's documentation is explicit that required reviewers and environment secrets are available only for public repositories on Free, Pro and Team. Until this is resolved, `release.yml` will publish without the approval step actually gating anything.

Three ways out, in order of preference:

1. **Make the repo public.** Cheapest, unlocks environments and required reviewers immediately, and matches every project cited in the research — pip, ruff, httpx and ordeq are all public. These packages are published to public PyPI regardless.
2. **Upgrade the org plan.**
3. **Stay private and gate on tag creation instead** — restrict who may create tags matching the release pattern. This is weaker: it controls *who tags*, not a second pair of eyes at the moment of publish.
