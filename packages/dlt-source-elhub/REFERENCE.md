# Reference

The detail behind the [README](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/README.md), for adopting the package rather than evaluating it. Nothing here is needed to get a first load running.

Most of it is shorter as code: [`daily_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/daily_load.py), [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/backfill.py) and [`companies.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/companies.py).

## The cursor is per metering point

`metering_values_hour` keeps one cursor for each metering point, in dlt's resource state under the point's id, and that cursor is the latest `insertDateTime` the point has returned. Each run asks each point for values inserted at or after its cursor. A point without a cursor is asked from `initial_insert_date_time`, which is by default an instant older than anything Elhub holds, so the API answers with its widest window — everything it retains, three years and 41 days, in one request.

Three things follow, and they are the reason for the design:

- **A new metering point loads its whole history the first time it is seen**, whenever that is. A company delegating access later, or a new site, needs no backfill.
- **Corrections arrive on their own.** Elhub re-inserts a corrected value with a new `insertDateTime`, so it is newer than the cursor and comes with the next run; the key (`meteringPointId`, `startTime`, `direction`) makes it overwrite the old row. A cursor on `startTime` would have dropped it as already seen.
- **Several companies share one pipeline.** A metering point id is unique across Elhub, so the cursors of one company's points never touch another's. One source per `consumer_org`, one pipeline, one dataset.

**Why `insertDateTime` is the cursor, not `startTime`.** The API's filter is on when a value was inserted, which is monotonic on Elhub's side; the usage time is not, because corrections and late readings land out of order. The filter is inclusive, so every run re-fetches the values inserted at exactly the cursor's instant — one day's values per point, 24 or 96 rows, written once more by the merge. That is cheaper to accept than to avoid: it cannot miss a value inserted in the same second as the cursor.

**What the state looks like**, and what you can do to it:

```python
pipeline.state["sources"]["elhub_source"]["resources"]["metering_values_hour"]["insert_date_time"]
# {'707057500083917012': '2026-10-13T02:04:25+02:00', ...}
```

Delete a point's entry and the next run loads that point's history again. Delete the pipeline's state and every point does. A cursor never moves backwards: a response holding only inserts older than the cursor, which a bound window can return, leaves it alone.

### Backfilling

Bind `start_date` and `end_date` on `metering_values_hour` and the request carries exactly that, and nothing from the state: the stored cursor is neither read nor advanced. Bind `metering_point_ids` on `metering_points` to backfill a few points rather than all:

```python
source = elhub_source()
source.metering_points.bind(metering_point_ids=["707057500083917012"])
source.metering_values_hour.bind(start_date="2026-10-01", end_date="2026-10-03")
```

The window is sent as given. A date is `YYYY-MM-DD`, midnight in Europe/Oslo, or an ISO 8601 instant with an offset. `endDate` is documented as inclusive, but a midnight `endDate` does not return the hour that starts at it ([measured](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/specs/README.md#api-quirks-worth-knowing)), so treat the pair as half-open on `startTime`. There is no window splitting to do: with an id the API takes the whole retained range in one request.

The ids a backfill reads are the ones the list call returns, which are the points with values in the last 24 hours. A point that has stopped reporting is not listed, and so not backfilled; `metering_points` takes `start_date` and `end_date` of its own, at most a day apart, to list the points of another day.

### Several companies

A Maskinporten token is issued for one organisation. Reading a company that delegated the scope to your client's organisation in Altinn means a token with that company's organisation number as the `consumer_org` claim, so each company is its own source:

```python
for company in ["977106206", "976543718"]:
    pipeline.run(elhub_source(consumer_org=company))
```

The sources share the pipeline, its dataset and the cursor table, as above. Run them one at a time so a company that fails does not stop the others, and the error names it: `MP-250` from Maskinporten means Elhub has not granted the scope to that organisation, `MP-251` that the delegation in Altinn is missing. How a company delegates is between it and Altinn, not this package.

Reading the client's own organisation needs no `consumer_org`. A company with no metering points is a `204` on the list call and an empty run, not an error — whether that is fine is your pipeline's call.

## Nesting

`max_table_nesting=0`, so a nested object or list lands as one JSON column instead of dlt's automatic child tables. That is the neutral position: unnesting invents tables, columns and keys (`_dlt_parent_id`, `_dlt_list_idx`) that exist nowhere in the API.

Today nothing nests. The API returns a metering point as `type`, `id` and `attributes`, and the only attribute is the values list, which is `metering_values_hour`'s table rather than a column. Any other attribute Elhub adds lands in an `attributes` JSON column on `metering_points`; any `relationships` the spec promises land the same way, as one column, if they ever appear. Raise the setting if you want child tables:

```python
source = elhub_source()
source.max_table_nesting = 2
```

## What the source does not expose

**The other datasets.** `METERING_VALUES_PER_DIRECTION_DAY_RESTRICTED`, `_MONTH_` and `_YEAR_` answer `403` to `elhub:enduser`, so there is no resource for them; sum the hourly values yourself. A resource for them under `elhub:thirdparty` is welcome from someone who can verify it.

**The `elhub:thirdparty` scope.** The source takes `scope`, and `headers` carries `X-Elhub-GLN` and `On-Behalf-Of`, but nothing has been run against that scope. Under it `includeAllMeasurements=Y` returns every channel of a point, and the key `meteringPointId`, `startTime`, `direction` may then need `measurementName` too; the settled channel this package sees is one per direction.

**Pagination.** The metering-points responses carry a `links.self` and no next link; a three-year history arrives as one response. The source reads each response whole.

**Rate limiting.** Elhub documents none, and the source does no throttling: one request to list, one per metering point.

## Logging

The package logs two things of its own. One line per metering point and run at INFO on `dlt_source_elhub.elhub`, with the point's id, how many values it returned and since when: dlt reports nothing for a point that returned nothing, and a pipeline that must notice an empty point hears it here. And at DEBUG on `dlt_source_elhub.maskinporten`, that a token was issued, with the scope and `consumer_org`. Never the token, the grant or the key. Everything else it does, it raises.

dlt logs every request on the logger named `dlt` at INFO, off by default. Two `[runtime]` settings are worth knowing, each with an env var (`RUNTIME__LOG_LEVEL` and so on):

| Setting | What it buys |
|---|---|
| `log_level` | `"INFO"` shows each request. Not `"DEBUG"` against the real API: dlt's REST client then logs request headers, and the bearer token rides in one. |
| `http_show_error_body` | `true` shows Elhub's own `errors[].detail` on a `4xx`, which dlt otherwise strips to `400 Client Error`. Safe: it widens the response body, not the request. |

The rest is in dlt's [running in production](https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format) guide.

## Column types

Each resource declares column hints for its scalar fields, typed per [`specs/meta-metering-points.json`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/specs/README.md). They buy one thing: a column keeps its type when a first page has nulls in it, or a field is missing entirely.

Everything else is dlt's default. A field the API adds after this release lands as a new column rather than failing the load, and a nullable field it stops sending is absent rather than fatal — `tests/test_schema_leniency.py` holds both to that. Times land as text, exactly as the API sends them, with the Europe/Oslo offset of the day: parsing is a transform on your side.

## Retention

Elhub deletes values older than three years and 41 days, and a `startDate` at exactly that limit is a `400`. The first load gets what is left on the day it runs, and nothing gets it back later. Load early, and keep what you loaded: your destination is the archive, Elhub is not.
