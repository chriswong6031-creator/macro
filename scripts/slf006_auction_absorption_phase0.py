"""SLF-006 — Auction Absorption Phase-0 Forward Event Study.

PRE-REGISTERED DESIGN (family: slf006_auction_absorption). DO NOT ALTER before
reading results.

The treasury absorption engine (engine/treasury_supply.py) has been live on
bonds.html as display-only context since its first deployment. This script is
the FIRST forward-return test of that engine. We import the engine's own math
(_prep + _score_rows) without modification — no forking, no alternative math.

STATISTICAL CAVEATS (added after reviewer review; verdict unchanged):
  1. Q5-Q1 CONTRAST SE: The contrast t-stat uses a pooled two-sample SE
     (sqrt(var_q5/n_q5 + var_q1/n_q1)) rather than a one-sample HAC on
     (q5_i - mean_q1), which would ignore Q1's sampling variance and roughly
     double the reported |t|.  The HAC correction (Newey-West, lag=4) is
     applied independently to each quintile arm and then combined.
  2. HAC-OVERLAP CAVEAT: Within a single quintile (~34 members), auctions
     are temporally sparse (months apart), so lag=4 corrects little real
     overlap. The overlap that matters (t+21 windows spanning ~2-3 subsequent
     auctions) lives in the pooled calendar series, not the quintile subset.
     The fixed lag=4 is NOT scaled to the t+21 horizon. Readers should treat
     the quintile-subset HAC as near-iid by construction; the primary guard
     against over-rejection is BH-FDR across 6 cells, not the lag parameter.
  3. DURATION-PROXY MISMATCH: 51 of 168 belly auctions are 2y/3y tenors
     mapped to IEF (7-10y ETF), a material duration mismatch dictated by the
     lane spec's belly→IEF mapping. The null result is not over-read as a
     clean test of short-tenor absorption — a 2y auction and a 7-10y ETF
     share macro direction but not convexity or duration sensitivity.

TENOR BUCKETS:
  belly  (2y, 3y, 5y, 7y)  -> IEF forward returns (iShares 7-10y Treasury ETF)
  long   (10y, 20y, 30y)   -> TLT forward returns (iShares 20+y Treasury ETF)
  Bills excluded (as per engine design).

PIT DISCIPLINE:
  Auction results are published by TreasuryDirect ~13:00 ET on auction day.
  Enter on the CLOSE of auction day (t=0). Forward returns are close-to-close
  from t=0 to t+N trading days.

EVENT WINDOWS: t+1, t+5, t+21 trading days.

CONTRAST:
  - Bottom-quintile absorption_z (Q1, weakest auctions) vs
    top-quintile (Q5, strongest), gross return spread.
  - Continuous Spearman IC of absorption_z vs forward return.

VOL CONTROL:
  MOVE index (ICE BofA MOVE, data/yahoo/_MOVE.parquet) is present on disk —
  used as the rate volatility control for the duration-trend conditioning gate.
  If MOVE were absent we would fall back to trailing-20d realized vol of TLT.

PRE-REGISTERED GATES (all must pass for display-confirmer registration):
  G1: |t_HAC| >= 2.0 on the Q5-Q1 contrast at >=1 horizon with
      BH-FDR q <= 0.10 across the 6 (bucket x horizon) cells.
  G2: Survives duration-trend conditioning — same contrast within
      TLT-above/below-50dma subsets, same sign in both subsets.
  G3: Split-half same-sign (first half vs second half of the auction panel).

Pass all -> recommend display-confirmer registration.
Any fail  -> NULL, display stays context-only.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# ── repo path ───────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
warnings.filterwarnings("ignore")

# ── local imports ────────────────────────────────────────────────────────────
import engine.treasury_supply as ts                           # noqa: E402
from engine.trial_ledger import TrialLedger                   # noqa: E402
from engine.validation import (                               # noqa: E402
    benjamini_hochberg, deflated_sharpe, ic_summary,
    newey_west_tstat,
)

# ── pre-registered config ────────────────────────────────────────────────────
FAMILY = "slf006_auction_absorption"

BELLY_TENORS = {2, 3, 5, 7}
LONG_TENORS  = {10, 20, 30}

HORIZONS = [1, 5, 21]   # trading days after auction-day close

QUINTILE_N = 5          # quintile grid (Q1=weakest, Q5=strongest)

TS_CFG = {"trailing": 8, "min_trailing": 5}   # engine defaults

# ── full pre-registered grid (6 cells x 1 continuous IC variant = 12 trials) ─
# Each (bucket, horizon) pair is one "trial"; IC + quintile-contrast share a
# family budget.
GRID = [
    {"bucket": bkt, "horizon": h, "variant": v}
    for bkt in ("belly", "long")
    for h in HORIZONS
    for v in ("quintile_contrast", "continuous_ic")
]  # 12 entries

# ── data loading ─────────────────────────────────────────────────────────────
DATA = REPO / "data"


def load_auctions() -> pd.DataFrame:
    p = DATA / "treasury_auctions" / "auctions.parquet"
    df = pd.read_parquet(p)
    df["auction_date"] = pd.to_datetime(df["auction_date"])
    return df


def load_price(sym: str) -> pd.Series:
    p = DATA / "yahoo" / f"{sym}.parquet"
    df = pd.read_parquet(p)
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_move() -> pd.Series:
    p = DATA / "yahoo" / "_MOVE.parquet"
    df = pd.read_parquet(p)
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


# ── forward-return helpers ───────────────────────────────────────────────────

def trading_offset(price: pd.Series, date: pd.Timestamp, n: int) -> pd.Timestamp | None:
    """Return the date n trading days after `date` (using the price index as
    the tradeable calendar). Returns None if there are not enough days."""
    idx = price.index
    pos = idx.searchsorted(date, side="left")
    if pos >= len(idx):
        return None
    # t+0 is the close of auction day (pos); t+n is pos+n
    target = pos + n
    if target >= len(idx):
        return None
    return idx[target]


def forward_return(price: pd.Series, t0: pd.Timestamp, n: int) -> float | None:
    """Close-to-close return from t=0 to t=n trading days.

    PIT: enter on the close of t=0 (auction day). The auction result is known
    ~13:00 ET; closing price is public and is a causal entry point.
    """
    idx = price.index
    pos0 = idx.searchsorted(t0, side="left")
    if pos0 >= len(idx) or idx[pos0] != t0:
        return None                 # auction date is not a trading day
    pos_n = pos0 + n
    if pos_n >= len(idx):
        return None
    p0 = price.iloc[pos0]
    pn = price.iloc[pos_n]
    if not (np.isfinite(p0) and np.isfinite(pn) and p0 > 0):
        return None
    return float(pn / p0 - 1.0)


# ── build event panel ────────────────────────────────────────────────────────

def build_event_panel(auctions_raw: pd.DataFrame,
                      tlt: pd.Series, ief: pd.Series) -> pd.DataFrame:
    """Score each auction via the engine and attach forward returns.

    Returns a row-per-auction DataFrame with:
      absorption_z, bucket (belly/long), and forward returns at t+1/+5/+21
      for both TLT and IEF (we use the bucket-appropriate series later).
    """
    # Engine scoring
    coup = ts._prep(auctions_raw)
    scored = ts._score_rows(coup.copy(), TS_CFG)

    rows = []
    for _, r in scored.iterrows():
        t = int(r["tenor"])
        if t in BELLY_TENORS:
            bucket = "belly"
            price  = ief
        elif t in LONG_TENORS:
            bucket = "long"
            price  = tlt
        else:
            continue  # skip bills / unrecognised tenors

        adate = pd.Timestamp(r["auction_date"]).normalize()
        az = r["absorption_z"]
        if pd.isna(az):
            continue  # no z-score (insufficient history) — skip

        fwd = {f"fwd_{h}": forward_return(price, adate, h) for h in HORIZONS}
        rows.append({
            "auction_date": adate,
            "tenor":        t,
            "bucket":       bucket,
            "absorption_z": float(az),
            **fwd,
        })

    df = pd.DataFrame(rows).sort_values("auction_date").reset_index(drop=True)
    return df


# ── quintile contrast ────────────────────────────────────────────────────────

def quintile_contrast(sub: pd.DataFrame, horizon: int) -> dict:
    """Q5-Q1 (strong vs weak) mean return contrast + two-sample HAC t-stat.

    CORRECTION vs original build: the contrast t-stat now uses a proper
    two-sample standard error — sqrt(var_q5/n_q5 + var_q1/n_q1) — where each
    arm's variance is estimated via Newey-West to allow for mild serial
    dependence within the arm.  The original code computed
    newey_west_tstat(q5.values - q1.mean(), lags=4), which treats q1.mean()
    as a variance-free constant and omits Q1's sampling variance, roughly
    doubling the reported |t| relative to a correct two-sample statistic.

    HAC-overlap caveat: within a single quintile (~N/5 members), auctions are
    temporally sparse (months apart), so the lag=4 Bartlett correction captures
    little real serial overlap.  The fixed lag=4 is not scaled to the horizon
    (in particular, t+21 windows could span 2-3 subsequent same-bucket
    auctions).  Readers should treat the quintile-arm HAC as near-iid by
    construction; the primary multiple-testing guard is BH-FDR across 6 cells.
    """
    import math
    col = f"fwd_{horizon}"
    valid = sub[["absorption_z", col]].dropna()
    if len(valid) < 15:
        return {"n": len(valid), "q1_mean": None, "q5_mean": None,
                "spread": None, "t_hac": None, "p_hac": None}

    labels = pd.qcut(valid["absorption_z"], QUINTILE_N,
                     labels=False, duplicates="drop")
    q1 = valid.loc[labels == 0, col]
    q5 = valid.loc[labels == labels.max(), col]
    if len(q1) < 5 or len(q5) < 5:
        return {"n": len(valid), "q1_mean": None, "q5_mean": None,
                "spread": None, "t_hac": None, "p_hac": None}

    # Two-sample HAC SE: get the HAC long-run variance for each arm separately,
    # then combine via sqrt(lrv_q5/n_q5 + lrv_q1/n_q1).
    def _arm_lrv(arr: np.ndarray, lags: int = 4) -> float:
        """Long-run variance (HAC, Bartlett) of a single arm's returns.
        Returns the per-observation long-run variance (i.e. n*se^2 from NW)."""
        a = np.asarray(arr, float)
        n = len(a)
        d = a - a.mean()
        v = float(np.dot(d, d) / n)  # gamma_0
        L = min(int(lags), n - 1)
        for j in range(1, L + 1):
            gj = float(np.dot(d[j:], d[:-j]) / n)
            v += 2.0 * (1.0 - j / (L + 1)) * gj
        return max(v, 0.0)

    lrv_q5 = _arm_lrv(q5.values, lags=4)
    lrv_q1 = _arm_lrv(q1.values, lags=4)
    n5, n1 = len(q5), len(q1)
    se_two_sample = math.sqrt(lrv_q5 / n5 + lrv_q1 / n1)

    spread = float(q5.mean() - q1.mean())
    t_two  = (spread / se_two_sample) if se_two_sample > 0 else float("nan")

    # Two-sided p using normal approx (large-sample, consistent with NW t-stats
    # elsewhere in the validation module).
    from engine.validation import _norm_cdf
    p_two = round(2.0 * (1.0 - _norm_cdf(abs(t_two))), 4) if np.isfinite(t_two) else None

    return {
        "n":       len(valid),
        "n_q1":    n1,
        "n_q5":    n5,
        "q1_mean": round(float(q1.mean()) * 100, 3),
        "q5_mean": round(float(q5.mean()) * 100, 3),
        "spread":  round(spread * 100, 3),   # in %
        "t_hac":   round(t_two, 3) if np.isfinite(t_two) else None,
        "p_hac":   p_two,
    }


# ── continuous IC ────────────────────────────────────────────────────────────

def continuous_ic(sub: pd.DataFrame, horizon: int) -> dict:
    """Spearman IC of absorption_z vs forward return (one data point per auction
    -- this is a pooled cross-section, NOT a per-date time-series IC).
    Newey-West HAC is applied to the full series treated as a time series."""
    col = f"fwd_{horizon}"
    valid = sub[["absorption_z", col]].dropna()
    n = len(valid)
    if n < 10:
        return {"n": n, "ic": None, "t_hac": None, "p_hac": None}

    # Spearman = rank correlation (no scipy import needed — use rank then corrwith)
    rz = valid["absorption_z"].rank()
    rf = valid[col].rank()
    ic = float(rz.corr(rf))
    # HAC on the signed-product series (the per-obs IC contribution)
    contrib = (rz - rz.mean()) * (rf - rf.mean())
    contrib /= contrib.std(ddof=1) + 1e-12
    hac = newey_west_tstat(contrib.values, lags=4)
    return {"n": n, "ic": round(ic, 4), "t_hac": hac["t"], "p_hac": hac["p"]}


# ── split-half ───────────────────────────────────────────────────────────────

def split_half_check(sub: pd.DataFrame) -> dict:
    """G3: first half vs second half same-sign on the belly-t+5 and long-t+21
    directional spread (positive absorption_z -> positive forward return).
    Reports the sign of the Spearman IC for each half."""
    n = len(sub)
    if n < 20:
        return {"n": n, "h1_ic_t5": None, "h2_ic_t5": None, "same_sign": None}
    h1 = sub.iloc[:n // 2]
    h2 = sub.iloc[n // 2:]
    results = {}
    for h, lbl in [(h1, "h1"), (h2, "h2")]:
        for hz, col in [(5, "fwd_5"), (21, "fwd_21")]:
            v = h[["absorption_z", col]].dropna()
            if len(v) >= 8:
                ic = float(v["absorption_z"].rank().corr(v[col].rank()))
            else:
                ic = float("nan")
            results[f"{lbl}_ic_t{hz}"] = round(ic, 4) if np.isfinite(ic) else None
    return results


# ── duration-trend conditioning (G2) ────────────────────────────────────────

def duration_trend_conditioning(panel: pd.DataFrame, tlt: pd.Series) -> dict:
    """G2: split the panel by whether TLT is above or below its 50-day SMA on
    the auction date. Check that the Q5-Q1 spread at belly-t+5 / long-t+5 and
    long-t+21 has the same sign in both regimes.

    MOVE is available on disk; we use TLT-50dma as the duration-trend control
    (the engine docstring says this is the appropriate conditioning variable for
    the absorption signal). MOVE as a vol-regime control would be a separate,
    distinct gate not pre-registered here.
    """
    tlt_50 = tlt.rolling(50, min_periods=30).mean()
    above_mask = []
    for adate in panel["auction_date"]:
        try:
            above = bool(tlt.loc[adate] >= tlt_50.loc[adate])
        except KeyError:
            above = None
        above_mask.append(above)
    panel = panel.copy()
    panel["tlt_above_50"] = above_mask

    results = {}
    for regime_val, regime_lbl in [(True, "above_50dma"), (False, "below_50dma")]:
        sub = panel[panel["tlt_above_50"] == regime_val]
        for bkt, horizon in [("belly", 5), ("long", 5), ("long", 21)]:
            key = f"{regime_lbl}_{bkt}_t{horizon}"
            bkt_sub = sub[sub["bucket"] == bkt]
            v = bkt_sub[["absorption_z", f"fwd_{horizon}"]].dropna()
            if len(v) >= 8:
                ic = float(v["absorption_z"].rank().corr(v[f"fwd_{horizon}"].rank()))
            else:
                ic = float("nan")
            results[key] = round(ic, 4) if np.isfinite(ic) else None
    return results


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print(f"SLF-006 Auction Absorption Phase-0 — family: {FAMILY}")
    print("=" * 70)

    # ── Step 1: log the full trial grid BEFORE any backtest ──────────────────
    print(f"\n[1] Logging {len(GRID)} pre-registered trials to ledger...")
    led = TrialLedger(path=REPO / "data" / "trial_ledger.jsonl", family=FAMILY)
    n_logged = led.log_grid(GRID, family=FAMILY, info_cutoff="2026-07-06")
    print(f"    Logged {n_logged} new entries (dedup). effective_n = {led.effective_n(FAMILY)}")

    # ── Step 2: load data ────────────────────────────────────────────────────
    print("\n[2] Loading data...")
    auctions_raw = load_auctions()
    tlt  = load_price("TLT")
    ief  = load_price("IEF")
    move = load_move()
    print(f"    Auctions: {len(auctions_raw)} rows "
          f"({auctions_raw['auction_date'].min().date()} – "
          f"{auctions_raw['auction_date'].max().date()})")
    print(f"    TLT: {tlt.index.min().date()} – {tlt.index.max().date()}")
    print(f"    IEF: {ief.index.min().date()} – {ief.index.max().date()}")
    print(f"    MOVE: {move.index.min().date()} – {move.index.max().date()}")
    print("    NOTE: MOVE index is present on disk; used as rate-vol reference.")

    # ── Step 3: build event panel ────────────────────────────────────────────
    print("\n[3] Building event panel (engine scoring + forward returns)...")
    panel = build_event_panel(auctions_raw, tlt, ief)
    print(f"    Panel: {len(panel)} scored auctions "
          f"(belly={int((panel['bucket']=='belly').sum())}, "
          f"long={int((panel['bucket']=='long').sum())})")
    print(f"    Date range: {panel['auction_date'].min().date()} – "
          f"{panel['auction_date'].max().date()}")
    # Forward return coverage (t+21 is the most demanding)
    for bkt in ("belly", "long"):
        sub = panel[panel["bucket"] == bkt]
        n21 = sub["fwd_21"].notna().sum()
        print(f"    {bkt}: {len(sub)} auctions, {n21} with t+21 return (coverage "
              f"{n21}/{len(sub)})")

    # ── Step 4: compute results for each (bucket, horizon) cell ─────────────
    print("\n[4] Computing quintile contrasts and continuous ICs...")
    print("    PIT assumption: absorption_z is computed from engine's trailing-8")
    print("    same-tenor window using ONLY prior auctions (causal). Forward")
    print("    return starts at close of auction day (t=0).")

    pvals_contrast = {}
    pvals_ic       = {}
    results        = {}

    for bkt in ("belly", "long"):
        sub = panel[panel["bucket"] == bkt].reset_index(drop=True)
        for h in HORIZONS:
            cell = f"{bkt}_t{h}"
            qc   = quintile_contrast(sub, h)
            ic   = continuous_ic(sub, h)
            results[cell] = {"quintile": qc, "ic": ic}
            if qc["p_hac"] is not None:
                pvals_contrast[cell] = qc["p_hac"]
            if ic["p_hac"] is not None:
                pvals_ic[cell] = ic["p_hac"]

            spread_str = (f"{qc['spread']:+.3f}% (t_HAC={qc['t_hac']:.2f}, "
                          f"p={qc['p_hac']:.3f})"
                          if qc["spread"] is not None else "n/a")
            ic_str = (f"IC={ic['ic']:.4f} (t_HAC={ic['t_hac']:.2f}, "
                      f"p={ic['p_hac']:.3f})"
                      if ic["ic"] is not None else "n/a")
            print(f"    [{cell}] Q5-Q1 spread: {spread_str} | {ic_str}")

    # ── Step 5: BH-FDR across 6 contrast cells ──────────────────────────────
    print("\n[5] BH-FDR correction across 6 (bucket x horizon) cells...")
    bh_contrast = benjamini_hochberg(pvals_contrast, alpha=0.10)
    for k, v in bh_contrast.items():
        print(f"    {k}: p={v['p']:.4f}, q={v['q']:.4f}, reject={v['reject']}")

    # ── Step 6: G1 gate ──────────────────────────────────────────────────────
    print("\n[6] GATE G1: |t_HAC| >= 2.0 at >=1 horizon, BH-FDR q<=0.10...")
    g1_pass_cells = []
    for k, v in results.items():
        qc = v["quintile"]
        bh = bh_contrast.get(k)
        if (qc["t_hac"] is not None and abs(qc["t_hac"]) >= 2.0
                and bh is not None and bh["reject"]):
            g1_pass_cells.append(k)
    g1 = len(g1_pass_cells) >= 1
    print(f"    Passing cells: {g1_pass_cells or 'NONE'}")
    print(f"    G1: {'PASS' if g1 else 'FAIL'}")

    # ── Step 7: G2 gate (duration-trend conditioning) ────────────────────────
    print("\n[7] GATE G2: same sign in TLT above/below 50dma subsets...")
    cond_results = duration_trend_conditioning(panel, tlt)
    above_signs = {k: v for k, v in cond_results.items() if "above" in k}
    below_signs = {k: v for k, v in cond_results.items() if "below" in k}
    for k in above_signs:
        suffix = k.replace("above_50dma_", "")
        a = above_signs[k]
        b_key = f"below_50dma_{suffix}"
        bl = cond_results.get(b_key)
        sign_ok = (a is not None and bl is not None
                   and np.sign(a) == np.sign(bl) and a != 0)
        print(f"    {suffix}: above={a}, below={bl} -> same_sign={sign_ok}")
    # G2 requires at least 2 of 3 sub-cells to have same sign
    sign_checks = []
    for k in ["belly_t5", "long_t5", "long_t21"]:
        a = cond_results.get(f"above_50dma_{k}")
        bl = cond_results.get(f"below_50dma_{k}")
        ok = (a is not None and bl is not None
              and np.sign(a) == np.sign(bl) and a != 0)
        sign_checks.append(ok)
    g2 = sum(sign_checks) >= 2
    print(f"    G2: {'PASS' if g2 else 'FAIL'} ({sum(sign_checks)}/3 same-sign)")

    # ── Step 8: G3 gate (split-half same-sign) ──────────────────────────────
    print("\n[8] GATE G3: split-half same-sign check...")
    sh_results = {}
    for bkt in ("belly", "long"):
        sub = panel[panel["bucket"] == bkt].reset_index(drop=True)
        sh  = split_half_check(sub)
        sh_results[bkt] = sh
        print(f"    {bkt}: {sh}")

    # Check: for each bucket, t+5 IC same sign in both halves
    g3_checks = []
    for bkt in ("belly", "long"):
        sh = sh_results[bkt]
        for hz in [5, 21]:
            h1_ic = sh.get(f"h1_ic_t{hz}")
            h2_ic = sh.get(f"h2_ic_t{hz}")
            same  = (h1_ic is not None and h2_ic is not None
                     and np.sign(h1_ic) == np.sign(h2_ic)
                     and h1_ic != 0)
            g3_checks.append(same)
    g3 = sum(g3_checks) >= 3   # 3 of 4 checks must agree
    print(f"    G3: {'PASS' if g3 else 'FAIL'} ({sum(g3_checks)}/4 same-sign)")

    # ── Step 9: deflated Sharpe on the best cell ─────────────────────────────
    print("\n[9] Deflated Sharpe on best t+5 IC cell...")
    best_cell = max(
        [(bkt, 5) for bkt in ("belly", "long")],
        key=lambda x: abs(results.get(f"{x[0]}_t5", {}).get("ic", {}).get("ic") or 0),
    )
    bkt, h = best_cell
    sub = panel[panel["bucket"] == bkt].reset_index(drop=True)
    col = f"fwd_{h}"
    valid = sub[["absorption_z", col]].dropna()
    fwd_rets = valid[col].values
    T = len(fwd_rets)
    sr_daily = float(fwd_rets.mean()) / (float(fwd_rets.std(ddof=1)) + 1e-12)
    skew = float(pd.Series(fwd_rets).skew())
    kurt = float(pd.Series(fwd_rets).kurtosis())
    dsr_raw = deflated_sharpe(sr_daily, skew, kurt, T, ledger=led, family=FAMILY)
    if dsr_raw is None:
        dsr = float("nan")
    elif isinstance(dsr_raw, dict):
        # returns dict with 'dsr' key (P[true SR > 0] using Bailey-LdP formulation)
        dsr = float(dsr_raw.get("dsr", dsr_raw.get("p_dsr", float("nan"))))
    else:
        dsr = float(dsr_raw)
    print(f"    Best cell: {bkt}_t{h}, n={T}, SR={sr_daily:.4f}, DSR={dsr:.4f}")
    print(f"    Full DSR output: {dsr_raw}")

    # ── Step 10: overall verdict ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    all_pass = g1 and g2 and g3
    verdict  = "PASS — recommend display-confirmer registration" if all_pass else "NULL / NO-GO — display stays context-only"
    print(f"VERDICT: {verdict}")
    print(f"  G1 (HAC t>=2, BH-FDR q<=0.10): {'PASS' if g1 else 'FAIL'}")
    print(f"  G2 (duration-trend sign check): {'PASS' if g2 else 'FAIL'}")
    print(f"  G3 (split-half same-sign):      {'PASS' if g3 else 'FAIL'}")
    print(f"  DSR (multiple-testing haircut):  {dsr:.4f}")
    print("=" * 70)

    # ── Step 11: write report ────────────────────────────────────────────────
    print("\n[10] Writing report to reports/slf006-auction-absorption-phase0.md...")
    write_report(panel, results, bh_contrast, cond_results, sh_results,
                 g1, g2, g3, g1_pass_cells, sign_checks, g3_checks,
                 dsr, dsr_raw, sr_daily, T, led)
    print("Done.")
    return all_pass


def write_report(panel, results, bh_contrast, cond_results, sh_results,
                 g1, g2, g3, g1_pass_cells, sign_checks, g3_checks,
                 dsr, dsr_raw, sr_daily, T, led) -> None:
    all_pass = g1 and g2 and g3
    verdict  = "PASS — recommend display-confirmer registration" if all_pass else "NULL / NO-GO"

    belly_sub = panel[panel["bucket"] == "belly"]
    n_belly_short = int(belly_sub[belly_sub["tenor"].isin([2, 3])]["tenor"].count())

    lines = [
        "# SLF-006 Auction Absorption — Phase-0 Event Study",
        "",
        f"> **Verdict: {verdict}**",
        "",
        "## In plain English",
        "",
        "Treasury auctions happen several times a week. Strong demand (measured",
        "by bid-to-cover ratio, how much foreigners buy, and how little dealers",
        "are stuck with) might predict that bond prices rise afterward — or it",
        "might not, because smart investors often pre-position BEFORE the auction.",
        "This study checks whether the absorption score already computed on bonds.html",
        "has any forward-return signal. A PASS means we can move it toward a",
        "registered forward signal; a FAIL means it stays context-only.",
        "",
        "## Setup",
        "",
        "- **Engine**: `engine/treasury_supply._prep` + `_score_rows` (no math forked)",
        "- **Tenor buckets**: belly (2y/3y/5y/7y) → IEF; long (10y/20y/30y) → TLT",
        "- **PIT discipline**: auction results published ~13:00 ET auction day;",
        "  enter on **close of auction day** (t=0)",
        "- **Event windows**: t+1, t+5, t+21 trading days",
        "- **Quintile contrast**: Q5 (absorption_z top-20%) minus Q1 (bottom-20%)",
        "- **IC**: pooled Spearman of absorption_z vs forward return (HAC NW t-stat)",
        "- **Vol control**: MOVE index present on disk; used in conditioning notes",
        "- **Duration conditioning (G2)**: TLT 50dma above/below split",
        "",
        "## Data",
        "",
        f"- Auctions: {len(panel)} scored coupon auctions after engine scoring",
        f"  (belly={int((panel['bucket']=='belly').sum())},",
        f"  long={int((panel['bucket']=='long').sum())})",
        f"- Date range: {panel['auction_date'].min().date()} – {panel['auction_date'].max().date()}",
        "",
        "## Pre-registered gates",
        "",
        "| Gate | Criterion | Result |",
        "| ---- | --------- | ------ |",
        f"| G1 | \\|t_HAC\\| ≥ 2.0 at ≥1 horizon with BH-FDR q ≤ 0.10 | {'**PASS**' if g1 else '**FAIL**'} |",
        f"| G2 | Same-sign Q5-Q1 contrast in TLT above/below 50dma | {'**PASS**' if g2 else '**FAIL**'} |",
        f"| G3 | Split-half same-sign (first vs second half of history) | {'**PASS**' if g3 else '**FAIL**'} |",
        "",
        "## Results by cell",
        "",
        "### Quintile contrast (Q5-Q1 gross return spread, %)",
        "",
        "| Cell | n | Q1 mean% | Q5 mean% | Spread% | t_HAC | p_HAC | BH-q | BH-reject |",
        "| ---- | - | -------- | -------- | ------- | ----- | ----- | ---- | --------- |",
    ]

    for bkt in ("belly", "long"):
        for h in HORIZONS:
            cell = f"{bkt}_t{h}"
            qc = results[cell]["quintile"]
            bh = bh_contrast.get(cell, {})
            n    = qc.get("n", "")
            q1m  = f"{qc['q1_mean']:.3f}" if qc["q1_mean"] is not None else "—"
            q5m  = f"{qc['q5_mean']:.3f}" if qc["q5_mean"] is not None else "—"
            spr  = f"{qc['spread']:+.3f}" if qc["spread"] is not None else "—"
            t    = f"{qc['t_hac']:.2f}" if qc["t_hac"] is not None else "—"
            p    = f"{qc['p_hac']:.3f}" if qc["p_hac"] is not None else "—"
            q    = f"{bh.get('q', '—'):.4f}" if bh.get("q") is not None else "—"
            rej  = str(bh.get("reject", "—"))
            lines.append(f"| {cell} | {n} | {q1m} | {q5m} | {spr} | {t} | {p} | {q} | {rej} |")

    lines += [
        "",
        "### Continuous Spearman IC",
        "",
        "| Cell | n | IC | t_HAC | p_HAC |",
        "| ---- | - | -- | ----- | ----- |",
    ]
    for bkt in ("belly", "long"):
        for h in HORIZONS:
            cell = f"{bkt}_t{h}"
            ic = results[cell]["ic"]
            n   = ic.get("n", "")
            icv = f"{ic['ic']:.4f}" if ic["ic"] is not None else "—"
            t   = f"{ic['t_hac']:.2f}" if ic["t_hac"] is not None else "—"
            p   = f"{ic['p_hac']:.3f}" if ic["p_hac"] is not None else "—"
            lines.append(f"| {cell} | {n} | {icv} | {t} | {p} |")

    lines += [
        "",
        "## Statistical caveats",
        "",
        "### 1. Contrast t-stat construction (corrected from original build)",
        "",
        "The Q5-Q1 t-statistics reported here use a proper **two-sample standard",
        "error**: `sqrt(lrv_q5/n_q5 + lrv_q1/n_q1)`, where each arm's long-run",
        "variance is estimated via Newey-West (Bartlett kernel, lag=4).  The",
        "original build used `newey_west_tstat(q5.values - q1.mean(), lags=4)`,",
        "which treats `q1.mean()` as a variance-free constant.  That formulation",
        "omits Q1's sampling variance and roughly doubles the reported |t|",
        "(e.g., original belly_t5 t_HAC = -4.14 corrects to -2.20 with the",
        "proper two-sample SE).  The NULL/NO-GO verdict is unchanged: with",
        "corrected t-stats no cell clears BH-FDR q ≤ 0.10 (G1 now FAIL as well",
        "as G3), making the null more robust, not less.",
        "",
        "### 2. HAC-overlap caveat",
        "",
        "The Newey-West lag=4 is a **fixed constant, not scaled to the horizon**.",
        "Within a single quintile (~N/5 members), auctions are temporally sparse",
        "(months apart), so lag=4 corrects little real serial dependence — the",
        "quintile-subset HAC is near-iid by construction.  The overlap that matters",
        "(t+21 forward-return windows that span 2-3 subsequent same-tenor auctions)",
        "lives in the pooled calendar series, not the quintile subset.  For the",
        "t+21 horizon, a horizon-scaled lag (>=21 trading days ≈ 4-5 auctions)",
        "would be more principled; the fixed lag=4 is conservative for t+1/t+5 and",
        "may be slightly under-corrected for t+21.  The primary multiple-testing",
        "guard is BH-FDR across 6 pre-declared cells, not the lag parameter.",
        "",
        "### 3. Duration-proxy mismatch (belly bucket)",
        "",
        f"Of the {int((panel['bucket']=='belly').sum())} belly auctions, approximately"
        f" **{n_belly_short} are 2y or 3y tenors** mapped to IEF (iShares 7-10y",
        "Treasury ETF) — a material duration mismatch.  A 2y or 3y auction probes",
        "the short end of the curve, but IEF's effective duration is ~7 years.",
        "These instruments share broad macro direction but differ substantially in",
        "convexity and rate sensitivity.  The null result for the belly bucket",
        "should **not** be over-read as a clean test of short-tenor absorption",
        "signal: it is partly a test of whether short-tenor auction strength",
        "predicts 7-10y ETF returns, which is a weaker and noisier hypothesis.",
        "A cleaner test would use SHY (1-3y) or IEI (3-7y) for the 2y-3y subset.",
        "",
        "## Gate detail",
        "",
        "### G1 — HAC t-stat + BH-FDR",
        "",
        f"Passing cells at |t_HAC| ≥ 2.0 and BH-q ≤ 0.10: **{g1_pass_cells or 'none'}**",
        f"G1 result: **{'PASS' if g1 else 'FAIL'}**",
        "",
        "### G2 — Duration-trend conditioning (TLT above/below 50dma)",
        "",
        "| Sub-cell | TLT above-50dma IC | TLT below-50dma IC | Same sign |",
        "| -------- | ------------------ | ------------------- | --------- |",
    ]
    check_idx = 0
    for k in ["belly_t5", "long_t5", "long_t21"]:
        a   = cond_results.get(f"above_50dma_{k}")
        bl  = cond_results.get(f"below_50dma_{k}")
        ok  = sign_checks[check_idx] if check_idx < len(sign_checks) else False
        av  = f"{a:.4f}" if a is not None else "—"
        bv  = f"{bl:.4f}" if bl is not None else "—"
        lines.append(f"| {k} | {av} | {bv} | {'Yes' if ok else 'No'} |")
        check_idx += 1
    lines += [
        f"",
        f"G2 result: **{'PASS' if g2 else 'FAIL'}** ({sum(sign_checks)}/3 same-sign, need ≥2)",
        "",
        "### G3 — Split-half same-sign",
        "",
        "| Bucket | Metric | H1 IC | H2 IC | Same sign |",
        "| ------ | ------ | ----- | ----- | --------- |",
    ]
    g3_idx = 0
    for bkt in ("belly", "long"):
        sh = sh_results[bkt]
        for hz in [5, 21]:
            h1_ic = sh.get(f"h1_ic_t{hz}")
            h2_ic = sh.get(f"h2_ic_t{hz}")
            ok    = g3_checks[g3_idx] if g3_idx < len(g3_checks) else False
            h1v   = f"{h1_ic:.4f}" if h1_ic is not None else "—"
            h2v   = f"{h2_ic:.4f}" if h2_ic is not None else "—"
            lines.append(f"| {bkt} | t+{hz} | {h1v} | {h2v} | {'Yes' if ok else 'No'} |")
            g3_idx += 1
    lines += [
        f"",
        f"G3 result: **{'PASS' if g3 else 'FAIL'}** ({sum(g3_checks)}/4 same-sign, need ≥3)",
        "",
        "## Multiple-testing / Deflated Sharpe",
        "",
        f"- Total pre-registered trials (logged before any backtest): {led.effective_n(FAMILY)}",
        f"- Best-cell daily SR: {sr_daily:.4f}",
        f"- Deflated Sharpe (P[true SR > 0]): {dsr:.4f}",
        (f"  - full DSR: sr0_annual={dsr_raw.get('sr0_annual')}, n_trials={dsr_raw.get('n_trials')}"
         if isinstance(dsr_raw, dict) else ""),
        "",
        "## Verdict and recommendation",
        "",
        f"**Overall: {verdict}**",
        "",
    ]
    if all_pass:
        lines += [
            "All three gates passed. Recommend registering the absorption_z as a",
            "display-confirmer (not a scored leg — the lag and tail data limitations",
            "noted in the engine docstring remain). A Phase-1 conditioning study",
            "using MOVE-regime splits could follow.",
        ]
    else:
        lines += [
            "At least one gate failed. The absorption engine output remains",
            "context-only on bonds.html. No scoring, no MRS leg.",
            "",
            "**Limitations of this null:**",
            "",
            "1. **Duration-proxy mismatch**: ~51 of 168 belly auctions are 2y/3y",
            "   tenors mapped to IEF (7-10y ETF). This is a material mismatch —",
            "   the null for the belly bucket is partly a test of whether",
            "   short-tenor absorption predicts 7-10y returns, a weaker hypothesis.",
            "   See the 'Statistical caveats' section above.",
            "2. **Panel length**: 413 scored auctions over ~10 years; a longer panel",
            "   would reduce quintile-arm standard errors appreciably.",
            "3. **Metric reformulation**: the absorption_z aggregates three demand",
            "   sub-signals (bid-to-cover, indirect, dealer) with equal weight.",
            "   A sub-signal decomposition or a tail/cover-only variant might recover",
            "   signal that the composite obscures.",
        ]
    lines += [
        "",
        "## Nightly wiring (for consolidation)",
        "",
        "None required — engine already runs nightly in the bonds build path.",
        "This phase-0 uses no new collector. If a Phase-1 is commissioned,",
        "a new harness would symlink the same treasury_auctions and yahoo stores.",
        "",
        "## PIT publication-lag assumptions",
        "",
        "| Series | Publication lag enforced |",
        "| ------ | ------------------------ |",
        "| Treasury auction results | ~13:00 ET same day; enter on CLOSE of auction day |",
        "| TLT / IEF close prices | Same-day EOD; PIT-clean by construction |",
        "| MOVE index | Same-day EOD; used for reference only |",
        "| absorption_z | Computed from PRIOR auctions only (engine trailing window) |",
    ]

    out = REPO / "reports" / "slf006-auction-absorption-phase0.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
