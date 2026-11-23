# Energy Data API: Usage Guidelines

Text from https://api.elhub.no/energy-data-api/dataset-guidelines and the dataset notes on https://api.elhub.no/energy-data-api/metering-points, fetched 13 Oct 2026. The pages are a JavaScript app, so this is the text as rendered, not a copy of the page. Formatting is ours.

## Date Range Limitations

`startDate` and `endDate` must follow the ISO 8601 format:

- Basic format: `yyyy-MM-dd` (defaults to midnight).
- Full format with timezone offset: `yyyy-MM-dd'T'HH:mm:ssXXX` (must be URL-encoded, e.g. `2023-01-01T00:00:00%2B02:00`).

Behavior:

- Both `startDate` and `endDate` are inclusive in the response.
- If `endDate` is omitted, it is inferred based on the dataset's date policy.
- If `startDate` is omitted, it is inferred based on the dataset's date policy.
- If both are omitted, the API automatically infers a valid default range using the dataset's date policy.
- Each dataset has a date policy that controls how date filtering works. The dataset table shows the applicable date policies for each dataset.
- Some datasets use different date policies depending on whether the request is made with or without an entity id in the path.
- Some datasets also have special-case rules, described in the dataset details.

Date policy terms:

- **Default Window**: the default time span used when one or both dates are missing.
- **Max Window**: the largest allowed time span in a single request.
- **Max Age From Now**: how far back in time data may be requested.

A request must satisfy all applicable limits at the same time. For example, even if a dataset allows a 1-year max window, the requested period may still be rejected if it starts too far back in time.

Examples:

- If a dataset has Default Window = 1 day, and only `endDate` is provided, the API will infer `startDate` as one day earlier, as long as the inferred range is valid.
- If a dataset has Max Window = 1 month, requests larger than one month are not allowed.
- If a dataset has Max Age From Now = 3 years and 41 days, the requested data cannot start earlier than that limit.
- If an inferred date would end up in the future, the API will instead use a valid non-future range or reject the request, depending on the dataset and input.

Not all dataset exports have date filters. The API returns data for the last 3 years.

## Access Control for Protected Datasets

- All datasets with the suffix `_RESTRICTED` contain business-sensitive / private data and require Maskinporten Authentication.
- Only consumers assigned the relevant scope(s) in Maskinporten by Elhub can access protected datasets.
- When accessing a protected dataset, include the following HTTP headers:

      Authorization: Bearer {MASKINPORTEN_ACCESS_TOKEN}
      X-Elhub-GLN: {YOUR_GLN_VALUE}

- As an end-user organization accessing the API with scope `elhub:enduser`, you do not need to include the `X-Elhub-GLN`. Passing of the maskinporten access token is sufficient.
- As a service provider accessing the API with scope `elhub:serviceprovider`, you will need to include `On-Behalf-Of` in the HTTP header in addition to the access token and GLN: `On-Behalf-Of: {GLN_OF_THE_PARTY_YOU_CAN_ACT_ON_BEHALF_OF}`.

## Required headers

The following headers must be included in every query: `Accept` and `User-Agent`. The headers listed above will generally be automatically included, but if they aren't, you will receive error code 403 - Forbidden.

## Accepted methods

Currently accepted HTTP methods: GET, POST.

## Dataset notes: metering points

Scopes, columns and date policies per dataset: `meta-metering-points.json`.

### METERING_VALUES_HOUR_RESTRICTED

Regarding scopes:

- For scope `elhub:enduser`, `metering-point-id` is not required, and `endUserId` cannot be used as a filter parameter.
- For scope `elhub:thirdparty`, `metering-point-id` is required, and `endUserId` can be used as a filter parameter.
- For scope `elhub:thirdparty`, `includeAllMeasurements (Y/N)` can be used as a filter. By default, it is set to 'N', meaning only the settled channels are returned.

Date usage:

- If both `insertDateTime` and `metering-point-id` are provided, the default `startDate`/`endDate` window is 3 years and 41 days unless explicitly specified.

### METERING_VALUES_PER_DIRECTION_MONTH_RESTRICTED

- Data is returned for whole months based on the `startDate` and `endDate` range. For example, if startDate is set to 2023-01-01 and endDate to 2023-03-31, data for January, February, and March 2023 will be returned.
- Data older than 3 years and 41 days is deleted and will be unavailable.
- Only complete months are returned. If a requested month contains incomplete or unavailable data that month will be excluded automatically.

### METERING_VALUES_PER_DIRECTION_YEAR_RESTRICTED

- Data is returned for entire years based on the `startDate` and `endDate` range. For instance, if startDate is 2023-01-01 and endDate is 2025-01-31, data for 2023, 2024, and 2025 will be returned.
- Data older than 3 years and 41 days is deleted and will be unavailable.
- Only complete years are returned. If a requested year contains incomplete or unavailable data that year will be excluded automatically.

### PRODUCTION_REVENUE_PER_YEAR_RESTRICTED

- Unlike other restricted datasets, this dataset is protected using ID-porten's user-controlled data sharing, where end users explicitly consent to access on behalf of an organization.
- Elhub controls which organizations can be granted access.
- The access token must follow ID-porten's access token specification and include Elhub's API host (for example, `https://api.elhub.no`) in the `aud` claim.
- Both a valid access token and the `productionPlantId` query parameter are mandatory.
- The organization number of the power producer must be provided in the `On-Behalf-Of` request header.
