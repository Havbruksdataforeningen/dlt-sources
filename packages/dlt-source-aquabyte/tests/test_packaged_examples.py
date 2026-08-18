"""The packaged `.dlt/*.example` files are checked by using them.

A consumer's first act is to copy these two files and fill in a key, so a section
name that dlt does not look in is a broken quick start — and it stayed broken for a
release because nothing here read the examples. These tests copy them into a throwaway
dlt project, point dlt at it, and build the source with **no arguments and no
environment variables**: whatever the examples fail to supply, the source fails to
resolve.

Nothing below names a config section. The prefix comes from the source itself, so
renaming the source's module moves the test, not the consumer.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dlt.common.configuration.container import Container
from dlt.common.configuration.exceptions import ConfigFieldMissingException
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext

import dlt_source_aquabyte.aquabyte as aquabyte_module
from dlt_source_aquabyte import aquabyte_source
from tests.conftest import resource_signature

DLT_DIR = Path(__file__).parent.parent / ".dlt"
SECRETS_EXAMPLE = DLT_DIR / "secrets.toml.example"
CONFIG_EXAMPLE = DLT_DIR / "config.toml.example"

# The placeholder the secrets example tells a consumer to overwrite.
PLACEHOLDER_KEY = "your-api-key-here"
SENTINEL_KEY = "sentinel-api-key"


@pytest.fixture
def source_from_examples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build the source from the example files alone, and return the mocked RESTClient.

    Follows the quick start literally: copy both examples, replace the placeholder key,
    and resolve. Every `SOURCES__*` variable is cleared first so a maintainer's own
    environment cannot make a broken example look fine.
    """
    for name in [name for name in os.environ if name.startswith("SOURCES__")]:
        monkeypatch.delenv(name, raising=False)

    settings = tmp_path / ".dlt"
    settings.mkdir()
    shutil.copy(CONFIG_EXAMPLE, settings / "config.toml")
    (settings / "secrets.toml").write_text(SECRETS_EXAMPLE.read_text().replace(PLACEHOLDER_KEY, SENTINEL_KEY))

    # `reload` swaps a process-global, so the restore below has to cover the reload
    # itself, not just the test body.
    run_context = Container()[PluggableRunContext]
    original_run_dir = run_context.context.run_dir
    try:
        run_context.reload(str(tmp_path))
        with patch.object(aquabyte_module, "RESTClient") as rest_client:
            try:
                source = aquabyte_source()
            except ConfigFieldMissingException as missing:
                pytest.fail(
                    "The example files do not supply everything aquabyte_source() resolves. "
                    "dlt lists the sections it looked in below; the examples must use one of "
                    f"them.\n\n{missing}"
                )
            yield source, rest_client
    finally:
        run_context.reload(original_run_dir)


def test_secrets_example_resolves_the_api_key(source_from_examples):
    """The section the example tells a consumer to write is the one dlt reads."""
    _, rest_client = source_from_examples
    assert rest_client.call_args.kwargs["auth"].api_key == SENTINEL_KEY


def test_config_example_supplies_every_setting_the_source_needs(source_from_examples):
    """`aquabyte_source()` takes no arguments a consumer copying the example must add."""
    source, rest_client = source_from_examples
    assert rest_client.call_args.kwargs["base_url"] == "https://api.aquabyte.ai/v3/"
    assert _initial_value(source, "biomass", "incremental_date") == "2020-01-01"
    assert _initial_value(source, "environmental", "incremental_from_time") == "2020-01-01T00:00:00Z"


def test_config_example_documents_only_real_resource_params(source_from_examples):
    """The commented per-resource blocks name resources and params that still exist.

    They are the documented per-resource config surface. Being comments, nothing else
    would notice them going stale.
    """
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


def test_neither_example_claims_ci_generates_it():
    """CI runs the offline suite with no credentials, so it generates neither file."""
    for example in (SECRETS_EXAMPLE, CONFIG_EXAMPLE):
        assert "AQUABYTE_API_KEY" not in example.read_text(), f"{example.name} still refers to a CI repository secret"


def _initial_value(source: Any, resource_name: str, argument: str) -> Any:
    """The `initial_value` the named resource's incremental was built with."""
    return resource_signature(source, resource_name).parameters[argument].default.initial_value


def _commented_resource_params(config_example: str, prefix: str) -> dict[str, list[str]]:
    """Parse the commented-out `# [<prefix><resource>]` blocks into resource → params."""
    documented: dict[str, list[str]] = {}
    current: str | None = None
    for line in config_example.splitlines():
        section = re.match(rf"^#\s*\[{re.escape(prefix)}(\w+)\]", line)
        if section:
            resource_name: str = section.group(1)
            current = resource_name
            documented.setdefault(resource_name, [])
            continue
        param = re.match(r"^#\s*(\w+)\s*=", line)
        if param and current:
            documented[current].append(param.group(1))
    return documented
