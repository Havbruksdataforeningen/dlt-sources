# Contributing

This repository holds the [dlt](https://dlthub.com/) source packages that Havbruksdataforeningen members share. It is public because the packages are published on PyPI, and because someone deciding whether to load data with one should be able to read exactly what it does.

It is written first for developers at member companies. Pull requests from anyone else are welcome on the same terms — nothing here is member-only.

## Open an issue before you write code

A released source package is a promise to everyone whose pipeline already loads data with it: the same resources, the same columns, the same meaning. So the expensive part of a change is deciding what it should be, not writing it. An issue is where that happens, and it costs you less than a rejected pull request.

Issues live in [GitHub Issues](https://github.com/Havbruksdataforeningen/dlt-sources/issues). Say which package you mean, what you are loading, and what the API actually returned — a response snippet is worth more than a description of one.

Small and obvious fixes — a typo, a broken link, a wrong example — need no issue. Just open the pull request.

## Set up

You need [uv](https://docs.astral.sh/uv/) and nothing else; it installs Python for you.

```bash
git clone https://github.com/Havbruksdataforeningen/dlt-sources.git
cd dlt-sources
uv sync --all-packages --all-groups   # one shared environment for every package
```

Tests run offline and need no supplier credentials, so this is enough to start.

## Read these first

| Document | Read it when |
|---|---|
| [`docs/source-guidelines.md`](docs/source-guidelines.md) | You are changing source-package code. The neutrality rules every package follows. |
| [`docs/monorepo.md`](docs/monorepo.md) | You wonder why one repository holds many packages, and what that promises you |
| [`docs/testing.md`](docs/testing.md) | You want to know how tests run and what CI provides |
| [`docs/AGENTS.md`](docs/AGENTS.md) | You are writing or editing any documentation, including a changelog entry |
| [`docs/release.md`](docs/release.md) | You are publishing a release |

## Changing an existing package

Work inside the package directory — it owns its own tests, lint config and version:

```bash
cd packages/dlt-source-aquabyte
uv run ruff format src tests examples
uv run ruff check --fix src tests examples
uv run pyright
uv run pytest                    # offline; add -m integration for the live API
```

CI runs all four on every pull request, for every package, and the single required check is `CI OK`. Running them locally first is faster than finding out from a red build.

Two things that are easy to forget:

- **Add a changelog entry** under `## [Unreleased]` in the package's `CHANGELOG.md`, describing what a *user of the package* will notice. Not needed for a change nobody installing the package can see — refactoring, tests, CI, docs.
- **If the change moves which API version the package is built against**, update the `## Compatibility` table in the package's README. That table is the single home for that mapping.

## Adding a new source package

Copy [`packages/dlt-source-aquabyte/`](packages/dlt-source-aquabyte/) and adapt it. It is the worked example, and copying it is the intended way to start — a package that looks like the others is one every contributor can already read.

Adding a folder is the whole job. The workspace root picks it up (`members = ["packages/*"]`), and CI loops over every package directory, so there is no workflow to write and no repository setting to change. What your package must have:

| | |
|---|---|
| `pyproject.toml` | Own name, own version, own dependencies. Keep the `[tool.ruff]`, `[tool.pyright]` and `[tool.pytest.ini_options]` sections as they are in `dlt-source-aquabyte`, so the standards stay identical everywhere. |
| `src/<module>/` | The importable package. dlt and pydantic only — see the source guidelines. |
| `tests/` | Passing without credentials or network. Give test files names that will not collide with another package's. |
| `examples/` | Runnable, one concept each. This is where destination, orchestration and logging choices are shown instead of being built in. |
| `README.md` | Including a `## Compatibility` table |
| `CHANGELOG.md` | Starting with an `## [Unreleased]` section |
| `LICENSE` | A copy of the repository's `LICENSE`. Packaging tools read it from the package directory. |
| `CONTEXT.md` | The package's glossary — see [`docs/domain.md`](docs/domain.md) |

The one thing that is not automatic is PyPI registration before the first publish, in [`docs/release.md`](docs/release.md#first-release-of-a-package).

## Pull requests

- **One branch per change**, off current `main`. Pull requests are squash-merged, so the pull request title becomes the commit message on `main`.
- **Write the title as a plain sentence** saying what changed, prefixed with the package name when it concerns one: `dlt-source-aquabyte: type the fishType field on harvest_report`.
- **Say what you verified**, not only what you changed. For a change driven by the API behaving unexpectedly, say what you observed live and when.
- **Keep unrelated changes out.** A reviewer who has to separate two changes reviews neither well.

Releases are not part of a pull request. Bumping a version and pushing a tag is a separate, deliberate step: [`docs/release.md`](docs/release.md).

## Licensing

The repository is licensed under [Apache-2.0](LICENSE). By opening a pull request you agree that your contribution is licensed the same way. There is no separate contributor agreement to sign.
