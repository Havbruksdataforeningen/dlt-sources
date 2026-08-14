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

Versions are independent per package, and a tag names what it releases — `dlt-source-aquabyte/v0.2.0` → PyPI, a release candidate `…/v0.2.0rc1` → a test release on TestPyPI. Trusted Publishing, no stored tokens.

The procedure lives in [`.agents/skills/release-package/`](.agents/skills/release-package/SKILL.md) — an agent skill your coding agent picks up automatically ("release dlt-source-aquabyte"), written to also read as a normal step-by-step document you can follow by hand. The reasoning behind the setup is in [`docs/research/ci-cd.md`](docs/research/ci-cd.md).
