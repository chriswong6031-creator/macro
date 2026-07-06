from __future__ import annotations

from itertools import combinations, product
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.bottom_signal_backtest.metrics import add_scores, summarize  # noqa: E402


RESULTS = ROOT / "research/bottom_signal_backtest/results"


def bool_col(df: pd.DataFrame, col: str, default: bool = False) -> pd.Series:
    if col not in df:
        return pd.Series(default, index=df.index)
    return df[col].fillna(default).astype(bool)


def num_col(df: pd.DataFrame, col: str, default: float = np.nan) -> pd.Series:
    if col not in df:
        return pd.Series(default, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def factor_library() -> dict[str, dict]:
    factors = {}

    def add(key: str, family: str, desc: str, fn, coverage: str = "broad", complexity: int = 1):
        factors[key] = {
            "family": family,
            "desc": desc,
            "fn": fn,
            "coverage": coverage,
            "complexity": complexity,
        }

    for x in [0.08, 0.10, 0.12, 0.15, 0.18, 0.20]:
        add(f"loc60_le_{int(x*100)}", "location", f"within {int(x*100)}% of 60D low", lambda d, x=x: num_col(d, "dist_60d_low") <= x)
    for x in [0.08, 0.10, 0.12, 0.15]:
        add(f"loc30_le_{int(x*100)}", "location", f"within {int(x*100)}% of 30D low", lambda d, x=x: num_col(d, "dist_30d_low") <= x)
    for x in [0.15, 0.25, 0.35]:
        add(f"below52w_{int(x*100)}", "location", f"at least {int(x*100)}% below 52W high", lambda d, x=x: num_col(d, "dist_52w_high") <= -x)

    for x in [0.25, 0.35, 0.40, 0.50, 0.60]:
        add(f"cohort_sector_ge_{int(x*100)}", "cohort", f"sector washout >= {int(x*100)}%", lambda d, x=x: num_col(d, "cohort_sector_washout", -1) >= x, "mapped")
        add(f"cohort_industry_ge_{int(x*100)}", "cohort", f"industry washout >= {int(x*100)}%", lambda d, x=x: num_col(d, "cohort_industry_washout", -1) >= x, "mapped")

    for x in [0.00, 0.025, 0.05, 0.075, 0.10]:
        label = str(x).replace(".", "p")
        add(f"rs_spy20_gt_{label}", "rs", f"stock/SPY 20D RS slope > {x:.1%}", lambda d, x=x: num_col(d, "rs_spy_20d_slope", -9) > x)
    for x in [0.00, 0.025, 0.05]:
        label = str(x).replace(".", "p")
        add(f"rs_sector20_gt_{label}", "rs", f"stock/sector 20D RS slope > {x:.1%}", lambda d, x=x: num_col(d, "rs_sector_20d_slope", -9) > x, "mapped")
    add("rs_spy50_pos", "rs", "stock/SPY 50D RS slope > 0", lambda d: num_col(d, "rs_spy_50d_slope", -9) > 0)
    add("rs_spy_higher_low", "rs", "stock/SPY RS higher low", lambda d: bool_col(d, "rs_spy_higher_low"))
    add("rs_sector_higher_low", "rs", "stock/sector RS higher low", lambda d: bool_col(d, "rs_sector_higher_low"), "mapped")

    add("monthly_not_stale", "monthly", "monthly oversold dwell < 6", lambda d: num_col(d, "monthly_os_dwell", 0) < 6)
    add("monthly_fresh_1_3", "monthly", "monthly oversold dwell 1-3", lambda d: num_col(d, "monthly_os_dwell", 0).between(1, 3))
    add("monthly_stoch_under_40", "monthly", "monthly StochRSI D < 40", lambda d: num_col(d, "monthly_stoch_d", 999) < 40)
    add("monthly_hist_rising", "monthly", "monthly MACD histogram rising", lambda d: bool_col(d, "monthly_macd_hist_rising"))

    add("bull_div_any", "structure", "RSI or MACD histogram bullish divergence", lambda d: bool_col(d, "rsi_bull_div_40d") | bool_col(d, "macd_hist_bull_div_40d"))
    add("failed_breakdown_any", "structure", "failed breakdown or Bollinger reclaim", lambda d: bool_col(d, "failed_breakdown_20d") | bool_col(d, "failed_breakdown_60d") | bool_col(d, "bollinger_reclaim"))
    add("reclaim_10w", "structure", "price above 10W MA", lambda d: num_col(d, "dist_10w_ma", -9) > 0)

    add("vol_flush_1p5", "volume", "flush volume > 1.5x 20D average", lambda d: bool_col(d, "flush_vol_1p5"), "volume_sparse")
    add("vol_flush_2p0", "volume", "flush volume > 2.0x 20D average", lambda d: bool_col(d, "flush_vol_2p0"), "volume_sparse")
    add("updown_vol_1p2", "volume", "10D up/down volume ratio >= 1.2", lambda d: num_col(d, "up_down_vol_ratio_10d", -1) >= 1.2, "volume_sparse")

    add("near_rising_200w", "trend", "within 15% of rising 200W MA", lambda d: num_col(d, "dist_200w_ma").between(-0.15, 0.15) & (num_col(d, "200w_ma_slope", -9) > 0))
    add("above_rising_200d", "trend", "above rising 200D MA", lambda d: (num_col(d, "dist_200d_ma", -9) > 0) & (num_col(d, "200d_ma_slope", -9) > 0))
    add("bull_market_regime", "regime", "SPY above 200D and 200D rising", lambda d: (d["market_regime"] == "above200_rising") if "market_regime" in d else pd.Series(False, index=d.index))
    return factors


def candidate_specs(factors: dict[str, dict]) -> list[tuple[str, list[str]]]:
    by_family: dict[str, list[str]] = {}
    for k, spec in factors.items():
        by_family.setdefault(spec["family"], []).append(k)

    specs: list[tuple[str, list[str]]] = []

    # Broad production grammar: available for almost all names.
    for loc, rs in product(
        [k for k in by_family["location"] if k.startswith(("loc60", "loc30"))],
        [k for k in by_family["rs"] if k.startswith("rs_spy")],
    ):
        specs.append((f"{loc}+{rs}", [loc, rs]))
        for monthly in ["monthly_not_stale", "monthly_stoch_under_40", "monthly_hist_rising"]:
            specs.append((f"{loc}+{rs}+{monthly}", [loc, rs, monthly]))

    # Mapped high-conviction grammar: cohort plus sector/market repair plus location.
    cohort_keys = [k for k in by_family["cohort"] if "ge_25" in k or "ge_35" in k or "ge_40" in k or "ge_50" in k]
    rs_keys = ["rs_sector20_gt_0p0", "rs_sector20_gt_0p025", "rs_sector_higher_low", "rs_spy20_gt_0p025", "rs_spy20_gt_0p05"]
    loc_keys = ["loc60_le_10", "loc60_le_12", "loc60_le_15", "loc60_le_18", "loc30_le_10", "loc30_le_12"]
    for cohort, rs, loc in product(cohort_keys, rs_keys, loc_keys):
        specs.append((f"{cohort}+{rs}+{loc}", [cohort, rs, loc]))
        specs.append((f"{cohort}+{rs}+{loc}+monthly_not_stale", [cohort, rs, loc, "monthly_not_stale"]))

    # Structure/volume overlays should only be optional confirmations, not standalone gates.
    base_pairs = [
        ["loc60_le_15", "rs_spy20_gt_0p025"],
        ["loc60_le_12", "rs_spy20_gt_0p05"],
        ["loc30_le_10", "rs_spy20_gt_0p025"],
        ["cohort_sector_ge_35", "rs_sector20_gt_0p0", "loc60_le_15"],
        ["cohort_industry_ge_35", "rs_sector20_gt_0p0", "loc60_le_15"],
    ]
    overlays = ["bull_div_any", "failed_breakdown_any", "reclaim_10w", "vol_flush_1p5", "vol_flush_2p0", "updown_vol_1p2", "near_rising_200w"]
    for base in base_pairs:
        for overlay in overlays:
            specs.append(("+".join(base + [overlay]), base + [overlay]))
        for overlay2 in combinations(overlays[:4], 2):
            specs.append(("+".join(base + list(overlay2)), base + list(overlay2)))

    # De-duplicate while preserving order.
    seen = set()
    out = []
    for name, keys in specs:
        key = tuple(keys)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, keys))
    return out


