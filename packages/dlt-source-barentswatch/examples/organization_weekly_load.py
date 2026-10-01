"""One company's localities in detail and the production areas around them in summary, weekly.

Put your own number in `ORGANIZATION_NO`: only the summary endpoint knows organisation numbers, so
one summary request finds the company's localities and `locality_week` loads those.
"""

import dlt

from dlt_source_barentswatch import fishhealth_source, last_n_weeks

ORGANIZATION_NO = "987654321"  # a placeholder: an organisation the API does not know is 200 and no rows
PRODUCTION_AREAS = [7, 8]
LOOKBACK_WEEKS = 4


def localities_of(organization_no: str) -> set[int]:
    """The locality numbers the API files under an organisation number, from the most recent week."""
    source = fishhealth_source().with_resources("locality_week_summary")
    source.locality_week_summary.bind(week_range=last_n_weeks(1), body={"organization": organization_no})
    return {row["localityNo"] for row in source.locality_week_summary}


def stamped_with(area: int):
    """A summary row does not say which area it was requested for. One argument: dlt passes `meta` as the second."""
    return lambda row: {**row, "productionArea": area}


pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_company", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)

locality_nos = localities_of(ORGANIZATION_NO)
print(f"{len(locality_nos)} localities under organisation {ORGANIZATION_NO}")

if locality_nos:
    detail = fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
    detail.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in locality_nos)
    detail.locality_week.bind(week_range=last_n_weeks(LOOKBACK_WEEKS))
    print(pipeline.run(detail))

for area in PRODUCTION_AREAS:
    summary = fishhealth_source().with_resources("locality_week_summary")
    summary.locality_week_summary.bind(week_range=last_n_weeks(LOOKBACK_WEEKS), body={"productionArea": area})
    summary.locality_week_summary.add_map(stamped_with(area))
    print(pipeline.run(summary))
