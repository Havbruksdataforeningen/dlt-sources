"""Route the package's log records to wherever your stack already sends logs."""

import logging

import dlt

from dlt_source_aquabyte import aquabyte_source

# The package logs on the named logger `dlt_source_aquabyte` and installs no handlers of
# its own, so this is the whole integration — stderr here, a file or syslog just as well.
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
logger = logging.getLogger("dlt_source_aquabyte")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

source = aquabyte_source()
source.biomass.bind(from_date="2026-01-01")  # overriding the cursor is logged at INFO

pipeline = dlt.pipeline(pipeline_name="aquabyte_logged", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(source.with_resources("biomass")))
