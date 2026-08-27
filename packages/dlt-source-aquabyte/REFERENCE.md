# Reference

The operational detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/README.md) — written for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

## The site registry is versioned

`/sites` reports what exists *today*, and a pen leaves it as soon as it is emptied, possibly after years of production. Replacing the table each run would drop the row with it, so `sites` loads with dlt's [`scd2` strategy](https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy): **a row is never deleted**, only retired by stamping `_dlt_valid_to`.

```sql
SELECT * FROM sites WHERE _dlt_valid_to IS NULL;                     -- current
SELECT * FROM sites WHERE id = 'site-001' ORDER BY _dlt_valid_from;  -- one site's history
```

**What counts as a new version.** Any field of the record changing, the nested `pens` list included, so a pen being renamed, going inactive or leaving the response versions its site too. The snapshot on the current site row therefore always shows the pens the API last reported — and so a site accumulates a version per pen change, which at a member company's site count is a handful of rows.

**`merge_key="id"`** scopes retirement to the ids a load actually carried, which is what makes `bind(site_id=...)` safe. The trade-off: a site absent from a *full* response is not retired either, and stays current indefinitely. Retire-on-absence and safe partial loads are the same switch, and this source picks the one that cannot lose data.

⚠️ To choose the other side, drop the merge key on a pipeline's **first** load only. dlt stores `merge_key` on the column and never removes it, so `apply_hints(merge_key=())` against an existing table is silently ignored (verified against dlt 1.30).

