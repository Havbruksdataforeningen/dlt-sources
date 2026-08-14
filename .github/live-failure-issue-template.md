---
title: Live API canary failed
labels: needs-triage
---

The nightly live-API run failed: [run {{ env.GITHUB_RUN_ID }}]({{ env.GITHUB_SERVER_URL }}/{{ env.GITHUB_REPOSITORY }}/actions/runs/{{ env.GITHUB_RUN_ID }}).

This issue is reused — it is updated rather than duplicated on each failure, so check the run link above for the current state rather than the date on this issue.

**What it means.** One of three things, in rough order of likelihood:

1. **The upstream API changed shape.** The schema-drift check compares the live response against the golden schema in `tests/schemas/`. If that is what failed, a vendor added, removed or retyped a field. Decide whether to absorb it (regenerate the golden schema) or to treat it as breaking.
2. **The upstream API is temporarily unavailable or rate-limiting.** Re-run the workflow manually before investigating further.
3. **Credentials expired.** The live tier fails loudly rather than skipping, by design.

**What it does not mean.** No consumer is broken yet — the shipped sources run under an `evolve` contract and will absorb an added field. This is an early warning, which is the entire point of it.
