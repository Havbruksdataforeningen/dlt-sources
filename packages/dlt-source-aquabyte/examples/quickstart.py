"""Minimal quickstart: load every Aquabyte resource into a local DuckDB file.

    uv run python examples/quickstart.py

Needs `.dlt/config.toml` and `.dlt/secrets.toml` (copy the `.example` files first).
DuckDB is this example's choice, not the package's — swap `destination=` for any
dlt destination.
"""

import sys

import dlt

from dlt_source_aquabyte import aquabyte_source


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="aquabyte",
        destination="duckdb",
        dataset_name="aquabyte_data",
    )

    load_info = pipeline.run(aquabyte_source())
    print(load_info)


if __name__ == "__main__":
    sys.exit(main() or 0)
