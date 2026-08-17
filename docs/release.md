# Releasing a package

How to publish a new version of a source package to PyPI, written for your first release. Follow it top to bottom; every step shows the exact command.

The examples use `dlt-source-aquabyte` going from `0.1.0` to `0.2.0`. Substitute your package and versions.

Why the repo works this way: [`monorepo.md`](monorepo.md).

## The one thing to understand first

Each package in this repo is a separate package on PyPI, with its own version and its own users. Someone who installs `dlt-source-aquabyte` never sees this repo and must not be affected when another package changes. So **a release is always a release of one package**, never of the repo — and the git tag has to say which package it means:

```
dlt-source-aquabyte/v0.2.0
└──────┬──────────┘ └─┬──┘
   which package    which version
```

The publishing itself is automated. When you push a tag like that, [`release.yml`](../.github/workflows/release.yml) builds that one package and publishes it. Your job is the five steps that lead up to that push.

## Before you start

Start from a clean, current `main`:

```bash
git switch main
git pull
git status        # should say "working tree clean"
```

**Is this the package's very first release?** Then someone has to register it with PyPI once before anything can be published — do [First release of a package](#first-release-of-a-package) below before continuing.

## Step 1 — decide the new version

Look at what has changed since the last release:

```bash
git log dlt-source-aquabyte/v0.1.0..main -- packages/dlt-source-aquabyte/
```

and read the `Unreleased` section of `packages/dlt-source-aquabyte/CHANGELOG.md`.

Then pick which part of the version to bump. Judge by what changes **for someone using the package**, not by how much work it was:

| What changed for a user of the package | Bump | Example |
|---|---|---|
| A bug fix; nothing new, nothing removed | `patch` | 0.1.0 → 0.1.1 |
| Something new; existing pipelines keep working unchanged | `minor` | 0.1.0 → 0.2.0 |
| Existing pipelines break or produce different tables | `major` | 1.2.0 → 2.0.0 |

Not sure whether a change is breaking? Ask yourself: did a resource, column or parameter change name, type or meaning — or disappear? Did a default change? Would a pipeline written against the current release run unmodified and produce the same tables? If any answer is "no" or "not sure", treat it as breaking.

One special rule while a package is at `0.x`: being pre-1.0 is not permission to break things quietly. A breaking change gets a **minor** bump and says so at the top of the changelog entry.

## Step 2 — bump the version

On a new branch, let `uv` edit the version for you:

```bash
git switch -c release-aquabyte-0.2.0
uv version --package dlt-source-aquabyte --bump minor
```

This changes one line — `version` in `packages/dlt-source-aquabyte/pyproject.toml`. Check with `git diff` that that is all it changed.

## Optional: do a test release

Before continuing you can do a **test release**: publish a **release candidate** version (`0.2.0rc1`) to TestPyPI, to check that the package builds and installs correctly. Nothing lands on the real index. Recommended for a first release or a risky change; skip ahead to step 3 otherwise.

On your release branch:

```bash
uv version --package dlt-source-aquabyte --bump minor --bump rc   # 0.1.0 -> 0.2.0rc1
git add packages/dlt-source-aquabyte/pyproject.toml
git commit -m "Release candidate dlt-source-aquabyte 0.2.0rc1"
git push origin HEAD

uv run scripts/validate_release.py dlt-source-aquabyte/v0.2.0rc1
git tag -a dlt-source-aquabyte/v0.2.0rc1 -m 'dlt-source-aquabyte 0.2.0rc1'
git push origin dlt-source-aquabyte/v0.2.0rc1
```

The validator catches a reused candidate number before TestPyPI refuses it.

The workflow sees a pre-release version and publishes to TestPyPI, with no approval step. Then install it from there and check it works — dependencies still come from normal PyPI, because TestPyPI does not carry them:

```bash
uv run --with 'dlt-source-aquabyte==0.2.0rc1' \
  --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match \
  python -c 'import dlt_source_aquabyte'
```

If something is wrong, fix it on the branch and bump to `rc2` with `uv version --package dlt-source-aquabyte --bump rc` — both indexes refuse a version number that has already been used, so every attempt needs a fresh one.

When it looks good, drop the candidate marker and continue at step 3:

```bash
uv version --package dlt-source-aquabyte --bump stable   # 0.2.0rc1 -> 0.2.0
```

## Step 3 — write the changelog entry

In `packages/dlt-source-aquabyte/CHANGELOG.md`, move the `Unreleased` content into a new section for this version:

```markdown
## [0.2.0] - 2026-08-14

### Added

- `welfare_scores` resource: per-pen fish welfare indicators from API v3.

### Fixed

- `biomass` no longer drops rows where `packing_method` is missing.
```

