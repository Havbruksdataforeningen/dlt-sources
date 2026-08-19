# dlt-source-aquabyte

An installable [dlt](https://dlthub.com/) source package that loads aquaculture data from the [Aquabyte API v3](https://api.aquabyte.ai/v3/docs) into any dlt destination: sites, pens, biomass, lice counts, welfare scores, behaviour and environmental readings.

**Records land as the API returns them** — nothing renamed, nothing dropped, no invented child tables. What *is* added is named up front rather than discovered later: `_dlt_valid_from` and `_dlt_valid_to` on the two versioned tables, and the pens nested inside each site, unwrapped into a `pens` table. Column names are the API's own field names, in dlt's usual snake_case.

Everything else is mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key and write-disposition defaults. Reshaping belongs in your transform layer, where you can change it without waiting for a release. The package depends on dlt and nothing else — destination, orchestrator, secrets manager and log routing stay your choices.

## Install

```bash
uv add dlt-source-aquabyte "dlt[duckdb]"   # any dlt destination works; DuckDB is the one below
```

## Quick start

Put the API base URL and your key in a `.dlt/` directory beside the script you are about to run.

`.dlt/config.toml`:

```toml
[sources.aquabyte]
base_url = "https://api.aquabyte.ai/v3/"
initial_date = "2020-01-01"             # first-run start for the date-based cursors
initial_time = "2020-01-01T00:00:00Z"   # first-run start for the time-based cursors
```

`.dlt/secrets.toml`:

```toml
[sources.aquabyte]
api_key = "your-api-key-here"
```

Then load every resource:

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

The two `initial_*` values are the first-run start for the resources that keep an incremental cursor; a run of only `sites`, `pens` or `environmental_latest` needs neither, and a cursor resource missing one fails with an error naming it. How far back your data goes differs per endpoint and per account, and setting a start earlier than that costs empty requests, not errors.

## What it loads

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `sites` | `GET /sites`, `GET /sites/{siteId}` | merge, `scd2` | `id` (merge key) |
| `pens` | _(transformer over `sites`)_ | merge, `scd2` | `id` (merge key) |
| `environmental` | `GET /environmental` | merge | `penId`, `fromTime`, `toTime` |
| `environmental_latest` | `GET /environmental/latest` | replace | — |
| `biomass` | `GET /biomass` | merge | `penId`, `date` |
| `harvest_report` | `GET /biomass/harvestReport` | merge | `penId`, `slaughterStartDate`, `mainReport`, `asOfDate` |
| `lice_count` | `GET /liceCount` | merge | `penId`, `date` |
| `behaviour_swim_speed` | `GET /behaviour/swimSpeed` | merge | `penId`, `fromTime`, `toTime` |
| `behaviour_breathing_index` | `GET /behaviour/breathingIndex` | merge | `penId`, `fromTime` |
| `welfare_scores` | `GET /welfareScores` | merge | `penId`, `date` |

`sites` reads every site, and `pens` unwraps the pens nested in each one — every pen, active or not. Both are **versioned rather than replaced**: a row is retired, never deleted, because a pen leaves `/sites` as soon as it is emptied ([what that means for your queries](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#the-registry-tables-are-versioned)). Nested objects land as one JSON column each, and `welfare_scores` is not unpivoted ([why, and how to override it](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#nesting)).

## Configuring a resource

Each resource takes exactly the params its endpoint documents, in snake_case:

```python
source = aquabyte_source()
source.sites.bind(site_id="site-001")     # switches to GET /sites/{siteId}
source.biomass.bind(pen_id="pen-abc", from_date="2026-01-01", bucket_size=500)
pipeline.run(source)
```

- **`pen_id`** defaults to `"all"` — the API's own value for "every pen", in one request. Pass one id, or a list to issue one request per pen. It is the one param `params` cannot override: it drives the fan-out, so `penId` is re-stamped per request after the merge.
- **Window params** (`from_date`/`from_time`) default to the incremental cursor, so a daily run resumes where it left off. Backfilling a past window has its own rule — see [the reference](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#windows-cursors-and-backfilling).
- **`params`** is on every resource and merged into the query string last: the escape hatch for a query param the API grows later, no release needed.

Params can also be set in config, per resource:

```toml
[sources.aquabyte.environmental]
period = "15min"
```

The package logs on the named logger `dlt_source_aquabyte` and installs no handlers, so [routing is yours](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#logging).

## Examples

One concept each, readable on GitHub. From a checkout, run one with `python examples/<name>.py`.

| Example | The one concept |
|---|---|
| [`quickstart.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/quickstart.py) | Load every resource into DuckDB |
| [`daily_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/daily_load.py) | Re-running resumes from the stored cursor |
| [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py) | Re-load a window, stored cursor untouched |
| [`logging_setup.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/logging_setup.py) | Route the package's logger consumer-side |

## Compatibility

| `dlt-source-aquabyte` | Aquabyte API |
|---|---|
| 0.1.x | v3.1 |

The two numbers are unrelated — the package version is ordinary [SemVer](https://semver.org/) and never mirrors the API's. Built against that version's [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md) and run against the live API (last on 2026-08-17). A later backwards-compatible version is expected to work and is not verified here; run the suite first.

## Read next

- [**Reference**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md) — versioned registry tables, nesting, backfilling, column types, and what the source deliberately does not expose.
- [**API quirks worth knowing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing) — where the live API departs from its own OpenAPI document, including which identifiers to join on. Some of them change what a correct query looks like, so read it before your first one.
- [**Changelog**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/CHANGELOG.md) and [**contributing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/LICENSE). `specs/openapi.json` is Aquabyte's own OpenAPI document, included as the spec this package is built against; it is their material, and the licence does not extend to it.
