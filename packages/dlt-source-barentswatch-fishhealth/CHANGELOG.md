# Changelog

All notable changes to `dlt-source-barentswatch-fishhealth`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Added

- Initial release: a dlt source for the BarentsWatch Fish Health API — the list of salmonoid localities (`locality`) and the detailed weekly report per locality (`locality_week`): lice counts, lice treatments, diseases, escapes, control areas and the aquaculture-register entry behind the locality. What each resource loads and how to configure it is in the [README](README.md).
- `locality_week_summary`: the weekly summary of every locality matching a filter, from `POST /v2/geodata/fishhealth/locality/{year}/{week}` — one request per week per production area or organisation, or one for the whole coast, instead of one per locality. A summary row has the same lice report as `locality_week`, diseases and lice treatments as names only, and none of the register, zone or escape fields; it merges on the same key, so the two tables join. Bind `production_areas`, `organizations` or `filters` (the spec's other ~30 body fields, sent as given). [`examples/production_areas.py`](examples/production_areas.py) is the fourth example: two areas, the last four weeks, on a timer. Which table to load for what is in [REFERENCE.md](REFERENCE.md#the-summary-and-the-detail).
- `WeekRange`, `last_n_weeks`, `current_iso_week`, `weeks_in_year` and `FIRST_YEAR`, for building the week range both weekly resources need — the API is addressed by ISO year and week, with no window parameter and no cursor.
- [REFERENCE.md](REFERENCE.md) holds the operational detail — the locality-week row, nesting, the lookback and backfilling, why HTTP 400 is skipped, and what the source deliberately does not expose — so the README stays a first read.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Fish Health API version the package is built and verified against. This release targets the `v1` spec, endpoints `GET /v1/geodata/fishhealth/localitieswithsalmonoids`, `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` and `POST /v2/geodata/fishhealth/locality/{year}/{week}`.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
