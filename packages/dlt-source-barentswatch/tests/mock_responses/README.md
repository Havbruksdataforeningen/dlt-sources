# Mock responses

**Every value in this directory is invented. None of it is BarentsWatch data.**

These files are templates, not recorded payloads. Their *shape* — which fields appear,
which arrive null, which arrays come back empty, how dates are formatted, how deeply
things nest — was taken from live responses on 2026-09-08. Their *values* were then made
up by hand. No real locality number, locality name, licensee, organisation number, licence
number or coordinate was carried across: the locality numbers are `9000N`, which the
Aquaculture Register does not issue, and the names are words like "Testholmen" and
"Prøvevika".

| File | Stands in for |
|---|---|
| `localities.json` | `GET /v1/geodata/fishhealth/localities` — the full locality list: number, name, municipality and register version |
| `localitieswithsalmonoids.json` | `GET /v1/geodata/fishhealth/localitieswithsalmonoids` — the salmonoid locality list, number and name only |
| `locality_week_reported.json` | `GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` for a week with a lice report and one treatment |
| `locality_week_fallow.json` | The same endpoint for a fallow week: `hasReported: false`, `isFallow: true`, every average null |
| `problem_details_400.json` | The same endpoint's 400 body — the API's answer for a week it has no report for |
| `locality_week_summary.json` | `POST /v2/geodata/fishhealth/locality/{year}/{week}` — the weekly summary of every locality matching the body's filter: one reported week, one fallow week, and one reported with a disease and a treatment category |

## Before you "fix" an odd-looking shape

Several fields look like mistakes and are not: `productionArea.color`, every `trend`,
`cleanerFishTreatment` and `mechanicalRemovalTreatment` arrive null although the spec
does not say they may. That is what the API does, and a fixture that smooths it over makes
the whole offline suite blind to it.

Which shapes those are is deliberately **not** listed in full here, so that the API's
behaviour has one place to be updated rather than two: they are in
["API quirks worth knowing"](../../specs/README.md#api-quirks-worth-knowing), next to the
spec they depart from.

`test_mock_fidelity.py` validates every fixture against its endpoint's response schema in
`specs/fishhealth.json`, so a shape the API could not have produced fails the suite rather
than sitting here unnoticed.

## Identifiers

`tests/conftest.py` exports the locality numbers as `ALL_LOCALITY_NOS`; keep them in step
with `localitieswithsalmonoids.json`. The salmonoid list is a subset of the full list, as it
is live, so every number in `localitieswithsalmonoids.json` is also in `localities.json`;
the municipality numbers there are invented too, `990N`. The two detailed weekly fixtures describe the first
two of those localities, but a test may serve either fixture for any locality and week — the
source stamps `localityNo`, `year` and `week` from the request, not from the body. The
summary fixture's three rows are the first three localities; a test may serve it for any
week and any body, since `year` and `week` are stamped from the request too and `localityNo`
from the row's `locality.no`. Keep the fixtures small: one licence or two proves the nesting as well as six would.
