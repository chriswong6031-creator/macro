"""Phase-1 (wave-1.5): the HAR-standardizer DISCRIMINATOR for pick_forward_dist.

FROZEN PRE-REGISTRATION (written BEFORE any pinball number was computed; every gap
closed before compute is recorded in AMENDMENTS below and repeated in the results file)
================================================================================
Family:  pick_forward_dist_phase1_har
Program: advanced-quant-methods-w1.5
Tier:    DIAGNOSTIC. This harness measures; it does not promote. No ship language, no
         authority claim, no gate on any user-facing surface follows from it.

QUESTION (frozen before anything was looked at)
----------------------------------------------
Wave-1 (research/PICK_FORWARD_DIST_PHASE0.md, merged as a5998ff0f3a) found that
S3_vol — cells cut on the name's 20d realized-vol z-score — improves out-of-sample
pinball loss against BOTH pre-registered nulls at H=21: +0.00280 [+0.00126, +0.00444]
vs the pooled marginal B0 (+1.09% of baseline units, 73% of dates positive, p<0.0002,
surviving a 10-test Bonferroni floor and refit-level clustering t=3.23).

Wave-1 also flagged, in its own frozen caveats, why that number is ambiguous. Outcomes
there are standardized by TRAILING 20-day realized vol. Trailing vol is a BIASED
forecast of forward vol, because realized vol mean-reverts: a name whose 20d vol just
spiked will realize LESS than one trailing sigma over the next month, and one sitting
in a vol trough will realize MORE. A cell that sorts on vol state therefore has a
mechanical way to win that has nothing to do with forward-return information — it can
simply correct the known bias in the SCALE. The adversarial review sharpened this: at
H=21 every scheme with a positive delta is a trailing-vol transform (S3 +0.00280,
S5 +0.00219, S4 +0.00091) and both non-vol schemes are negative (S2 -0.00028,
S1 -0.00052) — exactly the ordering the standardizer-artifact mechanism predicts.

  Two readings fit wave-1's evidence equally well:
    (A) STATE INFORMATION      — the vol-state cell says something about the shape of
                                 the forward distribution that the scale does not.
    (B) VOL-FORECAST CORRECTION — the cell is re-deriving a better forward-vol forecast,
                                 and the whole gain is the scale, not the state.

  This harness discriminates them by RE-RUNNING WAVE-1 WITH A BETTER STANDARDIZER.
  If the edge survives the better scale, (A). If it collapses, (B).

BOTH ANSWERS ARE WINS, and the writeup says which obtained and what it means:
  (A) -> the emitter conditions on vol-state cells over a trailing-vol scale.
  (B) -> the emitter ships MARGINAL cones on the HAR scale: simpler, no cells at all.
         "Use a better vol forecast" is itself the shippable width intelligence.
Neither answer authorizes a surface. Promotion is a separate adjudication.

WHAT CHANGES FROM WAVE-1 — EXACTLY ONE THING
--------------------------------------------
THE VOL_SCALE SERIES. Nothing else. Same store, same universe filter, same split
repair, same trading calendar, same H=21 primary, same tau grid, same 504-session
embargoed cohort, same quarterly refit schedule, same MIN_CELL_N / MIN_OWN_N floors,
same B0/B1 nulls, same per-date paired-delta statistic, same circular block bootstrap
(block=21, B=5000, seed=7). The STATE FEATURES ARE UNCHANGED TOO — the cells are still
cut on `rvol_z` exactly as wave-1 cut them, because the hypothesis under test is about
the SCALE, not about the state definition. Changing both at once would answer neither
question.

Mechanically, wave-1's own machinery is IMPORTED and CALLED, not re-implemented:
`scripts.pick_forward_dist_phase0` (loader, panel path, walk-forward, delta stats, era
split, every frozen constant) and `engine.pick_forward_dist`. The HAR arm is produced by
handing the SAME `p0.walk_forward` a panel whose three standardized outcome columns
(`z_ret_21`, `z_mae_21`, `z_mfe_21`) were rebuilt on the HAR scale. Both arms therefore
run byte-identical evaluation code over identical rows and identical dates. An
import-surface pin (`verify_phase0_surface`) makes the runner REFUSE TO RUN if any of
those imported signatures or frozen constants drift, so a later phase-0 refactor cannot
silently change what this study measured.

THE NEW STANDARDIZER
--------------------
A causal MULTI-SCALE REALIZED-VOL BLEND in the shape of the shipped house forward-vol
read: `engine.vol_forecast.har_vol` with HAR_LAGS = (2, 5, 22, 66), EQUAL WEIGHT.

  Named honestly: this is the "HAR-STYLE EQUAL-WEIGHT BLEND, THE SHIPPED HOUSE
  FORECASTER". It is NOT a fitted HAR. Corsi's HAR-RV is a REGRESSION with fitted
  betas on the daily/weekly/monthly components; this is the unweighted mean of realized
  vol over four lookbacks, which is what `engine/vol_forecast.py` actually ships and
  what `engine/anticipation.py` actually uses to set cone width. Calling it "a HAR"
  would claim a fit that does not exist. Whether the fitted version would do better is
  a different, later question and is explicitly out of scope.

  vol_scale_har(t) = har_vol(close)[t-1], clipped from below at VOL_FLOOR (0.005/day)

  Per name. Lag ONE bar, so the scale is fixed before the outcome window opens —
  identical lag convention to wave-1's `state_features.vol_scale`. Floor/winsor
  conventions are inherited VERBATIM from wave-1: a LOWER clip at VOL_FLOOR and NO
  upper winsor. That asymmetry is wave-1's, carried unchanged rather than re-designed
  here, because re-designing it would be a second change.

  The panel implementation is parity-tested against `engine.vol_forecast.har_vol`
  itself on a single series, and the blend definition (equal weight over HAR_LAGS,
  pct_change returns, ddof=0) is independently re-derived from first principles in
  tests/test_pick_forward_dist_phase1.py so a change to the shipped module fails loudly
  instead of silently redefining this study's scale.

DATA / UNIVERSE / SCHEMES / COHORT / WALK-FORWARD / BASELINES / METRICS
----------------------------------------------------------------------
Identical to wave-1. The full text is the frozen pre-registration in
`scripts/pick_forward_dist_phase0.py` (reproduced verbatim in section 5 of
research/PICK_FORWARD_DIST_PHASE0.md). It is not restated here so that there is exactly
ONE copy of it and no chance of the two drifting into disagreement. The constants it
fixes are pinned by `verify_phase0_surface` and printed in the results file.

Two horizon-scope reductions, both narrowing (AM-H1 below): only H=21 is run, and only
the vol-standardized frame. Wave-1's H=10/H=63 ladder and raw-percent frame were
descriptive rows that could not become a headline; they are not what this study asks.

PRE-REGISTERED READOUTS (H=21, vol-standardized frame only)
-----------------------------------------------------------
D-1  SURVIVAL.  S3_vol mean-pinball delta vs B0_pooled UNDER THE HAR STANDARDIZER,
     with the wave-1 date-blocked 95% CI (circular block bootstrap, block=21, B=5000,
     seed=7, `pfd.block_bootstrap_mean_ci`).
       PASS  <=>  the CI excludes 0  AND  the mean delta > 0.
     A FAIL is a RESULT and ships as one.

D-2  SHRINKAGE RATIO.  How much of wave-1's S3 edge survives the better scale.

     PRIMARY (scale-free), R_rel:
         R_rel = (S3 delta vs B0 under HAR,       as % of that arm's B0 mean pinball)
               / (S3 delta vs B0 under trailing20, as % of that arm's B0 mean pinball)
     The trailing20 denominator is RECOMPUTED IN THIS RUN on THIS panel — never lifted
     from the wave-1 artifact — so the two arms are apples-to-apples on identical rows
     and identical dates.

     SECONDARY (raw units), R_raw = ratio of the two mean deltas in their own units.
     Reported, never gating. R_raw is NOT scale-free: see AM-H2 — the HAR blend sits
     materially BELOW a 20d realized vol in LEVEL, which multiplies every pinball
     number in the HAR arm by a units factor that has nothing to do with skill. R_rel
     divides that factor out; R_raw does not. R_rel is therefore the primary.

     INTERPRETATION BANDS — FROZEN NOW, BEFORE ANY RESULT:
       R_rel >= 0.5  AND  D-1 PASS   ->  STATE_INFORMATION
       R_rel <  0.5  AND  D-1 FAIL   ->  VOL_FORECAST_CORRECTION
       anything else                 ->  MIXED   (the pattern is stated in words)
     Two degenerate cases, also frozen now:
       * If the trailing20 arm's OWN S3-vs-B0 delta is not positive with a CI excluding
         0 in THIS run, wave-1 did not replicate on this panel, the ratio has no
         denominator worth reading, and the verdict is INCONCLUSIVE_BASE.
       * If R_rel and R_raw land in DIFFERENT bands, the verdict is MIXED and both
         numbers are printed.
     A descriptive paired block-bootstrap interval for R_rel (same blocks, same B, same
     seed, both arms resampled on the SAME date blocks because they share evaluation
     dates) is reported. It gates nothing; replicates whose denominator is non-positive
     are counted and PRINTED as undefined rather than dropped silently.

DESCRIPTIVE READOUTS (no gates; every one of them is allowed to be a null)
     X-1  S5_trend_vol under both standardizers — wave-1's fragile second GO.
     X-2  B0 and B1 CALIBRATION under HAR vs trailing20: does the better standardizer
          improve EVERYONE's coverage, cells or no cells? Coverage is a hit rate and is
          unit-free, so it compares cleanly across arms. MEAN PINBALL LEVELS DO NOT —
          the two arms score different y's — so pinball is only ever read WITHIN an arm.
     X-3  S1/S2/S4 deltas under HAR: does the per-scheme ordering FLATTEN? Under
          reading (B) the vol-linked schemes should fall toward the non-vol ones.
     X-4  FORECAST QUALITY OF EACH STANDARDIZER (AM-H3). The discriminator's whole
          logic rests on "HAR is the better forward-vol forecast". That premise is
          MEASURED here, not assumed, on the same evaluated name-days: Pearson
          correlation of log(scale) with log(realized forward 21d vol), the mean and
          median of realized/predicted, the sd of log(realized/predicted), and the mean
          |log ratio|. The forward realized vol is `engine.vol_forecast.forward_vol_ann`
          — a LABEL by construction, look-ahead by design, used for validation only and
          never fed to any cone. If the blend turns out NOT to be the better forecaster,
          that is printed at the top of the writeup and the verdict is read in its
          light: a collapse under a WORSE scale would not be evidence for (B).

FALSIFICATION POSTURE
     A failed gate is a RESULT. Nothing is redefined, no threshold is moved, no horizon
     is swapped after seeing a number. D-1 is issued at H=21 only. Nulls are printed.
     No fused composite score is formed anywhere. No user-facing surface changes.

AMENDMENTS (gaps closed BEFORE any pinball was computed; none after)
  AM-H1 SCOPE NARROWING. Wave-1 ran three standardized horizons plus a raw-percent
        frame; this study runs H=21 in the vol-standardized frame ONLY, for both arms.
        The pre-registered readouts are all at H=21, wave-1's other rows were explicitly
        descriptive and barred from becoming a headline, and running two arms over the
        full ladder would quadruple the compute for rows no verdict reads. This is a
        narrowing, never a selection: H=21 was wave-1's primary before any of this.
  AM-H2 UNITS. Measured BEFORE any pinball was computed, on 12 large-cap series over
        their post-warm-up history: the HAR equal-weight blend sits at a median 0.846
        of the trailing-20d realized vol (per-name medians 0.830-0.861; pooled mean
        0.877, sd 0.258). The cause is arithmetic, not empirical — `realized_vol` uses
        ddof=0, and a 2-bar sample std with ddof=0 is |r1-r2|/2, whose expectation is
        ~0.56 sigma, so the short lags in the equal-weight blend drag the level down.
        A standardizer that is systematically ~15% low makes every standardized outcome
        ~18% larger and multiplies EVERY pinball number in that arm — baseline and
        scheme alike — by the same factor. A raw-unit delta ratio would therefore be
        inflated by a pure units artifact. Hence D-2's primary statistic is the ratio of
        PERCENT-OF-BASELINE deltas, which is exactly invariant to a global rescale of y,
        with the raw-unit ratio reported beside it. The ratio is not a global constant
        (p10 0.62, p90 1.13), so this removes the SYSTEMATIC component of the units
        factor, not all of it — stated, not hidden. NOTE the direction of the incentive:
        this correction makes the HAR arm's ratio SMALLER, i.e. it pushes toward the
        VOL_FORECAST_CORRECTION verdict, so it is the conservative choice against the
        more interesting (A) reading.
        NOTED POST-RUN (a disclosure; no gate, band, statistic or number moves): the
        SAME convention asymmetry exists on the LABEL side of X-4. The forward-vol
        label is engine.vol_forecast.forward_vol_ann — pct_change returns, ddof=0, a
        21-bar window — while the trailing predictor it is scored against is built
        from log returns with ddof=1 over 20 bars. The ddof=0/21-bar label is biased
        low by sqrt(20/21), i.e. about -0.025 in log terms, which is roughly a
        quarter of the trailing arm's reported overall log-ratio level. The label is
        IDENTICAL for both arms, so every X-4 and X-5 COMPARISON between them is
        unaffected; only the absolute log-ratio LEVELS carry the offset. Stated here
        so no reader mistakes that level for a pure forecast bias.
  AM-H3 FORECAST-QUALITY READ ADDED (X-4). Wave-1's own module docstring says the
        "HAR-style" claim should be measured rather than assumed. Because the entire
        discriminator rests on the new scale being BETTER, its forecast quality is
        measured descriptively here. It gates nothing and it cannot change D-1 or D-2 —
        it exists so a collapse cannot be mis-read as evidence for (B) when the honest
        cause was a worse forecaster.
  AM-H4 PANEL INTERSECTION. A row survives only if BOTH scales are finite and positive
        on it. Both arms then run on IDENTICAL rows, which is what makes the paired
        per-date delta comparison legitimate. The count of rows this removes relative to
        wave-1's universe is reported. It is removal-only and never touches an outcome.
  AM-H5 HAR-FRAME ARITHMETIC. `z_ret_21` in the HAR arm is re-standardized DIRECTLY
        from the panel's raw-percent `ret_21` column, so it carries no chained rounding.
        `z_mae_21`/`z_mfe_21` have no raw-percent column in the panel and are converted
        by the exact ratio (vol_scale / har_scale) — algebraically identical, since both
        frames divide the same percent outcome by (scale * sqrt(h)). The two routes are
        cross-checked against each other on `ret` in tests/test_pick_forward_dist_phase1.py.
  AM-H6 REPRODUCTION CONTROL. The trailing20 arm is a re-run of wave-1's primary cell on
        (almost) the same rows, so its S3-vs-B0 number is compared against wave-1's
        published +0.00280 [+0.00126, +0.00444] and the comparison is PRINTED. A large
        divergence would mean the machinery is not what wave-1 ran, and the D-2 ratio
        would be meaningless; it is checked rather than assumed.

Run:    python3 -m scripts.pick_forward_dist_phase1_har
        python3 -m scripts.pick_forward_dist_phase1_har --max-names 600   # smoke
Writes: research/pick_forward_dist_phase1_har_results.json
        research/PICK_FORWARD_DIST_PHASE1_HAR.md
"""
from __future__ import annotations

