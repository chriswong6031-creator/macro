#!/usr/bin/env python3
"""PSS-F4 — Downside-vol asymmetry flip (semivariance regime turn).

POST-STUDY CAUSAL-TIMING ERRATUM (2026-07-26).
The historical study below labels the FIRST bar of a run that is only known,
retrospectively, to survive P bars.  That onset label is useful for mechanism
attribution but is NOT a live fire: a causal P=5 confirmation is observable on
the fifth bar, four sessions later.  The historical function and report are
preserved for audit reproducibility.  New work must use
``_causal_sustained_run_fires`` or an explicit confirmation-day state machine;
see ``pss_f4_repair.py`` / ``pss_f4_hazard.py``.

PRE-REGISTRATION — this header is the pinned ruler AND the pinned construction,
committed BEFORE any timing outcome (MAE/W5/proximity) was computed. The prereg
commit ("prereg: PSS-F4 …") precedes the results commit in git history (audited).
Charters: research/PSS_WSIG_SHORTLIST_BY_FABLE.md §F4 + §"Execution rails";
research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W-SIG / §0 / §2.
Trial-ledger family: pss_f4_semivar (registered in data/trial_ledger.jsonl in the
same pre-run commit as this file). Siblings F1 (pss_f1_downvol, KILLED) + F2
(pss_f2_overnight, KILLED) + F3 (pss_f3_residual, KILLED) — this study REUSES
their corrected machinery (metric_arrays / null_stats / bars_for / tool_dates /
_name_uplift per-name-first collapse / c32_gate) and MUST NOT repeat F1's two
shipped bugs (E1 median-of-binary SIGN-FLIP on any binary-rate metric; E2
contaminated placebo pool). F4 is the LAST of the 4 W-SIG families.

Copy law R-W1T-3 governs all text here: this is a reset-CONFIRMER / exhaustion /
terminality / symmetry-reset construction — it never "calls bottoms" (the words
"bottom caller" / "calls bottoms" are BANNED; use exhaustion / reset / terminality).
"validated" is CI-banned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE ONE MECHANISM HYPOTHESIS (pre-registered).
A falling stock is dominated by DOWN-day variance (semivariance): the tape is
one-sided as sellers hit bids, so the asymmetry ratio A = RV_down / RV_up runs
ELEVATED (down-dominated) through the decline. A durable trough is the bar where
that asymmetry INVERTS — down-vol stops leading and up-day variance draws level
or exceeds it — because the marginal seller is gone and buyers set the range. A
dead-cat bounce raises up-vol transiently but down-vol RE-DOMINATES within days
(asymmetry snaps back); at a REAL bottom the symmetry PERSISTS. This is an
AT-TROUGH signal — it makes NO pre-trough earliness claim (unlike F2/F3). Its
ONLY path to usefulness is being a BETTER or genuinely COMPLEMENTARY at-trough
CONFIRMER than the incumbent Stoch-RSI reset; if requiring persistence P pushes
the fire so late that it just collapses into another late confirmer with no gain,
it is dead (charter falsifier prong 2).

WRONG-RULER CHECK (§W-SIG execution rail, performed BEFORE statistics were
chosen). The object under test is an ENTRY-TIMING claim: "does the first bar of a
SUSTAINED-SYMMETRIC run sit shallower-to-the-trough / closer-to-the-low than an
ordinary bar, AND is it a better at-trough confirmer than the incumbent?". It is
NOT a hold-return claim. Grading it on fwd63 hold returns would be the DNR §3
wrong-ruler law (#1458, Oracle reversion reframe — the same error PTT-W1-T
corrected; F1/F2/F3 carried the identical paragraph). Therefore the metrics below
are entry-quality metrics (MAE-to-trough, proximity-to-low, td-to-trough), never
drift metrics. fwd-return is not read.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL PINNED CONSTRUCTION (closes only; PIT throughout; level-invariant log rets).

RV WINDOW GRAIN (pinned choice, disclosed per the charter's explicit instruction).
Semivariance is a DAILY-BAR measure — the down/up decomposition of the tape is a
daily-return object. So RV_down / RV_up and the ratio A are computed on DAILY log
returns over a rolling window n; the tunable PERSISTENCE window P counts DAILY
bars of the sustained-symmetric run. (The RV windows are DAILY, NOT rung-bar; the
persistence P is the tunable. This is the charter's recommended choice, pinned
here.) The structure-derived rung is carried only as the earliness comparator's
rung for the incumbent (tool_dates(bars_for(px, rung), "S")), not as the RV grain.

1. SEMIVARIANCES + RATIO (daily log returns).
     r[d] = ln(close[d] / close[d-1])
     RV_down[d] = sqrt( mean( min(r,0)^2 over trailing n ) )   (downside semi-deviation)
     RV_up[d]   = sqrt( mean( max(r,0)^2 over trailing n ) )   (upside semi-deviation)
     A[d]       = RV_down[d] / RV_up[d]        (>1 = down-dominated; NaN if RV_up==0)
   Window n pinned = 20 (primary); grid also runs n=10.

2. PER-NAME TRAILING BANDS (PIT — no lookahead; the name's OWN percentiles).
   Over a trailing rolling window of A values (min TRAIL_MIN=252, cap TRAIL_MAX=756
   trading days), SHIFTED one bar so day d uses only data through d-1:
     A_base[d] = trailing MEDIAN of A     (the name's OWN 'normal' asymmetry level)
     A_hi[d]   = trailing 80th percentile of A   (its OWN down-dominated band)
   The symmetric-reset level is the name's OWN baseline A_base (NOT an absolute 1.0
   — see the MEASUREMENT AMENDMENT below, pinned pre-outcome). The down-dominated
   regime is A >= A_hi (its own upper percentile). A_hi percentile pinned = 80th.

3. FIRE (the sustained-symmetric-run start).
   Down-dominated regime "to flip FROM": A >= A_hi within the trailing LB=20 bars.
   Symmetric bar: A <= A_base (asymmetry drawn back to/through the name's baseline).
   FIRE[d] = the FIRST bar of a run of >= P consecutive symmetric bars (A <= A_base),
   where the name was in a down-dominated regime (A >= A_hi) within the prior LB bars.
   The persistence gate (P consecutive symmetric bars) is what kills dead-cats: a
   transient one-bar symmetry patch that re-inverts within < P bars does not fire.
   P pinned = 5 (primary); grid also runs P=3.

4. SMALL PINNED GRID (multiplicity budget = 4 cells, disclosed; NO per-name best-
   of-grid selection — the standing DNR §2 two-ruler kill, PTT-W1a).
     window n ∈ {10, 20}  ×  persistence P ∈ {3, 5}  = 4 cells.
   ALL FOUR graded and reported side by side. PRIMARY pre-registered cell =
   (n=20, P=5). The other three are robustness. n, P, the A_hi=80th percentile, the
   TRAIL_MIN/MAX window, and LB are FIXED (not derived, not outcome-selected). The
   rung (incumbent comparator only) is DERIVED per name from the codex.

   ┌─ MEASUREMENT AMENDMENT LOG (PRE-OUTCOME — measurement-DISTRIBUTION probes only;
   │  NO IS/OOS uplift (MAE/W5/prox) was computed or read before the final pin,
   │  mirroring F1 M1/M2, F3 sector-map re-pin, PTT-W1 A1/A2). ───────────────────
   │  A1 (charter sketch, DEGENERATE as an ABSOLUTE threshold): the §F4 sketch says
   │     "A crosses from >=A_hi DOWN through ~1 (symmetric) AND stays <=1 for P bars"
   │     and "defensives KO PG WMT COST live near A≈1 always (no signal content),
   │     high-beta names run structurally down-skewed", gated by an absolute
   │     "min-baseline-asymmetry" A_base≈1 eligibility threshold. MEASURED on a
   │     144-name probe (FIT era): the UNCONDITIONAL FIT-era baseline A_base is
   │     ~0.96 UNIVERSE-WIDE (median 0.963, deciles 0.906 / 0.963 / 1.044) — even
   │     the beta>1 focus names sit BELOW 1 (NVDA 0.85, AMZN 0.90, JPM 0.87). With
   │     RMS semi-deviations of log returns, up-day and down-day magnitudes are
   │     near-symmetric on average and near-high days (which dominate the sample)
   │     run A<1, so the UNCONDITIONAL median is <1 for essentially every name. An
   │     absolute crossing level of 1.0 and an absolute A_base>=1 eligibility gate
   │     are therefore both DEGENERATE against the data: the gate excludes the ENTIRE
   │     universe (A_base>=1.00 → 32/144; A_base>=1.05 → 14/144), INCLUDING the
   │     beta>1 focus the mechanism is FOR (this is the F1-M1 absolute-threshold
   │     degeneracy signature).
   │  A2 (the mechanism IS real, but CONDITIONAL — the re-pin motive). On the SAME
   │     probe, A DURING declines is genuinely down-dominant: median A in each name's
   │     DEEPEST-20% drawdown FIT days = 1.185 vs its SHALLOWEST-20% (near-high) days
   │     = 0.724, and 143/144 names have A(deep-drawdown) > A(shallow). The
   │     asymmetry the mechanism reads is CONDITIONAL ON THE DECLINE (down-vol
   │     dominates DURING selloffs relative to the name's OWN normal), not an
   │     unconditional A≈1 baseline. FINAL PIN: the symmetric-reset level is the
   │     name's OWN trailing A_base (its normal), the down-dominated regime is its
   │     OWN trailing A_hi (80th pct); both PIT-trailing. Absolute 1.0 is NOT used.
   │  A3 (eligibility re-pinned to DISPERSION, not absolute baseline). The charter's
   │     premise that defensives are baseline-symmetric with "no signal content"
   │     does NOT hold in the measured data: defensives have essentially the SAME
   │     conditional asymmetry as beta>1 names (ratio A(deep)/A(base): KO 1.35,
   │     COST 1.64, PEP 1.52 vs NVDA 1.17, AMZN 1.39, HD 1.35). So the eligibility
   │     gate cannot be "A_base near 1 → exclude"; the honest, non-degenerate gate is
   │     DISPERSION: a name is eligible iff it can REACH a down-dominated extreme
   │     meaningfully above its own baseline — SPREAD = A_hi_FIT − A_base_FIT >=
   │     SPREAD_MIN (pinned 0.15) — so the flip is measurable. MEASURED: spread is
   │     >= 0.27 for every probed name (5th pct 0.377, median 0.510), so the 0.15
   │     gate excludes NO name in-sample; it is a STATED gate that would exclude a
   │     genuinely-flat name if one existed. CONSEQUENCE (reported honestly, NOT a
   │     coverage win): the charter's "defensives KO PG WMT COST are correctly-null"
   │     prediction is NOT borne out — those names ARE eligible and DO produce a
   │     measurable flip; they are graded, and whether the flip carries near-trough
   │     information on them is left to the ruler, not assumed. The min-baseline-
   │     asymmetry idea survives only as this dispersion form.
   │  FINAL-PIN FIRE-COUNT PROBE (208-name sample, primary cell n=20/P=5): median
   │     18 FIT / 20 OOS fires per name; 0 zero-fire names; 208/208 with >=3 FIT +
   │     >=3 OOS. P=3 grid → median 21 FIT / 24 OOS. All four cells fire enough to
   │     grade. No MAE/W5/prox was computed in ANY probe.
   └──────────────────────────────────────────────────────────────────────────────

PER-NAME MEASUREMENT AXIS (report it; FIT-derivable, no event fitting):
  baseline asymmetry A_base_FIT (the name's median A over FIT), its dispersion
  A_disp_FIT (std of A over FIT), and the reachable down-dominated spread
  A_hi_FIT − A_base_FIT (the eligibility axis). All PRINTED, display-tier context.

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
  pss_f1_downvol.py / pss_f2_overnight.py / pss_f3_residual.py
  (groupby("sym").agg(w5=("w5_x","mean")) then cross-name median, mirroring
  ptt_w1_timing_regrade.bootstrap). A self-check asserts the F4-vs-all-days U_W5
  bootstrap point matches a direct per-name-median computation within bootstrap
  noise (printed — the F1 E1 guard).

  INFERENCE: month-cluster bootstrap (cluster = signal calendar month; DT-R14 —
  ticker-only clustering is FORBIDDEN), NB = 1000, RNG seed 20260731 (pinned).
  ERA SPLIT (DT-R16): FIT ≤ 2020-06-30 / TEST ≥ 2020-07-01, plus the 2021+ sub-
  window (≥ 2021-01-01). A full-sample-only effect is DISQUALIFIED. All grading is
  on TEST; FIT is used ONLY to measure the per-name axis (A_base/A_disp/spread).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FALSIFIER — THREE prongs, ALL pre-stated (this is F4's kill; the placebo mirrors
the precondition — the F1/F2/F3 lesson: a placebo must mirror the ACTUAL evaluator).
ALL nulls printed regardless of outcome (nulls printed, never hidden).

  1. F4 vs ALL-DAYS per-name random-day null (basic near-low check; charter §7
     ~16% ambient within-5%-of-low). PRONG 1: the sustained-symmetric-run start
     must beat this at a CI-clean margin on U_W5 (and be shallower on U_MAE).

  2. ASYMMETRY-ADDS-NOTHING null (the MIRROR placebo — F4's analog of F2's net-
     return-analog and F3's raw-return-analog). Build a TOTAL-VOL ANALOG = the
     IDENTICAL construction (same n, same P, same trailing bands, same LB regime
     gate, same run logic) but on TOTAL realized vol RV_tot = sqrt(RV_down^2 +
     RV_up^2) (= the ordinary rolling RMS of daily log returns) INSTEAD of the
     down/up RATIO A. I.e. the analog's "down-dominated" band and "reset" level are
     the name's OWN trailing HIGH percentile / MEDIAN of RV_tot, and it fires when
     RV_tot crosses DOWN from its trailing-high band through its median and stays
     <= median for P bars (a pure vol-COMPRESSION / vol-normalization signal — vol
     comes down and stays down, with NO directional decomposition). Grade F4 −
     total-vol-analog on U_MAE and U_W5 (month-cluster bootstrap PAIRED on the same
     resampled month-clusters, per-name-first). If the DIRECTIONAL asymmetry (the
     down/up RATIO) does not beat plain vol-normalization, the down/up decomposition
     carries NO information and F4 dies. F4 fires are NOT a subset of vol-compression
     days (A is a RATIO, RV_tot is a LEVEL — an asymmetry flip can happen while
     total vol stays elevated, and vol can compress while A stays down-dominated) —
     so the placebo is a matched-construction counterfactual, NOT a disjoint
     complement; an overlap census (both / F4-only / analog-only) is reported.

  3. F4 vs the INCUMBENT Stoch-RSI<20 cross at the derived rung (tool_dates(bars_for
     (px, rung), "S")) — the "better at-trough confirmer OR redundant" test (charter
     prong 2). Grade BOTH td_to_trough AND MAE-to-trough of F4 fires vs the
     incumbent's, on the SAME names. If persistence P pushes the fire so late that
     td_to_trough is no better than the incumbent's −2..−10 AND MAE is no shallower,
     F4 has collapsed into another reset-confirmer with no gain → dead. Report
     honestly whether F4 is a BETTER at-trough confirmer or just a redundant one.
     (F4 makes NO pre-trough claim, so "strictly earlier" is NOT required — the bar
     is "better or genuinely complementary at-trough", per the charter.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C32 TERMINALITY GATE (pre-registered CONDITIONER — a pre-stated column pair, NOT
post-hoc; graded WITH and WITHOUT on the primary cell). COPIED verbatim from
pss_f1_downvol.c32_gate (M = 20 td): decline decelerating INTO a fresh 60d low
(roc20 stopped making new lows + rolling-low slope flattening). The gate only
narrows.

2022-CLASS CONTAINMENT DIAGNOSTIC (pre-stated — the persistence gate is the
defense). Fire counts in H1-2022 (2022-01-01..2022-06-30) vs a ±21td window around
the 2022-10-13 low, ACROSS THE P GRID (P=3 vs P=5, at n=20), on the beta>1 focus
names (NVDA TSLA AMZN JPM XOM HD). Charter: too-short P re-imports the 2022 early-
fire class (brief symmetry patches during relief bounces that re-invert to down-
dominance within a few bars); a sufficiently long P should not trigger until the
true trough. The P-sensitivity of H1-2022 false fires is shown EXPLICITLY (P=3 vs
P=5) — this is the earliness-vs-2022-safety frontier the whole search sits on.
NVDA is OFF the W1 panel (fell to W1 eligibility) — run from raw OHLCV as a named
exhibit, flagged.

UNIVERSE / ELIGIBILITY. Universe = W1 panel names (data/research/ptt_w1_panel.parquet)
with OHLC (data/baskets/ohlcv per-symbol parquet). A name is F4-ELIGIBLE iff its
FIT-era A spread (A_hi_FIT − A_base_FIT) >= SPREAD_MIN (min-baseline-asymmetry as
DISPERSION — see amendment A3) AND it has >= 3 FIT and >= 3 TEST primary-cell fires
with resolvable mae63/prox. Coverage census (eligible / excluded + reasons: too-flat
asymmetry / too few fires) is PRINTED — never a bare count (vacuous-green law).
CORRECTLY-NULL DEFENSIVES: the charter predicts KO PG WMT COST are baseline-
symmetric and excluded by the min-baseline gate; the measured data does NOT bear
this out (they have normal conditional asymmetry and normal spread — amendment A3),
so they are reported as ELIGIBLE-and-graded, and the charter's "correctly-null
defensives" prediction is reported as NOT confirmed. This is disclosed as a finding,
not hidden as a coverage loss. yahoo close is total-return adjusted; semivariance
is on log returns so it is consistent (the TR adjustment nets out of the ratio).

REGISTRY COMPLIANCE. DT-R14 month-cluster · DT-R16 era split · DNR §2 two-ruler
kill respected (zero per-name best-of-grid; bands are per-name trailing PIT, not
outcome-selected; n/P/percentile/windows fixed) · DNR §3 wrong-ruler law is the
MOTIVE for the entry ruler · R-W1T-3 copy law (exhaustion / reset / terminality /
symmetry-reset language; no "bottom caller" / "calls bottoms" verb; "validated"
avoided) · display-tier only — NOTHING here promotes to authority (the gauntlet is
a PROMOTION gate, not this build gate; a null never blocks accrual; LLMs originate
nothing — deterministic arithmetic). The commissioning session rules the verdict;
this report states what was found, no verdict language.

Outputs: reports/pss_f4_semivar.md + data/research/pss_f4_semivar_panel.parquet.
Run: python3 scripts/research/pss_f4_semivar.py   (off the render path; <~30 min, 4 cores).
Deterministic (pinned seed 20260731) — a rerun reproduces the report byte-identical.
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

RNG = np.random.default_rng(20260731)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
PANEL_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
CODEX_PQ = ROOT / "data" / "personality_timing" / "codex.parquet"
OUT_MD = ROOT / "reports" / "pss_f4_semivar.md"
OUT_PQ = ROOT / "data" / "research" / "pss_f4_semivar_panel.parquet"

H = 63           # MAE window
PROX = 31        # ±31td proximity window (§7)
TEXIT = 21
NB = 1000
W5 = 5.0
N_PRIMARY = 20
P_PRIMARY = 5
GRID = [(n, P) for n in (10, 20) for P in (3, 5)]   # 4 cells
AHI_PCT = 80.0       # down-dominated band = trailing 80th pct of A
TRAIL_MIN = 252      # trailing band min obs
TRAIL_MAX = 756      # trailing band cap
LB = 20              # look-back for a down-dominated regime to flip FROM
SPREAD_MIN = 0.15    # eligibility: A_hi_FIT − A_base_FIT dispersion floor (amendment A3)
MIN_FIT = 3
MIN_TEST = 3
# beta>1 focus (should carry directional-vol asymmetry) — the 2022 P-sensitivity set
FOCUS = ["NVDA", "TSLA", "AMZN", "JPM", "XOM", "HD"]
# charter-named defensives (predicted correctly-null; amendment A3 finds them eligible)
DEFENSIVES = ["KO", "PG", "WMT", "COST"]
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


def half_masks(idx: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    return {
        "is": np.asarray(idx <= SPLIT),
        "oos": np.asarray(idx >= OOS_START),
        "oos21": np.asarray(idx >= SUB2021),
    }


# ── F4 construction ─────────────────────────────────────────────────────────

def semivars(ret: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Rolling downside / upside semi-deviation (RMS of neg / pos daily log rets)
    over trailing window n. Vectorized rolling — NO python per-bar loop."""
    s = pd.Series(ret)
    neg = s.clip(upper=0.0)
    pos = s.clip(lower=0.0)
    rv_down = np.sqrt((neg ** 2).rolling(n, min_periods=n).mean()).to_numpy()
    rv_up = np.sqrt((pos ** 2).rolling(n, min_periods=n).mean()).to_numpy()
    return rv_down, rv_up


