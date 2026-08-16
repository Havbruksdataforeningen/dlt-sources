"""Re-load an explicit historical window, ignoring the stored cursor."""

import dlt

from dlt_source_aquabyte import aquabyte_source

DATE_BASED = ("biomass", "harvest_report", "lice_count", "welfare_scores")
TIME_BASED = ("environmental", "behaviour_swim_speed", "behaviour_breathing_index")

# A window is bound per resource, and passing one overrides that resource's incremental
# cursor for the run. Which param it takes follows the endpoint: dates or timestamps.
source = aquabyte_source()
for name in DATE_BASED:
    source.resources[name].bind(from_date="2026-01-01", to_date="2026-01-31")
for name in TIME_BASED:
    source.resources[name].bind(from_time="2026-01-01T00:00:00Z", to_time="2026-02-01T00:00:00Z")

pipeline = dlt.pipeline(pipeline_name="aquabyte_backfill", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(source.with_resources(*DATE_BASED, *TIME_BASED)))
