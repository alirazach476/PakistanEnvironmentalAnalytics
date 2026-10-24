# Methodology

This document records every assumption, transformation, aggregation rule and statistical choice. Numeric
results are deliberately **not** written here — they are produced by the code (`reports/findings.md`, the
dashboard) so they always match the data.

## 1. Guiding principles

1. **Model output is not measurement.** All PM2.5 in this project is modelled. Statements describe the model
   output, and are labelled as such in every view.
2. **Sources stay separate.** World Bank (daily) and Kaggle/HF (hourly) PM2.5 come from different models, at
   different resolutions, for different periods. They are never averaged together; they are compared only on
   matched city-days.
3. **Concentrations are not converted to AQI.** The WHO 2021 guideline values (24-hour 15 µg/m³, annual
   5 µg/m³) appear only as reference lines/thresholds.
4. **Flag, don't delete.** Values that are physically impossible are excluded and logged; values that are
   merely unusual are flagged and kept, with optional exclusion in the dashboard.
5. **Independent units for inference.** Daily values within a city are serially dependent and are never
   treated as independent samples in a test.

## 2. Pipeline (`scripts/prepare_data.py` → `src/data/pipeline.py`)

The pipeline rebuilds every processed table from `data/raw` on each run and overwrites outputs atomically
(write to `.tmp`, then rename). Repeated runs therefore cannot accumulate duplicates; a test re-runs it and
compares row counts.

### 2.1 Loading and normalisation
- CSV and Parquet are supported (`src/data/load.py`). Raw files are only read.
- Column names: NFKC-normalised, lower-cased, punctuation → `_`, then mapped through a synonym table
  (`pm2_5`/`PM2.5` → `pm25`, `relative_humidity_2m_mean` → `humidity`, …). Collisions raise an error.
- City names: NFKC, whitespace collapsed, title-cased, alias table (e.g. "Islamabad Capital Territory" →
  "Islamabad"). A separate **matching key** strips everything except letters/digits (so "Arif Wala" and
  "Arifwala" collide and are flagged).
- Dates: parsed with `errors="coerce"`; unparseable values are excluded and logged. Time-zone-aware input is
  converted to the target zone and made naive; naive input is localised only when a source zone is known.

### 2.2 Validation and exclusions (`src/data/validate.py`, `src/data/clean.py`)
| Check | World Bank (single-value rows) | Kaggle/HF & ERA5 (multi-variable rows) |
|---|---|---|
| Unparseable date | row excluded | row excluded |
| Non-numeric value | row excluded | cell → NaN |
| Missing value | row excluded | kept as NaN |
| Outside plausible range (`PLAUSIBLE_RANGES` in `src/utils/config.py`) | row excluded | cell → NaN |
| Exact duplicate key + values | duplicates dropped (one kept) | same |
| Conflicting duplicate key (values differ) | **all copies** excluded (no arbitrary choice) | same |
| Country ≠ PAK | excluded | – |
| PM2.5 > PM10 | – | flagged |

Each action is written to `data/processed/exclusions_log.csv`.

### 2.3 Place identity
- **Province labels.** The source provides only ADM1 codes. Labels were assigned from the undisputed capital
  found inside each code (PAK002 Quetta → Balochistan, PAK003 Islamabad → ICT, PAK005 Peshawar → Khyber
  Pakhtunkhwa, PAK006 Lahore → Punjab, PAK007 Hyderabad → Sindh). The pipeline re-verifies these anchors on
  every run (`adm1_anchor_check` in the manifest). No boundary file is used, so a place's province is only as
  good as its source code; a nearest-neighbour consistency check lists candidates for review.
- **Disambiguated labels.** Places sharing a name get "(Province)" or, if still ambiguous, coordinates.
- **Identical series.** Places whose complete daily series are identical (SHA-1 of the rounded series) are
  grouped. Descriptive views keep all places; inferential tests keep one representative (most populous) per
  group.
- Coordinates are never corrected, even when they look wrong (e.g. a name/coordinate mismatch); they are
  flagged instead.

### 2.4 Model-artifact screen (`src/analysis/data_quality.py`)
Two diagnostics, both computed per place on the World Bank series:
1. **Fixed annual mean** — longest run of consecutive complete calendar years whose annual means differ by
   < 0.5 % from the previous year. Real annual concentrations normally vary by several percent; a run of
   ≥ 3 such years suggests the model scales daily values to a fixed annual level.
2. **Abrupt level shift** — for every candidate break (≥ 12 months each side) in the deseasonalised monthly
   anomaly series, a Welch t-statistic for the change in mean; the maximum is kept. Flag when t ≥ 10 **and**
   the shift is ≥ 30 % of the place's mean level. Because the maximum over many breaks inflates t, this is a
   screening rule, not a formal change-point test.

Flagged places are kept by default. The dashboard offers a global toggle to exclude them, and reports show key
results with and without them.

### 2.5 Outliers
Robust z-score on log PM2.5 within each place: `z = 0.6745 · (log x − median) / MAD`; flag when |z| > 3.5
(Iglewicz & Hoaglin). Logs are used because concentrations are right-skewed. Box plots separately use Tukey
fences (1.5 × IQR) for display only.

## 3. Temporal rules

