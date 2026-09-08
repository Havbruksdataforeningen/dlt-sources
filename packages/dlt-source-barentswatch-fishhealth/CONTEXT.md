# BarentsWatch Fish Health

BarentsWatch republishes what Norwegian fish farms report to the authorities, and their Fish Health API serves it per locality and ISO week. This package is true to that API: the terms below are BarentsWatch's, and we keep their meaning even where a member company uses a different word internally. Where the API's own field names are Norwegian regulatory concepts, the Norwegian term is given for recognition.

Shared repository terms are in [CONTEXT-MAP.md](../../CONTEXT-MAP.md).

## Language

### Suppliers and authorities

**BarentsWatch**:
The Norwegian public service that collects and republishes data about the sea and the coast, run by the Norwegian Coastal Administration. It operates several APIs; the Fish Health API is one of them, and this package reads only that one. BarentsWatch does not produce the fish health data — it republishes what the authorities below hold.

**Fish Health API**:
BarentsWatch's API for lice, treatments, diseases, escapes and licences per locality, at `https://www.barentswatch.no/bwapi/`. Its OpenAPI document calls itself `v1`; its paths carry `/v1/` and `/v2/` prefixes of their own. Norwegian: Fiskehelse.
_Avoid_: BarentsWatch API (there are several), Fiskehelse in English text

**Mattilsynet**:
The Norwegian Food Safety Authority, to which farms report lice counts and treatments weekly. The lice data in the API are their raw reports, updated nightly, not corrected before publishing. Referred to by its Norwegian name, because that is how the reports and the regulations name it.
_Avoid_: NFSA

**Aquaculture register**:
Fiskeridirektoratet's (the Norwegian Directorate of Fisheries') register of licences and localities, Akvakulturregisteret. The API's `aquaCultureRegister` on a weekly report is the locality's entry in it: **licences** (`licenseNo`, `licensee`, `capacity`, `species`, `productionType`), **organizations** holding them, and the locality's own capacity. A licence is granted to a licensee and is valid for one or more localities.
_Avoid_: permit, concession (the API says license)

**Organisation**:
A company holding licences, identified by its nine-digit organisation number from Brønnøysundregistrene (the Norwegian company register). The API returns it as `organizationNo` in a detailed row's `aquaCultureRegister.organizations`, and the summary's `organization` filter takes one such number per request; `organizations` on `locality_week_summary` is a list of them. A locality can belong to several organisations, which is why the source does not write the filter value back into the row. Norwegian: organisasjonsnummer.
_Avoid_: company number, org id

### Places