Background: [SCD2 and incremental loading](https://dlthub.com/blog/scd2-and-incremental-loading).

### Pens live on the site record

There is no `pens` table. The API serves no pens endpoint; it nests each site's pens inside the site record, and that is how they land — the `pens` column, one JSON array, versioning with the site. It carries every field the API declares on a pen: `id`, `name`, `penCode`, `isActive` and `external_id`. Which of them to join on is in [Identifiers](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#identifiers).

Unnesting it is your transform layer's job. Current pens are the `pens` of the rows where `_dlt_valid_to IS NULL`; pen history is the `pens` of every version, each carrying that version's validity interval.

Two rules to build on, because they are the source's and not your warehouse's. The first is a guarantee; the second is a decision left to you:

- **A pen leaving a site retires the version that listed it.** That version's `_dlt_valid_to` is the date the pen stopped being reported, and the pen's full record — not only its id — stays readable on that row. The pen's history therefore survives the pen.
- **A site leaving `/sites` is not retired at all.** `merge_key="id"` retires only ids the load carried, so a site absent from even a full response keeps `_dlt_valid_to IS NULL`, carrying its last pens snapshot with it. Whether such a site counts as gone is your decision, not the source's: record a last-seen timestamp per load on your side and read it from that.

If you would rather have a flat pen table than write the unnest, set `source.sites.max_table_nesting = 1` before the run and a `sites__pens` table appears — see [Nesting](#nesting).

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position, not an extra opinion: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and it would make the destination shape depend on which fields happened to be nested in the first page loaded.

It is a default, not a lock:

```python
source = aquabyte_source()
source.max_table_nesting = 2          # every resource
source.sites.max_table_nesting = 1    # or just one — gives you a sites__pens table
```

Nothing outranks that setting. The source declares column hints for scalar fields only, so no hint names a nested field, and the destination shape of nested data stays your call.

### `welfare_scores` is not unpivoted

The API returns one record per pen and date with every welfare category nested inside, and that is what lands: `penId`, `date`, and the nested object as one JSON column. A category the API adds later arrives untouched, because nothing here enumerates categories. Flattening it is a transform on your side — `LATERAL`/`UNNEST` in your warehouse, or dlt's `add_map` before load.

## Windows, cursors and backfilling

The incremental cursor is the only window mechanism, and its value is **always sent** as the request's `fromDate`/`fromTime`. A daily load binds nothing: the first run starts at `initial_date`/`initial_time`, every later one resumes from the stored cursor. A run whose request would carry no window start fails with an error naming what to set, so it never silently inherits the API's own default window.

To backfill, bind the window on the resource's `incremental_*` argument: `dlt.sources.incremental(initial_value=..., end_value=...)` runs with transient state, so dlt fetches and keeps exactly that window and the stored cursor is neither consulted nor advanced. The `end_value` is sent as the request's `toDate`/`toTime`; with no `end_value` bound, the request still carries an end, which is now. Runnable version: [`examples/backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py).

A window overlaps by design, and dlt drops what it already has. A daily load asks again for the cursor's own value: one row per pen per day for the date-based resources, one `period` bucket for the time-based ones. A date backfill also asks for one day past `end_value`, because dlt's end is exclusive and the API's `toDate` is inclusive; `toTime` is exclusive, so the time-based resources have no such extra bucket. Neither overlap is worth correcting for.

⚠️ **The cursor is per resource, not per pen.** One cursor covers every pen the resource loads (`penId=all` included), advancing to the newest row *any* pen reported. Data arriving late — a pen whose camera was offline, a re-issued `harvest_report` revision for an old slaughter — falls behind the cursor and is not requested again. When that matters, periodically re-load a recent window the backfill way; merge dispositions make re-loading idempotent.

### The window is split to stay inside the API's cap

The API caps how wide a window may be, and refuses a wider one with `400 Requested time range is larger than N days` rather than truncating it. The cap is a property of the endpoint **and the grain**, so `period` decides it — and an open-ended request is measured from the cursor to today, which makes this a daily-load concern and not only a backfill one. Without this, a pipeline that missed more days than its cap allows would fail every night afterwards, wider each time, and could not recover on its own.

So each resource splits its own requests: every request carries an explicit end (`toDate`/`toTime`), and a span wider than the cap becomes several requests, oldest first and contiguous — nothing skipped between them, and nothing asked for twice. You see one resource and one stream — `nextToken` pagination still runs per request, and the cursor advances as rows arrive, so a run interrupted part-way resumes from the last row loaded rather than starting over.

| Resource | `period` | Widest window |
|---|---|---|
| `environmental` | `15min` | 7 days |
| `environmental` | `h` | 31 days |
| `environmental` | `D`, unset | 366 days |
| `behaviour_swim_speed` | `h` | 31 days |
| `behaviour_swim_speed` | `D`, unset | 366 days |
| every other windowed resource | — | 366 days |

Nothing here has to be read to use the package. The caps are also data — `MAX_WINDOW_DAYS`, keyed by `(resource, period)`, with `None` as the period for the resources that do not take one — for a caller sizing chunks of its own, or checking a `--chunk-days` before making a request:

```python
from dlt_source_aquabyte import MAX_WINDOW_DAYS

MAX_WINDOW_DAYS[("environmental", "15min")]   # 7
```

The numbers are measured, not documented by the API ([how, and when](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing)). The arithmetic does not depend on them, so a cap that moves is a one-line change to that table.

One exception, and it is the `params` rule rather than a special case: send `fromDate`/`fromTime` or `toDate`/`toTime` through `params` and you own the window — it goes out as one request, unsplit.

## What the source does not expose

**`nextToken`**, on the six endpoints documenting it — pagination mechanics owned by dlt's `JSONResponseCursorPaginator`, and exposing it would let a caller break their own pagination. The other four read endpoints (`/sites`, `/sites/{siteId}`, `/environmental/latest`, `/biomass/harvestReport`) return none, so their resources read a single page rather than hoping a cursor paginator terminates.

**The paginator has been verified live.** On 2026-08-20, a 15-minute `environmental` window returned over 30,000 records across four pages, each landing near the ~9,700–9,900-record cap, and `biomass`, `lice_count` and `welfare_scores` each paged once in the same run. Every page arrived exactly once — no duplicate primary keys turned up across any of the merged results.

**The eight `/pens/{penId}/…` path variants**, marked `deprecated: true` — the v3.0 shape of the same data, replaced in v3.1 by `?penId=`. None accepts `nextToken`, so a result set past the record cap cannot be paged through, and `penId=all` fetches every pen in one request. Bind `pen_id` to read a single pen.

**`POST /superiorRate`** — marked "(Experimental API) … subject to change", and a POST computation rather than a read endpoint. Worth revisiting once it leaves preview.

Rate limit and result cap are in `specs/openapi.json`. The package does not throttle; each resource makes one request per page, for every pen at once.

## Logging

The package emits no log records of its own — it has nothing to say that dlt does not already log, and on failure it raises. There is no package logger to attach a handler to.

dlt logs, on the logger named `dlt` at INFO, the two lines an operator needs to verify a catch-up run or a backfill: the window each resource bound, and every request made. Both are off by default, because dlt's own level is `WARNING`.

Three `[runtime]` settings cover routing, and they are dlt's, not ours:

| Setting | What it buys |
|---|---|
| `log_level` | `"INFO"` turns both lines on |
| `log_format` | `"JSON"` for a collector to parse, or your own `{}`-style format string |
| `sentry_dsn` | logged errors and unhandled exceptions go to Sentry, once `sentry-sdk` is installed |

Each has an env var too (`RUNTIME__LOG_LEVEL` and so on). A service that ships records itself hands you a handler: attach it to the `dlt` logger before the run and dlt uses it. dlt documents all of this under [running in production](https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format), which is worth reading once — there is nothing package-specific to add.

## Column types

Each resource declares column hints for its scalar fields, typed per [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md). They buy one thing: a column keeps its type when the first page happens to be all nulls, or the field is missing entirely.

Everything else is dlt's own default. A field the API adds after this release lands as a new column rather than failing the load, and a nullable field it stops sending is absent rather than fatal — `tests/test_schema_leniency.py` holds both to that. Dates and timestamps land as text, exactly as the API sends them; parsing them is a transform on your side.
