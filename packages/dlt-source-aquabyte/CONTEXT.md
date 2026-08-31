# Aquabyte

Aquabyte supplies camera-based monitoring of farmed salmon in sea pens, and their API reports what the cameras observe. This package is true to that API: the terms below are Aquabyte's, and we keep their meaning even where a member company uses a different word internally.

Shared repository terms are in [CONTEXT-MAP.md](../../CONTEXT-MAP.md).

## Language

### Places

**Site**:
A licensed farming location holding a group of pens. Identified by `id`, with an optional `external_site_id` for the operator's own identifier.
_Avoid_: farm, locality, lokalitet, facility

**Pen**:
One net pen holding a population of fish, belonging to a site. Identified by `id`, with an optional `penCode`. The API accepts the literal value `all` for `penId`, which is the default this package sends.
_Avoid_: cage, merd, unit

**Active pen**:
A pen currently holding fish, and therefore the only kind that returns data. A pen that exists but holds no fish is **inactive**. Most resources return data for active pens only.

### Measurements

**Biomass**:
The daily estimate of fish weight in a pen, including `avgWeight`, `sampleSize`, `kFactor` and `cv`.
_Avoid_: weight, standing stock

**K-factor**:
The condition factor reported alongside biomass — a measure of fish weight relative to length.
_Avoid_: condition score (that is a welfare term, not this)

**CV**:
The coefficient of variation of the weight distribution in a pen. Reported as `cv` on biomass and as `coefficientOfVariation` on a harvest report — the same idea under two names, because the API names them differently.

**Harvest report**:
A per-pen report produced around slaughter, covering the planned or actual harvest: feeding and slaughter dates, temperature, loss factor, packing method, superior rate, and average round and packed weights.
_Avoid_: slaughter report, harvest plan

**Round weight**:
The weight of the whole fish. Distinct from **packed weight**, the weight after processing. The API reports both, in grams.

**Superior rate**:
The share of harvested fish graded as superior quality.

**Lice count**:
A sampled count of sea lice on fish in a pen, split by stage: `adultFemale`, `mobile`, and `caligus`. The `*Converted` fields are the API's own temperature-adjusted values.
_Avoid_: lus, parasite count

**Caligus**:
*Caligus elongatus*, counted separately from salmon lice.
_Avoid_: skottelus (in code and English text)

**Welfare score**:
An assessment of visible damage on fish in a pen, reported per **category** — `bodyWound`, `scaleLoss`, `mechHeadWound` and so on. Which categories exist is the API's call and changes between versions, so the set lives in `specs/openapi.json` and nowhere else; the package never enumerates them. Each category carries counts at severity **score 1, 2 and 3**, split into **active** and **healed** findings.
_Avoid_: health score, injury score

**Environmental data point**:
A pen's environmental readings over a time window (`fromTime`–`toTime`): temperature, camera depth, oxygen, salinity and fish density, as averages. Distinct from **environmental live**, which is the latest single reading at one `time` rather than a window.
_Avoid_: sensor reading, telemetry

**Behaviour**:
The camera-derived measures of how fish are acting, as opposed to how they measure. Two resources: **swim speed** and **breathing index**.

**Breathing index**:
Aquabyte's measure of respiration rate in a pen, used as a stress and gill-health indicator.

### Requests

**Window**:
The timespan one request asks for, as a start and an end: `fromDate`–`toDate` on the date resources, `fromTime`–`toTime` on the time resources. `toDate` is inclusive; `toTime` is exclusive.
_Avoid_: range, span, interval

**Period**:
The API's name for how coarse the rows are: `15min`, `h` or `D`. `D` when none is sent. Only `environmental` and `behaviour_swim_speed` take one.
_Avoid_: grain, granularity, resolution (in code; the README uses "grain" to explain what `period` means)

**Record cap**:
The most records one result set carries, 10 000, after which `nextToken` pages the rest. Documented in `openapi.json`, unlike the window cap — and independent of it: a window the API accepts can still page.
_Avoid_: result cap, page size

**Window cap**:
The widest window the API accepts, per resource and per period, in days. Measured, not documented; the table is `MAX_WINDOW_DAYS`. A wider window is refused, so the source splits it into several requests.
_Avoid_: limit, max range, and **cap** on its own — the API has a record cap and a rate limit too, so the word alone says which limit only by luck

## Uncertain — confirm with a domain expert

These are used in the API and mapped by this package, but the definitions above are inferred from field names and general aquaculture usage, not from Aquabyte documentation we have read:

- **Loss factor** on a harvest report — assumed to be the expected weight loss between live and packed weight.
- **Packing method** — the permitted values are not documented here.
- **Fish density** on an environmental data point — the unit is not stated in the API response.
