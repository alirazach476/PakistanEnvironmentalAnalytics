"""Generate the analysis notebooks in notebooks/ (then execute them with nbconvert).

Narrative cells describe *what* is computed; every number appears only in executed
outputs, so the notebooks never contain hand-typed findings.

Usage:
    python scripts/build_notebooks.py
    python -m jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
NB_DIR = ROOT / "notebooks"

SETUP = """import sys
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.io as pio
pio.renderers.default = "plotly_mimetype+notebook_connected"
pd.set_option("display.max_columns", 30, "display.width", 160)

from src.data import load
from src.analysis import descriptive, trends, seasonality, correlations, statistical_tests as st, data_quality as dq, sensitivity
from src.visualization import charts, maps
from src.data.transform import independent_units

wb = descriptive.real_only(load.load_processed("wb_daily"))
cities = load.load_processed("wb_cities")"""

NOTEBOOKS = {
    "01_dataset_audit.ipynb": [
        ("md", "# 01 · Dataset audit\nInventory of every acquired source: provenance, schema, coverage, resolution, "
               "units and licence. Raw files are read directly so the audit reflects what was downloaded."),
        ("code", SETUP),
        ("md", "## Source registry and pipeline manifest\nThe manifest records SHA-256 hashes of the raw inputs used for "
               "the current processed tables."),
        ("code", "import json\nfrom src.utils.config import SOURCES\npd.DataFrame(SOURCES).T[['short','value_type','resolution','license','url']]"),
        ("code", "print(json.dumps(load.load_manifest()['inputs'], indent=2))"),
        ("md", "## World Bank raw subset (Pakistan rows of the regional archive)"),
        ("code", "raw = load.load_wb_raw()\nprint(raw.shape)\nraw.head()"),
        ("code", "raw.dtypes.to_frame('dtype').T"),
        ("code", "pd.Series({'places': raw['geonameid'].nunique(), 'first date': raw['date'].min(), 'last date': raw['date'].max(),\n"
                 "           'distinct dates': raw['date'].nunique(), 'rows per place (min)': raw.groupby('geonameid').size().min(),\n"
                 "           'rows per place (max)': raw.groupby('geonameid').size().max(), 'null cells': int(raw.isna().sum().sum())})"),
        ("code", "raw['adm1cd_c'].value_counts().rename('places x days')"),
        ("md", "## Kaggle / Hugging Face hourly file"),
        ("code", "hf_raw = load.load_hf_raw()\nprint(hf_raw.shape)\nhf_raw.head(3)"),
        ("code", "hf_raw.describe().T.round(2)"),
        ("code", "hf_raw.groupby('city').agg(rows=('timestamp','size'), start=('timestamp','min'), end=('timestamp','max'))"),
        ("md", "## Open-Meteo ERA5 weather payloads"),
        ("code", "payloads, wman = load.load_weather_raw()\nprint(len(payloads), 'cities;', wman.get('model'), wman.get('timezone'))\n"
                 "pd.DataFrame([{**{'geonameid': p['geonameid']}, **p['meta']} for p in payloads])[['city','reason','requested_lat','grid_lat','requested_lon','grid_lon']].head(25)"),
        ("md", "## Coverage summary\nEach source is kept in its own analytical table."),
        ("code", "from src.utils.config import SOURCES\ncov = dq.source_coverage({'wb_pm25': (wb, 'date'), 'hf_aq': (load.load_processed('hf_hourly'), 'timestamp'),\n"
                 "                          'openmeteo_era5': (load.load_processed('weather_daily'), 'date')}, SOURCES)\ncov"),
        ("code", "charts.source_timeline(cov)"),
    ],
    "02_data_cleaning.ipynb": [
        ("md", "# 02 · Data cleaning and validation\nRe-runs the cleaning functions on the raw data and inspects the "
               "exclusion log, identity checks and model-artifact screen. The pipeline itself is "
               "`python scripts/prepare_data.py`."),
        ("code", SETUP),
        ("md", "## Exclusion and transformation log"),
        ("code", "load.load_exclusions()"),
        ("md", "## Schema validation of processed tables"),
        ("code", "from src.data.validate import validate_schema\nfor name in ['wb_daily','wb_cities','hf_hourly','hf_daily','weather_daily']:\n"
                 "    r = validate_schema(load.load_processed(name), name)\n    print(f'{name:15s}', 'OK' if r.ok else r.issues)"),
        ("md", "## Missing dates\nWhich calendar dates are absent from the World Bank series?"),
        ("code", "gaps = dq.find_gaps(wb['date'])\nprint(dq.missing_dates_pattern(gaps))\ngaps.head()"),
        ("code", "charts.gap_strip(gaps, wb['date'].min(), wb['date'].max())"),
        ("md", "## Place identity checks\nShared names, identical model series and province-code consistency."),
        ("code", "cities[cities['name_ambiguous']][['city_label','province','latitude','longitude','population']]"),
        ("code", "cities[cities['series_group_size'] > 1].sort_values('series_group')[['series_group','city_label','population','is_series_representative']]"),
        ("code", "pc = dq.province_consistency(cities)\npc[~pc['consistent']]"),
        ("md", "## Model-artifact screen\nTwo documented diagnostics: repeated annual means and abrupt level shifts."),
        ("code", "art = cities[cities['artifact_flag']]\nprint(len(art), 'of', len(cities), 'places flagged')\nart['artifact_reason'].value_counts()"),
        ("code", "art.sort_values('fixed_annual_run', ascending=False)[['city_label','province','fixed_annual_run','fixed_annual_from','fixed_annual_to','break_date','break_shift_rel']].head(15)"),
        ("code", "charts.artifact_annual_chart(trends.annual_series(wb), cities[cities['fixed_annual_run'] >= 3])"),
        ("code", "charts.break_date_chart(cities)"),
        ("md", "## Outlier flags\nRobust z-score on log PM2.5 within each city; flagged, never deleted."),
        ("code", "dq.outlier_summary(wb).head(10)"),
        ("md", "## Kaggle/HF timestamp diagnostic"),
        ("code", "hf = load.load_processed('hf_hourly')\nal = dq.diurnal_peak_alignment(hf)\n{k: v for k, v in al.items() if k != 'profile'}"),
        ("code", "charts.diurnal_alignment_chart(al['profile'])"),
    ],
    "03_exploratory_analysis.ipynb": [
        ("md", "# 03 · Exploratory analysis\nDistributions, rankings, seasonality and time series of World Bank "
               "modelled PM2.5."),
        ("code", SETUP),
        ("code", "descriptive.dataset_overview(wb)"),
        ("code", "descriptive.summary_stats(wb).T"),
        ("code", "charts.histogram(wb, log_x=True)"),
        ("md", "## City summary"),
        ("code", "cs = descriptive.city_summary(wb)\ncs.head(15)"),
        ("code", "maps.city_metric_map(cs)"),
        ("code", "charts.province_box(cs)"),
        ("md", "## Seasonality"),
        ("code", "seasonality.seasonal_summary(wb)"),
        ("code", "charts.season_box(wb)"),
        ("code", "top = cs.sort_values('population', ascending=False)['city_label'].astype(str).head(20).tolist()\n"
                 "charts.month_city_heatmap(seasonality.month_city_matrix(wb[wb['city_label'].astype(str).isin(top)]).reindex(top))"),
        ("code", "charts.weekday_chart(seasonality.weekday_profile(wb))"),
        ("md", "## Time series"),
        ("code", "charts.national_band(trends.monthly_series(wb))"),
        ("code", "sel = top[:5]\nd = wb[wb['city_label'].astype(str).isin(sel)]\n"
                 "charts.annual_lines(trends.annual_series(d, group_cols=('city_label',)))"),
        ("md", "## Hourly source (Kaggle/HF): pollutant distributions and diurnal profile\nHour labels are shown as "
               "given in the file (see notebook 02 for the timestamp diagnostic)."),
        ("code", "hf = load.load_processed('hf_hourly')\ndescriptive.summary_stats(hf, 'pm25', 'city').round(1)"),
        ("code", "charts.hour_profile_chart(seasonality.hour_profile(hf, 'pm25', by='city'))"),
    ],
    "04_statistical_analysis.ipynb": [
        ("md", "# 04 · Statistical analysis\nFormal tests use one value per city (independent units); places sharing "
               "an identical model series are reduced to one representative."),
        ("code", SETUP),
        ("code", "iu = independent_units(wb, cities)\nprint(wb['city_id'].nunique(), '->', iu['city_id'].nunique(), 'distinct series')"),
        ("md", "## Seasonal differences (Friedman, cities as blocks)"),
        ("code", "r = st.seasonal_friedman(iu)\nprint(r.interpretation)\nr.details.round(4)"),
        ("md", "## Province differences: Kruskal–Wallis and assumption-gated ANOVA"),
        ("code", "cm = iu.groupby(['city_id','province'], observed=True)['pm25'].median().reset_index()\n"
                 "k = st.group_kruskal(cm, 'pm25'); print(k.interpretation)\n"
                 "a = st.group_anova_if_justified(iu.groupby(['city_id','province'], observed=True)['pm25'].mean().reset_index(), 'pm25')\n"
                 "print(a.interpretation); a.assumption_checks"),
        ("md", "## Weekday vs weekend — significance vs importance"),
        ("code", "w = st.weekday_weekend_test(iu)\nprint(w.interpretation)"),
        ("md", "## Trends\nDeseasonalised monthly anomalies, OLS with Newey–West CIs, Theil–Sen, BH-FDR."),
        ("code", "tr = trends.city_trends(wb).merge(cities[['city_id','artifact_flag']], on='city_id')\n"
                 "pd.crosstab(tr['direction'], tr['artifact_flag'], margins=True)"),
        ("code", "charts.trend_forest(tr, n=10)"),
        ("code", "yrs = trends.complete_years(iu)\nfor sub, label in ((iu, 'all'), (iu[~iu['city_id'].astype(str).isin(set(cities.loc[cities['artifact_flag'],'city_id'].astype(str)))], 'artifact-flagged excluded')):\n"
                 "    t = st.period_change_test(trends.annual_series(sub), yrs[0], yrs[-1])\n    print(label, '->', t.interpretation)"),
        ("md", "## Weather correlations (raw vs deseasonalised, autocorrelation-adjusted)"),
        ("code", "ww = load.load_processed('wb_weather_daily')\nrows = []\nfor x in ['temperature','humidity','wind_speed','precipitation']:\n"
                 "    for des in (False, True):\n        rows.append(correlations.pooled_city_correlation(ww, x, deseasonalize=des))\npd.DataFrame(rows)"),
        ("code", "charts.lag_chart(correlations.lagged_correlation(ww, 'wind_speed', deseasonalize=True), 'wind_speed')"),
        ("code", "corr, n = correlations.correlation_matrix(correlations.add_anomalies(ww, ['pm25','temperature','humidity','wind_speed','precipitation']),\n"
                 "    ['pm25_anom','temperature_anom','humidity_anom','wind_speed_anom','precipitation_anom'])\ncharts.correlation_heatmap(corr, n)"),
        ("md", "## Sensitivity analysis"),
        ("code", "sensitivity.scenario_metrics(wb, cities).round(2)"),
    ],
    "05_city_comparisons.ipynb": [
        ("md", "# 05 · City comparisons\nLevel, spread and timing for selected large cities, a common-window ranking, "
               "and a comparison of the two PM2.5 sources where they overlap."),
        ("code", SETUP),
        ("code", "big = cities.sort_values('population', ascending=False)['city_label'].astype(str).head(8).tolist()\n"
                 "d = wb[wb['city_label'].astype(str).isin(big)].assign(city_label=lambda x: x['city_label'].astype(str))\nbig"),
        ("code", "stats = descriptive.summary_stats(d, 'pm25', 'city_label')\nstats['city_label'] = stats['city_label'].astype(str)\nstats.round(1)"),
        ("code", "charts.city_interval_dots(stats)"),
        ("code", "charts.box_violin(d, kind='violin')"),
        ("code", "charts.ecdf_chart(d)"),
        ("code", "charts.percentile_chart(descriptive.percentile_table(d))"),
        ("code", "m = trends.monthly_series(d, group_cols=('city_label',))\ncharts.multi_city_lines(m, 'period', 'mean', title='Monthly mean PM2.5')"),
        ("code", "charts.yoy_heatmap(trends.year_over_year(d, group_col='city_label'))"),
        ("md", "## Common-window ranking with artifact flags"),
        ("code", "descriptive.comparable_period_ranking(wb).merge(cities[['city_id','artifact_reason']], on='city_id').head(20)"),
        ("md", "## Source-to-source comparison (Kaggle/HF vs World Bank, same city and date)"),
        ("code", "ov = load.load_processed('source_overlap')\ndq.source_comparison(ov).round(2)"),
        ("code", "charts.source_comparison_scatter(ov)"),
    ],
}


def build() -> None:
    NB_DIR.mkdir(exist_ok=True)
    for name, cells in NOTEBOOKS.items():
        nb = nbf.v4.new_notebook()
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nb.cells = [nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src) for kind, src in cells]
        nbf.write(nb, NB_DIR / name)
        print("wrote", NB_DIR / name)


if __name__ == "__main__":
    build()