Describe what a user of the package will notice, not what the commits say. If the release contains a breaking change (see the 0.x rule above), state it in bold at the top of the entry.

## Step 4 — open a pull request and get it merged

```bash
git add packages/dlt-source-aquabyte/pyproject.toml packages/dlt-source-aquabyte/CHANGELOG.md
git commit -m "Release dlt-source-aquabyte 0.2.0"
git push origin HEAD
```

Open the pull request and get it reviewed and merged. The version that gets published is the one in `pyproject.toml`, so it must be on `main` before you tag — CI checks that the tag and the file agree, and stops the release if they do not.

## Step 5 — tag the merged commit

Once the pull request is merged, update your checkout and run the validator — it checks the tag you are about to create against `pyproject.toml`, the changelog and the index, before anything becomes permanent:

```bash
git switch main && git pull
uv run scripts/validate_release.py dlt-source-aquabyte/v0.2.0
```

When it says `Safe to tag`:

```bash
git tag -a dlt-source-aquabyte/v0.2.0 -m 'dlt-source-aquabyte 0.2.0'
git push origin dlt-source-aquabyte/v0.2.0
```

Two things to be careful about here:

- **Push the one tag by name, never `git push --tags`.** GitHub sends no event at all when more than three tags arrive at once, so the release would silently not run.
- **Pushing the tag is the point of no return.** PyPI never lets a version number be reused — not even after deleting it. If something is wrong, you fix it in a new version; you cannot re-release this one.

> **Known limitation:** the maintainer-approval step in the workflow does not gate anything yet — pushing the tag publishes immediately, and nobody reviews the run. Tracked in [#8](https://github.com/Havbruksdataforeningen/dlt-sources/issues/8), which must be resolved before the first real release. Remove this note when it is.

## What happens after the push

The workflow runs the same validator you ran in step 5, builds the package, and publishes it — a final version goes to PyPI, a pre-release version (like `0.2.0rc1`) goes to TestPyPI. Watch it under the repo's **Actions** tab, then check the result at `https://pypi.org/p/dlt-source-aquabyte`.

## First release of a package

The workflow authenticates with **Trusted Publishing**: PyPI accepts the upload because the workflow matches a registered publisher, not because anyone holds a token. For a package that does not exist on PyPI yet, that registration is a **pending publisher**, and a human has to create it once, by hand, before the first publish. If it is missing, the release fails at the very last step with an `invalid-publisher` error that does not explain itself.

Register it on **both** indexes — TestPyPI is a separate service with its own account, and test releases publish there. On each, go to your account's **Publishing** page and add a pending publisher:

| Field | On pypi.org | On test.pypi.org |
|---|---|---|
| Project name | `dlt-source-aquabyte` | `dlt-source-aquabyte` |
| Owner | `Havbruksdataforeningen` | `Havbruksdataforeningen` |
| Repository | `dlt-sources` | `dlt-sources` |
| Workflow | `release.yml` | `release.yml` |
| Environment | `pypi` | `testpypi` |

A pending publisher does not reserve the name — the name is claimed the first time the publish actually runs — so also check the name is still free on both indexes. For a first release, a test release is strongly recommended: it proves the whole chain (tag, workflow, publisher, install) before anything lands permanently on PyPI.

## Rules for the release workflow

You only need these if you are changing [`release.yml`](../.github/workflows/release.yml). Whatever you change, keep these true:

- **Tags are `<package>/vX.Y.Z`.** GitHub's `*` does not match `/`, so `dlt-source-aquabyte/v*` selects exactly one package. `ing-bank/ordeq`, a uv workspace publishing to PyPI, uses the same scheme.
- **PyPI or TestPyPI is decided by parsing the version** with `packaging`, never by looking for text in the tag. Text matching is wrong in both directions: a package named `dlt-source-devices` looks like a dev release, and `1.0.0b2` — a real pre-release — looks final.
- **Publish with `pypa/gh-action-pypi-publish`, not `uv publish`.** uv generates no PEP 740 attestations, and its default trusted-publishing mode hides authentication failures.
- **Trusted Publishing only, no stored tokens.** `id-token: write` goes at job level, never workflow level.
- **Build with `uv build --package <pkg> --no-sources`,** so the package is built the way someone installing it from PyPI gets it.
- **Environment names are fixed text — `pypi` and `testpypi`.** If the name came from an expression, GitHub would create any unknown environment with no protection rules, and a new package would publish ungated.
- **Pin the publish action to a commit SHA.** It holds our PyPI identity.
