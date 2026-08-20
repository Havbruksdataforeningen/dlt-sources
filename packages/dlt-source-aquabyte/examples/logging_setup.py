"""Route this pipeline's logs into the stack you already run, and its errors to Sentry."""

import os

import dlt

from dlt_source_aquabyte import aquabyte_source

# This package emits no log records of its own. dlt does, on the logger named `dlt`, and
# two of its INFO lines are the ones an operator wants: the window each resource bound,
# and every request it made. Everything below is dlt's own configuration — the three
# `[runtime]` keys, settable in config.toml instead of here.
# https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format

# Structured records on stderr, which is what a collector tailing the process parses —
# Datadog, Loki, CloudWatch, whichever agent you already run. Drop the format line to
# get dlt's human-readable one instead, or pass your own `{}`-style format string.
os.environ["RUNTIME__LOG_LEVEL"] = "INFO"
os.environ["RUNTIME__LOG_FORMAT"] = "JSON"

# A service that ships records itself hands you a handler instead. Attach it to the same
# logger before the run and dlt uses it — nothing else changes:
#     logging.getLogger("dlt").addHandler(YourServiceHandler())

# Errors that find you while you sleep: `pip install sentry-sdk`, set a DSN, and dlt
# reports every logged error and unhandled exception, tagged with the pipeline and the
# destination, plus a trace per run.
# os.environ["RUNTIME__SENTRY_DSN"] = "https://<key>@<org>.ingest.sentry.io/<project>"

pipeline = dlt.pipeline(pipeline_name="aquabyte_logged", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(aquabyte_source().with_resources("biomass")))
