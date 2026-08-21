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

## Add a new dlt-ingest source/package

`packages/dlt-source-aquabyte/` is the template. There is no CI to write and no repository to create: the workspace globs `packages/*` and every CI job loops over it, so a new folder is picked up on the next push.

Throughout, `<sourcename>` is your supplier in lowercase — `barentswatch`, `fishtalk`. Two spellings of it matter and they are not interchangeable:

| | Looks like | Used for |
|---|---|---|
| **Distribution name** | `dlt-source-<sourcename>` | The folder, the PyPI project, the release tag, `pip install` |
| **Import name** | `dlt_source_<sourcename>` | The folder under `src/`, and every `import` |

**1. Copy the folder, named after the distribution.**

```bash
mkdir packages/dlt-source-<sourcename>
git archive HEAD packages/dlt-source-aquabyte \
  | tar -x --strip-components=2 -C packages/dlt-source-<sourcename>
mv packages/dlt-source-<sourcename>/src/dlt_source_{aquabyte,<sourcename>}
```

Copy through `git archive` rather than `cp -R`: you get the tracked files only, so no build residue, no `.duckdb` files and no local `.dlt/secrets.toml` come along.

The folder name must be the distribution name. CI builds each package as `uv build --package "$(basename "$d")"`, which takes a distribution name, so any other folder name fails the Build job.

**2. Rewrite the metadata in `pyproject.toml`.**

Change `name`, `description` and `keywords`, and set `version = "0.1.0"`. Leave `[tool.ruff]`, `[tool.pyright]` and `[tool.pytest.ini_options]` identical — they are the same for every package on purpose, so that one `uv run ruff check` means the same thing everywhere.

**3. Fix the four places that still name Aquabyte.**

Only the last one raises an error. The other three are wrong quietly, so check them off deliberately.

| Where | Change it to |
|---|---|
| `pyproject.toml` → `[project.urls]`, `Homepage` and `Changelog` | Your package's path in this repo. They are the links PyPI shows on the project page |
| `pyproject.toml` → `[tool.setuptools.package-data]`, the key | `dlt_source_<sourcename>`, the **import** name. A key that matches nothing drops `py.typed` from the wheel, and every consumer's type checker treats your package as untyped |
| `pyproject.toml` → `[tool.ruff.lint.isort]`, `known-first-party` | `dlt_source_<sourcename>`. Wrong, and ruff sorts your own imports as third-party |
| `src/dlt_source_<sourcename>/__init__.py` → `version("...")` | `dlt-source-<sourcename>`, the **distribution** name. If it does not match `[project] name`, importing the package raises `PackageNotFoundError` |

**4. Replace the contents.** Everything below is still Aquabyte's.

| Path | What to do |
|---|---|
| `src/`, `tests/`, `examples/` | Rewrite. Tests must pass with no credentials — CI has none |
| `specs/` | Replace `openapi.json` with your supplier's spec, or drop the folder if they publish none |
| `.dlt/config.toml.example`, `.dlt/secrets.toml.example` | Rewrite for your config keys. These two are the only `.dlt/` files that belong in git; the real `config.toml` and `secrets.toml` are gitignored |
| `README.md` | Rewrite, keeping the `## Compatibility` table — it is how a user knows which API version the package targets |
| `CHANGELOG.md` | Empty it down to an `## [Unreleased]` heading |
| `CONTEXT.md` | Rewrite. See [`docs/domain.md`](docs/domain.md) for what belongs in it |
| `REFERENCE.md` | Rewrite, or drop it until the package has operational detail worth separating from the README |
| `LICENSE` | Leave as it is |

Read [`docs/source-guidelines.md`](docs/source-guidelines.md) before writing the source code — it has the neutrality and logging rules every source follows.

**5. List the package where a reader starts.**

A row in the table in [`README.md`](README.md), and an entry in [`CONTEXT-MAP.md`](CONTEXT-MAP.md).

**6. Run the checks CI runs.**

```bash
uv sync --all-packages --all-groups     # picks up the new package, updates uv.lock
cd packages/dlt-source-<sourcename>
uv run ruff format src tests examples
uv run ruff check --fix src tests examples
uv run pyright
uv run pytest
```

Then confirm it builds the way the release will, from the repo root:

```bash
uv build --package dlt-source-<sourcename> --no-sources
```

**7. Open the pull request.** Include the changed `uv.lock`.

**8. Register the project on PyPI — before the first release, not now.**

Nothing in steps 1–7 touches PyPI, and the package can sit merged and unreleased for as long as you like. But the first release fails at the last step unless a **pending publisher** exists on both indexes, so do this before tagging: [`docs/release.md`](docs/release.md#first-release-of-a-package). It is a form on each of pypi.org and test.pypi.org, filled in the same way, and whoever fills it in owns the project — Havbruksdataforeningen's PyPI organization is still awaiting approval.

## Pull requests

Branch off `main`. Prefix PR titles with the package name when it concerns one:

```
dlt-source-aquabyte: type the fishType field on harvest_report
```

Say what you verified, not only what you changed. Keep unrelated changes out.

Releasing is separate from any pull request: [`docs/release.md`](docs/release.md).

## Conventions

[`docs/source-guidelines.md`](docs/source-guidelines.md) for source code, [`docs/AGENTS.md`](docs/AGENTS.md) for anything you write in prose, [`docs/monorepo.md`](docs/monorepo.md) for why one repo holds many packages.

## Licensing

[Apache-2.0](LICENSE). Opening a pull request licenses your contribution the same way. There is no CLA.
