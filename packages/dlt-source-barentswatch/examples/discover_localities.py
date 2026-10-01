"""Print every locality that has had a salmonoid licence, to pick the numbers the other examples filter on."""

import dlt

from dlt_source_barentswatch import fishhealth_source

pipeline = dlt.pipeline(
    pipeline_name="barentswatch_fishhealth_discovery", destination="duckdb", dataset_name="barentswatch_fishhealth_data"
)
print(pipeline.run(fishhealth_source().with_resources("localities_with_salmonoids")))

with pipeline.sql_client() as db:
    rows = db.execute_sql("SELECT locality_no, name FROM localities_with_salmonoids ORDER BY name") or []

print(f"\n{len(rows)} rows, {len({no for no, _ in rows})} localities that have had a salmonoid licence\n")
print(f"{'locality_no':>12}  name")
for locality_no, name in rows:
    print(f"{locality_no:>12}  {name}")
