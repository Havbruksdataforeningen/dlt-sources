"""Load every metering point and its values into a local DuckDB file, today and every day after."""

import dlt

from dlt_source_elhub import elhub_source

# Bind nothing. A metering point the pipeline has not seen before is loaded with everything
# Elhub retains, in one request; every later run asks each point for what was inserted since
# its own cursor, which is yesterday's hours and any correction. A scheduler calls this on a
# timer, after 03:00 Europe/Oslo, when yesterday is in.
# DuckDB is this example's choice, not the package's — swap destination= for any dlt one.
pipeline = dlt.pipeline(pipeline_name="elhub", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(elhub_source()))
