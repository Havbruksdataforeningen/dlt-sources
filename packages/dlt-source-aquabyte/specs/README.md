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
them: records land as sent, so these reach whoever reads the data. The two that change how
you read it:

- **`behaviour_swim_speed` and `behaviour_breathing_index` return timestamps with no time
  zone** (`2026-01-10T00:00:00`), where `environmental` returns the same kind of field with
  a `Z`. The source does not rewrite them — they land as sent. Treat them as UTC, which is
  what the zoned endpoints use.
- **`lice_count` omits its five count fields entirely on a zero-sample record**, rather than
  sending nulls. Those columns are typed by the source's column hints and land as `NULL`, so `sampleSize = 0`
  is the condition to filter on, not `adultFemale IS NULL`.

And one that bites when you are debugging rather than reading:

- **The API ignores a query parameter it does not recognise instead of rejecting it.**
  Verified by sending an invented parameter name, which returned `200` and a normal result
  set. So a mistyped parameter is indistinguishable from a correct request — send `fromDat`
  instead of `fromDate` and you get the endpoint's own default window with nothing to tell
  you the window you asked for was dropped. Invalid *values* are rejected properly
  (`period=15min` on an endpoint allowing only `h` and `D` returns `422`); it is only unknown
  *names* that pass silently. This is also why `/behaviour/breathingIndex` accepting a
  `period` it does not document is no evidence that it supports one.

### Identifiers

Which key to use depends on what you are joining to, and the answer is different inside
and outside this dataset.

**Joining Aquabyte data to Aquabyte data: use `id`.** Every data endpoint stamps its
records with `penId`, and that value is the `id` on the pen — verified live, and asserted
by `test_full_pipeline_with_live_pens`. So `pens.id = biomass.pen_id` and so on, and there
is no alternative: `penCode` does not appear on the data endpoints at all.

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
