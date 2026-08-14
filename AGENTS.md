# dlt-sources

## Source guidelines

Every package is a neutral, reusable dlt source. Follow dlt's own conventions and best practices; where a choice is ours, stay unopinionated.

- **True to the API.** A source's only opinions are mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key/disposition defaults. Data lands as the API returns it; transforms belong to the consumer.
- **Stack-neutral core.** The library depends on dlt alone. Destination, orchestration, secrets management, and log routing are the consumer's choices — shown as runnable code in the package's `examples/`, not encoded in the library.
- **Logging.** Emit on a named stdlib logger (`logging.getLogger(__name__)`); consumers attach handlers. Log only the domain events dlt cannot know about (skipped items, source-side retries, cursor decisions) — dlt already logs requests, throughput, and outcomes. On failure, raise.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`havbruksdataforeningen/dlt-sources`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context: root `CONTEXT-MAP.md` (shared terms) + `CONTEXT.md` per package. See `docs/agents/domain.md`.
