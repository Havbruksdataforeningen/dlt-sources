# Elhub

Elhub is the Norwegian data hub for the electricity market, and its Energy Data API reports what the grid companies meter. This package is true to that API: the terms below are Elhub's, and we keep their meaning even where a member company uses a different word internally.

Shared repository terms are in [CONTEXT-MAP.md](../../CONTEXT-MAP.md).

## Language

### Things metered

**Metering point**:
One point where electricity is metered, identified by an 18-digit id (GS1 `målepunkt-ID`). The unit everything in the API hangs on, and the key of `metering_points`. Belongs to one **end user** at a time.
_Avoid_: meter, installation, målepunkt (in code and English text)

**Metering value**:
One metered quantity of energy over one interval of one metering point: `startTime` to `endTime`, `quantityKwh`, a `direction`, a `resolution`. One row of `metering_values_hour`.
_Avoid_: reading, measurement (that is a channel, below), consumption (that is one direction)

**Direction**:
Which way the energy flowed: `Out` of the grid, which is consumption, or `In` to the grid, which is production. One metering point can carry both, so the direction is part of the key.
_Avoid_: type, flow

**Resolution**:
How long one interval is: `PT60M` or `PT15M`. Set per metering point by its grid company, and it can change. Carried on every value, never assumed.
_Avoid_: granularity, frequency, period

**Measurement**:
The channel a value was read from, named like `EH.ELECTRIC.KWH.1.3`. Under `elhub:enduser` only the settled channel of each direction is returned; the thirdparty scope can ask for all of them.
_Avoid_: series, meter channel

### Time

**Insert time**:
`insertDateTime`, when Elhub stored the value. It is the API's filter and this package's cursor: a correction is a new insert of an old interval. When yesterday's values are inserted depends on the grid company, before 07:00 Europe/Oslo; Elhub forwards them to end users by 09:00.
_Avoid_: updated, loaded, received

**Window**:
The usage interval one request asks for, `startDate` to `endDate`, in Europe/Oslo with the offset written out. At most one day without an id, up to the whole **retention** with one.
_Avoid_: range, span, period

**Retention**:
How long Elhub keeps a value: three years and 41 days. Also the widest window and the oldest allowed start. What is older is gone, and no backfill gets it back.
_Avoid_: history limit, max age

### Access

**Scope**:
The Maskinporten permission a token carries. `elhub:enduser` reads your own organisation's metering points; `elhub:thirdparty` reads on behalf of others and needs GLN headers. This package is verified with the first.

**Dataset**:
Elhub's name for one shape of data on one entity, such as `METERING_VALUES_HOUR_RESTRICTED`. Which datasets a scope may read is in the entity's metadata (`specs/meta-metering-points.json`). `_RESTRICTED` means a token is needed.
_Avoid_: endpoint, table

**End user**:
The organisation a metering point belongs to, as Elhub sees it: `endUserId` on a value is its organisation number. The consumer of this package is normally one end user, or a group of them.
_Avoid_: customer, owner

**Consumer org**:
Maskinporten's name for the organisation a token is issued on behalf of, when it is not the client's own: the `consumer_org` claim, an organisation number. It is how one client reads several companies.
_Avoid_: subsidiary, tenant, company id

**Delegation**:
The act, in Altinn, by which one organisation lets another's Maskinporten client use a scope on its behalf. Done by the delegating organisation; without it, `consumer_org` is refused with `MP-251`.

### Requests

**Cursor**:
This package's per-metering-point record of the latest insert time it has loaded, stored in dlt's resource state under the point's id. Not Elhub's term; Elhub has no notion of a client's progress.
_Avoid_: watermark, checkpoint, state (that is where it lives)

**List call**:
The dataset call without an id, which returns every metering point the token reads together with their values in the window. The only way the API lists metering points. A point without values in the window is not listed.
_Avoid_: list endpoint (there is none)

## Uncertain — confirm with Elhub

- **`productCode`** on a value — assumed to identify the product per Elhub's [product identifier](https://dok.elhub.no/e27/product-identifier) list; one value, `8716867000030`, has been seen.
- **Whether a metering point's `resolution` can change over its life**, and what then happens to its history. The key assumes an interval is identified by its `startTime`, so a change leaves no overlap after the next load of the day in question.
