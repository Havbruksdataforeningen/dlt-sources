# Specs

`openapi.json` is the Aquabyte API's own OpenAPI document, and the source of truth for
this package. Everything about the API itself — auth, base URL, rate limit, the
`nextToken` pagination protocol, what changed in v3.1 — is in there, most of it under
`info.description`.

| | |
|---|---|
| Fetched from | <https://api.aquabyte.ai/v3/openapi.json> |
| `info.version` | `v3.1` |
| Fetched on | 2026-08-15 |

Refresh it by overwriting the file from that URL and running the tests —
`tests/test_param_surface.py` asserts every resource's signature against it. The
filename stays put, so `git log -p specs/openapi.json` reads as a history of the API's
own changes.

This package targets v3.1 only. The v3.0 endpoints are the `/pens/{penId}/…` path
variants, which the spec marks `deprecated: true` and which nothing here reads — `REFERENCE.md`
says why under "What the source does not expose". The notes from that migration
were deleted once it was done; `git log` has them if the history is ever wanted.

**Where the API and this spec disagree, the API wins.** The package is built against what
the API actually returns, not against what `openapi.json` says it should. The differences
found so far are below. They are short internal notes, not a bug report: feedback for
Aquabyte is sent to them directly rather than kept here.

## API quirks worth knowing

> **Observed against the live API on 2026-08-17.** Aquabyte have been told about these, so
> any of them may have been fixed since. Re-check before building on one, and update this
> section — and the fixtures that model it — when you do.

The API does a few things `openapi.json` does not describe. The source does not paper over
them: records land as sent, so these reach whoever reads the data. The ones that change how
you read it:

- ~~**`behaviour_swim_speed` and `behaviour_breathing_index` return timestamps with no time
  zone**~~ — **fixed by Aquabyte, verified live 2026-08-31.** Both now send `Z`
  (`2026-08-30T00:00:00Z`), matching `environmental`. Kept here because consumers who
  normalised around the old form should know it is gone, and because a stored cursor written
  before the fix is a zoneless string sitting next to zoned ones. Drop this entry once no
  live table still holds the old spelling.
- **`lice_count` omits its five count fields entirely on a zero-sample record**, rather than
  sending nulls. Those columns are typed by the source's column hints and land as `NULL`, so `sampleSize = 0`
  is the condition to filter on, not `adultFemale IS NULL`.
- **`biomass.weightDist` spans only the weights observed, which `openapi.json` does not say.**
  `interval` holds each bucket's **lower** edge, starts at `0`, and stops at the bucket
  holding the heaviest fish in the pen — nothing pads it to a fixed maximum, so the bucket
  count follows the population as much as `bucketSize` does. A pen of smolt returns one or
  two buckets; a pen averaging 4.7 kg at `bucketSize=250` returns thirty-seven.
  `distribution` holds shares summing to 1, one per edge, and any bucket in the range — the
  first included — can be `0`. Both arrays can be empty. (2026-08-20.)

Two the source normally keeps away from you. It measures every window, splits one wider than
the window cap, and always sends an end. Two requests escape that: one carries a window you
put in `params`, which the source sends on unchanged, and one carries a cursor value the
source cannot read as a date or a time, which it warns about and sends as a single request,
with no end. Know both quirks for those:

- **A window has a maximum width, per endpoint and per granularity.** A wider request is refused
  (`400 ... is larger than N days`), not truncated — and a request that sends no end is
  measured from its start to the start of the current UTC day, the quirk below, so this hits
  daily loads as well as backfills. The finer the granularity, the shorter the window cap. Nothing about it is in
  `openapi.json`.

  | Endpoint | `period` | Max window |
  |---|---|---|
  | `/environmental` | `15min` | **7 days** |
  | `/environmental` | `h` | **31 days** |
  | `/behaviour/swimSpeed` | `h` | **31 days** |
  | every endpoint at `D` or omitted | | 366 days |

  **The window cap is on `to - from`, not on the dates covered.** So a legal `toDate` window
  covers one more calendar date than the cap allows days, and a `toTime` window covers
  exactly as many, `toTime` being exclusive. All ten (endpoint, `period`) pairs bisected live on 2026-08-28: N returns
  `200` and N+1 returns `400`, every time. The source splits its own windows to fit.

  Two things for anyone re-probing this. The error text differs by endpoint — `Requested
  **date** range` on the date endpoints, `Requested **time** range` on the `fromTime` ones —
  so parse both if you read N out of it. And send a single `penId`: the window cap is checked before
  any data is fetched, so a refusal is instant, while a legal 366-day `/environmental` window
  at `penId=all` does not return inside 180 s. The pen does not change the verdict.

