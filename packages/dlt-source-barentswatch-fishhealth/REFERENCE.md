# Reference

The detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/README.md), for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

Most of it is shorter as code: [`discover_localities.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/discover_localities.py), [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/backfill.py) and [`weekly_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/weekly_load.py).

## One row per locality-week

The weekly endpoint answers one locality in one ISO week per request, with one `LocalityReportV2` object: who the locality is (`locality`, `geometry`, `municipality`, `productionArea`, `aquaCultureRegister`), what it is subject to this week (`controlAreas`, `exportRestrictionAreas`, `pdZoneId`, `diseases`, `farmedFishEscapes`) and what it reported (`liceReport`, `liceTreatments`). The source yields that object unchanged, plus the three values it asked with — `localityNo`, `year`, `week` — because the response does not repeat them and nothing else in it identifies the week. Those three are the merge key, so a week loaded twice lands once.

The columns, after dlt's snake_case (verified in DuckDB on 2026-09-08):

| Column | Holds |
|---|---|
| `locality_no`, `year`, `week` | The merge key, from the request path |
| `locality` | `{no, name, isOnLand}` |
| `geometry` | The locality's position, a GeoJSON Point |
| `municipality`, `production_area` | Where the locality is, by municipality and by [production area](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/CONTEXT.md#places) |
| `aqua_culture_register` | The locality's entry in Fiskeridirektoratet's register: licences, licensees, capacity, species, organizations |
| `control_areas`, `export_restriction_areas`, `pd_zone_id` | The disease-control regimes the locality falls under this week |
| `diseases`, `farmed_fish_escapes` | Disease cases and escape incidents at the locality |
| `lice_report` | `hasReported`, `isFallow`, the four lice counts as `{average, averageOfPreviousWeek, trend}`, and `seaTemperature` |
| `lice_treatments` | The treatments reported, one list or object per kind, plus `daysSinceLastChitinSynthesisInhibitorTreatment` |

**A fallow locality is a row, not a gap.** The API answers a fallow week with 200, `isFallow: true`, `hasReported: false` and null averages, and the source lands that row. `lice_report ->> 'hasReported'` is the condition that separates a reported week from a fallow one; a week the API has nothing for at all answers 400 and is [skipped](#http-400-means-no-report).

**The `locality` table is a snapshot of the list you loaded.** `locality` loads with `replace`, so each run leaves exactly the rows it fetched: every salmonoid locality with no `locality_nos` bound, or only the ones you named. It is the API's discovery list — `localityNo` and `name`, nothing more — and the input `locality_week` iterates over. Selecting `locality_week` alone with `with_resources("locality_week")` still fetches the list, because the transformer needs it, but writes no `locality` table.

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position rather than an extra opinion: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API, and a weekly report nests four levels deep — `liceTreatments.medicinalTreatments[].type`, `aquaCultureRegister.licenses[].localities[]` — so dlt's default would make a dozen tables out of one endpoint.

It is a default, not a lock:

```python
source = barentswatch_fishhealth_source()
source.max_table_nesting = 1  # one level of child tables: locality_week__diseases and the like
```

Nothing outranks that setting. The source declares no column hints, so no hint names a nested field.

Flattening `lice_report` into four averages and a trend is a transform on your side — `->>` and `LATERAL`/`UNNEST` in your warehouse, or dlt's `add_map` before load. The reports keep their nesting because a field BarentsWatch adds later then arrives untouched: nothing here enumerates treatment kinds or lice stages.

## Weeks, the lookback and backfilling

Runnable version of this section: [`weekly_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/weekly_load.py) for the scheduled load, [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/backfill.py) for the history.

**There is no cursor.** The endpoint takes no window: it is addressed by year and week, so a load is a set of weeks the caller chooses, and nothing is stored between runs. The `week_range` you bind decides every request, which makes a run reproducible and a re-run idempotent — `locality_week` merges on `localityNo`, `year`, `week`, so an overlap costs requests and nothing else. A `WeekRange` is inclusive at both ends and `validate()`d before the first request: a week that does not exist in its year, a year before `FIRST_YEAR` or a range that runs backwards raises before anything is fetched.

### The weekly load looks back

A locality's report for a week arrives after the week ends, and the API is updated nightly from what has been reported to Mattilsynet — so the newest week is incomplete on the day it becomes available, and a locality that reported late is not retroactively pushed to you. The scheduled load therefore re-requests a lookback of several complete weeks every run, `last_n_weeks(4)` in the example, and lets merge absorb the overlap. Four is a starting point, not a measurement: widen it if you find rows changing later than that.

`last_n_weeks(n)` gives the `n` complete ISO weeks *before* the current one, decided on the Europe/Oslo date rather than UTC, because that is where the reports are filed. The current week is left out because it is still being reported. A load that wants it anyway builds the range itself: `WeekRange(*last_n_weeks(n)[:2], *current_iso_week())`.

### Backfilling

A backfill is the same resource with a wider range — `WeekRange(FIRST_YEAR, 1, *current_iso_week())` is everything the API can have — and it costs localities × weeks requests, made serially. The README's [cost table](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/README.md#how-to-start) has the arithmetic. Three things that follow from it:

- **Backfill a few localities, not all of them, unless you mean to.** Every salmonoid locality back to 2012 is about 1.5 million requests. Bind `locality_nos`.
- **Chunk a large backfill by year** if your scheduler has a run-time limit. One `WeekRange` per year, each its own `pipeline.run`; merge makes the boundary weeks free to overlap.
- **Weeks before a locality existed cost a request each**, answered 400 in about 0.07 s. A locality that opened in 2019 still asks for 2012–2018, and skips them. If you know the opening year, start the range there.

The token is refreshed by the source, so a backfill longer than the token's 3 600 s does not fail mid-run.

## HTTP 400 means "no report"

The weekly endpoint answers **400** — a ProblemDetails body such as `{"title": "Locality week for 11340 2030-W1 was not found.", "status": 400}` — for every request it has no data for: a week the locality did not report, a week before it existed, a future week, a year before 2012, a locality number it does not know. All of them look the same. So the source treats 400 as "no report" and skips the week, and raises on every other non-200. The alternative, raising on 400, would fail every backfill on its first pre-opening week.

That is also why `locality_nos` is filtered against the discovered list rather than sent straight to the weekly endpoint. A mistyped number would otherwise cost one silent 400 per week — a whole backfill of nothing — with no log line to show for it. Instead the `locality` resource fetches the list, keeps the numbers you named that are on it, warns about the ones that are not, and raises if none are left.

Two consequences for reading the data:

- **A missing row means "the API had nothing", not "the locality was fallow."** Fallow weeks are rows with `isFallow: true` — see [One row per locality-week](#one-row-per-locality-week).
- **A locality that stops reporting stops producing rows,** and nothing tells you which of the reasons above applies. The INFO log line per locality carries the count of skipped weeks, which is the one signal there is — [Logging](#logging).

## What the source does not expose

**`GET /v1/geodata/fishhealth/localities`** — the full locality list, 2 706 entries against the salmonoid list's 2 002 on 2026-09-08, with `municipalityNo`, `municipality` and `aquaCultureRegistryVersion` besides number and name. Lice reporting applies to salmonoid localities, and the weekly endpoint is what this package is for, so the salmonoid list is the one that decides what to request. The extra fields are in every weekly row's `municipality` and `aqua_culture_register` anyway.

**`POST /v2/geodata/fishhealth/locality/{year}/{week}`** — a per-week summary of every locality in one request, with optional filters in the body. The obvious future resource for a national load: one request per week instead of 2 000. It returns a summary shape (`LocalityWeekReportV2`), not the detailed one, so it is a different table rather than a faster way to fill this one. Worth a resource of its own when someone needs it.

**The other ~120 paths in the spec** — lice per production area, disease and control-area detail, sea temperature, the aquaculture register itself, and so on. The spec is the Fish Health API in full; this package reads the two paths the weekly report needs.

**Throttling and retries beyond dlt's own.** BarentsWatch asks that batch requests are made one at a time, and the source does exactly that: one request, then the next. It adds no delay between them. dlt's [requests helper](https://dlthub.com/docs/general-usage/http/requests) retries connection errors, `429` and `5xx` on its defaults.

## Logging

The package logs three things of its own, on the logger `dlt_source_barentswatch_fishhealth.barentswatch_fishhealth`:

| Level | When |
|---|---|
| WARNING | A number in `locality_nos` is not a salmonoid locality, and is left out |
| INFO | A locality is done, and some of its weeks answered 400 — with the count of skipped weeks out of the range |
| DEBUG | One week answered 400 and was skipped |

Everything else the package does, it raises. The INFO line is the one to watch in a weekly load: a locality skipping all four weeks of the lookback is either fallow-and-unreported or gone, and the API does not say which.

dlt logs each request on the logger named `dlt` at INFO, off by default, dlt's own level being `WARNING`. Four dlt `[runtime]` settings cover routing, each with an env var (`RUNTIME__LOG_LEVEL` and so on):

| Setting | What it buys |
|---|---|
| `log_level` | `"INFO"` turns on dlt's request lines and this package's per-locality count; `"DEBUG"` adds the per-week skips |
| `log_format` | `"JSON"` for a collector to parse, or your own `{}`-style format string |
| `sentry_dsn` | logged errors and unhandled exceptions go to Sentry, once `sentry-sdk` is installed |
| `http_show_error_body` | `true` shows the API's own `title` on a non-200 — a `401` from a bad client, or a `400` the source would have skipped if you are probing by hand |

A service that ships records itself hands you a handler: attach it to the `dlt` logger before the run, and to `dlt_source_barentswatch_fishhealth` for this package's lines. The rest is in dlt's [running in production](https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format) guide.

## Column types

The source declares no column hints. Every column is typed by dlt from the data: `locality_no`, `year` and `week` are integers because the source injects them as integers, and every nested object or list is a JSON column because of [nesting](#nesting). A field the API adds after this release lands as a new column rather than failing the load, and a field it stops sending is absent rather than fatal. Dates and timestamps inside the JSON columns stay text, exactly as the API sends them; parsing is a transform on your side.
