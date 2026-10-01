"""The last few complete weeks for a few localities, to run on a timer.

Reports keep arriving after a week ends, so the load re-requests recent weeks rather than only the
newest; merge on locality, year and week absorbs the overlap.
"""

import dlt

from dlt_source_barentswatch import fishhealth_source, last_n_weeks

LOCALITY_NOS = {11340, 45072}
LOOKBACK_WEEKS = 4

source = fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
source.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in LOCALITY_NOS)
source.locality_week.bind(week_range=last_n_weeks(LOOKBACK_WEEKS))

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))
