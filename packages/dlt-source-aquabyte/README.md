# dlt-source-aquabyte

An installable [dlt](https://dlthub.com/) source package that ingests aquaculture data from the [Aquabyte API v3](https://api.aquabyte.ai/v3/docs) into any dlt destination.

The source's only opinions are mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key/write-disposition defaults. **Records land exactly as the API returns them** — nothing renamed, flattened, filtered or dropped. Reshaping belongs in your transform layer, where you can change it without waiting for a release.

It depends on dlt and pydantic, and on nothing else: no destination, orchestrator, secrets manager or logging backend is chosen for you. Those are your stack's decisions, shown as runnable code in [`examples/`](examples/).

## Installation

```bash
uv sync              # Library only
uv sync --group dev  # With dev/test dependencies (includes DuckDB)
```

## Quick start

```bash
# 1. Install with dev dependencies
uv sync --group dev

# 2. Configure credentials
cp .dlt/config.toml.example .dlt/config.toml
cp .dlt/secrets.toml.example .dlt/secrets.toml
# Edit .dlt/secrets.toml and add your API key

# 3. Run
uv run python examples/quickstart.py
```

```python
import dlt
from dlt_source_aquabyte import aquabyte_source

pipeline = dlt.pipeline(
    pipeline_name="aquabyte",
    destination="duckdb",     # any dlt destination
    dataset_name="aquabyte_data",
)
print(pipeline.run(aquabyte_source()))
```

## Resources

| Resource | Endpoint | Load strategy | Primary key |
|---|---|---|---|
| `sites` | `GET /sites` | replace | — |
| `pens` | _(transformer over `sites`)_ | replace | — |
| `environmental` | `GET /environmental` | merge | `penId`, `fromTime` |
| `environmental_latest` | `GET /environmental/latest` | replace | — |
| `biomass` | `GET /biomass` | merge | `penId`, `date` |
| `harvest_report` | `GET /biomass/harvestReport` | merge | `penId`, `slaughterStartDate` |
| `lice_count` | `GET /liceCount` | merge | `penId`, `date` |
| `behaviour_swim_speed` | `GET /behaviour/swimSpeed` | merge | `penId`, `fromTime` |
| `behaviour_breathing_index` | `GET /behaviour/breathingIndex` | merge | `penId`, `fromTime` |
| `welfare_scores` | `GET /welfareScores` | merge | `penId`, `date` |

`site_by_id` (`GET /sites/{siteId}`) is a standalone resource for targeted lookups.

`pens` unwraps the pens the `/sites` response nests inside each site — every pen, active or not. The data resources do not depend on it: they use the API's own `penId=all`, one request instead of one per pen.

### `welfare_scores` is not unpivoted

The API returns one record per pen and date with every welfare category nested inside it, and that is what lands: `penId`, `date`, and the whole nested object as a single JSON column (`max_table_nesting=0`). A category the API adds after this release arrives untouched, because nothing here enumerates categories.

Flattening it into one row per category is a transform on your side — a `LATERAL`/`UNNEST` over the JSON column in your warehouse, or dlt's `add_map` before load.

## Parameters

Each resource takes exactly the query params its endpoint documents, in snake_case:

```python
source = aquabyte_source()
source.biomass.bind(pen_id="pen-abc", from_date="2026-01-01", bucket_size=500)
source.environmental.bind(period="15min")
pipeline.run(source)
```

- **`pen_id`** defaults to `"all"` — the API's own value for "every pen", in one request. Pass a single pen id, or a list to issue one request per pen.
- **Window params** (`from_date`/`from_time`) default to the incremental cursor. Passing one explicitly overrides the cursor for that run.
- **`params`** is on every resource and merged into the query string last — the escape hatch for a query param the API grows later, no release needed.

Params can also be set in config, per resource:

```toml
[sources.aquabyte.environmental]
period = "15min"
```

[`docs/parameter-inventory.md`](docs/parameter-inventory.md) accounts for every parameter and endpoint in the spec — implemented, or omitted with the reason. `tests/test_param_surface.py` checks the code against the same spec file, so the two cannot drift apart.

## Schemas

The Pydantic models in `schemas.py` give the destination proper column types even when the first page is all nulls, and double as documentation of the API's record shapes. They allow extra fields, which dlt reads as the `evolve` column contract: **a field the API adds lands as a new column instead of failing the load.**

## Logging

The package logs on the named logger `dlt_source_aquabyte` and installs no handlers — routing is yours, via standard `logging`. It logs only what dlt cannot: an explicit window overriding the incremental cursor (INFO), no window start at all (WARNING), the cursor value a run resumed from and each request's params (DEBUG). On failure it raises. See [`examples/logging_setup.py`](examples/logging_setup.py).

## Configuration

`.dlt/config.toml`:

```toml
[sources.aquabyte]
base_url = "https://api.aquabyte.ai/v3/"
initial_date = "2020-01-01"             # first-run start for date-based cursors
initial_time = "2020-01-01T00:00:00Z"   # first-run start for time-based cursors
```

`.dlt/secrets.toml`:

```toml
[sources.aquabyte]
api_key = "your-api-key-here"
```

## Examples

| Example | What it shows |
|---|---|
| [`quickstart.py`](examples/quickstart.py) | Minimal run of every resource into DuckDB |
| [`daily_load.py`](examples/daily_load.py) | Scheduled incremental load, resuming from the stored cursor |
| [`backfill.py`](examples/backfill.py) | Re-loading an explicit historical window |
| [`logging_setup.py`](examples/logging_setup.py) | Routing the package's logger consumer-side |

## Development

```bash
uv sync --group dev                                      # Install dependencies
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/  # Lint and format
uv run pyright                                            # Type check
uv run bandit -r src/ -c pyproject.toml                   # Security scan
uv run python -m pytest -m "not integration"              # Unit tests (mocked API)
uv run python -m pytest -m integration                    # Integration tests (needs credentials)
```

## Project structure

```
dlt-source-aquabyte/
├── src/dlt_source_aquabyte/
│   ├── __init__.py      # Re-exports aquabyte_source, site_by_id, __version__
│   ├── aquabyte.py      # Source, resources and transformer
│   └── schemas.py       # Pydantic models from the OpenAPI schemas
├── docs/                # Parameter inventory
├── examples/            # Runnable consumer-side setups
├── specs/               # OpenAPI spec (source of truth)
├── tests/               # pytest tests + mock_responses/ + conftest.py
├── .dlt/                # Config and secrets (not committed)
└── .github/workflows/   # CI workflow (quality + integration)
```
