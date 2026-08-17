# Domain Docs

How the engineering skills consume this repo's domain documentation.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — shared terms used across sources, plus one pointer per package's `CONTEXT.md`. Read the ones relevant to the topic.
- **`packages/<package>/CONTEXT.md`** — the glossary for that source.
- **ADRs** — `docs/adr/` at the root for repo-wide decisions, `packages/<package>/docs/adr/` for package-scoped ones. Read those touching the area you're about to work in.

If any of these files don't exist yet, proceed silently. The `/domain-modeling` skill creates them lazily when terms or decisions actually get resolved.

## Layout

```
/
├── CONTEXT-MAP.md                     ← shared terms + pointers
├── docs/adr/                          ← repo-wide decisions
└── packages/
    └── dlt-source-aquabyte/
        ├── CONTEXT.md
        └── docs/adr/                  ← package-scoped decisions
```

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, test name), use the term as defined in the relevant `CONTEXT.md` or `CONTEXT-MAP.md`. If the concept isn't in a glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (…) — but worth reopening because…_
