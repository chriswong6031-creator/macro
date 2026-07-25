#!/usr/bin/env python3
"""Personality Timing Codex — per-name measured-structure store (W2, display-tier).

Masterplan: research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §3 (W2).
Charter (evidence base): research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md
§8 — the verdict this store operationalizes: structure-tailoring (measure the
bars → derive the rung) is the only fitting method above the random floor, and
the derived-rung Stoch-RSI tool CONFIRMS RESETS — it does not identify lows in
advance.

WHAT THIS IS. A measurement store, one row per name, covering the whole
mwr_phase1 universe (~1,63x names — NOT the narrower W1-eligibility panel; the
codex measures everyone). It records each name's reversion-by-scale structure,
its derived rung under BOTH the full and recent windows, the reset-behavior
profile of the derived-rung tool under the TIMING ruler, and (where present)
the W1/W1-T study-evidence joins. Every construction and metric is IMPORTED
from the two pinned W1 scripts — nothing is re-implemented — so the codex is
byte-consistent with the studies it summarizes.

COPY LAW R-W1T-3 (charter §7/§8). The derived-rung tool is a RESET CONFIRMER:
it fires shallow-adverse, typically after the trough (lateness IS the safety).
It confirms that a reset is underway; it does NOT claim to identify the low in
advance. Nothing in this store, its columns, or any consumer may frame the tool
as identifying/picking a market low ("bottom"-identification framing is banned).
"Reset confirmation" and "reset-confirmer lateness" are the sanctioned terms.

STUDY-ERA HINDSIGHT DISCLAIMER (charter §8 "store both, label both"; DNR §2
two-ruler audition kill). The columns rung_best_fwd63_test and
rung_best_umae_test are the argmax rung/tool chosen with OUT-OF-SAMPLE OUTCOMES
already visible — i.e. STUDY-ERA HINDSIGHT (audition-tier). They exist ONLY to
show, per name, how ruler-dependent the "best" rung is (fwd63 vs the timing
ruler can disagree). They are DISPLAY CONTEXT ONLY and MUST NEVER be used as a
selection input for any live tool choice — the lawful selector is rung_derived
(bars-only, zero outcome input). Using rung_best_* to pick a live tool re-opens
the two-ruler audition kill (DNR §2).

TIER / AUTHORITY. Display-tier context store. Deterministic arithmetic only; no
LLM origination; no graded-board writes; nothing here promotes any tool to
authority (rank/size/gate) — promotion needs its own prereg + gauntlet.

OFF THE RENDER PATH. This runs MANUAL / WEEKLY (regen command below). It is NOT
wired into the nightly dag.yml or engine/run.py — nightly wiring is a later wave
(W3+). Runtime target < 10 min on the survivor tape.

Schema: personality_timing.codex.v1
Output: data/personality_timing/codex.parquet
Regen:  python3 scripts/build_personality_codex.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Constructions + metric definitions are imported verbatim from the pinned W1
# scripts — the codex must not re-implement any of them (masterplan §W2).
from scripts.research.ptt_w1_persistence_of_fit import (  # noqa: E402
    RUNGS,
    bars_for,
    ou_halflife,
    rho_window,
    rung_from_rhos,
    tool_dates,
    volcluster_halflife,
)
from scripts.research.ptt_w1_timing_regrade import (  # noqa: E402
    metric_arrays,
    null_stats,
    sig_metrics,
)

OHLCV = ROOT / "data" / "baskets" / "ohlcv"
SPY_PQ = ROOT / "data" / "yahoo" / "SPY.parquet"
W1_PANEL = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
W1T_PANEL = ROOT / "data" / "research" / "ptt_w1t_panel.parquet"
LABELS = ROOT / "data" / "research" / "personality_pit_labels.parquet"
OUT_DIR = ROOT / "data" / "personality_timing"
OUT_PQ = OUT_DIR / "codex.parquet"

MIN_BARS = 60          # bars for a full-window rho (W1 MIN_BARS_FIT)
RECENT_DAYS = 756      # ~3 trading years for the recent window
TERCILE_MIN = 30       # min built rows before slow_defensive terciles are computed
TOOLS = [f"S{r}" for r in RUNGS] + [f"M{r}" for r in RUNGS]  # the 6-tool grid


# ── universe filter (byte-identical to mwr_phase1_conditioner_study.py) ────────

def _passes_filter(px: pd.Series) -> bool:
    """≥2900 daily closes, first bar ≤ 2014-06-30, last AND median close ≥ $2.
    NO W1-eligibility gate — the codex is a measurement store over the full
    mwr_phase1 universe (~1,63x names)."""
    if len(px) < 2900 or px.index[0] > pd.Timestamp("2014-06-30"):
        return False
    if float(px.iloc[-1]) < 2 or float(px.median()) < 2:
        return False
    return True


# ── beta vs SPY ────────────────────────────────────────────────────────────
# House precedent for market beta is engine/equity_factors.py (reads SPY from
# the yahoo store, data/yahoo/SPY.parquet). The W2 brief named
# data/baskets/ohlcv/SPY.parquet, but that file does not exist in this repo —
# SPY is not in the ohlcv basket. We source the canonical yahoo close instead
# (documented deviation) so beta_spy is populated rather than universally NaN.

def _load_spy() -> pd.Series | None:
    if not SPY_PQ.exists():
        return None
    spy = pd.read_parquet(SPY_PQ)
    col = "close" if "close" in spy.columns else spy.columns[0]
    return spy[col].dropna()


def beta_vs_spy(px: pd.Series, spy_ret: pd.Series) -> float:
    """OLS slope of the name's daily returns on SPY daily returns, full window,
    over the common calendar. NaN if fewer than ~60 overlapping return days or
    SPY has zero variance on the overlap."""
    if spy_ret is None or spy_ret.empty:
        return float("nan")
    ret = px.pct_change().dropna()
    both = pd.concat([ret.rename("x"), spy_ret.rename("m")], axis=1, join="inner").dropna()
    if len(both) < 60:
        return float("nan")
    var_m = float(both["m"].var())
    if not np.isfinite(var_m) or var_m == 0:
        return float("nan")
    # slope = cov(x, m) / var(m) — the OLS beta of x on m
    return float(both["x"].cov(both["m"]) / var_m)


# ── structure block (full + recent windows) ────────────────────────────────

def _rhos_full(px: pd.Series) -> dict[str, float]:
    """Lag-1 autocorr of bar returns per rung on the FULL window (all data);
    bars built on the full series (anchor-A phase preserved) via bars_for."""
    return {r: rho_window(bars_for(px, r), None, None, MIN_BARS) for r in RUNGS}


def _rhos_recent(px: pd.Series) -> dict[str, float]:
    """Same rho ladder on the last RECENT_DAYS trading days. Bars are rebuilt on
    the recent close slice so the recent window uses only recent information."""
    recent_px = px.iloc[-RECENT_DAYS:] if len(px) > RECENT_DAYS else px
    return {r: rho_window(bars_for(recent_px, r), None, None, MIN_BARS) for r in RUNGS}


def _stationarity_recent(full: dict[str, float], recent: dict[str, float]) -> float:
    """Mean |Δρ| between the full and recent windows across the 3 rungs.
    NaN if any of the 6 rho values is missing (partial drift is not reported)."""
    diffs = [abs(full[r] - recent[r]) for r in RUNGS
             if np.isfinite(full.get(r, np.nan)) and np.isfinite(recent.get(r, np.nan))]
    return float(np.mean(diffs)) if len(diffs) == len(RUNGS) else float("nan")


# ── reset-behavior profile under the TIMING ruler ──────────────────────────

def reset_profile(px: pd.Series, rung: str) -> dict:
    """Fire the derived-rung Stoch-RSI tool over the FULL window and score every
    signal on the W1-T timing metrics (imported metric_arrays / sig_metrics).

    All metrics are RESET-CONFIRMATION metrics (charter §7): MAE63 = shallowest
    adverse excursion after entry (≤0; shallower = safer); prox = distance above
    the ±31td-window low (≥0); td_to_trough = signed offset of the low from
    entry (negative = trough BEFORE entry = a confirmed reset; positive small =
    entered near/just-after the low). Per R-W1T-3 these are never framed as
    identifying a low ahead of time: the tool confirms that a reset is underway.
    """
    c = px.to_numpy(dtype=float)
    m = metric_arrays(c)
    full_mask = np.ones(len(px), dtype=bool)
    nl = null_stats(m, full_mask)                        # all-days base rates
    sm = sig_metrics(px, m, tool_dates(bars_for(px, rung), "S"))

    out: dict = {
        "n_signals": int(len(sm)),
        "sig_mae_med": np.nan, "base_mae_med": np.nan, "umae": np.nan,
        "sig_w5_rate": np.nan, "base_w5_rate": np.nan, "uw5": np.nan,
        "med_tdt": np.nan,
        "called_low_share": np.nan, "confirmed_reset_share": np.nan,
        "early_share": np.nan, "base_called_rate": np.nan,
    }
    if not nl:
        return out  # base-rate universe too small (<60 valid days) — nulls stay NaN
    out["base_mae_med"] = float(nl["mae_med"])
    out["base_w5_rate"] = float(nl["w5_rate"])
    out["base_called_rate"] = float(nl["called_rate"])
    if len(sm) == 0:
        return out
    tdt = sm["tdt"].to_numpy(dtype=float)
    out["sig_mae_med"] = float(sm["mae63"].median())
    out["umae"] = out["sig_mae_med"] - out["base_mae_med"]
    out["sig_w5_rate"] = float(sm["w5"].mean() * 100)
    out["uw5"] = out["sig_w5_rate"] - out["base_w5_rate"]
    out["med_tdt"] = float(np.median(tdt))
    # td_to_trough partition (W1-T §7 item 3 language; descriptive only):
    #   called low       −2 ≤ tdt ≤ +5  (entered within a few bars of the low)
    #   confirmed reset   tdt < −2       (trough already in — a confirmed reset)
    #   early             tdt > +5       (fired ahead of the low)
    out["called_low_share"] = float(((tdt >= -2) & (tdt <= 5)).mean() * 100)
    out["confirmed_reset_share"] = float((tdt < -2).mean() * 100)
    out["early_share"] = float((tdt > 5).mean() * 100)
    return out


# ── study-evidence joins ───────────────────────────────────────────────────

def _argmax_rung_fwd63(row: pd.Series) -> str | float:
    """STUDY-ERA HINDSIGHT (audition-tier) — argmax rung over the 6 oos_{tool}
    fwd63 columns from the W1 panel. Display context ONLY; never a selector."""
    vals = {t: row.get(f"oos_{t}", np.nan) for t in TOOLS}
    s = pd.Series(vals)
    if s.isna().all():
        return np.nan
    best_tool = str(s.idxmax())
    return best_tool[1:]  # strip the family letter → the rung


def _argmax_rung_umae(row: pd.Series) -> str | float:
    """STUDY-ERA HINDSIGHT (audition-tier) — argmax rung over the 6
    umae_oos_{tool} timing-ruler columns from the W1-T panel. Display context
    ONLY; never a selector (DNR §2 two-ruler audition kill)."""
    vals = {t: row.get(f"umae_oos_{t}", np.nan) for t in TOOLS}
    s = pd.Series(vals)
    if s.isna().all():
        return np.nan
    best_tool = str(s.idxmax())
    return best_tool[1:]


def load_study_joins() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-name study-evidence columns keyed by sym (NaN where a name is absent
    from the study panel — the codex universe is wider than the W1 panel)."""
    w1 = pd.DataFrame(columns=["sym"])
    if W1_PANEL.exists():
        p1 = pd.read_parquet(W1_PANEL)
        rec = pd.DataFrame({
            "sym": p1["sym"],
            "stationarity_fit": p1.get("stationarity_fit"),
            "w1_fwd63_oos": p1.get("oos_w1b_pure"),
            "rung_best_fwd63_test": p1.apply(_argmax_rung_fwd63, axis=1),
        })
        w1 = rec

    w1t = pd.DataFrame(columns=["sym"])
    if W1T_PANEL.exists():
        p2 = pd.read_parquet(W1T_PANEL)
        rec2 = pd.DataFrame({
            "sym": p2["sym"],
            "w1t_umae_oos": p2.get("umae_oos_w1b_pure"),
            "w1t_uw5_oos": p2.get("uw5_oos_w1b_pure"),
            "rung_best_umae_test": p2.apply(_argmax_rung_umae, axis=1),
        })
        w1t = rec2
    return w1, w1t


