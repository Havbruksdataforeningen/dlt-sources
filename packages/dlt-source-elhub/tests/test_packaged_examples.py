"""The packaged `.dlt/*.example` files are checked by using them.

A consumer's first act is to copy these two files and fill in a client, so a section name
that dlt does not look in is a broken quick start. These tests copy them into a throwaway
dlt project and build the source with no arguments and no environment variables: whatever
the examples fail to supply, the source fails to resolve.

The README inlines the same two files, so it is held to the examples here as well.
"""

import re
import shutil
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dlt.common.configuration.exceptions import ConfigFieldMissingException

import dlt_source_elhub.elhub as elhub_module
from dlt_source_elhub import elhub_source
from tests.conftest import dlt_project, resource_signature

README = Path(__file__).parent.parent / "README.md"
DLT_DIR = Path(__file__).parent.parent / ".dlt"
SECRETS_EXAMPLE = DLT_DIR / "secrets.toml.example"
CONFIG_EXAMPLE = DLT_DIR / "config.toml.example"

PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
SENTINEL_CLIENT_ID = "sentinel-client-id"


@pytest.fixture
def source_from_examples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build the source from the example files alone, and return the mocked RESTClient."""
    settings = tmp_path / ".dlt"
    settings.mkdir()
    shutil.copy(CONFIG_EXAMPLE, settings / "config.toml")
    (settings / "secrets.toml").write_text(SECRETS_EXAMPLE.read_text().replace(PLACEHOLDER, SENTINEL_CLIENT_ID, 1))

    with dlt_project(tmp_path, monkeypatch), patch.object(elhub_module, "RESTClient") as rest_client:
        try:
            source = elhub_source()
        except ConfigFieldMissingException as missing:
            pytest.fail(
                "The example files do not supply everything elhub_source() resolves. "
                "dlt lists the sections it looked in below; the examples must use one of "
                f"them.\n\n{missing}"
            )
        yield source, rest_client


def test_secrets_example_resolves_the_maskinporten_client(source_from_examples):
    """The section the example tells a consumer to write is the one dlt reads."""
    _, rest_client = source_from_examples
    auth = rest_client.call_args.kwargs["auth"]
    assert auth.credentials.client_id == SENTINEL_CLIENT_ID
    assert auth.credentials.kid == PLACEHOLDER
    assert auth.credentials.private_key.startswith("-----BEGIN PRIVATE KEY-----")
    assert auth.credentials.maskinporten_url == "https://maskinporten.no"


def test_config_example_supplies_what_the_source_reads(source_from_examples):
    _, rest_client = source_from_examples
    assert rest_client.call_args.kwargs["base_url"] == "https://api.elhub.no/energy-data/v0/"
    assert rest_client.call_args.kwargs["headers"]["User-Agent"] == "my-company-elhub-pipeline"


def test_config_example_documents_only_real_resource_params(source_from_examples):
    """The commented per-resource blocks name resources and params that still exist."""
    source, _ = source_from_examples
    documented = _commented_resource_params(CONFIG_EXAMPLE.read_text(), prefix=f"sources.{source.section}.")
    assert documented, "Expected the config example to document at least one per-resource param"

    for resource_name, params in documented.items():
        assert resource_name in source.resources, f"Config example documents an unknown resource: {resource_name}"
        signature = resource_signature(source, resource_name).parameters
        for param in params:
            assert param in signature, (
                f"Config example documents {resource_name}.{param}, which the resource does not take"
            )


def test_config_example_documents_only_real_source_settings():
    """The commented `[sources.elhub]` settings are arguments `elhub_source` takes."""
    import inspect

    section = CONFIG_EXAMPLE.read_text().split("[sources.elhub]", 1)[1].split("\n# [", 1)[0]
    documented = set(re.findall(r"^#?\s*(\w+)\s*=", section, re.MULTILINE))
    assert documented <= set(inspect.signature(elhub_source).parameters), documented


def test_readme_quick_start_matches_the_packaged_examples():
    """A reader on PyPI copies the README, a reader with a checkout copies the examples."""
    config, secrets = _readme_toml_blocks()[:2]
    assert config == {"sources": {"elhub": tomllib.loads(CONFIG_EXAMPLE.read_text())["sources"]["elhub"]}}
    assert secrets == tomllib.loads(SECRETS_EXAMPLE.read_text())


def _commented_resource_params(config_example: str, prefix: str) -> dict[str, list[str]]:
    """Parse the commented-out `# [<prefix><resource>]` blocks into resource → params."""
    documented: dict[str, list[str]] = {}
    current: str | None = None
    for line in config_example.splitlines():
        section = re.match(rf"^#\s*\[{re.escape(prefix)}(\w+)\]", line)
        if section:
            current = str(section.group(1))
            documented.setdefault(current, [])
            continue
        param = re.match(r"^#\s*(\w+)\s*=", line)
        if param and current:
            documented[current].append(param.group(1))
    return documented


def _readme_toml_blocks() -> list[dict[str, Any]]:
    """Every ```toml fenced block in the README, parsed."""
    blocks = re.findall(r"```toml\n(.*?)```", README.read_text(), re.DOTALL)
    assert len(blocks) >= 2, "Expected the README quick start to show config.toml and secrets.toml"
    return [tomllib.loads(block) for block in blocks]
