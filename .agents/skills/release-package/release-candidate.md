# Release candidate

Loaded from [`SKILL.md`](SKILL.md) when the developer accepts the test-release offer. Publishing a release candidate is how a test release is done: the same tag-driven workflow, but the pre-release version routes it to **TestPyPI**, with no approval step, and nothing lands on the real index.

The human gates hold here too: **you never push a tag**, release-candidate or not. You prepare the commit and hand over the commands.

## 1. Bump to the candidate version

Create the release branch and bump to the target version *plus* a candidate marker — `--bump` applies in order, so bumping `minor` from `0.1.0` with `rc` gives `0.2.0rc1`:

```bash
git switch -c release/<package>-v<version> origin/main
uv version --package <package> --bump <part> --bump rc
git add packages/<package>/pyproject.toml
git commit -m "Release candidate <package> <rc-version>"
```

## 2. Hand over the candidate tag

The tag must point at the commit that declares the candidate version, so push the branch first:

```bash
git push origin HEAD
```

Then print the commands for the developer:

```bash
git tag -a <package>/v<rc-version> -m '<package> <rc-version>'
git push origin <package>/v<rc-version>
```

The workflow parses `<rc-version>`, sees a pre-release, and publishes to TestPyPI without approval.

## 3. Check the candidate

Have the developer install it from TestPyPI — dependencies still come from PyPI, since TestPyPI does not carry them:

```bash
uv run --with '<package>==<rc-version>' --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match python -c 'import <module>'
```

and run whatever check makes sense for the change — an example pipeline, an import, a call against recorded data.

**If something is wrong**: fix it on the branch, then repeat from step 1's bump with `--bump rc` alone (giving `rc2`). Both indexes permanently refuse a version number that has been used, so every attempt needs a fresh candidate number.

## 4. Finalise the version

When the developer is satisfied:

```bash
uv version --package <package> --bump stable
```

This drops the candidate marker (`0.2.0rc1` → `0.2.0`). Leave it uncommitted — the release commit in the main procedure picks it up.

Return to [`SKILL.md`](SKILL.md) at step 6, **Draft the changelog entry**. The branch and the final version now exist, so step 5 stays skipped.