- **A request that sends no `toTime`/`toDate` is served up to the start of the current UTC
  day**, not up to the request time. Today's data is never in the answer, however late in the
  day you ask. The API echoes the window it chose, which is the only thing that makes this
  visible. Two requests three seconds apart, both sent at 11:29 UTC on 2026-08-27:

  ```text
  GET /v3/environmental?penId=all&fromTime=2026-08-26T00:00:00Z&period=15min
  → "toTime":"2026-08-27T00:00:00Z"     newest bucket 2026-08-26T23:45Z

  GET /v3/environmental?penId=all&fromTime=2026-08-26T00:00:00Z&toTime=2026-08-27T11:29:50Z&period=15min
  → "toTime":"2026-08-27T11:29:50Z"     newest bucket 2026-08-27T11:15Z
  ```

  The lag depends on the UTC date the job runs on, not the local date its schedule is written
  in: a 01:20 Europe/Oslo cron runs at 23:20 on the previous UTC date, so it loads data two
  days old, with no error and no missing rows to show for it. (2026-08-27.)

One the source leaves to you, because only you know how far back you meant to go:

- **`/welfareScores` refuses any window starting before 2024-04-20**, with
  `400 Welfare data is not available for dates before April 20, 2024` — a refusal, not an
  empty result. So an `initial_date` older than that fails `welfare_scores` on every run,
  while the six other resources load normally, and no amount of window splitting helps: the
  floor is on the start date itself. Set the resource's own `incremental_date` no earlier
  than the floor. (2026-08-20.)

And one that bites when you are debugging rather than reading:

- **The API ignores a query parameter it does not recognise instead of rejecting it.**
  Verified by sending an invented parameter name, which returned `200` and a normal result
  set. So a mistyped parameter is indistinguishable from a correct request — send `fromDat`
  instead of `fromDate` and you get the endpoint's own default window with nothing to tell
  you the window you asked for was dropped. Invalid *values* are rejected properly
  (`period=15min` on an endpoint allowing only `h` and `D` returns `422`); it is only unknown
  *names* that pass silently.

- **`/behaviour/breathingIndex` takes a `period` its OpenAPI document does not list, and
  allows only the daily one.** `period=h` returns `400 period must be daily` and
  `period=15min` a `422` naming the `h`/`D` enum — so the parameter is recognised and acted
  on, not ignored as an unknown name would be. The granularity is therefore fixed, which is why
  the resource is keyed on `penId` + `fromTime` without `toTime`. Reported upstream in #29.
  (2026-08-20.)

- **dlt hides the `detail` that says which limit you hit.** `http_show_error_body` defaults
  to `False`, so a refusal reaches your logs as `400 Client Error: Bad Request` and nothing
  more. Set `RUNTIME__HTTP_SHOW_ERROR_BODY=true` before debugging against this API.

### Identifiers

Which key to use depends on what you are joining to, and the answer is different inside
and outside this dataset.

**Joining Aquabyte data to Aquabyte data: use `id`.** Every data endpoint stamps its
records with `penId`, and that value is the `id` on the pen — verified live. So a pen's
`id`, read off the site record it is nested in, joins to `biomass.pen_id` and so on, and
there is no alternative: `penCode` does not appear on the data endpoints at all.

**Joining Aquabyte data to your own systems: `penCode` is the best available today.**
`pen.id` is Aquabyte's internal auto-increment key. It is stable within their system, which
is what makes it right for the join above, but it means nothing in anyone else's — no
system of yours knows it. `penCode` is the operator-set label, so it is the only field that
carries across. Know what you are relying on: the format is the operator's choice rather
than anything the API defines, so it is a business key by convention, not by guarantee, and
a label derived from a site name can move if that site is renamed.

For sites, `governmentSiteNumber` is the equivalent and a stronger one, being externally
assigned rather than chosen locally. It was present and non-null on every site.

**The fields meant for exactly this — `external_site_id` on a site and `external_id` on a
pen — came back empty.** Both are declared by the API, both are absent from every response,
and both land as `NULL`. They carry a customer's own identifiers for a third-party system,
so an empty column most likely means the account has not populated them rather than
anything being wrong. If they get filled in, they become the right answer to the second
question above and `penCode` stops having to serve.
