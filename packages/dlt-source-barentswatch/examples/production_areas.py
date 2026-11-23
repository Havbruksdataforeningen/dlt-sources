"""The weekly summary of every locality in a few production areas, one run per area."""

import dlt

from dlt_source_barentswatch import fishhealth_source, last_n_weeks

PRODUCTION_AREAS = [7, 8]
LOOKBACK_WEEKS = 4


def stamped_with(area: int):
    """A summary row does not say which area it was requested for. One argument: dlt passes `meta` as the second."""
    return lambda row: {**row, "productionArea": area}


pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_areas", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)

for area in PRODUCTION_AREAS:
    source = fishhealth_source().with_resources("locality_week_summary")
    source.locality_week_summary.bind(week_range=last_n_weeks(LOOKBACK_WEEKS), body={"productionArea": area})
    source.locality_week_summary.add_map(stamped_with(area))
    print(pipeline.run(source))
