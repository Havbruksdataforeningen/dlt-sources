# Aquabyte Public API v3.1 — observations from a live comparison against the OpenAPI document

We compared live responses from the Aquabyte Public API against the OpenAPI document the
API publishes, field by field, and are sending you the differences we found.

| | |
|---|---|
| OpenAPI document | `info.version` `v3.1`, fetched from <https://api.aquabyte.ai/v3/openapi.json> on 2026-08-15 |
| Live requests made | 2026-08-17 |
| Endpoints covered | `/sites`, `/sites/{siteId}`, `/environmental`, `/environmental/latest`, `/biomass`, `/biomass/harvestReport`, `/liceCount`, `/behaviour/swimSpeed`, `/behaviour/breathingIndex`, `/welfareScores` |

**All observations come from a single customer account.** Where we report that a field
never arrived, we cannot tell whether the field is unset for this account or missing for
everyone. We have flagged which of the two we think is more likely, but we are guessing;
please read these as questions rather than as confirmed defects.

Every endpoint returned HTTP 200 and a body matching its declared envelope. **No endpoint
returned a field the document does not declare**, so nothing below is about undocumented
data — only about declared fields that did not arrive, and about formats and behaviour
that differ from what the document states.

## Summary

| # | Endpoint | Observation | We presume wrong |
|---|---|---|---|
| 1 | `/sites`, `/sites/{siteId}` | `Site.external_site_id` declared, never returned | Either — depends on whether it is account-specific |
| 2 | `/sites`, `/sites/{siteId}` | `Pen.external_id` declared, never returned | Either — depends on whether it is account-specific |
| 3 | `/liceCount` | Five fields marked required are omitted from some records | The API |
| 4 | `/behaviour/swimSpeed`, `/behaviour/breathingIndex` | `date-time` fields returned with no UTC offset | The API |
| 5 | `/biomass/harvestReport` | `createdAt` precision differs from other timestamps | Neither — consistency note |
| 6 | `/biomass/harvestReport` | `fromDate` typed differently from every comparable parameter | The document |
| 7 | All | Unknown query parameters are accepted rather than rejected | The API |
| 8 | All | Result ordering is not documented | The document |
| 9 | All | `nextToken` pagination could not be exercised | — |

---

## 1. `/sites` and `/sites/{siteId}` — `external_site_id` is never returned

**The document says:** the `Site` schema declares `external_site_id` as a nullable string.

**The API did:** omitted the property entirely from every site object in both endpoints'
responses. The key is not present; it is not present-and-null.

**Presumed wrong:** we cannot tell. If this field carries a customer's own site
identifier and is simply unset for our account, the API is behaving correctly and the
document could say so. If it is meant to be populated for every account, the API is
dropping it.

We would like to use this field to join your site records to our own master data, so we
would value knowing which case this is, and how the field gets populated.

## 2. `/sites` and `/sites/{siteId}` — `external_id` is never returned on pens

**The document says:** the `Pen` schema declares `external_id` as a nullable string.

**The API did:** omitted the property entirely from every pen object nested in every site.
As above, the key is absent rather than null.

**Presumed wrong:** the same open question as finding 1, and the same request: we would
like to join your pens to our own pen master data.

## 3. `/liceCount` — required fields are omitted from zero-sample records

**The document says:** the `LiceCount` schema marks `adultFemale`,
`adultFemaleConverted`, `mobile`, `mobileConverted` and `caligus` as **required**. All
five are also declared nullable.

**The API did:** omitted all five properties from a minority of records — specifically,
records reporting a sample size of zero. The remaining records carry all five. When the
five are omitted they are omitted together, never individually.

**Presumed wrong:** the API. Because the schema already declares these fields nullable,
returning `null` for a zero-sample record would express the same thing and would conform
to the schema. As it stands, a strict validator rejects those records.

Either fix works for us: return `null`, or drop the five from the schema's `required`
list. Returning `null` is the smaller change for consumers.

## 4. `/behaviour/swimSpeed` and `/behaviour/breathingIndex` — timestamps carry no UTC offset

**The document says:** `fromTime` and `toTime` on `BehaviorSwimSpeed` and
`BehaviorBreathingIndex` are declared `"type": "string", "format": "date-time"`. In
OpenAPI, `date-time` is RFC 3339, which requires a time offset.

**The API did:** returned these fields as `YYYY-MM-DDTHH:MM:SS` — no `Z`, no numeric
offset. The same kind of field on `/environmental` and `/environmental/latest` is
returned as `YYYY-MM-DDTHH:MM:SSZ`, with the designator.

**Presumed wrong:** the API. This is the finding with the most consequence for us: a
consumer reading these two endpoints cannot tell from the payload what zone the times are
in, and a consumer reading them alongside `/environmental` gets two different formats for
what appears to be the same concept. We are currently assuming UTC, to match the
endpoints that say so. Please confirm whether that assumption is right.

## 5. `/biomass/harvestReport` — `createdAt` precision differs from other timestamps

**The document says:** `createdAt` is declared `date-time`, like every other timestamp in
the API.

