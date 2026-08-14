# Parameter inventory

Every endpoint and query parameter in `specs/openapi-v3.1.1.json` (Aquabyte API v3.1),
and what this package does with it. Nothing is left unaccounted for: a parameter is
either exposed on a resource or omitted on purpose, with the reason stated.

`tests/test_param_surface.py` reads the same spec file and asserts each resource's
signature against it, so this table cannot quietly drift out of date.

## Resources and their parameters

Python arguments are snake_case; the query param sent is the API's own camelCase name.
Every resource also takes `params: dict | None`, merged into the query string last —
the escape hatch for a query param the API grows after this release, and the reason a
new parameter never requires a new release.

| Endpoint | Resource | Parameter | Exposed as | Notes |
|---|---|---|---|---|
| `GET /sites` | `sites` | `siteId` | `site_id` | Optional filter; omit for every site. |
| `GET /sites/{siteId}` | `site_by_id` | `siteId` (path) | `site_id` | Standalone resource, not part of `aquabyte_source`. |
| `GET /environmental` | `environmental` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromTime` | `from_time` | Defaults to the incremental cursor on `fromTime`. |
| | | `toTime` | `to_time` | Omitted → API default (today). |
| | | `period` | `period` | `"15min"`, `"h"`, `"D"`. Omitted → API default (`"D"`). |
| | | `nextToken` | — | Pagination mechanics; see below. |
| `GET /environmental/latest` | `environmental_latest` | `penId` | `pen_id` | Defaults to `"all"`. |
| `GET /biomass` | `biomass` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromDate` | `from_date` | Defaults to the incremental cursor on `date`. |
| | | `toDate` | `to_date` | Omitted → API default (today). |
| | | `bucketSize` | `bucket_size` | `weightDist` bucket size in grams. Omitted → API default (1000). |
| | | `nextToken` | — | Pagination mechanics; see below. |
| `GET /biomass/harvestReport` | `harvest_report` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromDate` | `from_date` | Defaults to the incremental cursor on `slaughterStartDate`. |
| | | `toDate` | `to_date` | Omitted → API default (today). |
| `GET /liceCount` | `lice_count` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromDate` | `from_date` | Defaults to the incremental cursor on `date`. |
| | | `toDate` | `to_date` | Omitted → API default (today). |
| | | `nextToken` | — | Pagination mechanics; see below. |
| `GET /behaviour/swimSpeed` | `behaviour_swim_speed` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromTime` | `from_time` | Defaults to the incremental cursor on `fromTime`. |
| | | `toTime` | `to_time` | Omitted → API default (today). |
| | | `period` | `period` | `"h"` or `"D"` — no `15min` here, unlike `/environmental`. Omitted → API default (`"D"`). |
| | | `nextToken` | — | Pagination mechanics; see below. |
| `GET /behaviour/breathingIndex` | `behaviour_breathing_index` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromTime` | `from_time` | Defaults to the incremental cursor on `fromTime`. |
| | | `toTime` | `to_time` | Omitted → API default (today). |
| | | `nextToken` | — | Pagination mechanics; see below. |
| `GET /welfareScores` | `welfare_scores` | `penId` | `pen_id` | Defaults to `"all"`. |
| | | `fromDate` | `from_date` | Defaults to the incremental cursor on `date`. |
| | | `toDate` | `to_date` | Omitted → API default (today). |
| | | `nextToken` | — | Pagination mechanics; see below. |

The spec documents no `period` on `/behaviour/breathingIndex`, so the resource offers
none — a difference from `/behaviour/swimSpeed` that is easy to assume away.

`pens` has no parameters of its own: it is a transformer over the `sites` response,
unwrapping the pens the API nests inside each site.

## Consciously omitted

**`nextToken`, on all six endpoints that document it** — `/environmental`, `/biomass`,
`/liceCount`, `/behaviour/swimSpeed`, `/behaviour/breathingIndex` and `/welfareScores`.
It is pagination mechanics, owned by dlt's `JSONResponseCursorPaginator`, which reads
`nextToken` from each response and sends it on the next request until it is absent.
Exposing it would let a caller break their own pagination.

The other four read endpoints — `/sites`, `/sites/{siteId}`, `/environmental/latest`
and `/biomass/harvestReport` — return no `nextToken` at all, so their resources read a
single page (`SinglePagePaginator`) rather than hoping a cursor paginator terminates.

**The eight `/pens/{penId}/…` path variants** — `/pens/{penId}/environmental`,
`/pens/{penId}/environmental/latest`, `/pens/{penId}/biomass`,
`/pens/{penId}/biomass/harvestReport`, `/pens/{penId}/liceCount`,
`/pens/{penId}/behavior/swimSpeed`, `/pens/{penId}/behavior/breathingIndex` and
`/pens/{penId}/welfareScores`. These are the v3.0 shape of the same data; v3.1 replaced
them with `?penId=` on the flat endpoints, and the spec's own migration note recommends
the flat form. None of them accepts a `nextToken` query param either, so a result set
past the API's 10,000-record cap cannot be paged through — and `penId=all` fetches every
pen in one request where the path variants need one per pen, which matters against a
1000 requests/hour limit. To read one pen, bind `pen_id="pen-abc"`; to read several,
bind a list and the resource issues one request per pen id.

**`POST /superiorRate`** — not implemented. The spec marks it "(Experimental API) …
subject to change", and it is a POST computation rather than a read endpoint. Its
`penId`/`fromDate`/`toDate` params are therefore unimplemented along with it. Worth
revisiting once it leaves preview.

## Not parameters, but worth stating

- **Auth** — `apikey` request header on every call, from `dlt.secrets`.
- **Base URL** — `https://api.aquabyte.ai/v3/`, from `dlt.config`.
- **Rate limit** — 1000 requests/hour, per the spec's overview. The package does not
  throttle; a consumer close to the limit should prefer `penId="all"` over per-pen
  fan-out.
- **Result cap** — the API caps a result set at 10,000 records and paginates beyond
  that with `nextToken`.
