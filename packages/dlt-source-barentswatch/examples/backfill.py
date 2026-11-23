"""Every week the API has for a few localities, from 2012 to now, run once.

One request per locality per week: keep the filter, or this is every salmonoid locality back to
2012. Weeks before a locality existed answer 400 and are skipped.
"""

import dlt

from dlt_source_barentswatch import FIRST_YEAR, WeekRange, current_iso_week, fishhealth_source

LOCALITY_NOS = {11340, 45072}

source = fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
source.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in LOCALITY_NOS)
source.locality_week.bind(week_range=WeekRange(FIRST_YEAR, 1, *current_iso_week()))

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_backfill", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))
