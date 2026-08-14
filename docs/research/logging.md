# Logging in reusable dlt source libraries

Researched 2026-08-14 against the official Python, dlt, Prefect, and Dagster docs, plus the dlt and dagster source code where the docs are thin.

## TL;DR

Use the standard Python library pattern: every module logs to `logging.getLogger(__name__)`, the package attaches a `NullHandler`, and the library never adds handlers, sets levels, or prints. Prefect and Dagster capture stdlib loggers *by name*, so a named logger plugs into both with one line of consumer config. dlt already logs request traffic, throughput, and outcomes — a source only adds the domain events dlt cannot know about.

## 1. Python best practice for libraries

Source: [Logging HOWTO — Configuring Logging for a Library](https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library).

- Use a module-level logger named `__name__` in every module.
- Attach a `NullHandler` to the top-level package logger.
- "It is strongly advised that you do not add any handlers other than `NullHandler` to your library's loggers" — handler configuration belongs to the application.
- With no configuration at all, WARNING and above still print to stderr through logging's built-in last-resort handler. The docs call this "the best default behaviour".

Consequences:

- Problems are visible on screen with zero config; INFO/DEBUG stays off until the application enables it.
- `logging.getLogger("dlt_source_aquabyte")` returns the same object everywhere, so applications configure a library's logging entirely from outside, by name — no logger object passes through the API.

## 2. What dlt gives us for free

