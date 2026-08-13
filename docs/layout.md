# Repo layout

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each source is a
folder under `packages/` with its **own** `pyproject.toml` — own name, own dependencies, own
independent version. The workspace root is never published, and the monorepo is invisible to
consumers: a package installed from PyPI looks identical to one built from a dedicated repo.

```
dlt-sources/
├── pyproject.toml                    ← workspace root (never published)
└── packages/
    └── dlt-source-aquabyte/
        ├── pyproject.toml
        ├── src/dlt_source_aquabyte/  ← the only part that reaches a consumer
        ├── tests/
        └── examples/
```

Adding source number two = adding a folder. CI, lint config, review habits, and (eventually)
the release workflow are inherited, not re-established per repo.

Candidates to migrate in if the layout is adopted: `dlt-barentswatch-source`
(from Ingest-Barentswatch) and `dlt-fiskeridirektoratet-source`.