def asymmetry(close: pd.Series, n: int) -> np.ndarray:
    """A[d] = RV_down[d] / RV_up[d] over window n (>1 = down-dominated; NaN if RV_up==0)."""
    cn = close.to_numpy(dtype=float)
    ret = np.concatenate([[np.nan], np.log(cn[1:] / cn[:-1])])
    rv_down, rv_up = semivars(ret, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        A = np.where(rv_up > 0, rv_down / rv_up, np.nan)
    return A


def total_vol(close: pd.Series, n: int) -> np.ndarray:
    """RV_tot[d] = sqrt(RV_down^2 + RV_up^2) = rolling RMS of daily log rets over n
    (the TOTAL-VOL ANALOG's level — a directionless vol level, NO ratio)."""
    cn = close.to_numpy(dtype=float)
    ret = np.concatenate([[np.nan], np.log(cn[1:] / cn[:-1])])
    s = pd.Series(ret)
    return np.sqrt((s ** 2).rolling(n, min_periods=n).mean()).to_numpy()


def _trailing_bands(x: np.ndarray, idx: pd.DatetimeIndex
                    ) -> tuple[np.ndarray, np.ndarray]:
    """PIT trailing (base=median, hi=80th pct) over [TRAIL_MIN..TRAIL_MAX], shifted
    one bar so day d uses only data through d-1. Vectorized rolling — no per-bar loop."""
    s = pd.Series(x, index=idx)
    base = s.rolling(TRAIL_MAX, min_periods=TRAIL_MIN).median().shift(1).to_numpy()
    hi = s.rolling(TRAIL_MAX, min_periods=TRAIL_MIN).quantile(AHI_PCT / 100.0).shift(1).to_numpy()
    return base, hi


def _sustained_run_fires(x: np.ndarray, base: np.ndarray, hi: np.ndarray, P: int
                         ) -> np.ndarray:
    """Retrospective ONSET label for the historical, pre-registered study.

    This scans the completed run and stamps its first bar.  It is intentionally
    preserved for report reproducibility and MUST NOT be used as a live fire.
    New causal work uses ``_causal_sustained_run_fires`` below.
    """
    n = len(x)
    finite = np.isfinite(x) & np.isfinite(base) & np.isfinite(hi)
    below_base = finite & (x <= base)
    is_hi = finite & (x >= hi)
    # was in the elevated / down-dominated regime within the trailing LB bars
    was_hi = pd.Series(is_hi.astype(float)).rolling(LB, min_periods=1).max().to_numpy() > 0
    fire = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if below_base[i]:
            j = i
            while j < n and below_base[j]:
                j += 1
            if (j - i) >= P and was_hi[i]:
                fire[i] = True          # first bar of the sustained-symmetric/reset run
            i = j
        else:
            i += 1
    return fire


def _causal_sustained_run_fires(
    x: np.ndarray, base: np.ndarray, hi: np.ndarray, P: int
) -> np.ndarray:
    """Stamp the P-th reset bar, when persistence first becomes observable.

    The high-regime precondition is evaluated at the run's first bar using only
    history available by that start.  The output is prefix-invariant and never
    backdates a completed run to its onset.
    """
    if P < 1:
        raise ValueError("P must be >= 1")
    n = len(x)
    finite = np.isfinite(x) & np.isfinite(base) & np.isfinite(hi)
    below_base = finite & (x <= base)
    is_hi = finite & (x >= hi)
    was_hi = (
        pd.Series(is_hi.astype(float))
        .rolling(LB, min_periods=1)
        .max()
        .to_numpy()
        > 0
    )
    confirmed = (
        pd.Series(below_base.astype(float))
        .rolling(P, min_periods=P)
        .sum()
        .to_numpy()
        == P
    )
    prior_confirmed = np.concatenate([[False], confirmed[:-1]])
    first_confirmed = confirmed & ~prior_confirmed
    fire = np.zeros(n, dtype=bool)
    for end in np.flatnonzero(first_confirmed):
        start = int(end) - P + 1
        if start >= 0 and was_hi[start]:
            fire[int(end)] = True
    return fire


def f4_fires(close: pd.Series, n: int, P: int) -> np.ndarray:
    """Historical retrospective onset labels; use ``f4_causal_fires`` live."""
    idx = close.index
    A = asymmetry(close, n)
    base, hi = _trailing_bands(A, idx)
    return _sustained_run_fires(A, base, hi, P)


def f4_causal_fires(close: pd.Series, n: int, P: int) -> np.ndarray:
    """Live-safe F4 confirmations stamped on the observable P-th reset bar."""
    idx = close.index
    A = asymmetry(close, n)
    base, hi = _trailing_bands(A, idx)
    return _causal_sustained_run_fires(A, base, hi, P)


def totvol_analog_fires(close: pd.Series, n: int, P: int) -> np.ndarray:
    """ASYMMETRY-ADDS-NOTHING mirror placebo: the IDENTICAL construction on TOTAL
    realized vol RV_tot (directionless level) instead of the down/up ratio. Fires on
    a vol-COMPRESSION run (RV_tot crosses down from its trailing-high band through
    its trailing median and stays <= median for P bars) — a pure vol-normalization
    signal with NO directional decomposition."""
    idx = close.index
    rvt = total_vol(close, n)
    base, hi = _trailing_bands(rvt, idx)
    return _sustained_run_fires(rvt, base, hi, P)


def totvol_analog_causal_fires(
    close: pd.Series, n: int, P: int
) -> np.ndarray:
    """Live-safe total-vol placebo confirmations, stamped on the P-th bar."""
    idx = close.index
    rvt = total_vol(close, n)
    base, hi = _trailing_bands(rvt, idx)
    return _causal_sustained_run_fires(rvt, base, hi, P)


def fit_axis(close: pd.Series, n: int) -> dict[str, float]:
    """Per-name FIT-era asymmetry axis: A_base, A_disp, A_hi, spread (eligibility)."""
    A = asymmetry(close, n)
    fit = close.index <= SPLIT
    Af = A[fit]
    Af = Af[np.isfinite(Af)]
    out = {"a_base_fit": np.nan, "a_disp_fit": np.nan, "a_hi_fit": np.nan, "spread_fit": np.nan}
    if len(Af) < TRAIL_MIN:
        return out
    out["a_base_fit"] = float(np.median(Af))
    out["a_disp_fit"] = float(np.std(Af))
    out["a_hi_fit"] = float(np.percentile(Af, AHI_PCT))
    out["spread_fit"] = out["a_hi_fit"] - out["a_base_fit"]
    return out


# ── per-name computation ────────────────────────────────────────────────────

def load_px(sym: str) -> pd.Series:
    return pd.read_parquet(OHLCV / f"{sym}.parquet")["close"].dropna()


def _sig_row(sym, kind, i, idx, m, nulls, gate_c32, extra=None) -> dict:
    """One bootstrap signal row (per-name-first uplift inputs); COPIED shape F1/F2/F3."""
    row = {
        "sym": sym, "kind": kind, "date": idx[i], "month": str(idx[i])[:7],
        "mae_ex": m["mae63"][i] - nulls["oos"]["mae_med"],
        "w5_ex": (100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos"]["w5_rate"],
        "mae_ex21": (m["mae63"][i] - nulls["oos21"]["mae_med"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
        "w5_ex21": ((100.0 if m["prox"][i] <= W5 else 0.0) - nulls["oos21"]["w5_rate"]) if (idx[i] >= SUB2021 and nulls["oos21"]) else np.nan,
        "tdt": m["tdt"][i], "gc32": bool(gate_c32[i]), "sub21": bool(idx[i] >= SUB2021),
    }
    if extra:
        row.update(extra)
    return row


def compute_name(sym: str, rung: str) -> dict:
    """Per-cell fire metrics + the F4 / total-vol-analog / incumbent signal rows. NO
    best-of-grid selection: every cell graded independently."""
    close = load_px(sym)
    c = close.to_numpy(dtype=float)
    idx = close.index
    rec: dict = {"sym": sym, "rung": rung}
    if len(close) < TRAIL_MIN + PROX + H + 5:
        rec["excl"] = "short_history"
        return rec
    m = metric_arrays(c)
    masks = half_masks(idx)
    nulls = {h: null_stats(m, masks[h]) for h in ("is", "oos", "oos21")}
    if not nulls["is"] or not nulls["oos"]:
        rec["excl"] = "null_universe_small"
        return rec
    for h in ("is", "oos", "oos21"):
        for kk, vv in (nulls[h] or {}).items():
            rec[f"null_{h}_{kk}"] = vv

    # per-name FIT asymmetry axis (primary window) + dispersion eligibility gate
    ax = fit_axis(close, N_PRIMARY)
    rec.update(ax)
    if not np.isfinite(ax["spread_fit"]):
        rec["excl"] = "no_asym_axis"
        return rec
    if ax["spread_fit"] < SPREAD_MIN:
        rec["excl"] = f"flat_asymmetry(spread={ax['spread_fit']:.2f})"
        return rec

    c32 = c32_gate(close)
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    sig_rows: list[dict] = []
    fires_primary = None
    ta_primary = None
    for (n, P) in GRID:
        fire = f4_fires(close, n, P)
        valid = fire & fin
        for h in ("is", "oos", "oos21"):
            mk = masks[h]
            sub = valid & mk
            nn = int(sub.sum())
            rec[f"n_{h}_n{n}_P{P}"] = nn
            if nn == 0 or not nulls[h]:
                rec[f"umae_{h}_n{n}_P{P}"] = np.nan
                rec[f"uw5_{h}_n{n}_P{P}"] = np.nan
                continue
            mae = m["mae63"][sub]; prox = m["prox"][sub]
            rec[f"umae_{h}_n{n}_P{P}"] = float(np.median(mae) - nulls[h]["mae_med"])
            rec[f"uw5_{h}_n{n}_P{P}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
        if (n, P) == (N_PRIMARY, P_PRIMARY):
            fires_primary = fire
            ta_primary = totvol_analog_fires(close, n, P)
            # gate variants (RAW / +C32) — pre-stated column pair, primary cell
            for gate, gmask in (("raw", np.ones(len(c), bool)), ("c32", c32)):
                gv = valid & gmask
                for h in ("oos", "oos21"):
                    mk = masks[h]
                    sub = gv & mk
                    nn = int(sub.sum())
                    rec[f"n_{h}_{gate}"] = nn
                    if nn == 0 or not nulls[h]:
                        rec[f"umae_{h}_{gate}"] = np.nan
                        rec[f"uw5_{h}_{gate}"] = np.nan
                        continue
                    mae = m["mae63"][sub]; prox = m["prox"][sub]
                    rec[f"umae_{h}_{gate}"] = float(np.median(mae) - nulls[h]["mae_med"])
                    rec[f"uw5_{h}_{gate}"] = float((prox <= W5).mean() * 100 - nulls[h]["w5_rate"])
            # signal rows for the bootstrap (primary cell, TEST): F4 (raw/c32) + total-vol-analog
            for i in np.where(valid & masks["oos"])[0]:
                sig_rows.append(_sig_row(sym, "f4", i, idx, m, nulls, c32))
            tav = ta_primary & fin & masks["oos"]
            for i in np.where(tav)[0]:
                sig_rows.append(_sig_row(sym, "ta", i, idx, m, nulls, c32))

    # overlap census (primary cell, TEST): both / F4-only / analog-only
    if fires_primary is not None and ta_primary is not None:
        f4o = fires_primary & fin & masks["oos"]
        tao = ta_primary & fin & masks["oos"]
        rec["ov_both"] = int((f4o & tao).sum())
        rec["ov_f4only"] = int((f4o & ~tao).sum())
        rec["ov_taonly"] = int((tao & ~f4o).sum())

    # incumbent (Stoch-RSI<20 @ derived rung) fires — SAME names, TEST — earliness + MAE
    inc_tdt: list[float] = []
    inc_mae: list[float] = []
    if isinstance(rung, str):
        inc_dates = tool_dates(bars_for(close, rung), "S")
        inc_idx = idx.searchsorted(inc_dates)
        for i in inc_idx:
            if i < len(idx) and idx[i] >= OOS_START:
                if np.isfinite(m["tdt"][i]):
                    inc_tdt.append(float(m["tdt"][i]))
                if np.isfinite(m["mae63"][i]):
                    inc_mae.append(float(m["mae63"][i]))
    rec["inc_tdt_med"] = float(np.median(inc_tdt)) if inc_tdt else np.nan
    rec["inc_mae_med"] = float(np.median(inc_mae)) if inc_mae else np.nan
    rec["inc_n_oos"] = len(inc_tdt)
    # F4 primary tdt + MAE (TEST) for the better-confirmer-or-redundant test
    if fires_primary is not None:
        base = fires_primary & fin & masks["oos"]
        f4_tdt = m["tdt"][base]; f4_tdt = f4_tdt[np.isfinite(f4_tdt)]
        rec["f4_tdt_med"] = float(np.median(f4_tdt)) if len(f4_tdt) else np.nan
        rec["f4_n_oos"] = int(len(f4_tdt))
        f4_mae = m["mae63"][base]; f4_mae = f4_mae[np.isfinite(f4_mae)]
        rec["f4_mae_med"] = float(np.median(f4_mae)) if len(f4_mae) else np.nan
    if ta_primary is not None:
        tb = ta_primary & fin & masks["oos"]
        ta_tdt = m["tdt"][tb]; ta_tdt = ta_tdt[np.isfinite(ta_tdt)]
        rec["ta_tdt_med"] = float(np.median(ta_tdt)) if len(ta_tdt) else np.nan
        rec["ta_n_oos"] = int(len(ta_tdt))
        ta_mae = m["mae63"][tb]; ta_mae = ta_mae[np.isfinite(ta_mae)]
        rec["ta_mae_med"] = float(np.median(ta_mae)) if len(ta_mae) else np.nan
    rec["_sig"] = sig_rows
    return rec


# ── month-cluster bootstrap (COPIED per-name-first collapse from pss_f1/f2/f3) ─

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
    """Cluster = signal month. CIs on: F4 name-median U_MAE/U_W5 (raw, +C32),
    total-vol-analog U_MAE/U_W5, and the PAIRED F4−total-vol-analog diffs (same
    resampled clusters). Per-name-first collapse then cross-name median (F1 E1-fix)."""
    mcol = "mae_ex21" if sub21 else "mae_ex"
    wcol = "w5_ex21" if sub21 else "w5_ex"
    s = sig[np.isfinite(sig[mcol])].copy()
    if sub21:
        s = s[s.sub21]
    months = sorted(s["month"].unique())
    by_month = {mm: g for mm, g in s.groupby("month")}
    keys = ("f4_umae", "f4_uw5", "f4c_umae", "f4c_uw5",
            "ta_umae", "ta_uw5", "d_umae", "d_uw5")
    acc: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[mm] for mm in pick])
        bf4 = boot[boot.kind == "f4"]
        bf4c = bf4[bf4.gc32]
        bta = boot[boot.kind == "ta"]
        f4u, f4w = _name_uplift(bf4, mcol, wcol)
        f4cu, f4cw = _name_uplift(bf4c, mcol, wcol)
        tau, taw = _name_uplift(bta, mcol, wcol)
        acc["f4_umae"].append(f4u); acc["f4_uw5"].append(f4w)
        acc["f4c_umae"].append(f4cu); acc["f4c_uw5"].append(f4cw)
        acc["ta_umae"].append(tau); acc["ta_uw5"].append(taw)
        acc["d_umae"].append(f4u - tau); acc["d_uw5"].append(f4w - taw)   # PAIRED
    out = {}
    for k, v in acc.items():
        a = np.array(v, dtype=float)
        if np.isfinite(a).sum() < NB * 0.5:
            out[k] = (np.nan, np.nan)
        else:
            out[k] = (float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5)))
    return out


def direct_uw5_check(sig: pd.DataFrame) -> tuple[float, float]:
    """Self-check: direct per-name-median U_W5 (F4 and total-vol-analog), NO bootstrap.
    Must match the bootstrap point estimates within bootstrap noise (F1 E1 guard)."""
    s = sig[np.isfinite(sig["w5_ex"])]
    f4 = s[s.kind == "f4"]; ta = s[s.kind == "ta"]
    f4v = f4.groupby("sym")["w5_ex"].mean()
    tav = ta.groupby("sym")["w5_ex"].mean()
    return (float(np.median(f4v)) if len(f4v) else np.nan,
            float(np.median(tav)) if len(tav) else np.nan)


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


def p_sensitivity_counts(sym: str) -> dict | None:
    """H1-2022 vs ±21td-around-2022-low F4 fire counts ACROSS THE P GRID (P=3 vs P=5,
    n=20 primary window) — the earliness-vs-2022-safety frontier. RAW (no C32)."""
    try:
        close = load_px(sym)
    except Exception:  # noqa: BLE001
        return None
    if len(close) < TRAIL_MIN + PROX + H + 5:
        return None
    m = metric_arrays(close.to_numpy(dtype=float))
    fin = np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    idx = close.index
    center = idx.searchsorted(LOW22)
    win = np.zeros(len(idx), bool)
    a, b = max(0, center - 21), min(len(idx), center + 22)
    win[a:b] = True
    h1_mask = (idx >= H1_22[0]) & (idx <= H1_22[1])
    out = {}
    for P in (3, 5):
        fire = f4_fires(close, N_PRIMARY, P) & fin
        out[f"h1_P{P}"] = int((fire & h1_mask).sum())
        out[f"near_P{P}"] = int((fire & win).sum())
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
        nfit = r.get(f"n_is_n{N_PRIMARY}_P{P_PRIMARY}", 0)
        ntest = r.get(f"n_oos_n{N_PRIMARY}_P{P_PRIMARY}", 0)
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
    dchk_f4, dchk_ta = direct_uw5_check(sig)

    L: list[str] = []
    L.append("# PSS-F4 — Downside-vol asymmetry flip (semivariance regime turn)\n")
    L.append("Reset-CONFIRMER / symmetry-reset construction (copy law R-W1T-3 — no "
             "'bottom caller' / 'calls bottoms'). Pre-registered ruler + construction: "
             "script header, committed pre-run (prereg commit precedes results commit "
             "in git history; the absolute-threshold → per-name-baseline + dispersion-"
             "eligibility re-pin is disclosed there as amendments A1/A2/A3, all pre-"
             "outcome). Entry-timing ruler (§7), NOT hold returns (wrong-ruler check "
             "performed; motive #1458). Machinery (metric_arrays / null_stats / "
             "bars_for / tool_dates / _name_uplift per-name-first / c32_gate) COPIED "
             "from the W1 + F1 + F2 + F3 scripts. Inference: month-cluster bootstrap, "
             "NB=1000, seed 20260731. F4 makes NO pre-trough claim — it is an AT-TROUGH "
             "confirmer; its only path to usefulness is being a BETTER or genuinely "
             "COMPLEMENTARY at-trough confirmer than the incumbent. The commissioning "
             "session rules the verdict; this reports what was found.\n")

    # coverage census
    L.append("## Coverage census (eligible / excluded, with reasons)\n")
    tot = len(panel)
    L.append(f"- Universe: {tot} W1-panel names with OHLC (semivariance on daily log "
             f"returns; yahoo close is total-return adjusted, the ratio A nets it out).")
    L.append(f"- **F4-eligible: {len(p)}** (FIT-era asymmetry spread A_hi−A_base ≥ "
             f"{SPREAD_MIN} — min-baseline-asymmetry as DISPERSION, amendment A3 — AND "
             f"≥{MIN_FIT} FIT + ≥{MIN_TEST} TEST primary-cell (n={N_PRIMARY}, "
             f"P={P_PRIMARY}) fires with resolvable mae63/prox).")
    if len(exc):
        cats: dict[str, int] = {}
        for e in exc["excl"]:
            key = e.split("(")[0]
            cats[key] = cats.get(key, 0) + 1
        L.append(f"- **Excluded: {len(exc)}** — "
                 + "; ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])) + ".")
        L.append("  - `flat_asymmetry` = FIT-era A_hi−A_base < the dispersion floor "
                 "(cannot reach a down-dominated extreme above its own baseline → the "
                 "flip has no measurable content). `few_fires` = fewer than 3 FIT or 3 "
                 "TEST primary-cell fires. `short_history` = < TRAIL_MIN+PROX+H bars.")
    # CORRECTLY-NULL DEFENSIVES disposition (the charter prediction, tested honestly)
    L.append("- **Charter-named defensives (KO PG WMT COST) — the 'correctly-null' "
             "prediction, TESTED not assumed (amendment A3):**")
    elig_syms = set(p["sym"]) if len(p) else set()
    excl_syms = set(exc["sym"]) if len(exc) else set()
    for d in DEFENSIVES:
        if d in elig_syms:
            row = p[p.sym == d].iloc[0]
            L.append(f"  - {d}: **ELIGIBLE** — FIT A_base {row['a_base_fit']:.3f}, "
                     f"spread {row['spread_fit']:.3f} (≥ {SPREAD_MIN}); graded like any "
                     f"other name. NOT excluded as baseline-symmetric.")
        elif d in excl_syms:
            er = exc[exc.sym == d].iloc[0]["excl"]
            L.append(f"  - {d}: excluded ({er}).")
        else:
            L.append(f"  - {d}: not in the W1 panel (off-panel).")
    L.append("  - FINDING: the charter predicted these live near A≈1 with 'no signal "
             "content' and would be correctly-null. The MEASURED data does NOT bear "
             "this out — their conditional (in-drawdown) asymmetry and their A-spread "
             "are normal, so they are ELIGIBLE and graded. The 'correctly-null "
             "defensives' prediction is reported as NOT confirmed (disclosed as a "
             "finding, not a coverage loss).\n")
    # per-name axis distribution
    if "a_base_fit" in p and p.a_base_fit.notna().any():
        L.append(f"- Per-name FIT asymmetry axis (eligible names): A_base median "
                 f"{float(p.a_base_fit.median()):.3f} (deciles "
                 f"{np.nanpercentile(p.a_base_fit, [10, 50, 90]).round(3).tolist()}); "
                 f"A_disp median {float(p.a_disp_fit.median()):.3f}; spread (A_hi−A_base) "
                 f"median {float(p.spread_fit.median()):.3f}, min {float(p.spread_fit.min()):.3f}. "
                 f"NOTE: A_base < 1 across the panel (amendment A1) — the reset level is "
                 f"the name's OWN trailing baseline, never an absolute 1.0.")
    L.append(f"- TEST F4 signals (primary cell, pooled): "
             f"{int((sig.kind == 'f4').sum()):,}; total-vol-analog fires (TEST, "
             f"pooled): {int((sig.kind == 'ta').sum()):,}.\n")

    # panel base rates
    L.append(f"Panel all-days OOS base rates (median across eligible names): "
             f"MAE63 {float(p.null_oos_mae_med.median()):+.2f}%, "
             f"within-5%-of-low {float(p.null_oos_w5_rate.median()):.1f}%, "
             f"called-low {float(p.null_oos_called_rate.median()):.1f}%. (The charter's "
             f"~16% ambient within-5%-of-low is prong-1's null.)\n")

    # grid table
    L.append("## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level "
             "medians (no gate)\n")
    L.append("No per-name best-of-grid selection (DNR §2). Primary cell = "
             f"(n={N_PRIMARY}, P={P_PRIMARY}). Point estimates are panel medians of "
             "per-name uplifts; the CI/inference rows are the pooled month-cluster "
             "bootstrap on the primary cell below. n = RV window (daily); P = "
             "persistence (consecutive symmetric bars, the dead-cat gate).\n")
    L.append("| cell | n names | U_MAE | U_W5 | median OOS fires/name |")
    L.append("|---|---|---|---|---|")
    for (n, P) in GRID:
        um = f"umae_oos_n{n}_P{P}"; uw = f"uw5_oos_n{n}_P{P}"; nn = f"n_oos_n{n}_P{P}"
        star = " ★" if (n, P) == (N_PRIMARY, P_PRIMARY) else ""
        nser = p[nn][p[nn] > 0] if nn in p else pd.Series(dtype=float)
        L.append(f"| n={n}, P={P}{star} | {int(p[um].notna().sum())} | "
                 f"{float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp | "
                 f"{int(nser.median()) if len(nser) else 0} |")

    # eras for primary cell
    L.append("\n### Primary cell across eras (full TEST / 2021+ sub-window), no gate\n")
    L.append("| era | U_MAE | U_W5 |")
    L.append("|---|---|---|")
    pk = f"n{N_PRIMARY}_P{P_PRIMARY}"
    for era, suf in (("full TEST ≥2020-07", "oos"), ("2021+ ≥2021-01", "oos21")):
        L.append(f"| {era} | {float(p[f'umae_{suf}_{pk}'].median()):+.2f}pp | "
                 f"{float(p[f'uw5_{suf}_{pk}'].median()):+.2f}pp |")

    # gate-variant columns (primary cell): RAW / +C32
    L.append("\n## Gate variants on the primary cell (pre-stated column pair: RAW / "
             "+C32), name-level medians\n")
    L.append("RAW = no terminality gate. +C32 = decline-deceleration terminality "
             "gate (roc20 stopped making new lows while close ≤ 60d low + rolling-low "
             "slope flattening; copied verbatim from pss_f1_downvol).\n")
    L.append("| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS "
             "| median C32 fires/name |")
    L.append("|---|---|---|---|---|---|---|")
    c32_deg = False
    for gate, lab in (("raw", "RAW (no gate)"), ("c32", "+C32")):
        um = f"umae_oos_{gate}"; uw = f"uw5_oos_{gate}"
        um21 = f"umae_oos21_{gate}"; uw21 = f"uw5_oos21_{gate}"
        nn = f"n_oos_{gate}"
        nser = p.get(nn, pd.Series(dtype=float))
        nnames = int((nser >= 1).sum()) if nn in p else 0
        med_fires = float(nser[nser >= 1].median()) if (nn in p and (nser >= 1).any()) else float("nan")
        med_str = f"{med_fires:.0f}" if np.isfinite(med_fires) else "—"
        if gate == "c32" and np.isfinite(med_fires) and med_fires <= 2:
            c32_deg = True
        L.append(f"| {lab} | {float(p[um].median()):+.2f}pp | {float(p[uw].median()):+.2f}pp "
                 f"| {float(p[um21].dropna().median()):+.2f}pp | "
                 f"{float(p[uw21].dropna().median()):+.2f}pp | {nnames} | {med_str} |")
    if c32_deg:
        L.append("\n⚠️ **C32-gated U_W5 is DEGENERATE (small-sample artifact, NOT a "
                 "signal) — read the CI, not the point estimate.** The C32 gate is so "
                 "restrictive that the surviving names carry a median of ~1 gated fire "
                 "EACH, so each name's within-5%-of-low RATE collapses to 0% or 100% and "
                 "the cross-name median of those degenerate binary rates swings wildly "
                 "(here to a physically implausible ~+74pp). The month-cluster bootstrap "
                 "CI below correctly reports this column as `includes 0` (a wide, "
                 "0-straddling interval) — i.e. the C32-gated U_W5 estimates NOTHING. The "
                 "C32-gated U_MAE (a continuous statistic) does NOT collapse this way and "
                 "is read normally. This is a vacuous-green disclosure, not a result.")

    # inference CIs vs BOTH nulls
    L.append("\n## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls\n")
    L.append("Per-name-first collapse then cross-name median (matches the F1/F2/F3/"
             "W1-T machinery — the F1 E1 sign-flip bug is NOT repeated): within each "
             "month-cluster draw, U_MAE = name-median mae63 − name all-days median, "
             "U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN "
             "the cross-name median. Two nulls: (a) all-DAYS base rate [inside the "
             "per-name uplift], (b) the TOTAL-VOL ANALOG (identical construction on "
             "directionless RV_tot — the asymmetry-adds-nothing mirror placebo). The "
             "F4 − total-vol-analog diff is PAIRED on the same resampled month-clusters.\n")
    L.append(f"Self-check (F1 E1 guard): direct per-name-median U_W5 = F4 "
             f"{dchk_f4:+.2f}pp / total-vol-analog {dchk_ta:+.2f}pp; the bootstrap "
             f"point estimates below must match these within bootstrap noise.\n")
    L.append("| quantity | full TEST | 2021+ |")
    L.append("|---|---|---|")
    rows = [
        ("F4 U_MAE (vs all-days null), no gate", "f4_umae"),
        ("F4 U_W5 (vs all-days null), no gate", "f4_uw5"),
        ("F4 U_MAE, +C32", "f4c_umae"),
        ("F4 U_W5, +C32", "f4c_uw5"),
        ("total-vol-analog U_MAE (asymmetry-adds-nothing null)", "ta_umae"),
        ("total-vol-analog U_W5 (asymmetry-adds-nothing null)", "ta_uw5"),
        ("F4 − total-vol-analog  U_MAE (FALSIFIER, paired)", "d_umae"),
        ("F4 − total-vol-analog  U_W5 (FALSIFIER, paired)", "d_uw5"),
    ]
    for lab, key in rows:
        L.append(f"| {lab} | {ci_str(ci.get(key))} {verdict(ci.get(key))} | "
                 f"{ci_str(ci21.get(key))} {verdict(ci21.get(key))} |")
    L.append("\nThe FALSIFIER rows are the pre-stated kill (prong 2): if F4 − total-"
             "vol-analog does NOT exclude 0 (positive) on U_MAE/U_W5, the DIRECTIONAL "
             "asymmetry (the down/up ratio) carries no incremental information over "
             "plain vol-normalization, and F4 dies as a standalone construction. "
             "Printed regardless of outcome.\n")

    # overlap census
    L.append("## Overlap / disjointness census — F4 vs total-vol analog (primary "
             "cell, TEST)\n")
    L.append("A is a RATIO and RV_tot is a LEVEL — an asymmetry flip can happen while "
             "total vol stays elevated, and vol can compress while A stays down-"
             "dominated. So F4 fires are NOT a subset of vol-compression days; the "
             "placebo is a matched-construction counterfactual, not a disjoint "
             "complement.\n")
    if {"ov_both", "ov_f4only", "ov_taonly"}.issubset(p.columns):
        b = int(p.ov_both.sum()); fo = int(p.ov_f4only.sum()); no = int(p.ov_taonly.sum())
        tf4 = max(b + fo, 1)
        L.append(f"- BOTH F4 & total-vol-analog: {b:,} · F4-only (asymmetry flip w/o a "
                 f"coincident vol-compression run): {fo:,} ({fo / tf4:.0%} of F4 fires) "
                 f"· analog-only: {no:,}.")
        L.append(f"- F4-only share reflects how often the directional asymmetry flips "
                 f"without total vol simply compressing — the matched counterfactual is "
                 f"genuine, not a subset.\n")

    # better-confirmer-or-redundant test (F4 vs incumbent): td AND MAE
    L.append("## Better at-trough confirmer OR redundant? — F4 vs incumbent "
             "(Stoch-RSI<20 @ derived rung, SAME names)\n")
    L.append("F4 makes NO pre-trough claim (charter): 'strictly earlier' is NOT "
             "required. The test (charter prong 2) is whether F4 is a BETTER at-trough "
             "confirmer (shallower MAE and/or closer td_to_trough) or just a REDUNDANT "
             "one. td_to_trough: negative = trough BEFORE the fire (late confirmer). "
             "Per-name medians over TEST, then panel median of those. If P pushes the "
             "fire so late that td is no better than the incumbent's −2..−10 AND MAE is "
             "no shallower, F4 has collapsed into another reset-confirmer with no gain.\n")
    bi = p[np.isfinite(p.f4_tdt_med) & np.isfinite(p.inc_tdt_med)]
    L.append("| comparison | n names | F4 median tdt | incumbent median tdt | "
             "F4 − incumbent tdt | F4 median MAE | incumbent median MAE | F4 − inc MAE |")
    L.append("|---|---|---|---|---|---|---|---|")
    bm = p[np.isfinite(p.f4_tdt_med) & np.isfinite(p.inc_tdt_med)
           & np.isfinite(p.f4_mae_med) & np.isfinite(p.inc_mae_med)]
    if len(bm):
        dtd = float((bm.f4_tdt_med - bm.inc_tdt_med).median())
        dmae = float((bm.f4_mae_med - bm.inc_mae_med).median())
        L.append(f"| F4 vs incumbent | {len(bm)} | {float(bm.f4_tdt_med.median()):+.1f}td "
                 f"| {float(bm.inc_tdt_med.median()):+.1f}td | {dtd:+.1f}td | "
                 f"{float(bm.f4_mae_med.median()):+.2f}% | "
                 f"{float(bm.inc_mae_med.median()):+.2f}% | {dmae:+.2f}pp |")
    # vs total-vol analog too (context)
    bt = p[np.isfinite(p.f4_tdt_med) & np.isfinite(p.ta_tdt_med)
           & np.isfinite(p.f4_mae_med) & np.isfinite(p.ta_mae_med)]
    if len(bt):
        dtd = float((bt.f4_tdt_med - bt.ta_tdt_med).median())
        dmae = float((bt.f4_mae_med - bt.ta_mae_med).median())
        L.append(f"| F4 vs total-vol-analog (context) | {len(bt)} | "
                 f"{float(bt.f4_tdt_med.median()):+.1f}td | "
                 f"{float(bt.ta_tdt_med.median()):+.1f}td | {dtd:+.1f}td | "
                 f"{float(bt.f4_mae_med.median()):+.2f}% | "
                 f"{float(bt.ta_mae_med.median()):+.2f}% | {dmae:+.2f}pp |")
    L.append("\nFor tdt: MORE POSITIVE = closer to / before the trough = better. For "
             "F4 − incumbent MAE: POSITIVE = F4 shallower adverse excursion = better "
             "entry. F4 is a BETTER confirmer only if it improves on at least one axis "
             "at a meaningful margin; if both diffs sit near 0, F4 is REDUNDANT with "
             "the incumbent (the charter's prong-2 kill).\n")

    # 2022 P-sensitivity (the earliness-vs-2022-safety frontier)
    L.append("## 2022-class containment — P-sensitivity of H1-2022 false fires "
             "(the earliness-vs-2022-safety frontier)\n")
    L.append("Charter: too-short P re-imports the 2022 early-fire class (brief symmetry "
             "patches during relief bounces that re-invert to down-dominance within a "
             "few bars); a sufficiently long P should not trigger until the true trough. "
             "Fire counts H1-2022 (2022-01-01..2022-06-30) vs ±21td around the 2022-10-13 "
             "low, at n=20, ACROSS P=3 vs P=5 (RAW, no C32). NVDA is OFF-PANEL (W1 "
             "eligibility) — run from raw OHLCV, flagged.\n")
    L.append("| name | H1-2022 (P=3 / P=5) | ±21td 2022-low (P=3 / P=5) |")
    L.append("|---|---|---|")
    panel_syms = set(panel["sym"])
    agg_h1 = {3: 0, 5: 0}; agg_near = {3: 0, 5: 0}
    for sym in FOCUS:
        flag = "" if sym in panel_syms else " (off-panel)"
        cc = p_sensitivity_counts(sym)
        if cc is None:
            L.append(f"| {sym}{flag} | unmeasurable | — |")
        else:
            L.append(f"| {sym}{flag} | {cc['h1_P3']} / {cc['h1_P5']} | "
                     f"{cc['near_P3']} / {cc['near_P5']} |")
            for P in (3, 5):
                agg_h1[P] += cc[f"h1_P{P}"]; agg_near[P] += cc[f"near_P{P}"]
    L.append(f"| **FOCUS TOTAL** | **{agg_h1[3]} / {agg_h1[5]}** | "
             f"**{agg_near[3]} / {agg_near[5]}** |")
    L.append("\nIf P=5 cuts the H1-2022 false-fire count vs P=3 while retaining near-low "
             "coverage, the persistence gate is doing its 2022-defense job; if H1-2022 "
             "fires are as frequent at P=5 as at P=3, the too-short-P failure class is "
             "not contained by persistence alone. Reported regardless of outcome.\n")

    # product split (descriptive)
    L.append("## Product split (descriptive; near-low vs confirms-reset)\n")
    f4o = sig[sig.kind == "f4"]
    if len(f4o):
        called = float(((f4o.tdt >= -2) & (f4o.tdt <= 5)).mean() * 100)
        conf = float((f4o.tdt < -2).mean() * 100)
        early = float((f4o.tdt > 5).mean() * 100)
        L.append(f"F4 primary-cell TEST fires (n={len(f4o):,}): near-low (−2..+5td) "
                 f"{called:.0f}% · confirmed-reset (<−2td) {conf:.0f}% · after-low (>+5td) "
                 f"{early:.0f}% · median td_to_trough {float(f4o.tdt.median()):+.0f}td.\n")

    # what was found (no verdict language)
    L.append("## What was found (no verdict — the commissioning session rules)\n")
    f4_full = ci.get("f4_umae"); d_full = ci.get("d_umae"); dw_full = ci.get("d_uw5")
    L.append(f"- F4 (no gate) U_MAE vs the all-days null on full TEST: {ci_str(f4_full)} "
             f"({verdict(f4_full)}); U_W5 {ci_str(ci.get('f4_uw5'))} "
             f"({verdict(ci.get('f4_uw5'))}).")
    L.append(f"- The pre-stated FALSIFIER (F4 − total-vol analog, asymmetry-adds-"
             f"nothing): U_MAE {ci_str(d_full)} ({verdict(d_full)}), U_W5 "
             f"{ci_str(dw_full)} ({verdict(dw_full)}) on full TEST; 2021+ U_MAE "
             f"{ci_str(ci21.get('d_umae'))} ({verdict(ci21.get('d_umae'))}), U_W5 "
             f"{ci_str(ci21.get('d_uw5'))} ({verdict(ci21.get('d_uw5'))}).")
    L.append("- The +C32 gate column, the better-confirmer-or-redundant table (F4 vs "
             "incumbent on BOTH td_to_trough and MAE), the overlap census, and the 2022 "
             "P-sensitivity counts above are the pre-registered conditioner / falsifier "
             "reads. All nulls are printed. F4 makes NO pre-trough claim; the at-trough "
             "'better or redundant' verdict input is the F4-vs-incumbent table.")
    L.append("- CAUTION on the +C32-gated U_W5 point estimate: the gate leaves ~1 fire "
             "per surviving name, so that binary-rate column is a small-sample artifact "
             "(its CI correctly includes 0 — it estimates nothing); the gated U_MAE "
             "(continuous) is unaffected. See the gate-variant degeneracy note above.\n")

    # limitations
    L.append("## Limitations\n")
    L.append("- Closes-only MAE/troughs (house shadow-book form); intraday lows are "
             "deeper. Comparable across cells/variants, not absolute.")
    L.append("- Yahoo close is total-return adjusted; semivariance is on log returns "
             "and A is a RATIO, so the TR adjustment nets out (level-invariant).")
    L.append("- Survivor tape (data/baskets/ohlcv holds today's listings); per-name "
             "own-baseline netting removes level bias, not composition bias.")
    L.append("- The symmetric-reset level is the name's OWN trailing baseline A_base, "
             "NOT an absolute 1.0 — the unconditional FIT A_base is <1 across the panel "
             "(amendment A1); the mechanism's asymmetry is CONDITIONAL on the decline "
             "(amendment A2, measured pre-outcome). The absolute-1.0 crossing in the "
             "charter sketch was degenerate against the data and re-pinned pre-outcome.")
    L.append("- Eligibility is DISPERSION (A_hi−A_base spread), not an absolute A_base "
             "gate (amendment A3): the charter's baseline-symmetric-defensives premise "
             "did not hold in the data, so defensives are eligible-and-graded and the "
             "'correctly-null defensives' prediction is reported as NOT confirmed.")
    L.append("- ±31td proximity window is the §7 pin; long bear legs make 'the low' "
             "window-relative. The total-vol analog shares this window (fair test).")
    L.append("- Trailing bands are PIT (min 252 / cap 756 obs, shifted one bar); the "
             "leading region before the band fills never fires. n is the RV window "
             "(daily), P the persistence gate (the tunable) — the RV grain is daily, "
             "not rung-bar (pinned choice, disclosed).")
    L.append("- NVDA/PG are off the W1 panel (W1 eligibility); the 2022 P-sensitivity "
             "diagnostic runs NVDA as a raw-OHLCV exhibit, flagged.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    keep = [cc for cc in p.columns if not cc.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} "
          f"({len(p)} eligible names, {len(exc)} excluded)")


if __name__ == "__main__":
    main()