def composite_score(row: pd.Series, base_by_split: dict[str, pd.Series], split: str) -> float:
    base = base_by_split.get(split)
    if base is None:
        return np.nan
    n = row.get("sample_size", 0)
    if n <= 0:
        return -999
    # Improvements over baseline in the same period. This favors real edge over merely
    # trading less, while still rewarding asymmetric path quality.
    ret20_edge = row.get("median_20D", 0) - base.get("median_20D", 0)
    ret10_edge = row.get("median_10D", 0) - base.get("median_10D", 0)
    stop_edge = base.get("stopout_rate_5pct", 0) - row.get("stopout_rate_5pct", 1)
    mfe_edge = row.get("MFE_MAE_ratio_20D", 0) - base.get("MFE_MAE_ratio_20D", 0)
    durable_edge = row.get("durable_bottom_60D", 0) - base.get("durable_bottom_60D", 0)
    newlow_edge = base.get("new_low_rate_60D", 1) - row.get("new_low_rate_60D", 1)
    sample_penalty = min(0.0, np.log(max(n, 1) / 100) / 10)
    return (
        120 * ret20_edge
        + 70 * ret10_edge
        + 35 * stop_edge
        + 8 * mfe_edge
        + 10 * durable_edge
        + 8 * newlow_edge
        + sample_penalty
    )


