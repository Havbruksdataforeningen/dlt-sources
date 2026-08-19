- Revisit `POST /superiorRate` once it leaves preview — see "What the source does not expose" in the README.
- Consider a `CONTEXT.md` for the package, per `docs/agents/domain.md`.

Resolved:

- ~~Remove the `_resource` suffix from resource functions.~~
- ~~Use the `pens` transformer to feed the resources that need pen IDs.~~ Decided against: the v3.1 endpoints take `penId=all` and fetch every pen in one request, so chaining them off `pens` would cost one request per pen against a 1000/hour limit and couple every resource to `/sites`. `pens` stays a transformer over `sites` for unwrapping only.
- ~~Make the incremental `initial_value` a config variable instead of repeating it.~~ `initial_date` / `initial_time` on the source.
- ~~Implement integration tests against live data.~~ `tests/test_integration.py`, run with `-m integration`.
- ~~Version `sites` on its own fields only, so a pen change does not version its site.~~ Reverted before `0.1.0`. The `_site_version` digest bought a storage saving and paid in correctness: the nested `pens` snapshot on the current site row froze until one of the site's own fields changed, silently, and `source.sites.max_table_nesting = 1` materialised that stale snapshot as rows. `sites` versions on its whole record again, dlt's default. The rejected alternative was stripping `pens` from the site record, which would break that documented override. Decided at 10–15 sites, 6–12 pens each, changes rare — where the extra site versions cost nothing. Reintroduce a `row_version_column_name` only where a larger site or pen count makes that churn a measured cost.
