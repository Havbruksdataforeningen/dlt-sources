"""Load every metering point and its values into a local DuckDB file, today and every day after."""

import dlt

from dlt_source_elhub import elhub_source

# Bind nothing: an unseen metering point loads everything Elhub retains, a seen one what was inserted
# since its own cursor. Run it on a timer after 09:00 Europe/Oslo, when Elhub has forwarded yesterday.
pipeline = dlt.pipeline(pipeline_name="elhub", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(elhub_source()))
