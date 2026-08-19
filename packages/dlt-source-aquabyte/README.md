# dlt-source-aquabyte

An installable [dlt](https://dlthub.com/) source package that ingests aquaculture data from the [Aquabyte API v3](https://api.aquabyte.ai/v3/docs) into any dlt destination.

**Records land exactly as the API returns them** — nothing renamed, flattened, filtered or dropped. The source's only opinions are mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key/write-disposition defaults. Reshaping belongs in your transform layer, where you can change it without waiting for a release.

It depends on dlt and pydantic and nothing else — destination, orchestrator, secrets manager and log routing stay your choices, shown as runnable code in [`examples/`](https://github.com/Havbruksdataforeningen/dlt-sources/tree/main/packages/dlt-source-aquabyte/examples).

## Compatibility

| `dlt-source-aquabyte` | Aquabyte API |
|---|---|
| 0.1.x | v3.1 |

The two numbers are unrelated: the package version is ordinary [SemVer](https://semver.org/) describing what changed *for you*, and never mirrors the API's.

**Tested** — built against that version's [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md), asserted by `tests/test_param_surface.py`, and run against the live API (last on 2026-08-17). **Expected to work** — any later backwards-compatible version: the source holds no opinions the API can invalidate, so a compatible change usually needs no release here. Nothing verifies that for you; on a version not in the table, run the suite first.

The [`CHANGELOG`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/CHANGELOG.md) gets a line only when this table changes.

## Quick start

```bash
uv sync --group dev                              # --group dev adds DuckDB and the test deps
cp .dlt/config.toml.example .dlt/config.toml
cp .dlt/secrets.toml.example .dlt/secrets.toml   # then put your API key in it
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

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `sites` | `GET /sites`, `GET /sites/{siteId}` | merge, `scd2` | `id` (merge key) |
| `pens` | _(transformer over `sites`)_ | merge, `scd2` | `id` (merge key) |
| `environmental` | `GET /environmental` | merge | `penId`, `fromTime`, `toTime` |
| `environmental_latest` | `GET /environmental/latest` | replace | — |
| `biomass` | `GET /biomass` | merge | `penId`, `date` |
| `harvest_report` | `GET /biomass/harvestReport` | merge | `penId`, `slaughterStartDate` |
| `lice_count` | `GET /liceCount` | merge | `penId`, `date` |
| `behaviour_swim_speed` | `GET /behaviour/swimSpeed` | merge | `penId`, `fromTime`, `toTime` |
| `behaviour_breathing_index` | `GET /behaviour/breathingIndex` | merge | `penId`, `fromTime` |
| `welfare_scores` | `GET /welfareScores` | merge | `penId`, `date` |

`sites` reads every site. Binding `site_id` switches it to `GET /sites/{siteId}`, the API's only way to ask for one:

```python
source = aquabyte_source()
source.sites.bind(site_id="site-001")
```

Both endpoints write the same `sites` table, and backfilling one site does not disturb the others — see below.

`pens` unwraps the pens nested inside each `/sites` record — every pen, active or not. The data resources do not need it: they use the API's own `penId=all`, one request instead of one per pen.

### The registry tables are versioned

`/sites` reports what exists *today*, and a pen leaves it as soon as it is emptied, possibly after years of production. Replacing these tables each run would drop the row with it, so both load with dlt's [`scd2` strategy](https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy): **a row is never deleted**, only retired by stamping `_dlt_valid_to`.

```sql
SELECT * FROM pens WHERE _dlt_valid_to IS NULL;                    -- current
SELECT * FROM pens WHERE id = 'pen-002' ORDER BY _dlt_valid_from;  -- one pen's history
```

**What counts as a new version.** Any `pens` field changing, `isActive` included. For `sites`, its own fields only — dlt hashes the whole record by default, so a renamed pen would otherwise version its site too; `sites` carries a `_site_version` column (everything except `pens`) used as dlt's [`row_version_column_name`](https://dlthub.com/blog/scd2-nested-json-data-cost-optimization). So when only pens change, the `sites` row is untouched and its nested `pens` snapshot goes stale: read `pens` for pen state.

**`merge_key="id"`** scopes retirement to the ids a load actually carried, which is what makes `bind(site_id=...)` safe. The trade-off: a site or pen absent from a *full* response is not retired either, and stays current indefinitely. Retire-on-absence and safe partial loads are the same switch, and this source picks the one that cannot lose data.

⚠️ To choose the other side, drop the merge key on a pipeline's **first** load only. dlt stores `merge_key` on the column and never removes it, so `apply_hints(merge_key=())` against an existing table is silently ignored (verified against dlt 1.30).

Background: [SCD2 and incremental loading](https://dlthub.com/blog/scd2-and-incremental-loading).

### `welfare_scores` is not unpivoted

The API returns one record per pen and date with every welfare category nested inside, and that is what lands: `penId`, `date`, and the nested object as one JSON column. A category the API adds later arrives untouched, because nothing here enumerates categories. Flattening it is a transform on your side — `LATERAL`/`UNNEST` in your warehouse, or dlt's `add_map` before load.

### API quirks worth knowing

Where the live API departs from its own OpenAPI document, that reaches you rather than being smoothed over here. The departures are written down in [`specs/README.md`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing), including which identifiers to join on — which differs depending on whether you join within this dataset or out to your own systems.

**Read it before your first query.** Some of them change what a correct query looks like.

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position, not an extra opinion: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and it would make the destination shape depend on which fields happened to be nested in the first page loaded.

**A default, not a lock:**

```python
source = aquabyte_source()
source.max_table_nesting = 2          # every resource
source.sites.max_table_nesting = 1    # or just one — gives you a sites__pens table
```

This is also why the models in `schemas.py` declare scalar fields only: a declared nested field becomes a column hint dlt honours *over* this setting, silently ignoring a consumer who raised it. Nested fields still land — the models allow extras — but their shape stays your call. The one exception is `pens`, unwrapped by an explicit transformer rather than by dlt behind your back.

## Parameters

Each resource takes exactly the params its endpoint documents, in snake_case:

```python
source = aquabyte_source()
source.biomass.bind(pen_id="pen-abc", from_date="2026-01-01", bucket_size=500)
source.environmental.bind(period="15min")
pipeline.run(source)
```

- **`pen_id`** defaults to `"all"` — the API's own value for "every pen", in one request. Pass one id, or a list to issue one request per pen. The one param `params` cannot override: it drives the fan-out, so `penId` is re-stamped per request after the merge.
- **Window params** (`from_date`/`from_time`) default to the incremental cursor and are always sent, falling back to `initial_date`/`initial_time` when there is no cursor value — so a run never silently inherits the API's own default window. Passing one explicitly overrides the cursor for that run, forward only: a window reaching back *before* the stored cursor is refused, because dlt's incremental filter would silently drop every fetched row below the cursor. To backfill, bind the window on the `incremental_*` argument instead — `dlt.sources.incremental(initial_value=..., end_value=...)` runs with transient state, so dlt fetches and keeps exactly that window and the stored cursor is neither consulted nor advanced. See [`examples/backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py).
- **`params`** is on every resource and merged into the query string last — the escape hatch for a query param the API grows later, no release needed.

Params can also be set in config, per resource:

```toml
[sources.aquabyte.environmental]
period = "15min"
```

`tests/test_param_surface.py` asserts each resource's signature against `specs/openapi.json`, so the parameter surface cannot drift from the spec.

### What the source does not expose

**`nextToken`**, on the six endpoints documenting it — pagination mechanics owned by dlt's `JSONResponseCursorPaginator`, and exposing it would let a caller break their own pagination. The other four read endpoints (`/sites`, `/sites/{siteId}`, `/environmental/latest`, `/biomass/harvestReport`) return none, so their resources read a single page rather than hoping a cursor paginator terminates.

⚠️ **The paginator has never actually run.** As of 2026-08-17 no live response had carried a `nextToken`: the API caps a result set at 10,000 records and nothing we asked for came close. The wiring is right by inspection and the offline suite covers it, but the first backfill wide enough to hit the cap will be its first real test.

**The eight `/pens/{penId}/…` path variants**, marked `deprecated: true` — the v3.0 shape of the same data, replaced in v3.1 by `?penId=`. None accepts `nextToken`, so a result set past the record cap cannot be paged through, and `penId=all` fetches every pen in one request. Bind `pen_id` to read one pen or several.

**`POST /superiorRate`** — marked "(Experimental API) … subject to change", and a POST computation rather than a read endpoint. Worth revisiting once it leaves preview.

Rate limit and result cap are in `specs/openapi.json`. The package does not throttle; close to the limit, prefer `pen_id="all"` over per-pen fan-out.

## Schemas

The Pydantic models in `schemas.py` give the destination proper column types even when the first page is all nulls. They allow extra fields, which dlt reads as the `evolve` column contract: **a field the API adds lands as a new column instead of failing the load.** Scalar fields only — see [Nesting](#nesting).

## Logging

The package logs on the named logger `dlt_source_aquabyte` and installs no handlers; routing is yours, via standard `logging`. It logs only what dlt cannot: an explicit window overriding the cursor (INFO), a pen-id fan-out (INFO), a window start falling back to config (WARNING), and the cursor value a run resumed from (DEBUG). dlt logs the requests. On failure it raises. See [`examples/logging_setup.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/logging_setup.py).

## Configuration

`.dlt/config.toml`:

```toml
[sources.aquabyte]
base_url = "https://api.aquabyte.ai/v3/"
initial_date = "2020-01-01"             # first-run start for date-based cursors
initial_time = "2020-01-01T00:00:00Z"   # first-run start for time-based cursors
```

The two `initial_*` starts are needed only by the resources that keep an incremental cursor — a run selecting just `sites`, `pens` or `environmental_latest` resolves without them, and a cursor resource missing one fails with an error naming it.

How far back your data goes depends on when your cameras started reporting each metric, so it differs per endpoint and per account. Setting these earlier than your true start costs only empty requests — the API returns an empty result set, not an error.

`.dlt/secrets.toml`:

```toml
[sources.aquabyte]
api_key = "your-api-key-here"
```

## Examples

One concept each — run any of them with `uv run python examples/<name>.py`.

| Example | The one concept |
|---|---|
| [`quickstart.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/quickstart.py) | Load every resource into DuckDB |
| [`daily_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/daily_load.py) | Re-running resumes from the stored cursor |
| [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py) | Re-load a window, stored cursor untouched |
| [`logging_setup.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/logging_setup.py) | Route the package's logger consumer-side |

## Development

```bash
uv sync --group dev
uv run ruff format src tests examples && uv run ruff check --fix src tests examples
uv run pyright
uv run pytest                    # offline; -m integration hits the live API
uv run pytest --clean-db         # ...and delete the DuckDB files afterwards
```

`src/` holds the source (`aquabyte.py`) and its Pydantic models (`schemas.py`); `specs/` holds the OpenAPI document both are built against. CI, releasing and how to contribute are the repository's, not this package's — see [`CONTRIBUTING.md`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/LICENSE). `specs/openapi.json` is Aquabyte's own OpenAPI document, included as the spec this package is built against; it is their material, and the licence does not extend to it.
