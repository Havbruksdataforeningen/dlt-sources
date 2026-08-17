# Changelog

All notable changes to `dlt-source-aquabyte`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Added

- Initial source for the Aquabyte API: sites, pens, biomass, lice counts, welfare scores, behaviour (swim speed, breathing index), environmental readings and harvest reports.
- `harvest_report` types the `fishType` field the API returns.
- The README documents the API quirks that reach you as a consumer — unzoned timestamps on the two behaviour endpoints, and `lice_count` omitting its count fields on a zero-sample record.

### Fixed

- The packaged secrets example declared the API key under a section dlt does not read for this source, so following the quick start left credentials unresolved. It now uses `[sources.aquabyte]`, the section the README documents.