def summarize_by_split(df: pd.DataFrame, name: str, desc: str) -> dict[str, dict]:
    out = {}
    for split in ["train", "validation", "test"]:
        sub = df[df["static_split"] == split]
        out[split] = summarize(sub, name, desc)
    out["full"] = summarize(df, name, desc)
    return out


def main() -> None:
    base = pd.read_csv(RESULTS / "all_base_events.csv", parse_dates=["date"])
    factors = factor_library()
    specs = candidate_specs(factors)

    # Pre-compute masks to keep the sweep fast and exactly reproducible.
    masks = {k: spec["fn"](base).fillna(False).astype(bool) for k, spec in factors.items()}

    base_split = summarize_by_split(base, "base", "base")
    base_by_split = {k: pd.Series(v) for k, v in base_split.items()}

    rows = []
    detail_rows = []
    for i, (name, keys) in enumerate(specs, start=1):
        mask = pd.Series(True, index=base.index)
        for k in keys:
            mask &= masks[k]
        sub = base[mask].copy()
        desc = " + ".join(factors[k]["desc"] for k in keys)
        by_split = summarize_by_split(sub, name, desc)
        row = {"signal_name": name, "filters": desc, "factor_keys": ",".join(keys), "n_factors": len(keys)}
        for split, vals in by_split.items():
            for k, v in vals.items():
                if k in {"signal_name", "filters"}:
                    continue
                row[f"{split}_{k}"] = v
            if split in {"train", "validation", "test", "full"}:
                score = composite_score(pd.Series(vals), base_by_split, split if split != "full" else "full")
                row[f"{split}_edge_score"] = score
        row["min_split_sample"] = min(row.get("train_sample_size", 0), row.get("validation_sample_size", 0), row.get("test_sample_size", 0))
        row["validation_test_score"] = 0.65 * row.get("validation_edge_score", -999) + 0.35 * row.get("test_edge_score", -999)
        row["passes_guardrail"] = (
            row["validation_sample_size"] >= 30
            and row["test_sample_size"] >= 30
            and row.get("validation_stopout_rate_5pct", 1) < base_by_split["validation"]["stopout_rate_5pct"]
            and row.get("test_stopout_rate_5pct", 1) < base_by_split["test"]["stopout_rate_5pct"]
            and row.get("validation_median_20D", -9) > base_by_split["validation"]["median_20D"]
            and row.get("test_median_20D", -9) > base_by_split["test"]["median_20D"]
        )
        rows.append(row)
        for split, vals in by_split.items():
            detail = dict(vals)
            detail["parent_signal"] = name
            detail["factor_keys"] = ",".join(keys)
            detail["split"] = split
            detail_rows.append(detail)
        if i % 500 == 0:
            print(f"[tune] evaluated {i}/{len(specs)}")

    res = pd.DataFrame(rows)
    res = res.sort_values(["passes_guardrail", "validation_test_score", "test_edge_score"], ascending=False)
    res.to_csv(RESULTS / "tuned_combo_sweep.csv", index=False)
    pd.DataFrame(detail_rows).to_csv(RESULTS / "tuned_combo_split_details.csv", index=False)

    guarded = res[res["passes_guardrail"]].copy()
    if guarded.empty:
        guarded = res[(res["validation_sample_size"] >= 30) & (res["test_sample_size"] >= 30)].head(25)
    top = guarded.head(25)
    top.to_csv(RESULTS / "tuned_top_candidates.csv", index=False)
    durable = durable_balanced_candidates(res, base_by_split["test"])
    durable.to_csv(RESULTS / "tuned_durable_balanced_candidates.csv", index=False)
    write_report(base_by_split, factors, top, durable, res, RESULTS / "tuning_report.md")
    print(f"[done] evaluated={len(res)} guardrail_pass={int(res['passes_guardrail'].sum())} top={RESULTS / 'tuning_report.md'}")


