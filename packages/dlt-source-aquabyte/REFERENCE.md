# Reference

The detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/README.md), for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

Most of it is shorter as code: [`discover_history.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/discover_history.py), [`quickstart.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/quickstart.py) and [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py).

## The site registry is versioned

`/sites` reports what exists *today*, and a pen leaves it as soon as it is emptied, possibly after years of production. Replacing the table each run would drop that history, so `sites` loads with dlt's [`scd2` strategy](https://dlthub.com/docs/general-usage/merge-loading#scd2-strategy): **a row is never deleted**, only retired by stamping `_dlt_valid_to`.

```sql
SELECT * FROM sites WHERE _dlt_valid_to IS NULL;                     -- current
SELECT * FROM sites WHERE id = 'site-001' ORDER BY _dlt_valid_from;  -- one site's history
```

**What makes a new version:** any field changing, the nested `pens` list included. So renaming a pen, or a pen going inactive, versions its site. The current row therefore always shows the pens the API last reported. At a member company's site count, that is a handful of rows.

**Why `merge_key="id"`:** it scopes retirement to the ids a load actually carried, which is what makes `bind(site_id=...)` safe. The trade-off is that a site missing from a *full* response is not retired either, and stays current indefinitely. Retire-on-absence and safe partial loads are the same switch, and this source picks the one that cannot lose data.

⚠️ To choose the other side, drop the merge key on a pipeline's **first** load only. dlt stores `merge_key` on the column and never removes it, so `apply_hints(merge_key=())` against an existing table is silently ignored (verified against dlt 1.30).

