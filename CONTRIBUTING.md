# Contributing

Pull requests are welcome from anyone.

## Open an issue first

A released package is a promise to everyone whose pipeline already uses it: same resources, same columns, same meaning. Deciding what a change should be is the expensive part, and an issue costs you less than a rejected pull request.

Say which package, what you are loading, and what the API actually returned — a response snippet beats a description of one.

Typos, broken links and wrong examples need no issue. Just open the pull request.

## Set up

You need [uv](https://docs.astral.sh/uv/) and nothing else; it installs Python for you.

```bash
git clone https://github.com/Havbruksdataforeningen/dlt-sources.git
cd dlt-sources
uv sync --all-packages --all-groups
```

Tests run offline and need no supplier credentials.

## Changing a package

Work inside the package directory — it owns its tests, lint config and version:

```bash
cd packages/dlt-source-aquabyte
uv run ruff format src tests examples
uv run ruff check --fix src tests examples
uv run pyright
uv run pytest                    # offline; -m integration hits the live API
```

CI runs all four against every package. The one required check is `CI OK`.

Easy to forget:

- **A changelog entry** under `## [Unreleased]`, describing what a *user of the package* will notice. Skip it for changes they cannot see.
- **The `## Compatibility` table** in the package README, if the change moves which API version the package targets.

## Adding a package

Copy [`packages/dlt-source-aquabyte/`](packages/dlt-source-aquabyte/) and adapt it. Adding the folder is the whole job: the workspace root globs `packages/*` and CI loops over every package, so there is no workflow to write.

It needs `pyproject.toml` (keep the ruff, pyright and pytest sections identical), `src/`, `tests/` that pass without credentials, `examples/`, a `README.md` with a `## Compatibility` table, `CHANGELOG.md`, a copy of `LICENSE`, and `CONTEXT.md`.

The one manual step is PyPI registration before the first publish: [`docs/release.md`](docs/release.md#first-release-of-a-package).

## Pull requests

Branch off `main`. Pull requests are squash-merged, so the title becomes the commit message — write it as a plain sentence, prefixed with the package name when it concerns one:

```
dlt-source-aquabyte: type the fishType field on harvest_report
```

Say what you verified, not only what you changed. Keep unrelated changes out.

Releasing is separate from any pull request: [`docs/release.md`](docs/release.md).

## Conventions

[`docs/source-guidelines.md`](docs/source-guidelines.md) for source code, [`docs/AGENTS.md`](docs/AGENTS.md) for anything you write in prose, [`docs/monorepo.md`](docs/monorepo.md) for why one repo holds many packages.

## Licensing

[Apache-2.0](LICENSE). Opening a pull request licenses your contribution the same way. There is no CLA.
