# Changelog

All notable changes to `dlt-source-elhub`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

### Fixed

- A request Elhub leaves unanswered no longer ends in `401 The provided access token has expired`. dlt retried a timeout by re-sending the request, token included; the source now asks anew, as for a `429`, with a renewed token, and logs a WARNING. #94.

## [0.3.1] - 2026-11-10

### Fixed

- Waiting out Elhub's rate limit no longer ends in `401 The provided access token has expired`. A retry re-sent the first request, token included, and the refusal can outlast a token, 120 seconds by Digdir's default; each attempt now asks anew and carries a renewed token. #91.

## [0.3.0] - 2026-11-10

### Added

- Source params `request_max_attempts` and `request_max_retry_delay`: how long a `429` or `5xx` is retried. The defaults outlast Elhub's rate limit as measured; should Elhub change it, set them in `[sources.elhub]`. [Rate limiting](REFERENCE.md#what-the-source-does-not-expose), #88.

### Fixed

- A backfill waits out Elhub's rate limit instead of failing on the first `429`, with a WARNING each time it is refused. #88.
- An error status from Elhub raises `HTTPError` with the status and Elhub's body. Before, it surfaced as a JSON decode error or `KeyError: 'data'`, without either.

## [0.2.0] - 2026-11-10

### Added

- `metering_points` takes a `start_date`/`end_date` window wider than a day and lists it a day at a time, each point once, since the API lists at most a day per request. Bind the same window on both resources and a backfill reads every metering point the end user had in it, including one it has since lost: Elhub lists a point only for the days it belonged to the end user, and by id returns that period's values. Before, a backfill read only the points listed in the last 24 hours. [Reference](REFERENCE.md#backfilling), #85.

### Fixed

- The README no longer says the first run loads every metering point the end user ever had. It loads the points listed in the last 24 hours; a backfill over the retention finds the others.
- The recommended schedule is after 09:00 Europe/Oslo, when Elhub has forwarded yesterday to end users, not after 03:00. The insert time depends on the grid company: 02:05 held for one, another delivers around 06:15, and a daily load at 03:30 with the default list window left that company's metering points out. [API quirks](specs/README.md#api-quirks-worth-knowing).

## [0.1.1] - 2026-10-23

### Fixed

- A refused token request raises `MaskinportenError`, whose message carries Maskinporten's own `error` and `error_description` (`MP-250`, `MP-251`, ...) together with the scope and `consumer_org`. Before, it was requests' bare `400 Client Error`: dlt's `http_show_error_body` applies to the REST client, not to the token endpoint, so the reason never reached the logs. The signed grant stays out of the message. The exception is exported from the package.

## [0.1.0] - 2026-10-13

### Added

- Initial release: a dlt source for Elhub's Energy Data API — `metering_points`, the metering points an organisation can read, and `metering_values_hour`, their hourly or quarter-hourly metering values. What each resource loads and how to configure it is in the [README](README.md).
- Maskinporten authentication: `MaskinportenCredentials` (client id, key id, private key) resolved by dlt from `[sources.elhub.credentials]`, and `MaskinportenAuth`, the JWT bearer grant exchanged for a token and renewed before it expires. Reads a company that delegated the scope with `consumer_org`.
- A cursor per metering point on `insertDateTime`, kept in dlt's resource state: a new point loads everything Elhub retains on first contact, every later run loads what was inserted since, corrections included. [Reference](REFERENCE.md#the-cursor-is-per-metering-point).
- [API quirks worth knowing](specs/README.md#api-quirks-worth-knowing) records what was measured against the live API, next to a dated copy of Elhub's own documentation.
- [Compatibility](README.md#compatibility) records which API version the package is built and verified against. This release targets v0 with the scope `elhub:enduser`.
- The package ships a PEP 561 `py.typed` marker, so your type checker reads its annotations instead of treating it as untyped.
- Released under [Apache-2.0](LICENSE).
