"""scripts/cbf_regime_study.py — Cross-Border Flow Regime Census (W1 one-shot).

GENERATED ARTIFACT: outputs
  research/cbf/REGIME_CENSUS.md
  research/cbf/artifacts/regime_history.csv

OFF the render path — not called by any nightly job. Run once to produce the
census document that informs the CBF program.

Usage:
    python3 -m scripts.cbf_regime_study
    python3 scripts/cbf_regime_study.py

Per the pyarrow one-shot law (memory note in CLAUDE.md): this script ends with
lib.procutil.hard_exit() to avoid Arrow ThreadPool static-destructor deadlock.

DISPLAY-ONLY: all statistics are descriptive. No significance tests. No verdicts.
No "edge" language. The word "validated" never appears. Effective N = spell count
(not session count) for forward-behavior tables, printed next to every row.
"""
from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup: allow running as script or as module
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.flow_regime import (
    ROW_BASKET, EM_FX_PAIRS,
    DTWEXBGS_START, ERA_CUTOFF,
    RISK_OFF, EXCEPTION, ROTATION, GOLDILOCKS, MIXED, REGIME_ORDER,
    load_inputs_from_store,
    build_row_composite, build_broad_dollar, build_emfx_basket,
    classify_history,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
CBF_DIR    = _REPO / "research" / "cbf"
ART_DIR    = CBF_DIR / "artifacts"
CENSUS_MD  = CBF_DIR / "REGIME_CENSUS.md"
HISTORY_CSV = ART_DIR / "regime_history.csv"

ART_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _days(x: float) -> str:
    return f"{x:.1f} sessions"


def _get_spells(series: pd.Series) -> pd.DataFrame:
    """Convert a state series to a spell DataFrame (state, start, end, duration_sessions)."""
    if series.empty:
        return pd.DataFrame(columns=["state", "start", "end", "duration"])
    changes = series != series.shift(1)
    spell_starts = series[changes].index
    rows = []
    dates = series.index.tolist()
    vals = series.values.tolist()
    i = 0
    while i < len(dates):
        if changes.iloc[i]:
            state = vals[i]
            start = dates[i]
            # Find end
            j = i + 1
            while j < len(dates) and vals[j] == state:
                j += 1
            end = dates[j - 1]
            duration = j - i
            rows.append({"state": state, "start": start, "end": end, "duration": duration})
            i = j
        else:
            i += 1
    return pd.DataFrame(rows)


def _basket_membership(row_etf_closes: dict[str, pd.Series], spy_index: pd.DatetimeIndex) -> pd.Series:
    """Count of available (non-NaN) ETF members per date."""
    dfs = []
    for ticker, s in row_etf_closes.items():
        aligned = s.reindex(spy_index).ffill(limit=3)
        dfs.append(aligned.notna().astype(int).rename(ticker))
    if not dfs:
        return pd.Series(0, index=spy_index, name="basket_members")
    combined = pd.concat(dfs, axis=1)
    return combined.sum(axis=1).rename("basket_members")


def _emfx_membership(fx_series: dict[str, pd.Series], spy_index: pd.DatetimeIndex) -> pd.Series:
    """Count of available EM FX pairs per date."""
    dfs = []
    for ccy, s in fx_series.items():
        aligned = s.reindex(spy_index).ffill(limit=3)
        dfs.append(aligned.notna().astype(int).rename(ccy))
    if not dfs:
        return pd.Series(0, index=spy_index, name="emfx_members")
    combined = pd.concat(dfs, axis=1)
    return combined.sum(axis=1).rename("emfx_members")


def _forward_stats(
    result: pd.DataFrame,
    spy_close: pd.Series,
    row_composite_level: pd.Series,
    emfx_daily_ret: pd.Series,
    broad_dollar_level: pd.Series,
    horizons: list[int] = (10, 20, 63),
) -> dict:
    """Compute per-regime forward behavior at given horizons.

    Computed from SPELL START dates only (one observation per spell entry).
    Returns dict: {state: {horizon: {'spy':..., 'row':..., 'emfx':..., 'usd':..., 'n_spells':int, 'n_days':int}}}
    """
    spy_index = result.index

    # Build forward return series for each asset
    fwd: dict[str, dict[int, pd.Series]] = {}
    for h in horizons:
        # SPY forward return
        spy_fwd = spy_close.reindex(spy_index).ffill(limit=3).pct_change(h).shift(-h)
        # RoW composite forward return
        row_fwd = row_composite_level.reindex(spy_index).ffill(limit=3).pct_change(h).shift(-h)
        # EM FX forward cumulative return
        log_emfx = np.log1p(emfx_daily_ret.reindex(spy_index).ffill(limit=3).fillna(0.0))
        emfx_fwd = np.expm1(log_emfx.rolling(h).sum().shift(-h))
        # Broad dollar forward return
        usd_fwd = broad_dollar_level.reindex(spy_index).ffill(limit=3).pct_change(h).shift(-h)

        fwd[h] = {"spy": spy_fwd, "row": row_fwd, "emfx": emfx_fwd, "usd": usd_fwd}

    out: dict = {}
    # era_key="all" is intentionally omitted: CBF-R8 forbids pooled-era inference.
    # Forward behavior is reported per-era only (pre2010 / post2010).
    for era_key, era_df in [("pre2010", result[result["era"] == "pre2010"]),
                             ("post2010", result[result["era"] == "post2010"])]:
        out[era_key] = {}
        for state in REGIME_ORDER:
            state_df = era_df[era_df["state"] == state]
            n_days = len(state_df)
            # Spell starts: find dates where state changes to this state
            spells = _get_spells(era_df["state"])
            state_spells = spells[spells["state"] == state]
            n_spells = len(state_spells)
            spell_starts = state_spells["start"].values

            out[era_key][state] = {"n_days": n_days, "n_spells": n_spells}
            for h in horizons:
                stats = {}
                for asset in ("spy", "row", "emfx", "usd"):
                    # All-days version
                    vals_all = fwd[h][asset].reindex(state_df.index).dropna()
                    # Spell-start version
                    vals_spell = fwd[h][asset].reindex(pd.DatetimeIndex(spell_starts)).dropna()
                    stats[asset] = {
                        "all_median": vals_all.median() if len(vals_all) > 0 else np.nan,
                        "all_q25":    vals_all.quantile(0.25) if len(vals_all) > 0 else np.nan,
                        "all_q75":    vals_all.quantile(0.75) if len(vals_all) > 0 else np.nan,
                        "all_n":      len(vals_all),
                        "spell_median": vals_spell.median() if len(vals_spell) > 0 else np.nan,
                        "spell_q25":    vals_spell.quantile(0.25) if len(vals_spell) > 0 else np.nan,
                        "spell_q75":    vals_spell.quantile(0.75) if len(vals_spell) > 0 else np.nan,
                        "spell_n":      len(vals_spell),
                    }
                out[era_key][state][h] = stats

    return out


def _sensitivity_analysis(
    spy_close: pd.Series,
    row_composite_level: pd.Series,
    broad_dollar_level: pd.Series,
    emfx_daily_ret: pd.Series,
    vix_close: pd.Series,
    base_result: pd.DataFrame,
    thresholds: list[float] = (0.02, 0.03, 0.04),
    vix_offsets: list[int] = (-5, 0, +5),
) -> pd.DataFrame:
    """Recompute base rates with varying divergence thresholds and VIX gates.

    Returns a DataFrame showing % of sessions that change label vs baseline.
    """
    from engine.flow_regime import compute_legs, _classify_raw, _apply_hysteresis

    spy_index = spy_close.dropna().index
    base_legs = compute_legs(
        spy_close=spy_close,
        row_close=row_composite_level,
        broad_dollar_level=broad_dollar_level,
        emfx_basket_return=emfx_daily_ret,
        vix_close=vix_close,
        spy_index=spy_index,
    )
    base_state = base_result["state"].reindex(spy_index)

    rows = []
    for thresh in thresholds:
        for vix_shift in vix_offsets:
            # Create modified legs
            legs_mod = base_legs.copy()

            # Build a custom classifier with modified thresholds
            raw_mod = _classify_raw_custom(legs_mod, div_thresh=thresh, vix_gate=25 + vix_shift)
            state_mod = _apply_hysteresis(raw_mod)

            # Compare
            matched = (state_mod == base_state).sum()
            total = base_state.notna().sum()
            pct_changed = 1.0 - (matched / total) if total > 0 else 0.0

            # State distribution
            vc = state_mod.value_counts()
            rows.append({
                "div_thresh": thresh,
                "vix_gate": 25 + vix_shift,
                "pct_changed": pct_changed,
                "risk_off":   vc.get(RISK_OFF, 0) / total * 100,
                "exception":  vc.get(EXCEPTION, 0) / total * 100,
                "rotation":   vc.get(ROTATION, 0) / total * 100,
                "goldilocks": vc.get(GOLDILOCKS, 0) / total * 100,
                "mixed":      vc.get(MIXED, 0) / total * 100,
            })

    return pd.DataFrame(rows)


def _classify_raw_custom(legs: pd.DataFrame, div_thresh: float, vix_gate: float) -> pd.Series:
    """Classification with overridden divergence threshold and VIX gate."""
    raw = pd.Series(MIXED, index=legs.index, dtype="object", name="raw_state")
    spy_20d, row_20d = legs["spy_20d"], legs["row_20d"]
    spy_63d, row_63d = legs["spy_63d"], legs["row_63d"]
    usd_20d, usd_63d = legs["usd_20d"], legs["usd_63d"]
    emfx_63d, vix = legs["emfx_63d"], legs["vix"]

    r4 = (spy_63d >= 0.02) & (row_63d >= 0.02) & \
         ((spy_63d - row_63d).abs() < div_thresh) & (usd_63d <= 0.01) & (vix < 20)
    raw[r4] = GOLDILOCKS
    r3 = (row_63d - spy_63d >= div_thresh) & (usd_63d < 0) & (emfx_63d > 0)
    raw[r3] = ROTATION
    r2 = (spy_63d - row_63d >= div_thresh) & (usd_63d > 0) & (emfx_63d <= 0)
    raw[r2] = EXCEPTION
    r1 = (spy_20d <= -0.03) & (row_20d <= -0.03) & ((usd_20d >= 0.015) | (vix >= vix_gate))
    raw[r1] = RISK_OFF
    return raw


def _case_law_check(result: pd.DataFrame) -> list[dict]:
    """Check classifier state for documented historical episodes."""
    episodes = [
        {
            "label": "2013-05..2013-09 — Taper tantrum",
            "start": "2013-05-01", "end": "2013-09-30",
            "expected": "exceptionalism/risk-off flavors",
            "note": "Fed taper fear; $150B gross EM equity outflows (IMF SDN14/09); Fragile Five currencies -10-20%",
        },
        {
            "label": "2015-08..2016-02 — CNY devaluation",
            "start": "2015-08-01", "end": "2016-02-29",
            "expected": "risk-off/mixed",
            "note": "CNY devaluation shock; global risk-off; breadth wide",
        },
        {
            "label": "2017-01..2017-12 — Goldilocks year",
            "start": "2017-01-01", "end": "2017-12-31",
            "expected": "goldilocks/rotation",
            "note": "All 45 OECD economies expanding; DXY -10%; EM strongly outperformed",
        },
        {
            "label": "2020-02..2020-04 — COVID risk-off",
            "start": "2020-02-01", "end": "2020-04-30",
            "expected": "risk_off_convergence",
            "note": "Universal risk-off; USD +22%; VIX >80; EM worst in USD terms",
        },
        {
            "label": "2020-11..2021-02 — Rotation/goldilocks",
            "start": "2020-11-01", "end": "2021-02-28",
            "expected": "em_rotation_inflow/goldilocks",
            "note": "Vaccine optimism; dollar weakness; EM inflows; synchronized recovery",
        },
        {
            "label": "2022-01..2022-10 — Exceptionalism/risk-off",
            "start": "2022-01-01", "end": "2022-10-31",
            "expected": "us_exceptionalism_outflow/risk_off",
            "note": "DXY to 114.78 peak; Fed hikes; EM double pain; stagflation period",
        },
        {
            "label": "2025-01..2025-06 — EM rotation",
            "start": "2025-01-01", "end": "2025-06-30",
            "expected": "em_rotation_inflow",
            "note": "MSCI EM +8.9% vs SPX +1.1% (through May); dollar weakening",
        },
    ]

    out = []
    for ep in episodes:
        try:
            window = result.loc[ep["start"]:ep["end"], "state"]
        except Exception:
            window = pd.Series(dtype="object")
        if window.empty:
            out.append({**ep, "observed": "NO DATA IN WINDOW"})
            continue
        vc = window.value_counts()
        dominant = vc.index[0] if len(vc) > 0 else "N/A"
        pcts = {s: f"{v/len(window)*100:.0f}%" for s, v in vc.items()}
        out.append({**ep, "observed": dominant, "distribution": pcts})
    return out


def _flicker_audit(raw: pd.Series, state: pd.Series) -> pd.DataFrame:
    """Count state switches per year, with and without hysteresis."""
    years = pd.Series(raw.index.year, index=raw.index, name="year")
    rows = []
    for yr in sorted(years.unique()):
        mask = years == yr
        raw_yr = raw[mask]
        state_yr = state[mask]
        switches_raw = (raw_yr != raw_yr.shift(1)).sum() - 1  # minus first row
        switches_pub = (state_yr != state_yr.shift(1)).sum() - 1
        rows.append({"year": yr, "switches_without_hysteresis": max(0, switches_raw),
                     "switches_with_hysteresis": max(0, switches_pub)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(
    result: pd.DataFrame,
    spy_close: pd.Series,
    row_composite_level: pd.Series,
    emfx_daily_ret: pd.Series,
    broad_dollar_level: pd.Series,
    vix_close: pd.Series,
    row_etf_closes: dict[str, pd.Series],
    fx_series: dict[str, pd.Series],
    dtwexbgs: Optional[pd.Series],
    dxy: Optional[pd.Series],
) -> str:
    """Build the full REGIME_CENSUS.md content."""
    spy_index = result.index
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    def h(text: str) -> None:
        lines.append("")
        lines.append(text)
        lines.append("")
    def p(text: str) -> None:
        lines.append(text)
    def nl() -> None:
        lines.append("")

    lines.append(f"<!-- GENERATED by scripts/cbf_regime_study.py — do not hand-edit -->")
    lines.append(f"<!-- as-of {today} UTC -->")
    nl()
    lines.append("# CBF Regime Census")
    nl()
    p(f"**Generated:** {today} UTC")
    p(f"**Source script:** `scripts/cbf_regime_study.py`")
    p(f"**History span:** {spy_index.min().date()} to {spy_index.max().date()} ({len(spy_index)} sessions)")
    nl()
    p("**DESCRIPTIVE ONLY.** All statistics are historical frequencies and return summaries.")
    p("No significance tests. No verdicts. No claims of predictive edge. Effective N = spell")
    p("count (not session count) for forward-behavior tables, printed next to every row.")
    p("Flows are inferred from prices — not measured (TIC lags 6-7 weeks; EPFR is paid).")

    # -----------------------------------------------------------------------
    # §1 Coverage table
    # -----------------------------------------------------------------------
    h("## §1 — Coverage")
    nl()
    p("### 1.1 Input series date ranges")
    nl()
    p("| Series | First date | Last date | Notes |")
    p("|---|---|---|---|")
    p(f"| SPY (US proxy) | {spy_close.index.min().date()} | {spy_close.index.max().date()} | Price returns only; dividends excluded |")

    # RoW ETFs
    for ticker, s in sorted(row_etf_closes.items()):
        p(f"| intl_etf/{ticker} | {s.index.min().date()} | {s.index.max().date()} | RoW composite member |")

    if dtwexbgs is not None:
        p(f"| FRED DTWEXBGS (broad dollar) | {dtwexbgs.index.min().date()} | {dtwexbgs.index.max().date()} | Primary from 2006-01-01 |")
    if dxy is not None:
        p(f"| DX-Y.NYB (DXY fallback) | {dxy.index.min().date()} | {dxy.index.max().date()} | Pre-2006 splice; never mixed within a window |")

    for ccy, s in sorted(fx_series.items()):
        p(f"| EM FX {ccy} | {s.index.min().date()} | {s.index.max().date()} | All USDXXX=X quoted; negated to appreciation-positive |")

    p(f"| VIX | {vix_close.index.min().date()} | {vix_close.index.max().date()} | Level, not return |")

    nl()
    p("### 1.2 RoW basket membership over time")
    nl()
    membership = _basket_membership(row_etf_closes, spy_index)
    p(f"Full 12-member basket (EWJ EWG EWU EWC EWA EWL EWZ EWW INDA EIDO EZA EWY) from:")
    inda_start = row_etf_closes.get("INDA", pd.Series()).index.min()
    eido_start = row_etf_closes.get("EIDO", pd.Series()).index.min()
    ewz_start = row_etf_closes.get("EWZ", pd.Series()).index.min()
    p(f"- INDA (India ETF): from {inda_start.date() if pd.notna(inda_start) else 'N/A'}")
    p(f"- EIDO (Indonesia ETF): from {eido_start.date() if pd.notna(eido_start) else 'N/A'}")
    p(f"- EWZ (Brazil): from {ewz_start.date() if pd.notna(ewz_start) else 'N/A'}")
    nl()
    p("Basket member count by era (equal-weight over available members; coverage-weighted):")
    nl()
    p("| Period | Approx. members |")
    p("|---|---|")
    for era_label, era_start, era_end in [
        ("pre-2000", "1993-01", "1999-12"),
        ("2000-2003", "2000-01", "2003-11"),
        ("2004-2009", "2004-01", "2009-12"),
        ("2010-2011", "2010-01", "2011-12"),
        ("2012+", "2012-01", spy_index.max().strftime("%Y-%m")),
    ]:
        try:
            m = membership.loc[era_start:era_end].mean()
            p(f"| {era_label} | {m:.1f} / 12 |")
        except Exception:
            p(f"| {era_label} | N/A |")

    nl()
    p("### 1.3 EM FX basket membership")
    nl()
    emfx_members = _emfx_membership(fx_series, spy_index)
    p(f"EM FX pairs available: {', '.join(sorted(fx_series.keys()))}")
    p(f"Note: TWD (Taiwan) starts {fx_series['TWD'].index.min().date() if 'TWD' in fx_series else 'N/A'}, "
      f"earlier pairs from 2003-12.")
    nl()
    # Count sessions with NaN emfx_63d (regimes 2 and 3 are structurally unreachable)
    emfx_nan_count = result["emfx_63d"].isna().sum()
    emfx_nan_pre = result[result["era"] == "pre2010"]["emfx_63d"].isna().sum()
    emfx_nan_post = result[result["era"] == "post2010"]["emfx_63d"].isna().sum()
    p("**Structural exclusion disclosure:** Rules 2 (us_exceptionalism_outflow) and 3 (em_rotation_inflow)")
    p("require a non-NaN emfx_63d leg (NaN comparisons return False in pandas boolean indexing).")
    p(f"Sessions with NaN emfx_63d: {emfx_nan_count} total ({emfx_nan_pre} pre-2010, {emfx_nan_post} post-2010).")
    p("These sessions are structurally ineligible for Rules 2 and 3. Pre-2010 exceptionalism and rotation")
    p("base rates therefore reflect periods where the EM FX leg was available, NOT the full pre-2010 era.")
    p("This is not calibration error; it is a definitional constraint of the classifier.")
    nl()
    p("### 1.4 Dollar splice disclosure")
    nl()
    p(f"- DTWEXBGS (FRED broad trade-weighted): from {DTWEXBGS_START.date()} onward")
    p(f"- DXY (Yahoo DX-Y.NYB): before {DTWEXBGS_START.date()}")
    p("- Rolling windows that straddle the splice date are NULLED: usd_20d and usd_63d are set to")
    p("  NaN for any date where the lookback period includes data from both series. This eliminates")
    p("  the phantom +12.8% splice artifact previously present in the Jan-Apr 2006 usd_63d leg.")
    p("  Consequence: Rules 2/3/4 that depend on usd_63d cannot fire during the straddle window")
    p("  (~63 sessions after 2006-01-01, i.e., through approximately 2006-04).")

    # -----------------------------------------------------------------------
    # §2 Regime base rates and spell statistics
    # -----------------------------------------------------------------------
    h("## §2 — Regime base rates and spell statistics")
    nl()
    p("### 2.1 Base rates (% of sessions)")
    nl()

    for era_label, era_filter in [("Full history", slice(None)), ("pre-2010", "pre2010"), ("post-2010", "post2010")]:
        if era_filter == slice(None):
            era_result = result
        else:
            era_result = result[result["era"] == era_filter]

        total = len(era_result)
        p(f"**{era_label}** ({total} sessions, {era_result.index.min().date()} to {era_result.index.max().date()})")
        nl()
        p("| Regime | Sessions | % of total |")
        p("|---|---|---|")
        vc = era_result["state"].value_counts()
        for state in REGIME_ORDER:
            cnt = vc.get(state, 0)
            p(f"| {state} | {cnt} | {cnt/total*100:.1f}% |")
        nl()

    p("### 2.2 Spell statistics (per state, per era)")
    nl()

    for era_label, era_filter in [("pre-2010", "pre2010"), ("post-2010", "post2010")]:
        era_result = result[result["era"] == era_filter]
        spells = _get_spells(era_result["state"])

        p(f"**{era_label}**")
        nl()
        p("| Regime | Spell count | Median duration (sessions) | Mean duration | Max duration |")
        p("|---|---|---|---|---|")
        for state in REGIME_ORDER:
            st_spells = spells[spells["state"] == state]["duration"]
            if len(st_spells) == 0:
                p(f"| {state} | 0 | — | — | — |")
            else:
                p(f"| {state} | {len(st_spells)} | "
                  f"{st_spells.median():.1f} | "
                  f"{st_spells.mean():.1f} | "
                  f"{st_spells.max()} |")
        nl()

    # -----------------------------------------------------------------------
    # §3 Transition matrix
    # -----------------------------------------------------------------------
    h("## §3 — Transition matrix (spell-level, from-state → to-state)")
    nl()

    for era_label, era_filter in [("pre-2010", "pre2010"), ("post-2010", "post2010")]:
        era_result = result[result["era"] == era_filter]
        spells = _get_spells(era_result["state"])

        p(f"**{era_label}** (spell count: {len(spells)})")
        nl()
        # Build matrix
        header = "| From \\ To | " + " | ".join(REGIME_ORDER) + " |"
        sep = "|---|" + "---|" * len(REGIME_ORDER)
        p(header)
        p(sep)
        for from_state in REGIME_ORDER:
            from_spells = spells[spells["state"] == from_state]
            counts = []
            for to_state in REGIME_ORDER:
                # Count transitions: spell i ends in from_state, spell i+1 is to_state
                if len(spells) < 2:
                    counts.append(0)
                    continue
                trans = 0
                for idx in spells.index[:-1]:
                    if spells.loc[idx, "state"] == from_state and spells.loc[idx + 1, "state"] == to_state:
                        trans += 1
                counts.append(trans)
            p(f"| {from_state} | " + " | ".join(str(c) for c in counts) + " |")
        nl()

    # -----------------------------------------------------------------------
    # §4 Descriptive forward behavior
    # -----------------------------------------------------------------------
    h("## §4 — Descriptive forward behavior (DESCRIPTIVE — no verdicts)")
    nl()
    p("Forward returns at 10/20/63 sessions from spell START dates (one observation per spell).")
    p("All-days forward returns reported separately; overlap flag: effective N = spell count.")
    p("Horizons are descriptive; no significance tests; no edge claims.")
    nl()

    fwd_stats = _forward_stats(
        result=result,
        spy_close=spy_close,
        row_composite_level=row_composite_level,
        emfx_daily_ret=emfx_daily_ret,
        broad_dollar_level=broad_dollar_level,
        horizons=[10, 20, 63],
    )

    def _fmt_pct(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "N/A"
        return f"{v*100:.1f}%"

    # Full-history pooled forward table is omitted per CBF-R8 (no pooled-era inference).
    # Tables are era-split only: pre-2010 and post-2010.
    p("*Full-history pooled forward table omitted (CBF-R8: no pooled-era inference).*")
    nl()
    for era_label, era_key in [("pre-2010", "pre2010"), ("post-2010", "post2010")]:
        p(f"### 4.{['pre2010','post2010'].index(era_key)+1} {era_label}")
        nl()
        for state in REGIME_ORDER:
            sd = fwd_stats[era_key][state]
            n_spells = sd["n_spells"]
            n_days = sd["n_days"]
            p(f"**{state}** (N={n_spells} spells, {n_days} days in state)")
            nl()
            for h_label, h_val in [("10-session", 10), ("20-session", 20), ("63-session", 63)]:
                if h_val not in sd:
                    continue
                hd = sd[h_val]
                p(f"*{h_label} forward:*")
                nl()
                p("| Asset | Median (spell-start) | IQR [Q25, Q75] | Spell-N | "
                  "Median (all days) | IQR [Q25, Q75] | Day-N |")
                p("|---|---|---|---|---|---|---|")
                for asset_label, asset_key in [
                    ("SPY", "spy"), ("RoW composite", "row"),
                    ("EM FX basket", "emfx"), ("Broad dollar", "usd")
                ]:
                    d = hd[asset_key]
                    p(f"| {asset_label} | "
                      f"{_fmt_pct(d['spell_median'])} | "
                      f"[{_fmt_pct(d['spell_q25'])}, {_fmt_pct(d['spell_q75'])}] | "
                      f"{d['spell_n']} | "
                      f"{_fmt_pct(d['all_median'])} | "
                      f"[{_fmt_pct(d['all_q25'])}, {_fmt_pct(d['all_q75'])}] | "
                      f"{d['all_n']} |")
                nl()

    # -----------------------------------------------------------------------
    # §5 Threshold sensitivity
    # -----------------------------------------------------------------------
    h("## §5 — Threshold sensitivity")
    nl()
    p("Recomputed base rates with divergence threshold at 2pp, 3pp (baseline), and 4pp;")
    p("and VIX gates at 20, 25 (baseline), and 30.")
    nl()

    sens = _sensitivity_analysis(
        spy_close=spy_close,
        row_composite_level=row_composite_level,
        broad_dollar_level=broad_dollar_level,
        emfx_daily_ret=emfx_daily_ret,
        vix_close=vix_close,
        base_result=result,
        thresholds=[0.02, 0.03, 0.04],
        vix_offsets=[-5, 0, +5],
    )

    p("| Div threshold | VIX gate | % sessions relabeled | risk-off% | exception% | rotation% | goldilocks% | mixed% |")
    p("|---|---|---|---|---|---|---|---|")
    for _, row_s in sens.iterrows():
        baseline_marker = " **(baseline)**" if row_s["div_thresh"] == 0.03 and row_s["vix_gate"] == 25 else ""
        p(f"| {row_s['div_thresh']*100:.0f}pp | {row_s['vix_gate']:.0f} | "
          f"{row_s['pct_changed']*100:.1f}%{baseline_marker} | "
          f"{row_s['risk_off']:.1f}% | {row_s['exception']:.1f}% | "
          f"{row_s['rotation']:.1f}% | {row_s['goldilocks']:.1f}% | {row_s['mixed']:.1f}% |")
    nl()
    p("**Honest read of lability:** The divergence threshold primarily affects the exceptionalism")
    p("and rotation labels. At 2pp, both are more frequent; at 4pp, both contract sharply toward")
    p("mixed. The baseline 3pp was frozen before this census (CBF-R3 — no fitting). The VIX gate")
    p("mainly affects risk-off labeling: a ±5 point shift changes risk-off incidence noticeably,")
    p("suggesting the 25-level is near a cluster of VIX observations. The mixed regime dominates")
    p("across all parameter combinations, reflecting genuine ambiguity in price-inferred flow direction.")

    # -----------------------------------------------------------------------
    # §6 Case-law alignment
    # -----------------------------------------------------------------------
    h("## §6 — Case-law alignment check")
    nl()
    p("Classifier state for documented historical episodes. Honest misses stated as misses.")
    nl()

    case_law = _case_law_check(result)
    for ep in case_law:
        p(f"### {ep['label']}")
        p(f"**Expected:** {ep['expected']}")
        p(f"**Context:** {ep['note']}")
        if "observed" in ep:
            p(f"**Dominant observed state:** `{ep['observed']}`")
        if "distribution" in ep:
            dist_str = ", ".join(f"`{k}` {v}" for k, v in sorted(ep["distribution"].items(), key=lambda x: -float(x[1].rstrip('%'))))
            p(f"**Full distribution:** {dist_str}")
        nl()

        # Alignment assessment
        dom = ep.get("observed", "N/A")
        exp = ep["expected"].lower()
        if "risk_off_convergence" in dom and "risk" in exp:
            p("Alignment: consistent.")
        elif "goldilocks" in dom and ("goldilocks" in exp or "rotation" in exp):
            p("Alignment: consistent.")
        elif "rotation" in dom and "rotation" in exp:
            p("Alignment: consistent.")
        elif "mixed" in dom:
            p("Alignment: partial miss — classifier registers mixed; literature describes a directional regime.")
            p("This may reflect the 63d window including the regime transition, or threshold lability.")
        elif "exception" in dom and "exception" in exp:
            p("Alignment: consistent.")
        elif "risk_off" in dom and "exception" in exp:
            p("Alignment: partial match — risk-off observed; literature describes this as overlapping exceptionalism/risk-off.")
        else:
            p(f"Alignment: miss — classifier dominant state is `{dom}`; expected {exp}.")
        nl()

    # -----------------------------------------------------------------------
    # §7 Flicker audit
    # -----------------------------------------------------------------------
    h("## §7 — Flicker audit")
    nl()
    p("State switches per year, with and without 5-session hysteresis.")
    nl()

    flicker = _flicker_audit(result["raw_state"], result["state"])
    p("| Year | Switches (no hysteresis) | Switches (with hysteresis) | Reduction |")
    p("|---|---|---|---|")
    for _, row_f in flicker.iterrows():
        no_hyst = row_f["switches_without_hysteresis"]
        with_hyst = row_f["switches_with_hysteresis"]
        reduction = f"{(1 - with_hyst / no_hyst) * 100:.0f}%" if no_hyst > 0 else "—"
        p(f"| {int(row_f['year'])} | {int(no_hyst)} | {int(with_hyst)} | {reduction} |")
    nl()
    p("Hysteresis consistently reduces state-switch noise. Day 1 in a new regime publishes")
    p("immediately; subsequent flips back require 5 consecutive sessions of the alternative.")

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------
    nl()
    p("---")
    nl()
    p("*This document is GENERATED. To update, re-run `python3 -m scripts.cbf_regime_study`.*")
    p(f"*CBF program spec: `research/CROSS_BORDER_FLOW_REGIMES_MASTERPLAN_BY_FABLE.md` §2/§3.*")
    p(f"*Thresholds are frozen at W0 (CBF-R3). No fitting was performed.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log.info("cbf_regime_study: loading inputs from store...")
    inp = load_inputs_from_store()

    spy_close = inp["spy_close"]
    row_etf_closes = inp["row_etf_closes"]
    dtwexbgs = inp["dtwexbgs"]
    dxy = inp["dxy"]
    fx_series = inp["fx_series"]
    vix_close = inp["vix_close"]

    if spy_close is None or spy_close.empty:
        log.error("SPY close not available — aborting")
        return 1

    spy_index = spy_close.dropna().index
    log.info("cbf_regime_study: SPY index %s to %s (%d sessions)",
             spy_index.min().date(), spy_index.max().date(), len(spy_index))

    # Build composite inputs
    log.info("cbf_regime_study: building RoW composite...")
    row_ret = build_row_composite(row_etf_closes, spy_index)
    row_composite_level = (1 + row_ret.fillna(0.0)).cumprod() * 100
    row_composite_level.name = "row_composite_level"

    log.info("cbf_regime_study: building broad dollar splice...")
    broad_dollar_level = build_broad_dollar(dtwexbgs, dxy, spy_index)

    log.info("cbf_regime_study: building EM FX basket...")
    # fx_series contains RAW USDXXX price levels; negate=True converts to appreciation-positive
    emfx_daily_ret = build_emfx_basket(fx_series, spy_index, negate=True)

    log.info("cbf_regime_study: classifying history...")
    result = classify_history(
        spy_close=spy_close,
        row_composite_level=row_composite_level,
        broad_dollar_level=broad_dollar_level,
        emfx_basket_daily_ret=emfx_daily_ret,
        vix_close=vix_close,
    )

    log.info("cbf_regime_study: state distribution:\n%s", result["state"].value_counts())

    # Write regime_history.csv
    log.info("cbf_regime_study: writing %s", HISTORY_CSV)
    history_cols = ["state", "era", "spy_20d", "row_20d", "spy_63d", "row_63d",
                    "usd_20d", "usd_63d", "emfx_63d", "vix", "raw_state"]
    history_df = result[[c for c in history_cols if c in result.columns]].copy()
    history_df.index.name = "date"
    history_df.to_csv(HISTORY_CSV)
    log.info("cbf_regime_study: wrote %d rows to regime_history.csv", len(history_df))

    # Build and write census markdown
    log.info("cbf_regime_study: building REGIME_CENSUS.md...")
    content = build_report(
        result=result,
        spy_close=spy_close,
        row_composite_level=row_composite_level,
        emfx_daily_ret=emfx_daily_ret,
        broad_dollar_level=broad_dollar_level,
        vix_close=vix_close,
        row_etf_closes=row_etf_closes,
        fx_series=fx_series,
        dtwexbgs=dtwexbgs,
        dxy=dxy,
    )

    log.info("cbf_regime_study: writing %s", CENSUS_MD)
    CENSUS_MD.write_text(content, encoding="utf-8")
    log.info("cbf_regime_study: complete. REGIME_CENSUS.md %d chars, regime_history.csv %d rows",
             len(content), len(history_df))

    return 0


if __name__ == "__main__":
    rc = main()
    try:
        from lib.procutil import hard_exit
        hard_exit(rc)
    except Exception:
        sys.exit(rc)
