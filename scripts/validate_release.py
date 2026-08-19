# /// script
# requires-python = ">=3.11"
# dependencies = ["packaging"]
# ///
"""Validate a release tag before it is pushed (docs/release.md, step 5). CI runs the same script."""

from __future__ import annotations

import re
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parent.parent


class Invalid(Exception):
    """A defect that makes the remaining checks meaningless."""


def split_tag(tag: str) -> tuple[str, str]:
    package, sep, vpart = tag.partition("/")
    if not sep or not package or not vpart.startswith("v"):
        raise Invalid(f"Tag {tag!r} is not of the form <package>/v<version>")
    return package, vpart[1:]


def load_pyproject(package: str) -> dict:
    path = REPO_ROOT / "packages" / package / "pyproject.toml"
    if not path.is_file():
        raise Invalid(f"No package {package!r} in packages/")
    print(f"OK: tag names {package}, which exists in the workspace")
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def parse_pep440(version_str: str) -> Version:
    try:
        version = Version(version_str)
    except InvalidVersion:
        raise Invalid(f"{version_str!r} is not a valid PEP 440 version") from None
    print(f"OK: {version_str} is valid PEP 440")
    return version


def check_version_matches_pyproject(version: Version, version_str: str, project: dict) -> list[str]:
    declared = project["version"]
    if Version(declared) != version:
        return [f"Tag version {version_str} != pyproject.toml version {declared}"]
    print(f"OK: matches pyproject.toml ({declared})")
    return []


def check_changelog_has_entry(package: str, version: Version, version_str: str) -> list[str]:
    if version.is_prerelease:
        print("OK: pre-release — changelog entry not required yet")
        return []
    changelog = REPO_ROOT / "packages" / package / "CHANGELOG.md"
    if not changelog.is_file():
        return [
            f"packages/{package}/CHANGELOG.md does not exist. "
            "Create it and write the changelog entry before tagging (docs/release.md, step 3)."
        ]
    text = changelog.read_text(encoding="utf-8")
    if f"## [{version_str}]" not in text:
        return [
            f"packages/{package}/CHANGELOG.md has no '## [{version_str}]' section. "
            "Write the changelog entry before tagging (docs/release.md, step 3)."
        ]
    print(f"OK: CHANGELOG.md has a section for {version_str}")
    return check_changelog_date(package, version_str, text)


# The date is written by hand on the release day, and a release can sit on a branch for
# weeks before it is tagged. Nothing else notices a stale one — it just ships wrong.
STALE_AFTER_DAYS = 7


def check_changelog_date(package: str, version_str: str, text: str) -> list[str]:
    """The section's date must be present, well-formed, and about today."""
    heading = re.search(rf"^## \[{re.escape(version_str)}\](.*)$", text, re.MULTILINE)
    stamped = re.match(r"\s*-\s*(\d{4}-\d{2}-\d{2})\s*$", heading.group(1) if heading else "")
    if not stamped:
        return [
            f"packages/{package}/CHANGELOG.md heading for {version_str} carries no 'YYYY-MM-DD' date. "
            "Date-stamp it with the release day (docs/release.md, step 3)."
        ]
    try:
        stamp = date.fromisoformat(stamped.group(1))
    except ValueError:
        return [f"packages/{package}/CHANGELOG.md dates {version_str} as {stamped.group(1)!r}, not a real date."]

    today = date.today()
    if stamp > today:
        return [f"packages/{package}/CHANGELOG.md dates {version_str} as {stamp}, which is in the future."]
    if today - stamp > timedelta(days=STALE_AFTER_DAYS):
        return [
            f"packages/{package}/CHANGELOG.md dates {version_str} as {stamp}, over {STALE_AFTER_DAYS} days ago. "
            "Restamp it with the release day (docs/release.md, step 3)."
        ]
    print(f"OK: CHANGELOG.md dates {version_str} {stamp}")
    return []


def check_not_already_published(version: Version, version_str: str, project: dict) -> list[str]:
    # Pre-releases publish to TestPyPI, final versions to PyPI — and
    # neither index ever accepts a version twice.
    host = "test.pypi.org" if version.is_prerelease else "pypi.org"
    url = f"https://{host}/pypi/{project['name']}/{version_str}/json"
    try:
        with urllib.request.urlopen(url, timeout=10):
            return [
                f"{project['name']} {version_str} already exists on {host} "
                "and can never be reused — bump to a fresh version."
            ]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"OK: {version_str} is free on {host}")
            return []
        return [f"Unexpected HTTP {e.code} from {host} — try again."]
    except urllib.error.URLError as e:
        return [f"Could not reach {host} ({e.reason}) — try again."]


def main(tag: str) -> int:
    try:
        package, version_str = split_tag(tag)
        project = load_pyproject(package)
        version = parse_pep440(version_str)
    except Invalid as e:
        print(f"::error::{e}")
        return 1

    errors = [
        *check_version_matches_pyproject(version, version_str, project),
        *check_changelog_has_entry(package, version, version_str),
        *check_not_already_published(version, version_str, project),
    ]
    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print(f"\nSafe to tag: {tag}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: uv run scripts/validate_release.py <package>/v<version>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
