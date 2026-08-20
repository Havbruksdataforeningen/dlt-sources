"""Bring your own logger: route dlt's log records to wherever your stack sends logs."""

import logging
import os

import dlt

from dlt_source_aquabyte import aquabyte_source

# This package emits no log records of its own. dlt does, on the logger named `dlt`, and
# two of its INFO lines are the ones an operator wants: the window each resource bound,
# and every request made. dlt adopts a handler already on that logger, so attaching one
# is the whole integration — stderr here, a file or a DataDog handler just as well. dlt
# sets the format itself; `runtime.log_format` is where you change that.
logging.getLogger("dlt").addHandler(logging.StreamHandler())

# dlt's own level defaults to WARNING, so neither line is emitted until you raise it.
# `[runtime] log_level` in config.toml does the same thing from outside the script.
os.environ["RUNTIME__LOG_LEVEL"] = "INFO"

pipeline = dlt.pipeline(pipeline_name="aquabyte_logged", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(aquabyte_source().with_resources("biomass")))
