"""Pydantic models mirroring the Aquabyte API v3 schemas (`specs/openapi-v3.1.1.json`).

The models exist for two reasons only:

1. They give dlt proper column types at ingest, so a destination table is well typed
   even when the first page happens to be full of nulls.
2. They document the API's own record shapes — field names and nesting are the API's,
   never renamed or flattened.

Every model allows extra fields (`extra="allow"`), which dlt translates into the
`evolve` column contract: a field the API adds after this release lands in the
destination instead of failing the load. Fields the spec marks nullable default to
``None`` so a field the API stops sending does not fail the load either.

The models deliberately declare **scalar fields only**. A declared nested field
becomes a column hint that dlt honours over `max_table_nesting`, which would silently
override a consumer who raised the setting to get child tables. Nested fields still
land — `extra="allow"` carries them — and their destination shape stays the
consumer's call. See "Nesting" in the README.
"""

from pydantic import BaseModel, ConfigDict


class AquabyteModel(BaseModel):
    """Base for every Aquabyte record model: unknown fields pass through untouched."""

    model_config = ConfigDict(extra="allow")


class Pen(AquabyteModel):
    id: str
    name: str
    penCode: str | None = None
    isActive: bool
    external_id: str | None = None


class Site(AquabyteModel):
    """A `/sites` record. The nested `pens` list is undeclared on purpose — see the
    module docstring; the `pens` transformer unwraps it into its own table."""

    id: str
    name: str
    governmentSiteNumber: int | None = None
    external_site_id: str | None = None


class EnvironmentalDataPoint(AquabyteModel):
    penId: str
    fromTime: str
    toTime: str
    temperatureAvg: float | None = None
    cameraDepthAvg: float | None = None
    cameraDepthMin: float | None = None
    cameraDepthMax: float | None = None
    oxygenPct: float | None = None
    salinity: float | None = None
    fishDensity: float | None = None


class EnvironmentalDataLive(AquabyteModel):
    penId: str | None = None
    time: str
    temperature: float | None = None
    cameraDepth: float | None = None
    oxygenPct: float | None = None
    salinity: float | None = None


class BiomassDailyModel(AquabyteModel):
    """A `/biomass` record. The nested `weightDist` (`interval`/`distribution` arrays)
    is undeclared on purpose — see the module docstring."""

    penId: str
    date: str
    sampleSize: float | None = None
    avgWeight: float | None = None
    kFactor: float | None = None
    cv: float | None = None


class BiomassHarvestReport(AquabyteModel):
    """A `/biomass/harvestReport` record. The `packedWeightDistribution` and
    `roundWeightDistribution` mappings are undeclared on purpose — see the module
    docstring; their keys are open-ended weight buckets."""

    penId: str
    mainReport: bool
    asOfDate: str
    lastFeedingDate: str
    slaughterStartDate: str
    slaughterEndDate: str
    temperature: float
    lossFactor: float
    packingMethod: str | None = None
    measurementCount: int
    coefficientOfVariation: float
    avgPackedWeightGrams: float
    avgRoundWeightGrams: float
    superiorRate: float
    createdAt: str


class LiceCount(AquabyteModel):
    penId: str
    date: str
    sampleSize: float
    adultFemale: float | None = None
    adultFemaleConverted: float | None = None
    mobile: float | None = None
    mobileConverted: float | None = None
    caligus: float | None = None


class BehaviorSwimSpeed(AquabyteModel):
    penId: str
    fromTime: str
    toTime: str
    swimSpeedsampleSize: float
    swimSpeed: float | None = None
    swimTiltsampleSize: float
    swimTilt: float | None = None


class BehaviorBreathingIndex(AquabyteModel):
    penId: str
    fromTime: str
    toTime: str
    sampleSize: float
    breathingIndex: float | None = None


class WelfareScoresRecord(AquabyteModel):
    """A `/welfareScores` record exactly as the API returns it.

    The nested `welfareScores` mapping is undeclared on purpose — see the module
    docstring. It maps a category name to that category's scores (or null): `active`
    and `healed` keyed by the score bands the API uses literally (`"1"`, `"2"`,
    `"3"`), plus `nothing` and `sampleSize`; see `specs/openapi-v3.1.1.json`. Nothing
    here enumerates categories, so a category the API adds later lands untouched.
    """

    penId: str
    date: str