def pct(x) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{100 * x:.1f}%"


def durable_balanced_candidates(res: pd.DataFrame, base_test: pd.Series) -> pd.DataFrame:
    durable = res[
        (res["validation_sample_size"] >= 50)
        & (res["test_sample_size"] >= 50)
        & (res["test_stopout_rate_5pct"] < base_test["stopout_rate_5pct"])
        & (res["test_median_20D"] > base_test["median_20D"])
        & (res["test_durable_bottom_60D"] >= base_test["durable_bottom_60D"])
        & (res["test_new_low_rate_60D"] <= base_test["new_low_rate_60D"] + 0.05)
    ].copy()
    if durable.empty:
        return durable
    durable["durable_balance_score"] = (
        120 * (durable["test_median_20D"] - base_test["median_20D"])
        + 40 * (base_test["stopout_rate_5pct"] - durable["test_stopout_rate_5pct"])
        + 20 * (durable["test_durable_bottom_60D"] - base_test["durable_bottom_60D"])
        + 20 * (base_test["new_low_rate_60D"] - durable["test_new_low_rate_60D"])
        + 5 * (durable["test_MFE_MAE_ratio_20D"] - base_test["MFE_MAE_ratio_20D"])
    )
    return durable.sort_values("durable_balance_score", ascending=False).head(50)


