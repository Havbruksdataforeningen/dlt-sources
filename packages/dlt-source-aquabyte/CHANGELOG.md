# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Fixed

- **A window wider than the API allows is split into several requests instead of failing the load.** The window cap is 7 days at `period=15min`, 31 at `h` and 366 otherwise, and it applies to open-ended requests too — so a daily load that fell further behind than its window cap allowed could not catch up on its own. [What that means for a load](REFERENCE.md#windows-are-split-to-fit-the-window-cap).

### Added

- Every request now carries an explicit end (`toDate`/`toTime`): `end_value` when one is bound, now when none is.
- `MAX_WINDOW_DAYS`, the window cap table keyed by `(resource, period)`, is importable for sizing chunks of your own. It is writable too, so a window cap that moves does not need a release. The window caps are [measured, not documented by the API](specs/README.md#api-quirks-worth-knowing).
- A warning on the `dlt_source_aquabyte.windows` logger when a cursor value cannot be read as a date or a time, since the window then goes out unsplit and may be refused. The package had no logger before this.

## [0.1.0] - 2026-08-20

### Added

- Initial release: a dlt source for the Aquabyte API — sites, biomass, lice counts, welfare scores, behaviour (swim speed, breathing index), environmental readings and harvest reports. What each resource loads and how to configure it is in the [README](README.md).
- [REFERENCE.md](REFERENCE.md) holds the operational detail — the versioned site registry, nesting, backfilling, and what the source deliberately does not expose — so the README stays a first read.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Aquabyte API version the package is built and verified against. This release targets v3.1.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