import argparse
import inspect
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT_ROOT))
if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

from collectors.massive_stock_day import (                       # noqa: E402
    StaleLocalMirrorError, check_local_mirror_freshness)
from engine import pick_forward_dist as pfd                      # noqa: E402
from engine import vol_forecast as vf                            # noqa: E402
from engine.trial_ledger import TrialLedger                      # noqa: E402
from scripts import pick_forward_dist_phase0 as p0               # noqa: E402

# ------------------------------------------------------------------ frozen constants
FAMILY = "pick_forward_dist_phase1_har"
PROGRAM = "advanced-quant-methods-w1.5"

PRIMARY_H = 21
ARMS = ("trail20", "har")
ARM_LABEL = {"trail20": "trailing 20d realized vol (wave-1)",
             "har": "HAR-style equal-weight blend, lags (2,5,22,66) (wave-1.5)"}
FOCUS_SCHEME = "S3_vol"
FOCUS_BASELINE = "B0_pooled"
SHRINK_BAND = 0.5                     # D-2 interpretation band, frozen pre-result
TRADING_YEAR = 252

RESULTS_JSON = WT_ROOT / "research" / "pick_forward_dist_phase1_har_results.json"
RESULTS_MD = WT_ROOT / "research" / "PICK_FORWARD_DIST_PHASE1_HAR.md"
LEDGER_PATH = WT_ROOT / "data" / "trial_ledger.jsonl"


