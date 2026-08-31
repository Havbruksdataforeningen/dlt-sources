"""Load a history into the destination, leaving the stored cursor untouched."""

from datetime import UTC, datetime

import dlt

from dlt_source_aquabyte import aquabyte_source

# Step 2 of the README's "How to start": the earliest dates discover_history.py measured go
# here. No window arithmetic — the source splits the span into windows the API accepts.
#
# `end_value` is what makes this a backfill rather than a load: dlt then runs the resource
# with transient state, so the stored cursor is neither consulted nor advanced and the daily
# load is unaffected. Drop it and dlt stores a cursor instead, which is quickstart.py's job.
# Which argument carries the window follows the endpoint's cursor field, like every other param.
TODAY = datetime.now(tz=UTC).date().isoformat()
DATE_WINDOW = ("2020-01-01", TODAY)
TIME_WINDOW = ("2020-01-01T00:00:00Z", f"{TODAY}T00:00:00Z")

# `/welfareScores` refuses any start before this and fails the resource on every run that asks
# earlier, so it never starts before the floor however far back the rest of the backfill goes.
WELFARE_SCORES_FLOOR = "2024-04-20"

DATE_BASED = {
    "biomass": "incremental_date",
    "harvest_report": "incremental_slaughter_start_date",
    "lice_count": "incremental_date",
    "welfare_scores": "incremental_date",
}
TIME_BASED = {
    "environmental": "incremental_from_time",
    "behaviour_swim_speed": "incremental_from_time",
    "behaviour_breathing_index": "incremental_from_time",
}

source = aquabyte_source()
for name, argument in DATE_BASED.items():
    initial_value, end_value = DATE_WINDOW
    if name == "welfare_scores":
        initial_value = max(initial_value, WELFARE_SCORES_FLOOR)
    source.resources[name].bind(**{argument: dlt.sources.incremental(initial_value=initial_value, end_value=end_value)})
for name, argument in TIME_BASED.items():
    initial_value, end_value = TIME_WINDOW
    source.resources[name].bind(**{argument: dlt.sources.incremental(initial_value=initial_value, end_value=end_value)})

pipeline = dlt.pipeline(pipeline_name="aquabyte_backfill", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(source.with_resources(*DATE_BASED, *TIME_BASED)))
