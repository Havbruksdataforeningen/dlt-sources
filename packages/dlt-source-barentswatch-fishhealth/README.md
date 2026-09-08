# dlt-source-barentswatch-fishhealth

A [dlt](https://dlthub.com/) source for the [BarentsWatch Fish Health API](https://developer.barentswatch.no/docs/fishhealth): the weekly report per aquaculture locality — lice counts, lice treatments, diseases, escapes and the licences behind the locality, as reported to the Norwegian Food Safety Authority — into any dlt destination. In detail for the localities you name, or as a summary of every locality in a production area, under one company, or along the whole coast.

**Records land as the API returns them** — nothing renamed, nothing dropped, no invented child tables. Column names are the API's own, in dlt's usual snake_case. Reshaping belongs in your transform layer, where you can change it without waiting for a release.

The package handles auth, token refresh, ISO-week arithmetic and the API's "no report" answer. Its only dependency is dlt.

## How to start

```bash
uv add dlt-source-barentswatch-fishhealth "dlt[duckdb]"   # any dlt destination works; DuckDB is the one below
```

Then one file in a `.dlt/` directory beside your script, `.dlt/secrets.toml`:

```toml
[sources.barentswatch_fishhealth]
client_id = "your-client-id-here"
client_secret = "your-client-secret-here"
```

The two values are an OAuth2 client, registered under "Min side" at <https://www.barentswatch.no/minside/> ([how](https://developer.barentswatch.no/docs/appreg)). The source exchanges them for a token and refreshes it itself; nothing else needs configuring, because the API has one server and one token endpoint, both fixed in the package.

Optionally `.dlt/config.toml`, to load some localities rather than all of them:

```toml
[sources.barentswatch_fishhealth.localities_with_salmonoids]
locality_nos = [11340, 45072]
```

Then three steps for your own localities, one example each, and a fourth for comparing them against everyone else's. That is everything needed to get running, a page of code each.

1. **Discover** — [`discover_localities.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/discover_localities.py). One request, the `localities_with_salmonoids` resource alone: the API's list of every locality with a salmonoid licence, about 2 000, printed with number and name. Find yours by name and put their numbers in the config file above, or bind them in code as the next two examples do.
2. **Backfill** — [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/backfill.py). Every week from 2012 to now for the localities you chose, run once. Re-running it is safe: `locality_week` merges on locality, year and week.
3. **Weekly load** — [`weekly_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/weekly_load.py). The last four complete weeks for the same localities, on a timer from then on. It re-requests weeks it already has because reports arrive after the week ends ([why four](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#the-weekly-load-looks-back)).
4. **Compare** — [`production_areas.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/production_areas.py). The weekly summary of every locality in production areas 7 and 8, the last four complete weeks, on the same timer. One request per area per week, however many localities the area holds, so it is the load for monitoring your localities against their neighbours; the three steps above stay the load for your own localities in detail ([which to use for what](#what-it-loads)). It is a `POST` that only reads: the filter travels as a JSON body, and nothing is stored.

From a checkout, run one with `python examples/<name>.py`.

**Know the cost before step 2.** The detailed weekly endpoint answers one locality in one ISO week per request, and BarentsWatch asks that batch requests are made one at a time — so the source makes them that way, and the cost of a load is localities × weeks, at about 0.1 s each:

| Load | Requests | Takes |
|---|---|---|
| A few localities back to 2012 (about 770 weeks each) | a few thousand | minutes |
| Every salmonoid locality, four weeks | about 8 000 | a quarter of an hour |
| Every salmonoid locality back to 2012 | about 1.5 million | days |
| Production areas 7 and 8 summarised, four weeks | 8 | seconds |
| Production areas 7 and 8 summarised back to 2020 | about 700 | a minute |

Weeks before a locality existed answer 400 in about 0.07 s and are skipped, so a backfill from 2012 is not slower for a locality that opened in 2019 — but it is not free either.

The summary endpoint answers every locality matching the filter in one request per week, also in about 0.1 s, so its cost is filter values × weeks and does not grow with the number of localities: the whole coast is one request per week, 1 770 rows. The detailed endpoint for the same two areas and years would be about 316 localities × 350 weeks, 110 000 requests, hours.

## What it loads

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `localities` | `GET /v1/geodata/fishhealth/localities` | replace | — |
| `localities_with_salmonoids` | `GET /v1/geodata/fishhealth/localitieswithsalmonoids` | replace | — |
| `locality_week` | `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` | merge | `localityNo`, `year`, `week` |
| `locality_week_summary` | `POST /v2/geodata/fishhealth/locality/{year}/{week}` | merge | `localityNo`, `year`, `week` |

`locality_week` is a dlt transformer over `localities_with_salmonoids`: for each locality row it requests every week in the range you bind, and writes one row per week the API has a report for. `locality_week_summary` stands alone: for each week in its range it sends the filter you bind, and writes one row per locality the API matched. Five defaults worth knowing before your first query:

- **Two locality lists, named after their endpoints.** `localities_with_salmonoids` is the list lice reporting applies to — number and name, about 2 000 — and the one `locality_week` iterates over. `localities` is the full aquaculture register list, about 2 700, with `municipalityNo`, `municipality` and `aquaCultureRegistryVersion` besides; load it to join a municipality onto the weekly tables. It is not fetched unless you select it, and no argument narrows it — [what each holds](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#one-row-per-locality-week).
- **Two weekly tables, one key.** A summary row has the same `liceReport` as the detailed row for that locality-week, `diseases` and `liceTreatments` as names only (`["PANKREASSYKDOM"]`, `["IKKE_MEDIKAMENTELL"]`) where the detailed row has full case and treatment records, and none of the register, zone or escape fields. Load the summary to monitor lice across many localities and areas — one request per week per production area, per organisation, or for the whole coast. Load the detail for the disease cases and treatment records, the aquaculture-register entry and the control and PD zones. Both merge on `localityNo`, `year`, `week`, so they join row for row — [the field-by-field comparison](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#the-summary-and-the-detail).
- **The key is injected, not returned.** Neither weekly response says which week it is for, and the detailed one does not repeat the locality either, so the source adds `localityNo`, `year` and `week` from the request (the summary copies `localityNo` from each row's `locality.no`). They land as `locality_no`, `year`, `week` — [where the rest of the row comes from](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#one-row-per-locality-week).
- **Nested objects land as one JSON column each** — `lice_report`, `lice_treatments`, `aqua_culture_register`, `geometry` and so on — [why, and how to override it](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#nesting).
- **A week with no report is skipped, not an error.** The API answers HTTP 400 for it, and for an unknown locality number, and the source cannot tell the two apart — [what that means for `locality_nos`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#http-400-means-no-report).

## Configuring a resource

Five arguments across the four resources. The three `GET` endpoints take nothing but their path; the summary's `POST` takes a filter body, and its three extra arguments build it.

```python
source = barentswatch_fishhealth_source()
source.localities_with_salmonoids.bind(locality_nos=[11340, 45072])
source.locality_week.bind(week_range=last_n_weeks(4))
source.locality_week_summary.bind(week_range=last_n_weeks(4), production_areas=[7, 8])
pipeline.run(source)
```

| Argument | Resource | What to know |
|---|---|---|
| `locality_nos` | `localities_with_salmonoids` | A list of locality numbers to keep; `None` (the default) keeps every salmonoid locality. Bind it or set it in config under `[sources.barentswatch_fishhealth.localities_with_salmonoids]`. A number that is not a salmonoid locality is warned about and left out; an empty list, or a list with no match, raises. |
| `week_range` | `locality_week`, `locality_week_summary` | A `WeekRange(start_year, start_week, end_year, end_week)`, inclusive at both ends. **Required** on both — a run without one raises an error naming the resource. Bind it in code; it has no config form. |
| `production_areas` | `locality_week_summary` | A list of production-area ids, 1–13. One request per area per week, and the id is added to each row as `productionArea`, because the row does not say which area it came from. `None` (the default) leaves the area unfiltered; an empty list raises. Bind it, or set it in config under `[sources.barentswatch_fishhealth.locality_week_summary]`. |
| `organizations` | `locality_week_summary` | A list of nine-digit organisation numbers — `organizationNo` in the detailed row's `aquaCultureRegister.organizations`. One request per organisation per week, and each combines with each production area (AND): `production_areas=[7, 8]` with `organizations=["921668236"]` is that company's localities in 7, then in 8. Not added to the row, because a locality can belong to several organisations. Config form as above. |
| `filters` | `locality_week_summary` | A dict of the other ~30 body fields the spec lists under `LocalityReportQueryV2` — `onlyWithSalmonoidLicense`, `allWithReport`, `aboveLiceThreshold`, `insideIlaControlArea`, `countyMunicipality`, `withinPolygon`, `diseases` and so on — sent as given. Merged into the body last, so it wins over the two arguments above. With none of the three bound the body is `{}`, and every locality on the coast is a row. |

Four helpers build a `week_range`, all importable from the package:

| Helper | Gives you |
|---|---|
| `last_n_weeks(n)` | The `n` complete ISO weeks before the current one, decided on the Norwegian date. The weekly load's range. |
| `WeekRange(FIRST_YEAR, 1, *current_iso_week())` | Everything the API can have. `FIRST_YEAR` is 2012, the first year the API answers for. The backfill's range. |
| `current_iso_week()` | The `(year, week)` of today, for a range of your own that includes the current week. |
| `weeks_in_year(year)` | 52 or 53, for building ranges by hand. |

## Compatibility

| `dlt-source-barentswatch-fishhealth` | Fish Health API |
|---|---|
| 0.1.x | `v1` spec — `GET /v1/geodata/fishhealth/localities`, `GET /v1/geodata/fishhealth/localitieswithsalmonoids`, `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` and `POST /v2/geodata/fishhealth/locality/{year}/{week}` |

The two numbers are unrelated: the package version is ordinary [SemVer](https://semver.org/), and `v1` is what the API's own OpenAPI document calls itself while its paths carry `/v1/` and `/v2/` prefixes of their own. Built against that document's [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/specs/README.md) and run live against the API, last on 2026-09-08. A later backwards-compatible API version should work, but run the suite first.

## Read next

- [**API quirks worth knowing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/specs/README.md#api-quirks-worth-knowing) — where the live API departs from its OpenAPI document, and which identifiers to join on. The 400-for-everything answer changes what a correct load looks like, so read it before your first one.
- [**Reference**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md) — the locality-week row, the summary against the detail, nesting, weeks and the lookback, backfilling, what the source does not expose, logging and column types.
- [**Changelog**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/CHANGELOG.md) and [**contributing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/LICENSE). `specs/openapi.json` is BarentsWatch's own OpenAPI document, included as the spec this package is built against. It is their material, and the licence does not extend to it. The data the API serves is published under [NLOD](https://data.norge.no/nlod), as the document's `info.license` states.
