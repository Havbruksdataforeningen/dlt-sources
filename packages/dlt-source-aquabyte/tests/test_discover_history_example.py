"""`examples/discover_history.py` is checked by running it.

It is the first thing a new consumer runs, and the one example whose output they act on,
so a renamed resource or a wrong cursor column would cost them the run before they know
the package at all. This runs it against the mock API and reads what it printed.

Only the numbers need a live account; the shape does not, so it is held here. The run is
given its own working directory and dlt home, because the example names the pipeline a
consumer's own discovery run would name.
"""

import runpy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from dlt_source_aquabyte import MAX_WINDOW_DAYS
from tests.conftest import ENDPOINTS, SOURCE_CONFIG, calls_to, params_sent, serve

EXAMPLE = Path(__file__).parent.parent / "examples" / "discover_history.py"

ROUTES = {endpoint.path: endpoint.records for endpoint in ENDPOINTS}


@pytest.fixture
def example_run(mock_rest_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> dict[str, Any]:
    """Run the example as a consumer would, and return what it defined and what it printed."""
    for key, value in SOURCE_CONFIG.items():
        monkeypatch.setenv(f"SOURCES__AQUABYTE__{key.upper()}", str(value))
    monkeypatch.chdir(tmp_path)
    # The example lowers a window cap, and MAX_WINDOW_DAYS is a process-wide dict.
    monkeypatch.setitem(MAX_WINDOW_DAYS, ("environmental", "D"), MAX_WINDOW_DAYS[("environmental", "D")])
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    mock_rest_client.paginate.side_effect = serve(ROUTES)

    namespace = runpy.run_path(str(EXAMPLE), run_name="__main__")
    return {**namespace, "printed": capsys.readouterr().out}


def test_it_reports_a_date_range_and_a_row_count_for_every_resource(example_run):
    printed = example_run["printed"]
    reported = dict(line.split(maxsplit=1) for line in printed.splitlines() if line.strip())

    for resource in example_run["CURSOR_COLUMNS"]:
        assert resource in reported, f"{resource} is missing from the table the example printed:\n{printed}"
        earliest, newest, rows = reported[resource].split()
        assert earliest <= newest, f"{resource}: earliest {earliest} is after newest {newest}"
        assert int(rows) > 0, f"{resource}: reported no rows"


def test_it_never_asks_for_harvest_report(example_run, mock_rest_client):
    """That endpoint answers 500 to any window containing 2025-12-12, so it cannot be probed."""
    assert calls_to(mock_rest_client, "/biomass/harvestReport") == []


def test_it_asks_environmental_in_windows_the_api_answers_in_time(example_run, mock_rest_client):
    """A legal 366-day `/environmental` window at `penId=all` does not return inside 180 s.

    `specs/README.md#api-quirks-worth-knowing`. Every other resource is asked at the window
    cap, so this is the one place the example lowers it.
    """
    spans = [
        datetime.fromisoformat(params["toTime"]) - datetime.fromisoformat(params["fromTime"])
        for params in params_sent(mock_rest_client, "/environmental")
    ]
    assert spans, "the example asked /environmental for nothing"
    assert max(spans).days <= 31, f"widest /environmental window was {max(spans).days} days"
