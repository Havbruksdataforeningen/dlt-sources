# dlt-sources

## Source guidelines

Before building or modifying source-package code, read `docs/agents/source-guidelines.md` — the neutrality and logging rules every source follows.

## Testing

Before writing or changing tests, read `docs/agents/testing.md` — the two-tier split, how HTTP is faked, and what is deliberately not adopted.

## Releasing

Before cutting a release or touching release automation, read `docs/agents/releasing.md` — tag format, where the version lives, and the Trusted Publishing setup.

The evidence behind both, with citations, is in `docs/research/ci-cd.md`.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`havbruksdataforeningen/dlt-sources`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: root `CONTEXT-MAP.md` (shared terms) + `CONTEXT.md` per package. See `docs/agents/domain.md`.
