"""Re-load an explicit historical window, leaving the stored cursor untouched."""

import dlt

from dlt_source_aquabyte import aquabyte_source

# Backfill the dlt way: bind an incremental carrying the window. dlt runs it with
# transient state, so the window is requested from the API, enforced by dlt's own
# incremental filter, and the stored cursor is neither consulted nor advanced — the
# next regular run resumes exactly where it left off. Which argument carries it
# follows the endpoint's cursor field, like every other param.
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
    window = dlt.sources.incremental(initial_value="2026-01-01", end_value="2026-02-01")
    source.resources[name].bind(**{argument: window})
for name, argument in TIME_BASED.items():
    window = dlt.sources.incremental(initial_value="2026-01-01T00:00:00Z", end_value="2026-02-01T00:00:00Z")
    source.resources[name].bind(**{argument: window})

pipeline = dlt.pipeline(pipeline_name="aquabyte_backfill", destination="duckdb", dataset_name="aquabyte_data")

print(pipeline.run(source.with_resources(*DATE_BASED, *TIME_BASED)))
