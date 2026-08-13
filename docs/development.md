# Developing

## Setup

```bash
uv sync --all-packages --all-groups   # one shared dev environment for all members
```

## Working on a package

Each package has its own tests and lint config; run them from the package folder:

```bash
cd packages/dlt-source-aquabyte
uv run pytest -m "not integration"
uv run ruff format --check src tests && uv run ruff check src tests
```

Build one package: `uv build --package dlt-source-aquabyte` (from the repo root).

## CI

Every package's format check, lint, and tests run on every PR
(`.github/workflows/ci.yml`). Path filtering is deliberately skipped until the
minute of extra CI time actually hurts.

## Adding a new source

1. Copy the folder shape of an existing package into `packages/dlt-source-<name>/`.
2. Give it its own `pyproject.toml` (name, version `0.1.0`, dependencies).
3. That's it — CI picks it up automatically. Release setup is a separate one-time
   step, see [releasing](releasing.md).