**Locality**:
An aquaculture locality — one licensed place in the sea or on land where fish are held. The API's word, and the unit everything is reported per. Identified by `localityNo`, the locality number from the aquaculture register, which is the same number the industry and the authorities use. Norwegian: lokalitet, lokalitetsnummer.
_Avoid_: site, farm, facility (the spec's prose says "aquaculture site"; its field names say locality, and so does everyone in Norway)

**Salmonoid locality**:
A locality with a licence for a salmonoid species — salmon, trout, char. `GET /v1/geodata/fishhealth/localitieswithsalmonoids` lists them, about 2 000, and lice reporting applies to them. The `localities_with_salmonoids` resource is that list, and `locality_week` iterates over it.
_Avoid_: active locality (a salmonoid locality can be fallow)

**Locality list**:
The API has two, with similar names, and the source exposes both as resources named after their endpoints. `GET /v1/geodata/fishhealth/localities` is every aquaculture locality in the register, salmonoid or not — about 2 700 — with municipality number and name and the register version; the `localities` resource. `GET /v1/geodata/fishhealth/localitieswithsalmonoids` is the salmonoid localities only, number and name — about 2 000; the `localities_with_salmonoids` resource, the one the weekly detail is requested for.
_Avoid_: the locality list, locality table (say which)

**Production area**:
One of the thirteen zones the Norwegian coast is divided into for regulating salmon farming capacity, the traffic-light system, numbered 1 to 13 from south to north. Norwegian: produksjonsområde. A detailed weekly report carries the locality's as `productionArea` (`id`, `name`, `color`); the summary's `productionArea` filter takes that `id`, one per request, and the source writes the requested id into each summary row as `productionArea`, an integer, because the row does not carry it.
_Avoid_: zone (that word is used for PD zones)

**PD zone**:
The national zoning for pancreas disease: `pdZoneId` is `"pd"` (inside the PD zone, PD-sonen) or `"surveillance"` (the surveillance zone, PD-overvåkningssone), or null.

**Control area**:
An area declared by Mattilsynet around a disease outbreak, with restrictions on the localities inside it. Norwegian: kontrollområde. `controlAreas` names the disease, the type of area and the regulation that created it.
_Avoid_: quarantine zone

**Export restriction area**:
An area whose localities are under an export restriction for the week. `exportRestrictionAreas` carries links by `localityNo`, `year` and `week`.

### Time

**ISO week**:
The API's unit of time: a year and a week number under ISO 8601, so week 1 is the week with the year's first Thursday and a year has 52 or 53 weeks. `weeks_in_year(year)` says which. A week is addressed as `{year}/{week}` in the path, and lands as the `year` and `week` columns.
_Avoid_: calendar week, reporting week

**Locality-week**:
One locality in one ISO week — one request to the detailed weekly endpoint, and one row of `locality_week` or of `locality_week_summary`. Keyed by `localityNo`, `year`, `week` in both.
_Avoid_: report (a locality-week row exists for fallow weeks too, when nothing was reported)

**Locality-week summary**:
The shorter form of a locality-week, `LocalityWeekReportV2`, from `POST /v2/geodata/fishhealth/locality/{year}/{week}` — a `POST` that only reads: the filter is a JSON body, and nothing is stored. One request answers every locality matching the filter for the week, and each is one row of `locality_week_summary`: the same lice report as the detailed row, diseases and lice treatments as names only (`MEDIKAMENTELL`, `IKKE_MEDIKAMENTELL`, `RENSEFISK`), `hasSalmonoidLicense`, `isSlaughterHoldingCage` — and none of the register, zone or escape fields.
_Avoid_: aggregate (it is per locality, not a total), site summary (the spec's prose; the package says locality)

**Filtered locality**:
`isFiltered` on a summary row says whether the locality matched the filter. It only carries information with `tagFilteredLocalities: true` in `filters`, which makes the API return every locality and tag the matches instead of dropping the rest; without it, every row returned is a match.

**Week range**:
An inclusive span of ISO weeks, `WeekRange(start_year, start_week, end_year, end_week)`. The one argument both weekly resources need; there is no cursor and no window parameter. `FIRST_YEAR`, 2012, is the earliest year the API answers for.
_Avoid_: window, period, interval

**Lookback**:
The number of complete weeks a scheduled load re-requests each run, `last_n_weeks(n)`. Reports arrive late and the API is updated nightly, so recent weeks are re-loaded and merged rather than fetched once. The current week is not in the lookback.
_Avoid_: overlap, catch-up

### Lice

**Lice report**:
The locality's weekly salmon-lice count as reported to Mattilsynet: `liceReport`. Carries `hasReported`, `isFallow`, the four counts below and `seaTemperature`. Norwegian: lakselusrapport.
_Avoid_: lice count (that is one number in it)

**Adult female lice**, **mobile lice**, **stationary lice**, **total lice**:
The four counts in a lice report, each an **average per fish** for the week (`average`), the previous week's average (`averageOfPreviousWeek`) and a **trend**: `Stable`, `Increasing` or `Decreasing`. Adult female lice is the count the regulations set limits on. Norwegian: voksne hunnlus, bevegelige lus, fastsittende lus.
_Avoid_: lice per fish as a column name (the API says average)

**Fallow**:
A locality with no fish. The API sets `isFallow` when a locality obliged to report has not reported for four or more consecutive weeks, and assumes it holds no fish; it is then exempt from lice reporting. A fallow week is still a row, with `hasReported: false` and null averages. Norwegian: brakklagt.
_Avoid_: inactive, empty

**Lice treatment**:
A treatment against lice reported for the week, under `liceTreatments`, one list or object per kind: **medicinal** (a substance, with concentration and amount; typed `BADEBEHANDLING` bath, `FORBEHANDLING` in-feed, or `ANNEN_BEHANDLING` other), **non-medicinal** (typed `TERMISK_BEHANDLING` thermal, `MEKANISK_BEHANDLING` mechanical, `FERSKVANNSBEHANDLING` freshwater, or `ANNEN_BEHANDLING`), **bath** and **in-feed** as their own lists, **combination** (medicinal and non-medicinal together), **cleaner fish** (wrasse or lumpfish stocked in the pens; not reported after week 16 of 2018) and **mechanical removal** (a method name). Each says whether it covered the entire locality or a number of cages. The enum values are Norwegian, as Mattilsynet's reporting form names them.
_Avoid_: delousing, deworming

**Chitin synthesis inhibitor**:
A class of in-feed lice medicine. `daysSinceLastChitinSynthesisInhibitorTreatment` counts from the last such treatment, which matters because the regulations restrict how often it can be used at a locality.

### Fish health

**Disease**:
A disease case at the locality, under `diseases`: a name from the API's enum, a status (`SUSPECTED`, `DIAGNOSED`, `DISPROVED`), the dates of suspicion, diagnosis, emptying and closure, and how it was closed. The names are Norwegian regulatory names in upper snake case — `PANKREASSYKDOM` is pancreas disease (PD), `INFEKSIOES_LAKSEANEMI` is infectious salmon anaemia (ILA in Norwegian, ISA in English). Disease information comes from Mattilsynet and the Norwegian Veterinary Institute.
_Avoid_: outbreak (the API has statuses; a suspicion is not an outbreak)

**Farmed fish escape**:
An escape incident at the locality: species, date, a count or an estimate and its source. Norwegian: rømming.

## Uncertain — confirm with a domain expert

These are used in the API and land as the source yields them, but the definitions above are inferred from field names, the spec's short descriptions and general knowledge of Norwegian aquaculture regulation, not from BarentsWatch documentation we have read:

- **`localityNo` is the aquaculture register's locality number** — assumed, because the spec describes it as "the aquaculture site number" and the register's licence entries link localities by the same field. Not verified against Fiskeridirektoratet's own data.
- **Lice averages are per fish**, as Norwegian lice reporting counts them. The spec says only `average`.
- **`productionArea.color`** — the spec's enum is `green`, `yellow`, `red`, so it is read as the traffic-light status of the production area. Which assessment round it reflects, and how often it changes, is not stated.
- **`isOnLand`** — the spec says "whether the site is on land or at sea"; whether a land-based locality reports lice at all is not stated.
- **Export restriction area** — what the restriction covers, and who declares it, is not described in the spec.
- **`daysSinceLastChitinSynthesisInhibitorTreatment`** — the regulatory limit it relates to is not stated in the spec; the description above is general knowledge.
- **The `FIRST_YEAR` floor of 2012** — measured (2011-W1 is refused, 2012-W1 is served), not documented. Whether every locality's history starts there, or only the API's, is not known.
- **`isFiltered` and `tagFilteredLocalities`** — read from the spec's one-line description of the filter ("include all sites and tag filter matches"); not exercised live.
- **`hasSalmonoidLicense` and `isSlaughterHoldingCage`** — the spec's descriptions ("production license for salmonoid species", "slaughter holding cage license"); how they relate to the register's `productionType` is not stated. Norwegian: slaktemerd, for the second.
- **Production areas numbered south to north** — general knowledge of the traffic-light system; the spec says only that valid values are 1–13.
