# dlt-sources

Shared monorepo of [dlt](https://dlthub.com/) source packages for Havbruksdataforeningen members.

> **Status: proposal.** This repo exists as the concrete example for the layout discussion in
> [Ingest-Barentswatch#12](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/issues/12)
> (one `dlt-sources` monorepo vs. one repo per source). Nothing is decided yet — this is what
> option B looks like in practice, so it can actually be evaluated.

## Layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each source is a
folder under `packages/` with its **own** `pyproject.toml`, own name, and own independent
version. The workspace root is never published.

```
dlt-sources/
├── pyproject.toml                    ← workspace root (never published)
└── packages/
    └── dlt-source-aquabyte/          ← first member
        ├── pyproject.toml
        ├── src/dlt_source_aquabyte/  ← the only part that would reach a consumer
        ├── tests/
        └── examples/
```

Adding source number two = adding a folder. CI, lint config, review habits, and (eventually)
the release workflow are inherited, not re-established per repo.

## Working in the repo

```bash
uv sync --all-packages --all-groups   # one shared dev environment for all members
cd packages/dlt-source-aquabyte
uv run pytest -m "not integration"    # each package has its own tests and config
```

Build one package: `uv build --package dlt-source-aquabyte`.

## Releasing (not wired up yet)

Per-package tags route releases: `dlt-source-aquabyte/v0.2.0` → PyPI,
`…/v0.2.0-rc1` → TestPyPI. A concrete workflow sketch exists in
[Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20);
it moves here if/when #12 is decided in favour of this layout.

## Packages

| Package | Description |
|---|---|
| [`dlt-source-aquabyte`](packages/dlt-source-aquabyte/) | Aquabyte API v3 (sites, pens, biomass, lice, welfare, environment) |

Candidates to migrate in if the layout is adopted: `dlt-barentswatch-source`
(from Ingest-Barentswatch), `dlt-fiskeridirektoratet-source`.
