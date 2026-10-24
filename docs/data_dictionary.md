# Data dictionary

All processed tables live in `data/processed/` (Parquet) and are rebuilt by `python scripts/prepare_data.py`.
"Modelled" means model or reanalysis output — **no field in this project is a monitor measurement**.

## `wb_pm25_daily.parquet` — World Bank daily PM2.5 (one row per place per day)

| Field | Type | Unit | Source | Description / limitations |
|---|---|---|---|---|
| `city_id` | category | – | derived | `wb:<geonameid>`; stable key |
| `geonameid` | int | – | WB | GeoNames identifier of the place |
| `city` | category | – | WB | Place name after Unicode/whitespace/case normalisation |
| `city_label` | category | – | derived | Unique display label; shared names get `(Province)` or `(lat°N, lon°E)` |
| `province` | category | – | derived | Label inferred from `adm1_code` (see methodology); not an official boundary join |
| `adm1_code` | category | – | WB `adm1cd_c` | Source first-level admin code (PAK002…PAK007) |
| `latitude`, `longitude` | float | degrees | WB | Place coordinates as supplied (not corrected) |
| `population` | int | persons | WB | GeoNames population; vintage not documented |
| `date` | datetime (naive) | day | WB | Calendar day; day boundary/time zone undocumented by the source |
| `pm25` | float | µg/m³ (assumed) | WB | Modelled daily mean PM2.5; never converted to AQI |
| `source_id` | category | – | derived | Always `wb_pm25` |
| `value_type` | category | – | derived | Always `modelled` |
| `year`, `month` | int | – | derived | Calendar fields from `date` |
| `month_name` | category | – | derived | Jan…Dec |
| `season` | category | – | derived | Winter (Dec–Feb), Spring (Mar–Apr), Pre-monsoon (May–Jun), Monsoon (Jul–Sep), Post-monsoon (Oct–Nov) |
| `day_of_week` | category | – | derived | Monday…Sunday |
| `is_weekend` | bool | – | derived | Saturday or Sunday (see caveat in methodology) |
| `is_outlier` | bool | – | derived | Robust z-score of log PM2.5 within city > 3.5; flagged, not removed |

## `wb_cities.parquet` — one row per World Bank place

| Field | Unit | Description |
|---|---|---|
| `city_id`, `geonameid`, `city`, `city_label`, `adm1_code`, `province`, `latitude`, `longitude`, `population` | – | As above |
| `n_days`, `first_date`, `last_date` | days / date | Coverage of the place |
| `name_ambiguous` | bool | Another GeoNames ID shares the same normalised name (e.g. "Arif Wala"/"Arifwala") |
| `coords_in_bbox` | bool | Coordinates inside a generous Pakistan bounding box |
| `series_group`, `series_group_size` | int | Places whose full daily series is identical share a group (same model grid cell) |
| `is_series_representative` | bool | Most populous member of its series group; used for inferential tests |
| `fixed_annual_run`, `fixed_annual_from`, `fixed_annual_to` | years | Longest run of consecutive complete years with annual means within 0.5 % |
| `break_date`, `break_shift`, `break_shift_rel`, `break_t` | date / µg/m³ / ratio / – | Largest single level shift in deseasonalised monthly anomalies (screening scan) |
| `mean_level` | µg/m³ | Mean of complete monthly means |
| `artifact_flag`, `artifact_reason` | bool / text | Fixed annual mean ≥ 3 years and/or abrupt shift (t ≥ 10 and ≥ 30 % of level) |

## `hf_hourly.parquet` — Kaggle/HF hourly (one row per city per hour)

| Field | Unit | Description / limitations |
|---|---|---|
| `city_id` | – | `hf:<normalised name>` |
| `city`, `latitude`, `longitude` | – / degrees | As supplied |
| `timestamp` | naive datetime | Source hour label, unchanged. Pollutant columns appear to be UTC and weather columns local time (diagnostic in Data Quality) |
| `date`, `hour` | – | Derived from `timestamp` |
| `pm25`, `pm10`, `carbon_monoxide`, `nitrogen_dioxide`, `sulphur_dioxide`, `ozone`, `dust` | µg/m³ | Modelled (probable CAMS); invalid cells set to NaN |
| `temperature` | °C | Hourly 2 m temperature (source undocumented) |
| `humidity` | % | Relative humidity |
| `precipitation` | mm per hour | |
| `wind_speed` | km/h | Units inferred from the Open-Meteo default; not documented by uploader |
| `wind_direction` | ° | |
| `pressure` | hPa | |
| `source_id`, `value_type` | – | `hf_aq`, `modelled` |
| `year`, `month`, `season`, … | – | Calendar fields recomputed from `timestamp` |

## `hf_daily.parquet` — Kaggle/HF aggregated to days

Same variables as hourly. Rule: mean of hourly values (precipitation **summed**, wind direction **circular
mean**) when ≥ 18 valid hours exist for that variable; otherwise NaN. `n_hours` records the hours present.
Day boundaries follow the source's hour labels.

## `weather_daily.parquet` — ERA5 daily weather per World Bank place

| Field | Unit | Description |
|---|---|---|
| `city_id`, `geonameid` | – | World Bank place the weather was fetched for |
| `date` | day | Local (Asia/Karachi) day |
| `temperature`, `temperature_max`, `temperature_min` | °C | 2 m air temperature (daily mean/max/min) |
| `humidity` | % | Daily mean relative humidity at 2 m |
| `dew_point` | °C | Daily mean dew point at 2 m |
| `wind_speed`, `wind_speed_max` | km/h | 10 m wind speed (daily mean / max) |
| `wind_direction` | ° | Dominant 10 m wind direction |
| `precipitation` | mm/day | Daily total |
| `pressure` | hPa | Daily mean surface pressure |
| `grid_latitude`, `grid_longitude`, `grid_elevation_m` | degrees / m | ERA5 grid cell actually used |
| `source_id`, `value_type` | – | `openmeteo_era5`, `modelled` |

## `wb_weather_daily.parquet`

Inner join of `wb_pm25_daily` and `weather_daily` on `(city_id, date)`; all fields of both, plus
`weather_grid_lat`, `weather_grid_lon`, `weather_source_id`.

## `source_overlap_daily.parquet`

| Field | Description |
|---|---|
| `city_id`, `city` | Kaggle/HF city |
| `match_city_id`, `match_city_label`, `distance_km` | Nearest World Bank place (≤ 25 km) |
| `date` | Calendar date present in both sources |
| `pm25_hf` | Kaggle/HF daily mean (µg/m³) |
| `pm25_wb` | World Bank daily value (µg/m³) |
| `n_hours` | Hours behind `pm25_hf` |

The two PM2.5 values stay in separate columns: the table supports comparison only.

## Pipeline outputs

- `exclusions_log.csv` — every exclusion, nulling, flag and transformation: source, step, rule, column,
  rows affected, action, examples.
- `pipeline_manifest.json` — run time, SHA-256 of raw inputs, row counts, rules, ADM1 anchor check.
