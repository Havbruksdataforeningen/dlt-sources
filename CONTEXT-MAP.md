# Context Map

This repository holds one context per source package, plus the shared language below. Each source package is its own context: it has its own supplier, its own glossary, and its own version. No package depends on another.

## Contexts

- [dlt-source-aquabyte](./packages/dlt-source-aquabyte/CONTEXT.md) — the Aquabyte API v3: sites, pens, biomass, lice, welfare, behaviour and environment.

## Relationships

- **Package → package**: none, deliberately. Packages share conventions, not code. A term that two packages both need belongs in this file, not in a shared library.
- **Package → consumer**: a consumer installs one package from PyPI and never sees this repository. Terms below that describe the repository itself (workspace, rehearsal) are ours, not theirs.

## Shared language

These terms mean the same thing in every package.

### The packages themselves

**Source package**:
One installable distribution that reads one supplier's API. The unit of versioning and release.
_Avoid_: connector, integration, module

**Source**:
The dlt source function a package exposes. The entry point a consumer calls.
_Avoid_: client, adapter

**Resource**:
One dlt resource inside a source, normally corresponding to one API endpoint and producing one table.
_Avoid_: stream, endpoint, feed

**Consumer**:
The person or team that installs a source package and runs it in their own pipeline. Not us.
_Avoid_: user, client, customer

**Member company**:
A member of Havbruksdataforeningen. The reason a package exists, and the most common kind of consumer.

**Workspace**:
The uv workspace at the repository root. It exists for us. It is invisible to a consumer.
_Avoid_: monorepo (when referring to the buildable unit)

**Mechanics**:
The concerns a source package is permitted to have an opinion about: authentication, pagination, envelope unwrapping, incremental cursors, and overridable key and write-disposition defaults. Everything else belongs to the consumer.

### Data shape and change

**Envelope unwrapping**:
Taking the records out of the wrapper object a supplier returns, so the consumer receives records rather than the wrapper.

**Incremental cursor**:
The field a resource uses to ask the supplier for only what is new since the last run.

**Drift**:
A change a supplier makes to their API that alters the shape of the data we receive. The primary risk this repository is built to detect.
_Avoid_: breakage, schema change (too broad — a change we make is not drift)

**Golden schema**:
The committed dlt schema for a resource, held in the package's `tests/schemas/`. It records the shape we agreed to. Both test tiers compare against it.
_Avoid_: snapshot, baseline

**Schema contract**:
The dlt setting that decides what happens when incoming data does not match the schema. We use two of its modes: **evolve** in released packages, so a new supplier field cannot stop a consumer's pipeline, and **freeze** in the live tier, so the same field produces a failure we can see.

### Testing and release

**Unit tier**:
The tests in `tests/unit/`. They never use the network. They run on every pull request.
_Avoid_: integration test (ambiguous across the industry — it usually still means offline)

**Live tier**:
The tests in `tests/live/`. They use the real supplier API. They never run on a pull request.
_Avoid_: integration test, e2e, smoke test

**Rehearsal**:
A release to TestPyPI, using a pre-release version, done to check a release before the real one. Each rehearsal needs its own version number.
_Avoid_: dry run (nothing is simulated — it is a real publish to a different index)
