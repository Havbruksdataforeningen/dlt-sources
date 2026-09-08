# Specs

`openapi.json` is the BarentsWatch Fish Health API's own OpenAPI document, and the source
of truth for this package. Everything about the API itself — auth, base URL, the terms of
use, the note that the lice data are raw reports and not corrected before publishing — is in
there, most of it under `info.description` and `components.securitySchemes`.

| | |
|---|---|
| Fetched from | <https://www.barentswatch.no/bwapi/openapi/fishhealth/openapi.json> |
| `openapi` | `3.0.4` |
| `info.version` | `v1` |
| Fetched on | 2026-09-08 |

Refresh it by overwriting the file from that URL and running the tests —
`tests/test_spec_surface.py` pins the four paths this package reads, the server URL and
the token URL against it, and `tests/test_mock_fidelity.py` validates the offline
fixtures against its schemas. The filename stays put, so `git log -p specs/openapi.json`
reads as a history of the API's own changes.

The document covers the whole Fish Health API: 128 paths, from lice per production area to
the aquaculture register. This package reads four of them —
`GET /v1/geodata/fishhealth/localities`, `GET /v1/geodata/fishhealth/localitieswithsalmonoids`,
`GET /v2/geodata/fishhealth/locality/{localityNo}/{year}/{week}` and
`POST /v2/geodata/fishhealth/locality/{year}/{week}`, a `POST` that only reads (the filter
is a JSON body; nothing is stored) — and `REFERENCE.md` says why the rest is left alone
under "What the source does not expose". The `v1` in
`info.version` is the document's own version; the `/v1/` and `/v2/` in the paths are per
endpoint, and both are current.

**Where the API and this spec disagree, the API wins.** The package is built against what
the API actually returns, not against what `openapi.json` says it should. The differences
found so far are below. They are short internal notes, not a bug report: feedback for
BarentsWatch goes to them directly rather than being kept here.

## API quirks worth knowing

> **Observed against the live API on 2026-09-08.** Any of them may have been fixed since.
> Re-check before building on one, and update this section — and the fixtures that model
> it — when you do.

The API does a few things `openapi.json` does not describe. The source does not paper over
them: records land as sent, so these reach whoever reads the data. The ones that change how
you load or read it:

- **The weekly endpoint answers `400` for everything it has no data for, and says nothing
  else.** The spec lists a `400` response with a `ProblemDetails` body, and that is what
  arrives for every one of: a week the locality did not report, a week before the locality
  existed, a future week, a year before 2012, a locality number the API does not know. The
  body is the same shape each time — `{"title": "Locality week for 11340 2030-W1 was not
  found.", "status": 400, ..., "bwErrorCode": "GenericError"}`, with a `bwErrorCode` the
  spec's `ProblemDetails` does not declare. Only an invalid week number says something
  different (`Week must in the range [1, 52] or [1, 53]...`). So "no data" and "no such
  locality" are indistinguishable, and the source treats every `400` as a skipped week.
  A `401` is a bad token; anything else non-200 raises.

- **The API's history starts at ISO year 2012.** `2011-W1` is refused with the `400` above;
  `2012-W1` is served. Nothing in the spec says so. `FIRST_YEAR` in `weeks.py` pins it, and
  `WeekRange.validate()` refuses an earlier start before any request is made, because a
  range from 2000 would otherwise cost twelve years of silent `400`s per locality.

