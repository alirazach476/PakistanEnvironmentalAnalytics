# Findings report — Pakistan Environmental Analytics

_Generated 2026-10-24 18:37 UTC by `scripts/generate_reports.py` from data prepared 2026-10-24. Every number below is computed from the stored datasets._

> **All PM2.5 values are model estimates** (World Bank Global PM2.5 Watch), not monitor measurements. Weather is ERA5 reanalysis. Results describe the model output and are associations, not causal effects.

## 1. Coverage

- World Bank: **339 places**, **01 Oct 2018 – 30 Aug 2026**, **948,183 city-days**; 94 calendar dates are missing for every place, all of them the last day of a month.
- Kaggle/HF hourly: **10 cities**, 06 Nov 2025 – 04 Feb 2026, 21,840 city-hours (licence unknown; treated as modelled).
- ERA5 weather: **22 places**, 61,534 matched PM2.5–weather city-days.

## 2. Levels and rankings

- Median daily PM2.5 across all city-days: **59.4 µg/m³** (mean 68.4).
- 99 % of places have a median above the WHO 24-h guideline (15 µg/m³); the median place exceeds it on 100 % of days.
- Highest medians over the full common period:

| rank | city_label | median | n | artifact_reason |
|---|---|---|---|---|
| 1 | Larkana | 126.1 | 2797 | abrupt level shift |
| 2 | Rahim Yar Khan | 114.9 | 2797 | fixed annual mean + abrupt level shift |
| 3 | Multan | 111.4 | 2797 | fixed annual mean + abrupt level shift |
| 4 | Hingorja | 111.3 | 2797 | abrupt level shift |
| 4 | Setharja Old | 111.3 | 2797 | abrupt level shift |
| 6 | Gambat | 110.6 | 2797 | abrupt level shift |
| 7 | Sukkur | 110.1 | 2797 | fixed annual mean + abrupt level shift |
| 7 | Rohri | 110.1 | 2797 | fixed annual mean + abrupt level shift |
| 9 | Naudero | 109.1 | 2797 | abrupt level shift |
| 10 | Ghotki | 108.5 | 2797 | abrupt level shift |

- **10 of these top 10** are flagged for model artifacts. Excluding all flagged places, the top three are: Khurarianwala (95), Sargodha (93), Ladhewala Waraich (90) µg/m³.

## 3. Seasonality

- Median PM2.5 is highest in **Post-monsoon (72.8 µg/m³)** and lowest in **Monsoon (49.8 µg/m³)**.
- Across 324 cities, p < 0.001 (below α); Kendall's W = 0.64 (large agreement in seasonal ranking). Highest median season: Post-monsoon (75.5 µg/m³); lowest: Monsoon (50.7 µg/m³). 10 of 10 pairwise season contrasts remain below α after Holm correction.

## 4. Trends

- All places: 135 decreasing, 61 increasing, 143 no clear trend (deseasonalised OLS with Newey–West CI, BH-FDR).
- Excluding the 112 artifact-flagged places: 30 decreasing, 60 increasing, 137 no clear trend; median slope +0.42 µg/m³/yr.
- Change 2019 → 2025 (Wilcoxon signed-rank): Median city change -10.9 % (95 % bootstrap CI -17.1 to -5.6 %); 217 cities decreased, 107 increased; p < 0.001 (below α).
- Change 2019 → 2025 (Wilcoxon signed-rank) — artifact-flagged places excluded: Median city change -0.7 % (95 % bootstrap CI -2.4 to +0.8 %); 116 cities decreased, 101 increased; p = 0.037 (below α).

## 5. Weather relationships (within-city Spearman, city = unit)

| variable | raw median ρ | anomaly median ρ | cities | anomaly significant (FDR) |
|---|---|---|---|---|
| temperature | -0.16 | 0.21 | 22 | 18 |
| humidity | -0.20 | -0.28 | 22 | 22 |
| wind_speed | -0.33 | -0.25 | 22 | 21 |
| precipitation | -0.46 | -0.26 | 22 | 22 |
| pressure | 0.27 | -0.02 | 22 | 6 |
| dew_point | -0.34 | -0.14 | 22 | 22 |

