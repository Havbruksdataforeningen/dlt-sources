# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [0.1.0] - 2026-08-19

### Added

- Initial source for the Aquabyte API: sites, pens, biomass, lice counts, welfare scores, behaviour (swim speed, breathing index), environmental readings and harvest reports.
- `harvest_report` types the `fishType` field the API returns.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Aquabyte API version the package is built and verified against. This release targets v3.1.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).

### Fixed

- The packaged secrets example declared the API key under a section dlt does not read for this source, so following the [quick start](README.md#quick-start) left credentials unresolved. It now uses `[sources.aquabyte]`, the section [Configuration](README.md#configuration) documents.
