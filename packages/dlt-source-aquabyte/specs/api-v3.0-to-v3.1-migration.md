# Aquabyte API v3.0 → v3.1 Migration Guide

Reference specs: `openapi-v3.0.json` (old) and `openapi-v3.1.json` (new), both deleted
once the migration was done — read them from git history. The current spec is
`specs/openapi.json`.

## Summary

v3.1 moves all per-pen data endpoints from path-based (`/pens/{penId}/...`) to query-based (`/...?penId={penId}`), adds `nextToken` pagination, and makes `penId` a required query parameter everywhere. The old path-based endpoints are deprecated but still functional.

## Official Release Notes (from Aquabyte)

> With v3.1, we have added new APIs to support bulk fetching. One of the main use case is for user to download Aquabyte data into their own database. The new API allow us to download all pen with available data in a single call. For example, to fetch biomass data for all pens, you can use the following API call:
>
> `GET "https://api.aquabyte.ai/v3/biomass?penId=all&fromDate=2026-01-01&toDate=2026-01-02"`
>
> You can switch to v3.1 API simply by changing the URL from this pattern `GET /pens/{penId}/biomass` to this pattern `GET /biomass?penId={penId}`
>
> Since v3.1 support everything in v3.0. We recommend switching to v3.1 as soon as possible.
>
> **Result pagination:** Currently, Aquabyte Public API cap the result set up to 10,000 records. If the result set have more data than the limit, they will be returned in batches. In this case, the response will contain a `"nextToken"`. To fetch the next batch of data, repeat the request and add the `"nextToken"` to the query parameters. Repeat until `"nextToken"` is not present in the response.

### Known breaking changes not mentioned in release notes

- **`/environmental/latest` now requires `penId`** — was optional in v3.0, returns 422 without it in v3.1
- **`/biomass` now requires `fromDate`** — was optional in v3.0
- **`/behaviour/breathingIndex` removed `period` parameter** — was accepted in v3.0
- **Spelling change:** `/behavior/` → `/behaviour/` (British) in new endpoint paths

## Architecture Impact

The current source uses a **transformer pattern**: `sites → pens → per-pen transformers`. Each transformer receives a single pen dict and makes one API call per pen. In v3.1, all data endpoints support `penId=all` to fetch data for all pens in a single call. This opens the door to eliminating per-pen iteration entirely — but that is a **separate design decision**, not part of this migration.

**This migration should focus on switching to the new endpoint URLs while preserving the current transformer architecture.** The `penId=all` bulk-fetching optimization can be evaluated later.

---

## Endpoint URL Changes

Every per-pen resource in `aquabyte.py` needs its URL updated. The `penId` moves from a path segment to a query parameter.

| Resource | Old URL | New URL | `penId` |
|---|---|---|---|
| `environmental` | `/pens/{penId}/environmental` | `/environmental` | query param (required) |
| `biomass` | `/pens/{penId}/biomass` | `/biomass` | query param (required) |
| `harvest_report` | `/pens/{penId}/biomass/harvestReport` | `/biomass/harvestReport` | query param (required) |
| `lice_count` | `/pens/{penId}/liceCount` | `/liceCount` | query param (required) |
| `swim_speed` | `/pens/{penId}/behavior/swimSpeed` | `/behaviour/swimSpeed` | query param (required) |
| `breathing_index` | `/pens/{penId}/behavior/breathingIndex` | `/behaviour/breathingIndex` | query param (required) |
| `welfare_scores` | `/pens/{penId}/welfareScores` | `/welfareScores` | query param (required) |

**Note the spelling change:** `/behavior/` → `/behaviour/` (British spelling) for swim_speed and breathing_index.

### Example transformation

```python
# BEFORE (v3.0)
yield from client.paginate(f"/pens/{pen_id}/biomass", params=params, data_selector="biomass")

# AFTER (v3.1)
params["penId"] = pen_id
yield from client.paginate("/biomass", params=params, data_selector="biomass")
```

For every transformer: extract `pen_id = pen["id"]`, add `params["penId"] = pen_id`, and change the URL to the new flat path.

---

## `environmental_latest` — Now Requires `penId`

**Breaking change.** `penId` was optional in v3.0, is **required** in v3.1.

Current code (standalone `@dlt.resource`):
```python
@dlt.resource(write_disposition="replace", columns=EnvironmentalDataLive)
def environmental_latest(pen_id: str | None = None):
    params: dict[str, str] = {}
    if pen_id is not None:
        params["penId"] = pen_id
    yield from client.paginate("/environmental/latest", params=params, data_selector="data")
```

**Required change:** Must always pass `penId`. Two options:
1. Convert to a transformer (fed from `pens`), fetching per-pen — consistent with other resources
2. Pass `penId=all` to get all pens in one call — simpler but different pattern

Either way, `penId` can no longer be omitted.

---

## `nextToken` Pagination

v3.1 responses are capped at **10,000 records** and include an optional `nextToken` field for fetching the next page. This affects all data endpoints:

- `/environmental`
- `/biomass`
- `/liceCount`
- `/behaviour/swimSpeed`
- `/behaviour/breathingIndex`
- `/welfareScores`

**Does NOT affect:** `/sites`, `/sites/{siteId}`, `/environmental/latest`, `/biomass/harvestReport`.

### Current state

The source uses `SinglePagePaginator` because v3.0 returned full results. This must change to handle `nextToken`.