- Sign changes between raw and deseasonalised correlations for **temperature, pressure** — the raw association reflects the shared seasonal cycle.
- Correlations use autocorrelation-adjusted effective sample sizes; they are associations, not causal effects, and the PM2.5 model itself uses ERA5 inputs.

## 6. Weekday vs weekend

- Median weekday−weekend difference = -0.23 µg/m³ (95 % bootstrap CI -0.30 to -0.16), i.e. -0.3 % of the typical weekend level; p < 0.001 (below α); rank-biserial = -0.40 (moderate consistency across cities). The difference is consistent but very small in absolute terms; statistical significance here does not imply practical importance.

## 7. Data quality

- **Fixed annual means:** 11 places repeat the same annual mean (within 0.5 %) for ≥ 3 consecutive complete years: Chunian (7 yrs), Rohri (6 yrs), Sukkur (6 yrs), Rahim Yar Khan (6 yrs), Multan (5 yrs), Sialkot (4 yrs), Hadali (4 yrs), Mirpur Khas (3 yrs), Mustafabad (3 yrs), Dipalpur (3 yrs), Abbottabad (3 yrs).
- **Abrupt level shifts:** 106 places; most common month January 2022 (88 places).
- **Identical model series:** 29 places share their exact daily series with another place (324 distinct series in total).
- **Ambiguous names:** 8 places share a normalised name with another GeoNames ID.
- **Hourly timestamps (Kaggle/HF):** ozone peaks at hour label 9, temperature at 15 (offset +6 h), suggesting pollutant and weather columns use different time references.
- **Hourly identical series:** Islamabad = Rawalpindi (variables: dust, humidity, nitrogen_dioxide, ozone, pm10, pm25, precipitation, pressure, sulphur_dioxide, wind_speed).
- **Source agreement:** on 880 paired city-days, daily Pearson r between the Kaggle/HF and World Bank PM2.5 ranges from -0.28 to +0.40 (median +0.05); ratio of medians 0.44–1.43.

## 8. Sensitivity

| scenario | rows_removed_pct | cities | overall_median | top_city | top10_overlap_with_baseline | rank_spearman_vs_baseline |
|---|---|---|---|---|---|---|
| Baseline (all retained data) | 0.00 | 339 | 59.38 | Larkana | 10 | 1.00 |
| Exclude flagged outliers | 0.08 | 339 | 59.37 | Larkana | 10 | 1.00 |
| Winsorise at 1st/99th percentile | 0.00 | 339 | 59.38 | Larkana | 10 | 1.00 |
| Complete calendar years only | 11.58 | 339 | 60.50 | Larkana | 10 | 1.00 |
| Last 3 complete years only | 62.10 | 339 | 57.83 | Rahim Yar Khan | 5 | 0.95 |
| Drop winter months (Dec–Feb) | 24.96 | 339 | 57.09 | Larkana | 9 | 0.99 |
| One place per identical model series | 4.42 | 324 | 58.78 | Larkana | 8 | 1.00 |
| Exclude model-artifact-flagged places | 33.04 | 227 | 53.81 | Khurarianwala | 0 | 1.00 |

## Output files

- `reports/city_summary.csv`
- `reports/monthly_city_summary.csv`
- `reports/monthly_national_summary.csv`
- `reports/seasonal_comparison.csv`
- `reports/city_trends.csv`
- `reports/statistical_tests.csv`
- `reports/correlation_summary.csv`
- `reports/lagged_correlations.csv`
- `reports/completeness_by_city.csv`
- `reports/missing_dates.csv`
- `reports/pipeline_exclusions.csv`
- `reports/model_artifact_flags.csv`
- `reports/source_coverage.csv`
- `reports/source_comparison.csv`
- `reports/sensitivity_scenarios.csv`
- `reports/sensitivity_ranks.csv`