# ── personality label join ─────────────────────────────────────────────────

def load_labels(as_of: pd.Timestamp) -> pd.DataFrame:
    """Latest archetype + chart_primary per ticker with date ≤ build date."""
    if not LABELS.exists():
        return pd.DataFrame(columns=["sym", "archetype", "chart_primary"])
    lab = pd.read_parquet(LABELS, columns=["ticker", "date", "archetype", "chart_primary"])
    lab = lab[lab["date"] <= as_of].sort_values("date")
    arch = lab[lab["archetype"].notna()].groupby("ticker")["archetype"].last()
    chart = lab[lab["chart_primary"].notna()].groupby("ticker")["chart_primary"].last()
    out = pd.DataFrame({"archetype": arch, "chart_primary": chart})
    out.index.name = "sym"
    return out.reset_index()


# ── per-name row ───────────────────────────────────────────────────────────

def build_row(f: Path, as_of_iso: str, spy_ret: pd.Series | None) -> dict | None:
    px = pd.read_parquet(f)["close"].dropna()
    if not _passes_filter(px):
        return None

    rho_full = _rhos_full(px)
    rung, measured = rung_from_rhos(rho_full)            # ("1W", False) if unmeasured
    rho_rec = _rhos_recent(px)
    rung_rec, _ = rung_from_rhos(rho_rec)

    row: dict = {
        "sym": f.stem,
        "as_of": as_of_iso,
        "n_days": int(len(px)),
        "first_date": str(px.index[0].date()),
        # measured structure — full window
        "rho_3d": rho_full["3D"], "rho_1w": rho_full["1W"], "rho_2w": rho_full["2W"],
        "rung_derived": rung,
        "p_measured": bool(measured),
        # no_reversion: all measured rhos > 0 (the structural "washouts continue"
        # class — display flag, never a decision by itself, charter §1)
        "no_reversion": bool(measured and all(rho_full[r] > 0 for r in RUNGS)),
        "ou_hl": ou_halflife(px),
        "trend_persistence": float((px > px.rolling(200).mean()).mean()),
        "vol_ann": float(px.pct_change().std() * np.sqrt(252) * 100),
        "volcl_hl": volcluster_halflife(px),
        "beta_spy": beta_vs_spy(px, spy_ret),
        # measured structure — recent window (last RECENT_DAYS trading days)
        "rho_3d_3y": rho_rec["3D"], "rho_1w_3y": rho_rec["1W"], "rho_2w_3y": rho_rec["2W"],
        "rung_derived_3y": rung_rec,
        "stationarity_recent": _stationarity_recent(rho_full, rho_rec),
    }
    # reset-behavior profile at the derived rung, under the timing ruler
    row.update(reset_profile(px, rung))
    return row


