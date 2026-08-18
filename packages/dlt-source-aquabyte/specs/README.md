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
variants, which the spec marks `deprecated: true` and which nothing here reads — the
README says why under "What the source does not expose". The notes from that migration
were deleted once it was done; `git log` has them if the history is ever wanted.

**Where the API and this spec disagree, the API wins.** The package is built against what
the API actually returns, not against what `openapi.json` says it should. Where the two
differ in a way a consumer would notice, that goes in the package README under "API quirks
worth knowing" — a short internal note, not a bug report. Feedback for Aquabyte is sent to
them directly rather than kept here.
