"""Tests for the W2.7 leave-one-recession-out (LORO) recession-signal validator
(scripts/validate_business_cycle.py). Synthetic cycle frames with hand-planted
recessions so the OOS test is deterministic and the leak the wave removes is visible:
the operating point chosen per holdout is genuinely chosen on the OTHER recessions, and
the pooled headline is out-of-sample, not in-sample."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.grading_stats import jeffreys_ci  # noqa: E402
from scripts import validate_business_cycle as vbc  # noqa: E402


def _synthetic_cycle_frame(rng_seed: int = 0) -> pd.DataFrame:
    """A monthly frame engineered so the LORO fit genuinely VARIES by holdout and one
    recession is missed out-of-sample. Ingredients:

      • Three planted recessions of different depth: one SHALLOW (needs a loose −0.8-ish
        threshold to catch) and two DEEP (a tight −2.0 threshold catches them).
      • A benign 'growth scare' dip to −1.0 that becomes a FALSE POSITIVE only when the
        threshold is loose. So a loose threshold catches the shallow recession but incurs
        the FP; a tight threshold avoids the FP but misses the shallow recession.

    Consequence: when the SHALLOW recession is held out (train on the two deep ones), the
    objective — max-catch (both deep caught by anything ≤ their depth), then fewest FP —
    prefers a TIGHT threshold (avoids the scare FP). Scored OOS on the held-out shallow
    recession, that tight threshold MISSES it → oos_caught < n. The two deep holdouts
    instead admit a looser point, so the chosen op differs across folds."""
    idx = pd.date_range("1985-01-31", periods=360, freq="ME")  # 30y
    n = len(idx)
    mom = np.full(n, 0.6)          # benign expansion baseline
    diff = np.full(n, 70.0)
    rec = np.zeros(n, dtype=int)

    # (recession_start_i, dip_depth, dip_lead_months, rec_len)
    plants = [(60, -0.9, 8, 8),    # SHALLOW dip → only a loose threshold catches it
              (160, -2.2, 8, 8),   # deep dip
              (260, -2.3, 8, 8)]   # deep dip
    for start, depth, lead, length in plants:
        for j in range(lead):
            mom[start - lead + j] = depth * (j + 1) / lead
            diff[start - lead + j] = 45.0 - j    # broad-weak
        rec[start:start + length] = 1            # NBER band

    # benign growth scare (NO recession follows): a −1.0 dip that a LOOSE threshold
    # false-positives on, but a tight threshold ignores. Placed far from any recession.
    scare = 120
    for j in range(8):
        mom[scare + j] = -1.0
        diff[scare + j] = 44.0

    f = pd.DataFrame(index=idx)
    f["leading_mom6"] = mom
    f["leading_diffusion"] = diff
    f["nber_recession"] = rec
    return f


def test_evaluate_holdout_excludes_target() -> None:
    """With holdout_peak set, endo_caught counts only the OTHER recessions."""
    f = _synthetic_cycle_frame()
    peaks = vbc.nber_peaks_troughs(f["nber_recession"])
    r0 = peaks[0][0]
    full = vbc.evaluate(f, -1.0, 50.0, 3, 24, 18)
    held = vbc.evaluate(f, -1.0, 50.0, 3, 24, 18, holdout_peak=r0)
    # the held-out evaluation scores one fewer recession in its endo pool
    assert held["n_endogenous"] == full["n_endogenous"] - 1


def test_loro_is_out_of_sample_and_can_miss() -> None:
    """The core anti-overfit property: at least one holdout is chosen a rule on the OTHER
    recessions, and the pooled catch is reported OUT-OF-SAMPLE. On this synthetic frame
    the shallow recession is missed OOS by the deep-tuned rule → oos_caught < n."""
    f = _synthetic_cycle_frame()
    cfg = {"signal": {"diffusion_max": 50.0, "max_lead_window_m": 24, "lookahead_window_m": 18}}
    res = vbc.calibrate_loro(f, cfg)
    assert res["method"] == "LORO"
    assert res["n_endogenous"] == 3
    # per-holdout operating points are not all identical (the fit depends on which
    # recessions are in the training set → the point differs per holdout)
    chosen = {(r["train_operating_point"]["roc_threshold"],
               r["train_operating_point"]["min_consecutive_m"]) for r in res["per_holdout"]}
    assert len(chosen) >= 2, f"expected the LORO fit to vary by holdout, got {chosen}"
    # honest headline: out-of-sample catch is strictly below a perfect in-sample 3/3
    assert res["oos_caught"] < res["n_endogenous"]
    # the report ships a Jeffreys CI on the OOS catch rate (wide on N=3)
    ci = res["oos_catch_rate_jeffreys95"]
    assert ci is not None and ci[0] < res["oos_catch_rate"] < ci[1] or ci[0] <= res["oos_catch_rate"] <= ci[1]


def test_jeffreys_ci_is_honest_at_perfect_catch() -> None:
    """A 3/3 catch must NOT collapse to a zero-width [1,1] interval — the honesty the
    wave requires when reporting a tiny-N rate."""
    ci = jeffreys_ci(3, 3)
    assert ci is not None
    lo, hi = ci
    assert hi <= 1.0 and lo < 0.9   # wide lower bound: N=3 proves little
    # a 0/3 also has a non-trivial upper bound
    lo0, hi0 = jeffreys_ci(0, 3)
    assert lo0 == 0.0 and hi0 > 0.3
    assert jeffreys_ci(0, 0) is None


def test_loro_consensus_operating_point_is_a_grid_member() -> None:
    f = _synthetic_cycle_frame()
    cfg = {"signal": {"diffusion_max": 50.0, "max_lead_window_m": 24, "lookahead_window_m": 18}}
    res = vbc.calibrate_loro(f, cfg)
    op = res["consensus_operating_point"]
    thr_grid, mc_grid = vbc._grid(cfg)
    assert op["roc_threshold"] in [float(x) for x in thr_grid]
    assert op["min_consecutive_m"] in mc_grid
