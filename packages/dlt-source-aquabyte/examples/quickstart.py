"""Load every Aquabyte resource into a local DuckDB file."""

import dlt

from dlt_source_aquabyte import aquabyte_source

# DuckDB is this example's choice, not the package's — swap destination= for any dlt one.
pipeline = dlt.pipeline(pipeline_name="aquabyte", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(aquabyte_source()))
