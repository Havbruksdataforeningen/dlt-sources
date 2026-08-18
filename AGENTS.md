# dlt-sources

## Source guidelines

Before building or modifying source-package code, read `docs/source-guidelines.md` — the neutrality and logging rules every source follows.

## Contributing

`CONTRIBUTING.md` is the human-facing entry point: setup, the checks to run before a pull request, and what a new source package must contain. Keep it true when you change any of those, and do not duplicate it into `docs/`.

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
