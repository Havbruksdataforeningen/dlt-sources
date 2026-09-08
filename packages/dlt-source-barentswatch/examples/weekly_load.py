"""Load the last few complete weeks for a few localities, once a week from then on.

Reports for a week keep arriving after it ends, so a scheduled load re-requests a few recent
weeks every time instead of only the newest one; merge on locality, year and week makes the
overlap free. `last_n_weeks` leaves the current week out because it is still being reported.
DuckDB is this example's choice, not the package's — swap destination= for any dlt one.
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
