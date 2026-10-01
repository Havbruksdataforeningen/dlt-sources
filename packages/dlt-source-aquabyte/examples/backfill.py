"""Load a history into the destination, leaving the stored cursor untouched."""

from datetime import UTC, datetime

import dlt

from dlt_source_aquabyte import aquabyte_source

# Step 2 of the README's "How to start": the earliest dates discover_history.py measured go
# here. No window arithmetic — the source splits the span into windows the API accepts.
#
# `end_value` is what makes this a backfill rather than a load: dlt then runs the resource
# with transient state, so the stored cursor is neither consulted nor advanced and the daily
# load is unaffected. Drop it and dlt stores a cursor instead, which is daily_load.py's job.
TODAY = datetime.now(tz=UTC).date().isoformat()
DATE_WINDOW = ("2020-01-01", TODAY)
TIME_WINDOW = ("2020-01-01T00:00:00Z", f"{TODAY}T00:00:00Z")

# `/welfareScores` refuses any start before 2024-04-20 and fails the resource on every run that
# asks earlier, so it never starts before that however far back the rest of the backfill goes.
WELFARE_SCORES_WINDOW = (max(DATE_WINDOW[0], "2024-04-20"), TODAY)

# Which argument carries the window follows the endpoint's cursor field, like every other param.
WINDOWS = {
    "biomass": ("incremental_date", DATE_WINDOW),
    "harvest_report": ("incremental_slaughter_start_date", DATE_WINDOW),
    "lice_count": ("incremental_date", DATE_WINDOW),
    "welfare_scores": ("incremental_date", WELFARE_SCORES_WINDOW),
    "environmental": ("incremental_from_time", TIME_WINDOW),
    "behaviour_swim_speed": ("incremental_from_time", TIME_WINDOW),
    "behaviour_breathing_index": ("incremental_from_time", TIME_WINDOW),
}

source = aquabyte_source()
for resource, (argument, (initial_value, end_value)) in WINDOWS.items():
    window = dlt.sources.incremental(initial_value=initial_value, end_value=end_value)
    source.resources[resource].bind(**{argument: window})

pipeline = dlt.pipeline(pipeline_name="aquabyte_backfill", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(source.with_resources(*WINDOWS)))
