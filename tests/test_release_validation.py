"""The version number lives in three places and they must never disagree.

`pyproject.toml` declares it, `CHANGELOG.md` describes it, and the git tag publishes it.
`scripts/validate_release.py` compares all three, but only when a tag is pushed — and a tag
is the point of no return, since PyPI never lets a version number be reused. So these tests
run on every pull request instead: the invariants that hold at all times here, the validator's
own rules below, because a gate nothing checks is a gate that can quietly stop working.

Repo-level, unlike the package suites in `packages/*/tests/`: `docs/testing.md`.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES = sorted(path for path in (REPO_ROOT / "packages").iterdir() if (path / "pyproject.toml").is_file())


def _load_validator():
    """`scripts/validate_release.py` is a PEP 723 script, not an installed module."""
    spec = importlib.util.spec_from_file_location("validate_release", REPO_ROOT / "scripts" / "validate_release.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_release = _load_validator()


def _declared_version(package: Path) -> str:
    return tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _released_tags() -> list[tuple[str, str]]:
    """Every final release tag as `(package, version)`. Pre-release tags describe nothing."""
    found = subprocess.run(
        ["git", "tag", "-l", "*/v*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    tags = [validate_release.split_tag(tag) for tag in found]
    return [(package, version) for package, version in tags if not validate_release.Version(version).is_prerelease]


# --- The three places, checked against each other on every pull request ---


def changelog_disagreement(package: str, version: str, changelog: str, released: bool) -> str | None:
    """Why `changelog` fails to describe `version`, or None when it does.

    A release pull request bumps `pyproject.toml` and dates the changelog section together, so
    from the first release onwards the declared version always has a section. A package that has
    never been released has nothing to describe yet: `docs/new-package.md` starts its changelog
    at `## [Unreleased]`, which is the right state and must not be read as drift.
    """
    if not released:
        if "## [Unreleased]" not in changelog:
            return f"{package} has never been released, so CHANGELOG.md should collect entries under '## [Unreleased]' (docs/new-package.md)."
        return None
    if f"## [{version}]" not in changelog:
        return f"{package} declares {version} in pyproject.toml with no '## [{version}]' section in CHANGELOG.md. Write the entry, or bump the version back (docs/release.md, step 3)."
    return None


def test_a_bump_that_forgot_the_changelog_is_drift():
    assert changelog_disagreement("p", "0.4.0", "## [0.3.0] - 2026-08-31\n", released=True)
    assert not changelog_disagreement("p", "0.4.0", "## [0.4.0] - 2026-08-31\n", released=True)


def test_a_package_awaiting_its_first_release_is_not_drift():
    """Its pyproject declares 0.1.0 while the changelog is still collecting under Unreleased."""
    assert not changelog_disagreement("p", "0.1.0", "## [Unreleased]\n", released=False)
    assert changelog_disagreement("p", "0.1.0", "# Changelog\n", released=False), "but an empty one is"


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_the_declared_version_is_described_in_the_changelog(package: Path):
    """The rule above, against what is actually in the repo."""
    problem = changelog_disagreement(
        package.name,
        _declared_version(package),
        (package / "CHANGELOG.md").read_text(encoding="utf-8"),
        released=any(name == package.name for name, _ in _released_tags()),
    )

    assert problem is None, problem


def test_every_release_tag_has_the_changelog_section_it_was_cut_from():
    """The third place. A tag names a version a consumer can install, so it must be described.

    Needs the tags fetched — `actions/checkout` takes no tags by default.
    """
    tags = _released_tags()
    if not tags:
        pytest.skip("no release tags in this checkout, so there is nothing to compare against")

    undescribed = [
        f"{package}/v{version}"
        for package, version in tags
        if f"## [{version}]" not in (REPO_ROOT / "packages" / package / "CHANGELOG.md").read_text(encoding="utf-8")
    ]

    assert not undescribed, f"tagged, but described by no changelog section: {', '.join(undescribed)}"


@pytest.mark.parametrize("package", PACKAGES, ids=lambda path: path.name)
def test_the_declared_version_is_not_behind_a_tag(package: Path):
    """A version already published cannot be released again, so the next one must be higher.

    This catches the bump that never happened: a change merged on top of a released version,
    heading for a tag the index will refuse.
    """
    released = [validate_release.Version(version) for name, version in _released_tags() if name == package.name]
    if not released:
        pytest.skip(f"{package.name} has never been released")

    assert validate_release.Version(_declared_version(package)) >= max(released), (
        f"{package.name} declares {_declared_version(package)}, behind its own tag {max(released)}. "
        "PyPI never accepts a version twice (docs/release.md, step 2)."
    )


# --- The validator's own rules, so the gate cannot quietly stop working ---


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("dlt-source-aquabyte/v0.3.0", ("dlt-source-aquabyte", "0.3.0")),
        ("dlt-source-aquabyte/v1.0.0rc1", ("dlt-source-aquabyte", "1.0.0rc1")),
    ],
)
def test_a_well_formed_tag_splits_into_package_and_version(tag: str, expected: tuple[str, str]):
    assert validate_release.split_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    ["dlt-source-aquabyte", "dlt-source-aquabyte/0.3.0", "/v0.3.0", "v0.3.0"],
)
def test_a_tag_that_names_no_package_and_version_is_refused(tag: str):
    """`<package>/v<version>` is what the release workflow selects on, so nothing else may pass."""
    with pytest.raises(validate_release.Invalid):
        validate_release.split_tag(tag)


def test_a_version_the_index_would_refuse_is_refused_first():
    """`0.3.0-hotfix` is the shape of the mistake: a suffix PyPI has no meaning for."""
    with pytest.raises(validate_release.Invalid):
        validate_release.parse_pep440("0.3.0-hotfix")

    assert validate_release.parse_pep440("0.3.0rc1").is_prerelease, "a candidate is still valid"


def test_a_tag_and_a_pyproject_that_disagree_are_caught():
    version = validate_release.Version("0.3.0")

    assert validate_release.check_version_matches_pyproject(version, "0.3.0", {"version": "0.2.0"})
    assert not validate_release.check_version_matches_pyproject(version, "0.3.0", {"version": "0.3.0"})


def test_versions_are_compared_as_versions_rather_than_as_text():
    """`0.3` and `0.3.0` are the same release to PEP 440, and a mismatch here would be a lie."""
    assert not validate_release.check_version_matches_pyproject(
        validate_release.Version("0.3.0"), "0.3.0", {"version": "0.3"}
    )


@pytest.mark.parametrize(
    ("heading", "why"),
    [
        ("## [0.3.0]", "carries no date at all"),
        ("## [0.3.0] - 2026-13-01", "names a month that does not exist"),
        ("## [0.3.0] - not a date", "is not a date"),
        ("## [0.3.0] - 2099-01-01", "is in the future"),
        ("## [0.3.0] - 2020-01-01", "is long stale"),
    ],
)
def test_a_changelog_date_that_would_ship_wrong_is_caught(heading: str, why: str):
    """The date is typed by hand on release day and nothing downstream notices a wrong one."""
    assert validate_release.check_changelog_date("dlt-source-aquabyte", "0.3.0", f"{heading}\n\n### Added\n"), why


def test_a_changelog_dated_today_passes():
    today = validate_release.date.today().isoformat()

    assert not validate_release.check_changelog_date("dlt-source-aquabyte", "0.3.0", f"## [0.3.0] - {today}\n")


def test_the_date_of_another_version_is_not_read_as_this_ones():
    """Sections stack newest first, so the regex must anchor to the version it was asked about."""
    changelog = "## [0.3.0]\n\n### Added\n\n## [0.2.0] - 2026-08-31\n"

    assert validate_release.check_changelog_date("dlt-source-aquabyte", "0.3.0", changelog), (
        "0.3.0 has no date of its own and must not borrow 0.2.0's"
    )


def test_the_repo_uses_the_tag_shape_the_release_workflow_selects_on():
    """`release.yml` triggers on `dlt-source-*/v*`. A tag outside that shape publishes nothing."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    selector = re.search(r'^\s*-\s*"(dlt-source-\S+)"\s*$', workflow, re.MULTILINE)

    assert selector, "release.yml must select release tags by a quoted glob"
    assert selector.group(1) == "dlt-source-*/v*"
