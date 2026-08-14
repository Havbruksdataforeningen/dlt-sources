# dlt-sources

## Source guidelines

Before building or modifying source-package code, read `docs/agents/source-guidelines.md` — the neutrality and logging rules every source follows.

## Writing style

Docs here are read by developers at member companies who are new to this repo, not by us. Optimise for a low barrier to entry.

- **Write for a junior developer who knows Python and dlt, but is not an expert.** Assume the language and the framework; explain our decisions. Explain the why before the what.
- **Keep a document short enough that someone actually reads it.** If it outgrows one sitting, split it: a short main document, with detail in linked sub-files. Do not let a document grow past the point of being read.
- **Plain sentences, active voice, no metaphors or idioms.** Prefer a table or a list over a paragraph.
- **Use the terms in `CONTEXT-MAP.md` and the package's `CONTEXT.md`.** Do not invent synonyms for things that already have a name.
- **Prefer the simple mechanism.** When a rule needs machinery to follow, that machinery is a cost every contributor pays — say what it buys, or drop it.
- **Cite a source when justifying a decision.** Do not survey the field; one good precedent beats a table of them.

## Testing

Before writing or changing tests, read `docs/agents/testing.md` — offline by default, how HTTP is faked, and what is deliberately not adopted.

## Releasing

Before cutting a release or touching release automation, read `docs/agents/releasing.md` — tag format, where the version lives, and the Trusted Publishing setup.

The reasoning behind both is in `docs/research/ci-cd.md`, with the citations in `docs/research/ci-cd-evidence.md`.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`havbruksdataforeningen/dlt-sources`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: root `CONTEXT-MAP.md` (shared terms) + `CONTEXT.md` per package. See `docs/agents/domain.md`.
