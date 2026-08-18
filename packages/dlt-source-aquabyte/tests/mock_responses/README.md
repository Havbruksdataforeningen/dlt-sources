# Mock responses

**Every value in this directory is invented. None of it is Aquabyte data.**

These files are templates, not recorded payloads. Their *shape* — which fields appear,
which are omitted, which arrive null, how timestamps are formatted, how deeply things
nest — was taken from live responses on 2026-08-17. Their *values* were then made up by
hand, inside the ranges that run observed. No real identifier, site or pen name,
government site number or measurement was carried across.

## Before you "fix" an odd-looking shape

Several fixtures carry shapes that look like mistakes and are not: a record missing
fields its neighbours have, a timestamp without a time zone, a nested key that is absent
rather than null. They are what the API does, and a fixture that smooths one over makes
the whole offline suite blind to it.

Which shapes those are is deliberately **not** listed here, so that the API's behaviour
has one place to be updated rather than two: they are in
["API quirks worth knowing"](../../README.md#api-quirks-worth-knowing) in the package
README.

`test_mock_fidelity.py` validates every fixture against its record model, so a shape the
API could not have produced fails the suite rather than sitting here unnoticed.

## Identifiers and dates

Identifiers are the suite's own scheme (`site-00N`, `pen-00N`, with `pen-002` inactive),
and dates sit in the fixtures' existing synthetic early-2026 window — January for the
windowed endpoints, February for `environmental_latest.json`, which reports one moment
rather than a range. `tests/conftest.py` exports the pen constants; keep them in step
with `sites.json`.

## Per-pen templates

A data fixture holds records for **one** pen. `tests/conftest.py:serve()` clones them
across pens to answer a `penId=all` request, so a fixture that hardcodes several pens
breaks that helper. Keep record counts small — a handful per endpoint is enough to prove
a shape, and two sites carry the same structure as a dozen.
