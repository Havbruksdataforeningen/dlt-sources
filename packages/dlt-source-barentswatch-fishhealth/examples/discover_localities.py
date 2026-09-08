"""Load the salmonoid locality list and print it, to pick the `locality_nos` you will load weekly.

One request. The `locality` table it leaves behind is the API's own list — number and name — of
every locality with a salmonoid licence, about 2 000 of them. Find yours by name below, then put
their numbers in `.dlt/config.toml` under `[sources.barentswatch_fishhealth.locality]` or bind
them in code, as backfill.py and weekly_load.py do.
"""

import dlt

from dlt_source_barentswatch_fishhealth import barentswatch_fishhealth_source

# Only the locality list: locality_week is not selected, so no weekly request is made.
source = barentswatch_fishhealth_source().with_resources("locality")

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_discovery", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))

with pipeline.sql_client() as db:
    rows = db.execute_sql("SELECT locality_no, name FROM locality ORDER BY name") or []

print(f"\n{len(rows)} localities with a salmonoid licence\n")
print(f"{'locality_no':>12}  name")
for locality_no, name in rows:
    print(f"{locality_no:>12}  {name}")
