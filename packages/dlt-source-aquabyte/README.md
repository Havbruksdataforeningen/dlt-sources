# dlt-source-aquabyte

An installable [dlt](https://dlthub.com/) source package that ingests aquaculture data from the [Aquabyte API v3](https://api.aquabyte.ai/v3/docs) into DuckDB (dev) or Snowflake (prod).

Covers all 10 stable GET endpoints using a transformer-based architecture: `sites → pens → per-pen data`. The `/sites` endpoint is fetched once, active pens are extracted, and all 7 per-pen endpoints consume from the shared `pens` transformer.

## Installation

```bash
uv sync              # Library only
uv sync --group dev  # With dev/test dependencies (includes DuckDB)
```

## Quick Start

```bash
# 1. Install with dev dependencies
uv sync --group dev

# 2. Configure credentials
cp .dlt/config.toml.example .dlt/config.toml
cp .dlt/secrets.toml.example .dlt/secrets.toml
# Edit .dlt/secrets.toml and add your API key

# 3. Run the example pipeline
uv run python examples/basic_pipeline.py
```

## Usage

```python
import dlt
from dlt_source_aquabyte import aquabyte_source

pipeline = dlt.pipeline(
    pipeline_name="aquabyte",
    destination="duckdb",
    dataset_name="aquabyte_data",
)
load_info = pipeline.run(aquabyte_source())
print(load_info)
```

### CLI Example

```bash
# Full pipeline (auto-discovers all active pens)
uv run python examples/basic_pipeline.py

# Specific pens only
uv run python examples/basic_pipeline.py --pen-ids pen-abc pen-def

# Backfill a date range (date-based endpoints)
uv run python examples/basic_pipeline.py --from-date 2025-01-01 --to-date 2025-06-30

# Backfill a time range (time-based endpoints)
uv run python examples/basic_pipeline.py --from-time 2025-01-01T00:00:00Z --to-time 2025-06-30T00:00:00Z
```

## API Endpoints

| Resource | API Endpoint | Load Strategy | Description |
|----------|-------------|---------------|-------------|
| `sites` | `GET /sites` | Full replace | All sites and their pens |
| `pens` | _(derived from sites)_ | Full replace | Active pens, extracted via transformer |
| `environmental` | `GET /pens/{penId}/environmental` | Incremental merge | Temperature, oxygen, salinity, depth |
| `environmental_latest` | `GET /environmental/latest` | Full replace | Most recent readings across pens |
| `biomass` | `GET /pens/{penId}/biomass` | Incremental merge | Daily weight, K-factor, distributions |
| `harvest_report` | `GET /pens/{penId}/biomass/harvestReport` | Incremental merge | Slaughter reports and weights |
| `lice_count` | `GET /pens/{penId}/liceCount` | Incremental merge | Adult female, mobile, caligus counts |
| `swim_speed` | `GET /pens/{penId}/behavior/swimSpeed` | Incremental merge | Swim speed and tilt metrics |
| `breathing_index` | `GET /pens/{penId}/behavior/breathingIndex` | Incremental merge | Breathing frequency index |
| `welfare_scores` | `GET /pens/{penId}/welfareScores` | Incremental merge | 18 welfare categories (unpivoted) |

`site_by_id` (`GET /sites/{siteId}`) is available as a standalone utility for targeted lookups.

## Configuration

### `.dlt/config.toml`

```toml
[sources.aquabyte]
base_url = "https://api.aquabyte.ai/v3/"
environmental_period = "D"    # "15min", "h", or "D"
behavior_period = "D"         # "h" or "D"
initial_date = "2020-01-01"   # Start for date-based incremental endpoints
initial_time = "2020-01-01T00:00:00Z"  # Start for time-based incremental endpoints
```

### `.dlt/secrets.toml`

```toml
[sources.aquabyte]
api_key = "your-api-key-here"
```

## Development

```bash
uv sync --group dev                                      # Install dependencies
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/  # Lint and format
uv run pyright                                            # Type check
uv run bandit -r src/ -c pyproject.toml                   # Security scan
uv run python -m pytest -m "not integration"              # Unit tests (mocked API)
uv run python -m pytest -m integration                    # Integration tests (needs credentials)
```

## Project Structure

```
aquabyte_v3/
├── src/
│   └── dlt_source_aquabyte/
│       ├── __init__.py      # Re-exports aquabyte_source, site_by_id, __version__
│       ├── aquabyte.py      # dlt source, resources, and transformers
│       └── schemas.py       # Pydantic models from OpenAPI schemas
├── examples/                # Pipeline runner scripts
├── specs/                   # OpenAPI spec (source of truth)
├── tests/                   # pytest tests + mock_responses/ + conftest.py
├── .dlt/                    # Config and secrets (not committed)
└── .github/workflows/       # CI workflow (quality + integration)
```
