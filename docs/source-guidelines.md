# Source Guidelines

Every package is a neutral, reusable dlt source. Follow dlt's own conventions and best practices; where a choice is ours, stay unopinionated.

- **True to the API.** A source's only opinions are mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key/disposition defaults. Data lands as the API returns it; transforms belong to the consumer.
- **Stack-neutral core.** Depend on dlt, and beyond that on as little as the job honestly requires. Every runtime dependency is one a consumer inherits and has to resolve against their own environment, so a new one needs a reason worth writing next to it — not a ban, a bar. Destination, orchestration, secrets management, and log routing are always the consumer's choices, shown as runnable code in the package's `examples/` rather than encoded in the library.
- **Logging.** Emit on a named stdlib logger (`logging.getLogger(__name__)`); consumers attach handlers. Log only the domain events dlt cannot know about (skipped items, source-side retries, cursor decisions) — dlt already logs requests, throughput, and outcomes. On failure, raise.
