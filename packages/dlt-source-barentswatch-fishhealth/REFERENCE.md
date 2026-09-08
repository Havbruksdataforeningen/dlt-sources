# Reference

The detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/README.md), for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

Most of it is shorter as code: [`discover_localities.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/discover_localities.py), [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/backfill.py), [`weekly_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/weekly_load.py) and [`production_areas.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/production_areas.py).

## One row per locality-week

The detailed weekly endpoint answers one locality in one ISO week per request, with one `LocalityReportV2` object: who the locality is (`locality`, `geometry`, `municipality`, `productionArea`, `aquaCultureRegister`), what it is subject to this week (`controlAreas`, `exportRestrictionAreas`, `pdZoneId`, `diseases`, `farmedFishEscapes`) and what it reported (`liceReport`, `liceTreatments`). The source yields that object unchanged, plus the three values it asked with — `localityNo`, `year`, `week` — because the response does not repeat them and nothing else in it identifies the week. Those three are the merge key, so a week loaded twice lands once.

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

**The `localities_with_salmonoids` table is a snapshot of the list you loaded.** `localities_with_salmonoids` loads with `replace`, so each run leaves exactly the rows it fetched: every salmonoid locality with no `locality_nos` bound, or only the ones you named. It is the API's discovery list — `localityNo` and `name`, nothing more — and the input `locality_week` iterates over. Selecting `locality_week` alone with `with_resources("locality_week")` still fetches the list, because the transformer needs it, but writes no `localities_with_salmonoids` table. `locality_week_summary` does not read it at all: the filter body decides which localities it gets.

**The `localities` table is the register list, and nothing iterates over it.** `GET /v1/geodata/fishhealth/localities` is every aquaculture locality the API knows, salmonoid or not — 2 706 rows against the salmonoid list's 2 002 on 2026-09-08 — with `municipalityNo`, `municipality` and `aquaCultureRegistryVersion` besides number and name. It also loads with `replace`, takes no argument, and is fetched only when selected. The API has two locality lists with similar names, and the source exposes both under their own names so you can tell them apart; `locality_week` iterates over the salmonoid list because lice reporting applies to those, and this one is for joining a municipality onto the weekly tables.

## The summary and the detail

`POST /v2/geodata/fishhealth/locality/{year}/{week}` is a read that happens to be a `POST`: the filter is a JSON body because it is too rich for a query string, and nothing is stored. It answers one week per request with an array, one `LocalityWeekReportV2` per locality the filter matched — every locality on the coast for an empty body, 1 770 rows on 2025-W35 in 0.1 s. The source yields each row plus `localityNo` (copied from `locality.no`), `year` and `week`, the same merge key as `locality_week`, so the two tables join row for row.

The same locality-week, field by field (verified live on 2026-09-08):

| Field | `locality_week` (detail) | `locality_week_summary` |
|---|---|---|
| `locality`, `geometry`, `municipality` | Same | Same |
| `liceReport` | Full | Identical |
| `diseases` | Cases: name, sub-type, status, dates of suspicion, diagnosis, emptying and closure | Names only, e.g. `["PANKREASSYKDOM"]` — verified live on a locality with an open PD case |
| `liceTreatments` | Full records: kind, substances, number of cages, done before the count | Category names only, e.g. `["IKKE_MEDIKAMENTELL"]` |
| `aquaCultureRegister`, `pdZoneId`, `controlAreas`, `exportRestrictionAreas`, `farmedFishEscapes` | Present | Absent |
| `productionArea` | The API's `{id, name, color}` | Absent from the row; the source adds the integer it asked for, when it asked for one |
| `localityWeekId`, `isFiltered`, `hasSalmonoidLicense`, `isSlaughterHoldingCage` | Absent | Present |

Which to load follows from the table:

- **The summary, to monitor lice across many localities and areas.** Its cost is filter values × weeks, whatever the areas hold: two production areas back to 2020 is about 700 requests, a minute. The detailed endpoint for the same localities is about 110 000 requests, hours.
- **The detail, for what the summary lacks.** The treatment records, the aquaculture-register entry and the control and PD zones exist only in `locality_week`. Load it for your own localities, and join the summary on the shared key when you need both.

**The filters fan out and combine with AND.** The API takes one `productionArea` and one `organization` per request — a list answers 400, a comma-separated string matches nothing — so each of the source's two lists becomes one request per value, and the two lists become their product: `production_areas=[7, 8]` with `organizations=["921668236"]` is that company's localities in area 7, then in area 8, two requests per week. `filters` is the escape hatch for the other ~30 body fields; it is merged into the body last, so a `productionArea` in it overrides the named argument.

**`productionArea` is injected, `organization` is not.** A summary row does not say which area it came from, and a comparison across areas needs to know, so when the request was filtered by area the source writes the requested integer into the row as `productionArea`. It lands as `production_area` — the same column name as the detailed table, holding an integer where the detailed table holds the API's object. An organisation is not written back: a locality can belong to several organisations, so the request's filter value would be one of them, not the answer. The owning organisations are in the detailed row's `aquaCultureRegister.organizations`, as `organizationNo`.

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

**There is no cursor.** Neither weekly endpoint takes a window: both are addressed by year and week, so a load is a set of weeks the caller chooses, and nothing is stored between runs. The `week_range` you bind decides every request, which makes a run reproducible and a re-run idempotent — both weekly resources merge on `localityNo`, `year`, `week`, so an overlap costs requests and nothing else. A `WeekRange` is inclusive at both ends and `validate()`d before the first request: a week that does not exist in its year, a year before `FIRST_YEAR` or a range that runs backwards raises before anything is fetched.

### The weekly load looks back

A locality's report for a week arrives after the week ends, and the API is updated nightly from what has been reported to Mattilsynet — so the newest week is incomplete on the day it becomes available, and a locality that reported late is not retroactively pushed to you. The scheduled load therefore re-requests a lookback of several complete weeks every run, `last_n_weeks(4)` in the example, and lets merge absorb the overlap. Four is a starting point, not a measurement: widen it if you find rows changing later than that.

`last_n_weeks(n)` gives the `n` complete ISO weeks *before* the current one, decided on the Europe/Oslo date rather than UTC, because that is where the reports are filed. The current week is left out because it is still being reported. A load that wants it anyway builds the range itself: `WeekRange(*last_n_weeks(n)[:2], *current_iso_week())`.

### Backfilling

A backfill is the same resource with a wider range — `WeekRange(FIRST_YEAR, 1, *current_iso_week())` is everything the API can have — and it costs localities × weeks requests, made serially. The README's [cost table](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/README.md#how-to-start) has the arithmetic. Three things that follow from it:

- **Backfill a few localities, not all of them, unless you mean to.** Every salmonoid locality back to 2012 is about 1.5 million requests. Bind `locality_nos`.
- **Chunk a large backfill by year** if your scheduler has a run-time limit. One `WeekRange` per year, each its own `pipeline.run`; merge makes the boundary weeks free to overlap.
- **Weeks before a locality existed cost a request each**, answered 400 in about 0.07 s. A locality that opened in 2019 still asks for 2012–2018, and skips them. If you know the opening year, start the range there.
- **A summary backfill is cheap.** Production areas 7 and 8 from 2020 to now is 2 × 350 ≈ 700 requests, about a minute, against about 110 000 for the same localities in detail. If the question is lice across an area, backfill `locality_week_summary` and keep `locality_week` for your own localities — [The summary and the detail](#the-summary-and-the-detail).

The token is refreshed by the source, so a backfill longer than the token's 3 600 s does not fail mid-run.

## HTTP 400 means "no report"

Both weekly endpoints answer **400** — a ProblemDetails body such as `{"title": "Locality week for 11340 2030-W1 was not found.", "status": 400}` — for every request they have no data for: a week the locality did not report, a week before it existed, a future week, a year before 2012, a locality number the detailed endpoint does not know. All of them look the same. So the source treats 400 as "no report" and skips the week, in both resources, and raises on every other non-200. The alternative, raising on 400, would fail every backfill on its first pre-opening week.

The summary endpoint also answers 400 for a body it rejects — a list where it wants one value, such as `{"productionArea": [7, 8]}` through `filters`. That is skipped like any other 400, one DEBUG line per week, so a malformed `filters` looks like a range with no reports. Check the DEBUG lines, which carry the body, before concluding the weeks are empty.

That is also why `locality_nos` is filtered against the discovered list rather than sent straight to the weekly endpoint. A mistyped number would otherwise cost one silent 400 per week — a whole backfill of nothing — with no log line to show for it. Instead the `localities_with_salmonoids` resource fetches the list, keeps the numbers you named that are on it, warns about the ones that are not, and raises if none are left.

Two consequences for reading the data:

- **A missing row means "the API had nothing", not "the locality was fallow."** Fallow weeks are rows with `isFallow: true` — see [One row per locality-week](#one-row-per-locality-week).
- **A locality that stops reporting stops producing rows,** and nothing tells you which of the reasons above applies. In `locality_week` the INFO log line per locality carries the count of skipped weeks, which is the one signal there is — [Logging](#logging). In `locality_week_summary` a locality that stops reporting is still a row, with `liceReport.hasReported: false`, as long as the filter matches it; nothing is counted per locality there.

## What the source does not expose

**The summary's other body fields, as arguments.** `LocalityReportQueryV2` lists about 35 optional filters; the source names two of them, `productionArea` and `organization`, because those are the ones that fan out. The rest — `onlyWithSalmonoidLicense`, `allWithReport`, `aboveLiceThreshold`, `insideIlaControlArea`, `countyMunicipality`, `withinPolygon`, `diseases` and so on — reach the API through `filters`, sent as given, so they need no release to use and none to fix.

**The other ~120 paths in the spec** — lice per production area, disease and control-area detail, sea temperature, the aquaculture register itself, and so on. The spec is the Fish Health API in full; this package reads the four paths the weekly reports need, and stays partial on purpose: it covers what our own member companies load, and grows when one of them needs the next endpoint.

**Throttling and retries beyond dlt's own.** BarentsWatch asks that batch requests are made one at a time, and the source does exactly that: one request, then the next. It adds no delay between them. dlt's [requests helper](https://dlthub.com/docs/general-usage/http/requests) retries connection errors, `429` and `5xx` on its defaults.

## Logging

The package logs three things of its own, on the logger `dlt_source_barentswatch_fishhealth.barentswatch_fishhealth`:

| Level | When |
|---|---|
| WARNING | `localities_with_salmonoids`: a number in `locality_nos` is not a salmonoid locality, and is left out |
| INFO | `locality_week`: a locality is done, and some of its weeks answered 400 — with the count of skipped weeks out of the range |
| DEBUG | `locality_week`: one week answered 400 and was skipped. `locality_week_summary`: one week answered 400 for one filter body, and was skipped — the line carries the body |

Everything else the package does, it raises. The INFO line is the one to watch in a weekly load: a locality skipping all four weeks of the lookback is either fallow-and-unreported or gone, and the API does not say which. `locality_week_summary` has no INFO line, because there is nothing per locality to count: a matched locality is a row whether it reported or not.

dlt logs each request on the logger named `dlt` at INFO, off by default, dlt's own level being `WARNING`. Four dlt `[runtime]` settings cover routing, each with an env var (`RUNTIME__LOG_LEVEL` and so on):

| Setting | What it buys |
|---|---|
| `log_level` | `"INFO"` turns on dlt's request lines and this package's per-locality count; `"DEBUG"` adds the per-week skips |
| `log_format` | `"JSON"` for a collector to parse, or your own `{}`-style format string |
| `sentry_dsn` | logged errors and unhandled exceptions go to Sentry, once `sentry-sdk` is installed |
| `http_show_error_body` | `true` shows the API's own `title` on a non-200 — a `401` from a bad client, or a `400` the source would have skipped if you are probing by hand |

A service that ships records itself hands you a handler: attach it to the `dlt` logger before the run, and to `dlt_source_barentswatch_fishhealth` for this package's lines. The rest is in dlt's [running in production](https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format) guide.

## Column types

The source declares no column hints. Every column is typed by dlt from the data: `locality_no`, `year` and `week` are integers because the source injects them as integers, and every nested object or list is a JSON column because of [nesting](#nesting). Two columns share a name across the weekly tables and differ in shape: `lice_treatments` is an object in `locality_week` and a JSON array of category names in `locality_week_summary`, and `production_area` is the API's object in the detail and the injected integer in the summary. The summary's columns, after snake_case: `locality_no, year, week, production_area, locality_week_id, is_filtered, locality, geometry, municipality, has_salmonoid_license, is_slaughter_holding_cage, diseases, lice_report, lice_treatments`. The two lists are flat: `localities_with_salmonoids` is `locality_no, name`, and `localities` is `locality_no, name, municipality_no, municipality, aqua_culture_registry_version`. A field the API adds after this release lands as a new column rather than failing the load, and a field it stops sending is absent rather than fatal. Dates and timestamps inside the JSON columns stay text, exactly as the API sends them; parsing is a transform on your side.