Background: [SCD2 and incremental loading](https://dlthub.com/blog/scd2-and-incremental-loading).

### Pens live on the site record

There is no `pens` table — the API serves no pens endpoint. Each site's pens land as they arrive, one JSON array in the `pens` column, versioning with the site. It carries every field the API declares: `id`, `name`, `penCode`, `isActive` and `external_id`. Which to join on is in [Identifiers](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#identifiers).

Unnesting is your transform layer's job. Current pens are the `pens` of rows where `_dlt_valid_to IS NULL`; pen history is the `pens` of every version, each carrying that version's validity interval. For a flat table instead, set `source.sites.max_table_nesting = 1` and a `sites__pens` table appears — see [Nesting](#nesting).

Two rules to build on. The first is a guarantee, the second a decision left to you:

- **A pen leaving a site retires the version that listed it.** That version's `_dlt_valid_to` is the date the pen stopped being reported, and the pen's full record stays readable on that row. The pen's history survives the pen.
- **A site leaving `/sites` is not retired at all.** It keeps `_dlt_valid_to IS NULL` and its last pens snapshot. Whether that counts as gone is your call: record a last-seen timestamp per load on your side and read it from there.

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position rather than an extra opinion: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and it would make the destination shape depend on which fields happened to be nested in the first page loaded.

It is a default, not a lock:

```python
source = aquabyte_source()
source.max_table_nesting = 2  # every resource
source.sites.max_table_nesting = 1  # or just one — gives you a sites__pens table
```

Nothing outranks that setting. The source declares column hints for scalar fields only, so no hint names a nested field.

**`welfare_scores` is not unpivoted.** The API returns one record per pen and date with every category nested inside, and that is what lands. A category the API adds later arrives untouched, because nothing here enumerates categories. Flattening is a transform on your side — `LATERAL`/`UNNEST` in your warehouse, or dlt's `add_map` before load.

## Windows, cursors and backfilling

Runnable version of this section: [`quickstart.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/quickstart.py) for the daily load, [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/examples/backfill.py) for a window.

The incremental cursor is the only window mechanism, and its value is **always sent** as `fromDate`/`fromTime`:

- **A daily load binds nothing.** The first run starts at `initial_date`/`initial_time`, every later one resumes from the stored cursor. A request that would carry no start fails with an error naming what to set, rather than silently inheriting the API's default window.
- **A backfill binds the window** on the resource's `incremental_*` argument: `dlt.sources.incremental(initial_value=..., end_value=...)`. dlt runs that with transient state, so it fetches exactly that window and the stored cursor is neither consulted nor advanced. `end_value` is sent as `toDate`/`toTime`; with none bound, the request still carries an end — now.

Windows overlap by design and dlt drops what it already has. A daily load re-asks for the cursor's own value, and a date backfill asks one day past `end_value` because dlt's end is exclusive while `toDate` is inclusive. Neither is worth correcting for.

⚠️ **The cursor is per resource, not per pen.** One cursor covers every pen the resource loads (`penId=all` included), advancing to the newest row *any* pen reported. Data arriving late — a pen whose camera was offline, a re-issued `harvest_report` for an old slaughter — falls behind it and is not requested again. When that matters, periodically re-load a recent window the backfill way; merge dispositions make that idempotent.

### Windows are split to fit the window cap

The API refuses a window wider than the window cap rather than trimming it, and measures a request that sends no end to the start of the current UTC day. Without splitting, a daily load that fell further behind than the cap allows would fail, and keep failing.

So each resource sends an explicit end on every request, and splits a wider timespan into several, oldest first and contiguous. You still see one resource and one stream.

| Resource | `period` | Widest window |
|---|---|---|
| `environmental` | `15min` | 7 days |
| `environmental` | `h` | 31 days |
| `behaviour_swim_speed` | `h` | 31 days |
| everything else | — | 366 days |

You need none of this to use the package. The same window caps are importable, for sizing chunks of your own:

```python
from dlt_source_aquabyte import MAX_WINDOW_DAYS

MAX_WINDOW_DAYS[("environmental", "15min")]  # 7
```

- The key is `(resource, period)`, with `None` for the resources that take no `period`.
- The numbers are [measured, not documented by the API](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md#api-quirks-worth-knowing), so treat them as observations. The table is writable for that reason: if a window cap moves, assign the new value before your run instead of waiting for a release.
- Send a window param through `params` and you own the window — it goes out as one request, unsplit.

## What the source does not expose

**`nextToken`**, on the six endpoints documenting it. Pagination is dlt's `JSONResponseCursorPaginator`, and exposing the token would let a caller break their own pagination. The other four read endpoints (`/sites`, `/sites/{siteId}`, `/environmental/latest`, `/biomass/harvestReport`) return none, so those resources read a single page rather than hoping a cursor paginator terminates.

Verified live on 2026-08-20: a 15-minute `environmental` window returned over 30,000 records across four pages, each near the ~9,700–9,900-record cap, and `biomass`, `lice_count` and `welfare_scores` each paged once. Every page arrived exactly once.

**The eight `/pens/{penId}/…` path variants**, marked `deprecated: true` — the v3.0 shape of the same data, replaced in v3.1 by `?penId=`. None accepts `nextToken`, so a result set past the record cap cannot be paged through. Bind `pen_id` to read a single pen.

**`POST /superiorRate`** — marked experimental and subject to change, and a POST computation rather than a read endpoint. Worth revisiting once it leaves preview.

Rate limit and record cap are in `specs/openapi.json`. The package does not throttle; each resource makes one request per page, for every pen at once.

## Logging

The package logs one thing of its own: a warning on `dlt_source_aquabyte.windows` when it cannot read a cursor value as a date or a time, and so sends the window unsplit. Worth hearing, because that request may be refused and dlt hides the reason. Everything else it does, it raises.

dlt logs two lines an operator needs to verify a catch-up run or a backfill — the window each resource bound, and every request made — on the logger named `dlt` at INFO. Both are off by default, dlt's own level being `WARNING`.

Four dlt `[runtime]` settings cover routing, each with an env var (`RUNTIME__LOG_LEVEL` and so on):

| Setting | What it buys |
|---|---|
| `log_level` | `"INFO"` turns both lines on |
| `log_format` | `"JSON"` for a collector to parse, or your own `{}`-style format string |
| `sentry_dsn` | logged errors and unhandled exceptions go to Sentry, once `sentry-sdk` is installed |
| `http_show_error_body` | `true` shows the API's own `detail` on a `4xx` — the only thing that tells an over-wide window from a bad parameter |

A service that ships records itself hands you a handler: attach it to the `dlt` logger before the run, and to `dlt_source_aquabyte` for this package's warning. The rest is in dlt's [running in production](https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format) guide.

## Column types

Each resource declares column hints for its scalar fields, typed per [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-aquabyte/specs/README.md). They buy one thing: a column keeps its type when the first page is all nulls, or the field is missing entirely.

Everything else is dlt's default. A field the API adds after this release lands as a new column rather than failing the load, and a nullable field it stops sending is absent rather than fatal — `tests/test_schema_leniency.py` holds both to that. Dates and timestamps land as text, exactly as the API sends them; parsing is a transform on your side.
