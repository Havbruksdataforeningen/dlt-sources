"""Load several companies with one Maskinporten client, into one dataset."""

import dlt

from dlt_source_elhub import elhub_source

# One source per company: the token for each is issued with that company's organisation
# number as consumer_org, after the company has delegated the scope to the client's
# organisation in Altinn. The sources share the pipeline, and so the cursors, safely: a
# metering point id is unique across Elhub, and each point keeps its own cursor.
COMPANIES = ["999999991", "999999992", "999999993"]

pipeline = dlt.pipeline(pipeline_name="elhub", destination="duckdb", dataset_name="elhub_data")

# One run per company, so a company that fails does not stop the others, and the failure
# names it. What to do about a failed one — retry, alert — is the pipeline's call.
failed: dict[str, Exception] = {}
for company in COMPANIES:
    try:
        print(pipeline.run(elhub_source(consumer_org=company)))
    except Exception as error:  # collected and raised below, with the company's name
        failed[company] = error

if failed:
    raise RuntimeError(f"Elhub load failed for {', '.join(failed)}") from next(iter(failed.values()))
