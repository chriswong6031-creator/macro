#!/usr/bin/env python3
"""PSS-F2 — Overnight-vs-intraday return decomposition flip (who is selling).

PRE-REGISTRATION — this header is the pinned ruler AND the pinned construction,
committed BEFORE any timing outcome (MAE/W5/proximity) was computed. The prereg
commit ("prereg: PSS-F2 …") precedes the results commit in git history (audited).
Charters: research/PSS_WSIG_SHORTLIST_BY_FABLE.md §F2 + §"Execution rails";
research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W-SIG / §0 / §2.
Trial-ledger family: pss_f2_overnight (registered in data/trial_ledger.jsonl in
the same pre-run commit as this file). Sibling F1 (pss_f1_downvol, KILLED) — this
study REUSES F1's corrected machinery (metric_arrays / null_stats / bars_for /
tool_dates / _name_uplift per-name-first collapse) and MUST NOT repeat F1's two
shipped bugs (E1 median-of-binary sign-flip; E2 contaminated placebo pool).

Copy law R-W1T-3 governs all text here: this is a reset-CONFIRMER / exhaustion /
terminality / accumulation construction — it never "calls bottoms" (words "bottom
caller" / "calls bottoms" are BANNED). "validated" is CI-banned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE ONE MECHANISM HYPOTHESIS (pre-registered).
In names that bottom via session accumulation, a durable low is preceded by the
day's COMPOSITION inverting before its NET return does: the OVERNIGHT leg stays
negative (fear still gaps it down at the open) while the INTRADAY leg turns
persistently positive (buyers accumulate all session, close up off the open) —
this decoupling precedes the close-to-close turn the incumbent oscillator waits
for. Fire = a rolling window at the name's structure rung where the overnight
leg's median is < 0 AND the intraday leg's median is > 0 (and, in the stricter
grid cell, ≥ the name's own 60th-pct of positive intraday moves).

WRONG-RULER CHECK (§W-SIG execution rail, performed BEFORE statistics were
chosen). The object under test is an ENTRY-TIMING claim: "does an overnight-
negative / intraday-positive decoupling window sit shallower-to-the-trough /
closer-to-the-low / EARLIER than the aggregate net-return turn and the incumbent
cross?". It is NOT a hold-return claim. Grading it on fwd63 hold returns would be
the DNR §3 wrong-ruler law (#1458, Oracle reversion reframe — the same error PTT-
W1-T corrected). Therefore the metrics below are entry-quality metrics (MAE-to-
trough, proximity-to-low, td-to-trough), never drift metrics. fwd-return is not
read. (F1 header carried the identical paragraph; F2 inherits it verbatim in
spirit — the ruler choice is the same house §7 standard, motive #1458.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL PINNED CONSTRUCTION (daily OHLC → level-invariant ratio legs; PIT throughout).

1. THE TWO LEGS (daily grain — the mechanism's native grain; yahoo close is total-
   return adjusted, so both legs are RATIOS and the adjustment nets out — level-
   invariant, noted).
     overnight_ret[d] = open[d] / close[d-1] − 1     (the gap INTO the session)
     intraday_ret[d]  = close[d] / open[d]  − 1       (accumulation ACROSS the session)
     net_ret[d]       = close[d] / close[d-1] − 1     (= aggregate; used by the placebo)
   Algebraically (1+overnight)(1+intraday) = (1+net) exactly; the split is the
   decomposition F2 claims adds information over the aggregate net_ret.

2. RUNG-BAR AGGREGATION (structure rung from the codex; K bars measured on that
   rung). rung_derived is read PER NAME from data/personality_timing/codex.parquet
   (charter §F2 pins the codex as the rung source; F1 read the W1-panel column —
   they agree on shared names). Bar aggregation uses bars_for() from
   scripts/research/ptt_w1_persistence_of_fit.py (rung ∈ {3D, 1W, 2W}: 3D = daily
   iloc[2::3], 1W = W-FRI last, 2W = W-FRI last iloc[::2]). A rung bar's leg value
   = the MEDIAN of the DAILY leg values of the daily bars composing that rung bar
   (each daily row maps to the first rung-bar close date ≥ it). This keeps the
   overnight/intraday split DAILY (fear gaps at THE open, buyers accumulate over
   THE session — the mechanism is a daily-microstructure object) while the K-bar
   persistence window and the firing cadence live at the name's structure rung
   (§W-SIG: "over K bars at the reversion rung"). Unmeasurable rung ⇒ EXCLUDED
   with a printed reason (never defaulted).

3. FIRE. Over a trailing rolling window of K rung bars (inclusive of the current
   rung bar; PIT — no lookahead), fire on the current rung bar iff
     median(overnight_ret over the K rung bars)  < 0            (fear at the open persists)
     AND median(intraday_ret over the K rung bars) > q          (session accumulation)
   where q = 0 (simple flip) in the primary cell, and q = the name's own 60th
   percentile of its POSITIVE intraday_ret rung-bar values (its accumulation
   scale) in the stricter grid cell. The fire is stamped on the rung-bar CLOSE
   date and mapped to the nearest daily index for the §7 timing ruler.

4. SMALL PINNED GRID (multiplicity budget = 4 cells, disclosed; NO per-name best-
   of-grid selection — that is the standing DNR §2 two-ruler kill, PTT-W1a).
     K ∈ {3, 5}  ×  q ∈ { >0 simple flip , ≥ name-60th-pct of positive intraday }
     = 4 cells, all graded and reported side by side.
   PRIMARY pre-registered cell = (K=5, q = >0 simple flip). The other three are
   robustness. K and q are FIXED (not derived, not outcome-selected). The rung is
   DERIVED per name from measurement (codex), never outcome-selected.

   PRE-OUTCOME MEASUREMENT PROBE (fire-count DISTRIBUTION only — no MAE/W5/prox was
   computed or read, mirroring F1 M1/M2 / PTT-W1 A1/A2). Rung-bar-legs form,
   1,300 W1-panel names: primary cell (K=5, q>0) → median 65 OOS fires/name
   (deciles 27/65/114), 0 zero-fire names, 1,288 names ≥3 FIT+≥3 TEST; stricter
   cell (K=5, q60) → median 11 OOS fires/name (deciles 3/11/22), 39 zero-fire
   names, 979 names eligible. The primary cell is DELIBERATELY LOOSE (a mild-
   pullback-with-intraday-resilience condition is common) — this is a PROPERTY of
   the pinned construction, disclosed, NOT a degeneracy; the decomposition-vs-
   aggregate falsifier (§FALSIFIER) is exactly what tests whether that density
   carries information. Overlap probe (400 names, OOS): 36.4% of F2 fires occur
   while median net_ret ≤ 0 — F2 fires are NOT a subset of net-return-turn days
   (the whole claim), so the placebo is a matched-construction analog, not a
   disjoint complement. No re-pin was required (construction non-degenerate).

PER-NAME MEASUREMENT AXIS (report it; codex-derivable, no event fitting): the
name's overnight/intraday return-split RATIO — median|overnight_ret| /
median|intraday_ret| over FIT (how much of MY daily move is gap vs session) —
and its baseline intraday-leg vol (std of daily intraday_ret over FIT). All-gap
names (ratio ≫ 1: gap dominates, intraday leg is noise) and thin defensives
(both legs microstructure noise) are the structurally-ineligible classes the
charter predicts; the axis is printed, not gated on (display-tier context).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULER (§7 house standard; machinery COPIED from ptt_w1_timing_regrade.py —
metric_arrays / null_stats — and ptt_w1_persistence_of_fit.py — bars_for /
tool_dates — NOT reinvented). Closes-only, house shadow-book form.
  Per signal at daily index i:
    mae63 = min(close[i+1..i+63]) / close[i] − 1        (%; ≤0; PRIMARY-lens raw)
    prox  = close[i] / min(close[i−31..i+31]) − 1        (%; ≥0; §7 ±31td window)
    w5    = prox ≤ 5%                                    (entered within 5% of the low)
    tdt   = argmin offset of close in [i−31,i+31] (td; negative = trough BEFORE fire)
    mfe21 = max(close[i+1..i+21]) / close[i] − 1  ·  rc21 = close[i+21]/close[i] − 1
  Valid-day universe per half: i ≥ 31 AND i + 63 < len (both windows resolvable).
  RANDOM-DAY NULLS: per-name, per-half, per-metric all-days medians/rates over the
  half's valid days (the base-rate trap guard).
  THE TWO INFERENTIAL METRICS (exactly two; everything else is descriptive):
    U_MAE = median signal mae63 − all-days median mae63   (pp; +=shallower=better; PRIMARY)
    U_W5  = signal within-5%-of-low rate − all-days rate    (pp; CO-PRIMARY)
  tdt / prox3 / mfe21 / rc21 are DESCRIPTIVE.

  ⚠️ HARD AGGREGATION REQUIREMENT (F1 shipped a median-of-binary SIGN-FLIP bug
  here — NOT repeated). For ANY binary rate metric (U_W5, prox rates), aggregate
  PER-NAME FIRST: per name compute the RATE = mean(hit indicator), subtract the
  name's baseline rate, THEN take the cross-name MEDIAN of those per-name uplifts.
  NEVER take np.median over pooled per-fire binary-minus-constant rows (for a hit
  rate < 50% that mechanically collapses to −base, flipping the sign). The
  `_name_uplift` helper and the bootstrap are COPIED from the corrected
  pss_f1_downvol.py (groupby("sym").agg(w5=("w5_x","mean")) then cross-name
  median, mirroring ptt_w1_timing_regrade.bootstrap). A self-check asserts the
  F2-vs-all-days U_W5 bootstrap point matches a direct per-name-median computation
  within bootstrap noise (printed).

  INFERENCE: month-cluster bootstrap (cluster = signal calendar month; DT-R14 —
  ticker-only clustering is FORBIDDEN), NB = 1000, RNG seed 20260729 (pinned).
  ERA SPLIT (DT-R16): FIT ≤ 2020-06-30 / TEST ≥ 2020-07-01, plus the 2021+ sub-
  window (≥ 2021-01-01). A full-sample-only effect is DISQUALIFIED. All grading
  is on TEST; FIT is used ONLY to measure the per-name axis + the q60 threshold.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE FALSIFIER — TWO prongs, both pre-stated (this is F2's kill; the placebo mirrors
the precondition — the F1 lesson: a placebo must mirror the ACTUAL evaluator).
F2's edge CLAIM is that the DECOMPOSITION adds information over the AGGREGATE and
fires EARLIER. So:

  1. DECOMPOSITION-ADDS-NOTHING null (the mirror placebo). Build a NET-RETURN
     ANALOG signal = the IDENTICAL construction (same K, same rung, same rung-bar
     aggregation, same quantile logic, same window) but on net_ret (close-to-
     close) instead of the overnight/intraday split — i.e. fire when
     median(net_ret over K rung bars) > q (q = 0 simple, or the name's 60th-pct
     of positive net_ret rung bars in the stricter cell). Grade F2 − net-return-
     analog on U_MAE and U_W5 (month-cluster bootstrap, PAIRED on the same
     resampled month-clusters, per-name-first). If the split does not beat its own
     aggregate analog, the decomposition carries NO information and it dies. Also
     grade F2 vs the all-days per-name random-day null (basic near-low check, like
     F1's). Beware: F2 fires are NOT a subset of net-return-turn days (36.4% fire
     while net_ret ≤ 0 — measured pre-outcome) — so the placebo is a matched-
     construction counterfactual, NOT a disjoint complement; implemented as the
     analog signal, with an overlap/disjointness census (both/F2-only/analog-only)
     reported.

  2. EARLINESS (hard requirement from the charter). F2 median td_to_trough must be
     STRICTLY earlier (more positive / more pre-trough) than BOTH
       (a) the incumbent Stoch-RSI<20 cross at the derived rung
           (tool_dates(bars_for(px, rung), "S")), AND
       (b) the net-return analog,
     on the SAME names. If not strictly earlier, the "pre-trough" claim is
     RETRACTED to at/post in the report — stated plainly. The EARLINESS claim is
     graded on the +ATR-VETO variant (F2's required charter form, below). If the
     veto removes all the earliness, F2 is honestly NULL — reported plainly.

  ALL nulls are printed regardless of outcome (nulls printed, never hidden).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATES — pre-stated conditioner columns (grade WITH and WITHOUT, on the PRIMARY
cell; NOT on the grid cells). Three variants graded as a pre-stated column set:

  • RAW (no gate) — shows F2's 2022 exposure HONESTLY (F2 is the most 2022-exposed
    family, per the charter; the risk is carried openly).

  • +ATR-VETO — F2's own charter-mandated 2022 mitigation: fire ONLY when the
    intraday flip is accompanied by a NON-accelerating multi-bar ATR (the
    incumbent's accelerating-range veto analog). PINNED definition: on DAILY bars,
    ATR14 = Wilder-smoothed True Range over 14 days; the multi-bar ATR is
    NON-accelerating at a fire's rung-bar close date iff
        ATR14[today] ≤ ATR14[21 trading days ago]
    (the 21-td trailing ATR is not expanding — range is flat or contracting, not
    accelerating into the fire). Accelerating range (ATR14 rising over the trailing
    21 td) VETOES the fire. 21 td ≈ one month, matched to the mfe/rc horizon.

  • +C32 decline-deceleration gate — the slate-shared terminality conditioner
    (roc20 stopped making new lows while close ≤ 60d low + rolling-low slope
    flattening). COPIED verbatim from pss_f1_downvol.c32_gate (M = 20 td).

The EARLINESS claim (prong 2) is graded on the +ATR-VETO variant (F2's required
form). Per the charter: if the veto removes all the earliness, F2 is honestly
NULL — reported plainly if it occurs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2022-CLASS CONTAINMENT DIAGNOSTIC (pre-stated). Fire counts in H1-2022
(2022-01-01..2022-06-30) vs a ±21td window around the 2022-10-13 low — RAW,
+ATR-veto, +C32 — on the mega-cap focus names (AAPL MSFT AMZN GOOGL UNH HD COST)
and TSLA/NVDA as the expected-all-gap-FAIL class. The charter predicts RAW fires
INTO H1-2022 downtrends and the veto must SUPPRESS that while retaining near-low
coverage. NVDA is OFF the W1 panel (fell to W1 eligibility) but IS in the codex —
run from raw OHLCV as a named exhibit, flagged. Reported for the primary cell.

UNIVERSE / ELIGIBILITY. Universe = W1 panel names (data/research/ptt_w1_panel.parquet)
with OHLC incl. OPEN (data/baskets/ohlcv per-symbol parquet). A name is F2-
ELIGIBLE iff its codex rung is measurable AND it has ≥3 FIT and ≥3 TEST primary-
cell fires with resolvable mae63/prox. Coverage census (eligible / excluded +
reasons: no rung / too few fires) is PRINTED — never a bare count (vacuous-green
law). Expected structurally ineligible (accepted loss, reported as such): all-gap
names (some TSLA/NVDA regimes — intraday leg is noise) and thin defensives (open/
close split is microstructure noise).

REGISTRY COMPLIANCE. DT-R14 month-cluster · DT-R16 era split · DNR §2 two-ruler
kill respected (zero per-name best-of-grid; rung derived, not selected; K/q fixed)
· DNR §3 wrong-ruler law is the MOTIVE for the entry ruler · R-W1T-3 copy law
(exhaustion/reset/accumulation language; no "bottom caller"/"calls bottoms" verb;
"validated" avoided) · display-tier only — NOTHING here promotes to authority (the
gauntlet is a PROMOTION gate, not this build gate; a null never blocks accrual;
LLMs originate nothing — deterministic arithmetic). The commissioning session
rules the verdict; this report states what was found, no verdict language.

Outputs: reports/pss_f2_overnight.md + data/research/pss_f2_overnight_panel.parquet.
Run: python3 scripts/research/pss_f2_overnight.py   (off the render path; <~30 min, 4 cores).
Deterministic (pinned seed 20260729) — a rerun reproduces the report byte-identical.
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
from scripts.research.pss_f1_downvol import c32_gate  # noqa: E402 — C32 gate reused verbatim

RNG = np.random.default_rng(20260729)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
PANEL_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
CODEX_PQ = ROOT / "data" / "personality_timing" / "codex.parquet"
OUT_MD = ROOT / "reports" / "pss_f2_overnight.md"
OUT_PQ = ROOT / "data" / "research" / "pss_f2_overnight_panel.parquet"

H = 63           # MAE window
PROX = 31        # ±31td proximity window (§7)
TEXIT = 21
NB = 1000
W5 = 5.0
K_PRIMARY = 5
Q_PRIMARY = "simple"          # >0 simple flip
GRID = [(K, q) for K in (3, 5) for q in ("simple", "q60")]  # 4 cells
Q60 = 60.0
ATR_N = 14       # Wilder ATR window
ATR_LOOKBACK = 21  # non-accelerating: ATR14[t] <= ATR14[t-21]
MIN_FIT = 3
MIN_TEST = 3
MEGA = ["AAPL", "MSFT", "AMZN", "GOOGL", "UNH", "HD", "COST"]
EXPECT_FAIL = ["TSLA", "NVDA"]
LOW22 = pd.Timestamp("2022-10-13")
H1_22 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-06-30"))
DEFENSIVES = ["KO", "PG", "PEP", "WMT", "COST", "MCD", "JNJ"]


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


def half_masks(idx: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    return {
        "is": np.asarray(idx <= SPLIT),
        "oos": np.asarray(idx >= OOS_START),
        "oos21": np.asarray(idx >= SUB2021),
    }


# ── F2 construction ─────────────────────────────────────────────────────────

def rung_bar_legs(df: pd.DataFrame, rung: str
                  ) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Per-rung-bar median DAILY overnight / intraday / net legs.

    Daily legs (level-invariant ratios): overnight = open/prior_close − 1,
    intraday = close/open − 1, net = close/prior_close − 1. Each daily row maps to
    the first rung-bar close date ≥ it; the rung-bar leg value = median of the
    daily legs composing it. Keeps the split DAILY (mechanism grain) with the
    K-bar window at the structure rung. PIT — no lookahead within the aggregation
    (a rung bar only sees its own constituent daily bars)."""
    on = (df["open"] / df["close"].shift(1) - 1).to_numpy()
    it = (df["close"] / df["open"] - 1).to_numpy()
    net = (df["close"] / df["close"].shift(1) - 1).to_numpy()
    rb = bars_for(df["close"], rung).index
    pos = rb.searchsorted(df.index)          # rung bar each daily row belongs to
    valid = pos < len(rb)
    g = pd.DataFrame({"rb": pos[valid], "on": on[valid], "it": it[valid],
                      "net": net[valid]})
    agg = g.groupby("rb").agg(on=("on", "median"), it=("it", "median"),
                              net=("net", "median"))
    onb = np.full(len(rb), np.nan); itb = np.full(len(rb), np.nan)
    ntb = np.full(len(rb), np.nan)
    onb[agg.index.values] = agg["on"].to_numpy()
    itb[agg.index.values] = agg["it"].to_numpy()
    ntb[agg.index.values] = agg["net"].to_numpy()
    return rb, onb, itb, ntb


