# Changelog

All notable changes to `dlt-source-barentswatch-fishhealth`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Added

- Initial release: a dlt source for the BarentsWatch Fish Health API — the list of salmonoid localities (`locality`) and the detailed weekly report per locality (`locality_week`): lice counts, lice treatments, diseases, escapes, control areas and the aquaculture-register entry behind the locality. What each resource loads and how to configure it is in the [README](README.md).
- `WeekRange`, `last_n_weeks`, `current_iso_week`, `weeks_in_year` and `FIRST_YEAR`, for building the week range `locality_week` needs — the API is addressed by ISO year and week, with no window parameter and no cursor.
- [REFERENCE.md](REFERENCE.md) holds the operational detail — the locality-week row, nesting, the lookback and backfilling, why HTTP 400 is skipped, and what the source deliberately does not expose — so the README stays a first read.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Fish Health API version the package is built and verified against. This release targets the `v1` spec, endpoints `/v1/geodata/fishhealth/localitieswithsalmonoids` and `/v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}`.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
