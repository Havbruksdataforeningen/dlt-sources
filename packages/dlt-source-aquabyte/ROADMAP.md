- Revisit `POST /superiorRate` once it leaves preview — see "What the source does not expose" in the README.
- Consider a `CONTEXT.md` for the package, per `docs/agents/domain.md`.

Resolved:

- ~~Remove the `_resource` suffix from resource functions.~~
- ~~Use the `pens` transformer to feed the resources that need pen IDs.~~ Decided against: the v3.1 endpoints take `penId=all` and fetch every pen in one request, so chaining them off `pens` would cost one request per pen against a 1000/hour limit and couple every resource to `/sites`. `pens` stays a transformer over `sites` for unwrapping only.
- ~~Make the incremental `initial_value` a config variable instead of repeating it.~~ `initial_date` / `initial_time` on the source.
- ~~Implement integration tests against live data.~~ `tests/test_integration.py`, run with `-m integration`.
- ~~Version `sites` on its own fields only, so a pen change does not version its site.~~ Reverted before `0.1.0`. The `_site_version` digest applied [nested-JSON cost optimisation](https://dlthub.com/blog/scd2-nested-json-data-cost-optimization) where there was no cost to optimise: at 10–15 sites with 6–12 pens each and rare changes, the site-row churn it saved is a handful of rows, and in exchange the nested `pens` snapshot on the current site row went stale until a site field changed. `sites` versions on its whole record again, dlt's default. Stripping `pens` from the site record was rejected: it would break the documented `source.sites.max_table_nesting = 1` override. Reintroduce `row_version_column_name` only where a larger site or pen count makes that churn a measured cost.
