---
name: release-package
description: Walk a developer through releasing a new version of an existing source package to PyPI. Use when asked to release, publish, or bump the version of a package, or when a release pull request has merged and needs its tag.
allowed-tools: Read, Grep, Glob, Edit, Write, AskUserQuestion, Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git show:*), Bash(git fetch:*), Bash(git pull:*), Bash(git switch:*), Bash(git add:*), Bash(git commit:*), Bash(git push origin HEAD:*), Bash(git tag --list:*), Bash(git ls-remote:*), Bash(uv version:*), Bash(uv build:*), Bash(gh pr create:*), Bash(gh pr view:*), Bash(gh pr checks:*), Bash(gh issue view:*), Bash(curl:*)
---

# release-package

Release one source package from this repo to PyPI. A release is always a release of one package, never of the repo — the tag carries the package name (`dlt-source-aquabyte/v0.2.0`) so the workflow knows which package to build.

The release has two human gates, so it takes two invocations of this skill:

- **Phase 1** ends at an open pull request. A human reviews and merges it.
- **Phase 2**, a new invocation after the merge, verifies `main` and hands the developer the tag commands. A human pushes the tag.

You open the pull request and the human merges it. You print the tag commands and the human runs them. **Never merge the release pull request and never push a tag**, even if asked to — pushing the tag is what publishes, and a version number on PyPI is permanent. The `allowed-tools` list above enforces this where the tool honours it; where it is advisory, this paragraph is the rule.

The standards that constrain the release workflow file — tag format, PEP 440 routing, Trusted Publishing, build flags, action pinning — are recorded in [`docs/research/ci-cd.md`](../../../docs/research/ci-cd.md). Read it only if someone asks why a step is the way it is.

## Which phase you are in

Fetch, then compare three things for the package: the version in `packages/<package>/pyproject.toml` on `origin/main` (`git show origin/main:packages/<package>/pyproject.toml`), the package's newest `<package>/v*` tag, and any open release pull request.

- pyproject on `main` is **ahead of the newest tag** → the release PR has merged. Go to **Phase 2**.
- a release PR is **open** → phase 1 is mid-flight; resume it where it stopped.
- pyproject on `main` **equals the newest tag** (or the package has no tags) → a new release. Start **Phase 1**.

## Phase 1 — prepare the release

### 1. Preflight

Run every check and show the developer the results as a list; stop on any failure.

- **Working tree is clean**: `git status --porcelain` prints nothing.
- **Branch is current**: `git fetch origin` ran, and the local `main` is not behind `origin/main`.
- **The package exists in the workspace**: `packages/<package>/pyproject.toml` exists. Releasing a package that is not in the workspace yet is a different task — adding a package — and out of this skill's scope.
- **The changelog exists**: `packages/<package>/CHANGELOG.md` exists.
- **The package is published**: `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/<package>/json` returns `200`. A `404` means this is the package's **first release** — read [`first-release.md`](first-release.md) and follow it before continuing; it ends with a confirmation you must get from the developer.

Done when every check passed, or the run stopped at the first-release confirmation.

### 2. Ask what changed

Ground yourself first: read the `Unreleased` section of the changelog, and `git log <newest-tag>..origin/main -- packages/<package>/` (from the beginning of history if there is no tag yet).

Then ask the developer what changed **for someone who has the package installed** — the bump measures impact on consumers, not effort spent. If any change might be breaking and the developer is unsure, ask questions that surface it:

- Did a resource, column, field or parameter change name, type or meaning — or disappear?
- Did a default change — an argument's default value, which resources load by default, how incremental loading behaves?
- Would a pipeline written against the current release run unmodified against this one, producing the same tables?

Done when you can state, for each change, its consumer impact in one sentence.

### 3. Recommend the bump

Recommend one of `patch` (fixes, no interface change), `minor` (new capability, existing use unaffected), `major` (existing use breaks) — and show the reasoning, per change, so the developer can disagree knowingly. The developer picks; their pick wins.

One rule from [`docs/research/ci-cd.md`](../../../docs/research/ci-cd.md#versioning): being pre-1.0 is not permission to break things quietly. While at 0.x, a breaking change gets a **minor** bump and says so at the top of the changelog entry.

### 4. Offer a release candidate

Ask, every release, one yes/no question: publish a release candidate to TestPyPI first? Recommend yes for a first release or a risky change; otherwise no recommendation. Declining must cost the developer one word.

If accepted, read [`release-candidate.md`](release-candidate.md) and follow it; it says where it rejoins this procedure.

### 5. Make the edits

Skip this step if the release-candidate procedure already created the branch and finalised the version.

```bash
git switch -c release/<package>-v<new-version> origin/main
uv version --package <package> --bump <part>
```

(`--dry-run` first if you need the new version number for the branch name.) The bump edits `version` in the package's `pyproject.toml` and nothing else — verify with `git diff` that the diff is that one line.

### 6. Draft the changelog entry

In `packages/<package>/CHANGELOG.md`, move the `Unreleased` content into a new `## [<version>] - <YYYY-MM-DD>` section, keeping the Keep a Changelog subsections (`Added` / `Changed` / `Fixed` / `Removed`).

Draft the wording from the actual changes established in step 2: each line states what a consumer will notice, not a commit subject. A breaking change at 0.x is called out in bold at the top of the entry.

Show the draft and let the developer edit or rewrite it. Done only when the developer has approved the wording — it is their entry, not yours.

### 7. Open the pull request

```bash
git add packages/<package>/pyproject.toml packages/<package>/CHANGELOG.md
git commit -m "Release <package> <version>"
git push origin HEAD
gh pr create --title "Release <package> <version>" --body "<bump part and the reasoning from step 3, plus the changelog entry>"
```

Then stop and say so: a human reviews and merges this PR, and after the merge the developer re-invokes this skill for phase 2. Phase 1 is done at the open, unmerged pull request — an agent-merged release PR is a defect, not initiative.

## Phase 2 — hand over the publish

### 1. Verify the merged state

Fetch, then check — all against `origin/main`, not the local checkout:

- The release PR is merged (`gh pr view`).
- `git show origin/main:packages/<package>/pyproject.toml` declares exactly the version being released. Never hand over tag commands for a version `main` does not carry — the workflow would refuse the mismatch, and a mistyped tag is permanent.
- The changelog on `origin/main` has the `## [<version>]` section.
- The tag `<package>/v<version>` does not already exist (`git ls-remote --tags origin '<package>/v*'`).

### 2. Hand over the tag commands

Print the exact commands for the developer to run, with the real package name and version filled in:

```bash
git switch main && git pull
git tag -a <package>/v<version> -m '<package> <version>'
git push origin <package>/v<version>
```

Push the one tag by name — `git push --tags` silently skips the release when several tags arrive at once.

Tell the developer what the push triggers: the release workflow checks the tag against `pyproject.toml`, builds the package, and publishes — a final version to PyPI, a pre-release to TestPyPI.

> **Warning to repeat at handover:** until [#8](https://github.com/Havbruksdataforeningen/dlt-sources/issues/8) is resolved, the approval step gates nothing — pushing the tag publishes to PyPI immediately, with no second pair of eyes. Check whether #8 is closed; once it is, this warning is stale and this paragraph gets deleted (that deletion is in #8's acceptance criteria).

You are done when the commands are printed and the warning delivered. The push itself is the developer's.
