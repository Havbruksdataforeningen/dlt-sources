#!/usr/bin/env python3
"""Documentation checks, run by the `docs` job in .github/workflows/ci.yml.

Three checks, all facts a reader would call a defect if wrong:

1. Link integrity — every relative markdown link and in-page anchor in
   tracked *.md files resolves to a real file, directory or heading.
2. Skill validity — every .agents/skills/*/SKILL.md has YAML frontmatter
   whose `name` matches its directory name, and a non-empty `description`.
   Discovery depends on both (https://agentskills.io).
3. Symlink integrity — .claude/skills is a symlink resolving to
   .agents/skills, which is what makes Claude Code discover the skills.

Stdlib only, no dependencies: run as `python3 scripts/check_docs.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
CLAUDE_SKILLS_LINK = REPO_ROOT / ".claude" / "skills"

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")


def tracked_markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in out.split("\0") if name]


def strip_code(text: str) -> list[str]:
    """Lines with fenced blocks blanked and inline code spans removed."""
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else re.sub(r"`[^`]*`", "", line))
    return lines


def github_slug(heading: str, seen: dict[str, int]) -> str:
    """The anchor GitHub generates for a heading, with duplicate suffixes."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # links -> text
    text = text.replace("`", "").replace("*", "").replace("_", " ")
    text = text.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    slug = re.sub(r"\s", "-", slug)
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        seen: dict[str, int] = {}
        slugs = set()
        for line in strip_code(path.read_text(encoding="utf-8")):
            m = HEADING_RE.match(line)
            if m:
                slugs.add(github_slug(m.group(1), seen))
        cache[path] = slugs
    return cache[path]


def check_links(md_files: list[Path]) -> list[str]:
    errors = []
    anchor_cache: dict[Path, set[str]] = {}
    for md in md_files:
        for lineno, line in enumerate(strip_code(md.read_text(encoding="utf-8")), 1):
            for target in LINK_RE.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, mailto:, ...
                    continue
                where = f"{md.relative_to(REPO_ROOT)}:{lineno}"
                path_part, _, fragment = target.partition("#")
                dest = md if not path_part else (md.parent / path_part).resolve()
                if not dest.exists():
                    errors.append(f"{where}: broken link '{target}'")
                    continue
                if fragment:
                    if dest.suffix != ".md" or dest.is_dir():
                        continue  # anchors into non-markdown are not checked
                    if fragment not in anchors_of(dest, anchor_cache):
                        errors.append(f"{where}: missing anchor '{target}'")
    return errors


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    """Frontmatter as key -> value; simple `key: value` scalars only."""
    errors: list[str] = []
    fields: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return fields, [f"{path.relative_to(REPO_ROOT)}: no frontmatter block"]
    for line in lines[1:]:
        if line.strip() == "---":
            return fields, errors
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep or not key or key != key.strip() or not value.strip():
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: frontmatter line is not a "
                f"'key: value' scalar: {line!r}"
            )
            continue
        fields[key] = value.strip().strip("'\"")
    return fields, [f"{path.relative_to(REPO_ROOT)}: frontmatter never closed"]


def check_skills() -> list[str]:
    errors = []
    if not SKILLS_DIR.is_dir():
        return [f"{SKILLS_DIR.relative_to(REPO_ROOT)}: directory missing"]
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        rel = skill_md.relative_to(REPO_ROOT)
        if not skill_md.is_file():
            errors.append(f"{rel}: missing")
            continue
        fields, fm_errors = parse_frontmatter(skill_md)
        errors.extend(fm_errors)
        if fields.get("name") != skill_dir.name:
            errors.append(
                f"{rel}: frontmatter name {fields.get('name')!r} does not "
                f"match directory name {skill_dir.name!r}"
            )
        if not fields.get("description"):
            errors.append(f"{rel}: frontmatter has no description")
    return errors


def check_symlink() -> list[str]:
    rel = CLAUDE_SKILLS_LINK.relative_to(REPO_ROOT)
    if not CLAUDE_SKILLS_LINK.is_symlink():
        return [f"{rel}: missing or not a symlink"]
    if CLAUDE_SKILLS_LINK.resolve() != SKILLS_DIR.resolve():
        return [f"{rel}: resolves to {CLAUDE_SKILLS_LINK.resolve()}, not {SKILLS_DIR}"]
    return []


def main() -> int:
    errors = check_links(tracked_markdown_files()) + check_skills() + check_symlink()
    for error in errors:
        print(f"::error::{error}")
    if errors:
        print(f"\n{len(errors)} problem(s).", file=sys.stderr)
        return 1
    print("Docs OK: links resolve, skills valid, symlink intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
