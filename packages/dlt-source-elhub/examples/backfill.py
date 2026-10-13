"""Re-load one window of values, leaving the stored cursors untouched."""

import dlt

from dlt_source_elhub import elhub_source

# Dates are YYYY-MM-DD in Europe/Oslo, and the end is exclusive in practice: this window is the
# whole of October 1st and 2nd. Binding one is what makes this a backfill rather than a load:
# the request carries it instead of the point's cursor, and the cursor is neither consulted nor
# advanced, so the daily load is unaffected. Merge makes re-loading the same values idempotent.
source = elhub_source()
source.metering_values_hour.bind(start_date="2026-10-01", end_date="2026-10-03")

# Leave this out to backfill every metering point the list call returns.
source.metering_points.bind(metering_point_ids=["707057500083917012"])

pipeline = dlt.pipeline(pipeline_name="elhub_backfill", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(source.with_resources("metering_values_hour")))