### Implementation

dlt's RESTClient supports custom paginators. A `nextToken`-based paginator needs to:
1. Read `nextToken` from the response JSON
2. If present, include it as a query parameter in the next request
3. Stop when `nextToken` is `null` or absent

The `nextToken` field is at the **top level** of the response (sibling to the data array), not inside the data array. Example response structure:

```json
{
  "biomass": [...],
  "nextToken": "abc123"
}
```

**Note:** The `SinglePagePaginator` can remain for endpoints that don't paginate (`/sites`, `/environmental/latest`, `/biomass/harvestReport`). Only the 6 data endpoints above need the new paginator.

---

## Parameter Changes

### `breathing_index`: `period` parameter removed

The new `/behaviour/breathingIndex` endpoint **no longer accepts** a `period` query parameter. The current code passes `behavior_period`:

```python
params: dict[str, str] = {"period": behavior_period}
```

**Remove** the `period` parameter for `breathing_index`. The `swim_speed` endpoint still accepts `period`.

### `biomass`: `fromDate` now required

In v3.0 `fromDate` was optional (defaulting to 7 days before `toDate`). In v3.1 it is **required**. The current code already passes `fromDate` via incremental loading, so this should not break — but verify that `fromDate` is always included in the params.

### `harvest_report`: `fromDate` now optional

In v3.0 `fromDate` was required. In v3.1 it is **optional** (defaults to 7 days before `toDate`). No code change needed — the current code already handles it gracefully.

---

## Schema Changes

### `EnvironmentalDataPoint` gains `penId` field

In v3.1, the `EnvironmentalDataPoint` schema includes a **required** `penId` field. The current code manually injects `penId` into each record:

```python
for record in page:
    record["penId"] = pen_id
```

With v3.1, the API returns `penId` on each record natively. **This manual injection can be removed** from the `environmental` transformer.

Update `schemas.py` to add `penId: str` to the `EnvironmentalDataPoint` model (if not already present).

### Response wrapper schemas renamed

The response wrapper schemas have been renamed (e.g., `BiomassDailyResponse` → `Wrapped__2`), but the **inner data models are unchanged**:

- `EnvironmentalDataPoint` — unchanged (plus `penId` addition)
- `BiomassDailyModel` — unchanged
- `LiceCount` — unchanged
- `BehaviorSwimSpeed` — unchanged
- `BehaviorBreathingIndex` — unchanged
- `WelfareScoresRecord` — unchanged
- `BiomassHarvestReport` — unchanged
- `EnvironmentalDataLive` — unchanged
- `Site`, `Pen` — unchanged

**No changes needed** to Pydantic models in `schemas.py` (except adding `penId` to `EnvironmentalDataPoint`).

---

## Unchanged Endpoints

These endpoints are identical between v3.0 and v3.1:

| Endpoint | Notes |
|---|---|
| `GET /sites` | No changes |
| `GET /sites/{siteId}` | No changes |
| `GET /environmental/latest` | `penId` now required (see above), but URL and response schema unchanged |

---

## Files to Modify

| File | Changes |
|---|---|
| `src/dlt_source_aquabyte/aquabyte.py` | URL updates, `penId` as query param, `nextToken` paginator, `breathing_index` drops `period`, `environmental_latest` requires `penId`, remove manual `penId` injection in `environmental` |
| `src/dlt_source_aquabyte/schemas.py` | Add `penId: str` to `EnvironmentalDataPoint` |
| `tests/test_*.py` | Update mock URLs and response structures to match new endpoints |
| `tests/mock_responses/` | Update mock JSON if response structure changed |
| `tests/test_integration.py` | Should pass as-is once source code is updated |

---

## Migration Checklist

1. [ ] Add `nextToken` paginator class (or use dlt built-in if available)
2. [ ] Update `environmental` URL: `/pens/{penId}/environmental` → `/environmental?penId={penId}`
3. [ ] Update `biomass` URL: `/pens/{penId}/biomass` → `/biomass?penId={penId}`
4. [ ] Update `harvest_report` URL: `/pens/{penId}/biomass/harvestReport` → `/biomass/harvestReport?penId={penId}`
5. [ ] Update `lice_count` URL: `/pens/{penId}/liceCount` → `/liceCount?penId={penId}`
6. [ ] Update `swim_speed` URL: `/pens/{penId}/behavior/swimSpeed` → `/behaviour/swimSpeed?penId={penId}`
7. [ ] Update `breathing_index` URL: `/pens/{penId}/behavior/breathingIndex` → `/behaviour/breathingIndex?penId={penId}`
8. [ ] Update `welfare_scores` URL: `/pens/{penId}/welfareScores` → `/welfareScores?penId={penId}`
9. [ ] Remove `period` param from `breathing_index`
10. [ ] Fix `environmental_latest` to always pass `penId` (convert to transformer or use `penId=all`)
11. [ ] Remove manual `penId` injection from `environmental` transformer (API now returns it)
12. [ ] Add `penId: str` to `EnvironmentalDataPoint` in `schemas.py`
13. [ ] Use `nextToken` paginator for the 6 paginated endpoints
14. [ ] Keep `SinglePagePaginator` for `/sites`, `/environmental/latest`, `/biomass/harvestReport`
15. [ ] Update unit tests (mock URLs, response shapes)
16. [ ] Run quality gates: ruff, pyright, unit tests
17. [ ] Run integration tests to verify against live API
