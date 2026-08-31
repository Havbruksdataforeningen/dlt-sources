# dlt-sources

Shared [dlt](https://dlthub.com/) source packages for Havbruksdataforeningen members — one repo, one folder per source, each published as its own package.

> **Status: pre-1.0.** `dlt-source-aquabyte` is verified against the live Aquabyte API and heading for its first release. Folders here may still move; what a package promises its users is covered by its own version.

## Source packages

| Source package | Description |
|---|---|
| [`dlt-source-aquabyte`](packages/dlt-source-aquabyte/) | Aquabyte — camera-based monitoring of farmed salmon (sites, pens, biomass, lice, welfare, environment) |

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

Adding a source = adding a folder; CI and conventions are inherited. Why it works this way: [`docs/monorepo.md`](docs/monorepo.md).

## Developing

```bash
uv sync --all-packages --all-groups   # one shared dev environment

cd packages/dlt-source-aquabyte       # each package has its own tests and lint config
uv run pytest    # offline by default; live API tests need -m integration
```

Build one package: `uv build --package dlt-source-aquabyte` (from the root). CI runs every package's format check, lint, and tests on every PR.

## Releasing

Versions are independent per package, and a tag names what it releases — `dlt-source-aquabyte/v0.2.0` → PyPI, a release candidate `…/v0.2.0rc1` → a test release on TestPyPI. Trusted Publishing, no stored tokens.

The step-by-step guide, written for your first release, is [`docs/release.md`](docs/release.md).

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) — setup and what to run before a pull request. Adding a package for a new supplier: [`docs/new-package.md`](docs/new-package.md). Open an issue first.

Security problems go to [`SECURITY.md`](SECURITY.md), not the issue tracker.

## License

[Apache-2.0](LICENSE), with a copy shipped in each package. A vendor's OpenAPI document stays that vendor's material — see the package's own README.
