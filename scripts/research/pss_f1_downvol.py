#!/usr/bin/env python3
"""PSS-F1 — Down-volume envelope decay (forced-supply exhaustion on new lows).

PRE-REGISTRATION — this header is the pinned ruler AND the pinned construction,
committed BEFORE any timing outcome (MAE/W5/proximity) was computed. The prereg
commit ("prereg: PSS-F1 …") precedes the results commit in git history (audited).
Charters: research/PSS_WSIG_SHORTLIST_BY_FABLE.md §F1 + §"Execution rails";
research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W-SIG / §0 / §2.
Trial-ledger family: pss_f1_downvol (registered in data/trial_ledger.jsonl in
the same pre-run commit as this file).

Copy law R-W1T-3 governs all text here: this is a reset-CONFIRMER / exhaustion /
terminality construction — it never "calls bottoms". "validated" is CI-banned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE ONE MECHANISM HYPOTHESIS (pre-registered).
In names that bottom via orderly seller-exhaustion, durable lows are preceded by
NEW LOWS printed on a CONTRACTING down-day dollar-volume envelope — the forced-
selling cohort (margin calls, tax-loss, redemptions, index-deletion flow) is a
FINITE inventory that empties, so supply dries on new lows BEFORE demand arrives.
Fire = a fresh new-low bar whose down-day dollar volume sits BELOW a decaying
(negative-slope) envelope fitted across the decline's successive lower-low bars.

WRONG-RULER CHECK (§W-SIG execution rail, performed BEFORE statistics were
chosen). The object under test is an ENTRY-TIMING claim: "does a contracting-
envelope new-low bar sit shallower-to-the-trough / closer-to-the-low than an
ordinary bar?". It is NOT a hold-return claim. Grading it on fwd63 hold returns
would be the DNR §3 wrong-ruler law (#1458, Oracle reversion reframe — the same
error PTT-W1-T corrected). Therefore the metrics below are entry-quality metrics
(MAE-to-trough, proximity-to-low, td-to-trough), never drift metrics. fwd-return
is not read.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL PINNED CONSTRUCTION (closes-and-volume only; PIT throughout).

1. NEW-LOW BAR.  Bar i is a new-low bar iff
     close[i] == min(close[i-L+1 .. i])   (fresh L-day-low close)
     AND close[i] < close[i-1]            (a down day — the leg is being pressed)
     AND dvol[i] finite.
   dvol[i] = close[i] * volume[i]  (dollar volume; close is yahoo total-return
   adjusted — a level bias that nets out of the log-slope envelope). L pinned = 60
   trading days (the charter's 60d-low reference; grid also runs L=40).

2. PER-NAME ENVELOPE-FIT WINDOW W (from the down-volume persistence half-life).
   dv_halflife = the ACF-DECAY-FIT half-life of the FIT-era down-day log dollar
   volume: over lags k=1..40, take |ACF(k)|; fit log|ACF(k)| ~ a − b·k by OLS on
   the lags where |ACF(k)| > 0.02; dv_halflife = ln2 / b (b>0 required), capped
   250 td. This is the decay constant of the autocorrelation of down-day dollar
   volume — literally the charter's "how many bars a selling cohort takes to
   empty".  The envelope window (in trailing NEW-LOW bars) =
     W = clip( round(dv_halflife / 2), 6, 30 )
   (down-day new-low bars fall ~every 2 td in a decline, so half-life/2 converts
   td to new-low-bar count; clipped to a fittable band). Unmeasurable dv_halflife
   ⇒ name EXCLUDED with a printed reason (never defaulted — a name with no
   measurable down-volume persistence has no envelope to test).

   MEASUREMENT AMENDMENT LOG (PRE-OUTCOME — measurement-distribution probes only;
   NO IS/OOS uplift was computed or read before the final pin, mirroring PTT-W1
   A1/A2):
     M1 (charter sketch, DEGENERATE): "decay constant of the LAG-1 autocorrelation
        of down-day dollar volume". Lag-1 ACF of the down-day dvol series is ~white
        (successive down-day volumes nearly uncorrelated): 207-name probe → half-
        life 0.9–3.9 td (median 1.5), which cannot set an envelope window. Re-pinned
        to the MULTI-LAG ACF-decay fit above.
     M2 (spacing alternative, DEGENERATE): "median td between successive new-low
        bars" as the window unit — degenerate (207-name probe → all names 1.0–2.5
        td, because consecutive decline bars are all fresh 60d-lows). Discarded.
     FINAL PIN — multi-lag ACF-decay half-life: 205/207 measurable, non-degenerate
        (deciles 17.4 / 30.3 / 54.7 / 106.3 / 169.1 td; XOM 11, MSFT 74). W spans
        6–30 new-low bars across the probe (median 27). Fire-count probe (127
        names): median 8 FIT / 11 OOS fires per name; 0 unmeasurable. No outcome
        (MAE/W5/prox) was computed in any probe.

3. ENVELOPE FIT + FIRE.  At each new-low bar j (indexed over the name's ordered
   new-low bars, j >= W), fit OLS of log-dvol on ordinal position over the trailing
   W new-low bars [j-W .. j-1]; slope b1, intercept b0, residual sigma sig. The bar
   FIRES iff
     b1 < 0                                   (contracting / decaying envelope)
     AND  log_dvol[j] < (b0 + b1*W) - k*sig   (this new low prints BELOW the decayed
                                               envelope's extrapolated value).
   k pinned = 0.0 (grid also runs k=0.5, a stricter below-envelope margin).
   The fit uses ONLY bars strictly prior to j (PIT — no lookahead).

4. GRID (multiplicity budget, disclosed; a HANDFUL of cells, NOT a search).
     L ∈ {40, 60}  ×  k ∈ {0.0, 0.5}  = 4 cells.
   ALL FOUR are graded and reported side by side. There is NO per-name best-of-grid
   selection anywhere — that is the standing two-ruler kill (DO_NOT_REBUILD §2,
   PTT-W1a). W is DERIVED per name from measurement (never outcome-selected). The
   PRIMARY pre-registered cell = (L=60, k=0.0); the other three are robustness.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULER (§7 house standard; machinery COPIED from ptt_w1_timing_regrade.py —
metric_arrays / null_stats — and ptt_w1_persistence_of_fit.py — bars_for /
tool_dates — NOT reinvented).
  Per signal at daily index i (closes only):
    mae63 = min(close[i+1..i+63]) / close[i] − 1        (%; <=0; PRIMARY-lens raw)
    prox  = close[i] / min(close[i−31..i+31]) − 1        (%; >=0; §7 ±31td window)
    w5    = prox <= 5%   (entered within 5% of the ±31td low)
    tdt   = argmin offset of close in [i−31,i+31] (td; negative = trough BEFORE fire)
    mfe21 = max(close[i+1..i+21]) / close[i] − 1  ·  rc21 = close[i+21]/close[i] − 1
  Valid-day universe per half: i >= 31 AND i + 63 < len (both windows resolvable).
  RANDOM-DAY NULLS: per-name, per-half, per-metric all-days medians/rates over the
  half's valid days (the 69%-class base-rate trap guard).
  THE TWO INFERENTIAL METRICS (exactly two; everything else is descriptive):
    U_MAE = median signal mae63 − all-days median mae63   (pp; +=shallower=better)
    U_W5  = signal within-5%-of-low rate − all-days rate    (pp)
  INFERENCE: month-cluster bootstrap (cluster = signal calendar month; DT-R14 —
  ticker-only clustering is FORBIDDEN), NB = 1000, RNG seed 20260728 (pinned).
  ERA SPLIT (DT-R16, mirroring W1): FIT <= 2020-06-30 / TEST >= 2020-07-01, plus
  the 2021+ sub-window (>= 2021-01-01). A full-sample-only effect is disqualified.
  All grading is on TEST; FIT is used ONLY to measure dv_halflife (window derivation).

F1-SPECIFIC PRE-STATED KILL (the falsifier — printed regardless of outcome).
  Beyond the random-DAY nulls: compare signal new-low bars against RANDOM NEW-LOW
  bars within the same names' declines (per-name conditional base rate — the null
  is "an ordinary new-low bar", not "an ordinary day"), month-cluster-bootstrapped.
  If contracting-envelope new-low bars do NOT beat random new-low bars on U_MAE and
  U_W5, the exhaustion signature is illusory. This comparison is reported in every
  case — nulls are printed, never hidden.

C32 TERMINALITY GATE (pre-registered CONDITIONER — a pre-stated column pair, NOT
post-hoc). Every result table is graded WITH and WITHOUT the gate. Gate is TRUE at
bar i iff the decline is DECELERATING into a fresh low:
    close[i] <= 60d-low(close)[i]                          (at/into a fresh 60d low)
    AND roc20[i] > min(roc20[i-19 .. i])                   (20d rate-of-change has
                                                            stopped making new lows)
    AND slope(10d-min over last M bars)[i] flattening       (rolling-low slope higher
       i.e. > slope over the prior M bars                    than the prior window's)
  roc20[i] = close[i]/close[i-20] − 1. M pinned = 20 td. The gate only ever narrows.

2022-CLASS CONTAINMENT DIAGNOSTIC (pre-stated). On liquid mega-cap focus names
AAPL MSFT GOOGL META HD JPM XOM (+ NVDA TSLA as the expected-FAIL class): fire
counts in H1-2022 (2022-01-01..2022-06-30) vs a ±21td window around the 2022-10-13
low. The charter predicts the detector is STRUCTURALLY SILENT in H1-2022 (down-
volume was ELEVATING into each leg, so the envelope was not contracting). Reported
for the (L=60,k=0.0) primary cell. NOTE (pre-outcome): META, NVDA, PG are NOT in
the W1 panel (they fell to W1 eligibility ≥3+≥3 on all 6 tools); the containment
diagnostic runs them from raw OHLCV as named exhibits, flagged as off-panel.

EARLINESS vs INCUMBENT. Incumbent = Stoch-RSI<20 cross at the name's structure-
derived rung (rung_derived from data/research/ptt_w1_panel.parquet), via the FROZEN
machinery tool_dates(bars_for(px, rung_derived), "S"). Grade median td_to_trough of
F1 fires vs the incumbent's on the SAME names. The charter's earliness claim: F1 is
pre-trough (tdt > 0, fires before the low) while the incumbent is a late confirmer.

UNIVERSE / ELIGIBILITY. Universe = W1 panel names (data/research/ptt_w1_panel.parquet)
that have volume data (all 1,300 do). A name is F1-ELIGIBLE iff dv_halflife is
measurable AND it has >= 3 FIT and >= 3 TEST F1 fires (primary cell) with resolvable
mae63/prox. Coverage census (eligible / excluded counts AND why: no dv_halflife /
too few new-lows / too few fires) is PRINTED — never a bare count (vacuous-green
law). Defensives (KO PG class) are expected to be structurally ineligible (declines
too shallow to generate a measurable contracting envelope) — an ACCEPTED loss,
reported as such.

REGISTRY COMPLIANCE. DT-R14 month-cluster · DT-R16 era split · DNR §2 two-ruler
kill respected (zero per-name best-of-grid; W derived, not selected) · DNR §3 wrong-
ruler law is the MOTIVE for the entry ruler · R-W1T-3 copy law (exhaustion language;
no "bottom" verb; "validated" avoided) · display-tier only — NOTHING here promotes
to authority (the gauntlet is a PROMOTION gate, not this build gate; a null never
blocks accrual). The commissioning session rules the verdict; this report states
what was found, no verdict language.

Outputs: reports/pss_f1_downvol.md + data/research/pss_f1_downvol_panel.parquet.
Run: python3 scripts/research/pss_f1_downvol.py   (off the render path; ~10-20 min)
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from numpy.lib.stride_tricks import sliding_window_view  # noqa: E402

# COPIED machinery (identical code paths) — the ruler is not reinvented.
from scripts.research.ptt_w1_persistence_of_fit import (  # noqa: E402
    OOS_START, SPLIT, SUB2021, bars_for, tool_dates,
)

RNG = np.random.default_rng(20260728)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
PANEL_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
OUT_MD = ROOT / "reports" / "pss_f1_downvol.md"
OUT_PQ = ROOT / "data" / "research" / "pss_f1_downvol_panel.parquet"

H = 63           # MAE window
PROX = 31        # ±31td proximity window (§7)
TEXIT = 21
NB = 1000
W5 = 5.0
L_PRIMARY = 60
K_PRIMARY = 0.0
GRID = [(L, k) for L in (40, 60) for k in (0.0, 0.5)]  # multiplicity budget: 4 cells
W_FLOOR, W_CAP = 6, 30
ACF_MAXLAG = 40
ACF_FLOOR = 0.02
C32_M = 20       # rolling-low slope lookback
MIN_FIT = 3
MIN_TEST = 3
MEGA = ["AAPL", "MSFT", "GOOGL", "META", "HD", "JPM", "XOM"]
EXPECT_FAIL = ["NVDA", "TSLA"]
LOW22 = pd.Timestamp("2022-10-13")
H1_22 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-06-30"))


# ── timing-metric arrays (COPIED verbatim from ptt_w1_timing_regrade.py) ────

def metric_arrays(c: np.ndarray) -> dict[str, np.ndarray]:
    """Per-index timing metrics; NaN outside the valid-day universe
    (i >= PROX and i + H < len)."""
    n = len(c)
    out = {k: np.full(n, np.nan) for k in ("mae63", "prox", "tdt", "mfe21", "rc21")}
    if n < PROX + H + 2:
        return out
    fw = sliding_window_view(c[1:], H)
    fmin63 = fw.min(axis=1)
    i_hi = n - H - 1
    out["mae63"][:i_hi + 1] = (fmin63[:i_hi + 1] / c[:i_hi + 1] - 1) * 100
    f21 = sliding_window_view(c[1:], TEXIT)
    j_hi = n - TEXIT - 1
    out["mfe21"][:j_hi + 1] = (f21.max(axis=1)[:j_hi + 1] / c[:j_hi + 1] - 1) * 100
    out["rc21"][:j_hi + 1] = (c[TEXIT:TEXIT + j_hi + 1] / c[:j_hi + 1] - 1) * 100
    cw = sliding_window_view(c, 2 * PROX + 1)
    ctr = np.arange(PROX, n - PROX)
    out["prox"][ctr] = (c[ctr] / cw.min(axis=1) - 1) * 100
    out["tdt"][ctr] = cw.argmin(axis=1).astype(float) - PROX
    invalid = np.zeros(n, dtype=bool)
    invalid[:PROX] = True
    invalid[n - H:] = True
    for k in out:
        out[k][invalid] = np.nan
    return out


def null_stats(m: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, float]:
    v = mask & np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    if v.sum() < 60:
        return {}
    prox = m["prox"][v]
    tdt = m["tdt"][v]
    return {
        "mae_med": float(np.median(m["mae63"][v])),
        "w5_rate": float((prox <= W5).mean() * 100),
        "prox_med": float(np.median(prox)),
        "called_rate": float(((-2 <= tdt) & (tdt <= 5)).mean() * 100),
        "n_valid": int(v.sum()),
    }


# ── F1 construction ─────────────────────────────────────────────────────────

def dv_halflife(close: pd.Series, volume: pd.Series) -> float:
    """ACF-decay-fit half-life of FIT-era down-day log dollar volume (pin M-final)."""
    ldv = np.log((close * volume).replace(0, np.nan))
    down = close < close.shift(1)
    s = ldv[down].dropna()
    s = s[s.index <= SPLIT]
    if len(s) < 120:
        return float("nan")
    ac = np.array([abs(float(s.autocorr(k))) for k in range(1, ACF_MAXLAG + 1)])
    lags = np.arange(1, ACF_MAXLAG + 1)
    mask = ac > ACF_FLOOR
    if mask.sum() < 5:
        return float("nan")
    b = float(np.polyfit(lags[mask], np.log(ac[mask]), 1)[0])
    if b >= 0:
        return float("nan")
    return float(min(np.log(2) / (-b), 250.0))


def newlow_mask(close: pd.Series, L: int) -> np.ndarray:
    """Fresh L-day-low close AND a down day (dvol finiteness applied by caller)."""
    m = close.rolling(L, min_periods=L).min()
    return ((close == m) & (close < close.shift(1))).to_numpy()


def f1_fires(close: pd.Series, volume: pd.Series, L: int, k: float, W: int
             ) -> np.ndarray:
    """Boolean fire array over daily index. Contracting-envelope new-low bar
    printing below the decayed envelope. PIT: fit uses only prior new-low bars."""
    ldv = np.log((close * volume).replace(0, np.nan)).to_numpy()
    nl = newlow_mask(close, L) & np.isfinite(ldv)
    nlidx = np.where(nl)[0]
    fire = np.zeros(len(close), dtype=bool)
    if len(nlidx) < W + 2:
        return fire
    x = np.arange(W, dtype=float)
    for j in range(W, len(nlidx)):
        win = nlidx[j - W:j]              # W trailing PRIOR new-low bars (PIT)
        y = ldv[win]
        b1, b0 = np.polyfit(x, y, 1)
        if b1 >= 0:
            continue                     # require contracting envelope
        resid = y - (b0 + b1 * x)
        sig = float(resid.std())
        i = nlidx[j]
        if ldv[i] < (b0 + b1 * W) - k * sig:
            fire[i] = True
    return fire


def c32_gate(close: pd.Series, L: int = L_PRIMARY, M: int = C32_M) -> np.ndarray:
    """Decline decelerating INTO a fresh low (pre-registered conditioner)."""
    c = close.to_numpy(dtype=float)
    n = len(c)
    g = np.zeros(n, dtype=bool)
    if n < L + 20 + M + 1:
        return g
    low60 = close.rolling(L, min_periods=L).min().to_numpy()
    roc20 = np.full(n, np.nan)
    roc20[20:] = c[20:] / c[:-20] - 1
    # rolling 10d-min and its M-bar slope (regression slope of the last M lows)
    low10 = close.rolling(10, min_periods=10).min().to_numpy()
    xM = np.arange(M, dtype=float)
    xM -= xM.mean()
    denom = float((xM ** 2).sum())
    for i in range(L + 20 + M, n):
        if not (c[i] <= low60[i] + 1e-12):
            continue
        w = roc20[i - 19:i + 1]
        if not np.isfinite(w).all() or not (roc20[i] > np.min(w) + 1e-12):
            continue
        cur = low10[i - M + 1:i + 1]
        prev = low10[i - 2 * M + 1:i - M + 1]
        if not (np.isfinite(cur).all() and np.isfinite(prev).all()):
            continue
        s_cur = float((xM * (cur - cur.mean())).sum() / denom)
        s_prev = float((xM * (prev - prev.mean())).sum() / denom)
        if s_cur > s_prev:               # rolling-low slope flattening (less negative)
            g[i] = True
    return g


def half_masks(idx: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    return {
        "is": np.asarray(idx <= SPLIT),
        "oos": np.asarray(idx >= OOS_START),
        "oos21": np.asarray(idx >= SUB2021),
    }


# ── per-name computation ────────────────────────────────────────────────────

def load_px(sym: str) -> pd.DataFrame:
    df = pd.read_parquet(OHLCV / f"{sym}.parquet")[["close", "volume"]].dropna()
    return df


def compute_name(sym: str, rung: str) -> dict:
    """Returns a record with per-cell fire metrics + the F1/incumbent/random-newlow
    signal rows. NO best-of-grid selection: every cell graded independently."""
    df = load_px(sym)
    close, volume = df["close"], df["volume"]
    c = close.to_numpy(dtype=float)
    idx = close.index
    m = metric_arrays(c)
    masks = half_masks(idx)
    nulls = {h: null_stats(m, masks[h]) for h in ("is", "oos", "oos21")}
    rec: dict = {"sym": sym, "rung": rung}
    hl = dv_halflife(close, volume)
    rec["dv_halflife"] = hl
    if not np.isfinite(hl):
        rec["excl"] = "no_dv_halflife"
        return rec
    W = int(np.clip(round(hl / 2), W_FLOOR, W_CAP))
    rec["W"] = W
    if not nulls["is"] or not nulls["oos"]:
        rec["excl"] = "null_universe_small"
        return rec
    for h in ("is", "oos", "oos21"):
        for kk, vv in (nulls[h] or {}).items():
            rec[f"null_{h}_{kk}"] = vv

    c32 = c32_gate(close)
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    sig_rows: list[dict] = []
    fires_primary = None
    for (L, k) in GRID:
        fire = f1_fires(close, volume, L, k, W)
        valid = fire & fin
        for h, mk in (("is", masks["is"]), ("oos", masks["oos"]), ("oos21", masks["oos21"])):
            sub = valid & mk
            n = int(sub.sum())
            rec[f"n_{h}_L{L}_k{k}"] = n
            if n == 0 or not nulls[h]:
                rec[f"umae_{h}_L{L}_k{k}"] = np.nan
                rec[f"uw5_{h}_L{L}_k{k}"] = np.nan
                continue
            mae = m["mae63"][sub]
            prox = m["prox"][sub]
            rec[f"umae_{h}_L{L}_k{k}"] = float(np.median(mae) - nulls[h]["mae_med"])
            rec[f"uw5_{h}_L{L}_k{k}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
        # gated variant (C32) — pre-stated column pair
        for gate_on in (False, True):
            gv = valid & (c32 if gate_on else np.ones(len(c), bool))
            tag = "g1" if gate_on else "g0"
            for h, mk in (("oos", masks["oos"]), ("oos21", masks["oos21"])):
                sub = gv & mk
                n = int(sub.sum())
                rec[f"n_{h}_L{L}_k{k}_{tag}"] = n
                if n == 0 or not nulls[h]:
                    rec[f"umae_{h}_L{L}_k{k}_{tag}"] = np.nan
                    rec[f"uw5_{h}_L{L}_k{k}_{tag}"] = np.nan
                    continue
                mae = m["mae63"][sub]; prox = m["prox"][sub]
                rec[f"umae_{h}_L{L}_k{k}_{tag}"] = float(np.median(mae) - nulls[h]["mae_med"])
                rec[f"uw5_{h}_L{L}_k{k}_{tag}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
        if (L, k) == (L_PRIMARY, K_PRIMARY):
            fires_primary = fire
            # signal rows for the month-cluster bootstrap (primary cell, TEST, g0+g1)
            for i in np.where(valid & masks["oos"])[0]:
                sig_rows.append({
                    "sym": sym, "kind": "f1", "date": idx[i], "month": str(idx[i])[:7],
                    "mae_ex": m["mae63"][i] - nulls["oos"]["mae_med"],
                    "w5_ex": (100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"],
                    "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "tdt": m["tdt"][i], "gate": bool(c32[i]), "sub21": bool(idx[i] >= SUB2021),
                })

    # F1 falsifier null: ordinary new-low bars in the same declines (conditional base
    # rate). The placebo pool is the treatment-DISJOINT complement — every valid
    # new-low bar that did NOT fire F1 (same eligibility fin, same ±31td prox window,
    # same closes-only plane, same per-name baselines). Using the full complement
    # (not an equal-count subsample) keeps the null's per-name conditional rate exact.
    # E2 (errata): the pre-decontamination pool was ALL valid new-low bars, so 100%
    # of F1 fires sat inside their own null — corrected here to exclude the fires.
    nl_primary = newlow_mask(close, L_PRIMARY) & np.isfinite(np.log((close * volume).replace(0, np.nan)).to_numpy())
    comp = nl_primary & ~fires_primary          # disjoint complement: new-lows that did NOT fire F1
    for h, mk in (("oos", masks["oos"]), ("oos21", masks["oos21"])):
        pool = np.where(comp & fin & mk)[0]
        rec[f"nl_pool_{h}"] = int(len(pool))
        if not nulls[h] or len(pool) == 0:
            continue
        for i in pool:
            sig_rows.append({
                "sym": sym, "kind": "rnl" if h == "oos" else "rnl21", "date": idx[i],
                "month": str(idx[i])[:7],
                "mae_ex": (m["mae63"][i] - nulls["oos"]["mae_med"]) if nulls["oos"] else np.nan,
                "w5_ex": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"]) if nulls["oos"] else np.nan,
                "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (h == "oos21" and nulls["oos21"]) else np.nan,
                "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (h == "oos21" and nulls["oos21"]) else np.nan,
                "tdt": m["tdt"][i], "gate": bool(c32[i]), "sub21": bool(idx[i] >= SUB2021),
            })

    # incumbent (Stoch-RSI @ derived rung) fires — SAME names, TEST, for earliness
    inc_dates = tool_dates(bars_for(close, rung), "S")
    inc_idx = idx.searchsorted(inc_dates)
    inc_tdt = []
    for i in inc_idx:
        if i < len(idx) and np.isfinite(m["tdt"][i]) and idx[i] >= OOS_START:
            inc_tdt.append(float(m["tdt"][i]))
    rec["inc_tdt_med"] = float(np.median(inc_tdt)) if inc_tdt else np.nan
    rec["inc_n_oos"] = len(inc_tdt)
    # F1 primary tdt (OOS) for earliness
    if fires_primary is not None:
        f1_tdt = m["tdt"][fires_primary & fin & masks["oos"]]
        f1_tdt = f1_tdt[np.isfinite(f1_tdt)]
        rec["f1_tdt_med"] = float(np.median(f1_tdt)) if len(f1_tdt) else np.nan
        rec["f1_n_oos"] = int(len(f1_tdt))
    rec["_sig"] = sig_rows
    return rec


# ── month-cluster bootstrap (F1 vs random-day null AND vs random-new-low null) ─

def _name_uplift(g: pd.DataFrame, mcol: str, wcol: str) -> tuple[float, float]:
    """Collapse a subset of signal rows to the cross-name median uplift, per-name FIRST.
    E1 (errata): mirrors the W1-T machinery (ptt_w1_timing_regrade.bootstrap ~L386):
    per (sym) the MAE uplift is the median of mae_ex (= name median mae63 − name base)
    and the W5 uplift is the MEAN of w5_ex (= name signal-day rate − name base rate),
    THEN the cross-name MEDIAN of those per-name uplifts. The prior code took a pooled
    median over per-fire w5_ex ∈ {100−base, −base}, which for any hit rate <50% is
    mechanically ≈ −base regardless of the true uplift (estimator artifact)."""
    if not len(g):
        return np.nan, np.nan
    agg = g.groupby("sym").agg(mae=(mcol, "median"), w5=(wcol, "mean"))
    return float(np.median(agg["mae"])), float(np.median(agg["w5"]))


def bootstrap(sig: pd.DataFrame, sub21: bool) -> dict:
    """Cluster = signal month. Returns CIs on: F1 name-median U_MAE/U_W5 (g0 and g1),
    disjoint-complement new-low name-median U_MAE/U_W5, and the F1−complement diffs.
    Per-name-first collapse (E1) then cross-name median, exactly as W1-T grades it."""
    mcol = "mae_ex21" if sub21 else "mae_ex"
    wcol = "w5_ex21" if sub21 else "w5_ex"
    s = sig[np.isfinite(sig[mcol])].copy()
    if sub21:
        s = s[s.sub21]
    rnl_kind = "rnl21" if sub21 else "rnl"
    months = sorted(s["month"].unique())
    by_month = {m: g for m, g in s.groupby("month")}
    keys = ("f1_umae", "f1_uw5", "f1g_umae", "f1g_uw5",
            "rnl_umae", "rnl_uw5", "d_umae", "d_uw5", "dg_umae", "dg_uw5")
    acc: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[mm] for mm in pick])
        bf1 = boot[boot.kind == "f1"]
        bf1g = bf1[bf1.gate]
        brnl = boot[boot.kind == rnl_kind]
        f1u, f1w = _name_uplift(bf1, mcol, wcol)       # per-name-first, then cross-name median
        f1gu, f1gw = _name_uplift(bf1g, mcol, wcol)
        rnu, rnw = _name_uplift(brnl, mcol, wcol)
        acc["f1_umae"].append(f1u); acc["f1_uw5"].append(f1w)
        acc["f1g_umae"].append(f1gu); acc["f1g_uw5"].append(f1gw)
        acc["rnl_umae"].append(rnu); acc["rnl_uw5"].append(rnw)
        acc["d_umae"].append(f1u - rnu); acc["d_uw5"].append(f1w - rnw)
        acc["dg_umae"].append(f1gu - rnu); acc["dg_uw5"].append(f1gw - rnw)
    out = {}
    for k, v in acc.items():
        a = np.array(v, dtype=float)
        if np.isfinite(a).sum() < NB * 0.5:
            out[k] = (np.nan, np.nan)
        else:
            out[k] = (float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5)))
    return out


# ── report helpers ──────────────────────────────────────────────────────────

def ci_str(ci) -> str:
    if not ci or not np.isfinite(ci[0]):
        return "[—]"
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def verdict(ci) -> str:
    if not ci or not np.isfinite(ci[0]):
        return "—"
    if ci[0] > 0:
        return "excludes 0 ↑"
    if ci[1] < 0:
        return "excludes 0 ↓"
    return "includes 0"


def containment_counts(sym: str) -> tuple[int, int, int] | None:
    """(H1-2022 fires, ±21td-around-2022-low fires, total OOS fires) primary cell."""
    try:
        df = load_px(sym)
    except Exception:  # noqa: BLE001
        return None
    close, volume = df["close"], df["volume"]
    hl = dv_halflife(close, volume)
    if not np.isfinite(hl):
        return None
    W = int(np.clip(round(hl / 2), W_FLOOR, W_CAP))
    m = metric_arrays(close.to_numpy(dtype=float))
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    fire = f1_fires(close, volume, L_PRIMARY, K_PRIMARY, W) & fin
    idx = close.index
    h1 = int((fire & (idx >= H1_22[0]) & (idx <= H1_22[1])).sum())
    lo, hi = idx.searchsorted(LOW22 - pd.Timedelta(days=45)), idx.searchsorted(LOW22 + pd.Timedelta(days=45))
    win = np.zeros(len(idx), bool)
    # ±21 TRADING days around the nearest bar to 2022-10-13
    center = idx.searchsorted(LOW22)
    a, b = max(0, center - 21), min(len(idx), center + 22)
    win[a:b] = True
    near = int((fire & win).sum())
    tot = int((fire & (idx >= OOS_START)).sum())
    return h1, near, tot


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    panel = pd.read_parquet(PANEL_PQ)[["sym", "rung_derived", "vol", "trend", "class_vt"]]
    recs, sig_all, excl = [], [], []
    for _, prow in panel.iterrows():
        try:
            r = compute_name(prow["sym"], prow["rung_derived"])
        except Exception as e:  # noqa: BLE001 — counted, never silent
            excl.append({"sym": prow["sym"], "excl": f"error:{type(e).__name__}"})
            continue
        if "excl" in r:
            excl.append({"sym": r["sym"], "excl": r["excl"]})
            continue
        # eligibility: >=3 FIT and >=3 TEST primary-cell fires
        nfit = r.get(f"n_is_L{L_PRIMARY}_k{K_PRIMARY}", 0)
        ntest = r.get(f"n_oos_L{L_PRIMARY}_k{K_PRIMARY}", 0)
        if nfit < MIN_FIT or ntest < MIN_TEST:
            excl.append({"sym": r["sym"], "excl": f"few_fires(fit={nfit},test={ntest})"})
            continue
        sig_all.extend(r.pop("_sig"))
        recs.append(r)
    p = pd.DataFrame(recs)
    exc = pd.DataFrame(excl)
    sig = pd.DataFrame(sig_all)
    p = p.merge(panel, on="sym", how="left")

    ci = bootstrap(sig, sub21=False)
    ci21 = bootstrap(sig, sub21=True)

    L: list[str] = []
    L.append("# PSS-F1 — Down-volume envelope decay (forced-supply exhaustion on "
             "new lows)\n")
    L.append("Reset-CONFIRMER / exhaustion construction (copy law R-W1T-3). "
             "Pre-registered ruler + construction: script header, committed pre-run "
             "(prereg commit precedes results commit; measurement amendments M1/M2 "
             "disclosed there, both pre-outcome). Entry-timing ruler (§7), NOT hold "
             "returns (wrong-ruler check performed). Machinery (metric_arrays / "
             "null_stats / bars_for / tool_dates) COPIED from the W1 scripts. "
             "Inference: month-cluster bootstrap, NB=1000, seed 20260728. The "
             "commissioning session rules the verdict; this reports what was found.\n")

    # coverage census
    L.append("## Coverage census (eligible / excluded, with reasons)\n")
    tot = len(panel)
    L.append(f"- Universe: {tot} W1-panel names with volume (all {tot} have volume).")
    L.append(f"- **F1-eligible: {len(p)}** (dv_halflife measurable AND ≥{MIN_FIT} FIT "
             f"+ ≥{MIN_TEST} TEST primary-cell fires with resolvable mae63/prox).")
    if len(exc):
        cats: dict[str, int] = {}
        for e in exc["excl"]:
            key = e.split("(")[0]
            cats[key] = cats.get(key, 0) + 1
        L.append(f"- **Excluded: {len(exc)}** — "
                 + "; ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])) + ".")
        # defensives disposition
        defnames = ["KO", "PG", "PEP", "WMT", "COST", "MCD", "JNJ"]
        drows = exc[exc.sym.isin(defnames)]
        if len(drows):
            L.append("- Defensives disposition (expected structural ineligibility, "
                     "accepted loss): "
                     + ", ".join(f"{r.sym}→{r.excl}" for r in drows.itertuples()) + ".")
        inpanel_def = [d for d in defnames if d in set(p["sym"])]
        if inpanel_def:
            L.append(f"- Defensives that DID qualify: {', '.join(inpanel_def)}.")
    L.append(f"- dv_halflife (eligible names): median {float(p.dv_halflife.median()):.0f}td, "
             f"deciles {np.nanpercentile(p.dv_halflife, [10, 50, 90]).round(0).tolist()}. "
             f"Envelope window W: median {int(p.W.median())} new-low bars, "
             f"range {int(p.W.min())}–{int(p.W.max())}.")
    L.append(f"- TEST F1 signals (primary cell, pooled): "
             f"{int((sig.kind=='f1').sum()):,}; disjoint-complement new-low null pool "
             f"(TEST, new-lows that did NOT fire F1 — E2): "
             f"{int((sig.kind=='rnl').sum()):,}.\n")

    # panel base rates
    L.append(f"Panel all-days OOS base rates (median across eligible names): "
             f"MAE63 {float(p.null_oos_mae_med.median()):+.2f}%, "
             f"within-5%-of-low {float(p.null_oos_w5_rate.median()):.1f}%, "
             f"called-low {float(p.null_oos_called_rate.median()):.1f}%.\n")

    # grid table WITH/WITHOUT gate
    L.append("## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level "
             "medians, WITH and WITHOUT the C32 gate\n")
    L.append("No per-name best-of-grid selection (DNR §2). Primary cell = "
             f"(L={L_PRIMARY}, k={K_PRIMARY}). Point estimates are panel medians of "
             "per-name uplifts; the CI/inference row is the pooled month-cluster "
             "bootstrap on the primary cell below.\n")
    L.append("| cell | n names | U_MAE (no gate) | U_W5 (no gate) | U_MAE (C32 gate) "
             "| U_W5 (C32 gate) | n names gated |")
    L.append("|---|---|---|---|---|---|---|")
    for (Lc, k) in GRID:
        um = f"umae_oos_L{Lc}_k{k}"; uw = f"uw5_oos_L{Lc}_k{k}"
        umg = f"umae_oos_L{Lc}_k{k}_g1"; uwg = f"uw5_oos_L{Lc}_k{k}_g1"
        ng = int((p.get(f"n_oos_L{Lc}_k{k}_g1", pd.Series(dtype=float)) >= 1).sum()) if f"n_oos_L{Lc}_k{k}_g1" in p else 0
        star = " ★" if (Lc, k) == (L_PRIMARY, K_PRIMARY) else ""
        L.append(f"| L={Lc}, k={k}{star} | {int(p[um].notna().sum())} | "
                 f"{float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp | "
                 f"{float(p[umg].median()):+.2f}pp | {float(p[uwg].median()):+.2f}pp | {ng} |")

    # 2021+ sub-window for primary cell
    L.append("\n### Primary cell across eras (full TEST / 2021+ sub-window)\n")
    L.append("| era | U_MAE (no gate) | U_W5 (no gate) | U_MAE (gate) | U_W5 (gate) |")
    L.append("|---|---|---|---|---|")
    pk = f"L{L_PRIMARY}_k{K_PRIMARY}"
    for era, suf in (("full TEST ≥2020-07", "oos"), ("2021+ ≥2021-01", "oos21")):
        L.append(f"| {era} | {float(p[f'umae_{suf}_{pk}'].median()):+.2f}pp | "
                 f"{float(p[f'uw5_{suf}_{pk}'].median()):+.2f}pp | "
                 f"{float(p[f'umae_{suf}_{pk}_g1'].median()):+.2f}pp | "
                 f"{float(p[f'uw5_{suf}_{pk}_g1'].median()):+.2f}pp |")

    # inferential CIs (per-name-first month-cluster bootstrap — E1)
    L.append("\n## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls\n")
    L.append("Per-name-first collapse then cross-name median (E1 — matches the W1-T "
             "machinery): within each month-cluster draw, U_MAE = name-median mae63 − "
             "name all-days median, U_W5 = name signal-day within-5%-of-low rate − name "
             "all-days rate, THEN the cross-name median of those per-name uplifts (pp; "
             "for U_MAE + = shallower adverse = better entry). Two nulls: (a) all-DAYS "
             "base rate [in the per-name uplift], (b) the treatment-DISJOINT complement "
             "— valid new-low bars that did NOT fire F1, same declines (F1 falsifier, "
             "E2).\n")
    L.append("| quantity | full TEST | 2021+ |")
    L.append("|---|---|---|")
    rows = [
        ("F1 U_MAE (vs all-days null), no gate", "f1_umae"),
        ("F1 U_W5 (vs all-days null), no gate", "f1_uw5"),
        ("F1 U_MAE, C32 gate", "f1g_umae"),
        ("F1 U_W5, C32 gate", "f1g_uw5"),
        ("disjoint-complement new-low U_MAE (conditional null)", "rnl_umae"),
        ("disjoint-complement new-low U_W5 (conditional null)", "rnl_uw5"),
        ("F1 − complement  U_MAE (FALSIFIER)", "d_umae"),
        ("F1 − complement  U_W5 (FALSIFIER)", "d_uw5"),
        ("F1(gate) − complement  U_MAE", "dg_umae"),
        ("F1(gate) − complement  U_W5", "dg_uw5"),
    ]
    for lab, key in rows:
        L.append(f"| {lab} | {ci_str(ci.get(key))} {verdict(ci.get(key))} | "
                 f"{ci_str(ci21.get(key))} {verdict(ci21.get(key))} |")
    L.append("\nThe FALSIFIER rows are the pre-stated kill: if F1 − disjoint-complement "
             "does not exclude 0 (positive) on U_MAE/U_W5, the contracting-envelope "
             "new-low bar carries no information beyond an ordinary new-low bar. "
             "Printed regardless of outcome.\n")

    # 2022 containment
    L.append("## 2022-class containment (primary cell fire counts)\n")
    L.append("Charter prediction: STRUCTURALLY SILENT in H1-2022 (down-volume was "
             "elevating into each leg → envelope not contracting), coverage near "
             "the 2022-10-13 low. META/NVDA/PG are OFF-PANEL (fell to W1 eligibility) "
             "— run from raw OHLCV as named exhibits, flagged.\n")
    L.append("| name | class | H1-2022 fires | ±21td around 2022-10-13 low | total "
             "TEST fires |")
    L.append("|---|---|---|---|---|")
    panel_syms = set(panel["sym"])
    for sym in MEGA + EXPECT_FAIL:
        cc = containment_counts(sym)
        cls = "mega-cap focus" if sym in MEGA else "expected-FAIL"
        flag = "" if sym in panel_syms else " (off-panel)"
        if cc is None:
            L.append(f"| {sym}{flag} | {cls} | — | — | unmeasurable |")
        else:
            h1, near, tt = cc
            L.append(f"| {sym}{flag} | {cls} | {h1} | {near} | {tt} |")
    # aggregate over eligible mega focus in-panel
    mega_in = [s for s in MEGA if s in panel_syms]
    L.append(f"\nMega-cap focus in-panel: {', '.join(mega_in) or 'none'}. "
             "H1-2022 vs near-low counts test the containment claim per name above.\n")

    # earliness vs incumbent
    L.append("## Earliness vs incumbent (Stoch-RSI<20 cross @ derived rung, SAME "
             "names)\n")
    L.append("td_to_trough: negative = trough BEFORE the fire (late confirmer); "
             "positive = fire BEFORE the trough (pre-trough / early). Per-name "
             "medians over TEST, then panel median of those.\n")
    both = p[np.isfinite(p.f1_tdt_med) & np.isfinite(p.inc_tdt_med)]
    L.append(f"- Names with both F1 and incumbent TEST fires: {len(both)}.")
    if len(both):
        L.append(f"- **F1 median td_to_trough (panel median of name medians): "
                 f"{float(both.f1_tdt_med.median()):+.1f}td** "
                 f"(n_fires median {int(both.f1_n_oos.median())}/name).")
        L.append(f"- **Incumbent median td_to_trough: {float(both.inc_tdt_med.median()):+.1f}td** "
                 f"(n median {int(both.inc_n_oos.median())}/name).")
        d = float((both.f1_tdt_med - both.inc_tdt_med).median())
        L.append(f"- Per-name (F1 − incumbent) td_to_trough, median: {d:+.1f}td "
                 f"(positive = F1 fires earlier / more pre-trough than the incumbent "
                 f"on the same name).\n")

    # product split (descriptive)
    L.append("## Product split (descriptive; calls-low vs confirms-reset)\n")
    f1o = sig[sig.kind == "f1"]
    if len(f1o):
        called = float(((f1o.tdt >= -2) & (f1o.tdt <= 5)).mean() * 100)
        conf = float((f1o.tdt < -2).mean() * 100)
        early = float((f1o.tdt > 5).mean() * 100)
        L.append(f"F1 primary-cell TEST fires (n={len(f1o):,}): called-low (−2..+5td) "
                 f"{called:.0f}% · confirmed-reset (<−2td) {conf:.0f}% · early (>+5td) "
                 f"{early:.0f}% · median td_to_trough {float(f1o.tdt.median()):+.0f}td.\n")

    # what was found (no verdict language)
    L.append("## What was found (no verdict — the commissioning session rules)\n")
    d_full = ci.get("d_umae"); dw_full = ci.get("d_uw5")
    f1_full = ci.get("f1_umae")
    L.append(f"- F1 (no gate) U_MAE vs the all-days null on full TEST: "
             f"{ci_str(f1_full)} ({verdict(f1_full)}); U_W5 {ci_str(ci.get('f1_uw5'))} "
             f"({verdict(ci.get('f1_uw5'))}).")
    L.append(f"- The pre-stated FALSIFIER (F1 − disjoint-complement new-low): "
             f"U_MAE {ci_str(d_full)} ({verdict(d_full)}), U_W5 {ci_str(dw_full)} "
             f"({verdict(dw_full)}) on full TEST; 2021+ U_MAE "
             f"{ci_str(ci21.get('d_umae'))} ({verdict(ci21.get('d_umae'))}), U_W5 "
             f"{ci_str(ci21.get('d_uw5'))} ({verdict(ci21.get('d_uw5'))}).")
    L.append("- The C32-gate column pair, the 2022 containment counts, and the "
             "earliness-vs-incumbent table above are the pre-registered conditioner "
             "reads. All nulls are printed.\n")

    # ── ERRATA (post-outcome corrections toward the pre-registered definitions) ──
    L.append("## Errata (post-outcome corrections toward the pre-registered "
             "definitions — prompted by adversarial review)\n")
    L.append("Both corrections move the code TO the pinned ruler/construction in the "
             "script header; neither changes the pre-registration. They were made "
             "AFTER outcomes were seen, prompted by an adversarial review, and are "
             "disclosed here as errata rather than silently patched.\n")
    L.append("**E1 — estimator conformance (per-name-first U_W5/U_MAE).** The inference "
             "bootstrap computed `np.median` over the POOLED per-fire uplift rows. Each "
             "per-fire `w5_ex` ∈ {100−base, −base}; for any name-agnostic hit rate below "
             "50% the pooled median fire is a miss, so the U_W5 statistic collapsed to "
             "≈ −base (here ≈ −7pp) MECHANICALLY, independent of the true uplift — which "
             "is why the old inference U_W5 (≈ −7pp) contradicted this study's own "
             "name-median grid figure (+28.63pp, unchanged). The registered ruler "
             "defines U_W5 as a rate−rate and U_MAE as a name-median−base; the fix "
             "collapses per-name FIRST (name signal-day rate for W5 = mean of `w5_ex`; "
             "name-median mae63 for MAE) then takes the cross-name median — the exact "
             "machinery COPIED from ptt_w1_timing_regrade.bootstrap. Month-cluster "
             "resampling, seed 20260728, NB=1000 are unchanged.\n")
    L.append("**E2 — falsifier pool decontamination.** The random-new-low (RNL) null "
             "pool was ALL valid new-low bars — so 100% of the F1 fires sat inside their "
             "own null, contaminating the F1−RNL falsifier toward 0. The placebo-mirror "
             "house law requires a treatment-DISJOINT null: the pool is now the "
             "complement — valid new-low bars that did NOT fire F1 (same eligibility "
             "filter, same ±31td proximity window, same closes-only plane, same per-name "
             "baselines). The full complement is used (not an equal-count subsample), so "
             "the null's per-name conditional rate is exact.\n")
    L.append("**Invalid-as-printed headline CIs (audit trail).** The pre-correction "
             "inference table printed the estimator-artifact U_W5 CIs below; retained "
             "struck through for the audit record, NOT to be cited.\n")
    L.append("| quantity (E1-invalid) | full TEST (as printed) | 2021+ (as printed) |")
    L.append("|---|---|---|")
    L.append("| ~~F1 U_W5 (vs all-days null), no gate~~ | ~~[-7.74, -5.96] excludes 0 ↓~~ "
             "| ~~[-7.73, -5.56] excludes 0 ↓~~ |")
    L.append("| ~~F1 U_W5, C32 gate~~ | ~~[-7.90, -6.23] excludes 0 ↓~~ | "
             "~~[-7.94, -5.63] excludes 0 ↓~~ |")
    L.append("| ~~random-new-low U_W5 (contaminated null)~~ | ~~[-7.81, -5.34] excludes "
             "0 ↓~~ | ~~[-7.88, -5.48] excludes 0 ↓~~ |")
    L.append("\nU_MAE was less distorted than U_W5 by E1 (a continuous statistic, not a "
             "collapsed binary), but the corrected inference table above re-reports it "
             "under the same per-name-first collapse for consistency. The F1−complement "
             "falsifier CIs (both metrics) also change under E2 (decontaminated pool).\n")

    # limitations
    L.append("## Limitations\n")
    L.append("- Closes-only MAE/troughs (house shadow-book form); intraday lows are "
             "deeper. Comparable across cells, not absolute.")
    L.append("- Survivor tape (data/baskets/ohlcv holds today's listings); per-name "
             "own-baseline netting removes level bias, not composition bias.")
    L.append("- Yahoo close is total-return adjusted; the log-slope envelope is "
             "level-invariant so the adjustment nets out of the contraction test.")
    L.append("- ±31td proximity window is the §7 pin; long bear legs make 'the low' "
             "window-relative. The disjoint-complement new-low null shares this window "
             "(fair test).")
    L.append("- dv_halflife window derivation (M-final) rests on FIT-era down-day "
             "ACF; the lag-1 form (charter sketch) was degenerate and re-pinned "
             "pre-outcome (M1). W is a bucketed monotone map, not outcome-tuned.")
    L.append("- META/NVDA/PG are off the W1 panel (W1 eligibility); the containment "
             "diagnostic runs them as raw-OHLCV exhibits, flagged.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    keep = [c for c in p.columns if not c.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} "
          f"({len(p)} eligible names, {len(exc)} excluded)")


if __name__ == "__main__":
    main()
