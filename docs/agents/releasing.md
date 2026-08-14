# Releasing

Target state. Reasoning and citations live in [`docs/research/ci-cd.md`](../research/ci-cd.md); the automation is [`.github/workflows/release.yml`](../../.github/workflows/release.yml).

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

- **Versions are independent per package.** The monorepo is invisible to consumers; a bump to one source means nothing to another.
- **Tag format is `<package>/vX.Y.Z`.** *`ing-bank/ordeq` — a real uv-workspace monorepo publishing to PyPI — uses exactly this in production.* It also has a functional advantage: GitHub's `*` does not match `/`, so `dlt-source-aquabyte/v*` is an exact per-package selector, and `${REF_NAME%%/*}` is unambiguous because package names never contain `/`.
- **Push the tag by name. Never `git push --tags`.** GitHub creates **no push event at all** when more than three tags arrive at once — the release would silently never run.
- **The version lives statically in `pyproject.toml`**, bumped with `uv version --package <pkg> --bump <part>`. It stays visible in the PR diff next to the changelog entry. `setuptools-scm` does work correctly with prefixed tags (verified — via `[tool.setuptools_scm.tag] prefix`), but its one real prize, eliminating tag/metadata drift, is obtainable with the CI guard below and without requiring full-history checkouts.
- **CI asserts the tag matches the declared version**, compared as PEP 440 values so `v0.2.0-rc1` equals `0.2.0rc1`. Without it, tagging `v0.3.0` while `pyproject.toml` still says `0.1.0` publishes the wrong version *irrevocably* — PyPI never allows a version number to be reused. *`encode/httpx` guards the same way in `scripts/publish`.*
- **Prerelease routing is decided by PEP 440, never by substring matching on the tag.** Asking whether the ref contains `-rc` or `-dev` is wrong in both directions: a package named `dlt-source-devices` looks like a dev release, and `v1.0.0b2` — a genuine prerelease — looks like a final one and would go straight to production PyPI.
- **Trusted Publishing only. No stored PyPI tokens.** `id-token: write` at **job** level, never workflow level.
- **Publish with `pypa/gh-action-pypi-publish`, not `uv publish`.** uv's own docs state it does not generate PEP 740 attestations; the PyPA action generates and uploads them by default and checks metadata before upload. Also, `uv publish --trusted-publishing automatic` is the *default* and **swallows OIDC failures silently** — if you ever do use uv, pass `always` so a broken setup fails loudly.
- **Build with `uv build --package <pkg> --no-sources`.** `--no-sources` builds the package as a consumer receives it, with workspace redirects disabled, so a dependency that wouldn't resolve from PyPI fails in CI rather than downstream.
- **Pin the publish action by SHA, not tag.** It holds the publishing identity. The action's own README says to pin to a SHA rather than a branch pointer.
- **Environments are static — `pypi` and `testpypi`.** Not built from an expression: GitHub *implicitly creates* an unknown environment with no protection rules, so a new package name would silently produce an ungated publish path.
- **Changelogs are hand-written**, per package, in Keep a Changelog format, edited in the same PR as the bump. Commit logs are full of merge commits and obscure titles; a changelog entry documents a noteworthy difference, often spanning several commits. Revisit `release-please` manifest mode only when the package count makes this tedious.
- **Pre-1.0 is not a licence to break things quietly.** Breaking changes get a minor bump while at 0.x, and say so at the top of the changelog entry.

## One-time setup per package

- A **pending publisher** on PyPI (`owner=Havbruksdataforeningen`, `repo=dlt-sources`, `workflow=release.yml`, `environment=pypi`) and a matching one on TestPyPI (`environment=testpypi`). A pending publisher does **not** reserve the project name until it is first used to publish.
- Nothing else. The environments are shared across all packages and created once.

## Blocked: the approval gate needs a plan decision

**The maintainer-approval gate does not work today.** The org is on **GitHub Free** and this repo is **private**; GitHub's documentation is explicit that required reviewers and environment secrets are available only for public repositories on Free, Pro and Team. Until this is resolved, `release.yml` will publish without the approval step actually gating anything.

Three ways out, in order of preference:

1. **Make the repo public.** Cheapest, unlocks environments and required reviewers immediately, and matches every project cited in the research — pip, ruff, httpx and ordeq are all public. These packages are published to public PyPI regardless.
2. **Upgrade the org plan.**
3. **Stay private and gate on tag creation instead** — restrict who may create tags matching the release pattern. This is weaker: it controls *who tags*, not a second pair of eyes at the moment of publish.
