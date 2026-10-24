"""Project-wide analytical constants.

Everything here is a documented *rule* (thresholds, definitions, labels), never a
result. Results are always computed from the data at run time.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
SOURCES = {
    "wb_pm25": {
        "name": "World Bank — Daily City-Level PM2.5 Estimates 2018–2026 (Global PM2.5 Watch)",
        "short": "World Bank PM2.5 (modelled)",
        "url": "https://datacatalog.worldbank.org/search/dataset/0067162/daily-city-level-air-pollution-pm2-5-estimates-2018-2026",
        "file_url": "https://datacatalogfiles.worldbank.org/ddh-published/0067162/DR0096340/"
                    "PM25_Middle_East_North_Africa_Afghanistan_Pakistan.zip",
        "license": "CC BY-SA 4.0",
        "value_type": "modelled",
        "resolution": "daily",
        "description": "Machine-learning estimates combining IQAir monitors, TROPOMI satellite data, "
                       "ERA5 reanalysis, EDGAR emissions and geographic covariates.",
    },
    "hf_aq": {
        "name": "Pakistan Air Quality & Weather (10 Cities) — Kaggle dataset mirrored on Hugging Face",
        "short": "Kaggle/HF hourly AQ (modelled, probable CAMS)",
        "url": "https://huggingface.co/datasets/jason1966/ahsanneural_pakistan-air-quality-and-weather-10-cities",
        "file_url": "https://huggingface.co/datasets/jason1966/ahsanneural_pakistan-air-quality-and-weather-10-cities/"
                    "resolve/main/pakistan_air_quality_final_clean.csv",
        "license": "Unknown (not stated by uploader)",
        "value_type": "modelled",
        "resolution": "hourly",
        "description": "Hourly pollutants and weather for 10 cities. Provenance is undocumented; variable names "
                       "match the Open-Meteo Air Quality API (CAMS model), so values are treated as modelled.",
    },
    "openmeteo_era5": {
        "name": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
        "short": "Open-Meteo ERA5 weather (reanalysis)",
        "url": "https://open-meteo.com/en/docs/historical-weather-api",
        "file_url": "https://archive-api.open-meteo.com/v1/archive",
        "license": "CC BY 4.0 (Open-Meteo API data); ERA5 from Copernicus C3S",
        "value_type": "modelled",
        "resolution": "daily",
        "description": "ERA5 0.25° reanalysis daily aggregates, local day (Asia/Karachi), fetched once "
                       "and stored locally.",
    },
}

VALUE_TYPES = ("measured", "modelled", "synthetic")

# ---------------------------------------------------------------------------
# Province labels for World Bank ADM1 codes.
# The source only provides opaque codes. Labels were assigned by locating the
# undisputed provincial/federal capital inside each code (see docs/methodology.md):
#   PAK002 contains Quetta, PAK003 Islamabad, PAK005 Peshawar, PAK006 Lahore,
#   PAK007 Hyderabad/Sukkur/Larkana. The mapping is verified at pipeline run time.
# ---------------------------------------------------------------------------
ADM1_LABELS = {
    "PAK002": "Balochistan",
    "PAK003": "Islamabad Capital Territory",
    "PAK005": "Khyber Pakhtunkhwa",
    "PAK006": "Punjab",
    "PAK007": "Sindh",
}
ADM1_ANCHOR_CITIES = {
    "PAK002": "Quetta",
    "PAK003": "Islamabad",
    "PAK005": "Peshawar",
    "PAK006": "Lahore",
    "PAK007": "Hyderabad",
}

# ---------------------------------------------------------------------------
# Seasons (project definition, aligned with the South Asian monsoon cycle)
# ---------------------------------------------------------------------------
SEASON_BY_MONTH = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring",
    5: "Pre-monsoon", 6: "Pre-monsoon",
    7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
    10: "Post-monsoon", 11: "Post-monsoon",
}
SEASON_ORDER = ["Winter", "Spring", "Pre-monsoon", "Monsoon", "Post-monsoon"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------------------
# Validation rules: physically plausible ranges (inclusive). Values outside are
# *invalid* and excluded; values inside but statistically extreme are *outliers*
# and are flagged, never silently dropped.
# ---------------------------------------------------------------------------
PLAUSIBLE_RANGES = {
    "pm25": (0.0, 1500.0),            # µg/m³
    "pm10": (0.0, 3000.0),            # µg/m³
    "carbon_monoxide": (0.0, 50000.0),  # µg/m³
    "nitrogen_dioxide": (0.0, 2000.0),  # µg/m³
    "sulphur_dioxide": (0.0, 2000.0),   # µg/m³
    "ozone": (0.0, 1000.0),             # µg/m³
    "dust": (0.0, 10000.0),             # µg/m³
    "temperature": (-50.0, 60.0),       # °C
    "temperature_max": (-50.0, 60.0),
    "temperature_min": (-50.0, 60.0),
    "dew_point": (-60.0, 40.0),         # °C
    "humidity": (0.0, 100.0),           # %
    "precipitation": (0.0, 500.0),      # mm (per hour for hourly, per day for daily)
    "wind_speed": (0.0, 200.0),         # km/h
    "wind_speed_max": (0.0, 300.0),     # km/h
    "wind_direction": (0.0, 360.0),     # degrees
    "pressure": (500.0, 1100.0),        # hPa
    "latitude": (23.0, 37.5),           # Pakistan bounding box (generous)
    "longitude": (60.0, 78.0),
}

UNITS = {
    "pm25": "µg/m³", "pm10": "µg/m³", "carbon_monoxide": "µg/m³", "nitrogen_dioxide": "µg/m³",
    "sulphur_dioxide": "µg/m³", "ozone": "µg/m³", "dust": "µg/m³",
    "temperature": "°C", "temperature_max": "°C", "temperature_min": "°C", "dew_point": "°C",
    "humidity": "%", "precipitation": "mm", "wind_speed": "km/h", "wind_speed_max": "km/h",
    "wind_direction": "°", "pressure": "hPa",
}

LABELS = {
    "pm25": "PM2.5", "pm10": "PM10", "carbon_monoxide": "CO", "nitrogen_dioxide": "NO₂",
    "sulphur_dioxide": "SO₂", "ozone": "O₃", "dust": "Dust",
    "temperature": "Temperature", "temperature_max": "Max temperature", "temperature_min": "Min temperature",
    "dew_point": "Dew point", "humidity": "Relative humidity", "precipitation": "Precipitation",
    "wind_speed": "Wind speed", "wind_speed_max": "Max wind speed", "wind_direction": "Wind direction",
    "pressure": "Surface pressure",
}

POLLUTANTS = ["pm25", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust"]
WEATHER_VARS = ["temperature", "humidity", "wind_speed", "precipitation", "pressure", "dew_point"]

# ---------------------------------------------------------------------------
# Aggregation and completeness rules
# ---------------------------------------------------------------------------
MIN_HOURS_PER_DAY = 18          # hourly -> daily mean requires >= 75 % of hours
MIN_DAYS_PER_MONTH = 20         # daily -> monthly mean
MIN_MONTHS_PER_YEAR = 11        # monthly -> annual mean (WB drops each month's last day by design)
LOCAL_TZ = "Asia/Karachi"

# Outlier rule (flag only): robust z-score on log(PM2.5) within each city
OUTLIER_ROBUST_Z = 3.5

# Model-artifact screening (World Bank series; see docs/methodology.md)
ANNUAL_CONST_REL_TOL = 0.005     # consecutive annual means within 0.5 % of each other count as "fixed"
ARTIFACT_MIN_FIXED_YEARS = 3     # flag when >= 3 consecutive complete years share the same annual mean
ARTIFACT_BREAK_T = 10.0          # flag abrupt shifts with screening Welch t >= 10 ...
ARTIFACT_BREAK_REL = 0.30        # ... and size >= 30 % of the city's mean level

# Statistical defaults
ALPHA = 0.05
WEATHER_CITY_TOP_N = 20          # Open-Meteo weather fetched for the N most populous WB cities
OVERLAP_MAX_KM = 25.0            # source-to-source city matching radius

# WHO 2021 Air Quality Guideline reference values (reference lines only; not AQI)
WHO_PM25_ANNUAL = 5.0
WHO_PM25_24H = 15.0
