"""A quad label is a claim about that day's inputs — axis-dark days must not classify.

2026-08-08 incident (commit 901282ec209): the weekly deep-dive lane recomputed
the HK regime with the inflation axis NaN for the trailing 9 sessions (stale
runner cache + macro ffill runout) and apply_hysteresis CARRIED the last
confirmed label across the dark tail — site/hk_regime_timeline.json shipped
"Q3 Stagflation" on dates whose inflation input was null, while the daily
asia-close lane's full-input recompute of the same dates read Q1. Two writers,
two answers, and the label on the dark dates was a claim nothing supported.
(engine/store_guard.py refuses the degraded store overwrite; these tests pin
the other half — no label, and no shipped row, on an axis-dark day.)

The honest behavior is pinned at both layers every writer lane shares:
  * engine: apply_hysteresis emits NO confirmed label on a day whose raw quad
    is undefined (either axis NaN); machine memory is frozen across the gap so
    a short outage resumes without re-confirmation.
  * writers: the timeline exporters (build_hk / build_china — the same
    functions the daily asia-close and weekly deep-dive lanes both call, and
    mirrored by build_site.regime_timeline) ship only days with a label AND
    both axis scores, so the lanes cannot publish different answers for the
    same store and an axis-null date can never carry a definitive quad in any
    shipped artifact.

Run: .venv/bin/python -m pytest tests/test_quad_dark_day_disclosure.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.regime import apply_hysteresis  # noqa: E402

HYST_DAYS, SHOCK_Z = 5, 0.85


def _incident_axes() -> tuple[pd.Series, pd.Series]:
    """30 sessions establishing Q3 (g<0, i>=0), a 9-session dark tail on the
    inflation axis (the incident shape), then 4 healthy sessions."""
    idx = pd.bdate_range("2026-06-16", periods=43)
    g = pd.Series(-0.4, index=idx)
    i = pd.Series(0.4, index=idx)
    i.iloc[30:39] = np.nan
    return g, i


def _incident_hist() -> pd.DataFrame:
    """A store frame the way the live engine now writes it, over incident axes."""
    g, i = _incident_axes()
    out = apply_hysteresis(g, i, HYST_DAYS, SHOCK_Z)
    return pd.DataFrame({
        "quad": out["quad"],
        "growth_score": g,
        "inflation_score": i,
        "regime_confidence": 0.5,
        "liquidity": "neutral",
        "cycle": "mid",
    })


# --------------------------------------------------------------------------- engine


def test_dark_days_get_no_label_and_memory_resumes() -> None:
    g, i = _incident_axes()
    out = apply_hysteresis(g, i, HYST_DAYS, SHOCK_Z)
    assert (out["quad"].iloc[:30] == "Q3").all()
    dark = out.iloc[30:39]
    assert dark["quad"].isna().all(), \
        "an axis-dark day carried a confirmed label (the incident behavior)"
    # memory is frozen, not advanced: no candidate appears or counts down in the dark
    assert dark["pending_quad"].isna().all()
    assert (dark["pending_days"] == 0).all()
    # the held label resumes on the first healthy session — no re-confirmation wait
    assert (out["quad"].iloc[39:] == "Q3").all()


def test_label_implies_both_axes_valid_that_day() -> None:
    rng = np.random.default_rng(20260808)
    idx = pd.bdate_range("2015-01-01", periods=500)
    g = pd.Series(rng.uniform(-1, 1, len(idx)), index=idx)
    i = pd.Series(rng.uniform(-1, 1, len(idx)), index=idx)
    g[rng.random(len(idx)) < 0.08] = np.nan
    i[rng.random(len(idx)) < 0.08] = np.nan
    out = apply_hysteresis(g, i, HYST_DAYS, SHOCK_Z)
    labeled = out["quad"].notna()
    assert labeled.any()
    assert (labeled <= (g.notna() & i.notna())).all(), \
        "a confirmed label appeared on a day with a dark axis"


# -------------------------------------------------------------------------- writers


def test_hk_timeline_ships_no_axis_dark_date() -> None:
    from scripts.build_hk import hk_regime_timeline
    hist = _incident_hist()
    tl = hk_regime_timeline(hist)
    dark = {d.strftime("%Y-%m-%d") for d in hist.index[hist["inflation_score"].isna()]}
    assert dark and not (set(tl["dates"]) & dark)
    assert None not in tl["i"] and None not in tl["g"]
    assert set(tl["quad"]) <= {"Q1", "Q2", "Q3", "Q4"}
    # healthy sessions on BOTH sides of the gap still ship
    assert tl["dates"][-1] == hist.index[-1].strftime("%Y-%m-%d")
    json.dumps(tl, allow_nan=False)   # no NaN can leak into the artifact bytes


def test_hk_timeline_refuses_a_labeled_yet_dark_store_row() -> None:
    """The exact incident artifact shape: a store whose dark tail carries a
    label (as a pre-fix engine wrote it). The exporter itself keeps those rows
    out — writer agreement cannot depend on every lane running the same engine
    build against the same caches."""
    from scripts.build_hk import hk_regime_timeline
    hist = _incident_hist()
    hist["quad"] = hist["quad"].ffill()          # re-create the carried Q3 tail
    dark = {d.strftime("%Y-%m-%d") for d in hist.index[hist["inflation_score"].isna()]}
    tl = hk_regime_timeline(hist)
    assert not (set(tl["dates"]) & dark)
    assert None not in tl["i"]


def test_china_timeline_mirrors_the_same_contract() -> None:
    from scripts.build_china import china_regime_timeline
    hist = _incident_hist()
    carried = hist.copy()
    carried["quad"] = carried["quad"].ffill()
    dark = {d.strftime("%Y-%m-%d") for d in hist.index[hist["inflation_score"].isna()]}
    for frame in (hist, carried):
        tl = china_regime_timeline(frame)
        assert not (set(tl["dates"]) & dark)
        assert None not in tl["i"] and None not in tl["g"]
        assert set(tl["quad"]) <= {"Q1", "Q2", "Q3", "Q4"}
        json.dumps(tl, allow_nan=False)


def test_writers_are_a_pure_function_of_the_store() -> None:
    """Daily asia-close and weekly deep-dive both publish through this exporter:
    identical store input must yield an identical artifact, so two lanes can
    only disagree by writing different STORES — which engine/store_guard.py and
    weekly.yml's store+artifact pair-commit now police."""
    from scripts.build_hk import hk_regime_timeline
    hist = _incident_hist()
    assert hk_regime_timeline(hist) == hk_regime_timeline(hist.copy(deep=True))