Source: [Running in production](https://dlthub.com/docs/running-in-production/running) and the dlt-hub/dlt source code.

- **The `dlt` logger.** dlt logs to a stdlib logger named `dlt`; level via `RUNTIME__LOG_LEVEL` (default WARNING, INFO recommended in production), format via `log_format`, including JSON. Code detail (`dlt/common/logger.py`): dlt attaches its own stderr handler and sets `propagate=False`, so its logs reach stderr directly and never the root logger.
- **Request logging.** dlt's `RESTClient` logs every request at INFO and pagination detail at DEBUG on the `dlt` logger (`dlt/sources/helpers/rest_client/client.py`). `RUNTIME__LOG_LEVEL=INFO` turns it on — no source code needed.
- **Throughput.** `dlt.pipeline(..., progress="log")` prints periodic per-resource row counts and system stats to stdout ([pipeline docs](https://dlthub.com/docs/general-usage/pipeline#monitor-the-loading-progress)) — exactly what container and orchestrator log capture picks up.
- **Outcomes.** `pipeline.run()` returns `load_info`; `pipeline.last_trace` has timings and row counts per step. These are return values — the consumer logs a summary wherever they want.
- **Sentry.** Set `RUNTIME__SENTRY_DSN` (and `pip install sentry-sdk` — not a dlt dependency) and dlt sends exception traces whenever any Python logger logs an error, plus transaction traces for each `pipeline.run` with extract/normalize/load timings, tagged with pipeline and destination name ([running-in-production](https://dlthub.com/docs/running-in-production/running)). Because it hooks Python logging globally, errors from our named logger are included. Consumer opt-in; nothing for the library to do.

### What the source still logs manually

Only domain events dlt cannot see, on our named logger:

- WARNING — items the source skips or drops, and retries the source itself performs.
- INFO — per-resource start/finish summaries and incremental-cursor decisions (low volume; per-row throughput is `progress`'s job).
- DEBUG — envelope and pagination detail.
- Failures: raise. dlt fails the pipeline and the orchestrator reports it; logging the same error again is noise.

Note: dlt's own verified-sources repo tells contributors to use `from dlt.common import logger`. We deviate deliberately: that logger is a no-op outside pipeline runs, is not documented public API for third-party sources, and merges our messages into dlt's namespace so consumers cannot set our verbosity independently.

## 3. Prefect and Dagster

Both capture stdlib loggers by name — the mechanism our design keys on.

- **Prefect**: "By default, Prefect won't capture log statements from libraries that your flows and tasks use. You can tell Prefect to include logs from these libraries with the `PREFECT_LOGGING_EXTRA_LOGGERS` setting" ([logging customization](https://docs.prefect.io/v3/advanced/logging-customization)). One env var: `PREFECT_LOGGING_EXTRA_LOGGERS=dlt,dlt_source_aquabyte`. The official [dlt + Prefect walkthrough](https://dlthub.com/docs/walkthroughs/deploy-a-pipeline/deploy-with-prefect) just wraps `pipeline.run()` in a task — no logging bridge needed.
- **Dagster**: the [dagster-dlt integration](https://docs.dagster.io/integrations/libraries/dlt) runs the pipeline in-process and attaches row counts from `load_info` to asset materializations. Logs surface two ways: raw compute logs capture stdout/stderr (so `progress="log"` and dlt's stderr output land there automatically — the [official example](https://docs.dagster.io/integrations/libraries/dlt/dlt-pythonic) itself passes `progress="log"`), and `dagster.yaml` `python_logs: managed_python_loggers: [dlt_source_aquabyte, dlt]` routes named-logger records into the structured event log ([Python logging guide](https://docs.dagster.io/guides/monitor/logging/python-logging)).

## 4. The pattern for this repo

### Library (each package)

```python
# src/dlt_source_aquabyte/__init__.py
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
```

```python
# any module
import logging
logger = logging.getLogger(__name__)

logger.info("pens: fetching since cursor %s", cursor)
logger.warning("skipping frame %s: missing pen_id", frame_id)
logger.debug("page %d: %d items", page, len(items))
# failures: raise
```

No other handlers, no `setLevel`, no root-logger calls, no `print`, no logger parameters in the public API.

### Consumer examples

Everything below is application-side configuration; the library code never changes.

#### Plain Python

```python
import logging
logging.basicConfig(level=logging.INFO)   # our logger, via root
# RUNTIME__LOG_LEVEL=INFO                 # dlt internals + request logs, to stderr

pipeline = dlt.pipeline("aquabyte", destination="duckdb", progress="log")
info = pipeline.run(aquabyte_source())
```

#### Debug logging

Levels are set per logger, so DEBUG can be scoped to one package without drowning in everything else's chatter. dlt's docs recommend INFO in production and discourage DEBUG there ([running-in-production](https://dlthub.com/docs/running-in-production/running)).

```python
import logging

logging.basicConfig(level=logging.INFO)                            # baseline
logging.getLogger("dlt_source_aquabyte").setLevel(logging.DEBUG)   # our pagination/envelope detail only
# dlt internals + full request detail: export RUNTIME__LOG_LEVEL=DEBUG
# everything at once: logging.basicConfig(level=logging.DEBUG)
```

#### Prefect

Prefect captures stdlib loggers listed in `PREFECT_LOGGING_EXTRA_LOGGERS` into its API/UI ([logging customization](https://docs.prefect.io/v3/advanced/logging-customization)); `get_run_logger()` logs the run summary.

```bash
export PREFECT_LOGGING_EXTRA_LOGGERS=dlt,dlt_source_aquabyte
export RUNTIME__LOG_LEVEL=INFO
```

```python
import dlt
from prefect import flow, task
from prefect.logging import get_run_logger
from dlt_source_aquabyte import aquabyte_source

@task(retries=2)
def load_aquabyte():
    pipeline = dlt.pipeline("aquabyte", destination="duckdb", progress="log")
    info = pipeline.run(aquabyte_source())
    get_run_logger().info("aquabyte load: %s", info)

@flow
def aquabyte_flow():
    load_aquabyte()
```

#### Dagster

`managed_python_loggers` routes named-logger records into Dagster's structured event log ([Python logging guide](https://docs.dagster.io/guides/monitor/logging/python-logging)); `progress="log"` output also lands in raw compute logs via stdout.

```yaml
# dagster.yaml
python_logs:
  python_log_level: INFO
  managed_python_loggers:
    - dlt_source_aquabyte
    - dlt
```

```python
import dlt
from dagster import AssetExecutionContext
from dagster_dlt import DagsterDltResource, dlt_assets
from dlt_source_aquabyte import aquabyte_source

@dlt_assets(
    dlt_source=aquabyte_source(),
    dlt_pipeline=dlt.pipeline("aquabyte", destination="duckdb", progress="log"),
)
def aquabyte_assets(context: AssetExecutionContext, dlt_resource: DagsterDltResource):
    yield from dlt_resource.run(context=context)
```

#### Sentry (error tracking)

The SDK's logging integration is enabled by default and captures records from any stdlib logger — INFO+ as breadcrumbs, ERROR as events, honoring each logger's configured level ([Sentry logging integration](https://docs.sentry.io/platforms/python/integrations/logging/)). Alternatively dlt initializes Sentry itself from `RUNTIME__SENTRY_DSN` (§2). Either route covers our named logger.

```python
import logging
import sentry_sdk  # pip install sentry-sdk

sentry_sdk.init(dsn="https://<key>@sentry.io/<project>")
logging.basicConfig(level=logging.INFO)  # INFO+ breadcrumbs; ERROR → Sentry events
# alternative, no init call: export RUNTIME__SENTRY_DSN=https://<key>@sentry.io/<project>
```

#### Datadog, with the Agent

Datadog's standard model is agent-based: the app imports nothing from Datadog. A separate Datadog Agent process (host daemon or container sidecar) tails the app's stdout/file output and ships it to Datadog; JSON formatting lets the Agent parse levels and keep tracebacks as one event, and `ddtrace` adds trace IDs for APM users ([Python log collection](https://docs.datadoghq.com/logs/log_collection/python/)).

```python
import logging
from pythonjsonlogger.json import JsonFormatter  # pip install python-json-logger

handler = logging.StreamHandler()  # stdout; the Datadog Agent tails it
handler.setFormatter(JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler])
# dlt's own logger emits JSON too: RUNTIME__LOG_FORMAT=JSON, RUNTIME__LOG_LEVEL=INFO
```

#### Datadog, agentless (serverless)

Where no Agent can run — serverless platforms (Azure Functions, Lambda), locked-down PaaS, or hosts where you can't install software — logs are shipped in-process instead: a custom `logging.Handler` posts records to Datadog's [log-intake HTTP API](https://docs.datadoghq.com/api/latest/logs/) with `DD_API_KEY`. Attaching that handler to the named loggers is all it takes; the same setup can also route dlt's progress collector onto a logger instead of stdout (`dlt.progress.log(logger=...)`), since serverless stdout often isn't captured anywhere useful.

```python
import logging
import dlt
from datadog_api_client import ApiClient, Configuration  # pip install datadog-api-client
from datadog_api_client.v2.api.logs_api import LogsApi
from datadog_api_client.v2.model.http_log import HTTPLog
from datadog_api_client.v2.model.http_log_item import HTTPLogItem

class DatadogHandler(logging.Handler):
    def __init__(self, service: str):
        super().__init__()
        self.api = LogsApi(ApiClient(Configuration()))  # reads DD_API_KEY / DD_SITE env vars
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:
        self.api.submit_log(HTTPLog([HTTPLogItem(
            message=self.format(record), service=self.service,
            ddsource="python", status=record.levelname,
        )]))

handler = DatadogHandler(service="aquabyte")
handler.setLevel(logging.INFO)
run_logger = logging.getLogger("aquabyte_run")
for name in ("dlt_source_aquabyte", "dlt", "aquabyte_run"):
    logging.getLogger(name).addHandler(handler)

pipeline = dlt.pipeline(
    "aquabyte", destination="duckdb",
    progress=dlt.progress.log(log_period=30.0, logger=run_logger),  # progress → Datadog, not stdout
)
```

A production handler should batch records or hand them to a queue instead of one HTTP call per log line; error handling around `emit` omitted for brevity.

Sentry and Datadog overlap (both do APM/error tracking) but sit in different niches: Sentry is application error/trace monitoring; Datadog is a broad observability platform (infra metrics, log aggregation, dashboards). A source library supports both the same way — named stdlib logger, consumer wires the backend.

## Resolved questions

- **Logger names**: per-package via `__name__` (root `dlt_source_aquabyte`). It matches the import name, which is what orchestrator users will guess. No org-wide prefix.
- **dlt's runtime re-formats the first handler on the `dlt` logger** (`dlt/common/logger.py`), which could touch a Prefect handler attached first. Cosmetic only — records still flow, and it affects only the `dlt` logger, never ours. No action.
- **Routing `progress` onto a logger instead of stdout** is supported (`LogCollector(logger=...)`), but the stdout default is what compute-log capture wants; examples stay minimal and use `progress="log"` as-is.
- The dlt code paths cited were read on the `devel` branch on 2026-08-14; behavior-relevant claims are backed by the released docs above.
