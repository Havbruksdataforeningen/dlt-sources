# First release of a package

Loaded from [`SKILL.md`](SKILL.md) when the preflight finds the package unpublished — `https://pypi.org/pypi/<package>/json` returns `404`. Everything here happens once per package; on the next release the preflight finds a `200` and this file is never opened.

## Why this needs a human first

The release workflow authenticates with **Trusted Publishing**: PyPI accepts the upload because the workflow's identity matches a registered publisher, not because anyone holds a token. For a package that does not exist on PyPI yet, that registration is a **pending publisher**, and someone with a PyPI account must create it by hand before the first publish.

This is the one thing the preflight cannot check for you — pending publishers are visible only inside the account that created them. If it is missing, the publish fails at the very end of the release with an `invalid-publisher` error that does not explain itself, so confirm it now rather than discover it then.

## What the developer must confirm

Ask the developer to confirm, explicitly, that **both** registrations exist — TestPyPI is a separate service with its own account, and a test release publishes there:

1. A pending publisher on **pypi.org**: owner `Havbruksdataforeningen`, repository `dlt-sources`, workflow `release.yml`, environment `pypi`.
2. A pending publisher on **test.pypi.org**: same owner, repository and workflow, environment `testpypi`.

They are added under *Publishing* in the account settings of each index. A pending publisher does **not** reserve the name — the name is claimed the first time the publish actually runs — so also have the developer check the name is still free on both indexes.

## Two more things about a first release

- **A test release proves the whole chain** — tag, workflow, publisher, install — before anything lands permanently on PyPI. Say so when the offer comes up in step 4; the developer still decides.
- **The first version is whatever `pyproject.toml` already says** if the package has never been released; bump from there like any other release.

Done when the developer has explicitly confirmed both pending publishers. Then return to the preflight in [`SKILL.md`](SKILL.md) and continue.