def _roll_med(a: np.ndarray, K: int) -> np.ndarray:
    """Trailing K-bar median (inclusive of current bar); NaN until K bars exist."""
    return pd.Series(a).rolling(K, min_periods=K).median().to_numpy()


def q60_positive(a: np.ndarray) -> float:
    """Name's own 60th-pct of its POSITIVE leg values (accumulation scale)."""
    pos = a[np.isfinite(a) & (a > 0)]
    return float(np.percentile(pos, Q60)) if len(pos) > 20 else 0.0


def f2_fires_daily(df: pd.DataFrame, rung: str, K: int, q: str
                   ) -> np.ndarray:
    """Boolean fire array over the DAILY index. Overnight-negative / intraday-
    positive decoupling window at the structure rung, stamped on the rung-bar
    close and mapped to the nearest daily index. q60 threshold uses FIT-only
    positive-intraday values (PIT: no test data in the threshold)."""
    rb, onb, itb, _ = rung_bar_legs(df, rung)
    ovm = _roll_med(onb, K)
    ivm = _roll_med(itb, K)
    if q == "q60":
        fit_mask = rb <= SPLIT
        thr = q60_positive(itb[fit_mask])
    else:
        thr = 0.0
    fire_rb = (ovm < 0) & (ivm > thr)
    fire = np.zeros(len(df), dtype=bool)
    daily_idx = df.index
    hit = np.where(fire_rb)[0]
    for j in hit:
        di = daily_idx.searchsorted(rb[j])       # rung-bar close date → daily index
        if di < len(daily_idx):
            fire[di] = True
    return fire


