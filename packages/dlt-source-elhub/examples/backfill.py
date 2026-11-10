"""Re-load one window of values for every metering point the end user had in it, leaving the stored cursors untouched."""

import dlt

from dlt_source_elhub import elhub_source

# A bound window is sent instead of the point's cursor, which is neither read nor advanced. The end is
# exclusive in practice: this is the whole of October 1st and 2nd. Merge makes re-loading idempotent.
source = elhub_source()
source.metering_values_hour.bind(start_date="2026-10-01", end_date="2026-10-03")

# The same window on metering_points lists each of its days, so a point the end user has since lost is
# read too. Add metering_point_ids=[...] to backfill only those points.
source.metering_points.bind(start_date="2026-10-01", end_date="2026-10-03")

pipeline = dlt.pipeline(pipeline_name="elhub_backfill", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(source.with_resources("metering_values_hour")))
