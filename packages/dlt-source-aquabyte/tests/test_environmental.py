"""Behaviour specific to the environmental resource.

The shared mechanics — the pen, the window params, the envelope key, `period` — are in
`test_resource_loading.py`. `/environmental` is the resource used to exercise cursor
pagination, being one of the six endpoints that return a `nextToken`.
"""

from dlt_source_aquabyte import aquabyte_source
from tests.conftest import (
    SOURCE_CONFIG,
    assert_row_count,
    load_mock,
    make_per_pen_data,
    run_source,
)

DATA = load_mock("environmental.json")["data"]


def test_environmental_pagination_with_next_token(mock_rest_client):
    """Every page the cursor paginator yields is loaded, not just the first."""
    page1 = make_per_pen_data(DATA[:1], "pen-001")
    page2 = make_per_pen_data(DATA[1:], "pen-001")

    mock_rest_client.paginate.side_effect = lambda url, **kwargs: (
        iter([page1, page2]) if url == "/environmental" else iter([])
    )

    source = aquabyte_source(**SOURCE_CONFIG)
    source.environmental.bind(pen_id="pen-001")
    pipeline, load_info = run_source("test_env_pagination", source, ["environmental"])

    assert load_info is not None
    assert_row_count(pipeline, "environmental", len(DATA))
