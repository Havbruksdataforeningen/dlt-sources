# Releasing

> **Not wired up yet.** A concrete workflow sketch exists in
> [Ingest-Barentswatch#20](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/pull/20);
> it moves here if/when [#12](https://github.com/Havbruksdataforeningen/Ingest-Barentswatch/issues/12)
> is decided in favour of this layout.

The short version:

- Versions are independent per package; a tag names the package it releases.
- `dlt-source-aquabyte/v0.2.0` → build that package, publish to PyPI (after a
  maintainer approves the run).
- `dlt-source-aquabyte/v0.2.0-rc1` → same build, publish to TestPyPI for rehearsal.
- PyPI Trusted Publishing throughout — no tokens stored as secrets; one publisher
  registration per package, distinguished by GitHub environment name.
