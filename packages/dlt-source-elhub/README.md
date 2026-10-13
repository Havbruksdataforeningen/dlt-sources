# dlt-source-elhub

[![PyPI](https://img.shields.io/pypi/v/dlt-source-elhub.svg)](https://pypi.org/project/dlt-source-elhub/)

A [dlt](https://dlthub.com/) source for [Elhub's Energy Data API](https://api.elhub.no/energy-data-api/metering-points): your organisation's electricity metering points and their hourly metering values, authenticated through Maskinporten, into any dlt destination.

**Records land as the API returns them** — nothing renamed, nothing dropped, no invented child tables. Column names are the API's own, in dlt's usual snake_case. Reshaping belongs in your transform layer, where you can change it without waiting for a release.

The package handles the Maskinporten token, the headers Elhub insists on, envelope unwrapping and a cursor per metering point. It depends on dlt and PyJWT.

## How to start

Before any code: your organisation needs a Maskinporten client with the scope `elhub:enduser`, which Elhub grants to an organisation number on request ([Elhub's guide](https://api.elhub.no/energy-data-api/dataset-guidelines)). The client gives you a client id, a key id and a private key.

```bash
uv add dlt-source-elhub "dlt[duckdb]"   # any dlt destination works; DuckDB is the one below
```

Then two files in a `.dlt/` directory beside your script.

`.dlt/config.toml`:

```toml
[sources.elhub]
user_agent = "my-company-elhub-pipeline"   # Elhub refuses a request without one
```

`.dlt/secrets.toml`:

```toml
[sources.elhub.credentials]
client_id = "00000000-0000-0000-0000-000000000000"
kid = "00000000-0000-0000-0000-000000000000"
private_key = """-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----"""
```

Then one script, [`daily_load.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/daily_load.py), on a timer:

```python
import dlt
from dlt_source_elhub import elhub_source

pipeline = dlt.pipeline(pipeline_name="elhub", destination="duckdb", dataset_name="elhub_data")
pipeline.run(elhub_source())
```

There is no separate backfill step. The first run loads everything Elhub retains for every metering point — three years and 41 days, one request per point — and every run after loads what was inserted since, per point. Schedule it after 03:00 Europe/Oslo: yesterday's hours are inserted around 02:05. Run it soon: Elhub deletes data older than three years and 41 days, so each day a first load waits, a day of history is gone.

Two more examples, a page each: [`backfill.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/backfill.py) re-loads one window without touching the cursors, and [`companies.py`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/examples/companies.py) reads several companies with one client. From a checkout, run one with `python examples/<name>.py`.

## What it loads

| Resource | Endpoint | Load strategy | Key |
|---|---|---|---|
| `metering_points` | `GET /metering-points` | merge | `id` |
| `metering_values_hour` | `GET /metering-points/{id}` | merge | `meteringPointId`, `startTime`, `direction` |

Both read the dataset `METERING_VALUES_HOUR_RESTRICTED`, the only one the `elhub:enduser` scope answers; the day, month and year datasets are `403` under it, so aggregate downstream.

Three things worth knowing before your first query:

- **`metering_points` is the list of ids, found the only way Elhub offers.** There is no list endpoint; the dataset call without an id returns every point with values in the last 24 hours. A point lands as the API's `id` and `type`, with the values left to the other table. A point gone from the list keeps its row; its `_dlt_load_id` says when it was last seen.
- **`metering_values_hour` is one row per value**, with the point's `id` as `meteringPointId`. `resolution` is `PT60M` on most points and `PT15M` on some, so never assume 24 rows a day. `direction` is `Out` for consumption and `In` for production, both loaded. A corrected value overwrites the old one, because the key is the interval, not the insert.
- **The cursor is per metering point**, stored in dlt's resource state under the point's id. That is what makes a new point load its history on first contact, and several companies safe in one pipeline — [how it works](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/REFERENCE.md#the-cursor-is-per-metering-point).

## Configuring a resource

Each resource takes its endpoint's params in snake_case. Dates are `yyyy-MM-dd'T'HH:mm:ssXXX` in Europe/Oslo.

```python
source = elhub_source(consumer_org="977106206")
source.metering_values_hour.bind(start_date="2026-10-01T00:00:00+02:00", end_date="2026-10-03T00:00:00+02:00")
pipeline.run(source)
```

| Param | What to know |
|---|---|
| `consumer_org` | On the source. The organisation number of a company that delegated the scope to your client's organisation in Altinn; the token is then issued on its behalf. Leave it out to read the client's own organisation. One source per company. |
| `initial_insert_date_time` | On the source. Where a point the pipeline has not seen starts: values inserted at or after this instant. Left out, everything Elhub retains. |
| `start_date`, `end_date` | On both resources. On `metering_points` they move the discovery window, at most one day wide. On `metering_values_hour` they make the request a backfill: the window is sent as given, and the stored cursor is neither read nor advanced. The end is exclusive on `startTime` in practice. |
| `insert_date_time` | On `metering_values_hour`. Sent instead of the cursor, which is then neither read nor advanced. A backfill sends `ALL_RETAINED_HISTORY` here to get every value in its window. |
| `params` | On every resource, merged into the query string last, so it wins over every named param. The escape hatch for a param the API grows later. |
| `user_agent`, `headers` | On the source. Elhub answers `403` to a request without a `User-Agent`; `headers` adds any other, such as `X-Elhub-GLN` under another scope. |

Params can also be set in config, per resource:

```toml
[sources.elhub.metering_values_hour]
start_date = "2026-10-01T00:00:00+02:00"
end_date = "2026-10-03T00:00:00+02:00"
```

## Compatibility

| `dlt-source-elhub` | Energy Data API |
|---|---|
| 0.1.x | v0 |

The API is v0, and Elhub says breaking changes may come. Built against the dated copy of its documentation in [`specs/`](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/specs/README.md) and run live against it, last on 2026-10-13, with the scope `elhub:enduser`. The `elhub:thirdparty` scope is not verified.

## Read next

- [**API quirks worth knowing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/specs/README.md#api-quirks-worth-knowing) — what was measured against the live API: windows, the inclusive `insertDateTime` filter, `204` for empty, when yesterday arrives.
- [**Reference**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/REFERENCE.md) — the cursor, backfilling, several companies, nesting, what the source does not expose, logging and column types.
- [**Changelog**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/CHANGELOG.md) and [**contributing**](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/CONTRIBUTING.md).

## License

[Apache-2.0](https://github.com/Havbruksdataforeningen/dlt-sources/blob/main/packages/dlt-source-elhub/LICENSE). The files in `specs/` are Elhub's own API documentation, included as the spec this package is built against. They are Elhub's material, and the licence does not extend to them.
