# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Added

- Initial release: a dlt source for the Aquabyte API — sites, pens, biomass, lice counts, welfare scores, behaviour (swim speed, breathing index), environmental readings and harvest reports. What each resource loads and how to configure it is in the [README](README.md).
- `dlt` is the package's only dependency. Column types come from dlt's own column hints, so pydantic is not installed on your behalf and nothing here depends on dlt's deprecated pydantic integration. Destination column types, and how the source handles a field the API adds or stops sending, are unchanged.
- [REFERENCE.md](REFERENCE.md) holds the operational detail — versioned registry tables, nesting, backfilling, and what the source deliberately does not expose — so the README stays a first read.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Aquabyte API version the package is built and verified against. This release targets v3.1.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
