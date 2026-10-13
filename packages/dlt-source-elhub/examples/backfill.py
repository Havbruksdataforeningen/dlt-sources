"""Re-load one window of values for every metering point, leaving the stored cursors untouched."""

import dlt

from dlt_source_elhub import ALL_RETAINED_HISTORY, elhub_source

# Dates are yyyy-MM-dd'T'HH:mm:ssXXX in Europe/Oslo, and the end is treated as exclusive on
# startTime: this window is the whole of October 1st and 2nd.
START, END = "2026-10-01T00:00:00+02:00", "2026-10-03T00:00:00+02:00"

# Binding a window is what makes this a backfill rather than a load: the request carries it
# instead of the point's cursor, and the cursor is neither consulted nor advanced, so the
# daily load is unaffected. Values inserted at or after insert_date_time are returned, which
# with the oldest possible instant is every value in the window; merge makes re-loading them
# idempotent.
source = elhub_source()
source.metering_values_hour.bind(start_date=START, end_date=END, insert_date_time=ALL_RETAINED_HISTORY)

pipeline = dlt.pipeline(pipeline_name="elhub_backfill", destination="duckdb", dataset_name="elhub_data")

print(pipeline.run(source.with_resources("metering_values_hour")))
