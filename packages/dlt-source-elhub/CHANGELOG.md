# Changelog

All notable changes to `dlt-source-elhub`, written for people using the package. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); how to write an entry is in [`docs/release.md`](../../docs/release.md).

## [Unreleased]

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
