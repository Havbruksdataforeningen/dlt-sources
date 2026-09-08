"""Load every week the API has for a few localities, from the first year to now.

The weekly endpoint is one request per locality per week, and the API asks that requests are
made one at a time. So the cost of a backfill is the number of localities times the number of
weeks: a handful of localities back to 2012 is a few thousand requests and takes minutes; every
salmonoid locality is over a million requests and takes days. Weeks before a locality existed
answer 400 quickly and are skipped.

Re-running is safe: locality_week merges on locality, year and week.
"""

import dlt

from dlt_source_barentswatch_fishhealth import FIRST_YEAR, WeekRange, barentswatch_fishhealth_source, current_iso_week

# The numbers discover_localities.py printed for your localities.
LOCALITY_NOS = [11340, 45072]

# Only the detailed report and the list it iterates over: the summary resource is not bound here.
source = barentswatch_fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
source.localities_with_salmonoids.bind(locality_nos=LOCALITY_NOS)
source.locality_week.bind(week_range=WeekRange(FIRST_YEAR, 1, *current_iso_week()))

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_backfill", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))
