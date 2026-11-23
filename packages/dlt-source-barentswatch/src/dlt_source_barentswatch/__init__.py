"""dlt source package for the BarentsWatch APIs.

One source per API, each in its own module and named after it — `fishhealth` so far. They
share this package because they share a supplier: one OAuth client, one base URL, one token
endpoint, and BarentsWatch's request that calls are made one at a time, which only holds if
the caller sees them all.
"""

from importlib.metadata import version

from dlt_source_barentswatch.fishhealth import fishhealth_source
from dlt_source_barentswatch.weeks import (
    FIRST_YEAR,
    WeekRange,
    current_iso_week,
    last_n_weeks,
    weeks_in_year,
)

__version__ = version("dlt-source-barentswatch")
__all__ = [
    "FIRST_YEAR",
    "WeekRange",
    "current_iso_week",
    "fishhealth_source",
    "last_n_weeks",
    "weeks_in_year",
]
