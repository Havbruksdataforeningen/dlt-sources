# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Fixed

- **`max_window_days` no longer warns about `sites` and `environmental_latest`.** Both are resources the package loads; they have no cursor, so no window and no entry in `MAX_WINDOW_DAYS`, and 0.3.0 read that absence as a name it does not load. A consumer sizing chunks for a resource set heard the warning on every run that included `sites`. A resource with no window now answers the widest value quietly — it takes no window, so the answer must not narrow a chunk size — and the warning stays for names the source does not yield.

## [0.3.0] - 2026-08-31

### Added

- **`max_window_days(resource, period=None)`** — the window cap the source will split at, resolved the way the source resolves it. `MAX_WINDOW_DAYS` on its own does not answer for a `period` it is not keyed on: `MAX_WINDOW_DAYS[("environmental", None)]` raises where the source returns 366, the window cap of the period the API computes when a request sends none. Sizing chunks of your own from the table meant reimplementing that fallback by hand. The table stays public and writable for [correcting a window cap that has moved](REFERENCE.md#windows-are-split-to-fit-the-window-cap), and `max_window_days` reads what you assign to it.
- A warning on the `dlt_source_aquabyte.windows` logger when `max_window_days` is asked for a resource the package does not load. It still answers, with the widest window cap, because the table is writable and a missing window cap is not fatal — but a mistyped name would otherwise become a chunk the API refuses.

## [0.2.0] - 2026-08-31

### Fixed

- **A window wider than the API allows is split into several requests instead of failing the load.** The window cap is 7 days at `period=15min`, 31 at `h` and 366 otherwise, and it applies to open-ended requests too — so a daily load that fell further behind than its window cap allowed could not catch up on its own. [What that means for a load](REFERENCE.md#windows-are-split-to-fit-the-window-cap).

### Changed

- **`examples/quickstart.py` is now `examples/daily_load.py`.** The three examples are the three steps of [How to start](README.md#how-to-start): discover, backfill, daily load. "Quickstart" named a role two of them shared.
- **`examples/backfill.py` loads a history rather than one fixed month.** It takes the start you measured and runs to today, in one call — the source splits the span into requests the API accepts. It is now step 2 of the three-step path in the [README](README.md#how-to-start): discover, backfill, daily load.

### Added

- **`examples/discover_history.py`** — measures what your account holds: the earliest date, the newest date and the row count of each resource, all of them yours rather than shipped. It loads the history at `period="D"` and queries the result rather than probing for boundaries, because one request covers up to 366 days either way. Run it before choosing `initial_date`, `initial_time` and a `period`.
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
