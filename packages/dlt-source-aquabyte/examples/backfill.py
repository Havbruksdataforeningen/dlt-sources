"""Re-load historical data for chosen resources and date/time windows. See --help."""

import argparse
import sys

import dlt

from dlt_source_aquabyte import aquabyte_source

DATE_BASED = ["biomass", "harvest_report", "lice_count", "welfare_scores"]
TIME_BASED = ["environmental", "behaviour_swim_speed", "behaviour_breathing_index"]
REFERENCE = ["sites", "pens"]
ALL_RESOURCES = REFERENCE + DATE_BASED + TIME_BASED


def parse_backfill_window() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aquabyte backfill pipeline",
        epilog="Example: python examples/backfill.py --from-date 2026-01-01 --to-date 2026-01-31 --resources biomass lice_count",
    )
    parser.add_argument("--from-date", help=f"Start date (YYYY-MM-DD) for {', '.join(DATE_BASED)}")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--from-time", help=f"Start time (ISO 8601) for {', '.join(TIME_BASED)}")
    parser.add_argument("--to-time", help="End time (ISO 8601)")
    parser.add_argument("--pen-ids", nargs="+", help="Specific pen IDs to fetch (default: all)")
    parser.add_argument("--resources", nargs="+", choices=ALL_RESOURCES, default=ALL_RESOURCES)
    args = parser.parse_args()
    if not any([args.from_date, args.to_date, args.from_time, args.to_time]):
        parser.error("At least one of --from-date, --to-date, --from-time, --to-time is required")
    return args


def run_backfill() -> None:
    args = parse_backfill_window()

    pipeline = dlt.pipeline(
        pipeline_name="aquabyte_backfill",
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

    load_info = pipeline.run(source.with_resources(*args.resources))
    print(load_info)


if __name__ == "__main__":
    sys.exit(run_backfill() or 0)
