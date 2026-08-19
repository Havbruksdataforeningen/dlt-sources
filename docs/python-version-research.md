# The Python version floor for these source packages

Researched 2026-08-14 against the CPython devguide and release PEPs, the PyPA packaging specifications, the dependencies' own installed metadata and PyPI records, and each runtime vendor's own documentation — plus local experiments on 3.9 and 3.10 interpreters where the answer had to be measured rather than read.

## TL;DR

Keep `requires-python = ">=3.11"`. It is the lowest floor that is not already dead upstream — 3.10 reaches end-of-life in October 2026, two months from now — and simultaneously the highest floor that does not lock out the long-lived managed runtimes our member companies actually run on. Going lower is pointless (3.9 is EOL and the code does not even import there); going higher buys this codebase essentially nothing, because nothing in `src/` would be written differently on 3.12, 3.13 or 3.14. Raise the floor to `>=3.12` when Databricks Runtime 15.4 LTS goes out of support on 2027-08-19, which is also roughly when Python 3.11 itself goes EOL — one move, both reasons.

> **Update, 2026-08-20.** `schemas.py` and the `pydantic` dependency were removed in #18; column types now come from plain dlt column hints. The measurements below were taken before that and are left as recorded. Two of them read differently now: the package no longer needs its annotations evaluated at runtime (§4, PEP 649), and the 3.9 import failure is `aquabyte.py`'s own PEP 604 unions rather than the models'. The verdict is unchanged — `PenId = str | list[str]` and every `str | None` parameter still make the source 3.10-clean and no lower.

## 1. CPython release and support lifecycle

