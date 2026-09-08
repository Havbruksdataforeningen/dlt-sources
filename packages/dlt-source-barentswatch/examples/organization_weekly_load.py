"""Load one company's localities in detail and the production areas around them in summary, weekly.

The two halves of monitoring your own localities against their neighbours, in one run:
`locality_week` for every locality one company operates, `locality_week_summary` for every locality
in production areas 7 and 8. An organisation number is a filter the summary endpoint takes and
neither locality list carries, so the company's localities are discovered with one summary request
and handed to `locality_week` as an `add_filter` — which localities are yours stays the pipeline's
choice, as in weekly_load.py, where the numbers are written by hand instead.

**Put your own organisation number in below**: the one here is a placeholder that matches nothing,
so the run finds no localities and loads only the two production areas until you change it.

A company with 28 localities costs about 120 requests and ten seconds: 28 localities x 4 weeks in
detail, 2 areas x 4 weeks summarised, and the one that found the localities. Both weekly tables
merge on locality, year and week, so the overlap a repeated run costs is requests and nothing
else — why four weeks is weekly_load.py.
"""

import dlt

from dlt_source_barentswatch import fishhealth_source, last_n_weeks

# Yours, from the Brønnøysund register, digits only: a number the API does not recognise — one
# written 987 654 321, or one it has no localities for — is answered 200 with no rows, so an empty
# set below means the number is wrong rather than that the company has none.
ORGANIZATION_NO = "987654321"  # a placeholder, not a real organisation
PRODUCTION_AREAS = [7, 8]
LOOKBACK_WEEKS = 4

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_company", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)

# The company's localities: one summary request for the most recent complete week, iterated for the
# numbers rather than loaded — the rows the areas load writes are the same ones. A locality can have
# several licensees, so this is every locality the API files under that number, not only the ones
# the company holds alone; the licensees themselves are in the detailed row's aquaCultureRegister.
discovery = fishhealth_source().with_resources("locality_week_summary")
discovery.locality_week_summary.bind(week_range=last_n_weeks(1), body={"organization": ORGANIZATION_NO})
locality_nos = {row["localityNo"] for row in discovery.locality_week_summary}
print(f"{len(locality_nos)} localities under organisation {ORGANIZATION_NO}")

# The detail for those localities, from the salmonoid list locality_week iterates over. Skipped
# when nothing matched, which is what the placeholder number above does: the run would otherwise
# fetch the whole list to filter it down to nothing.
if locality_nos:
    detail = fishhealth_source().with_resources("localities_with_salmonoids", "locality_week")
    detail.localities_with_salmonoids.add_filter(lambda row: row["localityNo"] in locality_nos)
    detail.locality_week.bind(week_range=last_n_weeks(LOOKBACK_WEEKS))
    print(pipeline.run(detail))


def stamped_with(area: int):
    return lambda row: {**row, "productionArea": area}


# The summary for the areas around them, run once per area because the API takes one value, with the
# area stamped on because the row does not say which one it was requested for — production_areas.py.
for area in PRODUCTION_AREAS:
    summary = fishhealth_source().with_resources("locality_week_summary")
    summary.locality_week_summary.bind(week_range=last_n_weeks(LOOKBACK_WEEKS), body={"productionArea": area})
    summary.locality_week_summary.add_map(stamped_with(area))
    print(pipeline.run(summary))
