# /// script
# requires-python = ">=3.11"
# dependencies = ["packaging"]
# ///
"""Validate a release tag before it is pushed. CI runs the same script.

Usage, from the repo root, on the commit you are about to tag:

    uv run scripts/validate_release.py dlt-source-aquabyte/v0.2.0

Checks:

1. The tag is <package>/v<version>, and the package exists in packages/.
2. The version is valid PEP 440.
3. The version equals the one in the package's pyproject.toml, compared
   as PEP 440 values (so v0.2.0-rc1 equals 0.2.0rc1).
4. A final version has its `## [<version>]` section in the package's
   CHANGELOG.md. Pre-release versions skip this — their entry is
   written after the test release (docs/release.md).
5. The version is not already on the index it will publish to — PyPI
   for final versions, TestPyPI for pre-releases. Neither index accepts
   a version twice, ever.

Exit code 0 means the tag is safe to push. See docs/release.md, step 5.
"""

from __future__ import annotations

import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(tag: str) -> int:
    errors: list[str] = []

    package, sep, vpart = tag.partition("/")
    if not sep or not vpart.startswith("v") or not package:
        print(f"::error::Tag {tag!r} is not of the form <package>/v<version>")
        return 1
    version_str = vpart[1:]

    pyproject_path = REPO_ROOT / "packages" / package / "pyproject.toml"
    if not pyproject_path.is_file():
        print(f"::error::No package {package!r} in packages/")
        return 1
    print(f"OK: tag names {package}, which exists in the workspace")

    try:
        version = Version(version_str)
    except InvalidVersion:
        print(f"::error::{version_str!r} is not a valid PEP 440 version")
        return 1
    print(f"OK: {version_str} is valid PEP 440")

    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    declared = project["version"]
    if Version(declared) != version:
        errors.append(f"Tag version {version_str} != pyproject.toml version {declared}")
    else:
        print(f"OK: matches pyproject.toml ({declared})")

    if version.is_prerelease:
        print("OK: pre-release — changelog entry not required yet")
    else:
        changelog = pyproject_path.parent / "CHANGELOG.md"
        if f"## [{version_str}]" in changelog.read_text(encoding="utf-8"):
            print(f"OK: CHANGELOG.md has a section for {version_str}")
        else:
            errors.append(
                f"packages/{package}/CHANGELOG.md has no '## [{version_str}]' "
                "section. Write the changelog entry before tagging "
                "(docs/release.md, step 3)."
            )

    # The index this version will publish to must not have it already.
    host = "test.pypi.org" if version.is_prerelease else "pypi.org"
    url = f"https://{host}/pypi/{project['name']}/{version_str}/json"
    try:
        with urllib.request.urlopen(url, timeout=10):
            errors.append(
                f"{project['name']} {version_str} already exists on {host} "
                "and can never be reused — bump to a fresh version."
            )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"OK: {version_str} is free on {host}")
        else:
            errors.append(f"Unexpected HTTP {e.code} from {host} — try again.")
    except urllib.error.URLError as e:
        errors.append(f"Could not reach {host} ({e.reason}) — try again.")

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
