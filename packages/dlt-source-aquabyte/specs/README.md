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

- **`behaviour_swim_speed` and `behaviour_breathing_index` return timestamps with no time
  zone** (`2026-01-10T00:00:00`), where `environmental` returns the same kind of field with
  a `Z`. The source does not rewrite them — they land as sent. Treat them as UTC, which is
  what the zoned endpoints use.
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

- **The window has a maximum width, per endpoint and per grain, and the spec names none of
  it.** A wider request is refused — `400 Requested time range is larger than N days` — not
  truncated. Measured live on 2026-08-27 by sending a deliberately oversized window, which
  makes the API state its own cap; the two narrow ones were then confirmed inclusive by
  bisection (7 days `200`, 8 days `400`; 31 days `200`, 32 days `400`).

  | Endpoint | `period` | Max window |
  |---|---|---|
  | `/environmental` | `15min` | **7 days** |
  | `/environmental` | `h` | **31 days** |
  | `/environmental` | `D`, omitted | 366 days |
  | `/behaviour/swimSpeed` | `h` | **31 days** |
  | `/behaviour/swimSpeed` | `D`, omitted | 366 days |
  | `/behaviour/breathingIndex` | `D`, omitted | 366 days |
  | `/biomass`, `/liceCount`, `/welfareScores`, `/biomass/harvestReport` | — | 366 days |

  Two things make this worse than it looks. The cap applies to an **open-ended** window too,
  measured from `fromTime` to today — so it is not only a backfill concern, and the finer the
  grain the shorter the outage a daily pipeline survives. And the cap follows the *grain*, so
  choosing the finest `period` — the right default for a raw layer — buys the shortest cap.
  The source splits its own windows to stay inside them; the numbers live in
  `MAX_WINDOW_DAYS`. (2026-08-27.)

And one that bites when you are debugging rather than reading:

- **dlt hides the `detail` that says which of these you hit.** `http_show_error_body`
  defaults to `False`, so a refusal reaches your logs as `400 Client Error: Bad Request for
  url: ...` and nothing else — indistinguishable from a window too wide, a `welfareScores`
  date floor, or a bad parameter. Set `RUNTIME__HTTP_SHOW_ERROR_BODY=true` before debugging
  anything against this API.

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
  on, not ignored as an unknown name would be. The grain is therefore fixed, which is why
  the resource is keyed on `penId` + `fromTime` without `toTime`. Reported upstream in #29.
  (2026-08-20.)

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
