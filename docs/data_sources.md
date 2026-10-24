# Data sources

Three sources were acquired and verified on 2026-10-24. **None contains monitor measurements**: all are
model or reanalysis products, and each is labelled `value_type = "modelled"` in the processed tables.
Sources are cleaned and analysed separately; they are never pooled row-wise.

| ID | Source | Values | Resolution | Licence | Used for |
|---|---|---|---|---|---|
| `wb_pm25` | World Bank — Daily City-Level PM2.5 Estimates 2018–2026 (Global PM2.5 Watch) | PM2.5, modelled | daily, per place | CC BY-SA 4.0 | primary analytical dataset |
| `hf_aq` | Pakistan Air Quality & Weather (10 Cities) — Kaggle dataset mirrored on Hugging Face | PM2.5, PM10, CO, NO₂, SO₂, O₃, dust + weather; modelled (probable CAMS) | hourly | **unknown** | hourly/diurnal views, source comparison |
| `openmeteo_era5` | Open-Meteo Historical Weather API, ERA5 model | temperature, humidity, dew point, wind, precipitation, pressure | daily (local day) | CC BY 4.0 | weather relationships |

## 1. World Bank Global PM2.5 Watch (`wb_pm25`)

- **Catalogue page:** <https://datacatalog.worldbank.org/search/dataset/0067162/daily-city-level-air-pollution-pm2-5-estimates-2018-2026>
- **File used:** `PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip` (≈ 75.5 MB zipped, one ≈ 1 GB CSV)
  <https://datacatalogfiles.worldbank.org/ddh-published/0067162/DR0096340/PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip>
- **Licence:** Creative Commons Attribution-ShareAlike 4.0 (as stated on the catalogue page). Derived tables in
  `data/processed/` inherit the share-alike condition.
- **Method (from the catalogue):** machine-learning estimates combining IQAir monitor data, TROPOMI satellite
  retrievals, ERA5 reanalysis, EDGAR emissions, Köppen–Geiger climate zones, MERIT-DEM elevation and coastal
  indicators.
- **Schema as downloaded:** `wb_region, nam_0, adm0_wb_a3, pm25_iso3, adm1cd_c, geonameid, city, latitude,
  longitude, population, date, pm25`.
- **Units:** the catalogue page does not state units. Values are treated as µg/m³ because (a) PM2.5
  concentrations are conventionally reported in µg/m³, (b) the value range is consistent with published
  PM2.5 levels for South Asia. This is an assumption and is stated wherever values are shown.
- **Pakistan extraction:** rows with `adm0_wb_a3 == "PAK"` are streamed out of the regional CSV by
  `scripts/extract_worldbank_pakistan.py` into `data/raw/worldbank_pm25/worldbank_pm25_pakistan_subset.parquet`.
  The original zip is never modified. The South Asia regional file was **not** downloaded because the MENA file
  explicitly covers Pakistan; whether Pakistan also appears there was not verified.
- **Day boundary / time zone:** not documented by the source.

## 2. Kaggle / Hugging Face hourly dataset (`hf_aq`)

- **Hugging Face mirror (downloaded):**
  <https://huggingface.co/datasets/jason1966/ahsanneural_pakistan-air-quality-and-weather-10-cities>
  → `pakistan_air_quality_final_clean.csv` (3,778,678 bytes)
- **Original Kaggle page (named in the mirror's card):**
  <https://www.kaggle.com/datasets/ahsanneural/pakistan-air-quality-and-weather-10-cities> — the page's
  metadata could not be read without a Kaggle login, so the original description and licence were not verified.
- **Licence:** `unknown` in the Hugging Face card. Treat as **not cleared for redistribution**; it is used
  here for non-commercial analysis only. Remove it from any public deployment if that is a concern
  (the app runs without it — hourly views then show an explained empty state).
- **Provenance:** undocumented. Column names (`pm2_5`, `carbon_monoxide`, `nitrogen_dioxide`,
  `sulphur_dioxide`, `ozone`, `dust`) match the Open-Meteo Air Quality API, whose global pollutant data come
  from the CAMS atmospheric model; values are therefore labelled **modelled**.
- **Known issues found during the audit:** pollutant and weather columns appear to use different time
  references (≈ 6-hour offset in diurnal peaks); Islamabad and Rawalpindi share identical series for most
  variables; source-derived `aqi_category` and calendar columns are dropped and recomputed.

## 3. Open-Meteo ERA5 weather (`openmeteo_era5`)

- **API:** `https://archive-api.open-meteo.com/v1/archive` with `models=era5`, `timezone=Asia/Karachi`.
  Docs: <https://open-meteo.com/en/docs/historical-weather-api>
- **Licence:** Open-Meteo API data are offered under **CC BY 4.0** (<https://open-meteo.com/en/licence>);
  underlying ERA5 data from the Copernicus Climate Change Service.
- **Model:** ERA5 reanalysis, 0.25° grid. A single model is requested (not `best_match`) to keep the series
  homogeneous over 2018–2026.
- **Places fetched:** the 20 most populous World Bank places plus the World Bank place nearest each
  Kaggle/HF city (≤ 25 km): 22 places in total. Fetched **once** by
  `scripts/fetch_openmeteo_weather.py`; raw JSON responses and a manifest (request/grid coordinates,
  retrieval time) are stored in `data/raw/openmeteo_weather/`. The dashboard never calls the API.

## Placement instructions (manual download)

If the automated downloads fail, place files exactly here and run `python scripts/prepare_data.py --extract`:

```
data/raw/worldbank_pm25/PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip
data/raw/hf_pakistan_aq/pakistan_air_quality_final_clean.csv
data/raw/openmeteo_weather/   (run: python scripts/fetch_openmeteo_weather.py)
```

Only the World Bank file is required; the other two sources are optional and the app degrades gracefully
without them.

## Candidates investigated but not used

- **World Bank South Asia regional file** — not needed (Pakistan is in the MENA file).
- **Zenodo / other Kaggle datasets** — not searched exhaustively; no further dataset was added because none
  was verified for provenance, coverage and licence within this build.