# ============================================================== import-surface pin
# What this study measures is defined by code it IMPORTS rather than owns. Pin the call
# contract AND the frozen constants, and refuse to run when either drifts: a later
# phase-0 refactor must not be able to silently redefine wave-1.5's comparison arm.
# Parameter NAMES/KINDS/DEFAULTS are pinned (the real call contract); type annotations
# are not, so a cosmetic re-annotation does not trip the guard but a renamed argument,
# a new required argument, or a moved default does.
PHASE0_FUNC_SURFACE: dict[str, tuple[tuple[str, str, object], ...]] = {
    "resolve_data_root": (("arg", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),),
    "load_frames": (("store", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                    ("max_names", "POSITIONAL_OR_KEYWORD", None)),
    "walk_forward": (("panel", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                     ("cal", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                     ("h", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                     ("frame", "KEYWORD_ONLY", "std")),
    "delta_stats": (("wf", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                    ("scheme", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                    ("baseline", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                    ("block", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty)),
    "era_split": (("wf", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                  ("scheme", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                  ("baseline", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty)),
}

PHASE0_CONST_SURFACE: dict[str, object] = {
    "PRIMARY_H": 21,
    "WINDOW": 504,
    "MIN_CELL_N": 400,
    "MIN_OWN_N": 252,
    "TAUS": (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95),
    "OOS_START": "2023-01-01",
    "MIN_XSEC": 50,
    "ERA_SPLIT": "2025-01-01",
    "BOOT_B": 5000,
    "BOOT_SEED": 7,
    "COV_LO": 0.72,
    "COV_HI": 0.88,
    "SCHEMES": ("S1_trend", "S2_extension", "S3_vol", "S4_coil", "S5_trend_vol"),
    "BASELINES": ("B0_pooled", "B1_ownname"),
}

ENGINE_CONST_SURFACE: dict[str, object] = {
    "pfd.VOL_FLOOR": 0.005,
    "pfd.PRICE_MIN": 5.0,
    "pfd.DVOL_MIN": 2.0e6,
    "pfd.MIN_BARS": 300,
    "pfd.TAUS": (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95),
    "pfd.MAE_TAUS": (0.05, 0.25, 0.50),
    # The FEATURE windows. These define the trailing-20d comparison scale itself and the
    # 252d reference every state axis is z-scored/normalised against, so a change to any
    # of them silently redefines BOTH arms — the wave-1 baseline this study is measured
    # against AND the rvol_z cells it conditions on — while every signature above still
    # matches. VOL_WIN 20 -> 30 was the named defeating mutation the review found: it
    # moves the trailing standardizer, and therefore the D-2 denominator, invisibly.
    "pfd.VOL_WIN": 20,
    "pfd.VOL_MINP": 15,
    "pfd.REF_WIN": 252,
    "pfd.REF_MINP": 126,
    # All five scheme tuples, not just the two the readouts focus on: S1/S2/S4 are the
    # contrast that makes the X-3 "ordering flattens" reading mean anything, so a
    # redefined non-vol scheme would corrupt the conclusion without touching S3 or S5.
    "pfd.SCHEMES[S1_trend]": (("above_200dma", "bool", 2), ("slope50_up", "bool", 2)),
    "pfd.SCHEMES[S2_extension]": (("ext_pct", "q", 4),),
    "pfd.SCHEMES[S3_vol]": (("rvol_z", "q", 4),),
    "pfd.SCHEMES[S4_coil]": (("coil", "q", 4),),
    "pfd.SCHEMES[S5_trend_vol]": (("above_200dma", "bool", 2), ("rvol_z", "q", 3)),
    "vf.HAR_LAGS": (2, 5, 22, 66),
}


def _param_surface(fn) -> tuple[tuple[str, str, object], ...]:
    return tuple((p.name, p.kind.name, p.default)
                 for p in inspect.signature(fn).parameters.values())


def verify_phase0_surface() -> list[str]:
    """Raise unless the imported phase-0 / engine surface is exactly what wave-1 froze.

    Returns the list of checks that passed (so the results file can record what was
    pinned); raises RuntimeError naming every drift it found. Called at the TOP of
    run_study, so the runner refuses to produce a number against a moved baseline."""
    drift: list[str] = []
    checked: list[str] = []
    for name, want in PHASE0_FUNC_SURFACE.items():
        fn = getattr(p0, name, None)
        if fn is None or not callable(fn):
            drift.append(f"phase0.{name}: missing or not callable")
            continue
        got = _param_surface(fn)
        if got != want:
            drift.append(f"phase0.{name}: signature drift — want {want}, got {got}")
        checked.append(f"phase0.{name}{inspect.signature(fn)}")
    for name, want in PHASE0_CONST_SURFACE.items():
        if not hasattr(p0, name):
            drift.append(f"phase0.{name}: missing")
            continue
        got = getattr(p0, name)
        got_cmp = tuple(got) if isinstance(got, (tuple, list)) else got
        want_cmp = tuple(want) if isinstance(want, (tuple, list)) else want
        if got_cmp != want_cmp:
            drift.append(f"phase0.{name}: value drift — want {want_cmp!r}, got {got_cmp!r}")
        checked.append(f"phase0.{name}={got_cmp!r}")
    live = {
        "pfd.VOL_FLOOR": pfd.VOL_FLOOR, "pfd.PRICE_MIN": pfd.PRICE_MIN,
        "pfd.DVOL_MIN": pfd.DVOL_MIN, "pfd.MIN_BARS": pfd.MIN_BARS,
        "pfd.TAUS": tuple(pfd.TAUS), "pfd.MAE_TAUS": tuple(pfd.MAE_TAUS),
        "pfd.VOL_WIN": pfd.VOL_WIN, "pfd.VOL_MINP": pfd.VOL_MINP,
        "pfd.REF_WIN": pfd.REF_WIN, "pfd.REF_MINP": pfd.REF_MINP,
        "vf.HAR_LAGS": tuple(vf.HAR_LAGS),
    }
    live.update({f"pfd.SCHEMES[{s}]": tuple(pfd.SCHEMES.get(s, ())) for s in p0.SCHEMES})
    for name, want in ENGINE_CONST_SURFACE.items():
        got = live.get(name)
        want_cmp = tuple(want) if isinstance(want, (tuple, list)) else want
        if got != want_cmp:
            drift.append(f"{name}: value drift — want {want_cmp!r}, got {got!r}")
        checked.append(f"{name}={got!r}")
    if drift:
        raise RuntimeError(
            "phase-0 import surface drifted from the wave-1 pre-registration — refusing "
            "to run, because this study's comparison arm IS wave-1's machinery and a "
            "moved signature or constant silently changes what is being measured:\n  "
            + "\n  ".join(drift))
    return checked


# ============================================================== the new standardizer
def har_vol_scale(close, *, lags=None, floor: float = pfd.VOL_FLOOR) -> pd.Series:
    """The wave-1.5 standardizer: the shipped house HAR-style equal-weight realized-vol
    blend, lagged one bar and floored exactly as wave-1's `vol_scale` is.

    NOT a fitted HAR (see the module pre-registration): `engine.vol_forecast.har_vol` is
    the unweighted mean of trailing realized vol over HAR_LAGS = (2, 5, 22, 66). Calling
    the shipped function is deliberate — one definition of the house forecaster, not two.
    The lag-1 shift and the lower floor are the wave-1 conventions carried verbatim; the
    composition is pinned by tests/test_pick_forward_dist_phase1.py, which also re-derives
    the blend from first principles so a change inside `har_vol` fails loudly."""
    s = pd.Series(close).astype(float)
    blend = vf.har_vol(s, vf.HAR_LAGS if lags is None else lags)
    return blend.shift(1).clip(lower=float(floor))


def forward_rv_daily(close, horizon: int) -> pd.Series:
    """Realized forward vol over the next `horizon` bars, in DAILY units — the LABEL the
    two standardizers are scored against in X-4. Look-ahead by construction (that is what
    a label is); it is never fed to a cone, a cell, or a baseline."""
    s = pd.Series(close).astype(float)
    return vf.forward_vol_ann(s, int(horizon), trading_year=TRADING_YEAR) / np.sqrt(float(TRADING_YEAR))


def attach_scales(panel: pd.DataFrame, cal: pd.DatetimeIndex, frames: dict, *,
                  horizon: int) -> dict:
    """Write `har_scale` and `fwd_rv_<h>` onto the wave-1 panel, per name, in place.

    The panel drops its date index (it carries integer `sess` into the shared calendar),
    so each name's series is mapped back through `cal[sess]`. Removal-only: nothing here
    creates a row, and neither column is ever read by a cone."""
    n = len(panel)
    har = np.full(n, np.nan, dtype=np.float32)
    fwd = np.full(n, np.nan, dtype=np.float32)
    sess = panel["sess"].to_numpy()
    idx_by_name = panel.groupby("name", observed=True).indices
    missing = 0
    for name, rows in idx_by_name.items():
        f = frames.get(name)
        if f is None:
            missing += 1
            continue
        close = f["close"].astype(float)
        hs = har_vol_scale(close)
        fv = forward_rv_daily(close, horizon)
        if hs.index.has_duplicates:
            hs = hs[~hs.index.duplicated(keep="last")]
            fv = fv[~fv.index.duplicated(keep="last")]
        dates = cal[sess[rows]]
        har[rows] = hs.reindex(dates).to_numpy(dtype=np.float32)
        fwd[rows] = fv.reindex(dates).to_numpy(dtype=np.float32)
    panel["har_scale"] = har
    panel["fwd_rv"] = fwd
    return {"names_mapped": int(len(idx_by_name) - missing), "names_missing": int(missing)}


def build_har_frame(panel: pd.DataFrame, h: int) -> pd.DataFrame:
    """The HAR arm's panel: the SAME rows, the SAME features, the SAME raw outcomes —
    only the three standardized outcome columns are rebuilt on the HAR scale (AM-H5).

    `z_ret` is re-standardized directly from raw percent; `z_mae`/`z_mfe` have no raw
    column and are converted by the exact scale ratio. Because the columns keep wave-1's
    names, `p0.walk_forward` runs over this panel with byte-identical code."""
    trail = panel["vol_scale"].to_numpy(dtype=np.float64)
    hscale = panel["har_scale"].to_numpy(dtype=np.float64)
    ratio = trail / hscale
    root = np.sqrt(float(h))
    z_ret = (panel[f"ret_{h}"].to_numpy(dtype=np.float64) / 100.0) / (hscale * root)
    z_mae = panel[f"z_mae_{h}"].to_numpy(dtype=np.float64) * ratio
    z_mfe = panel[f"z_mfe_{h}"].to_numpy(dtype=np.float64) * ratio
    return panel.assign(**{f"z_ret_{h}": z_ret.astype(np.float32),
                           f"z_mae_{h}": z_mae.astype(np.float32),
                           f"z_mfe_{h}": z_mfe.astype(np.float32)})


# ============================================================== D-2 statistics
def _circular_block_index(n: int, block: int, rng) -> np.ndarray:
    """The index construction used by `pfd.block_bootstrap_mean_ci`, extracted so the
    two arms can be resampled on THE SAME blocks (they share evaluation dates, so a
    paired resample is the honest way to put a CI on their ratio)."""
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    starts = rng.integers(0, n, nb)
    return (starts[:, None] + grid[None, :]).ravel()[:n] % n


def shrinkage_ratio_ci(dh, bh, dt, bt, *, block: int, B: int, seed: int) -> dict:
    """Descriptive paired block-bootstrap interval for the scale-free shrinkage ratio.

    dh/dt are the per-date (B0 - S3) pinball deltas in the HAR / trailing arms; bh/bt are
    the per-date B0 pinball series of each arm. Every replicate resamples BOTH arms on the
    SAME date blocks. Replicates whose denominator is non-positive have no ratio; they are
    COUNTED AND PRINTED as undefined, never silently dropped into the percentile."""
    a_dh, a_bh = np.asarray(dh, float), np.asarray(bh, float)
    a_dt, a_bt = np.asarray(dt, float), np.asarray(bt, float)
    n = a_dh.size
    if not (a_bh.size == a_dt.size == a_bt.size == n) or n < max(block * 3, 60):
        return {"ci": None, "reason": "insufficient_or_misaligned_dates", "n": int(n)}
    rng = np.random.default_rng(seed)
    vals = np.empty(B)
    vals[:] = np.nan
    for k in range(B):
        idx = _circular_block_index(n, block, rng)
        num = a_dh[idx].mean() / a_bh[idx].mean() if a_bh[idx].mean() > 0 else np.nan
        den = a_dt[idx].mean() / a_bt[idx].mean()
        if np.isfinite(num) and np.isfinite(den) and den > 0:
            vals[k] = num / den
    good = np.isfinite(vals)
    if int(good.sum()) < B // 10:
        return {"ci": None, "reason": "denominator_non_positive_in_most_replicates",
                "undefined_frac": round(float(1.0 - good.mean()), 4), "B": int(B)}
    lo, mid, hi = (float(np.percentile(vals[good], p)) for p in (2.5, 50, 97.5))
    return {"ci": [round(lo, 4), round(mid, 4), round(hi, 4)],
            "undefined_frac": round(float(1.0 - good.mean()), 4),
            "block": int(block), "B": int(B), "seed": int(seed), "n_dates": int(n)}


def discriminate(d1_pass: bool, r_rel, r_raw, trail_replicated: bool) -> tuple[str, str]:
    """The frozen D-2 decision. Returns (verdict, one-line reason). No band is moved,
    no case is invented after the fact — every branch here was written before compute."""
    if not trail_replicated:
        return ("INCONCLUSIVE_BASE",
                "the trailing20 arm's own S3-vs-B0 delta is not positive with a CI "
                "excluding 0 in this run, so wave-1 did not replicate on this panel and "
                "the shrinkage ratio has no denominator worth reading")
    if r_rel is None or not np.isfinite(r_rel):
        return ("INCONCLUSIVE_BASE", "the shrinkage ratio is undefined on this run")
    hi_rel = bool(r_rel >= SHRINK_BAND)
    raw_ok = bool(r_raw is not None and np.isfinite(r_raw))
    hi_raw = bool(raw_ok and r_raw >= SHRINK_BAND)
    if hi_rel != hi_raw:
        # `r_raw` may be None/NaN here (hi_raw falls to False), so it is formatted
        # defensively — an unprintable secondary must never crash the verdict that
        # the PRIMARY statistic already decided.
        raw_txt = f"{r_raw:.3f}" if raw_ok else "undefined"
        return ("MIXED",
                f"the scale-free ratio ({r_rel:.3f}) and the raw-unit ratio "
                f"({raw_txt}) fall on opposite sides of the {SHRINK_BAND} band")
    if hi_rel and d1_pass:
        return ("STATE_INFORMATION",
                f"the edge survives the better scale ({r_rel:.0%} of it retained) and "
                "D-1's CI still excludes 0 on the positive side")
    if (not hi_rel) and (not d1_pass):
        return ("VOL_FORECAST_CORRECTION",
                f"the edge collapses under the HAR scale ({r_rel:.0%} retained) and "
                "D-1 fails — the wave-1 gain was the scale, not the state")
    if hi_rel and not d1_pass:
        return ("MIXED",
                f"{r_rel:.0%} of the point estimate survives but D-1's CI no longer "
                "excludes 0 — a shrunk edge this study cannot separate from zero")
    return ("MIXED",
            f"D-1 passes but only {r_rel:.0%} of the edge survives — the edge is real "
            "under the better scale yet most of wave-1's magnitude was the scale")


# ============================================================== forecast quality (X-4)
def forecast_quality(panel: pd.DataFrame, cal: pd.DatetimeIndex, h: int) -> dict:
    """X-4: how well does each standardizer actually forecast the forward 21d vol?

    Measured on the same span the walk-forward evaluates. Descriptive; gates nothing."""
    first_oos = int(np.searchsorted(cal.to_numpy(), np.datetime64(p0.OOS_START), side="left"))
    last_eval = len(cal) - 1 - h
    sess = panel["sess"].to_numpy()
    span = (sess >= first_oos) & (sess <= last_eval)
    fwd = panel["fwd_rv"].to_numpy(dtype=np.float64)
    out: dict[str, dict] = {}
    for arm, col in (("trail20", "vol_scale"), ("har", "har_scale")):
        pred = panel[col].to_numpy(dtype=np.float64)
        ok = span & np.isfinite(fwd) & (fwd > 0) & np.isfinite(pred) & (pred > 0)
        n = int(ok.sum())
        if n < 1000:
            out[arm] = {"n": n, "reason": "too few paired observations"}
            continue
        lp, lf = np.log(pred[ok]), np.log(fwd[ok])
        lr = lf - lp
        out[arm] = {
            "n": n,
            "corr_log_pred_vs_log_realized": round(float(np.corrcoef(lp, lf)[0, 1]), 4),
            "mean_realized_over_pred": round(float((fwd[ok] / pred[ok]).mean()), 4),
            "median_realized_over_pred": round(float(np.median(fwd[ok] / pred[ok])), 4),
            "sd_log_ratio": round(float(lr.std(ddof=1)), 4),
            "mean_abs_log_ratio": round(float(np.abs(lr).mean()), 4),
        }
    a, b = out.get("trail20", {}), out.get("har", {})
    if "corr_log_pred_vs_log_realized" in a and "corr_log_pred_vs_log_realized" in b:
        better = []
        if b["corr_log_pred_vs_log_realized"] > a["corr_log_pred_vs_log_realized"]:
            better.append("correlation")
        if b["sd_log_ratio"] < a["sd_log_ratio"]:
            better.append("log-ratio dispersion")
        if b["mean_abs_log_ratio"] < a["mean_abs_log_ratio"]:
            better.append("mean |log ratio|")
        out["har_is_better_on"] = better
        out["har_is_better_on_all_three"] = bool(len(better) == 3)
    return out


# ============================================================== X-5 (post-run addendum)
X5_PROVENANCE = (
    "X-5 IS NOT PART OF THE FROZEN PRE-REGISTRATION. It was written after a 1,500-file "
    "SMOKE run (not the study) returned a NULL on the pre-registered X-4 — the HAR blend "
    "was not the better forward-vol forecast on any of X-4's three measures — which left "
    "the pre-registered readouts hard to read: an edge shrinking under a scale that is "
    "not better overall proves nothing on its own. X-5 measures the SPECIFIC confound "
    "wave-1's caveat named, which X-4's aggregate measures cannot see. It is DESCRIPTIVE, "
    "it gates nothing, and neither D-1 nor D-2 reads it — both are computed by code "
    "frozen before any data was touched. It is recorded here, OUTSIDE the frozen header, "
    "rather than backdated into it. "
    "BAND CONSTRUCTION IS FULL-SPAN, NOT POINT-IN-TIME: the four rvol_z bands are "
    "equal-frequency cuts of the WHOLE evaluated span, not the walk-forward's "
    "per-refit embargoed edges, so they carry a hindsight whisker. That is acceptable "
    "only because nothing downstream reads X-5 and no gate depends on it — but X-5 "
    "does feed the headline MECHANISM claim, so the size of the bias-spread reduction "
    "it reports is suggestive rather than a point-in-time measurement.")


def state_conditional_bias(panel: pd.DataFrame, cal: pd.DatetimeIndex, h: int,
                           k: int = 4) -> dict:
    """X-5: the vol-state-CONDITIONAL bias of each standardizer.

    Wave-1's caveat is not about a scale being noisy in general — it is about a scale
    whose bias MOVES WITH THE VOL STATE, which is exactly what gives an S3 cell something
    mechanical to correct. Aggregate forecast quality (X-4) cannot see that: a scale can
    be worse on average and still be flatter across vol-state bands.

    Reported per arm: mean log(realized forward vol / predicted) inside each rvol_z band,
    and the SPREAD across bands. A smaller spread means less state-correlated bias, hence
    less for a vol-state cell to earn back. Descriptive; gates nothing.

    The bands here are full-span equal-frequency cuts of rvol_z, NOT the walk-forward's
    point-in-time per-refit edges — a hindsight whisker that is acceptable only because
    nothing downstream reads this, and stated rather than hidden."""
    first_oos = int(np.searchsorted(cal.to_numpy(), np.datetime64(p0.OOS_START), side="left"))
    last_eval = len(cal) - 1 - h
    sess = panel["sess"].to_numpy()
    span = (sess >= first_oos) & (sess <= last_eval)
    fwd = panel["fwd_rv"].to_numpy(dtype=np.float64)
    zc = panel["rvol_z"].to_numpy(dtype=np.float64)
    base_ok = span & np.isfinite(fwd) & (fwd > 0) & np.isfinite(zc)
    if int(base_ok.sum()) < 5000:
        return {"provenance": X5_PROVENANCE, "n": int(base_ok.sum()),
                "reason": "too few paired observations"}
    edges = np.unique(np.nanquantile(zc[base_ok], np.linspace(0.0, 1.0, k + 1)))
    nb = max(int(edges.size) - 1, 0)
    band = pfd.bands_of(zc, edges)
    out: dict = {"provenance": X5_PROVENANCE, "n": int(base_ok.sum()), "k_bands": nb,
                 "band_edges_rvol_z": [round(float(e), 4) for e in edges],
                 "band_meaning": "band 0 = lowest rvol_z (vol trough), "
                                 f"band {nb - 1} = highest (vol spike)",
                 "arms": {}}
    for arm, col in (("trail20", "vol_scale"), ("har", "har_scale")):
        pred = panel[col].to_numpy(dtype=np.float64)
        ok = base_ok & np.isfinite(pred) & (pred > 0)
        lr = np.log(fwd[ok] / pred[ok])
        bb = band[ok]
        bands, vals = {}, []
        for b in range(nb):
            m = bb == b
            mv = round(float(lr[m].mean()), 4) if bool(m.any()) else None
            bands[f"band{b}"] = {"n": int(m.sum()), "mean_log_realized_over_pred": mv}
            if mv is not None:
                vals.append(mv)
        out["arms"][arm] = {
            "bands": bands,
            "spread_max_minus_min": round(float(max(vals) - min(vals)), 4) if vals else None,
            "overall_mean_log_ratio": round(float(lr.mean()), 4),
        }
    sa = out["arms"]["trail20"]["spread_max_minus_min"]
    sb = out["arms"]["har"]["spread_max_minus_min"]
    if sa is not None and sb is not None:
        out["har_state_bias_spread_lower"] = bool(sb < sa)
        out["spread_reduction_frac"] = round(float(1.0 - sb / sa), 4) if sa else None
    return out


# ============================================================== AM-H6 reproduction
PHASE0_RESULTS = WT_ROOT / "research" / "pick_forward_dist_phase0_results.json"

# Rounded fallback ONLY — the values as PUBLISHED in the wave-1 writeup, kept for the
# case where the phase-0 artifact is absent. Comparing against these caps the check at
# 3 significant figures, which is coarser than this study's own resolution, so the
# artifact is always preferred.
WAVE1_S3_VS_B0 = {"mean_delta": 0.00280, "ci": [0.00126, 0.00444], "pct_of_baseline": 1.09}


def reproduction_control(d_trl: dict, path: Path = PHASE0_RESULTS) -> dict:
    """AM-H6: did the trailing20 arm reproduce wave-1's primary cell?

    Reads the COMMITTED phase-0 artifact and asserts field-by-field EXACT equality on
    the numbers wave-1 published for `S3_vol` vs `B0_pooled` at H=21. Exact, not
    approximate: both runs are deterministic (fixed seeds, sorted store glob) over the
    same panel, so any difference at all is a real divergence in the machinery and the
    D-2 ratio would be meaningless. Comparing against the writeup's ROUNDED literals
    instead would cap the check at the rounding, hiding a divergence smaller than 5e-6.

    Falls back to the rounded published literals, clearly labelled, only when the
    artifact is missing (a fresh checkout that never ran wave-1)."""
    fields = ("mean_delta", "ci", "pct_of_baseline", "excludes_zero", "n_dates",
              "gt0_prob", "frac_dates_positive", "block")
    mine = {k: d_trl.get(k) for k in fields}
    try:
        p0res = json.loads(path.read_text(encoding="utf-8"))
        ref = p0res["gates"]["S3_vol"]["G2_skill_vs_B0"]
        theirs = {k: ref.get(k) for k in fields}
        mismatches = {k: {"phase0": theirs[k], "this_run": mine[k]}
                      for k in fields if theirs[k] != mine[k]}
        return {
            "source": "committed phase-0 artifact (exact field equality)",
            "source_path": str(path),
            "phase0_S3_vs_B0": theirs,
            "this_run_trail20_S3_vs_B0": mine,
            "fields_compared": list(fields),
            "exact_match": not mismatches,
            "mismatches": mismatches or None,
        }
    except (OSError, KeyError, ValueError) as exc:
        raw_t = mine.get("mean_delta")
        return {
            "source": "FALLBACK — rounded literals from the wave-1 writeup; the phase-0 "
                      "artifact could not be read, so this check is capped at the "
                      "published rounding (3 s.f.) and is weaker than the exact one",
            "source_path": str(path),
            "fallback_reason": f"{type(exc).__name__}: {exc}",
            "wave1_published_rounded": WAVE1_S3_VS_B0,
            "this_run_trail20_S3_vs_B0": mine,
            "exact_match": None,
            "abs_diff_mean_delta": None if raw_t is None
            else round(abs(float(raw_t) - WAVE1_S3_VS_B0["mean_delta"]), 6),
            "within_wave1_published_ci": None if raw_t is None else bool(
                WAVE1_S3_VS_B0["ci"][0] <= float(raw_t) <= WAVE1_S3_VS_B0["ci"][1]),
        }


# ============================================================== study
def _arm_block(wf: dict, h: int) -> dict:
    """Per-arm summary: every scheme's delta vs both nulls, plus the nulls' own
    calibration. Pinball LEVELS are intentionally labelled as within-arm only."""
    schemes = {}
    for s in p0.SCHEMES:
        schemes[s] = {
            "coverage_80": round(float(wf["coverage"][s]), 4),
            "mean_pinball_within_arm": round(float(wf["pinball"][s].mean()), 6),
            "honest_frac": round(float(wf["honest_frac"][s]), 4),
            "cells_seen": wf["n_cells_seen"].get(s),
            "delta_vs_B0": p0.delta_stats(wf, s, "B0_pooled", h),
            "delta_vs_B1": p0.delta_stats(wf, s, "B1_ownname", h),
            "era_split_vs_B0": p0.era_split(wf, s, "B0_pooled"),
            "mae_p05_tail_hit": None if not np.isfinite(wf["tail_hit"][s])
            else round(float(wf["tail_hit"][s]), 4),
        }
    baselines = {b: {
        "coverage_80": round(float(wf["coverage"][b]), 4),
        "mean_pinball_within_arm": round(float(wf["pinball"][b].mean()), 6),
        "honest_frac": round(float(wf["honest_frac"][b]), 4),
        "breach_run": pfd.breach_run_stat(wf["breach"][b]),
    } for b in p0.BASELINES}
    return {
        "schemes": schemes, "baselines": baselines,
        "n_dates": wf["n_dates"], "n_name_days": wf["n_obs_total"],
        "n_names": wf["n_names"], "n_refits": wf["n_refits"],
        "first_eval": str(wf["dates"][0].date()) if wf["n_dates"] else None,
        "last_eval": str(wf["dates"][-1].date()) if wf["n_dates"] else None,
    }


def run_study(store: Path, max_names: int | None = None) -> dict:
    t_start = time.time()
    print(f"[startup] store       : {store}", flush=True)
    print(f"[startup] family      : {FAMILY} / program {PROGRAM}", flush=True)

    # The runner REFUSES to produce a number against a drifted baseline (import pin).
    pinned = verify_phase0_surface()
    print(f"[pin]     phase-0 import surface verified ({len(pinned)} checks)", flush=True)

    # Pre-register the multiple-testing budget BEFORE any compute (ledger law).
    led = TrialLedger(path=LEDGER_PATH, family=FAMILY)
    configs = [{
        "arm": a, "standardizer": ARM_LABEL[a], "scheme": s,
        "cells": pfd.SCHEME_CELLS[s], "horizon": PRIMARY_H, "frame": "vol_standardized",
        "test": "mean_pinball_delta_vs_B0_and_B1",
    } for a in ARMS for s in p0.SCHEMES] + [{
        "arm": a, "standardizer": ARM_LABEL[a], "baseline": b, "horizon": PRIMARY_H,
        "frame": "vol_standardized", "role": "pre-registered null",
    } for a in ARMS for b in p0.BASELINES] + [{
        "readout": "D2_shrinkage_ratio", "focus": FOCUS_SCHEME, "baseline": FOCUS_BASELINE,
        "horizon": PRIMARY_H, "band": SHRINK_BAND,
        "test": "scale_free_ratio_of_percent_of_baseline_deltas",
    }]
    n_new = led.log_grid(configs, info_cutoff="2026-07-02",
                         note="pick_forward_dist wave-1.5 HAR-standardizer discriminator; "
                              "frozen prereg in the script docstring, written before compute")
    print(f"[ledger]  {n_new} new trial configs (family={FAMILY}, total "
          f"{led.literal_n(FAMILY)})", flush=True)

    print("[load]    reading + split-repairing the store (wave-1 loader) ...", flush=True)
    t0 = time.time()
    frames, lstats = p0.load_frames(store, max_names=max_names)
    print(f"[load]    {lstats['read_ok']:,} read, {lstats['prefilter_pass']:,} prefiltered, "
          f"{lstats['split_repaired']:,} split-repaired ({lstats['bars_stamped']:,} bars "
          f"stamped) in {time.time()-t0:.0f}s", flush=True)

    print("[panel]   assembling the wave-1 observation panel (H=21 only, AM-H1) ...", flush=True)
    t0 = time.time()
    panel, cal = pfd.build_panel(frames, horizons=(PRIMARY_H,))
    if panel.empty:
        raise SystemExit("no eligible observations — refusing to report an empty study")
    rows_wave1 = int(len(panel))
    names_wave1 = int(panel["name"].astype(str).nunique())
    print(f"[panel]   {rows_wave1:,} rows, {names_wave1:,} names, calendar "
          f"{cal[0].date()} -> {cal[-1].date()} ({len(cal)} sessions) in "
          f"{time.time()-t0:.0f}s", flush=True)

    print("[scale]   computing the HAR blend + the forward-vol label per name ...", flush=True)
    t0 = time.time()
    map_stats = attach_scales(panel, cal, frames, horizon=PRIMARY_H)
    del frames
    fq = forecast_quality(panel, cal, PRIMARY_H)
    scb = state_conditional_bias(panel, cal, PRIMARY_H)
    keep = np.isfinite(panel["har_scale"].to_numpy()) & (panel["har_scale"].to_numpy() > 0)
    n_dropped = int((~keep).sum())
    if not keep.all():
        panel = panel.loc[keep].reset_index(drop=True)
    print(f"[scale]   done in {time.time()-t0:.0f}s; AM-H4 intersection dropped "
          f"{n_dropped:,} of {rows_wave1:,} rows ({100.0*n_dropped/max(rows_wave1,1):.3f}%)",
          flush=True)

    print("[wf]      arm 1/2 — trailing20 (the wave-1 arm, recomputed here) ...", flush=True)
    t0 = time.time()
    wf_trail = p0.walk_forward(panel, cal, PRIMARY_H, frame="std")
    print(f"[wf]      trail20 done: {wf_trail['n_dates']} dates, "
          f"{wf_trail['n_obs_total']:,} name-days in {time.time()-t0:.0f}s", flush=True)

    print("[wf]      arm 2/2 — HAR-style equal-weight blend ...", flush=True)
    t0 = time.time()
    panel_har = build_har_frame(panel, PRIMARY_H)
    wf_har = p0.walk_forward(panel_har, cal, PRIMARY_H, frame="std")
    del panel_har
    print(f"[wf]      har done: {wf_har['n_dates']} dates, "
          f"{wf_har['n_obs_total']:,} name-days in {time.time()-t0:.0f}s", flush=True)

    arms = {"trail20": _arm_block(wf_trail, PRIMARY_H), "har": _arm_block(wf_har, PRIMARY_H)}

    # ---------------- D-1
    d_har = arms["har"]["schemes"][FOCUS_SCHEME]["delta_vs_B0"]
    d_trl = arms["trail20"]["schemes"][FOCUS_SCHEME]["delta_vs_B0"]
    d1_pass = bool(d_har.get("excludes_zero") and (d_har.get("mean_delta") or 0.0) > 0)

    # ---------------- D-2
    trail_replicated = bool(d_trl.get("excludes_zero") and (d_trl.get("mean_delta") or 0.0) > 0)
    pct_h, pct_t = d_har.get("pct_of_baseline"), d_trl.get("pct_of_baseline")
    raw_h, raw_t = d_har.get("mean_delta"), d_trl.get("mean_delta")
    r_rel = (pct_h / pct_t) if (pct_h is not None and pct_t not in (None, 0)) else None
    r_raw = (raw_h / raw_t) if (raw_h is not None and raw_t not in (None, 0)) else None
    verdict, reason = discriminate(d1_pass, r_rel, r_raw, trail_replicated)

    dh = (wf_har["pinball"]["B0_pooled"] - wf_har["pinball"][FOCUS_SCHEME]).dropna()
    dt = (wf_trail["pinball"]["B0_pooled"] - wf_trail["pinball"][FOCUS_SCHEME]).dropna()
    common = dh.index.intersection(dt.index)
    ratio_ci = shrinkage_ratio_ci(
        dh.reindex(common).to_numpy(), wf_har["pinball"]["B0_pooled"].reindex(common).to_numpy(),
        dt.reindex(common).to_numpy(), wf_trail["pinball"]["B0_pooled"].reindex(common).to_numpy(),
        block=PRIMARY_H, B=p0.BOOT_B, seed=p0.BOOT_SEED)

    # ---------------- AM-H6 reproduction control
    repro = reproduction_control(d_trl)

    runtime = time.time() - t_start
    out = {
        "family": FAMILY,
        "program": PROGRAM,
        "tier": "diagnostic — wave-1.5 discriminator; promotes nothing",
        "prereg": "frozen in the module docstring of scripts/pick_forward_dist_phase1_har.py",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_sec": round(runtime, 1),
        "verdict": verdict,
        "verdict_reason": reason,
        "D1_survival": {
            "scheme": FOCUS_SCHEME, "baseline": FOCUS_BASELINE, "horizon": PRIMARY_H,
            "standardizer": ARM_LABEL["har"], "pass": d1_pass, **d_har,
        },
        "D2_shrinkage": {
            "band": SHRINK_BAND,
            "ratio_relative_primary": None if r_rel is None else round(float(r_rel), 4),
            "ratio_raw_units_secondary": None if r_raw is None else round(float(r_raw), 4),
            "har_pct_of_baseline": pct_h, "trail20_pct_of_baseline": pct_t,
            "har_mean_delta": raw_h, "trail20_mean_delta": raw_t,
            "trailing20_replicated_wave1": trail_replicated,
            "paired_block_bootstrap_ci_descriptive": ratio_ci,
        },
        "reproduction_control_AM_H6": repro,
        "forecast_quality_X4": fq,
        "state_conditional_bias_X5": scb,
        "arms": arms,
        "standardizers": ARM_LABEL,
        "config": {
            "horizon": PRIMARY_H, "frame": "vol_standardized",
            "taus": list(p0.TAUS), "window_sessions": p0.WINDOW,
            "min_cell_n": p0.MIN_CELL_N, "min_own_n": p0.MIN_OWN_N,
            "vol_floor_daily": pfd.VOL_FLOOR, "har_lags": list(vf.HAR_LAGS),
            "oos_start": p0.OOS_START, "min_cross_section": p0.MIN_XSEC,
            "refit": "quarterly", "eval_cadence": "every session",
            "bootstrap": {"B": p0.BOOT_B, "seed": p0.BOOT_SEED, "block": PRIMARY_H},
            "import_surface_pinned": pinned,
        },
        "data": {
            "store": str(store),
            "files_seen": lstats["files"], "files_read": lstats["read_ok"],
            "prefilter_pass": lstats["prefilter_pass"],
            "split_repaired_names": lstats["split_repaired"],
            "split_bars_stamped": lstats["bars_stamped"],
            "calendar_first": str(cal[0].date()), "calendar_last": str(cal[-1].date()),
            "calendar_sessions": int(len(cal)),
            "panel_rows_wave1_universe": rows_wave1,
            "panel_rows_both_scales_finite": int(len(panel)),
            "rows_dropped_by_scale_intersection_AM_H4": n_dropped,
            "panel_names": names_wave1,
            "names_mapped": map_stats["names_mapped"],
            "names_missing_from_frames": map_stats["names_missing"],
            "prices": "unadjusted; splits repaired via replay_standout_pipeline.split_adjust; "
                      "dividends NOT adjusted (price return)",
        },
        "caveats": [
            "WAVE-1'S CAVEATS ALL STILL APPLY, UNCHANGED: survivorship (store begins "
            "2021-07-06), single era (one macro regime block, no out-of-era "
            "replication), price-return not total-return, ~8-10 unrepaired spinoffs, "
            "instrument mix (ETFs/ADRs/preferreds clear the liquidity filter), "
            "overlapping forward windows, ratio-neutral back-adjustment, and the "
            "structurally weak G1/G4 gates. This study changes the STANDARDIZER; it "
            "does not repair a single one of those. Read research/PICK_FORWARD_DIST_"
            "PHASE0.md sections 3 and 3b alongside this file.",
            "MEAN PINBALL IS NOT COMPARABLE ACROSS THE TWO ARMS. Each arm scores a "
            "DIFFERENT standardized outcome, so its losses live in its own units. Only "
            "WITHIN-arm deltas and unit-free rates (coverage, honest_frac, tail hit) "
            "cross the arm boundary. Every pinball level below is labelled "
            "'within_arm' for exactly this reason, and D-2's primary ratio is built "
            "from percent-of-baseline deltas so the units divide out (AM-H2).",
            "THE HAR BLEND IS NOT A FITTED HAR. It is the shipped house equal-weight "
            "multi-scale realized-vol blend over lags (2, 5, 22, 66). A fitted "
            "HAR-RV regression would weight the components; this does not. If the "
            "verdict is VOL_FORECAST_CORRECTION, the honest read is 'a better SCALE "
            "beats the cells', not 'Corsi's HAR is the answer' — the fitted version "
            "was never tested here.",
            "THE SHORT LAGS DRAG THE LEVEL DOWN (AM-H2): the blend's 2- and 5-bar "
            "components use ddof=0 on tiny samples, which biases them low, so the "
            "blend sits at ~0.85 of a 20d realized vol. This is a LEVEL effect and it "
            "cancels out of coverage and out of the percent-of-baseline ratio; it does "
            "NOT cancel out of the raw-unit ratio, which is why that one is secondary.",
            "ONE HORIZON, ONE FRAME (AM-H1). H=10, H=63 and the raw-percent frame are "
            "not run in either arm. They were descriptive rows in wave-1 that could "
            "not become a headline, and no readout here reads them. A reader who wants "
            "the horizon ladder has wave-1's, on wave-1's scale.",
            "THE STATE DEFINITION IS UNCHANGED. Cells are still cut on `rvol_z` (20d "
            "realized vol z-scored against its own trailing 252d reference), exactly "
            "as wave-1 cut them. This study does not ask whether a HAR-based STATE "
            "would condition better — only whether the wave-1 edge survives a better "
            "SCALE. A HAR-based state axis is a different, later question.",
            "NO COVERAGE TEST STATISTIC. The coverage numbers are pooled hit rates at "
            "OVERLAPPING origins, as in wave-1; the review's non-overlapping-origin "
            "coverage test (Kupiec/Christoffersen at independent origins) is NOT built "
            "here and remains open. The X-2 comparison is therefore descriptive: it "
            "says which arm's realized coverage is closer to nominal on the same "
            "dates, not that the difference is significant.",
            "DIAGNOSTIC TIER. Nothing here promotes, ranks, sizes, gates or escalates. "
            "No fused composite is formed. No site, template, dag, synapse or registry "
            "file is touched by this lane.",
        ],
    }
    return out, wf_trail, wf_har


# ============================================================== report
def _fmt_ci(d: dict) -> str:
    if not d or d.get("ci") is None:
        return "n/a"
    lo, _, hi = d["ci"]
    return f"{d['mean_delta']:+.5f} [{lo:+.5f}, {hi:+.5f}]"


def _fmt_pct(d: dict) -> str:
    v = (d or {}).get("pct_of_baseline")
    return "n/a" if v is None else f"{v:+.3f}%"


def emitter_reading(out: dict) -> list[str]:
    """What the verdict means for the per-pick cone emitter, stated against the numbers
    this run actually produced. Both of the two headline verdicts are wins; the MIXED
    branches are the ones that need the pattern spelled out rather than a slogan."""
    v = out["verdict"]
    d1, d2 = out["D1_survival"], out["D2_shrinkage"]
    fq = out.get("forecast_quality_X4") or {}
    scb = out.get("state_conditional_bias_X5") or {}
    r = d2.get("ratio_relative_primary")
    r_txt = "n/a" if r is None else f"{r:.0%}"
    har_pct = d1.get("pct_of_baseline")
    trl_pct = d2.get("trail20_pct_of_baseline")
    har_better = fq.get("har_is_better_on")
    spread_cut = scb.get("spread_reduction_frac")

    L: list[str] = []
    if v == "STATE_INFORMATION":
        L.append(
            f"**The vol-state cell carries something the scale does not.** {r_txt} of "
            f"wave-1's relative edge survives a standardizer built on a different "
            f"construction, and D-1's interval still excludes zero on the positive side.")
        L.append("")
        L.append(
            "**For the emitter:** a per-pick cone conditions on vol-state cells over a "
            "trailing-vol scale — the cells earn their place. Quote the width in the "
            "frame the gates read, keep the cell-honesty stamp visible, and keep the "
            "surface language at \"windows, not certainties\".")
    elif v == "VOL_FORECAST_CORRECTION":
        L.append(
            f"**Wave-1's S3 edge was the standardizer, not the state.** Only {r_txt} of "
            f"the relative edge survives the change of scale"
            + (f" ({har_pct:+.3f}% of baseline pinball against {trl_pct:+.3f}%)"
               if (har_pct is not None and trl_pct is not None) else "")
            + ", and D-1's interval no longer excludes zero.")
        L.append("")
        if spread_cut is not None:
            lost = 1.0 - (r or 0.0)
            gap = lost - spread_cut
            L.append(
                f"X-5 confirms the mechanism DIRECTIONALLY, not quantitatively: removing "
                f"**{spread_cut:.1%} of the state-correlated scale bias** removed "
                f"**{lost:.1%} of the edge** — the two move the same way, but "
                f"**{gap * 100.0:.1f} percentage points of the collapse are NOT "
                f"accounted for** by the bias-spread reduction alone, and this study "
                f"does not explain the remainder. "
                f"The trailing-20d scale under-predicts forward vol in a vol "
                f"trough and over-predicts after a spike — exactly the mean reversion "
                f"wave-1's caveat named — and an `S3_vol` cell earns its pinball back by "
                f"re-pricing those bands. Take the state-dependent bias away and the cell "
                f"has little left to sell. Read the size of the correspondence as "
                f"suggestive: X-5's bands are FULL-SPAN equal-frequency cuts of `rvol_z`, "
                f"not the walk-forward's point-in-time per-refit edges, so they carry a "
                f"hindsight whisker (stated, not hidden — nothing downstream reads them).")
            L.append("")
        # The verdict is B0-referenced by pre-registration. If the OTHER pre-registered
        # null still rejects, that is a material qualification and must not be left to a
        # reader to spot in a table further down.
        b1h = ((out.get("arms", {}).get("har", {}).get("schemes", {})
                .get(FOCUS_SCHEME, {})).get("delta_vs_B1") or {})
        b1t = ((out.get("arms", {}).get("trail20", {}).get("schemes", {})
                .get(FOCUS_SCHEME, {})).get("delta_vs_B1") or {})
        p_one = (None if d1.get("gt0_prob") is None
                 else round(1.0 - float(d1["gt0_prob"]), 4))
        b1_ratio = (b1h.get("pct_of_baseline") / b1t["pct_of_baseline"]
                    if b1t.get("pct_of_baseline") else None)
        if b1h.get("excludes_zero") and (b1h.get("mean_delta") or 0.0) > 0:
            L.append(
                f"**Two things keep this a re-read rather than a proven negative.** "
                f"First, against the OTHER pre-registered null — the own-name marginal "
                f"B1 — S3 under the HAR scale **still excludes zero** "
                f"({_fmt_ci(b1h)}, {b1h.get('pct_of_baseline'):+.3f}% of baseline"
                + (f", ratio {b1_ratio:.3f} — above the {SHRINK_BAND} band"
                   if b1_ratio is not None else "") + "). Second, D-1's margin is thin"
                + (f" (one-sided p {p_one:.3f})" if p_one is not None else "")
                + " — a marginal non-rejection, not a decisive one. Read B1 with wave-1's "
                "own disclosure attached: B1 degrades to B0 for ~40% of name-days "
                "(REVIEW-2), so it is a ~60/40 blend of the own-name test and the B0 "
                "test, not a fully independent second opinion. The honest statement is "
                "that the **B0-referenced** vol-state edge does not survive a state-flat "
                "scale at the pre-registered bar; a residual own-name-referenced read "
                "remains, and it is not promotable either.")
            L.append("")
        L.append(
            "**For the emitter:** ship MARGINAL cones — no cells. Simpler, no "
            "cell-honesty floor to police, one fewer thing to explain, and one fewer "
            "conditional claim to defend. The B0-referenced conditional read was not "
            "carrying forward-return information; it was carrying a scale correction.")
        L.append("")
        if har_better == []:
            L.append(
                "**But read the scale half of that carefully, because X-4 is a null.** "
                "The HAR-style equal-weight blend is **not** the better forward-vol "
                "forecast in aggregate — it loses to the plain 20d realized vol on all "
                "three of X-4's measures. It wins this discriminator by being FLATTER "
                "ACROSS VOL STATES, not by being more accurate. So the shippable "
                "instruction is NOT \"ship the HAR blend\". It is: **the width scale "
                "must be one whose bias does not move with vol state** — that is the "
                "property that absorbed wave-1's edge, and it is the property to "
                "select on. Which scale actually has it, at good aggregate accuracy, is "
                "the open rung: a FITTED forward-vol forecast is the obvious untested "
                "candidate and nothing here measures it.")
        else:
            L.append(
                f"The HAR blend is the better forward-vol read on {', '.join(har_better)} "
                f"(X-4), so \"use a better vol forecast\" is itself the shippable width "
                f"intelligence here — a cleaner product than the conditional read would "
                f"have been. A FITTED forward-vol forecast remains the untested rung "
                f"above it.")
    elif v == "INCONCLUSIVE_BASE":
        L.append(
            "**The comparison arm did not reproduce wave-1 on this panel**, so the "
            "shrinkage ratio has no denominator worth reading.")
        L.append("")
        L.append(
            "**For the emitter:** nothing here changes the wave-1 posture. The "
            "discriminator itself needs repair before it can decide anything.")
    else:  # MIXED
        survived = bool(d1.get("pass"))
        L.append(
            f"**The edge {'survives' if survived else 'does not survive'} the change of "
            f"scale, but most of its magnitude does not.** {r_txt} of wave-1's relative "
            f"edge is retained"
            + (f" — {har_pct:+.3f}% of baseline pinball under the new scale against "
               f"{trl_pct:+.3f}% under wave-1's" if (har_pct is not None and trl_pct is not None)
               else "")
            + f". {out['verdict_reason'].capitalize()}.")
        L.append("")
        L.append(
            "Neither frozen reading wins outright because **both mechanisms are really "
            "present**. "
            + (f"X-5 measures the one wave-1's caveat named: the new scale carries "
               f"{spread_cut:.0%} less vol-state-correlated bias, and that is the part of "
               f"the wave-1 number that disappeared. "
               if spread_cut is not None and spread_cut > 0 else "")
            + ("What is left over is not zero"
               if survived else "What is left over cannot be separated from zero")
            + " — which is the honest size of the state effect.")
        L.append("")
        L.append("**For the emitter**, three things follow, and they are separable:")
        L.append("")
        L.append(
            f"1. **The vol-state conditioning is not purely a standardizer artifact.** "
            f"It {'still clears' if survived else 'no longer clears'} the pooled-marginal "
            f"null under a scale built on a different construction, so a cell-conditioned "
            f"cone is {'defensible' if survived else 'not defensible on this evidence'} — "
            f"but only at its post-shrinkage size.")
        L.append(
            f"2. **The honest effect size is the small one.** Any width claim should quote "
            + (f"{har_pct:+.3f}% of baseline pinball, not wave-1's {trl_pct:+.3f}%"
               if (har_pct is not None and trl_pct is not None) else "the post-shrinkage number")
            + ". Wave-1 already called this economically small; it is smaller.")
        L.append(
            "3. **\"Ship a better vol scale\" is now its own open lane, and this run does "
            "NOT close it.** "
            + ("The equal-weight HAR blend is not the better forward-vol forecast in "
               "aggregate (X-4), so it is not itself the scale to ship. "
               if har_better == [] else
               (f"The blend is better on {', '.join(har_better)} but not on all three "
                f"(X-4), so it is not yet the scale to ship. " if har_better else ""))
            + "A FITTED forward-vol forecast is the untested rung — it is the thing that "
            "could deliver the width intelligence the collapse reading promised, and "
            "nothing here measures it.")
    return L


def write_markdown(out: dict, path: Path) -> None:
    prereg = (Path(__file__).read_text(encoding="utf-8").split('"""', 2)[1]).strip()
    d1 = out["D1_survival"]
    d2 = out["D2_shrinkage"]
    L: list[str] = []
    L.append("# Pick-class forward distributions — wave-1.5 HAR-standardizer discriminator")
    L.append("")
    L.append(f"**Family** `{out['family']}` · **Program** `{out['program']}` · "
             f"**Tier** {out['tier']}")
    L.append(f"**Generated** {out['generated_utc']} · **Runtime** {out['runtime_sec']:.0f}s")
    L.append("")
    L.append("Wave-1 measured that vol-state cells (`S3_vol`) beat the pooled marginal at "
             "H=21 — with outcomes standardized by TRAILING 20d vol, a biased forward-vol "
             "forecast. This study re-runs wave-1 changing **exactly one thing**: the "
             "vol_scale series becomes the shipped house HAR-style equal-weight blend. "
             "Both possible answers are wins; the question is which one obtained.")
    L.append("")
    L.append(f"## 0. Verdict — **{out['verdict']}**")
    L.append("")
    L.extend(emitter_reading(out))
    L.append("")
    L.append("| Readout | Result |")
    L.append("|---|---|")
    _p1 = (None if d1.get("gt0_prob") is None else 1.0 - float(d1["gt0_prob"]))
    L.append(f"| **D-1** S3 vs B0 under HAR | {_fmt_ci(d1)} "
             f"({_fmt_pct(d1)} of baseline"
             + (f", one-sided p {_p1:.3f}" if _p1 is not None else "")
             + f") — **{'PASS' if d1['pass'] else 'FAIL'}** |")
    r_rel_s = "n/a" if d2["ratio_relative_primary"] is None else f"{d2['ratio_relative_primary']:.3f}"
    r_raw_s = "n/a" if d2["ratio_raw_units_secondary"] is None else f"{d2['ratio_raw_units_secondary']:.3f}"
    L.append(f"| **D-2** shrinkage ratio (scale-free, primary) | {r_rel_s} "
             f"(band {d2['band']}) |")
    L.append(f"| D-2 raw-unit ratio (secondary) | {r_raw_s} |")
    rc = d2.get("paired_block_bootstrap_ci_descriptive") or {}
    if rc.get("ci"):
        L.append(f"| D-2 paired bootstrap interval (descriptive) | "
                 f"[{rc['ci'][0]:.3f}, {rc['ci'][2]:.3f}], median {rc['ci'][1]:.3f}"
                 + (f"; {rc['undefined_frac']:.1%} of replicates undefined"
                    if rc.get("undefined_frac") else "") + " |")
    else:
        L.append(f"| D-2 paired bootstrap interval (descriptive) | "
                 f"not computed — {rc.get('reason', 'n/a')} |")
    L.append(f"| Wave-1 replication in the trailing20 arm | "
             f"{'YES' if d2['trailing20_replicated_wave1'] else 'NO'} |")
    L.append("")
    e = out["arms"]["har"]
    L.append(f"**Evaluated** {e['n_dates']:,} sessions ({e['first_eval']} to "
             f"{e['last_eval']}), {e['n_name_days']:,} name-days, {e['n_names']:,} "
             f"distinct names at H={out['config']['horizon']}, on rows where BOTH scales "
             f"are finite (AM-H4).")
    L.append("")

    L.append("## 1. Per-scheme deltas under both standardizers")
    L.append("")
    L.append("| Scheme | Δ vs B0, trailing20 | % of base | Δ vs B0, HAR | % of base | "
             "retained (scale-free) |")
    L.append("|---|---|---|---|---|---|")
    for s in p0.SCHEMES:
        a = out["arms"]["trail20"]["schemes"][s]["delta_vs_B0"]
        b = out["arms"]["har"]["schemes"][s]["delta_vs_B0"]
        pa, pb = a.get("pct_of_baseline"), b.get("pct_of_baseline")
        ret = "n/a" if (pa in (None, 0) or pb is None) else f"{pb / pa:+.2f}"
        star = " **(focus)**" if s == FOCUS_SCHEME else ""
        L.append(f"| `{s}`{star} | {_fmt_ci(a)} | {_fmt_pct(a)} | {_fmt_ci(b)} | "
                 f"{_fmt_pct(b)} | {ret} |")
    L.append("")
    L.append("Deltas are per-date **baseline minus scheme** mean pinball on the identical "
             "cross-section, so a positive number is skill. CI = circular block bootstrap, "
             f"block = {out['config']['bootstrap']['block']}, B = "
             f"{out['config']['bootstrap']['B']}, seed = {out['config']['bootstrap']['seed']} "
             "— wave-1's settings, unchanged. **The two arms' pinball levels are in "
             "different units** (each arm standardizes by its own scale), so the "
             "percent-of-baseline columns are the ones that compare; the raw columns are "
             "only ever read within an arm. A `retained` value near 1 means the scheme's "
             "edge is indifferent to the scale; near 0 means the edge WAS the scale.")
    L.append("")
    L.append("| Scheme | Δ vs B1, trailing20 | Δ vs B1, HAR |")
    L.append("|---|---|---|")
    for s in p0.SCHEMES:
        a = out["arms"]["trail20"]["schemes"][s]["delta_vs_B1"]
        b = out["arms"]["har"]["schemes"][s]["delta_vs_B1"]
        L.append(f"| `{s}` | {_fmt_ci(a)} ({_fmt_pct(a)}) | {_fmt_ci(b)} ({_fmt_pct(b)}) |")
    L.append("")

    L.append("## 2. X-2 — calibration of the nulls under each standardizer")
    L.append("")
    L.append("| Arm | B0 coverage | B1 coverage | B1 honest frac | S3 coverage | S5 coverage |")
    L.append("|---|---|---|---|---|---|")
    for arm in ARMS:
        ab = out["arms"][arm]
        L.append(f"| `{arm}` | {ab['baselines']['B0_pooled']['coverage_80']:.4f} | "
                 f"{ab['baselines']['B1_ownname']['coverage_80']:.4f} | "
                 f"{ab['baselines']['B1_ownname']['honest_frac']:.3f} | "
                 f"{ab['schemes']['S3_vol']['coverage_80']:.4f} | "
                 f"{ab['schemes']['S5_trend_vol']['coverage_80']:.4f} |")
    L.append("")
    L.append("Nominal is 0.800. Coverage is a hit rate, so it is unit-free and this is "
             "the one table that compares cleanly across arms. Descriptive only — no "
             "overlap-corrected test statistic is computed (see caveats).")
    L.append("")

    L.append("## 3. X-4 — is the new standardizer actually the better forward-vol forecast?")
    L.append("")
    fq = out["forecast_quality_X4"]
    L.append("| Arm | corr(log σ̂, log σ_fwd) | mean σ_fwd/σ̂ | median σ_fwd/σ̂ | "
             "sd log ratio | mean abs log ratio | n |")
    L.append("|---|---|---|---|---|---|---|")
    for arm in ARMS:
        f = fq.get(arm, {})
        if "corr_log_pred_vs_log_realized" not in f:
            L.append(f"| `{arm}` | n/a | n/a | n/a | n/a | n/a | {f.get('n', 0):,} |")
            continue
        L.append(f"| `{arm}` | {f['corr_log_pred_vs_log_realized']:.4f} | "
                 f"{f['mean_realized_over_pred']:.4f} | {f['median_realized_over_pred']:.4f} | "
                 f"{f['sd_log_ratio']:.4f} | {f['mean_abs_log_ratio']:.4f} | {f['n']:,} |")
    L.append("")
    better = fq.get("har_is_better_on")
    if better is None:
        L.append("Forecast quality could not be measured on this run — printed as a null, "
                 "not hidden.")
    elif better:
        L.append(f"The HAR blend is the better forward-vol read on: **{', '.join(better)}** "
                 f"(of three measures). σ_fwd is the realized 21d forward vol, a LABEL — "
                 f"look-ahead by construction and never fed to a cone.")
    else:
        L.append("**The HAR blend is NOT the better forward-vol forecast on any of the "
                 "three measures.** That is a null, and it is printed here at the top of "
                 "the interpretation rather than buried: a shrinking edge under a scale "
                 "that is not actually better is weaker evidence for the "
                 "vol-forecast-correction reading than the design assumed.")
    L.append("")

    L.append("## 3b. X-5 — vol-state-CONDITIONAL bias of each scale (post-run addendum)")
    L.append("")
    scb = out.get("state_conditional_bias_X5") or {}
    L.append(f"*{scb.get('provenance', X5_PROVENANCE)}*")
    L.append("")
    if "arms" not in scb:
        L.append(f"Not computed — {scb.get('reason', 'n/a')}. Printed as a null, not hidden.")
    else:
        nb = scb["k_bands"]
        L.append("| Arm | " + " | ".join(f"band {i}" for i in range(nb))
                 + " | spread (max−min) | overall |")
        L.append("|---|" + "---|" * (nb + 2))
        for arm in ARMS:
            ab = scb["arms"][arm]
            cells = " | ".join(
                ("n/a" if ab["bands"][f"band{i}"]["mean_log_realized_over_pred"] is None
                 else f"{ab['bands'][f'band{i}']['mean_log_realized_over_pred']:+.4f}")
                for i in range(nb))
            sp = ab["spread_max_minus_min"]
            L.append(f"| `{arm}` | {cells} | "
                     f"{'n/a' if sp is None else f'{sp:.4f}'} | "
                     f"{ab['overall_mean_log_ratio']:+.4f} |")
        L.append("")
        L.append(f"Cells are mean log(realized forward 21d vol / predicted) inside each "
                 f"`rvol_z` band ({scb['band_meaning']}). A POSITIVE number means the scale "
                 f"UNDER-predicts; negative means it OVER-predicts. The **spread** is the "
                 f"quantity wave-1's caveat is about: it is how much of the scale's error "
                 f"a vol-state cell can mechanically earn back by re-pricing the band.")
        L.append("")
        L.append("**Band construction is FULL-SPAN, not point-in-time.** The four `rvol_z` "
                 "bands are equal-frequency cuts of the whole evaluated span, not the "
                 "walk-forward's per-refit embargoed edges, so they carry a hindsight "
                 "whisker. Nothing downstream reads X-5 and no gate depends on it — but "
                 "X-5 does feed the headline mechanism claim, so treat the SIZE of the "
                 "bias-spread reduction as suggestive rather than as a point-in-time "
                 "measurement.")
        if scb.get("har_state_bias_spread_lower") is not None:
            if scb["har_state_bias_spread_lower"]:
                L.append("")
                L.append(f"The HAR scale's state-conditional bias spread is "
                         f"**{scb['spread_reduction_frac']:.0%} smaller** than the "
                         f"trailing-20d scale's. That is the mechanism, measured: there is "
                         f"less state-correlated error left for an `S3_vol` cell to "
                         f"correct, which is what the shrinkage in D-2 is made of.")
            else:
                L.append("")
                L.append("**The HAR scale's state-conditional bias spread is NOT smaller "
                         "than the trailing-20d scale's.** That is a null, and it weakens "
                         "the mechanistic story: whatever drove the shrinkage in D-2, it "
                         "was not a reduction in vol-state-correlated scale bias as "
                         "measured here.")
    L.append("")
    L.append("## 4. AM-H6 reproduction control — did the trailing20 arm reproduce wave-1?")
    L.append("")
    r = out["reproduction_control_AM_H6"]
    L.append(f"Source: {r['source']}.")
    L.append("")
    if r.get("exact_match") is not None:
        ref, mine = r["phase0_S3_vs_B0"], r["this_run_trail20_S3_vs_B0"]
        L.append("| Field | phase-0 artifact | this run (trailing20) | equal |")
        L.append("|---|---|---|---|")
        for k in r["fields_compared"]:
            L.append(f"| `{k}` | `{ref.get(k)}` | `{mine.get(k)}` | "
                     f"{'YES' if ref.get(k) == mine.get(k) else '**NO**'} |")
        L.append("")
        if r["exact_match"]:
            L.append(f"**All {len(r['fields_compared'])} fields match EXACTLY.** Both runs "
                     "are deterministic (fixed seeds, sorted store glob) over the same "
                     "panel, and the AM-H4 both-scales-finite intersection removed no "
                     "rows, so exact equality is the right bar — anything less would mean "
                     "the machinery is not wave-1's and the D-2 shrinkage ratio would be "
                     "meaningless. Checked against the committed artifact rather than the "
                     "writeup's rounded literals, which would cap the check at 3 "
                     "significant figures.")
        else:
            L.append(f"**MISMATCH on {len(r['mismatches'])} field(s)** — the comparison arm "
                     "is NOT wave-1's number, so the D-2 shrinkage ratio below rests on a "
                     "denominator this study cannot vouch for. Printed, not hidden.")
    else:
        w = r["wave1_published_rounded"]
        mine = r["this_run_trail20_S3_vs_B0"]
        L.append(f"- Wave-1 published (rounded): {w['mean_delta']:+.5f} "
                 f"[{w['ci'][0]:+.5f}, {w['ci'][1]:+.5f}]")
        L.append(f"- This run, trailing20 arm: {_fmt_ci(mine)}")
        L.append(f"- Absolute difference: {r['abs_diff_mean_delta']}; inside the published "
                 f"CI: {r['within_wave1_published_ci']}")
        L.append("")
        L.append(f"**Weaker check than intended** — {r['fallback_reason']}.")
    L.append("")

    L.append("## 5. Honest caveats")
    L.append("")
    for c in out["caveats"]:
        L.append(f"- {c}")
    L.append("")
    d = out["data"]
    L.append("## 6. Data + universe as actually read")
    L.append("")
    L.append(f"- Store `{d['store']}` — {d['files_seen']:,} parquet files, "
             f"{d['files_read']:,} read, {d['prefilter_pass']:,} past the cheap prefilter")
    L.append(f"- Calendar {d['calendar_first']} to {d['calendar_last']} "
             f"({d['calendar_sessions']} sessions)")
    L.append(f"- Wave-1 universe {d['panel_rows_wave1_universe']:,} rows across "
             f"{d['panel_names']:,} names; both-scales-finite panel "
             f"{d['panel_rows_both_scales_finite']:,} rows "
             f"({d['rows_dropped_by_scale_intersection_AM_H4']:,} dropped, AM-H4)")
    L.append(f"- Splits repaired on {d['split_repaired_names']:,} names; "
             f"{d['split_bars_stamped']:,} split-print bars stamped ineligible")
    L.append(f"- {d['prices']}")
    L.append("")
    L.append(f"- Import surface pinned before the run: {len(out['config']['import_surface_pinned'])} "
             "phase-0/engine signatures and frozen constants (the runner refuses to "
             "produce a number if any drifted)")
    L.append("")
    L.append("## 7. Frozen pre-registration (verbatim)")
    L.append("")
    L.append("```text")
    L.append(prereg)
    L.append("```")
    L.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", default=None, help="massive_stock_day directory")
    ap.add_argument("--max-names", type=int, default=None, help="smoke-run cap on files read")
    ap.add_argument("--out-json", default=str(RESULTS_JSON))
    ap.add_argument("--out-md", default=str(RESULTS_MD))
    ap.add_argument("--allow-stale", action="store_true",
                    help="run against a local massive_stock_day mirror 20+ trading "
                         "sessions behind (refused by default; the mirror is not "
                         "self-updating, so the study would be as of its frozen date)")
    args = ap.parse_args()

    store = p0.resolve_data_root(args.data_root)
    if store is None:
        print("HALT: no massive_stock_day parquets found on the resolution ladder "
              "(--data-root / $MACRO_PRIMARY_DATA / <repo>/data/massive_stock_day / "
              "primary checkout). Refusing to emit a study with no data.", flush=True)
        return 2
    # Reachable is not current: the ladder happily resolves a mirror frozen weeks ago.
    try:
        check_local_mirror_freshness(store,
                                     entrypoint="scripts/pick_forward_dist_phase1_har.py",
                                     allow_stale=args.allow_stale)
    except StaleLocalMirrorError:
        sys.exit(2)   # the banner already printed the lag and the fix command

    out, _t, _h = run_study(store, max_names=args.max_names)

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=1, default=str) + "\n",
                                   encoding="utf-8")
    write_markdown(out, Path(args.out_md))

    d1, d2 = out["D1_survival"], out["D2_shrinkage"]
    print("\n============ WAVE-1.5 DISCRIMINATOR (H=21, vol-standardized) ============")
    print(f"  D-1  S3_vol vs B0 under HAR : {_fmt_ci(d1)}  {_fmt_pct(d1)} of baseline"
          f"   -> {'PASS' if d1['pass'] else 'FAIL'}")
    print(f"  D-2  shrinkage ratio        : rel {d2['ratio_relative_primary']}  "
          f"(raw {d2['ratio_raw_units_secondary']}), band {d2['band']}")
    print(f"  VERDICT                     : {out['verdict']}")
    print(f"         {out['verdict_reason']}")
    print(f"\nwrote {args.out_json}\nwrote {args.out_md}\n"
          f"runtime {out['runtime_sec']:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
