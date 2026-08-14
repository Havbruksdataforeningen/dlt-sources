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

The API returns one record per pen and date with every welfare category nested inside it, and that is what lands: `penId`, `date`, and the whole nested object as a single JSON column. A category the API adds after this release arrives untouched, because nothing here enumerates categories.

Flattening it into one row per category is a transform on your side — a `LATERAL`/`UNNEST` over the JSON column in your warehouse, or dlt's `add_map` before load.

## Nesting

The source sets `max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position, not an extra opinion: unnesting invents tables, column names and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and this source leaves reshaping to you. It also keeps the destination shape a function of the API response alone, rather than of which fields happened to be nested in the first page loaded.

**It is a default, not a lock.** Raise it for the whole source or one resource and dlt unnests as usual:

```python
source = aquabyte_source()
source.max_table_nesting = 2          # every resource
source.sites.max_table_nesting = 1    # or just one — gives you a sites__pens table
```

This is also why the Pydantic models in `schemas.py` declare scalar fields only. A declared nested field becomes a column hint that dlt honours *over* this setting, which would silently ignore a consumer who raised it. Nested fields still land — the models allow extra fields — but their shape stays your call. The one exception is `pens`, which is unwrapped by an explicit transformer you can see in the resource list, rather than by dlt behind your back.

## Parameters

Each resource takes exactly the query params its endpoint documents, in snake_case:

```python
source = aquabyte_source()
source.biomass.bind(pen_id="pen-abc", from_date="2026-01-01", bucket_size=500)
source.environmental.bind(period="15min")
pipeline.run(source)
```

- **`pen_id`** defaults to `"all"` — the API's own value for "every pen", in one request. Pass a single pen id, or a list to issue one request per pen. It is the one param `params` cannot override: `penId` is re-stamped per request after the merge, because it drives the fan-out.
- **Window params** (`from_date`/`from_time`) default to the incremental cursor, and are always sent — falling back to the configured `initial_date`/`initial_time` if there is no cursor value, so a run never silently inherits the API's own default window. Passing one explicitly overrides the cursor for that run.
- **`params`** is on every resource and merged into the query string last — the escape hatch for a query param the API grows later, no release needed.

Params can also be set in config, per resource:

```toml
[sources.aquabyte.environmental]
period = "15min"
```

`tests/test_param_surface.py` asserts each resource's signature against `specs/openapi-v3.1.1.json`, so the published parameter surface cannot drift from the spec.

### What the source does not expose

**`nextToken`**, on the six endpoints that document it. It is pagination mechanics, owned by dlt's `JSONResponseCursorPaginator`, which reads `nextToken` from each response and sends it on the next request until it is absent. Exposing it would let a caller break their own pagination. The other four read endpoints — `/sites`, `/sites/{siteId}`, `/environmental/latest` and `/biomass/harvestReport` — return no `nextToken` at all, so their resources read a single page (`SinglePagePaginator`) rather than hoping a cursor paginator terminates.

**The eight `/pens/{penId}/…` path variants.** These are the v3.0 shape of the same data; v3.1 replaced them with `?penId=` on the flat endpoints, and the spec's own migration note recommends the flat form. None of them accepts a `nextToken` query param either, so a result set past the API's 10,000-record cap cannot be paged through — and `penId=all` fetches every pen in one request where the path variants need one per pen, which matters against a 1000 requests/hour limit. To read one pen, bind `pen_id="pen-abc"`; to read several, bind a list.

**`POST /superiorRate`.** The spec marks it "(Experimental API) … subject to change", and it is a POST computation rather than a read endpoint. Worth revisiting once it leaves preview.

The API's own limits are worth knowing either way: **1000 requests/hour**, and a **10,000-record cap** per result set, paginated beyond that with `nextToken`. The package does not throttle; a consumer close to the limit should prefer `pen_id="all"` over per-pen fan-out.

## Schemas

The Pydantic models in `schemas.py` give the destination proper column types even when the first page is all nulls, and double as documentation of the API's record shapes. They allow extra fields, which dlt reads as the `evolve` column contract: **a field the API adds lands as a new column instead of failing the load.** They type scalar fields only — see [Nesting](#nesting) for why.

## Logging

The package logs on the named logger `dlt_source_aquabyte` and installs no handlers — routing is yours, via standard `logging`. It logs only what dlt cannot: an explicit window overriding the incremental cursor (INFO), a pen-id fan-out (INFO), a window start falling back to config because there was no cursor value (WARNING), and the cursor value a run resumed from (DEBUG). dlt itself logs the requests. On failure it raises. See [`examples/logging_setup.py`](examples/logging_setup.py).

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
├── examples/            # Runnable consumer-side setups
├── specs/               # OpenAPI spec (source of truth)
├── tests/               # pytest tests + mock_responses/ + conftest.py
├── .dlt/                # Config and secrets (not committed)
└── .github/workflows/   # CI workflow (quality + integration)
```
