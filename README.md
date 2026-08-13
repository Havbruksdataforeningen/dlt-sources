# dlt-sources

Shared [dlt](https://dlthub.com/) source packages for Havbruksdataforeningen members — one repo, one folder per source, each published as its own package.

> **Status: proposal.** This repo is the concrete example for the layout discussion in
> [Ingest-Barentswatch#12](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/issues/12). Nothing is decided yet.

## Packages

| Package | Description |
|---|---|
| [`dlt-source-aquabyte`](packages/dlt-source-aquabyte/) | Aquabyte API v3 (sites, pens, biomass, lice, welfare, environment) |

## Layout

One folder per source; each is its own package with its own version. The root is never published.

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

## More

- [Repo layout](docs/layout.md) — how the workspace is organised
- [Developing](docs/development.md) — setup, running tests, adding a source
- [Releasing](docs/releasing.md) — how packages would reach PyPI (not wired up yet)
