"""Daily load pipeline for the Aquabyte data platform.

Loads reference data (sites, pens) and all incremental data resources.
Skips environmental_latest (realtime use case only).

On first run, backfills from initial_date/initial_time in .dlt/config.toml.
On subsequent runs, dlt incremental state picks up where the last successful
run left off — automatically catching up on any missed days.

No parameters needed. Just run it:

    python examples/daily_load.py
"""

import sys

import dlt

from dlt_source_aquabyte import aquabyte_source

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


def main() -> None:
    """Run the daily Aquabyte pipeline."""
    pipeline = dlt.pipeline(
        pipeline_name="aquabyte_daily",
        destination="duckdb",
        dataset_name="aquabyte_data",
    )

    source = aquabyte_source()

    load_info = pipeline.run(source.with_resources(*DAILY_RESOURCES))
    print(load_info)


if __name__ == "__main__":
    sys.exit(main() or 0)
