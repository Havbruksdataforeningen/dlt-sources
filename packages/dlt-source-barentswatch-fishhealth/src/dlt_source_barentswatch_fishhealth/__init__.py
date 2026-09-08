"""dlt source package for the BarentsWatch Fish Health API."""

from importlib.metadata import version

from dlt_source_barentswatch_fishhealth.barentswatch_fishhealth import barentswatch_fishhealth_source
from dlt_source_barentswatch_fishhealth.weeks import (
    FIRST_YEAR,
    WeekRange,
    current_iso_week,
    last_n_weeks,
    weeks_in_year,
)

__version__ = version("dlt-source-barentswatch-fishhealth")
__all__ = [
    "FIRST_YEAR",
    "WeekRange",
    "barentswatch_fishhealth_source",
    "current_iso_week",
    "last_n_weeks",
    "weeks_in_year",
]
