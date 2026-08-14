# Releasing

How to publish a source package to PyPI.

Reasoning: [`docs/research/ci-cd.md`](../research/ci-cd.md). Citations: [`ci-cd-evidence.md`](../research/ci-cd-evidence.md). Automation: [`.github/workflows/release.yml`](../../.github/workflows/release.yml). Vocabulary: [`CONTEXT-MAP.md`](../../CONTEXT-MAP.md).

## Why it works this way

This repo holds several source packages, but **each one is a separate package on PyPI** with its own version number and its own users. Someone who installs `dlt-source-aquabyte` does not know the other packages exist, and must not be affected when they change. We keep everything in one repo for our own convenience — the repo itself is invisible to whoever installs the package.

That has one consequence you need to remember: **a release is always a release of one package**, never of the repo. So the git tag has to say which package it means. That is why tags start with the package name:

```
dlt-source-aquabyte/v0.2.0
└──────┬──────────┘ └─┬──┘
   which package    which version
```

The workflow reads the package name from the tag and builds only that package. Nothing else in the repo is touched or published.

## How to release

**1. Bump the version.** Pick the part that matches what changed:

```bash
uv version --package dlt-source-aquabyte --bump patch   # bug fix
uv version --package dlt-source-aquabyte --bump minor   # new feature
uv version --package dlt-source-aquabyte --bump major   # breaking change
```

This edits `version` in that package's `pyproject.toml`. Nothing else.

**2. Update the changelog.** In `packages/<package>/CHANGELOG.md`, move the entries from `Unreleased` into a new section for this version.

**3. Open a pull request with those two changes and merge it.** The version that gets published is the one in `pyproject.toml`, so it has to be on `main` before you tag.

**4. Tag the merged commit and push the tag:**

```bash
git tag -a dlt-source-aquabyte/v0.2.0 -m 'dlt-source-aquabyte 0.2.0'
git push origin dlt-source-aquabyte/v0.2.0
```

Push the one tag by name. Do **not** use `git push --tags` — see the rules below.

**5. Approve the run.** A maintainer approves it in GitHub Actions, and the package goes to PyPI.

## Test it first with a release candidate

Before a real release you can publish to **TestPyPI** instead, to check that the package builds and installs correctly. Use a release candidate version — `0.2.0rc1` — and the same steps as above:

```bash
uv version --package dlt-source-aquabyte --bump rc
git tag -a dlt-source-aquabyte/v0.2.0rc1 -m 'dlt-source-aquabyte 0.2.0rc1'
git push origin dlt-source-aquabyte/v0.2.0rc1
```

The workflow sees that `0.2.0rc1` is a pre-release version and sends it to TestPyPI. No approval is needed. Install it from there and check it works.

If something is wrong, fix it and use `rc2`. Each attempt needs its own version number, because PyPI and TestPyPI both refuse to accept a version that already exists.

## Rules

- **Each package has its own version.** Releasing one says nothing about the others.
- **Tags are `<package>/vX.Y.Z`.** GitHub's `*` does not match `/`, so `dlt-source-aquabyte/v*` selects exactly one package. `ing-bank/ordeq`, a uv workspace publishing to PyPI, uses the same scheme.
- **Push the tag by name. Never `git push --tags`.** GitHub sends **no push event at all** when more than three tags arrive at once, so the release silently does not run.
- **The version lives in `pyproject.toml`**, not in the tag. Keeping it in the file means you see it in the pull request, next to the changelog entry.
- **CI checks that the tag matches the version in the file**, comparing them as PEP 440 values so `v0.2.0-rc1` equals `0.2.0rc1`. Without that check, tagging `v0.3.0` while the file says `0.1.0` would publish the wrong version **permanently** — PyPI never lets a version number be reused.
- **PyPI or TestPyPI is decided by parsing the version**, never by looking for text in the tag. Text matching is wrong in both directions: a package called `dlt-source-devices` looks like a dev release, and `v1.0.0b2` — a real pre-release — looks final.
- **Trusted Publishing only. No stored PyPI tokens.** `id-token: write` goes at **job** level, never workflow level.
- **Publish with `pypa/gh-action-pypi-publish`, not `uv publish`.** uv's own docs say it does not generate PEP 740 attestations, and it defaults to `--trusted-publishing automatic`, which hides authentication failures.
- **Build with `uv build --package <pkg> --no-sources`,** so the package is built the way someone installing it from PyPI gets it.
- **Pin the publish action to a commit SHA.** It holds our PyPI identity.
- **Environment names are fixed text — `pypi` and `testpypi`.** If the name came from an expression, GitHub would create any environment that does not exist yet **with no protection rules**, and a new package would publish with no approval.
- **Being pre-1.0 is not permission to break things quietly.** While at 0.x, a breaking change gets a minor bump and says so at the top of the changelog entry.

## One-time setup per package

Before a package's first release, someone has to register it with both indexes:

- A **pending publisher** on PyPI — owner `Havbruksdataforeningen`, repo `dlt-sources`, workflow `release.yml`, environment `pypi`.
- The same on TestPyPI, with environment `testpypi`.

A pending publisher does not reserve the name; the name is claimed the first time you actually publish.

Nothing else. The two environments are shared by every package and are created once.

## Known limitation

**The approval step in step 5 does not gate anything yet.** GitHub only offers required reviewers on public repositories for our plan, and this repo is private. The workflow runs and publishes without waiting for anyone.

Tracked in [#8](https://github.com/Havbruksdataforeningen/dlt-sources/issues/8), which must be resolved before the first real release. This section gets removed when it is.
