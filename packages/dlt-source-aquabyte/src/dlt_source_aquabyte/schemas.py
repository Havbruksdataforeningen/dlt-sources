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
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    id: str
    name: str
    governmentSiteNumber: int | None = None
    external_site_id: str | None = None
    pens: list[Pen] = Field(default_factory=list)


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


class WeightDistModel(AquabyteModel):
    interval: list[float] = Field(default_factory=list)
    distribution: list[float] = Field(default_factory=list)


class BiomassDailyModel(AquabyteModel):
    penId: str
    date: str
    sampleSize: float | None = None
    avgWeight: float | None = None
    kFactor: float | None = None
    cv: float | None = None
    weightDist: WeightDistModel | None = None


class BiomassHarvestReport(AquabyteModel):
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
    packedWeightDistribution: dict[str, float] = Field(default_factory=dict)
    roundWeightDistribution: dict[str, float] = Field(default_factory=dict)
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


class WelfareScoreDetail(AquabyteModel):
    """Documentation model for one welfare category inside a `WelfareScoresRecord`.

    Not used to validate rows — `welfare_scores` lands the whole nested object as a
    single JSON column (see `WelfareScoresRecord`) — but it is the shape a consumer's
    transform layer will find there. `active` and `healed` are keyed by the score
    bands the API uses literally: `"1"`, `"2"`, `"3"`.
    """

    active: dict[str, float]
    nothing: float
    sampleSize: float
    healed: dict[str, float] | None = None


class WelfareScoresRecord(AquabyteModel):
    """A `/welfareScores` record exactly as the API returns it.

    `welfareScores` maps a category name to a `WelfareScoreDetail` object (or null).
    It is deliberately typed as a plain mapping rather than a fixed list of
    categories: a category the API adds later must land untouched, and the resource
    sets `max_table_nesting=0` so the whole mapping becomes one JSON column anyway.
    Flattening it into one row per category is the consumer's transform.

    The categories the spec documents today: bodyWound, scaleLoss, snoutWound,
    maturation, eyeBleeding, eyeClouding, exophthalmos, opercularDamage,
    backDeformity, pelvicFin, pectoralFin, caudalFin, analFin, dorsalFin,
    upperJawDeformity, lowerJawDeformity, breathingMouth, mechHeadWound.
    """

    penId: str
    date: str
    welfareScores: dict[str, Any] | None = None
