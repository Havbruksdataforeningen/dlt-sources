"""Tests for the site_by_id resource."""

from unittest.mock import MagicMock, patch

import dlt
from dlt.sources.helpers.rest_client.paginators import SinglePagePaginator

from dlt_source_aquabyte import site_by_id
from tests.conftest import assert_row_count, load_mock


def test_site_by_id_loads_into_duckdb():
    """site_by_id resource loads a single site into DuckDB."""
    single_site = [load_mock("sites.json")["sites"][0]]

    with patch("dlt_source_aquabyte.aquabyte.RESTClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.paginate.return_value = iter([single_site])

        pipeline = dlt.pipeline(
            pipeline_name="test_site_by_id",
            destination="duckdb",
            dataset_name="test_site_by_id_data",
            dev_mode=True,
        )
        load_info = pipeline.run(
            site_by_id(site_id="site-001", base_url="https://test.api/v3/", api_key="test-key"),
        )

        assert load_info is not None
        assert_row_count(pipeline, "site_by_id", 1)

        call = mock_client.paginate.call_args
        assert call.args[0] == "/sites/site-001"
        assert call.kwargs["params"] == {}
        assert call.kwargs["data_selector"] == "sites"
        assert isinstance(call.kwargs["paginator"], SinglePagePaginator)
