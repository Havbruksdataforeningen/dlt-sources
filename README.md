# dlt-sources

Shared [dlt](https://dlthub.com/) source packages for Havbruksdataforeningen members — one repo, one folder per source, each published as its own package.

> **Status: proposal.** This repo is the concrete example for the layout discussion in
> [Ingest-Barentswatch#12](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/issues/12). Nothing is decided yet.

## Packages

| Package | Description |
|---|---|
| [`dlt-source-aquabyte`](packages/dlt-source-aquabyte/) | Aquabyte API v3 (sites, pens, biomass, lice, welfare, environment) |

## Layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each source is a folder with its **own** `pyproject.toml` — own name, own dependencies, own independent version. The root is never published, and the monorepo is invisible to consumers.

```
dlt-sources/
├── pyproject.toml                    ← workspace root
└── packages/
    └── dlt-source-aquabyte/
        ├── pyproject.toml
        ├── src/dlt_source_aquabyte/  ← what a consumer installs
        ├── tests/
        └── examples/
```

Adding a source = adding a folder; CI and conventions are inherited.

## Developing

```bash
uv sync --all-packages --all-groups   # one shared dev environment

cd packages/dlt-source-aquabyte       # each package has its own tests and lint config
uv run pytest -m "not integration"
```

Build one package: `uv build --package dlt-source-aquabyte` (from the root). CI runs every package's format check, lint, and tests on every PR.

## Releasing

Not wired up yet — a concrete workflow sketch lives in [Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20). The short version: versions are independent per package, and a tag names what it releases — `dlt-source-aquabyte/v0.2.0` → PyPI (maintainer approves), `…/v0.2.0-rc1` → TestPyPI rehearsal. Trusted Publishing, no stored tokens.
