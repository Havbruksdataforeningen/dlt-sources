- Revisit `POST /superiorRate` once it leaves preview — see `docs/parameter-inventory.md`.
- Consider a `CONTEXT.md` for the package, per `docs/agents/domain.md`.

Resolved:

- ~~Remove the `_resource` suffix from resource functions.~~
- ~~Use the `pens` transformer to feed the resources that need pen IDs.~~ Decided against: the v3.1 endpoints take `penId=all` and fetch every pen in one request, so chaining them off `pens` would cost one request per pen against a 1000/hour limit and couple every resource to `/sites`. `pens` stays a transformer over `sites` for unwrapping only.
- ~~Make the incremental `initial_value` a config variable instead of repeating it.~~ `initial_date` / `initial_time` on the source.
- ~~Implement integration tests against live data.~~ `tests/test_integration.py`, run with `-m integration`.