# ── driver ─────────────────────────────────────────────────────────────────

def main() -> None:
    as_of = pd.Timestamp(date.today())
    as_of_iso = as_of.date().isoformat()
    spy = _load_spy()
    spy_ret = spy.pct_change().dropna() if spy is not None else None

    files = sorted(OHLCV.glob("*.parquet"))
    rows: list[dict] = []
    failed: list[str] = []
    for f in files:
        try:
            r = build_row(f, as_of_iso, spy_ret)
        except Exception as exc:  # noqa: BLE001 — counted, never silent
            failed.append(f"{f.stem}: {type(exc).__name__}")
            continue
        if r is not None:
            rows.append(r)

    df = pd.DataFrame(rows)

    # slow_defensive: vol_ann in the BOTTOM tercile of the built universe
    # (fwd126-class marker per MWR §2d — a display FLAG, it decides nothing).
    df["slow_defensive"] = False
    if len(df) >= TERCILE_MIN:
        v0 = df["vol_ann"].quantile(1 / 3)
        df["slow_defensive"] = df["vol_ann"] <= v0
    # lateness_pctl: percentile rank of med_tdt across the names that have one
    # (charter §3 "reset-confirmer lateness" percentile). NOTE the sign of the
    # ruler: td_to_trough is negative when the trough is ALREADY IN before entry
    # (the most confirmed-reset, latest-firing names — e.g. GEF/UHT at ~-21td),
    # and positive when the tool fires AHEAD of the low. So a HIGH percentile =
    # a HIGH (more positive) med_tdt = an EARLIER-firing tool (less confirmation);
    # a LOW percentile = the most confirmed, latest-firing tool. NaN names get no
    # rank. Consumers must read the percentile with this ruler, never inverted.
    df["lateness_pctl"] = df["med_tdt"].rank(pct=True) * 100

    # study-evidence joins (NaN where a name is absent from the study panel)
    w1, w1t = load_study_joins()
    if len(w1):
        df = df.merge(w1, on="sym", how="left")
    if len(w1t):
        df = df.merge(w1t, on="sym", how="left")
    # ensure the join columns exist even when a panel was missing entirely
    for col in ["stationarity_fit", "w1_fwd63_oos", "rung_best_fwd63_test",
                "w1t_umae_oos", "w1t_uw5_oos", "rung_best_umae_test"]:
        if col not in df.columns:
            df[col] = np.nan

    # personality label join
    lab = load_labels(as_of)
    if len(lab):
        df = df.merge(lab, on="sym", how="left")
    for col in ["archetype", "chart_primary"]:
        if col not in df.columns:
            df[col] = np.nan

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PQ, index=False)

    # ── summary ────────────────────────────────────────────────────────────
    print(f"personality codex: {len(df)} rows written to {OUT_PQ.relative_to(ROOT)}")
    print(f"  files scanned: {len(files)}; load failures: {len(failed)}"
          + (f" ({'; '.join(failed[:5])}{'…' if len(failed) > 5 else ''})" if failed else ""))
    if len(df):
        rung_dist = df["rung_derived"].value_counts().to_dict()
        print(f"  rung distribution (full-window derived): {rung_dist}")
        print(f"    unmeasured → 1W fallback: {int((~df['p_measured']).sum())} names")
        print(f"  no_reversion (all ρ>0, 'washouts continue' class): "
              f"{int(df['no_reversion'].sum())} names "
              f"({100 * float(df['no_reversion'].mean()):.1f}%)")
        print(f"  slow_defensive (bottom vol tercile): {int(df['slow_defensive'].sum())} names")
        cov = int(df["archetype"].notna().sum())
        print(f"  personality-label coverage: {cov}/{len(df)} names carry an archetype")
        with_tdt = df["med_tdt"].dropna()
        if len(with_tdt):
            print(f"  reset lateness (med_tdt across {len(with_tdt)} measured names): "
                  f"p10 {with_tdt.quantile(0.10):+.0f}td · median "
                  f"{with_tdt.median():+.0f}td · p90 {with_tdt.quantile(0.90):+.0f}td "
                  f"(negative = trough before entry = confirmed reset)")
        w1cov = int(df["w1_fwd63_oos"].notna().sum())
        w1tcov = int(df["w1t_umae_oos"].notna().sum())
        print(f"  study-join coverage: W1 fwd63 {w1cov} names · W1-T timing {w1tcov} names")


if __name__ == "__main__":
    main()
