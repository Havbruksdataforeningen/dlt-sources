"""Load every Aquabyte resource into a local DuckDB file, today and every day after."""

import dlt

from dlt_source_aquabyte import aquabyte_source

# Bind nothing. The first run starts at the initial_date/initial_time in config and loads the
# whole history, split into windows the API accepts; every later run resumes from the cursor
# dlt stored, and a re-run after an interruption merges rather than duplicates.
# DuckDB is this example's choice, not the package's — swap destination= for any dlt one.
pipeline = dlt.pipeline(pipeline_name="aquabyte", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(aquabyte_source()))
