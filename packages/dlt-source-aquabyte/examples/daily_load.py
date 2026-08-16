"""Re-run on a schedule: each resource picks up from the cursor dlt stored last time."""

import dlt

from dlt_source_aquabyte import aquabyte_source

# Bind nothing. The first run starts at the initial_date/initial_time in config, every
# later run resumes from the stored cursor, so a scheduler just calls this on a timer.
pipeline = dlt.pipeline(pipeline_name="aquabyte_daily", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(aquabyte_source()))
