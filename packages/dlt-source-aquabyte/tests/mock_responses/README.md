# Mock responses

**Every value in this directory is invented. None of it is Aquabyte data.**

These files are templates, not recorded payloads. Their *shape* — which fields appear,
which are omitted, which arrive null, how timestamps are formatted, how deeply things
nest — was taken from a live comparison against the Aquabyte API on 2026-08-17, written
up in [`specs/api-observations-2026-08-17.md`](../../specs/api-observations-2026-08-17.md).
Their *values* were then made up by hand, inside the ranges that run observed. No real
identifier, site or pen name, government site number or measurement was carried across.

Identifiers are the suite's own scheme (`site-00N`, `pen-00N`, with `pen-002` inactive),
and dates sit in a synthetic January 2026 window. `tests/conftest.py` exports the pen
constants; keep them in step with `sites.json`.

## Shapes worth not "fixing"

Several of these look like mistakes and are not. They are what the API does, and the
offline suite is blind to them if a fixture smooths them over.

| File | Shape | Why |
|---|---|---|
| `sites.json` | No `external_site_id` on a site, no `external_id` on a pen | Declared in the spec, absent from every live response — the key is missing, not null |
| `lice_count.json` | The zero-sample record omits all five count fields | Live omits them together on a zero-sample record, rather than sending null |
| `swim_speed.json`, `breathing_index.json` | Timestamps have no trailing `Z` | These two endpoints return unzoned timestamps; `environmental.json` keeps the `Z` its endpoint does send |
| `welfare_scores.json` | A category with no data is absent, not null; `healed` appears on `bodyWound` only | Both match live exactly |
| `biomass.json` | The last record's `weightDist` arrays are empty | Live returns empty arrays for some records |
| `harvest_report.json` | Distribution keys are `0.0-1.0` … `14.0-15.0`; `createdAt` has microseconds | The live key format and timestamp precision |

## Per-pen templates

A data fixture holds records for **one** pen. `tests/conftest.py:serve()` clones them
across pens to answer a `penId=all` request, so a fixture that hardcodes several pens
breaks that helper. Keep record counts small — a handful per endpoint is enough to prove
a shape, and two sites carry the same structure as a dozen.
