"""Load the salmonoid locality list and print it, to pick the `locality_nos` you will load weekly.

One request. The `localities_with_salmonoids` table it leaves behind is the API's own list — number
and name — of every locality with a salmonoid licence, about 2 000 of them, and the list `locality_week`
iterates over. Find yours by name below and put their numbers in backfill.py and weekly_load.py, which
filter that list with dlt's `add_filter`. (`localities`, the other list, is every locality in the register
with its municipality, salmonoid or not.)
"""

import dlt

from dlt_source_barentswatch_fishhealth import barentswatch_fishhealth_source

# Only the locality list: locality_week is not selected, so no weekly request is made.
source = barentswatch_fishhealth_source().with_resources("localities_with_salmonoids")

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_discovery", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(source))

with pipeline.sql_client() as db:
    rows = db.execute_sql("SELECT locality_no, name FROM localities_with_salmonoids ORDER BY name") or []

print(f"\n{len(rows)} localities with a salmonoid licence\n")
print(f"{'locality_no':>12}  name")
for locality_no, name in rows:
    print(f"{locality_no:>12}  {name}")
