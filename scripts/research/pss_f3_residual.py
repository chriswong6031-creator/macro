#!/usr/bin/env python3
"""PSS-F3 — Idiosyncratic residual reset (beta-stripped own-flush exhaustion).

PRE-REGISTRATION — this header is the pinned ruler AND the pinned construction,
committed BEFORE any timing outcome (MAE/W5/proximity) was computed. The prereg
commit ("prereg: PSS-F3 …") precedes the results commit in git history (audited).
Charters: research/PSS_WSIG_SHORTLIST_BY_FABLE.md §F3 + §"Execution rails";
research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W-SIG / §0 / §2.
Trial-ledger family: pss_f3_residual (registered in data/trial_ledger.jsonl in
the same pre-run commit as this file). Siblings F1 (pss_f1_downvol, KILLED) + F2
(pss_f2_overnight, KILLED) — this study REUSES their corrected machinery
(metric_arrays / null_stats / bars_for / tool_dates / _name_uplift per-name-first
collapse / c32_gate) and MUST NOT repeat F1's two shipped bugs (E1 median-of-
binary sign-flip on any binary-rate metric; E2 contaminated placebo pool).

Copy law R-W1T-3 governs all text here: this is a reset-CONFIRMER / exhaustion /
terminality / capitulation construction — it never "calls bottoms" (the words
"bottom caller" / "calls bottoms" are BANNED; use exhaustion/reset/terminality/
capitulation). "validated" is CI-banned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE ONE MECHANISM HYPOTHESIS (pre-registered).
At a durable IDIOSYNCRATIC bottom, a name's sellers exhaust while the market /
sector tide is still going out, so the beta-stripped RESIDUAL (name return minus
its rolling beta × sector-benchmark return) prints its capitulation and turns UP
BEFORE the RAW price low — because the price is still being dragged down by a
falling benchmark the name no longer leads down. Fire ONLY when the residual and
systemic components DISAGREE (residual recovering while the raw price is still
falling / flat). This is the "different stocks bottom differently" family:
SILENT by construction in systemic flushes (high name–sector R², residual not
leading — see the 2022 containment test).

WRONG-RULER CHECK (§W-SIG execution rail, performed BEFORE statistics were
chosen). The object under test is an ENTRY-TIMING claim: "does a residual-turn-up-
while-price-still-falling bar sit shallower-to-the-trough / closer-to-the-low /
EARLIER than the raw-price analog and the incumbent cross?". It is NOT a hold-
return claim. Grading it on fwd63 hold returns would be the DNR §3 wrong-ruler law
(#1458, Oracle reversion reframe — the same error PTT-W1-T corrected; F1 and F2
carried the identical paragraph). Therefore the metrics below are entry-quality
metrics (MAE-to-trough, proximity-to-low, td-to-trough), never drift metrics.
fwd-return is not read.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL PINNED CONSTRUCTION (closes only; PIT throughout; level-invariant log rets).

0. SECTOR-ETF MAPPING (per name → GICS sector → SPDR sector ETF).
   PINNED SOURCE = data/breadth/ticker_sectors.parquet (ticker → GICS sector, the
   canonical 11 GICS labels), mapped to the SPDR sector ETF by the fixed dict
   GICS_ETF below (Information Technology→XLK, Financials→XLF, Energy→XLE,
   Materials→XLB, Industrials→XLI, Health Care→XLV, Consumer Staples→XLP,
   Utilities→XLU, Consumer Discretionary→XLY, Real Estate→XLRE, Communication
   Services→XLC). ETF PRICE series = data/yahoo/{ETF}.parquet 'close' (yahoo total-
   return adjusted, deep history: XLB/XLE/XLF/XLI/XLK/XLP/XLU/XLV/XLY from 1998,
   XLRE from 2015-10, XLC from 2018-06). NAME PRICE = data/baskets/ohlcv/{sym}.parquet
   'close' (also total-return adjusted — SAME convention, so the beta regression is
   consistent; both legs are ratios/log-returns and the TR adjustment nets out).

   CONSTRUCTION RE-PIN (PRE-OUTCOME, disclosed — mirrors F1 M1/M2 amendment
   pattern; NO IS/OOS uplift computed or read before this pin). The charter §F3
   sketch says "data/sector_holdings membership". Inspected: data/sector_holdings/
   history.parquet is a TOP-20-holdings-per-ETF snapshot (220 tickers = 11×20) —
   it resolves only 164/1300 W1 names, biased to the largest holdings, too thin
   for a panel study. data/breadth/ticker_sectors.parquet is a purpose-built
   ticker→GICS map covering 799/1300 W1 names with the exact 11 GICS labels that
   map 1:1 to the SPDR sector ETFs — the SAME mechanism (idiosyncratic-vs-SECTOR),
   richer coverage. Re-pinned to ticker_sectors as the membership source; the
   top-20 history.parquet agrees on shared names (both are current GICS). A name
   with no resolvable sector mapping is EXCLUDED (printed reason) — NEVER defaulted
   to SPY: that would change the mechanism from idiosyncratic-vs-sector to
   idiosyncratic-vs-market (a market-residual SECONDARY column is added, clearly
   labeled, NOT the primary — see §SECONDARY).

1. THE LEGS (daily, level-invariant log returns; PIT).
     r_name[d] = ln(close_name[d] / close_name[d-1])
     r_sec[d]  = ln(close_sec[d]  / close_sec[d-1])   (on the name↔ETF inner-join calendar)
   Name and ETF are inner-joined on common trading dates before differencing.

2. ROLLING OLS BETA (vectorized cov/var — NOT a python np.polyfit-per-bar loop;
   the charter's heaviest-step requirement). Over a trailing window of `betawin`
   return days:
     beta[d]  = Cov(r_name, r_sec)[trailing betawin] / Var(r_sec)[trailing betawin]
     alpha[d] = mean(r_name)[betawin] − beta[d]·mean(r_sec)[betawin]
   PIT — the residual on day d uses the beta/alpha estimated THROUGH d−1
   (beta_pit = beta.shift(1), alpha_pit = alpha.shift(1); no lookahead):
     r_res[d] = r_name[d] − alpha_pit[d] − beta_pit[d]·r_sec[d]
   Trailing name–sector R² (for the mechanism test, §FALSIFIER prong 4):
     r2[d] = Corr(r_name, r_sec)[trailing betawin]²   (also shifted PIT for the fire).

3. RESIDUAL DRAWDOWN + TURN (the capitulation object).
     R_cum[d]  = cumsum(r_res)                          (cumulative residual path)
     R_max[d]  = cummax(R_cum)                          (trailing residual high, PIT)
     rdd[d]    = R_cum[d] − R_max[d]   (≤0)              (residual drawdown from its high)
     z_rdd[d]  = rdd[d] / (rolling_std(r_res, betawin)[d] · sqrt(betawin))
                 (residual drawdown in residual-vol units — the per-name z-extreme;
                  scaled by sqrt(betawin) so it is a cumulative-path z, comparable
                  across windows).
   RESIDUAL TURN-UP (higher-low / momentum sign-flip UP over RMOM bars):
     resid_up[d] = (R_cum[d] > R_cum[d-1])                       (residual advancing today)
                   AND (R_cum[d] − min(R_cum[d-RMOM .. d]) > 0)   (off a local residual low)
   RMOM pinned = 5 trading days (a short residual-momentum window; NOT grid-varied —
   the grid varies z and betawin only, per charter).

4. THE DISAGREEMENT GATE (residual and systemic DISAGREE — F3's distinctive fire
   condition). The raw price must still be falling or flat while the residual turns:
     raw_falling[d] = (r_name[d] ≤ 0)                            (name not up on the day)
                      AND (close_name[d] < max(close_name[d-RMOM .. d]))
                                                                  (raw price not recovered —
                                                                   still below its recent high)
   FIRE[d]  iff
     z_rdd[d] ≤ zthr           (residual drawdown at a per-name z-extreme)
     AND resid_up[d]           (residual makes a higher-low / turns UP)
     AND raw_falling[d]        (RAW price still deepening/flat — DISAGREEMENT)
   The fire is emitted at the name's structure-derived RUNG: a raw-daily fire is
   RETAINED only if it lands on/at a rung-bar close (rung from the codex), matching
   the "emit at the structure-derived rung" charter instruction — see rung_gate().

5. SMALL PINNED GRID (multiplicity budget = 4 cells, disclosed; NO per-name best-
   of-grid selection — the standing DNR §2 two-ruler kill, PTT-W1a).
     zthr ∈ {−1.5, −2.0}  ×  betawin ∈ {60, 120} trading days  = 4 cells.
   ALL FOUR graded and reported side by side. PRIMARY pre-registered cell =
   (zthr=−2.0, betawin=120). The other three are robustness. zthr and betawin are
   FIXED (not derived, not outcome-selected). The rung is DERIVED per name from the
   codex (never outcome-selected).

PER-NAME MEASUREMENT AXIS (report it; bars-derivable, no event fitting):
  (a) residual-return autocorrelation HALF-LIFE at the bar-size ladder — the same
      rho-ladder machinery as W1b structure-measurement but computed on the RESIDUAL
      series (r_res) not raw: rho at 3D / 1W / 2W bar sizes and an ACF-decay half-
      life of the residual series (how fast a name's idiosyncratic shock mean-
      reverts). (b) beta-estimation-window stationarity: the split-era beta drift
      = |beta_FIT_median − beta_TEST_median| (does the name's sector beta drift
      across eras — a residual-fit stationarity read). Both PRINTED, display-tier
      context — NOT gated on.

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
  tdt / prox / mfe21 / rc21 are DESCRIPTIVE.

  ⚠️ HARD AGGREGATION REQUIREMENT (F1 shipped a median-of-binary SIGN-FLIP bug
  here — NOT repeated). For ANY binary rate metric (U_W5, prox rates), aggregate
  PER-NAME FIRST: per name compute the RATE = mean(hit indicator), subtract the
  name's baseline rate, THEN take the cross-name MEDIAN of those per-name uplifts.
  NEVER take np.median over pooled per-fire binary-minus-constant rows (for a hit
  rate < 50% that mechanically collapses to −base, flipping the sign). The
  `_name_uplift` helper and the bootstrap are COPIED from the corrected
  pss_f1_downvol.py / pss_f2_overnight.py (groupby("sym").agg(w5=("w5_x","mean"))
  then cross-name median, mirroring ptt_w1_timing_regrade.bootstrap). A self-check
  asserts the F3-vs-all-days U_W5 bootstrap point matches a direct per-name-median
  computation within bootstrap noise (printed — the F1 E1 guard).

  INFERENCE: month-cluster bootstrap (cluster = signal calendar month; DT-R14 —
  ticker-only clustering is FORBIDDEN), NB = 1000, RNG seed 20260730 (pinned).
  ERA SPLIT (DT-R16): FIT ≤ 2020-06-30 / TEST ≥ 2020-07-01, plus the 2021+ sub-
  window (≥ 2021-01-01). A full-sample-only effect is DISQUALIFIED. All grading is
  on TEST; FIT is used ONLY to measure the per-name axis (beta drift, residual rho).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FALSIFIER — FIVE prongs, ALL pre-stated (this is F3's kill; the placebo mirrors
the precondition — the F1 lesson; F2's net-return-analog is the template). ALL
nulls printed regardless of outcome (nulls printed, never hidden).

  1. F3 vs ALL-DAYS per-name random-day null (basic near-low check, like F1/F2's).

  2. RESIDUALIZATION-ADDS-NOTHING null (the MIRROR placebo — F3's analog of F2's
     net-return-analog). Build a RAW-RETURN ANALOG = the IDENTICAL construction
     (same zthr, same betawin-length windows, same RMOM turn logic, same rung gate)
     but on RAW returns / RAW drawdown instead of the residual: r_raw = r_name,
     RAWcum = cumsum(r_name), raw drawdown z, raw turn-up, and the SAME "still-
     falling" gate is vacuous on raw (drop it — the raw analog fires on a raw-price
     z-drawdown that turns up). Grade F3 − raw-return-analog on U_MAE and U_W5
     (month-cluster bootstrap PAIRED on the same resampled month-clusters, per-
     name-first). If beta-stripping does NOT beat the raw analog, the
     residualization carries NO information and F3 dies. F3 fires are NOT a subset
     of raw-turn days (F3 requires the residual to lead WHILE raw is still down) —
     so the placebo is a matched-construction counterfactual, NOT a disjoint
     complement; an overlap census (both / F3-only / analog-only) is reported.

  3. F3 vs the INCUMBENT Stoch-RSI<20 cross at the derived rung (tool_dates(bars_for
     (px, rung), "S")): F3's MAE-to-trough must be SHALLOWER (charter prong 2), on
     the SAME names.

  4. MECHANISM test (charter prong 3 — F3's distinctive falsifier). F3 fires must
     CONCENTRATE in LOW-R² (idiosyncratic) windows. Compute the trailing name–sector
     R² (PIT) at each fire; report the distribution of fires across the NAME'S OWN
     R² TERCILES (terciles cut per name on that name's valid-day R² distribution).
     PRE-STATED: residual-lead should concentrate in the LOWER R² tercile. If fires
     cluster in the HIGH-R² (systemic) tercile instead, the mechanism is dead —
     reported regardless of outcome.

  5. EARLINESS. F3 median td_to_trough must be STRICTLY earlier (more positive /
     more pre-trough) than BOTH (a) the incumbent Stoch-RSI cross AND (b) the raw-
     return analog, on the SAME names. If not strictly earlier, the "pre-trough"
     claim is RETRACTED to at/post — stated plainly (F2's earliness claim failed
     this exact test; grade it honestly).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C32 TERMINALITY GATE (pre-registered CONDITIONER — a pre-stated column pair, NOT
post-hoc; graded WITH and WITHOUT on the primary cell). COPIED verbatim from
pss_f1_downvol.c32_gate (M = 20 td): decline decelerating INTO a fresh 60d low
(roc20 stopped making new lows + rolling-low slope flattening). The gate only
narrows.

2022-CLASS CONTAINMENT DIAGNOSTIC (pre-stated — F3's STRUCTURAL strength).
The charter claims F3 CANNOT fire the 2022 pattern BY CONSTRUCTION (2022 mega-cap
troughs were SYSTEMIC — high R², residual not leading — so the disagreement gate
stays shut). Fire counts in H1-2022 (2022-01-01..2022-06-30) vs a ±21td window
around the 2022-10-13 low, on the high-idiosyncratic-variance focus names
(TSLA NVDA META JNJ UNH PG) AND on expected-SILENT high-R²/index-like names
(KO, PG-in-broad-selloffs, MSFT during macro flushes). PREDICTION: H1-2022 fires
≈ 0 on the systemic names. If F3 fires heavily into H1-2022, the by-construction
containment claim is FALSE — reported regardless. META/NVDA/PG are OFF the W1
panel (fell to W1 eligibility) — run from raw OHLCV as named exhibits, flagged.

SECONDARY (clearly-labeled, NOT primary): a MARKET-residual variant — the same
construction with the sector ETF replaced by SPY (data/yahoo/_GSPC.parquet). This
is reported as a SECONDARY column ONLY (idiosyncratic-vs-market, a different
mechanism than the primary idiosyncratic-vs-sector) so the sector-vs-market
distinction is auditable; it NEVER substitutes for the sector residual on an
unmapped name.

UNIVERSE / ELIGIBILITY. Universe = W1 panel names (data/research/ptt_w1_panel.parquet)
that (a) resolve to a sector ETF (ticker_sectors) AND (b) have the ETF series in
data/yahoo AND (c) have baskets/ohlcv price. A name is F3-ELIGIBLE iff its codex
rung is measurable AND it has ≥3 FIT and ≥3 TEST primary-cell fires with resolvable
mae63/prox. Coverage census (eligible / excluded + reasons: no sector map / no ETF
series / no rung / too few fires) is PRINTED — never a bare count (vacuous-green
law). High-R² / index-like names that stay STRUCTURALLY SILENT are the FEATURE,
not a miss — reported as correctly-silent (zero-fire on the systemic class), not
as excluded.

REGISTRY COMPLIANCE. DT-R14 month-cluster · DT-R16 era split · DNR §2 two-ruler
kill respected (zero per-name best-of-grid; rung derived, not selected; zthr/betawin
fixed) · DNR §3 wrong-ruler law is the MOTIVE for the entry ruler · R-W1T-3 copy
law (exhaustion/reset/terminality/capitulation language; no "bottom caller"/"calls
bottoms" verb; "validated" avoided) · display-tier only — NOTHING here promotes to
authority (the gauntlet is a PROMOTION gate, not this build gate; a null never
blocks accrual; LLMs originate nothing — deterministic arithmetic). The
commissioning session rules the verdict; this report states what was found, no
verdict language.

Outputs: reports/pss_f3_residual.md + data/research/pss_f3_residual_panel.parquet.
Run: python3 scripts/research/pss_f3_residual.py   (off the render path; <~30 min, 4 cores).
Deterministic (pinned seed 20260730) — a rerun reproduces the report byte-identical.
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

RNG = np.random.default_rng(20260730)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
YAHOO = ROOT / "data" / "yahoo"
PANEL_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
CODEX_PQ = ROOT / "data" / "personality_timing" / "codex.parquet"
SECMAP_PQ = ROOT / "data" / "breadth" / "ticker_sectors.parquet"
OUT_MD = ROOT / "reports" / "pss_f3_residual.md"
OUT_PQ = ROOT / "data" / "research" / "pss_f3_residual_panel.parquet"

H = 63           # MAE window
PROX = 31        # ±31td proximity window (§7)
TEXIT = 21
NB = 1000
W5 = 5.0
RMOM = 5         # residual-momentum / higher-low window (FIXED — grid varies z & betawin only)
ZTHR_PRIMARY = -2.0
BW_PRIMARY = 120
GRID = [(z, bw) for z in (-1.5, -2.0) for bw in (60, 120)]  # 4 cells
MIN_FIT = 3
MIN_TEST = 3
GICS_ETF = {
    "Information Technology": "XLK", "Financials": "XLF", "Energy": "XLE",
    "Materials": "XLB", "Industrials": "XLI", "Health Care": "XLV",
    "Consumer Staples": "XLP", "Utilities": "XLU", "Consumer Discretionary": "XLY",
    "Real Estate": "XLRE", "Communication Services": "XLC",
}
# focus: high-idiosyncratic-variance (should FIRE idiosyncratically) vs expected-silent systemic
IDIO = ["TSLA", "NVDA", "META", "JNJ", "UNH", "PG"]
SYSTEMIC = ["KO", "PG", "MSFT"]           # expected structurally silent in H1-2022 (systemic/high-R²)
FOCUS_2022 = IDIO + [s for s in SYSTEMIC if s not in IDIO]
LOW22 = pd.Timestamp("2022-10-13")
H1_22 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-06-30"))
SPY_PQ = YAHOO / "_GSPC.parquet"          # market-residual SECONDARY benchmark


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


# ── F3 construction ─────────────────────────────────────────────────────────

def load_px(sym: str) -> pd.Series:
    """Deep name close (total-return adjusted) from baskets/ohlcv."""
    return pd.read_parquet(OHLCV / f"{sym}.parquet")["close"].dropna()


def load_etf(etf: str) -> pd.Series:
    """Sector-ETF close (yahoo total-return adjusted, deep history)."""
    return pd.read_parquet(YAHOO / f"{etf}.parquet")["close"].dropna()


def rolling_beta_resid(rn: np.ndarray, rb: np.ndarray, bw: int
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """VECTORIZED rolling-OLS beta / PIT residual / trailing R² over a betawin
    window (cov/var — NOT a np.polyfit-per-bar loop; the charter's heaviest step).

    beta[d]  = Cov(rn, rb)/Var(rb) over trailing bw; alpha[d] = mean(rn) − beta·mean(rb).
    PIT: r_res[d] = rn[d] − alpha[d-1] − beta[d-1]·rb[d]. r2[d] = Corr(rn,rb)² (PIT-
    shifted for the fire). Returns (r_res, beta_pit, r2_pit)."""
    sn = pd.Series(rn); sb = pd.Series(rb)
    mn = sn.rolling(bw, min_periods=bw).mean()
    mb = sb.rolling(bw, min_periods=bw).mean()
    cov = sn.rolling(bw, min_periods=bw).cov(sb)
    var = sb.rolling(bw, min_periods=bw).var()
    std_n = sn.rolling(bw, min_periods=bw).std()
    std_b = sb.rolling(bw, min_periods=bw).std()
    beta = cov / var
    alpha = mn - beta * mb
    r2 = (cov / (std_n * std_b)) ** 2
    beta_pit = beta.shift(1)
    alpha_pit = alpha.shift(1)
    r_res = sn - alpha_pit - beta_pit * sb
    return r_res.to_numpy(), beta_pit.to_numpy(), r2.shift(1).to_numpy()


def _turn_and_drawdown(cum: np.ndarray, unit_std: np.ndarray, bw: int
                       ) -> tuple[np.ndarray, np.ndarray]:
    """(z_drawdown, turn_up) for a cumulative-return path `cum`.

    z_dd[d] = (cum[d] − cummax(cum)[d]) / (unit_std[d]·sqrt(bw))  (≤0, cumulative-path z).
    turn_up[d] = cum[d] > cum[d-1]  AND  cum[d] − min(cum[d-RMOM..d]) > 0."""
    n = len(cum)
    cmax = np.fmax.accumulate(np.where(np.isnan(cum), -np.inf, cum))
    cmax[~np.isfinite(cum)] = np.nan
    dd = cum - cmax
    denom = unit_std * np.sqrt(bw)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(denom > 0, dd / denom, np.nan)
    up = np.zeros(n, dtype=bool)
    if n > RMOM:
        rmin = pd.Series(cum).rolling(RMOM + 1, min_periods=RMOM + 1).min().to_numpy()
        adv = np.zeros(n, dtype=bool)
        adv[1:] = cum[1:] > cum[:-1]
        higher_low = np.zeros(n, dtype=bool)
        ok = np.isfinite(cum) & np.isfinite(rmin)
        higher_low[ok] = (cum[ok] - rmin[ok]) > 0
        up = adv & higher_low
    return z, up


def f3_fires(close: pd.Series, r_res: np.ndarray, unit_std: np.ndarray,
             zthr: float, bw: int) -> np.ndarray:
    """F3 fire array over the name's daily index. Residual z-extreme drawdown +
    residual turn-up WHILE raw price still falling/flat (the disagreement gate)."""
    c = close.to_numpy(dtype=float)
    n = len(c)
    r_res = np.asarray(r_res, dtype=float)
    # cumulative residual path; leading region (before the first finite residual,
    # i.e. before the beta window fills) is masked NaN so it never fires.
    firstok = int(np.argmax(np.isfinite(r_res))) if np.isfinite(r_res).any() else n
    Rcum = np.cumsum(np.where(np.isfinite(r_res), r_res, 0.0))
    Rcum[:firstok] = np.nan
    z, up = _turn_and_drawdown(Rcum, unit_std, bw)
    # raw price still falling / flat (disagreement): name not up today AND price below recent high
    rn_day = np.full(n, np.nan)
    rn_day[1:] = np.log(c[1:] / c[:-1])
    rmax = pd.Series(c).rolling(RMOM + 1, min_periods=RMOM + 1).max().to_numpy()
    raw_falling = np.zeros(n, dtype=bool)
    ok = np.isfinite(rn_day) & np.isfinite(rmax)
    raw_falling[ok] = (rn_day[ok] <= 0.0) & (c[ok] < rmax[ok])
    fire = np.zeros(n, dtype=bool)
    valid = np.isfinite(z) & up & raw_falling
    fire[valid] = z[valid] <= zthr
    return fire


def raw_analog_fires(close: pd.Series, zthr: float, bw: int) -> np.ndarray:
    """RESIDUALIZATION-ADDS-NOTHING mirror placebo: IDENTICAL construction on RAW
    returns / RAW drawdown (no beta strip). The 'still-falling' gate is vacuous on
    raw (a raw z-drawdown turning up IS the raw price turning up), so it is dropped;
    the analog fires on a raw-price z-drawdown extreme that turns up over RMOM."""
    c = close.to_numpy(dtype=float)
    n = len(c)
    rn = np.full(n, np.nan)
    rn[1:] = np.log(c[1:] / c[:-1])
    RAWcum = np.cumsum(np.where(np.isfinite(rn), rn, 0.0))
    RAWcum[0] = np.nan
    unit_std = pd.Series(rn).rolling(bw, min_periods=bw).std().to_numpy()
    z, up = _turn_and_drawdown(RAWcum, unit_std, bw)
    fire = np.zeros(n, dtype=bool)
    valid = np.isfinite(z) & up
    fire[valid] = z[valid] <= zthr
    return fire


def rung_gate(close: pd.Series, rung: str) -> np.ndarray:
    """Boolean mask: True on daily indices that are on/at a rung-bar close (emit at
    the structure-derived rung). A fire is retained only if it lands on a rung bar."""
    idx = close.index
    rb = bars_for(close, rung).index
    pos = idx.searchsorted(rb)          # daily index of each rung-bar close
    g = np.zeros(len(idx), dtype=bool)
    pos = pos[pos < len(idx)]
    g[pos] = True
    return g


def residual_rho_axis(r_res_daily: pd.Series) -> dict[str, float]:
    """Per-name residual-return autocorrelation at the 3D/1W/2W bar ladder + an
    ACF-decay half-life of the residual series (measurement axis; FIT-derivable)."""
    s = r_res_daily.dropna()
    out = {"resid_rho_3d": np.nan, "resid_rho_1w": np.nan, "resid_rho_2w": np.nan,
           "resid_hl": np.nan}
    if len(s) < 130:
        return out
    # bar-ladder residual (cumulative residual return per bar, differenced)
    Rcum = s.cumsum()
    for tag, rung in (("resid_rho_3d", "3D"), ("resid_rho_1w", "1W"), ("resid_rho_2w", "2W")):
        bar = bars_for(Rcum.rename("close"), rung)      # bars_for keys off a close-like series
        br = bar.diff().dropna()
        if len(br) > 20:
            out[tag] = float(br.autocorr(1)) if br.std() > 0 else np.nan
    # ACF-decay half-life on FIT-era residual (mirror F1 dv_halflife machinery)
    sf = s[s.index <= SPLIT]
    if len(sf) >= 120:
        ac = np.array([abs(float(sf.autocorr(k))) for k in range(1, 41)])
        lags = np.arange(1, 41)
        mk = ac > 0.02
        if mk.sum() >= 5:
            b = float(np.polyfit(lags[mk], np.log(ac[mk]), 1)[0])
            if b < 0:
                out["resid_hl"] = float(min(np.log(2) / (-b), 250.0))
    return out


# ── per-name computation ────────────────────────────────────────────────────

def _sig_row(sym, kind, i, idx, m, nulls, gate_c32, sub21_flag) -> dict:
    """One bootstrap signal row (per-name-first uplift inputs); COPIED shape from F1/F2."""
    return {
        "sym": sym, "kind": kind, "date": idx[i], "month": str(idx[i])[:7],
        "mae_ex": m["mae63"][i] - nulls["oos"]["mae_med"],
        "w5_ex": (100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"],
        "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
        "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
        "tdt": m["tdt"][i], "gc32": bool(gate_c32[i]), "sub21": bool(idx[i] >= SUB2021),
    }


def compute_name(sym: str, etf: str, rung: str) -> dict:
    """Per-cell fire metrics + the F3 / raw-analog / incumbent signal rows. NO
    best-of-grid selection: every cell graded independently."""
    close = load_px(sym)
    rec: dict = {"sym": sym, "etf": etf, "rung": rung}
    if not isinstance(rung, str):
        rec["excl"] = "no_rung"
        return rec
    try:
        etf_close = load_etf(etf)
    except Exception:  # noqa: BLE001
        rec["excl"] = "no_etf_series"
        return rec
    # inner-join name & ETF on common trading dates → common closes
    j = pd.DataFrame({"c": close}).join(pd.DataFrame({"e": etf_close}), how="inner").dropna()
    if len(j) < BW_PRIMARY + PROX + H + 5:
        rec["excl"] = "short_joined_history"
        return rec
    close = j["c"]
    idx = close.index
    c = close.to_numpy(dtype=float)
    rn = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    ce = j["e"].to_numpy(dtype=float)
    rb = np.concatenate([[np.nan], np.log(ce[1:] / ce[:-1])])

    m = metric_arrays(c)
    masks = half_masks(idx)
    nulls = {h: null_stats(m, masks[h]) for h in ("is", "oos", "oos21")}
    if not nulls["is"] or not nulls["oos"]:
        rec["excl"] = "null_universe_small"
        return rec
    for h in ("is", "oos", "oos21"):
        for kk, vv in (nulls[h] or {}).items():
            rec[f"null_{h}_{kk}"] = vv

    c32 = c32_gate(close)
    rgate = rung_gate(close, rung)
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])

    # per-name axis: residual rho ladder (uses primary-betawin residual) + beta drift
    r_res_p, beta_pit_p, r2_p = rolling_beta_resid(rn, rb, BW_PRIMARY)
    ax = residual_rho_axis(pd.Series(r_res_p, index=idx))
    rec.update(ax)
    bser = pd.Series(beta_pit_p, index=idx)
    b_fit = bser[idx <= SPLIT].median()
    b_test = bser[idx >= OOS_START].median()
    rec["beta_fit_med"] = float(b_fit) if np.isfinite(b_fit) else np.nan
    rec["beta_test_med"] = float(b_test) if np.isfinite(b_test) else np.nan
    rec["beta_drift"] = float(abs(b_fit - b_test)) if (np.isfinite(b_fit) and np.isfinite(b_test)) else np.nan

    sig_rows: list[dict] = []
    fires_primary = None
    ra_primary = None
    r2_primary = r2_p
    # cache residual/unit_std per betawin (2 windows)
    res_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for bw in (60, 120):
        if bw == BW_PRIMARY:
            rr, bp, r2b = r_res_p, beta_pit_p, r2_p
        else:
            rr, bp, r2b = rolling_beta_resid(rn, rb, bw)
        ustd = pd.Series(rr).rolling(bw, min_periods=bw).std().to_numpy()
        res_cache[bw] = (rr, ustd, r2b)

    for (zthr, bw) in GRID:
        rr, ustd, r2b = res_cache[bw]
        fire = f3_fires(close, rr, ustd, zthr, bw) & rgate
        valid = fire & fin
        for h in ("is", "oos", "oos21"):
            mk = masks[h]
            sub = valid & mk
            n = int(sub.sum())
            rec[f"n_{h}_z{zthr}_bw{bw}"] = n
            if n == 0 or not nulls[h]:
                rec[f"umae_{h}_z{zthr}_bw{bw}"] = np.nan
                rec[f"uw5_{h}_z{zthr}_bw{bw}"] = np.nan
                continue
            mae = m["mae63"][sub]; prox = m["prox"][sub]
            rec[f"umae_{h}_z{zthr}_bw{bw}"] = float(np.median(mae) - nulls[h]["mae_med"])
            rec[f"uw5_{h}_z{zthr}_bw{bw}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
        if (zthr, bw) == (ZTHR_PRIMARY, BW_PRIMARY):
            fires_primary = fire
            ra_primary = raw_analog_fires(close, zthr, bw) & rgate
            r2_primary = r2b
            # gate variants (RAW / +C32) — pre-stated column pair, primary cell
            for gate, gmask in (("raw", np.ones(len(c), bool)), ("c32", c32)):
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
            # signal rows for the bootstrap (primary cell, TEST): F3 (raw/c32) + raw-analog
            for i in np.where(valid & masks["oos"])[0]:
                row = _sig_row(sym, "f3", i, idx, m, nulls, c32, None)
                row["r2"] = float(r2b[i]) if np.isfinite(r2b[i]) else np.nan
                sig_rows.append(row)
            rav = ra_primary & fin & masks["oos"]
            for i in np.where(rav)[0]:
                row = _sig_row(sym, "ra", i, idx, m, nulls, c32, None)
                row["r2"] = np.nan
                sig_rows.append(row)

    # overlap census (primary cell, TEST): both / F3-only / analog-only
    if fires_primary is not None and ra_primary is not None:
        f3o = fires_primary & fin & masks["oos"]
        rao = ra_primary & fin & masks["oos"]
        rec["ov_both"] = int((f3o & rao).sum())
        rec["ov_f3only"] = int((f3o & ~rao).sum())
        rec["ov_raonly"] = int((rao & ~f3o).sum())

    # MECHANISM: per-name R² terciles of the name's valid-day R², fire distribution
    if fires_primary is not None:
        r2v = r2_primary[fin & masks["oos"]]
        r2v = r2v[np.isfinite(r2v)]
        if len(r2v) >= 30:
            q1, q2 = np.percentile(r2v, [33.333, 66.667])
            fmask = fires_primary & fin & masks["oos"]
            fr2 = r2_primary[fmask]; fr2 = fr2[np.isfinite(fr2)]
            if len(fr2):
                rec["mech_low"] = int((fr2 <= q1).sum())
                rec["mech_mid"] = int((fr2 > q1) & (fr2 <= q2))
                rec["mech_high"] = int((fr2 > q2).sum())
                rec["mech_n"] = int(len(fr2))

    # incumbent (Stoch-RSI<20 @ derived rung) fires — SAME names, TEST, earliness
    inc_dates = tool_dates(bars_for(close, rung), "S")
    inc_idx = idx.searchsorted(inc_dates)
    inc_tdt = []
    for i in inc_idx:
        if i < len(idx) and np.isfinite(m["tdt"][i]) and idx[i] >= OOS_START:
            inc_tdt.append(float(m["tdt"][i]))
    rec["inc_tdt_med"] = float(np.median(inc_tdt)) if inc_tdt else np.nan
    rec["inc_n_oos"] = len(inc_tdt)
    # F3 primary tdt + MAE (TEST) for earliness + MAE-to-trough vs incumbent
    if fires_primary is not None:
        base = fires_primary & fin & masks["oos"]
        f3_tdt = m["tdt"][base]; f3_tdt = f3_tdt[np.isfinite(f3_tdt)]
        rec["f3_tdt_med"] = float(np.median(f3_tdt)) if len(f3_tdt) else np.nan
        rec["f3_n_oos"] = int(len(f3_tdt))
        f3_mae = m["mae63"][base]; f3_mae = f3_mae[np.isfinite(f3_mae)]
        rec["f3_mae_med"] = float(np.median(f3_mae)) if len(f3_mae) else np.nan
    # incumbent MAE-to-trough (median mae63 at incumbent fires, TEST)
    inc_mae = [float(m["mae63"][i]) for i in inc_idx
               if i < len(idx) and np.isfinite(m["mae63"][i]) and idx[i] >= OOS_START]
    rec["inc_mae_med"] = float(np.median(inc_mae)) if inc_mae else np.nan
    if ra_primary is not None:
        nb = ra_primary & fin & masks["oos"]
        ra_tdt = m["tdt"][nb]; ra_tdt = ra_tdt[np.isfinite(ra_tdt)]
        rec["ra_tdt_med"] = float(np.median(ra_tdt)) if len(ra_tdt) else np.nan
        rec["ra_n_oos"] = int(len(ra_tdt))
        ra_mae = m["mae63"][nb]; ra_mae = ra_mae[np.isfinite(ra_mae)]
        rec["ra_mae_med"] = float(np.median(ra_mae)) if len(ra_mae) else np.nan
    rec["_sig"] = sig_rows
    return rec


# ── month-cluster bootstrap (COPIED per-name-first collapse from pss_f1/f2) ───

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
    """Cluster = signal month. CIs on: F3 name-median U_MAE/U_W5 (raw, +C32),
    raw-return-analog U_MAE/U_W5, and the PAIRED F3−raw-analog diffs (same resampled
    clusters). Per-name-first collapse then cross-name median (F1 E1-corrected)."""
    mcol = "mae_ex21" if sub21 else "mae_ex"
    wcol = "w5_ex21" if sub21 else "w5_ex"
    s = sig[np.isfinite(sig[mcol])].copy()
    if sub21:
        s = s[s.sub21]
    months = sorted(s["month"].unique())
    by_month = {mm: g for mm, g in s.groupby("month")}
    keys = ("f3_umae", "f3_uw5", "f3c_umae", "f3c_uw5",
            "ra_umae", "ra_uw5", "d_umae", "d_uw5")
    acc: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[mm] for mm in pick])
        bf3 = boot[boot.kind == "f3"]
        bf3c = bf3[bf3.gc32]
        bra = boot[boot.kind == "ra"]
        f3u, f3w = _name_uplift(bf3, mcol, wcol)
        f3cu, f3cw = _name_uplift(bf3c, mcol, wcol)
        rau, raw = _name_uplift(bra, mcol, wcol)
        acc["f3_umae"].append(f3u); acc["f3_uw5"].append(f3w)
        acc["f3c_umae"].append(f3cu); acc["f3c_uw5"].append(f3cw)
        acc["ra_umae"].append(rau); acc["ra_uw5"].append(raw)
        acc["d_umae"].append(f3u - rau); acc["d_uw5"].append(f3w - raw)   # PAIRED
    out = {}
    for k, v in acc.items():
        a = np.array(v, dtype=float)
        if np.isfinite(a).sum() < NB * 0.5:
            out[k] = (np.nan, np.nan)
        else:
            out[k] = (float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5)))
    return out


def direct_uw5_check(sig: pd.DataFrame) -> tuple[float, float]:
    """Self-check: direct per-name-median U_W5 (F3 and raw-analog), NO bootstrap.
    Must match the bootstrap point estimates within bootstrap noise (F1 E1 guard)."""
    s = sig[np.isfinite(sig["w5_ex"])]
    f3 = s[s.kind == "f3"]; ra = s[s.kind == "ra"]
    f3v = f3.groupby("sym")["w5_ex"].mean()
    rav = ra.groupby("sym")["w5_ex"].mean()
    return (float(np.median(f3v)) if len(f3v) else np.nan,
            float(np.median(rav)) if len(rav) else np.nan)


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


def containment_counts(sym: str, etf: str, rung: str) -> dict | None:
    """H1-2022 vs ±21td-around-2022-low fire counts, RAW / +C32, primary cell.
    Also the median trailing R² at H1-2022 fires (mechanism check on the tape)."""
    try:
        close = load_px(sym)
        etf_close = load_etf(etf)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rung, str):
        return None
    j = pd.DataFrame({"c": close}).join(pd.DataFrame({"e": etf_close}), how="inner").dropna()
    if len(j) < BW_PRIMARY + PROX + H + 5:
        return None
    close = j["c"]; idx = close.index
    c = close.to_numpy(dtype=float); ce = j["e"].to_numpy(dtype=float)
    rn = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    rb = np.concatenate([[np.nan], np.log(ce[1:] / ce[:-1])])
    rr, _, r2b = rolling_beta_resid(rn, rb, BW_PRIMARY)
    ustd = pd.Series(rr).rolling(BW_PRIMARY, min_periods=BW_PRIMARY).std().to_numpy()
    m = metric_arrays(c)
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    rgate = rung_gate(close, rung)
    c32 = c32_gate(close)
    fire = f3_fires(close, rr, ustd, ZTHR_PRIMARY, BW_PRIMARY) & rgate & fin
    center = idx.searchsorted(LOW22)
    win = np.zeros(len(idx), bool)
    a, b = max(0, center - 21), min(len(idx), center + 22)
    win[a:b] = True
    h1_mask = (idx >= H1_22[0]) & (idx <= H1_22[1])
    out = {}
    for gate, gmask in (("raw", np.ones(len(idx), bool)), ("c32", c32)):
        fg = fire & gmask
        out[f"h1_{gate}"] = int((fg & h1_mask).sum())
        out[f"near_{gate}"] = int((fg & win).sum())
    h1fr2 = r2b[fire & h1_mask]; h1fr2 = h1fr2[np.isfinite(h1fr2)]
    out["h1_r2_med"] = float(np.median(h1fr2)) if len(h1fr2) else np.nan
    # name's own R² median over TEST (context for "is this a high-R² name")
    r2t = r2b[fin & (idx >= OOS_START)]; r2t = r2t[np.isfinite(r2t)]
    out["r2_test_med"] = float(np.median(r2t)) if len(r2t) else np.nan
    return out


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    panel = pd.read_parquet(PANEL_PQ)[["sym", "vol", "trend", "class_vt"]]
    codex = pd.read_parquet(CODEX_PQ).set_index("sym")["rung_derived"]
    secmap = pd.read_parquet(SECMAP_PQ).drop_duplicates("ticker", keep="first")
    secmap = secmap.set_index("ticker")["sector"].map(GICS_ETF)  # ticker → ETF

    recs, sig_all, excl = [], [], []
    for _, prow in panel.iterrows():
        sym = prow["sym"]
        etf = secmap.get(sym)
        if not isinstance(etf, str):
            excl.append({"sym": sym, "excl": "no_sector_map"})
            continue
        rung = codex.get(sym)
        try:
            r = compute_name(sym, etf, rung)
        except Exception as e:  # noqa: BLE001 — counted, never silent
            excl.append({"sym": sym, "excl": f"error:{type(e).__name__}"})
            continue
        if "excl" in r:
            excl.append({"sym": r["sym"], "excl": r["excl"]})
            continue
        nfit = r.get(f"n_is_z{ZTHR_PRIMARY}_bw{BW_PRIMARY}", 0)
        ntest = r.get(f"n_oos_z{ZTHR_PRIMARY}_bw{BW_PRIMARY}", 0)
        if nfit < MIN_FIT or ntest < MIN_TEST:
            excl.append({"sym": r["sym"], "excl": f"few_fires(fit={nfit},test={ntest})"})
            # RETAIN structurally-silent names as a reported class (see census), but
            # they are not eligible for the graded tables.
            continue
        sig_all.extend(r.pop("_sig"))
        recs.append(r)
    p = pd.DataFrame(recs)
    exc = pd.DataFrame(excl)
    sig = pd.DataFrame(sig_all)
    p = p.merge(panel, on="sym", how="left")

    ci = bootstrap(sig, sub21=False)
    ci21 = bootstrap(sig, sub21=True)
    dchk_f3, dchk_ra = direct_uw5_check(sig)

    L: list[str] = []
    L.append("# PSS-F3 — Idiosyncratic residual reset (beta-stripped own-flush "
             "exhaustion)\n")
    L.append("Reset-CONFIRMER / idiosyncratic-capitulation construction (copy law "
             "R-W1T-3 — no 'bottom caller' / 'calls bottoms'). Pre-registered ruler "
             "+ construction: script header, committed pre-run (prereg commit "
             "precedes results commit in git history; the sector-mapping source re-pin "
             "is disclosed there, pre-outcome). Entry-timing ruler (§7), NOT hold "
             "returns (wrong-ruler check performed; motive #1458). Machinery "
             "(metric_arrays / null_stats / bars_for / tool_dates / _name_uplift "
             "per-name-first / c32_gate) COPIED from the W1 + F1 + F2 scripts. "
             "Inference: month-cluster bootstrap, NB=1000, seed 20260730. The "
             "commissioning session rules the verdict; this reports what was found.\n")

    # coverage census
    L.append("## Coverage census (eligible / excluded, with reasons)\n")
    tot = len(panel)
    L.append(f"- Universe: {tot} W1-panel names. Sector-ETF mapping = "
             f"data/breadth/ticker_sectors.parquet (ticker→GICS→SPDR sector ETF); "
             f"ETF price = data/yahoo/{{ETF}} (TR-adj); name price = "
             f"data/baskets/ohlcv (TR-adj, same convention).")
    L.append(f"- **F3-eligible: {len(p)}** (sector-ETF resolvable AND codex rung "
             f"measurable AND ≥{MIN_FIT} FIT + ≥{MIN_TEST} TEST primary-cell "
             f"(z={ZTHR_PRIMARY}, betawin={BW_PRIMARY}) fires with resolvable mae63/prox).")
    if len(exc):
        cats: dict[str, int] = {}
        for e in exc["excl"]:
            key = e.split("(")[0]
            cats[key] = cats.get(key, 0) + 1
        L.append(f"- **Excluded: {len(exc)}** — "
                 + "; ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])) + ".")
        L.append("  - `no_sector_map` = not in the GICS ticker→sector table (NOT "
                 "defaulted to SPY — that would change the mechanism to idiosyncratic-"
                 "vs-market; a market-residual SECONDARY is noted separately). "
                 "`few_fires` INCLUDES the high-R²/index-like names that stay "
                 "STRUCTURALLY SILENT — that silence is the FEATURE (systemic names "
                 "have no residual to lead the price), reported as correctly-silent, "
                 "not as a miss.")
    # ETF mapping distribution among eligible
    if "etf" in p and len(p):
        L.append(f"- Eligible-name ETF distribution: "
                 + ", ".join(f"{k}:{v}" for k, v in p["etf"].value_counts().items()) + ".")
    # per-name axis distribution
    if "resid_hl" in p and p.resid_hl.notna().any():
        rh = p.resid_hl.dropna()
        L.append(f"- Per-name residual ACF-decay half-life (FIT): median "
                 f"{float(rh.median()):.0f}td, deciles "
                 f"{np.nanpercentile(rh, [10, 50, 90]).round(0).tolist()}. "
                 f"Residual rho@3D median {float(p.resid_rho_3d.median()):+.3f}, "
                 f"@1W {float(p.resid_rho_1w.median()):+.3f}, "
                 f"@2W {float(p.resid_rho_2w.median()):+.3f}.")
    if "beta_drift" in p and p.beta_drift.notna().any():
        L.append(f"- Per-name sector-beta drift |β_FIT − β_TEST|: median "
                 f"{float(p.beta_drift.median()):.2f} (β_FIT median "
                 f"{float(p.beta_fit_med.median()):.2f}, β_TEST median "
                 f"{float(p.beta_test_med.median()):.2f}).")
    L.append(f"- TEST F3 signals (primary cell, pooled): "
             f"{int((sig.kind == 'f3').sum()):,}; raw-return-analog fires (TEST, "
             f"pooled): {int((sig.kind == 'ra').sum()):,}.\n")

    # panel base rates
    L.append(f"Panel all-days OOS base rates (median across eligible names): "
             f"MAE63 {float(p.null_oos_mae_med.median()):+.2f}%, "
             f"within-5%-of-low {float(p.null_oos_w5_rate.median()):.1f}%, "
             f"called-low {float(p.null_oos_called_rate.median()):.1f}%.\n")

    # grid table
    L.append("## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level "
             "medians (no gate)\n")
    L.append("No per-name best-of-grid selection (DNR §2). Primary cell = "
             f"(z={ZTHR_PRIMARY}, betawin={BW_PRIMARY}). Point estimates are panel "
             "medians of per-name uplifts; the CI/inference rows are the pooled month-"
             "cluster bootstrap on the primary cell below.\n")
    L.append("| cell | n names | U_MAE | U_W5 | median OOS fires/name |")
    L.append("|---|---|---|---|---|")
    for (z, bw) in GRID:
        um = f"umae_oos_z{z}_bw{bw}"; uw = f"uw5_oos_z{z}_bw{bw}"; nn = f"n_oos_z{z}_bw{bw}"
        star = " ★" if (z, bw) == (ZTHR_PRIMARY, BW_PRIMARY) else ""
        nser = p[nn][p[nn] > 0] if nn in p else pd.Series(dtype=float)
        L.append(f"| z={z}, betawin={bw}{star} | {int(p[um].notna().sum())} | "
                 f"{float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp | "
                 f"{int(nser.median()) if len(nser) else 0} |")

    # eras for primary cell
    L.append("\n### Primary cell across eras (full TEST / 2021+ sub-window), no gate\n")
    L.append("| era | U_MAE | U_W5 |")
    L.append("|---|---|---|")
    pk = f"z{ZTHR_PRIMARY}_bw{BW_PRIMARY}"
    for era, suf in (("full TEST ≥2020-07", "oos"), ("2021+ ≥2021-01", "oos21")):
        L.append(f"| {era} | {float(p[f'umae_{suf}_{pk}'].median()):+.2f}pp | "
                 f"{float(p[f'uw5_{suf}_{pk}'].median()):+.2f}pp |")

    # gate-variant columns (primary cell): RAW / +C32
    L.append("\n## Gate variants on the primary cell (pre-stated column pair: RAW / "
             "+C32), name-level medians\n")
    L.append("RAW = no terminality gate. +C32 = decline-deceleration terminality "
             "gate (roc20 stopped making new lows while close ≤ 60d low + rolling-low "
             "slope flattening; copied verbatim from pss_f1_downvol).\n")
    L.append("| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS |")
    L.append("|---|---|---|---|---|---|")
    for gate, lab in (("raw", "RAW (no gate)"), ("c32", "+C32")):
        um = f"umae_oos_{gate}"; uw = f"uw5_oos_{gate}"
        um21 = f"umae_oos21_{gate}"; uw21 = f"uw5_oos21_{gate}"
        nn = f"n_oos_{gate}"
        nnames = int((p.get(nn, pd.Series(dtype=float)) >= 1).sum()) if nn in p else 0
        L.append(f"| {lab} | {float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp "
                 f"| {float(p[um21].dropna().median()):+.2f}pp | "
                 f"{float(p[uw21].dropna().median()):+.2f}pp | {nnames} |")

    # inference CIs vs BOTH nulls
    L.append("\n## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls\n")
    L.append("Per-name-first collapse then cross-name median (matches the F1/F2/W1-T "
             "machinery — the F1 E1 sign-flip bug is NOT repeated): within each "
             "month-cluster draw, U_MAE = name-median mae63 − name all-days median, "
             "U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN "
             "the cross-name median. Two nulls: (a) all-DAYS base rate [inside the "
             "per-name uplift], (b) the RAW-RETURN ANALOG (identical construction on "
             "raw returns/drawdown — the residualization-adds-nothing mirror placebo). "
             "The F3 − raw-analog diff is PAIRED on the same resampled month-clusters.\n")
    L.append(f"Self-check (F1 E1 guard): direct per-name-median U_W5 = F3 "
             f"{dchk_f3:+.2f}pp / raw-analog {dchk_ra:+.2f}pp; the bootstrap point "
             f"estimates below must match these within bootstrap noise.\n")
    L.append("| quantity | full TEST | 2021+ |")
    L.append("|---|---|---|")
    rows = [
        ("F3 U_MAE (vs all-days null), no gate", "f3_umae"),
        ("F3 U_W5 (vs all-days null), no gate", "f3_uw5"),
        ("F3 U_MAE, +C32", "f3c_umae"),
        ("F3 U_W5, +C32", "f3c_uw5"),
        ("raw-return-analog U_MAE (residualization-adds-nothing null)", "ra_umae"),
        ("raw-return-analog U_W5 (residualization-adds-nothing null)", "ra_uw5"),
        ("F3 − raw-analog  U_MAE (FALSIFIER, paired)", "d_umae"),
        ("F3 − raw-analog  U_W5 (FALSIFIER, paired)", "d_uw5"),
    ]
    for lab, key in rows:
        L.append(f"| {lab} | {ci_str(ci.get(key))} {verdict(ci.get(key))} | "
                 f"{ci_str(ci21.get(key))} {verdict(ci21.get(key))} |")
    L.append("\nThe FALSIFIER rows are the pre-stated kill: if F3 − raw-return-analog "
             "does NOT exclude 0 (positive) on U_MAE/U_W5, beta-stripping the residual "
             "carries no incremental information over the raw-price analog, and F3 "
             "dies as a standalone construction. Printed regardless of outcome.\n")

    # overlap census
    L.append("## Overlap / disjointness census — F3 vs raw-return analog (primary "
             "cell, TEST)\n")
    L.append("The whole F3 claim is that the residual turns up WHILE the raw price is "
             "still falling — so F3 fires are NOT a subset of raw-turn days; the "
             "placebo is a matched-construction counterfactual, not a disjoint "
             "complement.\n")
    if {"ov_both", "ov_f3only", "ov_raonly"}.issubset(p.columns):
        b = int(p.ov_both.sum()); fo = int(p.ov_f3only.sum()); no = int(p.ov_raonly.sum())
        tf3 = max(b + fo, 1)
        L.append(f"- BOTH F3 & raw-analog: {b:,} · F3-only (raw price still ≤ recent "
                 f"high at fire): {fo:,} ({fo / tf3:.0%} of F3 fires) · raw-analog-only: "
                 f"{no:,}.")
        L.append(f"- F3-only share reflects how often the residual leads before the "
                 f"raw price turns (the pre-registered mechanism); the raw analog is a "
                 f"genuine matched counterfactual, not a subset.\n")

    # MECHANISM: R²-tercile fire concentration
    L.append("## Mechanism test — F3 fire concentration across the name's own R² "
             "terciles (charter falsifier prong 4)\n")
    L.append("PRE-STATED: residual-lead should CONCENTRATE in the LOWER (idiosyncratic) "
             "R² tercile. If fires cluster in the HIGH-R² (systemic) tercile, the "
             "mechanism is dead. R² = trailing name–sector regression R² (PIT) at each "
             "fire; terciles cut per name on that name's own valid-day R² distribution, "
             "then summed across names.\n")
    if {"mech_low", "mech_mid", "mech_high"}.issubset(p.columns):
        lo = int(p.mech_low.fillna(0).sum()); mi = int(p.mech_mid.fillna(0).sum())
        hi = int(p.mech_high.fillna(0).sum())
        tt = max(lo + mi + hi, 1)
        L.append("| R² tercile (per name) | F3 fires | share |")
        L.append("|---|---|---|")
        L.append(f"| LOW R² (idiosyncratic) | {lo:,} | {lo / tt:.0%} |")
        L.append(f"| MID R² | {mi:,} | {mi / tt:.0%} |")
        L.append(f"| HIGH R² (systemic) | {hi:,} | {hi / tt:.0%} |")
        L.append(f"\nNames with a resolvable tercile split: "
                 f"{int(p.mech_low.notna().sum())}. The pre-stated direction is "
                 f"LOW-tercile concentration; the observed split is above (reported "
                 f"regardless of outcome).\n")

    # earliness vs incumbent AND vs raw-analog + MAE-to-trough vs incumbent
    L.append("## Earliness — F3 vs incumbent (Stoch-RSI<20 @ derived rung) AND vs "
             "raw-return analog (SAME names)\n")
    L.append("td_to_trough: negative = trough BEFORE the fire (late confirmer); "
             "positive = fire BEFORE the trough (pre-trough / early). Per-name medians "
             "over TEST, then panel median of those. Charter hard requirement: F3 "
             "median td_to_trough must be STRICTLY earlier than BOTH the incumbent AND "
             "the raw-analog, else the 'pre-trough' claim is RETRACTED to at/post.\n")
    bi = p[np.isfinite(p.f3_tdt_med) & np.isfinite(p.inc_tdt_med)]
    bn = p[np.isfinite(p.f3_tdt_med) & np.isfinite(p.ra_tdt_med)]
    L.append("| comparison | n names | F3 median tdt | other median tdt | "
             "F3 − other (per-name median) | strictly earlier? |")
    L.append("|---|---|---|---|---|---|")
    if len(bi):
        d = float((bi.f3_tdt_med - bi.inc_tdt_med).median())
        L.append(f"| vs incumbent | {len(bi)} | {float(bi.f3_tdt_med.median()):+.1f}td "
                 f"| {float(bi.inc_tdt_med.median()):+.1f}td | {d:+.1f}td | "
                 f"{'YES' if d > 0 else 'NO'} |")
    if len(bn):
        d = float((bn.f3_tdt_med - bn.ra_tdt_med).median())
        L.append(f"| vs raw-analog | {len(bn)} | {float(bn.f3_tdt_med.median()):+.1f}td "
                 f"| {float(bn.ra_tdt_med.median()):+.1f}td | {d:+.1f}td | "
                 f"{'YES' if d > 0 else 'NO'} |")
    L.append("")
    # MAE-to-trough vs incumbent (charter falsifier prong 3): F3 must be SHALLOWER
    L.append("### MAE-to-trough vs incumbent (charter falsifier prong 3: F3 must be "
             "SHALLOWER)\n")
    bm = p[np.isfinite(p.f3_mae_med) & np.isfinite(p.inc_mae_med)]
    if len(bm):
        d = float((bm.f3_mae_med - bm.inc_mae_med).median())
        L.append(f"- F3 median mae63 (TEST, {len(bm)} names): "
                 f"{float(bm.f3_mae_med.median()):+.2f}% · incumbent median mae63: "
                 f"{float(bm.inc_mae_med.median()):+.2f}% · F3 − incumbent (per-name "
                 f"median): {d:+.2f}pp (positive = F3 SHALLOWER adverse excursion = "
                 f"better entry; the pre-stated requirement).")
    bmr = p[np.isfinite(p.f3_mae_med) & np.isfinite(p.ra_mae_med)]
    if len(bmr):
        dr = float((bmr.f3_mae_med - bmr.ra_mae_med).median())
        L.append(f"- vs raw-analog: F3 − raw-analog median mae63 (per-name median, "
                 f"{len(bmr)} names): {dr:+.2f}pp.\n")

    # 2022 containment
    L.append("## 2022-class containment (primary cell fire counts): RAW / +C32\n")
    L.append("Charter STRUCTURAL claim: F3 CANNOT fire the 2022 pattern BY "
             "CONSTRUCTION (2022 mega-cap troughs were SYSTEMIC — high R², residual "
             "not leading — so the disagreement gate stays shut). PREDICTION: H1-2022 "
             "fires ≈ 0 on the systemic names (KO, PG, MSFT in macro flushes). "
             "META/NVDA/PG are OFF-PANEL (W1 eligibility) — run from raw OHLCV, "
             "flagged. `H1 R²` = median trailing name–sector R² at the H1-2022 fires "
             "(high → systemic regime, the mechanism-off condition).\n")
    L.append("| name | class | H1-2022 (raw / +C32) | ±21td 2022-low (raw / +C32) | "
             "H1 R² | name R² (TEST med) |")
    L.append("|---|---|---|---|---|---|")
    panel_syms = set(panel["sym"])
    secmap_full = pd.read_parquet(SECMAP_PQ).drop_duplicates("ticker", keep="first")
    secmap_full = secmap_full.set_index("ticker")["sector"].map(GICS_ETF)
    for sym in FOCUS_2022:
        etf = secmap_full.get(sym)
        rung = codex.get(sym)
        cls = "idiosyncratic" if sym in IDIO else "systemic (expected silent)"
        flag = "" if sym in panel_syms else " (off-panel)"
        if not isinstance(etf, str):
            L.append(f"| {sym}{flag} | {cls} | no sector map | — | — | — |")
            continue
        cc = containment_counts(sym, etf, rung)
        if cc is None:
            L.append(f"| {sym}{flag} ({etf}) | {cls} | unmeasurable | — | — | — |")
        else:
            r2h = f"{cc['h1_r2_med']:.2f}" if np.isfinite(cc['h1_r2_med']) else "—"
            r2t = f"{cc['r2_test_med']:.2f}" if np.isfinite(cc['r2_test_med']) else "—"
            L.append(f"| {sym}{flag} ({etf}) | {cls} | {cc['h1_raw']} / {cc['h1_c32']} | "
                     f"{cc['near_raw']} / {cc['near_c32']} | {r2h} | {r2t} |")
    L.append("\nIf F3 fires heavily into H1-2022 on the systemic names, the by-"
             "construction containment claim is FALSE (reported regardless).\n")

    # product split (descriptive)
    L.append("## Product split (descriptive; calls-low vs confirms-reset)\n")
    f3o = sig[sig.kind == "f3"]
    if len(f3o):
        called = float(((f3o.tdt >= -2) & (f3o.tdt <= 5)).mean() * 100)
        conf = float((f3o.tdt < -2).mean() * 100)
        early = float((f3o.tdt > 5).mean() * 100)
        L.append(f"F3 primary-cell TEST fires (n={len(f3o):,}): near-low (−2..+5td) "
                 f"{called:.0f}% · confirmed-reset (<−2td) {conf:.0f}% · early (>+5td) "
                 f"{early:.0f}% · median td_to_trough {float(f3o.tdt.median()):+.0f}td.\n")

    # what was found (no verdict language)
    L.append("## What was found (no verdict — the commissioning session rules)\n")
    f3_full = ci.get("f3_umae"); d_full = ci.get("d_umae"); dw_full = ci.get("d_uw5")
    L.append(f"- F3 (no gate) U_MAE vs the all-days null on full TEST: {ci_str(f3_full)} "
             f"({verdict(f3_full)}); U_W5 {ci_str(ci.get('f3_uw5'))} "
             f"({verdict(ci.get('f3_uw5'))}).")
    L.append(f"- The pre-stated FALSIFIER (F3 − raw-return analog, residualization-"
             f"adds-nothing): U_MAE {ci_str(d_full)} ({verdict(d_full)}), U_W5 "
             f"{ci_str(dw_full)} ({verdict(dw_full)}) on full TEST; 2021+ U_MAE "
             f"{ci_str(ci21.get('d_umae'))} ({verdict(ci21.get('d_umae'))}), U_W5 "
             f"{ci_str(ci21.get('d_uw5'))} ({verdict(ci21.get('d_uw5'))}).")
    L.append("- The mechanism R²-tercile concentration table, the +C32 gate column, "
             "the earliness-vs-incumbent AND earliness-vs-raw-analog tables, the "
             "MAE-to-trough-vs-incumbent read, and the 2022 containment counts above "
             "are the pre-registered conditioner / falsifier reads. All nulls are "
             "printed. The earliness claim is graded honestly; if F3 is not strictly "
             "earlier than BOTH the incumbent and the raw-analog, the 'pre-trough' "
             "claim is retracted (strictly-earlier? = NO in the earliness table).\n")

    # limitations
    L.append("## Limitations\n")
    L.append("- Closes-only MAE/troughs (house shadow-book form); intraday lows are "
             "deeper. Comparable across cells/variants, not absolute.")
    L.append("- Name (baskets/ohlcv) and sector ETF (yahoo) are BOTH total-return "
             "adjusted, so the beta regression is on a consistent scale (log returns "
             "are level-invariant); the two series are inner-joined on common trading "
             "dates before differencing.")
    L.append("- XLRE (from 2015-10) and XLC (from 2018-06) have short FIT-era history; "
             "names mapped there have fewer FIT-era residual bars — a coverage matter, "
             "reflected in the census, not silently defaulted.")
    L.append("- Sector mapping is the CURRENT GICS membership (ticker_sectors); a name "
             "that changed GICS sector historically is mapped by its current sector "
             "(the top-20 sector_holdings snapshot agrees on shared names). A name with "
             "no GICS map is excluded, never defaulted to SPY (that is the market-"
             "residual SECONDARY, a different mechanism).")
    L.append("- Survivor tape (data/baskets/ohlcv holds today's listings); per-name "
             "own-baseline netting removes level bias, not composition bias.")
    L.append("- ±31td proximity window is the §7 pin; long bear legs make 'the low' "
             "window-relative. The raw-return analog shares this window (fair test).")
    L.append("- The residual is beta-stripped vs the sector ETF; residual mean-reversion "
             "(residual rho ladder) is the measurement axis, not an event fit.")
    L.append("- META/NVDA/PG are off the W1 panel (W1 eligibility); the containment "
             "diagnostic runs them as raw-OHLCV exhibits, flagged.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    keep = [cc for cc in p.columns if not cc.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} "
          f"({len(p)} eligible names, {len(exc)} excluded)")


if __name__ == "__main__":
    main()
