"""Column hints per resource — the API's own field names, typed per `specs/meta-metering-points.json`.

Why they are here at all, and what they do not cover: `REFERENCE.md#column-types`.
"""

from dlt.common.schema.typing import TTableSchemaColumns

METERING_POINT_COLUMNS: TTableSchemaColumns = {
    "id": {"data_type": "text", "nullable": False},
    "type": {"data_type": "text"},
}

# `meteringPointId` is the one column the API does not put on a value: it is the `id` of the
# metering point the value is nested under, named as Elhub names it on its other datasets.
METERING_VALUES_HOUR_COLUMNS: TTableSchemaColumns = {
    "meteringPointId": {"data_type": "text", "nullable": False},
    "startTime": {"data_type": "text", "nullable": False},
    "endTime": {"data_type": "text", "nullable": False},
    "direction": {"data_type": "text", "nullable": False},
    "quantityKwh": {"data_type": "double"},
    "resolution": {"data_type": "text"},
    "measurementName": {"data_type": "text"},
    "productCode": {"data_type": "bigint"},
    "endUserId": {"data_type": "text"},
    "insertDateTime": {"data_type": "text"},
}
