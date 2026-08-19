# The Python version floor for these source packages

**Keep `requires-python = ">=3.11"`.** Researched 2026-08-14 against the CPython devguide, the PyPA packaging specifications and each runtime vendor's own documentation; condensed 2026-08-20, with the full survey in `git log`.

## Why 3.11

Two facts set a library's floor: whether upstream still patches the interpreter, and whether consumers can still get it. Everything else — how old the release feels, what syntax we would gain — is a proxy or a nicety.

- **Below 3.11 is dead or dying.** 3.9 went end-of-life on 2025-10-31, and dlt declares `>=3.10` anyway. Python 3.10 reaches end-of-life in October 2026 — a floor declared in August 2026 that expires eight weeks later is one we would have to undo within the quarter.
- **Above 3.11 costs member companies their upgrade path.** Databricks Runtime 15.4 LTS ships Python 3.11.11 and is supported until 2027-08-19. DBR jumps straight from 3.11 to 3.12 at 16.4 LTS, so a `>=3.12` floor would make these packages uninstallable on a runtime Databricks itself still supports — on a platform Norwegian enterprise data teams commonly run, where the Python version is frozen for the cluster's three-year life.
- **And it would buy this code nothing.** Nothing in `src/` would be written differently on 3.12, 3.13 or 3.14: no generics for PEP 695 to simplify, no forward references to defer, one f-string in the whole package. The source waits on HTTP, so there is no performance argument either.

Sources: [Status of Python versions](https://devguide.python.org/versions/) and the [DBR 15.4 LTS system environment](https://docs.databricks.com/aws/en/release-notes/runtime/15.4lts).

## What the dependencies allow

dlt is the binding one. It raised its own floor at 1.29.0, from `>=3.9.2` to `>=3.10`, and 1.30.0 declares `>=3.10,<3.15`. Our 3.11 sits one minor version above what dlt permits — not stranding anyone dlt itself would serve, not inheriting a dead interpreter.

Do **not** mirror dlt's `<3.15` ceiling. PyPA cautions against upper bounds because they "can cause different errors and version conflicts"; dlt's own cap already protects the install, and a copy in our metadata would only make these packages harder to unblock the day dlt lifts it.

## The trap that makes a conservative floor worth it

When a project raises its floor, pip does not error on an older interpreter — "it will attempt to install the last package distribution that supported that Python runtime". A member company still on 3.11 would get no failure. They would get the last 3.11-compatible release, silently and indefinitely, and stop receiving fixes without noticing.

For a library consumed by teams who did not choose its floor, that is a far worse outcome than being one version conservative. The same guide gives the operational rule: **a floor bump ships alone**, no features bundled in, so consumers can see it in the changelog.

Source: [Dropping support for older Python versions](https://packaging.python.org/en/latest/guides/dropping-older-python-versions/).

## Where the floor is asserted

| Setting | Value | Why it is there |
|---|---|---|
| `project.requires-python` | `>=3.11` | the claim itself |
| `[tool.pyright] pythonVersion` | `"3.11"` | unset, pyright checks against the developer's own interpreter — the wrong default for a library |
| `[tool.ruff] target-version` | `"py311"` | ruff would infer this from `requires-python`; explicit is fine, disagreeing is not |
| CI matrix | `["3.11", "3.14"]` | the floor proves the claim is honest; the newest version dlt supports proves the package survives the current stdlib and PEP 649 |

A future bump moves all four together. `uv sync` respects `requires-python`, so a matrix entry below the floor fails visibly rather than drifting out of agreement with the metadata.

## When to raise it

Both conditions, not either:

1. Python 3.11 is at or past upstream end-of-life (approximately October 2027), **and**
2. no long-lived pinned runtime a member company plausibly runs still ships 3.11.

They expire together: DBR 15.4 LTS ends 2027-08-19, AWS Lambda deprecates `python3.11` on 2027-06-30, Azure Functions and Google Cloud Run functions end 3.11 support in October 2027, and CPython's own end-of-life is around then too. So the next move is a single bump to `>=3.12`, shipped alone, around **2027 Q4**.

Do not bump on the [SPEC 0](https://scientific-python.org/specs/spec-0000/) calendar, which would have dropped 3.11 in October 2025. Its three-year rule exists to bound CI matrices and per-interpreter binary-wheel builds for compiled scientific packages; this is pure Python with a two-job matrix, so SPEC 0 optimises a cost we do not carry while charging one we do.

Re-check this document whenever dlt raises its own floor. That is the real forcing function — we cannot support an interpreter our main dependency has abandoned.
