# Source Guidelines

Every package is a neutral, reusable dlt source. Follow dlt's own conventions and best practices; where a choice is ours, stay unopinionated.

- **True to the API.** A source's only opinions are mechanics: auth, pagination, envelope unwrapping, incremental cursors, and overridable key/disposition defaults. Data lands as the API returns it; transforms belong to the consumer.
- **Stack-neutral core.** The library depends on dlt (plus pydantic for typing) and nothing else. Destination, orchestration, secrets management, and log routing are the consumer's choices — shown as runnable code in the package's `examples/`, not encoded in the library.
- **Logging.** Emit on a named stdlib logger (`logging.getLogger(__name__)`); consumers attach handlers. Log only the domain events dlt cannot know about (skipped items, source-side retries, cursor decisions) — dlt already logs requests, throughput, and outcomes. On failure, raise.
