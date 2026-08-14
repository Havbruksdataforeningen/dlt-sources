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

Each package owns how it tests itself. `docs/agents/testing.md` covers only how tests are run and what CI provides; `packages/dlt-source-aquabyte/tests/` is the example to copy from.

The reasoning behind the testing and release setup is in `docs/research/ci-cd.md`, with the citations in `docs/research/ci-cd-evidence.md`.

## Procedures and standards

New instructions go in one of two places:

- A **procedure** — a task with a beginning, an end and an order — is a skill in `.agents/skills/`, one folder per skill. Releasing a package is one: `.agents/skills/release-package/`.
- A **standard** — a rule that constrains everything you do — is a document in `docs/agents/`.

Creating a new skill is a human decision. When a procedure seems to qualify, propose the skill and let a human create it.

`.claude/skills` is a committed symlink to `.agents/skills`, so Claude Code discovers the same skills other tools read from `.agents/`. CI checks that it still resolves.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`havbruksdataforeningen/dlt-sources`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: root `CONTEXT-MAP.md` (shared terms) + `CONTEXT.md` per package. See `docs/agents/domain.md`.
