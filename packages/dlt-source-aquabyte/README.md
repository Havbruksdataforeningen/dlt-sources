# dlt-source-aquabyte

A [dlt](https://dlthub.com/) source for the [Aquabyte API v3](https://api.aquabyte.ai/v3/docs): sites, biomass, lice counts, welfare scores, behaviour and environmental readings, into any dlt destination.

**Records land as the API returns them** — nothing renamed, nothing dropped, no invented child tables. Column names are the API's own, in dlt's usual snake_case. Reshaping belongs in your transform layer, where you can change it without waiting for a release.

The package handles auth, pagination, envelope unwrapping, incremental cursors and window splitting. Its only dependency is dlt.

## How to start

Three examples, in this order. That is everything needed to get running, a page of code each.

1. **Discover** — [`discover_history.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/discover_history.py). How far back your account goes and how much is there, per resource. Its output is the input to the next step.
2. **Backfill** — [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py). Load that history in one run, from the earliest date you just measured. The stored cursor is left alone, so this can be re-run at any time without disturbing step 3.
3. **Daily load** — [`quickstart.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/quickstart.py). The same script on a timer from then on, each run resuming from the cursor.

No step computes a window: the source splits a multi-year span into requests the API accepts. From a checkout, run one with `python examples/<name>.py`.

## Install

```bash
uv add dlt-source-aquabyte "dlt[duckdb]"   # any dlt destination works; DuckDB is the one below
```

## Quick start

Two files in a `.dlt/` directory beside your script.

`.dlt/config.toml`:

```toml
[sources.aquabyte]
base_url = "https://api.aquabyte.ai/v3/"
initial_date = "2020-01-01"            # first-run start, date resources
initial_time = "2020-01-01T00:00:00Z"  # first-run start, time resources
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
    destination="duckdb",  # any dlt destination
    dataset_name="aquabyte_data",
)
print(pipeline.run(aquabyte_source()))
```

Three things about those start values:

- **Start as far back as you like.** A long first run is split into windows the API accepts. A start earlier than your data costs empty requests, not errors.
  How far back your account actually goes is worth measuring first: [`discover_history.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/discover_history.py).
- **`welfare_scores` is the exception.** It refuses any start before **2024-04-20**, so an older `initial_date` fails that one resource on every run. Give it a start of its own:

  ```python
  source.welfare_scores.bind(incremental_date=dlt.sources.incremental(initial_value="2024-04-20"))
  ```

- **`sites` and `environmental_latest` need neither value**, keeping no cursor. A cursor resource missing one fails with an error naming it.

## What it loads

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `sites` | `GET /sites`, `GET /sites/{siteId}` | merge, `scd2` | `id` (merge key) |
| `environmental` | `GET /environmental` | merge | `penId`, `fromTime`, `toTime` |
| `environmental_latest` | `GET /environmental/latest` | replace | — |
| `biomass` | `GET /biomass` | merge | `penId`, `date` |
| `harvest_report` | `GET /biomass/harvestReport` | merge | `penId`, `slaughterStartDate`, `mainReport`, `asOfDate` |
| `lice_count` | `GET /liceCount` | merge | `penId`, `date` |
| `behaviour_swim_speed` | `GET /behaviour/swimSpeed` | merge | `penId`, `fromTime`, `toTime` |
| `behaviour_breathing_index` | `GET /behaviour/breathingIndex` | merge | `penId`, `fromTime` |
| `welfare_scores` | `GET /welfareScores` | merge | `penId`, `date` |

Three defaults worth knowing before your first query:

- **There is no pens table.** The API serves no pens endpoint, so each site record carries its pens as the API nests them, active or not — [where pen history lives](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#pens-live-on-the-site-record).
- **`sites` is versioned, not replaced.** A pen leaves `/sites` as soon as it is emptied, so a row is retired rather than deleted — [what that means for your queries](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#the-site-registry-is-versioned).
- **Nested objects land as one JSON column each**, `welfare_scores` included — [why, and how to override it](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#nesting).

## Configuring a resource

Each resource takes its endpoint's params in snake_case. The window is the exception: the incremental cursor drives it, and a backfill binds it on the resource's `incremental_*` argument ([how](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#windows-cursors-and-backfilling)).

```python
source = aquabyte_source()
source.sites.bind(site_id="site-001")  # switches to GET /sites/{siteId}
source.biomass.bind(pen_id="pen-abc", bucket_size=250)
pipeline.run(source)
```

| Param | What to know |
|---|---|
| `pen_id` | Defaults to `"all"`, the API's own value for every pen in one request. Pass one id to read a single pen. |
| `site_id` | The one path param. Binding it moves `sites` to the per-site endpoint; both write the same table. |
| `params` | On every resource, merged into the query string last, so it wins over every named param. The escape hatch for a param the API grows later. |

Params can also be set in config, per resource:

```toml
[sources.aquabyte.environmental]
period = "15min"
```

### Two params decide the grain of the data itself

`period` and `bucket_size` change what the API computes for you, not which rows you ask for. Decide both before the first load: a coarse setting is not wrong, but the detail under it never lands, and getting it later means re-loading that history the backfill way.

| Param | Resource | Values | API default | What it decides |
|---|---|---|---|---|
| `period` | `environmental` | `h`, `D`, `15min` | `D` | Row grain: `h` is 24× the rows of `D`, `15min` is 96× |
| `period` | `behaviour_swim_speed` | `h`, `D` | `D` | As above. `15min` here is a `422` — only `environmental` takes it |
| `bucket_size` | `biomass` | integer grams | `1000` | Bucket width of the nested `weightDist` histogram — no extra rows |

⚠️ **Changing `period` later leaves both grains in the table.** The key is `penId` + `fromTime` + `toTime`, so hourly rows do not merge over the daily ones they cover. Keep one period per resource, or re-load the history behind the change. That is also why `behaviour_breathing_index` drops `toTime` from its key: it is daily-only, so its grain cannot change.

`period` also sets the widest window the API accepts — 7 days at `15min`, 31 at `h`, 366 at `D` — and the source splits its requests to fit, so a long catch-up works at any grain ([detail](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md#windows-are-split-to-fit-the-window-cap)).

`weightDist` covers only the weights observed, so a smolt pen returns two buckets and a harvest-size pen at 250 g a few dozen ([what the arrays hold](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing)).

## Compatibility

| `dlt-source-aquabyte` | Aquabyte API |
|---|---|
| 0.1.x | v3.1 |

The two numbers are unrelated: the package version is ordinary [SemVer](https://semver.org/). Built against that API version's [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md) and run live against it, last on 2026-08-31. A later backwards-compatible API version should work, but run the suite first.

## Read next

- [**API quirks worth knowing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing) — where the live API departs from its OpenAPI document, and which identifiers to join on. Some change what a correct query looks like, so read it before your first one.
- [**Reference**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/REFERENCE.md) — site versioning, nesting, backfilling, window splitting, logging and column types.
- [**Changelog**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/CHANGELOG.md) and [**contributing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/LICENSE). `specs/openapi.json` is Aquabyte's own OpenAPI document, included as the spec this package is built against. It is their material, and the licence does not extend to it.
