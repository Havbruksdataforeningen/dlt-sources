# Mock responses

Real responses from `GET /energy-data/v0/metering-points` with
`dataset=METERING_VALUES_HOUR_RESTRICTED` and the scope `elhub:enduser`, fetched on
2026-10-13 and anonymised: metering point ids, `endUserId` and `quantityKwh` are replaced,
and each list of values is cut to its first rows. Structure, field names, types and the
time format are untouched.

| File | Call | Shows |
|---|---|---|
| `metering_points_hour_all.json` | no id, no dates | every metering point of one company, last 24 hours; one `PT60M` and one `PT15M` point |
| `metering_points_hour_by_id.json` | with id and `startDate`/`endDate` | one metering point over a window |

An empty result is `204 No Content` with no body, which `tests/conftest.py` serves
directly rather than from a file. The other datasets answer `403` to this scope, so there
is no fixture for them.

Keep the files as the API sends them. Shapes that look odd are probably the API's, and the
place to record one is [API quirks worth knowing](../../specs/README.md#api-quirks-worth-knowing),
next to the spec it departs from.