| Aggregation | Rule |
|---|---|
| hourly → daily (Kaggle/HF) | mean (precipitation **sum**, wind direction **circular mean**); requires ≥ 18 valid hours |
| daily → monthly | mean of daily values; month complete with ≥ 20 valid days |
| monthly → annual | mean of **complete monthly means** (so months are equally weighted); year complete with ≥ 11 complete months |
| rolling means | centred, calendar-aware (gaps are not bridged); require ≥ 70 % of the window |

The World Bank series lacks the last day of every month (detected by the gap analysis), so complete months
have one day fewer than calendar months; the 20-day rule is unaffected.

**Time zones.** World Bank days have an undocumented boundary. ERA5 weather was requested for the local day
(Asia/Karachi). Weather–PM2.5 lagged correlations at ±1 day are reported to show sensitivity to this
mismatch. Kaggle/HF timestamps are kept exactly as labelled; a diagnostic compares the hour of peak ozone with
the hour of peak temperature (both normally peak in the early-to-mid afternoon) and reports the offset.

**Seasons** (project definition aligned with the monsoon cycle): Winter Dec–Feb, Spring Mar–Apr,
Pre-monsoon May–Jun, Monsoon Jul–Sep, Post-monsoon Oct–Nov.

**Weekend** = Saturday and Sunday. Official weekends in Pakistan have changed over time, and daily models may
not resolve weekly emission cycles; weekday results are therefore descriptive.

## 4. Statistical methods

Every test returns: question, null hypothesis, unit of analysis, n, assumptions (and checks), statistic,
p-value, effect size (with bootstrap CI where meaningful) and an interpretation generated from the numbers.

| Question | Unit | Method | Effect size |
|---|---|---|---|
| Do seasons differ? | city (seasonal median) | Friedman test, cities as blocks; pairwise Wilcoxon signed-rank with Holm correction | Kendall's W; matched-pairs rank-biserial |
| Do provinces differ? | city (overall median) | Kruskal–Wallis (groups with < 3 cities excluded); pairwise Mann–Whitney with Holm | ε²; rank-biserial |
| Same, parametric | city (mean) | One-way ANOVA **only if** Shapiro–Wilk (each group) and Levene do not reject at α = 0.05; otherwise reported as "not justified" | η² |
| Weekday vs weekend | city (difference of means) | Wilcoxon signed-rank | median difference (µg/m³ and % of level), bootstrap CI, rank-biserial |
| Change between two complete years | city (annual means) | Wilcoxon signed-rank | median % change, bootstrap CI; counts up/down |
| Weather association | city (one Spearman ρ per city) | per-city ρ with **autocorrelation-adjusted** p (effective n, Bretherton et al. 1999), BH-FDR across cities; one-sample Wilcoxon on the ρ values | median ρ with bootstrap CI |
| Long-term trend per city | monthly anomalies | OLS with Newey–West (HAC, 12 lags) CI; Theil–Sen slope; BH-FDR across cities | slope µg/m³/yr and % of level per year |

**Deseasonalisation.** For trends and anomaly correlations, each value is reduced by the place's mean for that
calendar month. Pollution and weather share a strong annual cycle, so raw correlations largely reflect
seasonality; anomaly correlations describe day-to-day co-variation.

**Effective sample size.** `n_eff = n (1 − r₁ₓr₁ᵧ)/(1 + r₁ₓr₁ᵧ)` with lag-1 autocorrelations r₁. p-values and
confidence intervals for correlations are recomputed with `n_eff`.

**Multiple comparisons.** Holm within each family of pairwise contrasts; Benjamini–Hochberg FDR across
cities; Holm across the family of headline tests on the Statistical Analysis page.

**Significance vs importance.** With hundreds of cities and years of data, tiny effects reach p < 0.05. Effect
sizes, confidence intervals and differences in µg/m³ are always shown, and interpretation text calls out
statistically significant but practically negligible effects.

**Remaining dependence.** Cities are treated as independent units, but neighbouring cities share regional
meteorology and the modelled surface is spatially smooth, so city-level p-values remain somewhat optimistic.
This caveat is attached to every test result.

## 5. Sensitivity analysis (`src/analysis/sensitivity.py`)

The same headline metrics (overall median, median of city medians, top city, overlap of the top-10, Spearman
correlation of city rankings with the baseline) are recomputed under:
baseline · outliers excluded · winsorised at 1st/99th percentiles · complete calendar years only · last three
complete years · winter excluded · one place per identical series · artifact-flagged places excluded.

## 6. Source comparison

Each Kaggle/HF city is paired with the nearest World Bank place within 25 km (haversine). On shared dates the
report gives n, medians, mean bias, MAE, ratio of medians and Pearson r with an autocorrelation-adjusted CI.
Agreement or disagreement indicates model uncertainty; neither source is treated as truth.

## 7. Known limitations

- No ground-truth monitor data; all conclusions concern model estimates.
- The World Bank model shows fixed annual levels and abrupt shifts for many places (see the artifact screen);
  rankings and trends for those places reflect model behaviour.
- Units of the World Bank PM2.5 field are not stated by the source (assumed µg/m³).
- Kaggle/HF data have unknown licence and provenance, cover only one winter, and show a likely timestamp
  misalignment between pollutant and weather columns.
- ERA5 is 0.25° reanalysis; it does not resolve urban microclimates. Weather was fetched for 22 places only.
- Province labels come from source codes, not a boundary overlay.
- Population figures are GeoNames values of unknown vintage.
