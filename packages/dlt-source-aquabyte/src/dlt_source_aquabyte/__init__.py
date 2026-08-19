"""dlt source package for the Aquabyte API v3."""

from importlib.metadata import version

from dlt_source_aquabyte.aquabyte import aquabyte_source

__version__ = version("dlt-source-aquabyte")
__all__ = ["aquabyte_source"]
