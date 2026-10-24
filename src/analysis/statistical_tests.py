"""Formal hypothesis tests with full reporting.

Design principle: repeated daily observations from the same city are *not*
independent, so every test here uses an independent-enough unit of analysis —
usually the city (one summary value per city), with paired designs where the
same cities are compared across conditions. Remaining caveat: neighbouring
cities share regional air masses (spatial dependence), so city-level p-values
are still somewhat optimistic; this is stated in every result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from src.analysis.correlations import pooled_city_correlation
from src.analysis.seasonality import city_season_medians, weekday_weekend_by_city
from src.data.validate import require_columns
from src.utils.config import ALPHA

SPATIAL_CAVEAT = ("Cities are treated as independent units, but nearby cities share regional "
                  "meteorology and the modelled surface is spatially smooth, so p-values may be optimistic.")
MODELLED_CAVEAT = "Values are model estimates, not monitor measurements; results describe the model output."


@dataclass
class TestResult:
    name: str
    question: str
    null_hypothesis: str
    unit_of_analysis: str
    n: int
    test: str
    statistic: float = np.nan
    p_value: float = np.nan
    effect_size_name: str = ""
    effect_size: float = np.nan
    effect_ci: tuple[float, float] | None = None
    assumptions: list[str] = field(default_factory=list)
    assumption_checks: dict = field(default_factory=dict)
    interpretation: str = ""
    caveats: list[str] = field(default_factory=list)
    details: pd.DataFrame | None = None
    justified: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("details", None)
        return d

    def summary_row(self) -> dict:
        return {"test": self.name, "question": self.question, "method": self.test, "unit": self.unit_of_analysis,
                "n": self.n, "statistic": self.statistic, "p_value": self.p_value,
                "effect_size_name": self.effect_size_name, "effect_size": self.effect_size,
                "effect_ci_low": self.effect_ci[0] if self.effect_ci else np.nan,
                "effect_ci_high": self.effect_ci[1] if self.effect_ci else np.nan,
                "justified": self.justified, "interpretation": self.interpretation}


# ---------------------------------------------------------------------------
# Effect-size helpers
# ---------------------------------------------------------------------------


def effect_label(value: float, kind: str) -> str:
    """Conventional (Cohen-style) magnitude labels; context still matters more than labels."""
    if not np.isfinite(value):
        return "undetermined"
    v = abs(value)
    cuts = {"kendall_w": (0.1, 0.3, 0.5), "epsilon_sq": (0.01, 0.08, 0.26), "eta_sq": (0.01, 0.06, 0.14),
            "rank_biserial": (0.1, 0.3, 0.5), "r": (0.1, 0.3, 0.5)}[kind]
    return "negligible" if v < cuts[0] else "small" if v < cuts[1] else "moderate" if v < cuts[2] else "large"


def paired_rank_biserial(diff: np.ndarray) -> float:
    """Matched-pairs rank-biserial correlation (Kerby, 2014)."""
    d = np.asarray(diff, dtype=float)
    d = d[np.isfinite(d) & (d != 0)]
    if d.size == 0:
        return np.nan
    ranks = stats.rankdata(np.abs(d))
    return float((ranks[d > 0].sum() - ranks[d < 0].sum()) / ranks.sum())


def mwu_rank_biserial(u: float, n1: int, n2: int) -> float:
    return float(1 - 2 * u / (n1 * n2))


def bootstrap_ci(values, func=np.median, n_boot: int = 4000, ci: float = 0.95, seed: int = 0) -> tuple[float, float]:
    v = np.asarray(pd.Series(values).dropna(), dtype=float)
    if v.size < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    boots = np.array([func(rng.choice(v, v.size, replace=True)) for _ in range(n_boot)])
    a = (1 - ci) / 2
    return float(np.quantile(boots, a)), float(np.quantile(boots, 1 - a))


def _p_text(p: float, alpha: float = ALPHA) -> str:
    if not np.isfinite(p):
        return "p could not be computed"
    return f"p {'<' if p < 0.001 else '='} {max(p, 0.001):.3f}" + (" (below α)" if p < alpha else " (not below α)")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def seasonal_friedman(daily: pd.DataFrame, value: str = "pm25", city_col: str = "city_id") -> TestResult:
    """Do PM2.5 levels differ across seasons? Friedman test, cities as blocks."""
    require_columns(daily, [value, city_col, "season"])
    wide = city_season_medians(daily, value, city_col).dropna()
    k, n = wide.shape[1], wide.shape[0]
    res = TestResult(
        name="Seasonal differences (Friedman)", test="Friedman rank test (repeated measures)",
        question="Does median PM2.5 differ between seasons when the same cities are compared?",
        null_hypothesis="Within each city, the distribution of seasonal medians is the same for all seasons.",
        unit_of_analysis="city (median of daily values per season)", n=n,
        assumptions=["Cities are independent blocks", "Seasonal medians are ordinal-comparable within city",
                     "No normality assumption"],
        caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT], effect_size_name="Kendall's W")
    if n < 3 or k < 2:
        res.justified = False
        res.interpretation = "Not enough cities or seasons with data to run the test."
        return res
    stat, p = stats.friedmanchisquare(*[wide[c].to_numpy() for c in wide.columns])
    w = stat / (n * (k - 1))
    res.statistic, res.p_value, res.effect_size = float(stat), float(p), float(w)

    pairs = []
    for a, b in combinations(wide.columns, 2):
        d = (wide[a] - wide[b]).to_numpy()
        s, pp = stats.wilcoxon(wide[a], wide[b], zero_method="wilcox")
        pairs.append({"season_a": a, "season_b": b, "median_diff": float(np.median(d)),
                      "rank_biserial": paired_rank_biserial(d), "W": float(s), "p_value": float(pp)})
    pairs = pd.DataFrame(pairs)
    pairs["p_holm"] = multipletests(pairs["p_value"], method="holm")[1]
    res.details = pairs
    order = wide.median().sort_values(ascending=False)
    res.interpretation = (
        f"Across {n} cities, {_p_text(p)}; Kendall's W = {w:.2f} ({effect_label(w, 'kendall_w')} agreement "
        f"in seasonal ranking). Highest median season: {order.index[0]} "
        f"({order.iloc[0]:.1f} µg/m³); lowest: {order.index[-1]} ({order.iloc[-1]:.1f} µg/m³). "
        f"{int((pairs['p_holm'] < ALPHA).sum())} of {len(pairs)} pairwise season contrasts remain below α after Holm correction.")
    return res


def group_kruskal(city_level: pd.DataFrame, value: str, group_col: str = "province", min_group: int = 3) -> TestResult:
    """Kruskal–Wallis across groups of cities (e.g. provinces), one value per city."""
    require_columns(city_level, [value, group_col])
    counts = city_level.groupby(group_col, observed=True)[value].count()
    kept = counts[counts >= min_group].index.tolist()
    dropped = counts[counts < min_group].index.tolist()
    d = city_level[city_level[group_col].isin(kept)]
    groups = [g[value].dropna().to_numpy() for _, g in d.groupby(group_col, observed=True)]
    n, k = sum(len(g) for g in groups), len(groups)
    res = TestResult(
        name=f"Differences between {group_col} groups (Kruskal–Wallis)", test="Kruskal–Wallis H test",
        question=f"Do city-level median PM2.5 values differ between {group_col} groups?",
        null_hypothesis=f"City medians come from the same distribution in every {group_col}.",
        unit_of_analysis="city (median of all daily values)", n=n, effect_size_name="epsilon²",
        assumptions=["Independent cities", "Similar distribution shapes across groups for a location interpretation",
                     f"Groups with fewer than {min_group} cities excluded"],
        assumption_checks={"groups_tested": kept, "groups_excluded_small_n": dropped},
        caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT,
                 "Province membership is derived from source ADM1 codes (see methodology)."])
    if k < 2:
        res.justified = False
        res.interpretation = "Fewer than two groups with enough cities."
        return res
    h, p = stats.kruskal(*groups)
    eps = (h - k + 1) / (n - k) if n > k else np.nan
    res.statistic, res.p_value, res.effect_size = float(h), float(p), float(eps)
    pairs = []
    for (ga, a), (gb, b) in combinations(d.groupby(group_col, observed=True), 2):
        u, pp = stats.mannwhitneyu(a[value], b[value], alternative="two-sided")
        pairs.append({"group_a": ga, "group_b": gb, "n_a": len(a), "n_b": len(b),
                      "median_a": a[value].median(), "median_b": b[value].median(),
                      "rank_biserial": mwu_rank_biserial(u, len(a), len(b)), "U": float(u), "p_value": float(pp)})
    pairs = pd.DataFrame(pairs)
    pairs["p_holm"] = multipletests(pairs["p_value"], method="holm")[1]
    res.details = pairs
    res.interpretation = (f"{k} groups, {n} cities: H = {h:.2f}, {_p_text(p)}; ε² = {eps:.2f} "
                          f"({effect_label(eps, 'epsilon_sq')}). "
                          f"{int((pairs['p_holm'] < ALPHA).sum())} of {len(pairs)} pairwise contrasts below α after Holm.")
    return res


def group_anova_if_justified(city_level: pd.DataFrame, value: str, group_col: str = "province",
                             min_group: int = 3) -> TestResult:
    """One-way ANOVA only when normality (Shapiro–Wilk per group) and equal variances (Levene)
    are not rejected; otherwise the result is marked not justified with the reasons."""
    require_columns(city_level, [value, group_col])
    counts = city_level.groupby(group_col, observed=True)[value].count()
    d = city_level[city_level[group_col].isin(counts[counts >= min_group].index)]
    groups = {g: x[value].dropna().to_numpy() for g, x in d.groupby(group_col, observed=True)}
    n = sum(len(v) for v in groups.values())
    res = TestResult(
        name=f"One-way ANOVA by {group_col} (assumption-gated)", test="One-way ANOVA (F test)",
        question=f"Do mean city-level PM2.5 values differ between {group_col} groups?",
        null_hypothesis="All group means are equal.", unit_of_analysis="city (mean of daily values)", n=n,
        assumptions=["Independent cities", "Approximately normal residuals within groups", "Equal variances"],
        effect_size_name="eta²", caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT])
    if len(groups) < 2:
        res.justified = False
        res.interpretation = "Fewer than two groups with enough cities."
        return res
    shapiro = {g: float(stats.shapiro(v).pvalue) for g, v in groups.items() if 3 <= len(v) <= 5000}
    lev = stats.levene(*groups.values(), center="median")
    res.assumption_checks = {"shapiro_p_by_group": shapiro, "levene_p": float(lev.pvalue)}
    failed = [g for g, p in shapiro.items() if p < ALPHA]
    reasons = []
    if failed:
        reasons.append(f"normality rejected (Shapiro–Wilk p < {ALPHA}) in: {', '.join(map(str, failed))}")
    if lev.pvalue < ALPHA:
        reasons.append(f"equal variances rejected (Levene p = {lev.pvalue:.3g})")
    if reasons:
        res.justified = False
        res.interpretation = ("ANOVA not reported because its assumptions are not reasonably met: "
                              + "; ".join(reasons) + ". Use the Kruskal–Wallis result instead.")
        return res
    f, p = stats.f_oneway(*groups.values())
    allv = np.concatenate(list(groups.values()))
    ss_between = sum(len(v) * (v.mean() - allv.mean()) ** 2 for v in groups.values())
    eta = ss_between / ((allv - allv.mean()) ** 2).sum()
    res.statistic, res.p_value, res.effect_size = float(f), float(p), float(eta)
    res.interpretation = f"F = {f:.2f}, {_p_text(p)}; η² = {eta:.2f} ({effect_label(eta, 'eta_sq')})."
    return res


def weekday_weekend_test(daily: pd.DataFrame, value: str = "pm25", city_col: str = "city_id") -> TestResult:
    """Paired Wilcoxon across cities: weekday mean vs weekend (Sat/Sun) mean."""
    w = weekday_weekend_by_city(daily, value, city_col)
    n = len(w)
    res = TestResult(
        name="Weekday vs weekend (Wilcoxon signed-rank)", test="Wilcoxon signed-rank test (paired)",
        question="Within cities, is mean PM2.5 different on weekdays than on weekends?",
        null_hypothesis="The weekday−weekend difference is symmetric about zero.",
        unit_of_analysis="city (weekday mean − weekend mean)", n=n,
        effect_size_name="matched-pairs rank-biserial",
        assumptions=["Independent cities", "Symmetric distribution of differences"],
        caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT,
                 "Weekend defined as Saturday–Sunday; official weekends in Pakistan have changed over time.",
                 "A daily model may not resolve weekly emission cycles."])
    if n < 6:
        res.justified = False
        res.interpretation = "Too few cities for a paired test."
        return res
    s, p = stats.wilcoxon(w["weekday_mean"], w["weekend_mean"])
    rb = paired_rank_biserial(w["difference"].to_numpy())
    med = float(w["difference"].median())
    res.statistic, res.p_value, res.effect_size = float(s), float(p), rb
    res.effect_ci = bootstrap_ci(w["difference"])
    res.details = w
    rel = 100 * med / float(w["weekend_mean"].median())
    res.assumption_checks = {"median_difference_pct_of_level": rel}
    res.interpretation = (f"Median weekday−weekend difference = {med:+.2f} µg/m³ "
                          f"(95 % bootstrap CI {res.effect_ci[0]:+.2f} to {res.effect_ci[1]:+.2f}), i.e. "
                          f"{rel:+.1f} % of the typical weekend level; {_p_text(p)}; "
                          f"rank-biserial = {rb:+.2f} ({effect_label(rb, 'rank_biserial')} consistency across cities). "
                          + ("The difference is consistent but very small in absolute terms; statistical "
                             "significance here does not imply practical importance." if abs(rel) < 2 else ""))
    return res


def period_change_test(annual: pd.DataFrame, year_a: int, year_b: int, city_col: str = "city_id") -> TestResult:
    """Paired Wilcoxon on city annual means between two complete calendar years."""
    require_columns(annual, [city_col, "year", "mean"])
    w = annual[annual["year"].isin([year_a, year_b])].pivot_table(index=city_col, columns="year", values="mean",
                                                                   observed=True).dropna()
    n = len(w)
    res = TestResult(
        name=f"Change {year_a} → {year_b} (Wilcoxon signed-rank)", test="Wilcoxon signed-rank test (paired)",
        question=f"Did city annual mean PM2.5 change between {year_a} and {year_b}?",
        null_hypothesis="The distribution of city-level differences is symmetric about zero.",
        unit_of_analysis="city (annual mean, complete years only)", n=n,
        effect_size_name="median % change",
        assumptions=["Independent cities", "Symmetric differences", "Both years meet completeness rules"],
        caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT,
                 "Two-year comparisons are sensitive to inter-annual meteorology; see trend analysis."])
    if n < 6 or year_a not in w.columns or year_b not in w.columns:
        res.justified = False
        res.interpretation = "Not enough cities with complete data in both years."
        return res
    diff = w[year_b] - w[year_a]
    pct = 100 * diff / w[year_a]
    s, p = stats.wilcoxon(w[year_b], w[year_a])
    res.statistic, res.p_value, res.effect_size = float(s), float(p), float(pct.median())
    res.effect_ci = bootstrap_ci(pct)
    res.assumption_checks = {"rank_biserial": paired_rank_biserial(diff.to_numpy()),
                             "n_cities_increased": int((diff > 0).sum()), "n_cities_decreased": int((diff < 0).sum())}
    res.details = pd.DataFrame({"year_a": w[year_a], "year_b": w[year_b], "difference": diff, "pct_change": pct}).reset_index()
    res.interpretation = (f"Median city change {pct.median():+.1f} % (95 % bootstrap CI {res.effect_ci[0]:+.1f} to "
                          f"{res.effect_ci[1]:+.1f} %); {res.assumption_checks['n_cities_decreased']} cities decreased, "
                          f"{res.assumption_checks['n_cities_increased']} increased; {_p_text(p)}.")
    return res


def weather_correlation_test(df: pd.DataFrame, x: str, y: str = "pm25", deseasonalize: bool = True,
                             method: str = "spearman") -> TestResult:
    """Within-city correlation summarised across cities (city = unit); autocorrelation-adjusted."""
    s = pooled_city_correlation(df, x, y, method, deseasonalize=deseasonalize)
    n = s.get("n_cities", 0)
    tag = "deseasonalised anomalies" if deseasonalize else "raw daily values"
    res = TestResult(
        name=f"{y} vs {x} ({tag})", test=f"{method.title()} correlation per city + one-sample Wilcoxon on r",
        question=f"Is daily {y} associated with {x} within cities ({tag})?",
        null_hypothesis="The median within-city correlation is zero.",
        unit_of_analysis="city (one correlation coefficient per city)", n=n, effect_size_name="median r",
        assumptions=["Monotonic relationship (Spearman)", "Per-city p-values use effective sample size for "
                     "lag-1 autocorrelation", "Cities treated as independent"],
        caveats=[SPATIAL_CAVEAT, MODELLED_CAVEAT, "Correlation does not imply causation; weather and pollution "
                 "share seasonal drivers and confounders (e.g. crop burning, heating)."])
    if n < 6:
        res.justified = False
        res.interpretation = "Too few cities with paired weather data."
        return res
    from src.analysis.correlations import city_correlations
    per = city_correlations(df, x, y, method, deseasonalize=deseasonalize)
    stat, p = stats.wilcoxon(per["r"])
    res.statistic, res.p_value, res.effect_size = float(stat), float(p), s["median_r"]
    res.effect_ci = bootstrap_ci(per["r"])
    res.details = per
    res.assumption_checks = {"n_significant_fdr": s["n_significant_fdr"], "n_positive": s["n_positive"],
                             "n_negative": s["n_negative"], "median_n_eff": float(per["n_eff"].median())}
    res.interpretation = (f"Median within-city r = {s['median_r']:+.2f} (range {s['min_r']:+.2f} to {s['max_r']:+.2f}; "
                          f"{effect_label(s['median_r'], 'r')}); {s['n_positive']} positive / {s['n_negative']} negative; "
                          f"{s['n_significant_fdr']} of {n} cities significant after FDR with adjusted n. "
                          f"Across cities, {_p_text(p)}. Association only — not evidence of causation.")
    return res


def results_table(results: list[TestResult]) -> pd.DataFrame:
    return pd.DataFrame([r.summary_row() for r in results])
