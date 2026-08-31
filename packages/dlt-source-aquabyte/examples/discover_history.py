"""Measure what one account holds: each resource's earliest date, newest date and row count.

Run this first. The API answers none of those questions — `openapi.json` describes shapes,
not what a contract holds, and the answer differs per account and per resource. Every date
printed is measured; the dates written into this file are the API's own, not an account's.

It loads rather than probes. At `period="D"` one request covers up to 366 days, the window
cap,
so measuring a year costs the same as loading it: six years of every resource is around a
hundred requests, inside the API's 1000 requests per hour. Set the config starts earlier
than you think your data begins — a start before your first record costs empty requests,
not errors — and re-run after an interruption, which the stored cursor and the resources'
merge dispositions resume rather than duplicate.

Two results read as faults and are not. Resources do not all start on the same date, and
they do not all end on it: one can lag the others by a day or two, and a load that finds it
empty is normal. Read the newest dates before writing a freshness alert.

Then set `period` and `bucket_size` per resource in config and load with `quickstart.py`.
A finer `period` costs rows and requests: `environmental` at `15min` returns 96 times the
rows below, in 7-day windows instead of 366-day ones.
"""

import dlt

from dlt_source_aquabyte import MAX_WINDOW_DAYS, aquabyte_source

# Each resource's cursor field, spelled as dlt lands it in the destination.
# `harvest_report` is left out on purpose: it answers 500 to any window containing
# 2025-12-12, and returns fewer reports the wider you ask, so neither its range nor its
# count would mean anything over a multi-year window (Havbruksdataforeningen/dlt-sources#32).
CURSOR_COLUMNS = {
    "biomass": "date",
    "lice_count": "date",
    "welfare_scores": "date",
    "environmental": "from_time",
    "behaviour_swim_speed": "from_time",
    "behaviour_breathing_index": "from_time",
}

# A legal 366-day `/environmental` window at `penId=all` does not return inside 180 s
# (`specs/README.md#api-quirks-worth-knowing`), so this run asks that one resource a month at
# a time. Lowering the window cap is all it takes — the source still splits its own windows,
# and 31 days is a width the API is known to serve, not a measured boundary.
MAX_WINDOW_DAYS[("environmental", "D")] = 31

# The coarsest `period` the two resources that take one accept, whatever config says: this
# run measures the history, it is not the load you keep.
source = aquabyte_source()
source.resources["environmental"].bind(period="D")
source.resources["behaviour_swim_speed"].bind(period="D")

# `/welfareScores` refuses any start before this, whoever asks, so a run reaching further
# back has to give that one resource a start of its own or lose it on every run.
source.resources["welfare_scores"].bind(incremental_date=dlt.sources.incremental(initial_value="2024-04-20"))

pipeline = dlt.pipeline(pipeline_name="aquabyte_discovery", destination="duckdb", dataset_name="aquabyte_history")
pipeline.run(source.with_resources(*CURSOR_COLUMNS))

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
