# Writing documentation

Style rules for every document in this repo — the files here, the README, the glossaries and the changelogs. Docs are read by developers at member companies who are new to this repo, not by us. Optimise for a low barrier to entry.

- **Write for a junior developer who knows Python and dlt.** Assume the language and the framework; explain our decisions. Explain the why before the what, as if onboarding a new developer.
- **Keep a document short enough that someone actually reads it.** If it outgrows one sitting, split it into a short main document, with detail in linked sub-files. Do not let a document grow past the point of being read.
- **Plain sentences, active voice, no metaphors or idioms.** Prefer a table or a list over a paragraph.
- **Use the terms in `CONTEXT-MAP.md` and the package's `CONTEXT.md`.** Do not invent synonyms for things that already have a name.
- **Prefer the simple mechanism.** When a rule needs machinery to follow, that machinery is a cost every contributor pays — say what it buys, or drop it.
- **Cite a source when justifying a decision.** Do not survey the field; one good precedent beats a table of them.

## What is here

| File | Read it when |
|---|---|
| [`release.md`](release.md) | You are publishing a release, or changing the release workflow |
| [`testing.md`](testing.md) | You want to know how tests are run and what CI provides |
| [`monorepo.md`](monorepo.md) | You wonder why one repo holds many packages, and what that promises you |
| [`source-guidelines.md`](source-guidelines.md) | You are building or changing source-package code |
| [`domain.md`](domain.md) | You want the glossary system (`CONTEXT-MAP.md` + `CONTEXT.md`) explained |
| [`issue-tracker.md`](issue-tracker.md) | You are creating or working with issues |
| [`triage-labels.md`](triage-labels.md) | You are labelling issues |
| [`logging-research.md`](logging-research.md) | Background research on logging in dlt sources — notes, not rules |
