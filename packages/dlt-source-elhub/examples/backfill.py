"""Re-load one window of values, leaving the stored cursors untouched."""

import dlt

from dlt_source_elhub import elhub_source

# A bound window is sent instead of the point's cursor, which is neither read nor advanced. The end is
# exclusive in practice: this is the whole of October 1st and 2nd. Merge makes re-loading idempotent.
source = elhub_source()
source.metering_values_hour.bind(start_date="2026-10-01", end_date="2026-10-03")

# Leave this out to backfill every metering point the list call returns or has returned before.
source.metering_points.bind(metering_point_ids=["707057500000000001"])

pipeline = dlt.pipeline(pipeline_name="elhub_backfill", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(source.with_resources("metering_values_hour")))
