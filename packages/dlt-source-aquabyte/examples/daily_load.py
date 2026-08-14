"""Scheduled daily load.

Nothing is bound: the first run starts from the `initial_date`/`initial_time` in
config, and every later run resumes from the incremental cursor dlt stored. Which
scheduler triggers this — cron, Airflow, Prefect, a CI job — is your choice.

    uv run python examples/daily_load.py
"""

import sys

import dlt

from dlt_source_aquabyte import aquabyte_source

# environmental_latest is excluded: realtime polling, not a daily batch concern.
DAILY_RESOURCES = [
    "sites",
    "pens",
    "environmental",
    "biomass",
    "harvest_report",
    "lice_count",
    "behaviour_swim_speed",
    "behaviour_breathing_index",
    "welfare_scores",
]


def run_daily_load() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="aquabyte_daily",
        destination="duckdb",
        dataset_name="aquabyte_data",
    )

    load_info = pipeline.run(aquabyte_source().with_resources(*DAILY_RESOURCES))
    print(load_info)


if __name__ == "__main__":
    sys.exit(run_daily_load() or 0)
