"""Column hints per resource — the API's own field names, typed per `specs/openapi.json`.

Why they are here at all, and what they do not cover: `REFERENCE.md#column-types`.
"""

from dlt.common.schema.typing import TTableSchemaColumns

# `nullable: False` marks the fields the spec requires and forbids to be null. Nested
# fields get no hint, so `max_table_nesting` alone decides their shape.
# `tests/test_mock_fidelity.py` checks every entry against the spec.

SITE_COLUMNS: TTableSchemaColumns = {
    "id": {"data_type": "text", "nullable": False},
    "name": {"data_type": "text", "nullable": False},
    "governmentSiteNumber": {"data_type": "bigint"},
    "external_site_id": {"data_type": "text"},
}

ENVIRONMENTAL_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "temperatureAvg": {"data_type": "double"},
    "cameraDepthAvg": {"data_type": "double"},
    "cameraDepthMin": {"data_type": "double"},
    "cameraDepthMax": {"data_type": "double"},
    "oxygenPct": {"data_type": "double"},
    "salinity": {"data_type": "double"},
    "fishDensity": {"data_type": "double"},
}

ENVIRONMENTAL_LATEST_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text"},
    "time": {"data_type": "text", "nullable": False},
    "temperature": {"data_type": "double"},
    "cameraDepth": {"data_type": "double"},
    "oxygenPct": {"data_type": "double"},
    "salinity": {"data_type": "double"},
}

BIOMASS_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double"},
    "avgWeight": {"data_type": "double"},
    "kFactor": {"data_type": "double"},
    "cv": {"data_type": "double"},
}

HARVEST_REPORT_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "mainReport": {"data_type": "bool", "nullable": False},
    "asOfDate": {"data_type": "text", "nullable": False},
    "lastFeedingDate": {"data_type": "text", "nullable": False},
    "slaughterStartDate": {"data_type": "text", "nullable": False},
    "slaughterEndDate": {"data_type": "text", "nullable": False},
    "temperature": {"data_type": "double", "nullable": False},
    "lossFactor": {"data_type": "double", "nullable": False},
    "packingMethod": {"data_type": "text"},
    "fishType": {"data_type": "text"},
    "measurementCount": {"data_type": "bigint", "nullable": False},
    "coefficientOfVariation": {"data_type": "double", "nullable": False},
    "avgPackedWeightGrams": {"data_type": "double", "nullable": False},
    "avgRoundWeightGrams": {"data_type": "double", "nullable": False},
    "superiorRate": {"data_type": "double", "nullable": False},
    "createdAt": {"data_type": "text", "nullable": False},
}

LICE_COUNT_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "adultFemale": {"data_type": "double"},
    "adultFemaleConverted": {"data_type": "double"},
    "mobile": {"data_type": "double"},
    "mobileConverted": {"data_type": "double"},
    "caligus": {"data_type": "double"},
}

SWIM_SPEED_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "swimSpeedsampleSize": {"data_type": "double", "nullable": False},
    "swimSpeed": {"data_type": "double"},
    "swimTiltsampleSize": {"data_type": "double", "nullable": False},
    "swimTilt": {"data_type": "double"},
}

BREATHING_INDEX_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "fromTime": {"data_type": "text", "nullable": False},
    "toTime": {"data_type": "text", "nullable": False},
    "sampleSize": {"data_type": "double", "nullable": False},
    "breathingIndex": {"data_type": "double"},
}

WELFARE_SCORES_COLUMNS: TTableSchemaColumns = {
    "penId": {"data_type": "text", "nullable": False},
    "date": {"data_type": "text", "nullable": False},
}
