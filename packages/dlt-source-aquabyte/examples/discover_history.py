"""Measure what one account holds: each resource's earliest date, newest date and row count.

Run it with `initial_date` and `initial_time` set earlier than your first camera went into the
sea: a start before your first record costs empty requests, not errors. The output is what
those two settings should be, and how fresh each resource is.
"""

import time

import dlt

from dlt_source_aquabyte import aquabyte_source

# Each resource's cursor field, spelled as dlt lands it in the destination. `harvest_report`
# is left out: over a multi-year window neither its range nor its count means anything
# (Havbruksdataforeningen/dlt-sources#32).
CURSOR_COLUMNS = {
    "biomass": "date",
    "lice_count": "date",
    "welfare_scores": "date",
    "environmental": "from_time",
    "behaviour_swim_speed": "from_time",
    "behaviour_breathing_index": "from_time",
}

# The coarsest `period`, whatever config says: this run measures the history, it is not the
# load you keep. A 366-day `/environmental` window at `penId=all` does not answer inside 180 s
# (`specs/README.md#api-quirks-worth-knowing`), so it is asked for 31 days at a time. Lower
# that if the resource still hangs.
source = aquabyte_source()
source.resources["environmental"].bind(period="D", max_window_days=31)
source.resources["behaviour_swim_speed"].bind(period="D")

# `/welfareScores` refuses any start before this, so a run reaching further back has to give
# that one resource a start of its own or lose it on every run.
source.resources["welfare_scores"].bind(incremental_date=dlt.sources.incremental(initial_value="2024-04-20"))

pipeline = dlt.pipeline(pipeline_name="aquabyte_discovery", destination="duckdb", dataset_name="aquabyte_history")

# One resource per run, so its name is on screen while its requests are in flight: loading the
# whole source in one call makes a slow resource look like a hung script.
print("loading")
for resource in CURSOR_COLUMNS:
    print(f"  {resource:<27}", end="", flush=True)
    started = time.monotonic()
    pipeline.run(source.with_resources(resource))
    print(f"{time.monotonic() - started:>6.0f}s")

# A resource that returned nothing has no table to query, so it is reported as zero rows.
loaded = set(pipeline.default_schema.data_table_names())

print(f"\n{'resource':<27}{'earliest':<22}{'newest':<22}{'rows':>8}")
with pipeline.sql_client() as db:
    for resource, cursor in CURSOR_COLUMNS.items():
        # Both names come from CURSOR_COLUMNS above, so nothing here comes from input.
        span = f'SELECT MIN("{cursor}"), MAX("{cursor}"), COUNT(*) FROM {resource}'  # noqa: S608
        rows = db.execute_sql(span) if resource in loaded else None
        earliest, newest, count = rows[0] if rows else ("-", "-", 0)
        print(f"{resource:<27}{earliest!s:<22}{newest!s:<22}{count:>8}")

print("\nwelfare_scores cannot report earlier than 2024-04-20: the API refuses any start before it.")
