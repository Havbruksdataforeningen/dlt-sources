"""Load every Aquabyte resource into local DuckDB, with optional date/pen overrides."""

import argparse
import sys

import dlt

from dlt_source_aquabyte import aquabyte_source


def run_all_resources() -> None:
    parser = argparse.ArgumentParser(description="Aquabyte API v3 dlt pipeline")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD) for date-based endpoints")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--from-time", help="Start time (ISO 8601) for time-based endpoints")
    parser.add_argument("--to-time", help="End time (ISO 8601)")
    parser.add_argument("--pen-ids", nargs="+", help="Specific pen IDs to fetch (default: all)")
    args = parser.parse_args()

    pipeline = dlt.pipeline(
        pipeline_name="aquabyte",
        destination="duckdb",
        dataset_name="aquabyte_data",
    )

    source = aquabyte_source(
        pen_ids=args.pen_ids,
        from_date=args.from_date,
        to_date=args.to_date,
        from_time=args.from_time,
        to_time=args.to_time,
    )

    load_info = pipeline.run(source)
    print(load_info)


if __name__ == "__main__":
    sys.exit(run_all_resources() or 0)
