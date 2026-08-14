# Testing

How tests are run in this repo. **Not** how to write them — that is each package's own business.

## Each package owns its tests

A source package decides how it tests itself: what it fakes, what it asserts on, how it structures fixtures. One supplier's API might justify recorded responses; another might have a public sandbox worth testing against for real. Those are package-level calls, and the package author is the one who can make them.

So this document is short on purpose. Instead of rules, look at [`packages/dlt-source-aquabyte/tests/`](../../packages/dlt-source-aquabyte/tests/) — it is the worked example, and it is the thing to copy from when you add a package.

## Where tests live

```
packages/<name>/tests/
```

Inside the package, next to the code it tests. There is no repo-level test suite and no repo-level `conftest.py`.

Each package configures pytest itself, in its own `pyproject.toml`. That is what keeps packages independent: you can change markers, plugins or settings in your package without affecting anyone else's.

## How they run

**Locally**, from the package directory:

```bash
uv run pytest
```

**In CI**, on every pull request, the same command runs in every package directory. Every package's suite runs on every PR — not only the ones you changed. That is deliberate: it is simple, it needs no configuration, and it catches a change in one package that breaks another. If CI ever gets slow enough to be annoying, that is the moment to make it smarter, not before.

Coverage is measured and printed, never enforced. There is no minimum percentage to hit.

## What CI gives you, and what it doesn't

**CI has no supplier credentials.** It gets no API keys, no accounts, no secrets. So whatever `uv run pytest` does in your package, it has to work without them and pass.

If your package has tests that need real credentials or a real API, keep them out of the default `pytest` run — for example in a separate directory that your `addopts` ignores — and run them by hand. There is no scheduled job that runs them for you, and nothing stops you adding one for a specific package later if it earns its place.

**CI runs format, lint and type checks as separate jobs**, alongside the tests, so one push tells you about all of them at once. See [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

## Two things to keep to

These are about not breaking other people, not about testing style:

- **The default test run writes only inside `tmp_path`.** It runs on other people's machines and in CI, and should leave nothing behind. Tests you run by hand — live tests especially — are welcome to write a `.duckdb` file into the package directory so you can inspect what was ingested; `*.duckdb` is gitignored, so it stays on your machine.
- **Give test files names that will not collide** across packages, or put `__init__.py` in your test folders. Two packages both having a bare `test_sites.py` confuses pytest's default import mode.
