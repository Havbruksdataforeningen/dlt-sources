"""The packaged `.dlt/*.example` files are checked by using them.

A consumer's first act is to copy these two files and fill in credentials, so a section
name that dlt does not look in is a broken quick start. These tests copy them into a
throwaway dlt project, point dlt at it, and build the source with **no arguments and no
environment variables**: whatever the examples fail to supply, the source fails to resolve.

The README inlines the same two files, for a reader on PyPI who has no checkout to copy
from, so it is held to the examples here as well.

Nothing below names a config section. The prefix comes from the source itself, so
renaming the source's module moves the test, not the consumer.
"""

import re
import shutil
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest
from dlt.common.configuration.container import Container
from dlt.common.configuration.exceptions import ConfigFieldMissingException
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext

from dlt_source_barentswatch import fishhealth_source
from dlt_source_barentswatch.fishhealth import TOKEN_URL
from tests.conftest import resource_signature

README = Path(__file__).parent.parent / "README.md"
DLT_DIR = Path(__file__).parent.parent / ".dlt"
SECRETS_EXAMPLE = DLT_DIR / "secrets.toml.example"
CONFIG_EXAMPLE = DLT_DIR / "config.toml.example"

# The placeholders the secrets example tells a consumer to overwrite, and what the test writes instead.
PLACEHOLDERS = {"your-client-id-here": "sentinel-client-id", "your-client-secret-here": "sentinel-client-secret"}


@pytest.fixture
def source_from_examples(isolated_run_context: Path) -> Any:
    """Build the source from the example files alone.

    Follows the quick start literally: copy both examples into the empty project the
    autouse fixture already pointed dlt at, replace the placeholders, and resolve.
    """
    settings = isolated_run_context / ".dlt"
    settings.mkdir()
    shutil.copy(CONFIG_EXAMPLE, settings / "config.toml")
    secrets = SECRETS_EXAMPLE.read_text()
    for placeholder, sentinel in PLACEHOLDERS.items():
        secrets = secrets.replace(placeholder, sentinel)
    (settings / "secrets.toml").write_text(secrets)
    # dlt reads the toml files when the run context loads, so point it at them again now
    # that they exist. The autouse fixture restores the original context afterwards.
    Container()[PluggableRunContext].reload(str(isolated_run_context))

    try:
        return fishhealth_source()
    except ConfigFieldMissingException as missing:
        pytest.fail(
            "The example files do not supply everything fishhealth_source() resolves. "
            "dlt lists the sections it looked in below; the examples must use one of "
            f"them.\n\n{missing}"
        )


def test_secrets_example_resolves_the_credentials(source_from_examples, mock_api):
    """The section the example tells a consumer to write is the one dlt reads — and what reaches the token endpoint."""
    mock_api.localities()

    list(source_from_examples.localities_with_salmonoids)

    (token_request,) = mock_api.requests_to(TOKEN_URL)
    sent = {key: value for key, [value] in parse_qs(token_request.text).items()}
    assert sent["client_id"] == PLACEHOLDERS["your-client-id-here"]
    assert sent["client_secret"] == PLACEHOLDERS["your-client-secret-here"]


def test_config_example_documents_only_real_resource_params(source_from_examples):
    """The commented block names a resource and an argument that still exist, and sets nothing by itself.

    It is the documented per-resource config surface. Being a comment, nothing else would
    notice it going stale.
    """
    assert tomllib.loads(CONFIG_EXAMPLE.read_text()) == {}, "everything in the config example is commented out"

    documented = _commented_resource_params(
        CONFIG_EXAMPLE.read_text(), prefix=f"sources.{source_from_examples.section}."
    )
    assert documented, "Expected the config example to document at least one per-resource param"
    _assert_real_resource_params(source_from_examples, documented, "Config example")
    assert documented == {"locality_week_summary": ["body"]}


def test_readme_secrets_match_the_packaged_example():
    """A reader on PyPI copies the README, a reader with a checkout copies the example; they must agree."""
    assert _readme_toml_blocks()[0] == tomllib.loads(SECRETS_EXAMPLE.read_text())


def test_readme_config_names_real_resource_params(source_from_examples):
    """The README's optional config block, if it shows one, sets a real argument on a real resource under the section dlt reads."""
    blocks = _readme_toml_blocks()
    if len(blocks) < 2:
        pytest.skip("the README shows no config.toml block")
    sections = blocks[1]["sources"][source_from_examples.section]
    documented = {resource_name: list(params) for resource_name, params in sections.items()}
    assert documented, "Expected the README config block to set at least one per-resource param"
    _assert_real_resource_params(source_from_examples, documented, "README")


def test_neither_example_claims_ci_generates_it():
    """CI runs the offline suite with no credentials, so it generates neither file."""
    for example in (SECRETS_EXAMPLE, CONFIG_EXAMPLE):
        assert "BARENTSWATCH_CLIENT" not in example.read_text(), f"{example.name} refers to a CI repository secret"


def _assert_real_resource_params(source: Any, documented: dict[str, list[str]], where: str) -> None:
    for resource_name, params in documented.items():
        assert resource_name in source.resources, f"{where} documents an unknown resource: {resource_name}"
        signature = resource_signature(source, resource_name).parameters
        for param in params:
            assert param in signature, f"{where} documents {resource_name}.{param}, which the resource does not take"


def _commented_resource_params(config_example: str, prefix: str) -> dict[str, list[str]]:
    """Parse the commented-out `# [<prefix><resource>]` and `# [<prefix><resource>.<param>]` blocks into resource → params.

    A dotted section is a table-valued argument — `locality_week_summary.body` — so the
    section itself names the param, and the keys under it are the argument's contents.
    """
    documented: dict[str, list[str]] = {}
    current: str | None = None
    for line in config_example.splitlines():
        section = re.match(rf"^#\s*\[{re.escape(prefix)}(\w+)(?:\.(\w+))?\]", line)
        if section:
            resource_name, param = section.group(1), section.group(2)
            documented.setdefault(resource_name, [])
            if param:
                documented[resource_name].append(param)
                current = None
            else:
                current = resource_name
            continue
        param_line = re.match(r"^#\s*(\w+)\s*=", line)
        if param_line and current:
            documented[current].append(param_line.group(1))
    return documented


def _readme_toml_blocks() -> list[dict[str, Any]]:
    """Every ```toml fenced block in the README, parsed. The first is secrets.toml, the second config.toml."""
    blocks = re.findall(r"```toml\n(.*?)```", README.read_text(), re.DOTALL)
    assert blocks, "Expected the README quick start to show secrets.toml"
    return [tomllib.loads(block) for block in blocks]