Source: [Status of Python versions — Python Developer's Guide](https://devguide.python.org/versions/), with per-release schedules in [PEP 619 (3.10)](https://peps.python.org/pep-0619/), [PEP 664 (3.11)](https://peps.python.org/pep-0664/), [PEP 693 (3.12)](https://peps.python.org/pep-0693/), [PEP 719 (3.13)](https://peps.python.org/pep-0719/), [PEP 745 (3.14)](https://peps.python.org/pep-0745/) and [PEP 790 (3.15)](https://peps.python.org/pep-0790/).

Every version gets roughly 18 months of bugfix releases, then security-only source releases until five years after its `.0`. As of 2026-08-14:

| Version | Schedule PEP | First release | Status today | End of life |
|---|---|---|---|---|
| 3.9 | PEP 596 | 2020-10-05 | end-of-life | 2025-10-31 |
| 3.10 | PEP 619 | 2021-10-04 | security-only | 2026-10 (~2 months away) |
| 3.11 | PEP 664 | 2022-10-24 | security-only | 2027-10 |
| 3.12 | PEP 693 | 2023-10-02 | security-only | 2028-10 |
| 3.13 | PEP 719 | 2024-10-07 | bugfix | 2029-10 |
| 3.14 | PEP 745 | 2025-10-07 | bugfix | 2030-10 |
| 3.15 | PEP 790 | 2026-10-01 (planned) | prerelease | 2031-10 |

Two facts drive everything below.

- **3.9 is gone.** It went end-of-life on 2025-10-31. No security fixes are being issued; nobody should be building a new data platform on it.
- **3.10 is about to go.** PEP 619: "it is expected that security updates (source only) will be released until 5 years after the release of 3.10 final, so until approximately October 2026." A floor of `>=3.10` chosen today would be obsolete before the first package release is a quarter old.

By contrast, 3.11 — the version this repo already requires — was released 2022-10-24 and is supported until approximately October 2027. It is old in wall-clock terms and *still has fourteen months of upstream security support left*. "Released in October 2022" is not by itself an argument against it; the EOL date is the fact that matters.

## 2. What the dependencies allow

Source: the installed distribution metadata in this repo's `.venv`, plus the [PyPI JSON API](https://pypi.org/pypi/dlt/json) records for individual dlt releases.

Read from `.venv` on 2026-08-14:

| Distribution | Version | `Requires-Python` |
|---|---|---|
| dlt | 1.30.0 | `>=3.10,<3.15` |
| pydantic | 2.13.4 | `>=3.9` |
| pydantic-core | 2.46.4 | `>=3.9` |
| requests | 2.34.2 | `>=3.10` |
| duckdb (dev extra) | 1.5.5 | `>=3.10.0` |
| pytest (dev) | 9.1.1 | `>=3.10` |

dlt 1.30.0 also publishes `Programming Language :: Python :: 3.10` through `3.14` classifiers — so 3.10–3.14 is dlt's own declared support window, and dlt caps the *ceiling* at `<3.15`.

dlt raised its own floor recently, and the PyPI record shows exactly when:

- dlt 1.28.0 — `>=3.9.2,<3.15`
- dlt 1.29.0 — `>=3.10,<3.15`
- dlt 1.30.0 — `>=3.10,<3.15`

So the hard lower bound from the dependency graph is **3.10** (dlt), and pydantic imposes nothing above 3.9. Our floor of 3.11 sits exactly one minor version above what dlt permits — close enough that we are not stranding anyone dlt itself would serve, and not so low that we inherit a dead interpreter.

The ceiling is worth noting too: because dlt declares `<3.15`, these packages cannot usefully be installed on 3.15 when it ships in October 2026 regardless of what we declare. We should *not* mirror that cap ourselves (see §6 on upper bounds) — it is dlt's constraint to enforce, and the resolver will enforce it.

## 3. Where this code actually runs — the constraint that actually binds

These are libraries. Member companies install them into data platforms we do not control, so the floor is set by the *oldest Python those platforms still offer*, not by what is convenient for us. All figures below are as of 2026-08-14.

### Orchestrators

Source: each project's own published distribution metadata, via the PyPI JSON API ([`prefect`](https://pypi.org/pypi/prefect/json), [`dagster`](https://pypi.org/pypi/dagster/json), [`apache-airflow`](https://pypi.org/pypi/apache-airflow/json)).

| Project | Latest release | `Requires-Python` | Released |
|---|---|---|---|
| Prefect | 3.8.3 | `>=3.10,<3.15` | 2026-08-13 |
| Dagster | 1.13.17 | `>=3.10,<3.15` | 2026-08-07 |
| Apache Airflow | 3.3.1 | `>=3.10,!=3.15` | 2026-08-12 |

All three still support 3.10 — none of them would be blocked by a 3.11 floor, and all three would still install alongside us on 3.11. Note also that all three cap at `<3.15` / `!=3.15`, the same ceiling dlt has.

### Managed compute

**Databricks Runtime** — the decisive one, and the reason the answer is 3.11 rather than 3.12.

Source: [Databricks Runtime release notes versions and compatibility](https://docs.databricks.com/aws/en/release-notes/runtime/) plus the per-release "System environment" sections for [17.3 LTS](https://docs.databricks.com/aws/en/release-notes/runtime/17.3lts), [16.4 LTS](https://docs.databricks.com/aws/en/release-notes/runtime/16.4lts), [15.4 LTS](https://docs.databricks.com/aws/en/release-notes/runtime/15.4lts) and [14.3 LTS](https://docs.databricks.com/aws/en/release-notes/runtime/14.3lts).

| DBR | Released | End of support | Python |
|---|---|---|---|
| 19 | 2026-06-15 | TBD at LTS transition | — |
| 18 LTS | 2026-06-10 | 2029-06-10 | — |
| 17.3 LTS | 2025-10-22 | 2028-10-22 | 3.12.3 |
| 16.4 LTS | 2025-05-09 | 2028-05-09 | 3.12.3 |
| **15.4 LTS** | 2024-08-19 | **2027-08-19** | **3.11.11** |
| **14.3 LTS** | 2024-02-01 | **2027-02-01** | **3.10.12** |
| 13.3 LTS | 2023-08-22 | 2026-08-22 (~1 week away) | — |

Databricks LTS runtimes get three years of support, and the Python they ship is frozen for that whole period — a team on an LTS cluster cannot upgrade Python without migrating the cluster. Note where the boundary falls: DBR jumps straight from 3.11 (15.4 LTS) to 3.12 (16.4 LTS), so *every supported DBR older than 16.4 is on 3.11 or below*. **DBR 15.4 LTS ships Python 3.11.11 and is supported until 2027-08-19.** That is a full year from now, on a platform Norwegian enterprise data teams commonly run. A `>=3.12` floor would make these packages uninstallable on a Databricks runtime that Databricks itself still supports — and per §6 the affected team would not even see an error, just a frozen old version.

DBR 14.3 LTS (Python 3.10.12) is supported until 2027-02-01, which *outlives* Python 3.10's own upstream EOL of October 2026. That is not a reason to floor at 3.10 — we should not aim a new library at an interpreter CPython has stopped patching — but it is worth knowing that 3.10 does not vanish from the field the moment upstream drops it.

**Snowflake Snowpark for Python.** Source: [Setting up your development environment for Snowpark Python](https://docs.snowflake.com/en/developer-guide/snowpark/python/setup). Generally available on 3.10, 3.11, 3.12 and 3.13, with 3.14 in preview; 3.9 is deprecated. 3.11 is comfortably inside the GA window.

**AWS Lambda.** Source: [Lambda runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html). Supported Python runtimes and their forecast deprecation dates: `python3.10` — Oct 31, 2026; `python3.11` — Jun 30, 2027; `python3.12` — Oct 31, 2028; `python3.13` and `python3.14` — Jun 30, 2029. `python3.9` was deprecated Dec 15, 2025. AWS's own stated policy is to "deprecate a runtime when any major component of the runtime reaches the end of community long-term support" — i.e. it tracks the same CPython EOL dates §1 is built on.

**Azure Functions.** Source: [Supported languages in Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/supported-languages). Python versions and expected end-of-support: 3.10 — October 2026; 3.11 — October 2027; 3.12 — October 2028; 3.13 — October 2029; 3.14 — October 2030. All are GA. Again, Microsoft's dates are CPython's dates.

**Google Cloud Run functions.** Source: [Runtime support](https://docs.cloud.google.com/functions/docs/runtime-support). Python 3.10 deprecates 2026-10-04 (decommission 2027-04-04); 3.11 deprecates 2027-10-24 (decommission 2028-04-24); 3.12 deprecates 2028-10-02; 3.13 and 3.14 later still. Python 3.9 was decommissioned 2026-04-05, so it is already gone.

### What this adds up to

Every serverless vendor pegs its Python support to CPython's own EOL calendar, so for them "floor at 3.11" and "floor at whatever CPython still supports" are the same statement. The one place they diverge is **long-lived pinned runtimes** — Databricks LTS above all — where a customer's Python version is frozen by their platform choice for three years and cannot be changed without a cluster migration. That is where a library's floor does real damage, and it is exactly where 3.11 is still live.

## 4. What raising the floor would buy this code

Sources: [What's New in Python 3.12](https://docs.python.org/3/whatsnew/3.12.html), [3.13](https://docs.python.org/3/whatsnew/3.13.html), [3.14](https://docs.python.org/3/whatsnew/3.14.html).

The honest answer for `packages/dlt-source-aquabyte/src/` — 335 lines in `aquabyte.py`, 143 in `schemas.py`, 6 in `__init__.py` — is **almost nothing**. Feature by feature, against the code that actually exists:

**PEP 695 type-parameter syntax and `type` aliases (3.12).** The source declares no generics at all — no `TypeVar`, no generic class or function. The only type alias is `PenId = str | list[str]` (`aquabyte.py`), which would become `type PenId = str | list[str]`. The documented benefit is lazy evaluation: "The value of type aliases and the bound and constraints of type variables created through this syntax are evaluated only on demand … This means type aliases are able to refer to other types defined later in the file." `PenId` refers to two builtins. There is no forward reference to defer. **Gain: cosmetic only.** There is a small *cost*: `type` aliases are `TypeAliasType` objects, not plain unions, which is a worse fit for a docstring-carrying public name.

**PEP 692 `TypedDict` for `**kwargs` (3.12).** The source has no `**kwargs` function whose keys are a fixed known set. `_query(extra=None, **named: Any)` (`aquabyte.py`) is deliberately open-ended — its whole job is to accept arbitrary named query params and drop the unset ones — and the `params: dict[str, Any] | None` escape hatch exists precisely so that query params this release has never heard of can be passed through. Typing either as a `TypedDict` would contradict the source's stated design ("carry query params this release does not know about"). `_paginate_per_pen` forwards a fixed set of arguments to `client.paginate`, whose signature is dlt's, not ours. **Gain: zero, and arguably negative.**

**PEP 701 f-string relaxations (3.12).** "Expression components inside f-strings can now be any valid Python expression, including strings reusing the same quote as the containing f-string, multi-line expressions, comments, backslashes …". `src/` contains exactly one f-string — `f"/sites/{site_id}"` (`aquabyte.py`). It does not reuse quotes, nest, span lines, or need a backslash. Every log call uses `%`-style lazy formatting by design (see `docs/logging-research.md`), so f-strings are actively rare here. **Gain: zero.**

**PEP 649/749 deferred annotations (3.14).** In 3.14, "the annotations on functions, classes, and modules are no longer evaluated eagerly. Instead, annotations are stored in special-purpose annotate functions and evaluated only when necessary", and "it is no longer necessary to enclose annotations in strings if they contain forward references." This repo deliberately removed `from __future__ import annotations` in commit `8578535` — and PEP 649 is the reason that removal is safe long-term rather than merely tolerable. But it changes nothing for us today, for two reasons. First, the source has no forward references, so eager evaluation costs nothing but a negligible import-time union construction. Second, and more importantly, **this package needs its annotations evaluated**: dlt reads the pydantic models in `schemas.py` at runtime to derive column types (`columns=Site`, `columns=BiomassDailyModel`, …), and pydantic must resolve `str | None` to a real type object to build a validator. PEP 649 makes annotations lazy, not absent — pydantic still triggers evaluation. The `from __future__ import annotations` *string* semantics would actively have been the wrong choice here; PEP 649 simply confirms the removal was right. **Gain: zero today; vindication of an existing decision.**

**`except*` / `ExceptionGroup` (3.11 — already available).** Not used, and there is no place for it: the source's error policy is to raise and let dlt fail the pipeline (see `docs/logging-research.md` §2). No concurrent fan-out collects multiple failures — `_paginate_per_pen` iterates pen ids sequentially. **Gain: zero, and already in the floor anyway.**

**`tomllib` (3.11 — already available).** The package parses no TOML. dlt owns config-file reading (`.dlt/config.toml`, `.dlt/secrets.toml`). **Gain: zero.**

**Free-threading (3.13 experimental, 3.14 officially supported).** 3.13 shipped it as an experimental separate build with "a substantial single-threaded performance hit"; 3.14 declares "PEP 779: Free-threaded Python is officially supported" with "a performance penalty on single-threaded code in free-threaded mode … now roughly 5-10%." This is a pure-Python package with no C extension and no threading of its own — free-threading is a property of the interpreter build, not of `requires-python`, and a consumer who wants a free-threaded build can already use one. **Gain: zero. Not a reason to raise a floor.**

**Performance.** The published claims are real but aimed elsewhere. 3.12: comprehension inlining "speeds up execution of a comprehension by up to two times"; `isinstance()` against runtime-checkable protocols "a speed up of between two and 20 times"; asyncio "some benchmarks showing a 75% speed up". 3.14: the tail-calling interpreter shows "a geometric mean of 3-5% faster on the standard pyperformance benchmark suite". This source's wall-clock time is HTTP round-trips to `api.aquabyte.ai` plus dlt's normalize/load, none of it in our comprehensions. The one arguably-relevant number is the *earlier* jump: 3.11 is "between 10-60% faster than Python 3.10. On average, we measured a 1.25x speedup" ([What's New in 3.11](https://docs.python.org/3/whatsnew/3.11.html)) — an argument for not dropping *to* 3.10, not for climbing past 3.11.

**Typing niceties.** `@typing.override` (3.12), PEP 696 type-parameter defaults and PEP 742 `TypeIs` (3.13) are all irrelevant here: no inheritance beyond `AquabyteModel(BaseModel)` with no method overrides, no generics, no type guards. Note also that `typing.Self`, `assert_type`, `LiteralString`, `Required`/`NotRequired` all landed in **3.11** and are therefore already available under the current floor — unused, but available.

## 5. What lowering the floor would cost

Sources: [What's New in Python 3.10 — PEP 604](https://docs.python.org/3/whatsnew/3.10.html) and [What's New in Python 3.11 — `datetime.UTC`](https://docs.python.org/3/whatsnew/3.11.html); measured locally on 2026-08-14 with `uv run --isolated --no-project --python 3.10` and `--python 3.9`.

### Lowering to 3.10: one line

The library source is already 3.10-clean. Verified by running it on a real 3.10.20 interpreter with dlt and pydantic installed:

```
3.10.20 (main, Jun 23 2026, 15:45:03) [Clang 22.1.3 ]
import OK ['aquabyte_source', 'site_by_id']
PenId str | list[str]
schemas OK id='1' name='x' governmentSiteNumber=None external_site_id=None pens=[]
```

`PenId = str | list[str]` at module scope and every `str | None` annotation in `schemas.py` are PEP 604 unions, which work at runtime from **3.10** onward, not 3.11 — "Python 3.10+" per What's New in 3.10. `dict[str, Any]` and `list[Pen]` are PEP 585 builtin generics, 3.9+. Nothing in `src/` needs 3.11.

The single 3.11-only construct in the whole package is in the tests:

- `packages/dlt-source-aquabyte/tests/test_integration.py:9` — `from datetime import UTC, datetime, timedelta`
- `packages/dlt-source-aquabyte/tests/test_integration.py:39` — `_NOW = datetime.now(tz=UTC)`

`datetime.UTC` is "a convenience alias for `datetime.timezone.utc`" added in 3.11. On 3.10 this breaks the whole suite at *collection* time, not just when integration tests run — `pytest -m "not integration"` still imports every test module:

```
tests/test_integration.py:9: in <module>
    from datetime import UTC, datetime, timedelta
E   ImportError: cannot import name 'UTC' from 'datetime'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Cost of supporting 3.10: rewrite two lines to `from datetime import datetime, timedelta, timezone` / `datetime.now(tz=timezone.utc)`. That is the entire technical cost. **The reason not to do it is §1, not §5**: 3.10 dies in October 2026.

### Lowering to 3.9: impossible

Two independent blockers, both measured:

1. **The code does not import.** On 3.9.6: `import FAILED: TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`. PEP 604 unions are evaluated at class-body and `def` time (this repo has no `from __future__ import annotations` to string-ify them), so `schemas.py` raises before a single model is built. Making it work would mean reverting to `Optional[str]` / `Union[str, List[str]]` throughout `schemas.py` and `aquabyte.py` — a real, ugly, permanent tax.
2. **dlt refuses.** dlt 1.29.0+ declares `>=3.10`. The 3.9 experiment silently back-solved to **dlt 1.28.0** (`>=3.9.2`) — an older, unsupported dlt, which is exactly the failure mode described in §6.

3.9 has been end-of-life since 2025-10-31. There is no case for it.

## 6. Packaging semantics of `requires-python`

Sources: [Core metadata specifications — `Requires-Python`](https://packaging.python.org/en/latest/specifications/core-metadata/#requires-python) and [Dropping support for older Python versions](https://packaging.python.org/en/latest/guides/dropping-older-python-versions/).

What the field is: "This field specifies the Python version(s) that the distribution is compatible with. Installation tools may look at this when picking which version of a project to install." It takes a version specifier and — unlike most metadata fields — "cannot be followed by an environment marker."

What installers do with it: "Metadata 1.2+ installers, such as Pip, will adhere to this specification by matching the current Python runtime and comparing it with the required version in the package metadata." Support landed in pip 9.0 and later.

**The consequence that matters for a published package.** When a project raises its floor in a new release, an installer on an older interpreter does not error — "it will attempt to install the last package distribution that supported that Python runtime." So if we ship `dlt-source-aquabyte` 0.5.0 with `>=3.11` and later ship 1.0.0 with `>=3.12`, a member company still on 3.11 does not get a loud failure. They get **0.5.0, silently, indefinitely**, and stop receiving bug fixes without noticing. That is a far worse outcome for a library consumed by teams who did not choose its floor than a floor that is one version conservative.

This is not theoretical: it is precisely what happened in the 3.9 experiment in §5, where the resolver quietly served dlt 1.28.0 instead of 1.30.0.

Two operational rules follow from the same guide:

- "Give each version compatibility change its own release" — a floor bump ships alone, no features bundled in, so consumers can see it in the changelog.
- Do not add an upper bound. The guide "cautions against adding upper bounds to version ranges, as this 'can cause different errors and version conflicts'." dlt's `<3.15` cap already protects the install; duplicating it in our metadata would only make our packages harder to unblock the day dlt lifts it.

## 7. Prevailing convention in this ecosystem

Source: the [PyPI JSON API](https://pypi.org/pypi/dlt/json) records for each project's latest release, read 2026-08-14; [dlt's own `pyproject.toml`](https://github.com/dlt-hub/dlt/blob/master/pyproject.toml) and [`test_common.yml` workflow](https://github.com/dlt-hub/dlt/blob/master/.github/workflows/test_common.yml).

| Distribution | Latest | `Requires-Python` | Released |
|---|---|---|---|
| dlt | 1.30.0 | `>=3.10,<3.15` | (installed here) |
| pydantic | 2.13.4 | `>=3.9` | (installed here) |
| dbt-core | 1.12.2 | `>=3.10` | 2026-08-12 |
| pyarrow | 25.0.1 | `>=3.10` | 2026-08-10 |
| SQLAlchemy | 2.0.52 | `>=3.7` | 2026-08-11 |
| pandas | 3.0.5 | `>=3.11` | 2026-07-22 |
| numpy | 2.5.2 | `>=3.12` | 2026-08-09 |
| Prefect | 3.8.3 | `>=3.10,<3.15` | 2026-08-13 |
| Dagster | 1.13.17 | `>=3.10,<3.15` | 2026-08-07 |
| Apache Airflow | 3.3.1 | `>=3.10,!=3.15` | 2026-08-12 |

The clustering is unmistakable: **the data-engineering half of this list sits at `>=3.10`** (dlt, dbt-core, pyarrow, Prefect, Dagster, Airflow), pandas sits at `>=3.11`, and only numpy — the origin of the NEP 29 convention — is at `>=3.12`. SQLAlchemy at `>=3.7` is the outlier in the other direction, a deliberately conservative posture for a library embedded in everything.

Our `>=3.11` therefore sits *above* the median of the tools these packages will be installed next to, and level with pandas. It is not a lax floor.

**dlt itself.** `requires-python = ">=3.10, <3.15"` in its repo, matching the published metadata. More telling is what dlt actually tests: its `test_common.yml` matrix runs Linux jobs on **3.10, 3.11, 3.12, 3.13 and 3.14**, plus a `linux-lowest-direct-3.11` job pinning minimum direct dependencies. dlt does not merely declare 3.10 — it verifies it on every commit.

**Third-party `dlt-source-*` packages on PyPI.** The two published examples found — [`dlt-source-notion` 0.0.10](https://pypi.org/pypi/dlt-source-notion/json) and [`dlt-source-personio` 0.0.4](https://pypi.org/pypi/dlt-source-personio/json) — both declare `>=3.12`. This is the one data point that points the other way, and it is weak: two packages, both early-version, both plausibly from the same template, and neither serving a fleet of member companies with pinned managed runtimes. A convention set by two 0.0.x packages does not outweigh the runtime evidence in §3.

**SPEC 0 / NEP 29.** Source: [SPEC 0 — Minimum Supported Dependencies](https://scientific-python.org/specs/spec-0000/), which "builds on [NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html)" rather than superseding it. The rule: "Support for Python versions be dropped **3 years** after their initial release." Its published drop schedule puts **Python 3.11 in 2025 Q4 (drop date 2025-10-23)** and 3.12 in 2026 Q4 — so SPEC 0, applied literally, would say our floor should already be `>=3.12`, moving to `>=3.13` in about two months.

We should not follow it here, and the spec's own stated rationale says why: it exists because "limiting tested dependency combinations decreases CI complexity and code complication, freeing developer resources". That is a compelling trade for numpy, scipy and scikit-learn — projects that build binary wheels across a matrix of Python versions, OSes and architectures, and whose C extensions genuinely have to be recompiled per interpreter. This is a pure-Python package with two runtime dependencies, no compiled code, no wheels to build per version, and a two-job CI matrix. SPEC 0's cost side is essentially zero for us, so its 3-year rule optimizes a burden we do not carry, while its benefit side — locking out member companies on pinned runtimes — is a cost we *do* carry. The relevant window here is CPython's own five-year EOL, not the ecosystem's three-year convenience window.

## 8. The CI question

Source: the repo's own [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

CI currently pins a single interpreter:

```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
```

A declared floor that is never tested at the floor is a guess, and a declared floor that is only *ever* tested at the floor is worse — it is the ceiling that breaks first, since 3.12+ removes deprecated stdlib surface (3.13 alone dropped 19 "dead battery" modules per PEP 594) and 3.14 changes annotation semantics wholesale.

Recommendation: a two-point matrix — **the floor and the newest version dlt supports**.

```yaml
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.14"]
```

with `python-version: ${{ matrix.python-version }}` in the `setup-python` step. Two jobs, not four: the floor proves `>=3.11` is honest, and 3.14 proves the package survives PEP 649 deferred annotations and the current stdlib. 3.12 and 3.13 are interpolation between two tested endpoints for a pure-Python package with no version-conditional code — not worth doubling the bill. Add 3.15 to the matrix when dlt lifts its `<3.15` cap.

Note that `uv sync` respects `requires-python`, so a matrix entry below the floor fails immediately and visibly — the matrix cannot silently drift out of agreement with the metadata.

## Recommendation

**(a) The floor: keep `requires-python = ">=3.11"`. Change nothing in the repo's metadata.**

`>=3.11` is already correct, and it is correct for reasons, not by luck:

- Everything below it is dead or dying. 3.9 went EOL 2025-10-31, and the package genuinely does not import there (§5). 3.10 reaches EOL in October 2026 — declaring a floor in August 2026 that expires in October 2026 would be a mistake we would have to undo within the quarter.
- Everything above it costs consumers reach and buys this code nothing. §4 walks every candidate feature from 3.12, 3.13 and 3.14 against the actual 638 lines in `src/` and finds no gain that is more than cosmetic. There is no performance argument either: this source waits on HTTP.

**(b) Is a version released in October 2022 reasonable to require? Yes — and the release date is the wrong question.**

The question a library floor answers is not "how old does this feel" but "who am I locking out, and is upstream still fixing their security bugs". On both counts 3.11 is comfortable today: CPython supports it until approximately October 2027, and Databricks Runtime 15.4 LTS — a supported, current-until-2027-08-19 platform that a Norwegian aquaculture data team may well be sitting on — ships Python 3.11.11 and cannot be moved off it without a cluster migration. Azure Functions, AWS Lambda and Cloud Run functions all still list 3.11 as supported, on schedules that track CPython's.

Age is only a proxy for those two facts, and it is a bad proxy. What makes a Python version unusable as a floor is that upstream stopped patching it or that consumers can no longer get it — not its birthday. October 2022 sounds old; the operative fact is that 3.11 has fourteen months of upstream security support and a year of Databricks LTS ahead of it. By the same test, 3.10 — only one year older — is *not* acceptable, because it dies in eight weeks.

The trade-off stated plainly: holding at 3.11 costs us the 3.12+ syntax sugar in §4, which for this codebase is one `type` keyword we do not need. Moving to 3.12 would cost member companies on 3.11-based managed runtimes their upgrade path — and per §6 they would not even get an error, just a silently frozen old version. That asymmetry is the whole argument. For a library, an unnecessary floor bump is a bug you ship to other people's pipelines.

**When to raise it next.** Use a two-condition rule, and raise only when both are met:

1. Python 3.11 is at or past upstream EOL (approximately 2027-10, §1), **and**
2. no long-lived pinned runtime a member company plausibly runs still ships 3.11.

The dates line up unusually neatly. Databricks Runtime 15.4 LTS — the newest DBR on 3.11 — goes out of support 2027-08-19; AWS Lambda deprecates `python3.11` on 2027-06-30; Azure Functions and Google Cloud Run functions both end 3.11 support in October 2027; and CPython's own 3.11 EOL is approximately October 2027. **Everything expires within four months of each other in the second half of 2027**, so the next move is a single bump to `>=3.12`, shipped alone, around **2027 Q4**. Do not bump on the SPEC 0 calendar, which would have had us drop 3.11 in October 2025 — SPEC 0's three-year window exists to bound CI matrices and binary-wheel builds for compiled scientific packages, and this is a pure-Python package with two dependencies and a two-job matrix. Re-check this document, rather than acting on the calendar alone, whenever dlt raises its own floor: dlt going to `>=3.12` would be a genuine forcing function, since we cannot support an interpreter our only real dependency has abandoned.

**What to change in the repo.** The floor decision requires no changes — `requires-python = ">=3.11"`, `[tool.pyright] pythonVersion = "3.11"` and `[tool.ruff] target-version = "py311"` are already consistent with each other and with the recommendation. Two optional cleanups, neither urgent:

- **CI matrix** (§8): add 3.14 alongside 3.11 in `.github/workflows/ci.yml`. This is the one change worth making, because it is the only one that converts a claim into a tested fact.
- **Redundant tool settings**: Ruff infers its target from `project.requires-python` when `target-version` is unset — the docs recommend exactly that, "as it's based on Python packaging standards" ([Ruff settings](https://docs.astral.sh/ruff/settings/#target-version)). Pyright, by contrast, falls back to "the version of the current python interpreter, if one is present" when `pythonVersion` is unspecified ([Pyright configuration](https://microsoft.github.io/pyright/#/configuration)), which is exactly the wrong default for a library — a developer on 3.14 would silently type-check against 3.14. So: dropping `[tool.ruff] target-version` removes a value that can drift out of sync with `requires-python`, while `[tool.pyright] pythonVersion = "3.11"` should stay pinned. Keeping both explicit is also defensible; what is not defensible is letting either disagree with `requires-python`, which is the thing to check on any future bump.
