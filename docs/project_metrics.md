# Project metrics

_Measured 2026-10-24 18:57 UTC by `scripts/project_metrics.py`._

## Code

| Area | Files | Lines |
|---|---|---|
| src/data | 6 | 952 |
| src/analysis | 8 | 1,199 |
| src/visualization | 4 | 963 |
| src/ui + utils | 6 | 545 |
| pages + app.py | 11 | 987 |
| scripts | 8 | 811 |
| tests | 7 | 738 |
| **Total Python** | 51 | 6,195 |

## Visualisation library

- 40 chart functions (3 geographic): `city_ranking_bar`, `city_interval_dots`, `province_box`, `multi_city_lines`, `national_band`, `annual_lines`, `yoy_heatmap`, `trend_chart`, `trend_forest`, `calendar_heatmap`, `month_city_heatmap`, `season_box`, `month_profile_chart`, `weekday_chart`, `hour_profile_chart`, `histogram`, `ecdf_chart`, `box_violin`, `percentile_chart`, `outlier_timeline`, `exceedance_bar`, `weather_scatter`, `correlation_heatmap`, `lag_chart`, `city_correlation_dots`, `missingness_heatmap`, `completeness_bar`, `observations_by_month`, `gap_strip`, `exclusion_chart`, `source_timeline`, `source_comparison_scatter`, `diurnal_alignment_chart`, `sensitivity_ranks`, `effect_size_chart`, `artifact_annual_chart`, `break_date_chart`, `city_metric_map`, `trend_map`, `coverage_map`
- 10 dashboard pages

## Data (from pipeline_manifest.json)

- `wb_daily`: rows = 948,183, cities = 339, date_min = 2018-10-01, date_max = 2026-08-30
- `hf_hourly`: rows = 21,840, cities = 10
- `hf_daily`: rows = 910
- `weather_daily`: rows = 63,602, cities = 22
- `wb_weather_daily`: rows = 61,534
- `source_overlap`: rows = 880

## Tests

- 69 test functions in 7 files (parametrised cases expand this number when run).
- Last full run: `89 passed in 87.57s (0:01:27)`
