# Context Map

This repository holds one context per source package, plus the shared language below. Each source package is its own context: it has its own supplier, its own glossary, and its own version. No package depends on another.

## Contexts

- [dlt-source-aquabyte](./packages/dlt-source-aquabyte/CONTEXT.md) — Aquabyte, a supplier of camera-based monitoring of farmed salmon in sea pens. Their API reports sites, pens, biomass, lice, welfare, behaviour and environment.

## Relationships

- **Package → package**: none, deliberately. Packages share conventions, not code. A term that two packages both need belongs in this file, not in a shared library.
- **Package → consumer**: a consumer installs one package from PyPI and never sees this repository. Terms below that describe the repository itself (such as workspace) are ours, not theirs.

## Shared language

These terms mean the same thing in every package.

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
