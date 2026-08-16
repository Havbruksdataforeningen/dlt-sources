"""Consumer-side log routing.

The package logs on the named logger `dlt_source_aquabyte` (and its per-module
children) and installs no handlers of its own — where the records go is your choice,
made with the standard library, not ours. This example sends them to stderr; the same
three lines point them at a file, syslog, or whatever handler your stack already uses.

    uv run python examples/logging_setup.py

What the package logs, and nothing more: the decisions dlt cannot narrate for you.

    INFO     an explicit from_date/from_time overrode the incremental cursor
    INFO     a pen-id list fanned out into one request per pen
    WARNING  no cursor value yet, so the configured initial_date/initial_time applies
    DEBUG    the cursor value a run resumed from

dlt itself logs the requests, row counts and load outcomes on its own `dlt` logger,
configured through dlt's `runtime` settings — see
https://dlthub.com/docs/running-in-production/running#set-the-log-level-and-format
"""

import logging
import sys

import dlt

from dlt_source_aquabyte import aquabyte_source


def route_source_logs(level: int = logging.INFO) -> None:
    """Send this package's log records to stderr."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))

    logger = logging.getLogger("dlt_source_aquabyte")
    logger.setLevel(level)
    logger.addHandler(handler)

    # Set level=logging.DEBUG above to also see the cursor value each resource resumed
    # from — the first thing to look at when a run returns fewer rows than expected.
    # The requests themselves are dlt's to log, on its own `dlt` logger.


def main() -> None:
    route_source_logs()

    pipeline = dlt.pipeline(
        pipeline_name="aquabyte_logged",
        destination="duckdb",
        dataset_name="aquabyte_data",
    )

    # An explicit from_date overrides the incremental cursor — logged at INFO, so a
    # surprising backfill is explainable after the fact.
    source = aquabyte_source()
    source.biomass.bind(from_date="2026-01-01", to_date="2026-01-31")

    load_info = pipeline.run(source.with_resources("biomass"))
    print(load_info)


if __name__ == "__main__":
    sys.exit(main() or 0)
