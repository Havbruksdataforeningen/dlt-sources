# Reference

The operational detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/README.md) — written for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

## The registry tables are versioned

`/sites` reports what exists *today*, and a pen leaves it as soon as it is emptied, possibly after years of production. Replacing these tables each run would drop the row with it, so `sites` and `pens` load with dlt's [`scd2` strategy](https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy): **a row is never deleted**, only retired by stamping `_dlt_valid_to`.

```sql
SELECT * FROM pens WHERE _dlt_valid_to IS NULL;                    -- current
SELECT * FROM pens WHERE id = 'pen-002' ORDER BY _dlt_valid_from;  -- one pen's history
```

**What counts as a new version.** Any field of the record changing. For `pens` that includes `isActive`; for `sites` it includes the nested `pens` list, so a pen being renamed, going inactive or leaving the response versions its site too. The nested snapshot on the current site row therefore always shows the pens the API last reported — and so a site accumulates a version per pen change, which at a member company's site count is a handful of rows.

**`merge_key="id"`** scopes retirement to the ids a load actually carried, which is what makes `bind(site_id=...)` safe. The trade-off: a site or pen absent from a *full* response is not retired either, and stays current indefinitely. Retire-on-absence and safe partial loads are the same switch, and this source picks the one that cannot lose data.

⚠️ To choose the other side, drop the merge key on a pipeline's **first** load only. dlt stores `merge_key` on the column and never removes it, so `apply_hints(merge_key=())` against an existing table is silently ignored (verified against dlt 1.30).

Background: [SCD2 and incremental loading](https://dlthub.com/blog/scd2-and-incremental-loading).

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position, not an extra opinion: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and it would make the destination shape depend on which fields happened to be nested in the first page loaded.

It is a default, not a lock:

```python
source = aquabyte_source()
source.max_table_nesting = 2          # every resource
source.sites.max_table_nesting = 1    # or just one — gives you a sites__pens table
```

Nothing outranks that setting. The source declares column hints for scalar fields only, so no hint names a nested field, and the destination shape of nested data stays your call. The one exception is `pens`, unwrapped by an explicit transformer rather than by dlt behind your back.

### `welfare_scores` is not unpivoted

The API returns one record per pen and date with every welfare category nested inside, and that is what lands: `penId`, `date`, and the nested object as one JSON column. A category the API adds later arrives untouched, because nothing here enumerates categories. Flattening it is a transform on your side — `LATERAL`/`UNNEST` in your warehouse, or dlt's `add_map` before load.

## Windows, cursors and backfilling

Window params (`from_date`/`from_time`) default to the incremental cursor and are **always sent**, falling back to `initial_date`/`initial_time` when there is no cursor value — so a run never silently inherits the API's own default window.

Passing one explicitly overrides the cursor for that run, forward only: a window reaching back *before* the stored cursor is refused, because dlt's incremental filter would silently drop every fetched row below the cursor.

To backfill, bind the window on the `incremental_*` argument instead. `dlt.sources.incremental(initial_value=..., end_value=...)` runs with transient state, so dlt fetches and keeps exactly that window and the stored cursor is neither consulted nor advanced. Runnable version: [`examples/backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py).

⚠️ **The cursor is per resource, not per pen.** One incremental cursor spans the whole pen fan-out (`penId=all` included), advancing to the newest row *any* pen reported. Data arriving late — a pen whose camera was offline, a re-issued `harvest_report` revision for an old slaughter — falls behind the cursor and is not requested again. When that matters, periodically re-load a recent window the backfill way; merge dispositions make re-loading idempotent.

## What the source does not expose

**`nextToken`**, on the six endpoints documenting it — pagination mechanics owned by dlt's `JSONResponseCursorPaginator`, and exposing it would let a caller break their own pagination. The other four read endpoints (`/sites`, `/sites/{siteId}`, `/environmental/latest`, `/biomass/harvestReport`) return none, so their resources read a single page rather than hoping a cursor paginator terminates.

⚠️ **The paginator has never actually run.** As of 2026-08-17 no live response had carried a `nextToken`: the API caps a result set at 10,000 records and nothing we asked for came close. The wiring is right by inspection and the offline suite covers it, but the first backfill wide enough to hit the cap will be its first real test.

**The eight `/pens/{penId}/…` path variants**, marked `deprecated: true` — the v3.0 shape of the same data, replaced in v3.1 by `?penId=`. None accepts `nextToken`, so a result set past the record cap cannot be paged through, and `penId=all` fetches every pen in one request. Bind `pen_id` to read one pen or several.

**`POST /superiorRate`** — marked "(Experimental API) … subject to change", and a POST computation rather than a read endpoint. Worth revisiting once it leaves preview.

Rate limit and result cap are in `specs/openapi.json`. The package does not throttle; close to the limit, prefer `pen_id="all"` over per-pen fan-out.

## Logging

The package logs on the named logger `dlt_source_aquabyte` and installs no handlers; routing is yours, via standard `logging`. It logs only what dlt cannot: an explicit window overriding the cursor (INFO), a pen-id fan-out (INFO), a window start falling back to config (WARNING), and the cursor value a run resumed from (DEBUG). dlt logs the requests. On failure it raises. See [`examples/logging_setup.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/logging_setup.py).

## Column types

Each resource declares column hints for its scalar fields, typed per [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md). They buy one thing: a column keeps its type when the first page happens to be all nulls, or the field is missing entirely.

Everything else is dlt's own default. A field the API adds after this release lands as a new column rather than failing the load, and a nullable field it stops sending is absent rather than fatal — `tests/test_schema_leniency.py` holds both to that. Dates and timestamps land as text, exactly as the API sends them; parsing them is a transform on your side.