**The API did:** returned it with microsecond precision and a `Z` designator, where the
other `date-time` fields in the API are returned with second precision.

**Presumed wrong:** neither — both forms are valid RFC 3339, and this breaks nothing for
us. We mention it only because a single house format across the API would be easier to
consume. The date-only fields on this endpoint (`asOfDate`, `lastFeedingDate`,
`slaughterStartDate`, `slaughterEndDate`) are returned as plain `YYYY-MM-DD` and match
their declared `date` format.

## 6. `/biomass/harvestReport` — `fromDate` is typed unlike every comparable parameter

**The document says:** `fromDate` on this endpoint is `"required": false` with schema
`{"type": "string", "format": "date"}`. Every other optional date or time parameter in
the API — `toDate` on this same endpoint, and `fromDate`/`toDate`/`fromTime`/`toTime`
elsewhere — is declared as `anyOf: [string, null]`.

**The API did:** accepted the request with `fromDate` omitted and returned 200, which is
what `"required": false` promises.

**Presumed wrong:** the document. The behaviour is right; only the type declaration is
inconsistent with its neighbours. Code generators that read the document will produce a
non-nullable parameter here and a nullable one everywhere else.

## 7. All endpoints — unknown query parameters are accepted, not rejected

**The document says:** each endpoint declares a closed set of query parameters.

**The API did:** returned 200 and a normal result set when we sent a deliberately
invented parameter name alongside valid parameters. We tried this on `/sites` and on
`/biomass`; both ignored the unknown parameter silently.

For contrast, the API does validate parameters it knows: sending `period=15min` to
`/behaviour/swimSpeed`, whose `PeriodEnum` allows only `h` and `D`, correctly returns 422
with a clear message. And `penId`, which the document marks required on all seven
endpoints that declare it, is genuinely enforced — omitting it returns 422 everywhere we
tried.

**Presumed wrong:** the API, mildly. The consequence for a consumer is that a mistyped
parameter name is indistinguishable from a correct request: send `fromDat` instead of
`fromDate` and you get 200 with the endpoint's default window, and nothing tells you the
window you asked for was ignored. Rejecting unknown parameters with 422, the way you
already reject unknown *values*, would turn a silent wrong answer into an obvious error.

We appreciate this may be deliberate, to leave room for adding parameters without
breaking older clients. If so, it is worth stating in the documentation.

**Related:** `/behaviour/breathingIndex` declares no `period` parameter, while
`/environmental` and `/behaviour/swimSpeed` both do. Sending `period` to
`/behaviour/breathingIndex` returns 200 — but given the above, that is the API ignoring
an unknown parameter rather than evidence that it is supported. We have taken the
document at its word and do not send `period` to that endpoint. Please confirm that
`/behaviour/breathingIndex` genuinely has no aggregation period, rather than an
undocumented one.

## 8. All endpoints — result ordering is not documented

**The document says:** nothing about the order of records within a response.

**The API did:** returned records grouped by pen, and within each pen ordered by time
ascending. This held on every multi-pen endpoint we read.

**Presumed wrong:** the document. This matters more than it looks, because of pagination:
a consumer who fetches a capped result set and resumes with `nextToken` cannot assume the
records arrive in global time order, so "the latest record I have seen" is not a safe
high-water mark mid-pagination. If the grouping and ordering above are a guarantee rather
than an accident of the current implementation, saying so in the documentation would let
consumers rely on it. If they are not a guarantee, that is worth saying too.

## 9. All endpoints — `nextToken` pagination could not be exercised

**The document says:** result sets are capped at 10,000 records, and a capped response
carries a `nextToken` to fetch the next batch.

**The API did:** returned no `nextToken` on any request we made. The largest single
result set we received was on the order of a few thousand records — well under the
documented cap — so this is not a contradiction. We simply never triggered pagination,
and therefore have not verified it. We deliberately kept our request windows narrow to
stay inside the hourly rate limit, which is why we did not reach the cap.

We did confirm one detail of the protocol as documented: when there is no next batch,
`nextToken` is **omitted from the response body** rather than returned as `null`. That
matches how the documentation describes the loop.

---

## Things we checked that were correct

So that this is not only a list of problems:

- Every endpoint's response envelope matched its declared wrapper schema.
- No endpoint returned any property the document does not declare, at any nesting level.
- `penId` is enforced as required exactly where the document says it is, and `all` works
  as documented on every endpoint that accepts it.
- `period` enum values are validated against exactly the values the document declares,
  including the difference between `/environmental` (which accepts `15min`) and
  `/behaviour/swimSpeed` (which does not).
- Omitting the optional date and time parameters returns the documented default window.
- On `/welfareScores`, every welfare category the `WelfareScoresDetail` schema declares
  appeared in the data at least once, and the proportions within a category always summed
  to exactly 1. Categories with no data are omitted from the object rather than returned
  as null, which conforms — the properties are not marked required — and is worth
  contrasting with finding 3, where the same style of omission applies to fields that
  *are* marked required.
- The nested `welfareScores` category objects carry `healed` only for some categories,
  which conforms: `healed` is declared but not required on `WelfareScoreDetail`.
