# Security

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting instead: go to the [Security tab](https://github.com/Havbruksdataforeningen/dlt-sources/security/advisories/new) and report a vulnerability. Only the maintainers see it, and the report stays private until there is a fix to release.

Tell us which package and version, what an attacker can do, and how to reproduce it. You will get a first reply within a week.

## What is in scope

These packages are libraries. They hold a supplier's API credentials and talk to that supplier's API, so the realistic problems are of that kind:

- A credential reaching somewhere it should not — a log line, an exception message, a URL, a file written by the package.
- A request that skips TLS verification, or sends credentials somewhere other than the configured API.
- A dependency with a known vulnerability that a consumer inherits by installing the package.

Out of scope: how *you* store your API key, and how your destination or orchestrator is configured. Those are your stack's decisions, which these packages deliberately do not make — see [`docs/source-guidelines.md`](docs/source-guidelines.md).

## Supported versions

Only the latest released version of each package gets fixes. Versions are independent per package, so "latest" means latest of that package. There are no long-term support branches.