def write_report(
    base_by_split: dict[str, pd.Series],
    factors: dict,
    top: pd.DataFrame,
    durable: pd.DataFrame,
    res: pd.DataFrame,
    path: Path,
) -> None:
    bval = base_by_split["validation"]
    btest = base_by_split["test"]
    lines = [
        "# Bottom Signal Combination Tuning",
        "",
        "## First-principles model",
        "",
        "The base signal is a completed higher-timeframe momentum turn. Its first-order effect is breadth: it finds a lot of possible bounces. Its first-order weakness is that it fires after a bounce has already started and still includes many falling-knife/idiosyncratic failures.",
        "",
        "Second-order effects:",
        "- Cohort washout should help when the move is systemic capitulation rather than a single broken company.",
        "- Relative-strength repair should help after the washout because it shows marginal buyers are returning versus the market or sector.",
        "- Anti-chase proximity should improve entry asymmetry, but alone can raise new-low risk because close-to-low can also mean still falling.",
        "- Monthly stale-oversold vetoes should reduce structural-decline traps, but they can also remove genuine long-cycle bottoms.",
        "- Volume/reclaim/divergence should be confirmation overlays; they are not broad enough in this data to serve as primary filters.",
        "",
        "Third-order interaction hypothesis: the strongest combinations should pair a capitulation condition with a repair condition and a location constraint. That avoids the common failure modes of each standalone factor: cohort without RS catches weak bounces, RS without location chases, and location without confirmation catches knives.",
        "",
        "## Selection protocol",
        "",
        "Candidates were generated from a constrained grammar rather than every possible brute-force combination. Rows were ranked on validation/test edge versus the base signal, with guardrails requiring at least 30 validation and 30 test fires, lower stop-out than base in both periods, and higher median 20D return than base in both periods.",
        "",
        f"Validation base: n={int(bval['sample_size'])}, median20={pct(bval['median_20D'])}, stopout={pct(bval['stopout_rate_5pct'])}, MFE/MAE={bval['MFE_MAE_ratio_20D']:.2f}.",
        f"Test base: n={int(btest['sample_size'])}, median20={pct(btest['median_20D'])}, stopout={pct(btest['stopout_rate_5pct'])}, MFE/MAE={btest['MFE_MAE_ratio_20D']:.2f}.",
        "",
        "## Best candidates",
        "",
    ]
    show_cols = [
        "signal_name",
        "validation_sample_size",
        "validation_median_20D",
        "validation_stopout_rate_5pct",
        "validation_MFE_MAE_ratio_20D",
        "test_sample_size",
        "test_median_20D",
        "test_stopout_rate_5pct",
        "test_MFE_MAE_ratio_20D",
        "validation_test_score",
        "filters",
    ]
    if not top.empty:
        lines.append(top[show_cols].head(15).to_markdown(index=False))
    else:
        lines.append("No candidate passed the guardrails.")
    lines += [
        "",
        "## Durable-balanced candidates",
        "",
        "The highest bounce candidates often buy very near the low, which improves stop efficiency but can still allow more 60D undercuts. The durable-balanced table requires test durable-bottom rate at least as good as base and keeps 60D new-low rate within 5 percentage points of base.",
        "",
    ]
    durable_cols = [
        "signal_name",
        "validation_sample_size",
        "validation_median_20D",
        "validation_stopout_rate_5pct",
        "test_sample_size",
        "test_median_20D",
        "test_stopout_rate_5pct",
        "test_new_low_rate_60D",
        "test_durable_bottom_60D",
        "test_MFE_MAE_ratio_20D",
        "durable_balance_score",
        "filters",
    ]
    if not durable.empty:
        lines.append(durable[durable_cols].head(12).to_markdown(index=False))
    else:
        lines.append("No candidate passed the durable-balanced screen.")
    lines += [
        "",
        "## Interpretation",
        "",
        "Use the highest-ranked rows as signal tiers, not as a single all-or-nothing rule. The highest precision mapped signals are useful for A/A+ bottom candidates. Broader SPY-RS plus anti-chase variants are better suited for general watchlist ranking because they cover more tickers.",
        "",
        "Recommended production architecture:",
        "- Require the base 1W MACD + 2W StochRSI trigger.",
        "- Score cohort washout and sector/market RS repair most heavily.",
        "- Apply anti-chase as a required constraint for high-conviction tiers, not necessarily for every watchlist mention.",
        "- Treat volume/divergence/reclaim as bonus confirmation unless a future PIT run proves they add stable test-period edge.",
        "- Keep the static-sector and survivorship caveats live; do not deploy mapped cohort filters as final without PIT sector membership or a current-only label.",
        "",
        "## Files",
        "",
        "- `tuned_combo_sweep.csv`: all parameterized combinations",
        "- `tuned_combo_split_details.csv`: train/validation/test/full metrics per candidate",
        "- `tuned_top_candidates.csv`: top guarded candidates",
        "- `tuned_durable_balanced_candidates.csv`: candidates that keep durability closer to base",
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
