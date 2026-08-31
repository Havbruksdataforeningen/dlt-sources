# dlt-sources

## This file, and `CLAUDE.md`

Instructions for agents live here. `CLAUDE.md` is one line pointing at this file and holds nothing of its own, because Claude Code does not read `AGENTS.md` on its own — verified 2026-08-30 against Claude Code 2.1.251, in a clone of this repo with no `CLAUDE.md`: the session auto-loaded the user's own `CLAUDE.md` and nothing from the repo. A pointer cannot drift out of step with this file, and does no harm if a later version reads it directly.

## Source guidelines

Before building or modifying source-package code, read `docs/source-guidelines.md` — the neutrality and logging rules every source follows.

## Contributing

`CONTRIBUTING.md` is the human-facing entry point: setup and the checks to run before a pull request. Adding a package for a new supplier is `docs/new-package.md`, linked from there. Keep both true when you change what they describe, and do not duplicate `CONTRIBUTING.md` into `docs/`.

## Writing documentation

When writing or editing any documentation — files in `docs/`, the README, a glossary, a changelog — follow the style rules in `docs/AGENTS.md`.

## Testing

Each package owns how it tests itself. `docs/testing.md` covers only how tests are run and what CI provides; `packages/dlt-source-aquabyte/tests/` is the example to copy from.

## Releasing

Before publishing a release or touching release automation, read `docs/release.md` — the step-by-step guide, including the rules the release workflow must keep to.

Why the repo is one workspace of independently versioned packages, and what that promises contributors: `docs/monorepo.md`.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`havbruksdataforeningen/dlt-sources`), via the `gh` CLI. See `docs/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/triage-labels.md`.

### Domain docs

Multi-context: root `CONTEXT-MAP.md` (shared terms) + `CONTEXT.md` per package. See `docs/domain.md`.
