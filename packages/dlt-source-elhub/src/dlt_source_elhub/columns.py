"""Column hints: the API's own field names, typed per `specs/meta-metering-points.json`."""

from dlt.common.schema.typing import TTableSchemaColumns

METERING_POINT_COLUMNS: TTableSchemaColumns = {
    "id": {"data_type": "text", "nullable": False},
    "type": {"data_type": "text"},
}

# `meteringPointId` is the id of the point the value is nested under, named as Elhub's other datasets name it.
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
