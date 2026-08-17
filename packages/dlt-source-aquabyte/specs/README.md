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

`api-v3.0-to-v3.1-migration.md` records a migration that is done; the specs it
references were deleted and live in git history.

`api-observations-2026-08-17.md` is what a live run found when every response was
compared against `openapi.json` field by field. It is written **for Aquabyte's
developers**, not for this repo — send it to them as it stands. It deliberately contains
no data: field names, types and HTTP status codes only, because it leaves the building.
A later comparison gets its own dated file rather than overwriting this one.