- **A fallow locality is a `200`, not a `400`.** A week a locality is fallow answers with a
  full report: `liceReport.isFallow: true`, `hasReported: false`, and `null` in every
  `average`. The row lands. Nothing about the response shape says this, and it is the
  reason a missing row and a fallow week are different things — [REFERENCE.md](../REFERENCE.md#http-400-means-no-report).

- **Properties whose schema is a bare `$ref` arrive as `null` with no `nullable: true`.**
  The document is OpenAPI 3.0 and marks nullability with `nullable: true` — but a property
  that is only `{"$ref": ...}` cannot carry the marker (a sibling of `$ref` is ignored in
  3.0), and several such properties are `null` in real responses: `productionArea.color`,
  every `liceReport.*.trend`, `liceTreatments.cleanerFishTreatment` and
  `liceTreatments.mechanicalRemovalTreatment`. The spec reads as if these are always
  present. `tests/test_mock_fidelity.py` validates the fixtures against the spec with
  exactly two relaxations — a `$ref` property may be `null`, and so may a property marked
  `nullable` — and nothing else, so a fixture that departs from the spec in any other way
  fails.

- **A week's row can change after it first appears.** The operation description says the
  information is updated nightly from reports to Mattilsynet via Altinn, and a report for a
  week arrives after the week ends — so the same locality-week loaded on two days can
  differ, and merge overwrites the older one. That is what the weekly load's lookback is
  for. Whether the non-lice parts of the row — the register entry, control areas — are the
  week's state or today's is not stated; treat them as today's until verified.

- **Cleaner fish stops at week 16 of 2018.** The operation description says so: cleaner
  fish is not included after that week because the reporting requirements changed, and
  `info.description` adds that data from 19 April 2018 may be missing during the
  transition. `liceTreatments.cleanerFishTreatment` was `null` on every recent week
  checked, not an empty object.

- **`localitieswithsalmonoids` returns the same locality more than once.** 2 002 objects for
  1 902 distinct `localityNo` on 2026-09-08: 92 numbers twice and four three times, 100
  surplus objects. Every repeat is the same site under another spelling of its name — a
  punctuation variant (`Alterosen (Land)` / `Alterosen Land`, `Industrilab Hib` /
  `Industrilab,,Hib` / `Industrilab.,Hib`), an abbreviation expanded (`Dolma N` /
  `Dolma Nord`), a typo (`Kvenbukta V` / `Kvernbukta V`) or an outright rename
  (`Arveneset` / `Skjelfjord`, `Veso Vikan` / `Vikan Akvavet`). Nothing but `name` differs;
  the objects carry no other field. The list looks like it is keyed on the site's name
  history rather than on its number. `localities`, the register list, has none of this —
  2 706 objects, 2 706 distinct numbers — and the salmonoid numbers are a subset of it, so
  the two lists disagree only in this one respect. Raised with BarentsWatch rather than
  worked around here.

  It reaches a load two ways: `localities_with_salmonoids` lands 2 002 rows for 1 902
  localities, so count `distinct locality_no` over it; and `locality_week` iterates that
  list, so a duplicated locality is requested once per repeat — 100 redundant requests per
  week loaded, about 5 % of a full-coast run, deduplicated on arrival by the merge key.
  De-duplication is left to the transform layer rather than done in the source: the API's
  answer lands as the API gave it, and the canonical name for a locality comes from
  Fiskeridirektoratet's register anyway, not from this list.

And one that bites when you are debugging rather than reading:

- **dlt hides the `title` that says what the API objected to.** `http_show_error_body`
  defaults to `False`, so a refusal the source does not swallow reaches your logs as
  `401 Client Error: Unauthorized` and nothing more. Set `RUNTIME__HTTP_SHOW_ERROR_BODY=true`
  before debugging against this API. The skipped `400`s are `DEBUG` lines, one per week —
  [Logging](../REFERENCE.md#logging).

Two of the three `GET` endpoints take nothing but their path, and `localities` takes one
optional `query` — a free-text search by name or site id, which this package does not send
and which does not filter the duplicates above — so there is no mistyped-parameter quirk to
know about there. The summary `POST` takes a filter body,
`LocalityReportQueryV2`, and has three of its own:

- **`productionArea` and `organization` take one value each.** The spec types them as one
  integer and one string, and the API means it: a JSON list in `productionArea` answers
  `400`, and a comma-separated string in `organization` answers `200` with no rows. Two
  areas is therefore the resource run once per area, each with its own `body`, as
  `examples/production_areas.py` does. A list in the `body` reaches the API as sent, and
  its `400` is skipped like a week with no report —
  [REFERENCE.md](../REFERENCE.md#http-400-means-no-report).

- **`liceTreatments` and `diseases` are a different shape on the two weekly endpoints.**
  The detailed report carries an object, `LiceTreatments`, with one list or object per kind
  of treatment, and `diseases` as full cases with status and dates; the summary carries an
  array of `LiceTreatmentName` — `MEDIKAMENTELL`, `IKKE_MEDIKAMENTELL`, `RENSEFISK` — and an
  array of `DiseaseName`. Both are what the spec declares, and both were verified live on a
  locality with an open PD case; the quirk is that the same field names land as
  `lice_treatments` and `diseases` in both tables and do not mean the same thing.
  `liceReport` is identical on the two.

- **A summary row does not say which production area it is in.** `LocalityWeekReportV2`
  has no `productionArea`, so a load of two areas lands as one undifferentiated set of
  rows, and an empty body returns every locality on the coast — 1 770 rows on 2025-W35 —
  with no area on any of them. The detailed row carries `productionArea` as
  `{id, name, color}`; the summary never does. Stamp it on with `add_map` if you need it.

### Identifiers

**`localityNo` is the key, inside and outside this dataset.** Both locality lists return it
as `localityNo`, both weekly reports repeat it as `locality.no`, and the source adds it
as `locality_no` on every weekly row — from the request path in `locality_week`, copied
from `locality.no` in `locality_week_summary` — because neither weekly response says
which week it answers, and the detailed one does not repeat the locality. All three are the same number:
the locality number from the aquaculture register, which is the identifier the industry,
Fiskeridirektoratet and Mattilsynet all use. So it joins `localities_with_salmonoids` and `localities` to `locality_week` by
construction, and — assumed rather than verified — `locality_week` to any other
BarentsWatch dataset and to a member company's own systems.

**A week is `year` + `week`, ISO.** The API addresses a week by its ISO year and week
number, and the source lands both as integers. Join on the pair: an ISO year is not a
calendar year at the edges, so `2026-W1` may hold days of December 2025.

**The register's own identifiers travel inside `aqua_culture_register`.** `licenses[].licenseNo`
is Fiskeridirektoratet's licence number, and `organizations[].organizationNo` is the
Brønnøysund organization number of the licensee — the one field that joins to a company
register outside aquaculture, and the value the summary's `organization` filter takes.
Both are inside the JSON column; unnesting them is your transform's job.
