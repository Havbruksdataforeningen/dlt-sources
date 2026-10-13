# Specs

A dated copy of Elhub's own documentation of the Energy Data API, the source of truth
for this package. The API is v0, and Elhub says breaking changes may come, so the copy
is dated: when something breaks, a fresh fetch diffs against it.

| File | Source | Fetched |
|---|---|---|
| `openapi.yaml` | <https://api.elhub.no/energy-data/v0/openapi.yaml> | 2026-10-13 |
| `meta-metering-points.json` | <https://api.elhub.no/energy-data/v0/meta/metering-points> — the datasets of the metering-points entity: scopes, columns, filters and date policies | 2026-10-13 |
| `dataset-guidelines.md` | The text of <https://api.elhub.no/energy-data-api/dataset-guidelines> and the dataset notes on <https://api.elhub.no/energy-data-api/metering-points>, as rendered — the pages are a JavaScript app | 2026-10-13 |

Refresh the first two with `curl` against their URLs and run the tests. The third has to be
read out of the website. Elhub's change log and known issues:
<https://api.elhub.no/energy-data-api/change-logs> ·
<https://elhub.no/kjente-feil-i-elhubs-api/>.

`meta-metering-points.json` is the authority on what each dataset accepts; read it before
guessing at a parameter, a scope or a date window.

**Where the API and this spec disagree, the API wins.** The package is built against what
the API returns, not against what the documents say it should. What was measured is below.

## API quirks worth knowing

> **Observed against the live API on 2026-10-07 and 2026-10-13**, with the scope
> `elhub:enduser` and the dataset `METERING_VALUES_HOUR_RESTRICTED`. Re-check before
> building on one, and update this section when you do.

The ones that decide what the source does:

- **Only `METERING_VALUES_HOUR_RESTRICTED` answers `elhub:enduser`.** The day, month and
  year datasets (`METERING_VALUES_PER_DIRECTION_*_RESTRICTED`) return `403` with that scope,
  although `meta-metering-points.json` lists `end-user` among their audiences. Aggregate
  downstream.
- **There is no endpoint that lists metering points.** The dataset call without an id,
  `GET /metering-points?dataset=METERING_VALUES_HOUR_RESTRICTED`, returns every metering
  point the token reads, each with its values in the window. Without dates that window is
  the **last 24 hours counted from the request**, so a call at 13:00 holds yesterday's
  hours from 14:00 on, and nothing of today, which is not inserted yet. That call is how
  `metering_points` discovers them.
- **With an id, the whole retained history comes in one call.** `GET /metering-points/{id}`
  takes a window of up to 3 years and 41 days (`datePolicyWithId` in the metadata), and a
  three-year hourly history is one response of 26,280 values. The list call without an id
  is capped at one day (`datePolicyWithoutId`).
- **`insertDateTime` is a filter, and it is inclusive.** Sent with an id and no dates, the
  API answers with its widest window and returns every value inserted *at or after* that
  instant: an old `insertDateTime` is the whole history, the stored one is yesterday plus
  any correction. It works without an id too, inside the 24-hour window. A value inserted
  exactly at the instant is included, so a run re-fetches the boundary rows it already has.
- **Empty is `204 No Content` with no body**, not an empty list: an `insertDateTime` newer
  than the latest insert, a window with no values, a company with no metering points.
- **Yesterday's hours are inserted around 02:05 Europe/Oslo** (`insertDateTime` observed at
  02:01 to 02:04 on consecutive days, one insert per metering point per day). Schedule a
  daily load after 03:00.
- **`resolution` varies per metering point.** `PT60M` and `PT15M` both occur, so one point
  can carry 96 values a day where another carries 24. Never assume hourly rows.

Two about dates:

- **A `startDate` exactly 3 years and 41 days back is refused** with `400`; a week inside
  the limit is fine. Elhub deletes data older than that, so every day a first load waits,
  a day of history is gone. Let the API infer the start (send `insertDateTime` and no dates)
  rather than computing one at the edge.
- **`endDate` at midnight does not include the hour that starts at that midnight.** A window
  `startDate=2026-10-01T00:00:00+02:00&endDate=2026-10-03T00:00:00+02:00` returned values
  starting from `2026-10-01T00:00` to `2026-10-02T23:00` — 48 values, two whole days. The
  documentation says both ends are inclusive; in practice treat the pair as half-open on
  `startTime`. A plain `yyyy-MM-dd` is accepted as well and means midnight in Europe/Oslo
  (`startDate=2026-10-01&endDate=2026-10-03` returned the same 48 values, 2026-10-13); the
  full form is `yyyy-MM-dd'T'HH:mm:ssXXX` in Europe/Oslo and must be URL-encoded,
  which `requests` does for you.

And three about getting a request through at all:

- **`Accept` and `User-Agent` are mandatory.** A request without either is `403`, with
  no body that says why. The source sends both on every request.
- **The Maskinporten grant needs a `jti`, and `exp - iat` of at most 120 s.** Without a
  unique `jti` two grants in the same second are the same grant, and Maskinporten refuses a
  grant it has seen (`Grant has been used before`). The token's `expires_in` is set on the
  client in Digdir's self-service portal (1200 s on the one this package was verified with).
- **A delegated company is read with the `consumer_org` claim**, the organisation number of
  the company that delegated `elhub:enduser` to the client's organisation in Altinn.
  `MP-250` means Elhub has not granted the scope to that organisation; `MP-251` means the
  delegation in Altinn is missing or hit the wrong service. Which Altinn service, and how to
  delegate, is a matter for the consumer's own organisation, not for this package.
