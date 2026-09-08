"""Load the weekly summary of every locality in a few production areas, once a week from then on.

One request per week per area, however many localities the area holds, so the whole history
of two areas is a few hundred requests. The summary row carries the lice report and the diseases
exactly as the detailed report does, and the treatments as category names; it is what a
comparison across localities needs. Add `organizations=["<org no>"]` to narrow it to one
company's localities, or leave every filter out for the whole country.
"""

import dlt

from dlt_source_barentswatch_fishhealth import barentswatch_fishhealth_source, last_n_weeks

PRODUCTION_AREAS = [7, 8]
LOOKBACK_WEEKS = 4

source = barentswatch_fishhealth_source().with_resources("locality_week_summary")
source.locality_week_summary.bind(week_range=last_n_weeks(LOOKBACK_WEEKS), production_areas=PRODUCTION_AREAS)

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_areas", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))
