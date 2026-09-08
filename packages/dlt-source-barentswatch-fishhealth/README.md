# dlt-source-barentswatch-fishhealth

A [dlt](https://dlthub.com/) source for the [BarentsWatch Fish Health API](https://developer.barentswatch.no/docs/fishhealth): the weekly report per aquaculture locality — lice counts, lice treatments, diseases, escapes and the licences behind the locality, as reported to the Norwegian Food Safety Authority — into any dlt destination.

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
[sources.barentswatch_fishhealth.locality]
locality_nos = [11340, 45072]
```

Then three steps, one example each. That is everything needed to get running, a page of code each.

1. **Discover** — [`discover_localities.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/discover_localities.py). One request: the API's list of every locality with a salmonoid licence, about 2 000, printed with number and name. Find yours by name and put their numbers in the config file above, or bind them in code as the next two examples do.
2. **Backfill** — [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/backfill.py). Every week from 2012 to now for the localities you chose, run once. Re-running it is safe: `locality_week` merges on locality, year and week.
3. **Weekly load** — [`weekly_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/examples/weekly_load.py). The last four complete weeks for the same localities, on a timer from then on. It re-requests weeks it already has because reports arrive after the week ends ([why four](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#the-weekly-load-looks-back)).

From a checkout, run one with `python examples/<name>.py`.

**Know the cost before step 2.** The weekly endpoint answers one locality in one ISO week per request, and BarentsWatch asks that batch requests are made one at a time — so the source makes them that way, and the cost of a load is localities × weeks, at about 0.1 s each:

| Load | Requests | Takes |
|---|---|---|
| A few localities back to 2012 (about 770 weeks each) | a few thousand | minutes |
| Every salmonoid locality, four weeks | about 8 000 | a quarter of an hour |
| Every salmonoid locality back to 2012 | about 1.5 million | days |

Weeks before a locality existed answer 400 in about 0.07 s and are skipped, so a backfill from 2012 is not slower for a locality that opened in 2019 — but it is not free either.

## What it loads

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `locality` | `GET /v1/geodata/fishhealth/localitieswithsalmonoids` | replace | — |
| `locality_week` | `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` | merge | `localityNo`, `year`, `week` |

`locality_week` is a dlt transformer over `locality`: for each locality row it requests every week in the range you bind, and writes one row per week the API has a report for. Three defaults worth knowing before your first query:

- **The key is injected, not returned.** The API's weekly response does not repeat which locality and week it is for, so the source adds `localityNo`, `year` and `week` from the request path. They land as `locality_no`, `year`, `week` — [where the rest of the row comes from](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#one-row-per-locality-week).
- **Nested objects land as one JSON column each** — `lice_report`, `lice_treatments`, `aqua_culture_register`, `geometry` and so on — [why, and how to override it](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#nesting).
- **A week with no report is skipped, not an error.** The API answers HTTP 400 for it, and for an unknown locality number, and the source cannot tell the two apart — [what that means for `locality_nos`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md#http-400-means-no-report).

## Configuring a resource

Two arguments, one per resource. Nothing else is configurable, because the two endpoints take nothing but their path.

```python
source = barentswatch_fishhealth_source()
source.locality.bind(locality_nos=[11340, 45072])
source.locality_week.bind(week_range=last_n_weeks(4))
pipeline.run(source)
```

| Argument | Resource | What to know |
|---|---|---|
| `locality_nos` | `locality` | A list of locality numbers to keep; `None` (the default) keeps every salmonoid locality. Bind it or set it in config under `[sources.barentswatch_fishhealth.locality]`. A number that is not a salmonoid locality is warned about and left out; an empty list, or a list with no match, raises. |
| `week_range` | `locality_week` | A `WeekRange(start_year, start_week, end_year, end_week)`, inclusive at both ends. **Required** — a run without one raises an error naming it. Bind it in code; it has no config form. |

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
| 0.1.x | `v1` spec — `GET /v1/geodata/fishhealth/localitieswithsalmonoids` and `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` |

The two numbers are unrelated: the package version is ordinary [SemVer](https://semver.org/), and `v1` is what the API's own OpenAPI document calls itself while its paths carry `/v1/` and `/v2/` prefixes of their own. Built against that document's [`specs/openapi.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/specs/README.md) and run live against the API, last on 2026-09-08. A later backwards-compatible API version should work, but run the suite first.

## Read next

- [**API quirks worth knowing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/specs/README.md#api-quirks-worth-knowing) — where the live API departs from its OpenAPI document, and which identifiers to join on. The 400-for-everything answer changes what a correct load looks like, so read it before your first one.
- [**Reference**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/REFERENCE.md) — the locality-week row, nesting, weeks and the lookback, backfilling, what the source does not expose, logging and column types.
- [**Changelog**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/CHANGELOG.md) and [**contributing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-barentswatch-fishhealth/LICENSE). `specs/openapi.json` is BarentsWatch's own OpenAPI document, included as the spec this package is built against. It is their material, and the licence does not extend to it. The data the API serves is published under [NLOD](https://data.norge.no/nlod), as the document's `info.license` states.
