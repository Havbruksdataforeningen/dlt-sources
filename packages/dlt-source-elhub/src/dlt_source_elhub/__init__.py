"""dlt source package for Elhub's Energy Data API."""

from importlib.metadata import version

from dlt_source_elhub.elhub import ALL_RETAINED_HISTORY, elhub_source
from dlt_source_elhub.maskinporten import MaskinportenAuth, MaskinportenCredentials

__version__ = version("dlt-source-elhub")
__all__ = ["ALL_RETAINED_HISTORY", "MaskinportenAuth", "MaskinportenCredentials", "elhub_source"]
