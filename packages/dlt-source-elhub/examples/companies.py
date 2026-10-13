"""Load several companies with one Maskinporten client, into one dataset."""

import dlt

from dlt_source_elhub import elhub_source

# One source per company: its token is issued with the company's organisation number as consumer_org.
# The sources share the pipeline safely: a metering point id is unique across Elhub.
COMPANIES = ["999999991", "999999992", "999999993"]

pipeline = dlt.pipeline(pipeline_name="elhub", destination="duckdb", dataset_name="elhub_data")

# One run per company, so a company that fails does not stop the others and the failure names it.
failed: dict[str, Exception] = {}
for company in COMPANIES:
    try:
        print(pipeline.run(elhub_source(consumer_org=company)))
    except Exception as error:  # collected and raised below, with the company's name
        failed[company] = error

if failed:
    raise RuntimeError(f"Elhub load failed for {', '.join(failed)}") from next(iter(failed.values()))
