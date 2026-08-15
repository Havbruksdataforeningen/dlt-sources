# Aquabyte Public API

To use our API you must be issued an API key.

Instructions: For all HTTPS requests you will need to pass in your API key as part of the header: apikey: {API_KEY}

Our base url is https://api.aquabyte.ai/v3/

Requests are limited to 1000 requests/hour

## `openapi.json`

The source of truth for this package. `tests/test_param_surface.py` asserts each
resource's signature against it, so the published parameter surface cannot drift from
the spec.

| | |
|---|---|
| Fetched from | <https://api.aquabyte.ai/v3/openapi.json> |
| `info.version` | `v3.1` |
| Fetched on | 2026-08-15 |

Refresh it by overwriting this file from that URL and running the tests — the filename
stays put so `git log -p specs/openapi.json` reads as a history of the API's own
changes. Earlier snapshots (`openapi-v3.0.json`, `openapi-v3.1.json` and a hand-edited
`openapi-v3.1.1.json` that documented a `/sites` `siteId` query param the API does not
have) were deleted; they remain in git history.