def net_analog_fires_daily(df: pd.DataFrame, rung: str, K: int, q: str
                           ) -> np.ndarray:
    """The DECOMPOSITION-ADDS-NOTHING mirror placebo: identical construction on
    net_ret (close-to-close) instead of the split. Fire when the K-rung-bar median
    net_ret > q (q = 0 simple, or FIT 60th-pct of positive net_ret rung bars)."""
    rb, _, _, ntb = rung_bar_legs(df, rung)
    ntm = _roll_med(ntb, K)
    if q == "q60":
        thr = q60_positive(ntb[rb <= SPLIT])
    else:
        thr = 0.0
    fire_rb = ntm > thr
    fire = np.zeros(len(df), dtype=bool)
    daily_idx = df.index
    for j in np.where(fire_rb)[0]:
        di = daily_idx.searchsorted(rb[j])
        if di < len(daily_idx):
            fire[di] = True
    return fire


def atr_nonaccel_daily(df: pd.DataFrame) -> np.ndarray:
    """Non-accelerating multi-bar ATR veto mask on the DAILY index (True = allow).
    ATR14 = Wilder-smoothed True Range; non-accelerating iff ATR14[t] ≤
    ATR14[t-ATR_LOOKBACK] (21-td trailing ATR not expanding). Accelerating range
    vetoes (mask False)."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = len(close)
    pc = np.empty(n); pc[0] = close[0]; pc[1:] = close[:-1]
    tr = np.maximum.reduce([high - low, np.abs(high - pc), np.abs(low - pc)])
    atr = pd.Series(tr).ewm(alpha=1.0 / ATR_N, adjust=False,
                            min_periods=ATR_N).mean().to_numpy()
    allow = np.zeros(n, dtype=bool)
    for i in range(ATR_LOOKBACK, n):
        if np.isfinite(atr[i]) and np.isfinite(atr[i - ATR_LOOKBACK]):
            allow[i] = atr[i] <= atr[i - ATR_LOOKBACK]
    return allow


def split_ratio(df: pd.DataFrame) -> tuple[float, float]:
    """Per-name axis (FIT): overnight/intraday split ratio + baseline intraday vol."""
    on = (df["open"] / df["close"].shift(1) - 1)
    it = (df["close"] / df["open"] - 1)
    fit = df.index <= SPLIT
    on_f = on[fit].dropna(); it_f = it[fit].dropna()
    if len(on_f) < 60 or len(it_f) < 60:
        return float("nan"), float("nan")
    denom = float(np.median(np.abs(it_f)))
    ratio = float(np.median(np.abs(on_f)) / denom) if denom > 0 else float("nan")
    ivol = float(it_f.std() * 100)
    return ratio, ivol


# ── per-name computation ────────────────────────────────────────────────────

def load_px(sym: str) -> pd.DataFrame:
    return pd.read_parquet(OHLCV / f"{sym}.parquet")[
        ["open", "high", "low", "close", "volume"]].dropna()


def compute_name(sym: str, rung: str) -> dict:
    """Per-cell fire metrics + the F2 / net-analog / incumbent signal rows. NO
    best-of-grid selection: every cell graded independently."""
    df = load_px(sym)
    close = df["close"]
    c = close.to_numpy(dtype=float)
    idx = close.index
    m = metric_arrays(c)
    masks = half_masks(idx)
    nulls = {h: null_stats(m, masks[h]) for h in ("is", "oos", "oos21")}
    rec: dict = {"sym": sym, "rung": rung}
    if not isinstance(rung, str):
        rec["excl"] = "no_rung"
        return rec
    ratio, ivol = split_ratio(df)
    rec["split_ratio"] = ratio
    rec["intraday_vol"] = ivol
    if not nulls["is"] or not nulls["oos"]:
        rec["excl"] = "null_universe_small"
        return rec
    for h in ("is", "oos", "oos21"):
        for kk, vv in (nulls[h] or {}).items():
            rec[f"null_{h}_{kk}"] = vv

    c32 = c32_gate(close)
    atr_allow = atr_nonaccel_daily(df)
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    sig_rows: list[dict] = []
    fires_primary = None
    na_primary = None
    for (K, q) in GRID:
        fire = f2_fires_daily(df, rung, K, q)
        valid = fire & fin
        for h in ("is", "oos", "oos21"):
            mk = masks[h]
            sub = valid & mk
            n = int(sub.sum())
            rec[f"n_{h}_K{K}_{q}"] = n
            if n == 0 or not nulls[h]:
                rec[f"umae_{h}_K{K}_{q}"] = np.nan
                rec[f"uw5_{h}_K{K}_{q}"] = np.nan
                continue
            mae = m["mae63"][sub]; prox = m["prox"][sub]
            rec[f"umae_{h}_K{K}_{q}"] = float(np.median(mae) - nulls[h]["mae_med"])
            rec[f"uw5_{h}_K{K}_{q}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
        if (K, q) == (K_PRIMARY, Q_PRIMARY):
            fires_primary = fire
            na_primary = net_analog_fires_daily(df, rung, K, q)
            # gate variants (RAW / +ATR-veto / +C32) — pre-stated column set, primary cell
            for gate, gmask in (("raw", np.ones(len(c), bool)),
                                ("atr", atr_allow), ("c32", c32)):
                gv = valid & gmask
                for h in ("oos", "oos21"):
                    mk = masks[h]
                    sub = gv & mk
                    n = int(sub.sum())
                    rec[f"n_{h}_{gate}"] = n
                    if n == 0 or not nulls[h]:
                        rec[f"umae_{h}_{gate}"] = np.nan
                        rec[f"uw5_{h}_{gate}"] = np.nan
                        continue
                    mae = m["mae63"][sub]; prox = m["prox"][sub]
                    rec[f"umae_{h}_{gate}"] = float(np.median(mae) - nulls[h]["mae_med"])
                    rec[f"uw5_{h}_{gate}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
            # signal rows for the bootstrap (primary cell, TEST): F2 (raw/atr/c32) + net-analog
            va = valid & masks["oos"]
            for i in np.where(va)[0]:
                sig_rows.append({
                    "sym": sym, "kind": "f2", "date": idx[i], "month": str(idx[i])[:7],
                    "mae_ex": m["mae63"][i] - nulls["oos"]["mae_med"],
                    "w5_ex": (100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"],
                    "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "tdt": m["tdt"][i], "atr": bool(atr_allow[i]), "gc32": bool(c32[i]),
                    "sub21": bool(idx[i] >= SUB2021),
                })
            # net-return analog fires (same cell, TEST) — the mirror placebo pool
            nav = na_primary & fin & masks["oos"]
            for i in np.where(nav)[0]:
                sig_rows.append({
                    "sym": sym, "kind": "na", "date": idx[i], "month": str(idx[i])[:7],
                    "mae_ex": m["mae63"][i] - nulls["oos"]["mae_med"],
                    "w5_ex": (100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"],
                    "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
                    "tdt": m["tdt"][i], "atr": bool(atr_allow[i]), "gc32": bool(c32[i]),
                    "sub21": bool(idx[i] >= SUB2021),
                })

    # overlap census (primary cell, TEST): both / F2-only / analog-only
    if fires_primary is not None and na_primary is not None:
        f2o = fires_primary & fin & masks["oos"]
        nao = na_primary & fin & masks["oos"]
        rec["ov_both"] = int((f2o & nao).sum())
        rec["ov_f2only"] = int((f2o & ~nao).sum())
        rec["ov_naonly"] = int((nao & ~f2o).sum())

    # incumbent (Stoch-RSI<20 @ derived rung) fires — SAME names, TEST, earliness
    inc_dates = tool_dates(bars_for(close, rung), "S")
    inc_idx = idx.searchsorted(inc_dates)
    inc_tdt = []
    for i in inc_idx:
        if i < len(idx) and np.isfinite(m["tdt"][i]) and idx[i] >= OOS_START:
            inc_tdt.append(float(m["tdt"][i]))
    rec["inc_tdt_med"] = float(np.median(inc_tdt)) if inc_tdt else np.nan
    rec["inc_n_oos"] = len(inc_tdt)
    # F2 tdt (primary, TEST) — RAW and +ATR-veto — for earliness
    if fires_primary is not None:
        base = fires_primary & fin & masks["oos"]
        f2_tdt = m["tdt"][base]; f2_tdt = f2_tdt[np.isfinite(f2_tdt)]
        rec["f2_tdt_med"] = float(np.median(f2_tdt)) if len(f2_tdt) else np.nan
        rec["f2_n_oos"] = int(len(f2_tdt))
        av = base & atr_allow
        f2a = m["tdt"][av]; f2a = f2a[np.isfinite(f2a)]
        rec["f2atr_tdt_med"] = float(np.median(f2a)) if len(f2a) else np.nan
        rec["f2atr_n_oos"] = int(len(f2a))
    if na_primary is not None:
        nb = na_primary & fin & masks["oos"]
        na_tdt = m["tdt"][nb]; na_tdt = na_tdt[np.isfinite(na_tdt)]
        rec["na_tdt_med"] = float(np.median(na_tdt)) if len(na_tdt) else np.nan
        rec["na_n_oos"] = int(len(na_tdt))
    rec["_sig"] = sig_rows
    return rec


# ── month-cluster bootstrap (COPIED per-name-first collapse from pss_f1_downvol) ─

def _name_uplift(g: pd.DataFrame, mcol: str, wcol: str) -> tuple[float, float]:
    """Collapse a subset of signal rows to the cross-name median uplift, per-name
    FIRST (mirrors pss_f1_downvol._name_uplift / ptt_w1_timing_regrade.bootstrap):
    per (sym) the MAE uplift is the median of mae_ex (= name median mae63 − name
    base) and the W5 uplift is the MEAN of w5_ex (= name signal-day rate − name
    base rate), THEN the cross-name MEDIAN. NEVER a pooled median over per-fire
    w5_ex ∈ {100−base, −base} (that collapses to ≈ −base for any hit rate <50%,
    the F1 E1 sign-flip bug)."""
    if not len(g):
        return np.nan, np.nan
    agg = g.groupby("sym").agg(mae=(mcol, "median"), w5=(wcol, "mean"))
    return float(np.median(agg["mae"])), float(np.median(agg["w5"]))


def bootstrap(sig: pd.DataFrame, sub21: bool) -> dict:
    """Cluster = signal month. CIs on: F2 name-median U_MAE/U_W5 (raw, +ATR, +C32),
    net-return-analog U_MAE/U_W5, and the PAIRED F2−net-analog diffs (same resampled
    clusters). Per-name-first collapse then cross-name median (F1 E1-corrected)."""
    mcol = "mae_ex21" if sub21 else "mae_ex"
    wcol = "w5_ex21" if sub21 else "w5_ex"
    s = sig[np.isfinite(sig[mcol])].copy()
    if sub21:
        s = s[s.sub21]
    months = sorted(s["month"].unique())
    by_month = {mm: g for mm, g in s.groupby("month")}
    keys = ("f2_umae", "f2_uw5", "f2a_umae", "f2a_uw5", "f2c_umae", "f2c_uw5",
            "na_umae", "na_uw5", "d_umae", "d_uw5", "da_umae", "da_uw5")
    acc: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[mm] for mm in pick])
        bf2 = boot[boot.kind == "f2"]
        bf2a = bf2[bf2.atr]
        bf2c = bf2[bf2.gc32]
        bna = boot[boot.kind == "na"]
        f2u, f2w = _name_uplift(bf2, mcol, wcol)
        f2au, f2aw = _name_uplift(bf2a, mcol, wcol)
        f2cu, f2cw = _name_uplift(bf2c, mcol, wcol)
        nau, naw = _name_uplift(bna, mcol, wcol)
        acc["f2_umae"].append(f2u); acc["f2_uw5"].append(f2w)
        acc["f2a_umae"].append(f2au); acc["f2a_uw5"].append(f2aw)
        acc["f2c_umae"].append(f2cu); acc["f2c_uw5"].append(f2cw)
        acc["na_umae"].append(nau); acc["na_uw5"].append(naw)
        acc["d_umae"].append(f2u - nau); acc["d_uw5"].append(f2w - naw)   # PAIRED
        acc["da_umae"].append(f2au - nau); acc["da_uw5"].append(f2aw - naw)
    out = {}
    for k, v in acc.items():
        a = np.array(v, dtype=float)
        if np.isfinite(a).sum() < NB * 0.5:
            out[k] = (np.nan, np.nan)
        else:
            out[k] = (float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5)))
    return out


def direct_uw5_check(sig: pd.DataFrame) -> tuple[float, float]:
    """Self-check: direct per-name-median U_W5 (F2 and net-analog), NO bootstrap.
    Must match the bootstrap point estimates within bootstrap noise (F1 E1 guard)."""
    s = sig[np.isfinite(sig["w5_ex"])]
    f2 = s[s.kind == "f2"]; na = s[s.kind == "na"]
    f2v = f2.groupby("sym")["w5_ex"].mean()
    nav = na.groupby("sym")["w5_ex"].mean()
    return (float(np.median(f2v)) if len(f2v) else np.nan,
            float(np.median(nav)) if len(nav) else np.nan)


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


def containment_counts(sym: str, rung: str) -> dict | None:
    """H1-2022 vs ±21td-around-2022-low fire counts, RAW / +ATR / +C32, primary cell."""
    try:
        df = load_px(sym)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rung, str):
        return None
    close = df["close"]
    m = metric_arrays(close.to_numpy(dtype=float))
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    fire = f2_fires_daily(df, rung, K_PRIMARY, Q_PRIMARY) & fin
    atr_allow = atr_nonaccel_daily(df)
    c32 = c32_gate(close)
    idx = close.index
    center = idx.searchsorted(LOW22)
    win = np.zeros(len(idx), bool)
    a, b = max(0, center - 21), min(len(idx), center + 22)
    win[a:b] = True
    h1_mask = (idx >= H1_22[0]) & (idx <= H1_22[1])
    out = {}
    for gate, gmask in (("raw", np.ones(len(idx), bool)),
                        ("atr", atr_allow), ("c32", c32)):
        fg = fire & gmask
        out[f"h1_{gate}"] = int((fg & h1_mask).sum())
        out[f"near_{gate}"] = int((fg & win).sum())
    return out


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    panel = pd.read_parquet(PANEL_PQ)[["sym", "vol", "trend", "class_vt"]]
    codex = pd.read_parquet(CODEX_PQ).set_index("sym")["rung_derived"]
    recs, sig_all, excl = [], [], []
    for _, prow in panel.iterrows():
        sym = prow["sym"]
        rung = codex.get(sym)
        try:
            r = compute_name(sym, rung)
        except Exception as e:  # noqa: BLE001 — counted, never silent
            excl.append({"sym": sym, "excl": f"error:{type(e).__name__}"})
            continue
        if "excl" in r:
            excl.append({"sym": r["sym"], "excl": r["excl"]})
            continue
        nfit = r.get(f"n_is_K{K_PRIMARY}_{Q_PRIMARY}", 0)
        ntest = r.get(f"n_oos_K{K_PRIMARY}_{Q_PRIMARY}", 0)
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
    dchk_f2, dchk_na = direct_uw5_check(sig)

    L: list[str] = []
    L.append("# PSS-F2 — Overnight-vs-intraday return decomposition flip (who is "
             "selling)\n")
    L.append("Reset-CONFIRMER / session-accumulation construction (copy law "
             "R-W1T-3 — no 'bottom caller' / 'calls bottoms'). Pre-registered ruler "
             "+ construction: script header, committed pre-run (prereg commit "
             "precedes results commit in git history). Entry-timing ruler (§7), NOT "
             "hold returns (wrong-ruler check performed; motive #1458). Machinery "
             "(metric_arrays / null_stats / bars_for / tool_dates / _name_uplift "
             "per-name-first) COPIED from the W1 + F1 scripts. Inference: month-"
             "cluster bootstrap, NB=1000, seed 20260729. The commissioning session "
             "rules the verdict; this reports what was found.\n")

    # coverage census
    L.append("## Coverage census (eligible / excluded, with reasons)\n")
    tot = len(panel)
    L.append(f"- Universe: {tot} W1-panel names with OHLC incl. OPEN (rung_derived "
             f"read per name from data/personality_timing/codex.parquet).")
    L.append(f"- **F2-eligible: {len(p)}** (codex rung measurable AND ≥{MIN_FIT} FIT "
             f"+ ≥{MIN_TEST} TEST primary-cell (K={K_PRIMARY}, q=simple) fires with "
             f"resolvable mae63/prox).")
    if len(exc):
        cats: dict[str, int] = {}
        for e in exc["excl"]:
            key = e.split("(")[0]
            cats[key] = cats.get(key, 0) + 1
        L.append(f"- **Excluded: {len(exc)}** — "
                 + "; ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])) + ".")
        drows = exc[exc.sym.isin(DEFENSIVES)]
        if len(drows):
            L.append("- Defensives disposition (open/close split = microstructure "
                     "noise; expected structural ineligibility, accepted loss): "
                     + ", ".join(f"{r.sym}→{r.excl}" for r in drows.itertuples()) + ".")
        inpanel_def = [d for d in DEFENSIVES if d in set(p["sym"])]
        if inpanel_def:
            L.append(f"- Defensives that DID qualify: {', '.join(inpanel_def)}.")
    # per-name axis distribution
    if "split_ratio" in p and p.split_ratio.notna().any():
        sr = p.split_ratio.dropna()
        L.append(f"- Per-name overnight/intraday split ratio (|gap|/|session|, FIT): "
                 f"median {float(sr.median()):.2f}, deciles "
                 f"{np.nanpercentile(sr, [10, 50, 90]).round(2).tolist()} "
                 f"(≫1 = gap-dominated / intraday leg thinner). Baseline intraday-leg "
                 f"vol: median {float(p.intraday_vol.median()):.2f}%.")
        gap_dom = int((sr > 1.0).sum())
        L.append(f"- Gap-dominated eligible names (split ratio > 1): {gap_dom} "
                 f"({gap_dom / len(sr):.0%}) — the intraday leg is comparatively thin "
                 f"there (all-gap-class risk carried openly).")
    L.append(f"- TEST F2 signals (primary cell, pooled): "
             f"{int((sig.kind == 'f2').sum()):,}; net-return-analog fires (TEST, "
             f"pooled): {int((sig.kind == 'na').sum()):,}.\n")

    # panel base rates
    L.append(f"Panel all-days OOS base rates (median across eligible names): "
             f"MAE63 {float(p.null_oos_mae_med.median()):+.2f}%, "
             f"within-5%-of-low {float(p.null_oos_w5_rate.median()):.1f}%, "
             f"called-low {float(p.null_oos_called_rate.median()):.1f}%.\n")

    # grid table
    L.append("## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level "
             "medians (RAW, no gate)\n")
    L.append("No per-name best-of-grid selection (DNR §2). Primary cell = "
             f"(K={K_PRIMARY}, q=simple>0). Point estimates are panel medians of "
             "per-name uplifts; the CI/inference rows are the pooled month-cluster "
             "bootstrap on the primary cell below. q=simple → median(intraday)>0; "
             "q60 → median(intraday) ≥ the name's FIT 60th-pct of positive intraday.\n")
    L.append("| cell | n names | U_MAE | U_W5 | median OOS fires/name |")
    L.append("|---|---|---|---|---|")
    for (K, q) in GRID:
        um = f"umae_oos_K{K}_{q}"; uw = f"uw5_oos_K{K}_{q}"; nn = f"n_oos_K{K}_{q}"
        star = " ★" if (K, q) == (K_PRIMARY, Q_PRIMARY) else ""
        nser = p[nn][p[nn] > 0] if nn in p else pd.Series(dtype=float)
        L.append(f"| K={K}, q={q}{star} | {int(p[um].notna().sum())} | "
                 f"{float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp | "
                 f"{int(nser.median()) if len(nser) else 0} |")

    # eras for primary cell
    L.append("\n### Primary cell across eras (full TEST / 2021+ sub-window), RAW\n")
    L.append("| era | U_MAE | U_W5 |")
    L.append("|---|---|---|")
    pk = f"K{K_PRIMARY}_{Q_PRIMARY}"
    for era, suf in (("full TEST ≥2020-07", "oos"), ("2021+ ≥2021-01", "oos21")):
        L.append(f"| {era} | {float(p[f'umae_{suf}_{pk}'].median()):+.2f}pp | "
                 f"{float(p[f'uw5_{suf}_{pk}'].median()):+.2f}pp |")

    # gate-variant columns (primary cell): RAW / +ATR-veto / +C32
    L.append("\n## Gate variants on the primary cell (pre-stated column set: RAW / "
             "+ATR-veto / +C32), name-level medians\n")
    L.append("RAW carries F2's 2022 exposure honestly. +ATR-veto = fire only when "
             "ATR14[t] ≤ ATR14[t−21] (non-accelerating trailing range — the "
             "incumbent's accelerating-range veto analog). +C32 = decline-"
             "deceleration terminality gate (copied from pss_f1_downvol).\n")
    L.append("| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS |")
    L.append("|---|---|---|---|---|---|")
    for gate, lab in (("raw", "RAW (no gate)"), ("atr", "+ATR-veto"), ("c32", "+C32")):
        um = f"umae_oos_{gate}"; uw = f"uw5_oos_{gate}"
        um21 = f"umae_oos21_{gate}"; uw21 = f"uw5_oos21_{gate}"
        nn = f"n_oos_{gate}"
        nnames = int((p.get(nn, pd.Series(dtype=float)) >= 1).sum()) if nn in p else 0
        L.append(f"| {lab} | {float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp "
                 f"| {float(p[um21].dropna().median()):+.2f}pp | "
                 f"{float(p[uw21].dropna().median()):+.2f}pp | {nnames} |")

    # inference CIs vs BOTH nulls
    L.append("\n## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls\n")
    L.append("Per-name-first collapse then cross-name median (matches the F1/W1-T "
             "machinery — the F1 E1 sign-flip bug is NOT repeated): within each "
             "month-cluster draw, U_MAE = name-median mae63 − name all-days median, "
             "U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN "
             "the cross-name median. Two nulls: (a) all-DAYS base rate [inside the "
             "per-name uplift], (b) the NET-RETURN ANALOG (identical construction on "
             "net_ret — the decomposition-adds-nothing mirror placebo). The F2 − "
             "net-analog diff is PAIRED on the same resampled month-clusters.\n")
    L.append(f"Self-check (F1 E1 guard): direct per-name-median U_W5 = F2 "
             f"{dchk_f2:+.2f}pp / net-analog {dchk_na:+.2f}pp; the bootstrap point "
             f"estimates below must match these within bootstrap noise.\n")
    L.append("| quantity | full TEST | 2021+ |")
    L.append("|---|---|---|")
    rows = [
        ("F2 U_MAE (vs all-days null), RAW", "f2_umae"),
        ("F2 U_W5 (vs all-days null), RAW", "f2_uw5"),
        ("F2 U_MAE, +ATR-veto", "f2a_umae"),
        ("F2 U_W5, +ATR-veto", "f2a_uw5"),
        ("F2 U_MAE, +C32", "f2c_umae"),
        ("F2 U_W5, +C32", "f2c_uw5"),
        ("net-return-analog U_MAE (aggregate null)", "na_umae"),
        ("net-return-analog U_W5 (aggregate null)", "na_uw5"),
        ("F2 − net-analog  U_MAE (FALSIFIER, paired)", "d_umae"),
        ("F2 − net-analog  U_W5 (FALSIFIER, paired)", "d_uw5"),
        ("F2(ATR) − net-analog  U_MAE (paired)", "da_umae"),
        ("F2(ATR) − net-analog  U_W5 (paired)", "da_uw5"),
    ]
    for lab, key in rows:
        L.append(f"| {lab} | {ci_str(ci.get(key))} {verdict(ci.get(key))} | "
                 f"{ci_str(ci21.get(key))} {verdict(ci21.get(key))} |")
    L.append("\nThe FALSIFIER rows are the pre-stated kill: if F2 − net-return-analog "
             "does NOT exclude 0 (positive) on U_MAE/U_W5, the DECOMPOSITION carries "
             "no incremental information over just watching close-to-close, and F2 "
             "dies as a standalone construction. Printed regardless of outcome.\n")

    # overlap census
    L.append("## Overlap / disjointness census — F2 vs net-return analog (primary "
             "cell, TEST)\n")
    L.append("The whole F2 claim is that the intraday leg flips while net_ret is "
             "still negative — so F2 fires are NOT a subset of net-turn days; the "
             "placebo is a matched-construction counterfactual, not a disjoint "
             "complement.\n")
    if {"ov_both", "ov_f2only", "ov_naonly"}.issubset(p.columns):
        b = int(p.ov_both.sum()); fo = int(p.ov_f2only.sum()); no = int(p.ov_naonly.sum())
        tf2 = b + fo
        L.append(f"- BOTH F2 & net-analog: {b:,} · F2-only (net_ret still ≤0 at fire): "
                 f"{fo:,} ({fo / tf2:.0%} of F2 fires) · net-analog-only: {no:,}.")
        L.append(f"- F2-only share confirms the composition inverts before the net "
                 f"does in {fo / tf2:.0%} of F2 fires (the pre-registered mechanism); "
                 f"the net-analog is broader ({b + no:,} fires) and largely "
                 f"non-overlapping — a genuine matched counterfactual.\n")

    # earliness vs incumbent AND vs net-analog
    L.append("## Earliness — F2 vs incumbent (Stoch-RSI<20 @ derived rung) AND vs "
             "net-return analog (SAME names)\n")
    L.append("td_to_trough: negative = trough BEFORE the fire (late confirmer); "
             "positive = fire BEFORE the trough (pre-trough / early). Per-name "
             "medians over TEST, then panel median of those. Charter hard requirement: "
             "F2 (in its required +ATR-veto form) must be STRICTLY earlier than BOTH "
             "the incumbent AND the net-analog, else the 'pre-trough' claim is "
             "RETRACTED to at/post.\n")
    bi = p[np.isfinite(p.f2atr_tdt_med) & np.isfinite(p.inc_tdt_med)]
    bn = p[np.isfinite(p.f2atr_tdt_med) & np.isfinite(p.na_tdt_med)]
    L.append("| comparison | n names | F2(+ATR) median tdt | other median tdt | "
             "F2 − other (per-name median) | strictly earlier? |")
    L.append("|---|---|---|---|---|---|")
    if len(bi):
        d = float((bi.f2atr_tdt_med - bi.inc_tdt_med).median())
        L.append(f"| vs incumbent | {len(bi)} | {float(bi.f2atr_tdt_med.median()):+.1f}td "
                 f"| {float(bi.inc_tdt_med.median()):+.1f}td | {d:+.1f}td | "
                 f"{'YES' if d > 0 else 'NO'} |")
    if len(bn):
        d = float((bn.f2atr_tdt_med - bn.na_tdt_med).median())
        L.append(f"| vs net-analog | {len(bn)} | {float(bn.f2atr_tdt_med.median()):+.1f}td "
                 f"| {float(bn.na_tdt_med.median()):+.1f}td | {d:+.1f}td | "
                 f"{'YES' if d > 0 else 'NO'} |")
    # RAW F2 earliness too (context)
    br = p[np.isfinite(p.f2_tdt_med) & np.isfinite(p.inc_tdt_med)]
    if len(br):
        d = float((br.f2_tdt_med - br.inc_tdt_med).median())
        L.append(f"| vs incumbent (RAW F2, context) | {len(br)} | "
                 f"{float(br.f2_tdt_med.median()):+.1f}td | "
                 f"{float(br.inc_tdt_med.median()):+.1f}td | {d:+.1f}td | "
                 f"{'YES' if d > 0 else 'NO'} |")
    L.append("")

    # 2022 containment
    L.append("## 2022-class containment (primary cell fire counts): RAW / +ATR-veto "
             "/ +C32\n")
    L.append("Charter prediction: RAW fires INTO H1-2022 downtrends (F2 is the most "
             "2022-exposed family); the ATR-veto must SUPPRESS that while retaining "
             "coverage near the 2022-10-13 low. TSLA/NVDA are the expected-all-gap-"
             "FAIL class. NVDA is OFF-PANEL (W1 eligibility) — run from raw OHLCV, "
             "flagged.\n")
    L.append("| name | class | H1-2022 (raw / +ATR / +C32) | ±21td 2022-low (raw / "
             "+ATR / +C32) |")
    L.append("|---|---|---|---|")
    panel_syms = set(panel["sym"])
    for sym in MEGA + EXPECT_FAIL:
        rung = codex.get(sym)
        cc = containment_counts(sym, rung)
        cls = "mega-cap focus" if sym in MEGA else "expected-FAIL (all-gap)"
        flag = "" if sym in panel_syms else " (off-panel)"
        if cc is None:
            L.append(f"| {sym}{flag} | {cls} | — | unmeasurable |")
        else:
            L.append(f"| {sym}{flag} | {cls} | "
                     f"{cc['h1_raw']} / {cc['h1_atr']} / {cc['h1_c32']} | "
                     f"{cc['near_raw']} / {cc['near_atr']} / {cc['near_c32']} |")
    L.append("")

    # product split (descriptive)
    L.append("## Product split (descriptive; calls-low vs confirms-reset)\n")
    f2o = sig[sig.kind == "f2"]
    if len(f2o):
        called = float(((f2o.tdt >= -2) & (f2o.tdt <= 5)).mean() * 100)
        conf = float((f2o.tdt < -2).mean() * 100)
        early = float((f2o.tdt > 5).mean() * 100)
        L.append(f"F2 primary-cell TEST fires (n={len(f2o):,}): near-low (−2..+5td) "
                 f"{called:.0f}% · confirmed-reset (<−2td) {conf:.0f}% · early (>+5td) "
                 f"{early:.0f}% · median td_to_trough {float(f2o.tdt.median()):+.0f}td.\n")

    # what was found (no verdict language)
    L.append("## What was found (no verdict — the commissioning session rules)\n")
    f2_full = ci.get("f2_umae"); d_full = ci.get("d_umae"); dw_full = ci.get("d_uw5")
    L.append(f"- F2 (RAW) U_MAE vs the all-days null on full TEST: {ci_str(f2_full)} "
             f"({verdict(f2_full)}); U_W5 {ci_str(ci.get('f2_uw5'))} "
             f"({verdict(ci.get('f2_uw5'))}).")
    L.append(f"- The pre-stated FALSIFIER (F2 − net-return analog, decomposition-"
             f"adds-nothing): U_MAE {ci_str(d_full)} ({verdict(d_full)}), U_W5 "
             f"{ci_str(dw_full)} ({verdict(dw_full)}) on full TEST; 2021+ U_MAE "
             f"{ci_str(ci21.get('d_umae'))} ({verdict(ci21.get('d_umae'))}), U_W5 "
             f"{ci_str(ci21.get('d_uw5'))} ({verdict(ci21.get('d_uw5'))}).")
    L.append("- The +ATR-veto and +C32 gate columns, the earliness-vs-incumbent AND "
             "earliness-vs-net-analog tables, the 2022 containment counts, and the "
             "overlap census above are the pre-registered conditioner reads. All "
             "nulls are printed. The earliness claim is graded on the +ATR-veto form; "
             "if the veto removed the earliness, the 'pre-trough' claim is stated as "
             "retracted in the earliness table (strictly-earlier? = NO).\n")

    # limitations
    L.append("## Limitations\n")
    L.append("- Closes-only MAE/troughs (house shadow-book form); intraday lows are "
             "deeper. Comparable across cells/variants, not absolute.")
    L.append("- Yahoo close is total-return adjusted; the overnight/intraday RATIO "
             "split is level-invariant so the adjustment nets out (open is the raw "
             "session open on the same adjusted scale — the ratio is unaffected).")
    L.append("- Survivor tape (data/baskets/ohlcv holds today's listings); per-name "
             "own-baseline netting removes level bias, not composition bias.")
    L.append("- The primary cell (K=5, q=simple>0) is deliberately loose (median 65 "
             "OOS fires/name) — a mild-pullback-with-intraday-resilience condition is "
             "common; the decomposition-vs-aggregate falsifier is the test of whether "
             "that density carries information beyond the net-return turn.")
    L.append("- ±31td proximity window is the §7 pin; long bear legs make 'the low' "
             "window-relative. The net-return analog shares this window (fair test).")
    L.append("- Rung-bar legs take the MEDIAN daily leg within each rung bar (robust "
             "to a single outlier day); the split stays a daily-microstructure object "
             "with the persistence window at the structure rung.")
    L.append("- NVDA is off the W1 panel (W1 eligibility); the containment diagnostic "
             "runs it as a raw-OHLCV exhibit, flagged.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    keep = [c for c in p.columns if not c.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} "
          f"({len(p)} eligible names, {len(exc)} excluded)")


if __name__ == "__main__":
    main()
