"""Pydantic models generated from the Aquabyte API v3 OpenAPI spec."""

from pydantic import BaseModel


class Pen(BaseModel):
    id: str
    name: str
    penCode: str | None
    isActive: bool
    external_id: str | None = None


class Site(BaseModel):
    id: str
    name: str
    governmentSiteNumber: int | None
    external_site_id: str | None = None
    pens: list[Pen]


class SitesResponse(BaseModel):
    sites: list[Site]


class EnvironmentalDataPoint(BaseModel):
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


class EnvironmentalDataLive(BaseModel):
    penId: str | None = None
    time: str
    temperature: float | None = None
    cameraDepth: float | None = None
    oxygenPct: float | None = None
    salinity: float | None = None


class WeightDistModel(BaseModel):
    interval: list[float]
    distribution: list[float]


class BiomassDailyModel(BaseModel):
    penId: str
    date: str
    sampleSize: float | None = None
    avgWeight: float | None = None
    kFactor: float | None = None
    cv: float | None = None
    weightDist: WeightDistModel | None = None


class BiomassHarvestReport(BaseModel):
    penId: str
    mainReport: bool
    asOfDate: str
    lastFeedingDate: str
    slaughterStartDate: str
    slaughterEndDate: str
    temperature: float
    lossFactor: float
    packingMethod: str | None
    measurementCount: int
    coefficientOfVariation: float
    avgPackedWeightGrams: float
    avgRoundWeightGrams: float
    superiorRate: float
    packedWeightDistribution: dict[str, float]
    roundWeightDistribution: dict[str, float]
    createdAt: str


class LiceCount(BaseModel):
    penId: str
    date: str
    sampleSize: float
    adultFemale: float | None
    adultFemaleConverted: float | None
    mobile: float | None
    mobileConverted: float | None
    caligus: float | None


class BehaviorSwimSpeed(BaseModel):
    penId: str
    fromTime: str
    toTime: str
    swimSpeedsampleSize: float
    swimSpeed: float | None
    swimTiltsampleSize: float
    swimTilt: float | None


class BehaviorBreathingIndex(BaseModel):
    penId: str
    fromTime: str
    toTime: str
    sampleSize: float
    breathingIndex: float | None


class WelfareScoreProportions(BaseModel):
    score_1: float
    score_2: float
    score_3: float

    model_config = {"populate_by_name": True}

    def __init__(self, **data: float):
        # Map numeric keys "1", "2", "3" to score_1, score_2, score_3
        mapped = {}
        for key, value in data.items():
            if key == "1":
                mapped["score_1"] = value
            elif key == "2":
                mapped["score_2"] = value
            elif key == "3":
                mapped["score_3"] = value
            else:
                mapped[key] = value
        super().__init__(**mapped)


class WelfareScoreDetail(BaseModel):
    active: WelfareScoreProportions
    nothing: float
    sampleSize: float
    healed: WelfareScoreProportions | None = None


class WelfareScoreRow(BaseModel):
    """Flat output model for unpivoted welfare scores (one row per pen+date+category)."""

    penId: str
    date: str
    category: str
    activeScore1: float
    activeScore2: float
    activeScore3: float
    healedScore1: float | None = None
    healedScore2: float | None = None
    healedScore3: float | None = None
    nothing: float
    sampleSize: float
