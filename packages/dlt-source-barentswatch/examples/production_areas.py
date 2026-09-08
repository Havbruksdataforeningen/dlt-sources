"""Load the weekly summary of every locality in a few production areas, once a week from then on.

The summary endpoint takes its filter as a request body — `LocalityReportQueryV2` in the spec —
and one value per filter, so this runs the resource once per area. One request per week per area,
however many localities the area holds. The row does not say which area it was requested for, so
dlt's `add_map` stamps it on; the source leaves such choices to the pipeline.
"""

import dlt

from dlt_source_barentswatch import fishhealth_source, last_n_weeks

PRODUCTION_AREAS = [7, 8]
LOOKBACK_WEEKS = 4

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_areas", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)


def stamped_with(area: int):
    return lambda row: {**row, "productionArea": area}


for area in PRODUCTION_AREAS:
    source = fishhealth_source().with_resources("locality_week_summary")
    source.locality_week_summary.bind(week_range=last_n_weeks(LOOKBACK_WEEKS), body={"productionArea": area})
    source.locality_week_summary.add_map(stamped_with(area))
    print(pipeline.run(source))
