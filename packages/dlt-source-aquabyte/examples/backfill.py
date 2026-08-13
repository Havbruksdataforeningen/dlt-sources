"""Backfill pipeline for the Aquabyte data platform.

Re-loads historical data for specific resources and date ranges.
Useful for filling gaps, reprocessing after schema changes, or
loading data for a new pen.

Usage examples:

    # Backfill all date-based resources for January 2026:
    python examples/backfill.py --from-date 2026-01-01 --to-date 2026-01-31

    # Backfill only biomass and lice_count:
    python examples/backfill.py --from-date 2026-01-01 --to-date 2026-01-31 \
        --resources biomass lice_count

    # Backfill time-based resources (environmental, swim speed, breathing index):
    python examples/backfill.py --from-time 2026-01-01T00:00:00Z --to-time 2026-01-31T23:59:59Z \
        --resources environmental behaviour_swim_speed behaviour_breathing_index

    # Backfill specific pens only:
    python examples/backfill.py --from-date 2026-01-01 --to-date 2026-01-31 \
        --pen-ids pen-abc-123 pen-def-456

    # Backfill everything (all resources, all pens) from a specific date:
    python examples/backfill.py --from-date 2025-06-01 --to-date 2025-12-31 \
        --from-time 2025-06-01T00:00:00Z --to-time 2025-12-31T23:59:59Z

Available resources:
    Date-based:  biomass, harvest_report, lice_count, welfare_scores
    Time-based:  environmental, behaviour_swim_speed, behaviour_breathing_index
    Reference:   sites, pens (no date filtering, always full replace)
"""

import argparse
import sys

import dlt

from dlt_source_aquabyte import aquabyte_source

ALL_RESOURCES = [
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
    """Run the Aquabyte backfill pipeline."""
    parser = argparse.ArgumentParser(
        description="Aquabyte backfill pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python examples/backfill.py --from-date 2026-01-01 --to-date 2026-01-31\n"
            "  python examples/backfill.py --from-date 2026-01-01 --resources biomass lice_count\n"
            "  python examples/backfill.py --from-time 2026-01-01T00:00:00Z --resources environmental\n"
        ),
    )
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD) for date-based resources")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD) for date-based resources")
    parser.add_argument("--from-time", help="Start time (ISO 8601) for time-based resources")
    parser.add_argument("--to-time", help="End time (ISO 8601) for time-based resources")
    parser.add_argument("--pen-ids", nargs="+", help="Specific pen IDs to fetch (default: all)")
    parser.add_argument(
        "--resources",
        nargs="+",
        choices=ALL_RESOURCES,
        default=ALL_RESOURCES,
        help="Resources to backfill (default: all)",
    )
    args = parser.parse_args()

    if not any([args.from_date, args.to_date, args.from_time, args.to_time]):
        parser.error("At least one of --from-date, --to-date, --from-time, --to-time is required")

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
    sys.exit(main() or 0)
