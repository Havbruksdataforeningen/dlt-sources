# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Fixed

- **A window wider than the API allows is now split into several requests instead of failing the load.** The API caps window width per endpoint and per grain — 7 days at `period=15min`, 31 at `h`, 366 otherwise — and refuses a wider one with a `400` rather than truncating it. Because an open-ended request is measured to today, a daily load that missed more days than its cap allowed failed every night afterwards, wider each time, and could not recover without someone binding a window by hand. Each resource now splits its own span, oldest first: [what that means for a load](REFERENCE.md#the-window-is-split-to-stay-inside-the-apis-cap).

### Added

- **Every request now carries an explicit end** (`toDate`/`toTime`), which is `end_value` when one is bound and now when none is. The width of a request is therefore known before it is sent, rather than being whatever the gap since the last successful run happens to be.
- **`MAX_WINDOW_DAYS`**, the cap table keyed by `(resource, period)`, is importable from the package — for sizing chunks of your own, or rejecting a `--chunk-days` before spending a request. The caps are [measured, not documented by the API](specs/README.md#api-quirks-worth-knowing).

## [0.1.0] - 2026-08-20

### Added

- Initial release: a dlt source for the Aquabyte API — sites, biomass, lice counts, welfare scores, behaviour (swim speed, breathing index), environmental readings and harvest reports. What each resource loads and how to configure it is in the [README](README.md).
- [REFERENCE.md](REFERENCE.md) holds the operational detail — the versioned site registry, nesting, backfilling, and what the source deliberately does not expose — so the README stays a first read.
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records where the live API departs from its own OpenAPI document, in ways that reach you as a consumer.
- [Compatibility](README.md#compatibility) records which Aquabyte API version the package is built and verified against. This release targets v3.1.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
