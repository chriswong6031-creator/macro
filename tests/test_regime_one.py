"""Regime One tests — masterplan W2 acceptance (one test per mechanism).

Mechanisms guarded here:
  1. Flip attribution & veto — a dead-feed (renormalization) flip is VETOED and the
     label freezes; a genuine data flip passes. (The chaos-test core, #3.)
  2. Causal filtered P(Quad) — the emitted live probability is FILTERED (each point
     conditions on data up to that day only), a proper simplex, and flagged
     smoothed_hindsight=False (#16).
  3. Fused risk — confidence DEGRADES when tape & macro disagree on the inflation
     axis (the 84.2%/inflection leakage finding encoded as an explicit input, #1/#4).
  4. Freshness ledger — the compact bitmask round-trips per-leg availability + the
     degraded flag (#32).
  5. Passports — every regime_one number carries {basis, frame, freshness, n}.
  6. Gross mapping — the single versioned table is the one source; degraded holds
     gross no looser than caution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import regime_one as R

_CENTROID = {"Q1": (0.5, -0.5), "Q2": (0.5, 0.5), "Q3": (-0.5, 0.5), "Q4": (-0.5, -0.5)}


def _synthetic_scores(block=200, cycles=2, seed=1):
    rng = np.random.default_rng(seed)
    order = ["Q1", "Q2", "Q3", "Q4"] * cycles
    rows, quads = [], []
    for q in order:
        gc, ic = _CENTROID[q]
        rows.append(rng.normal([gc, ic], 0.15, (block, 2)))
        quads += [q] * block
    X = np.vstack(rows)
    idx = pd.bdate_range("2005-01-03", periods=len(X))
    return pd.DataFrame({"growth_score": X[:, 0], "inflation_score": X[:, 1], "quad": quads},
                        index=idx)


# --- helpers to fabricate a tape/macro read without touching the store ------- #
def _legs(names, weight=1.0, value=1):
    """A leg dict as _subread emits: {leg: {value, weight}}."""
    return {n: {"value": value, "weight": weight} for n in names}


def _read(growth_legs, inflation_legs, gscore, iscore, asof="2026-06-30"):
    """Minimal tape/macro-shaped dict for attribute_flip / fused_risk."""
    return {
        "growth": gscore, "inflation": iscore,
        "growth_legs": growth_legs, "inflation_legs": inflation_legs,
        "n_available": sum(1 for c in {**growth_legs, **inflation_legs}.values()
                           if c["value"] is not None),
        "passport": R._passport(basis="market", frame="latest",
                                freshness={"asof": asof, "expected_cadence": "D",
                                           "state": "fresh"}, n=0),
    }


# --------------------------------------------------------------------------- #
# 1. Flip attribution & veto — THE chaos test
# --------------------------------------------------------------------------- #
# A mildly-negative tape growth read: three legs +1, three -1 -> tape-only weighted
# mean is slightly NEGATIVE (the -1 legs carry equal or more weight). payrolls+indpro
# (+1, w0.5 each) are what hold the FULL axis positive; when they die the axis flips.
_TAPE_G_MIXED = {"copper_gold": {"value": 1, "weight": 1.0},
                 "xly_xlp": {"value": 1, "weight": 1.0},
                 "us2y_direction": {"value": 1, "weight": 0.5},
                 "iwm_spy": {"value": -1, "weight": 1.0},
                 "cyclical_defensive": {"value": -1, "weight": 1.0},
                 "breadth_direction": {"value": -1, "weight": 1.0}}


def test_dead_feed_flip_is_vetoed():
    """Kill payrolls+indpro (they go NaN) so the growth axis renormalizes over the
    survivors and the quad flips Q1->Q4 with NO leg-value change — the flip must be
    VETOED and the label frozen at Q1, degraded published loudly."""
    # PREV: tape mixed (slightly negative alone) + payrolls/indpro +1 hold axis positive.
    prev = {"tape": _read(dict(_TAPE_G_MIXED), _legs(R._TAPE_INFL, value=-1), 0.077, -0.5),
            "macro": _read({"payrolls_trend": {"value": 1, "weight": 0.5},
                            "indpro_trend": {"value": 1, "weight": 0.5}}, {}, 1.0, None),
            "_legacy_quad": "Q1"}
    # CUR: IDENTICAL tape values; payrolls & indpro DIED (value None). Axis renormalizes
    # over the tape survivors -> now slightly negative -> raw quad Q4.
    tape = _read(dict(_TAPE_G_MIXED), _legs(R._TAPE_INFL, value=-1), -0.09, -0.5)
    macro = _read({"payrolls_trend": {"value": None, "weight": 0.5},
                   "indpro_trend": {"value": None, "weight": 0.5}}, {}, None, None)

    flip = R.attribute_flip(prev, tape, macro, legacy_quad="Q4")
    assert flip["flipped"] is True
    assert flip["degraded"] is True, flip
    assert flip["label_quad"] == "Q1", "label must freeze at prior on a renorm-driven flip"
    assert set(flip["components"]["vanished_legs"]) >= {"payrolls_trend", "indpro_trend"}
    assert flip["components"]["renorm_share"] > 0.50
    assert flip["components"]["data_delta"] == 0.0, "no leg value changed"


def test_genuine_data_flip_passes():
    """When leg VALUES flip (no legs vanish), the flip is data-driven and must PASS —
    label moves to the new quad, not degraded."""
    prev_g = {**_legs(R._TAPE_GROWTH, value=1),
              "payrolls_trend": {"value": 1, "weight": 0.5},
              "indpro_trend": {"value": 1, "weight": 0.5}}
    prev = {"tape": _read({k: v for k, v in prev_g.items() if k in R._TAPE_GROWTH}, {}, 0.9, None),
            "macro": _read({k: v for k, v in prev_g.items() if k in R._MACRO_GROWTH}, {}, 1.0, None),
            "_legacy_quad": "Q1"}
    # CUR: every growth leg VALUE flips to -1, all legs still AVAILABLE (nothing died).
    cur_g = {**_legs(R._TAPE_GROWTH, value=-1),
             "payrolls_trend": {"value": -1, "weight": 0.5},
             "indpro_trend": {"value": -1, "weight": 0.5}}
    tape = _read({k: v for k, v in cur_g.items() if k in R._TAPE_GROWTH}, {}, -0.9, None)
    macro = _read({k: v for k, v in cur_g.items() if k in R._MACRO_GROWTH}, {}, -1.0, None)

    flip = R.attribute_flip(prev, tape, macro, legacy_quad="Q4")
    assert flip["flipped"] is True
    assert flip["degraded"] is False, flip
    assert flip["label_quad"] == "Q4", "a genuine data flip must be honored"
    assert flip["components"]["renorm_share"] <= 0.50


def test_first_run_no_prev_never_flips():
    tape = _read(_legs(R._TAPE_GROWTH, value=1), _legs(R._TAPE_INFL, value=-1), 0.5, -0.5)
    macro = _read({}, {}, None, None)
    flip = R.attribute_flip(None, tape, macro, legacy_quad="Q1")
    assert flip["flipped"] is False
    assert flip["degraded"] is False
    assert flip["label_quad"] == "Q1"


# --------------------------------------------------------------------------- #
# 2. Causal filtered P(Quad)
# --------------------------------------------------------------------------- #
def test_filtered_pquad_is_a_simplex_and_causal_flagged():
    out = R._causal_filtered_pquad(_synthetic_scores())
    assert out is not None
    p = out["regime_probs_filtered"]
    assert abs(sum(p.values()) - 1.0) < 1e-6
    assert all(0.0 <= v <= 1.0 for v in p.values())
    assert out["smoothed_hindsight"] is False
    # last synthetic block is Q4 -> filtered read should favor Q4
    assert out["modal_quad"] == "Q4"


def _overlapping_scores(seed=3):
    """A NOISY 4-quad cycle whose states OVERLAP (0.55 noise) so the smoother's
    future-peeking materially changes the posterior at transitions. The final cycle's
    Q3->Q4 transition sits inside the last-252 history window."""
    rng = np.random.default_rng(seed)
    order = (["Q1"] * 300 + ["Q2"] * 300 + ["Q3"] * 300 + ["Q4"] * 300
             + ["Q1"] * 300 + ["Q2"] * 300 + ["Q3"] * 120 + ["Q4"] * 120)
    rows = []
    for q in order:
        gc, ic = _CENTROID[q]
        rows.append(rng.normal([gc, ic], 0.55, 2))
    X = np.array(rows)
    idx = pd.bdate_range("2004-01-01", periods=len(X))
    return pd.DataFrame({"growth_score": X[:, 0], "inflation_score": X[:, 1],
                         "quad": order}, index=idx)


def test_filtered_differs_from_smoothed_at_a_transition():
    """The filtered posterior must NOT equal the smoothed (full-sample) posterior at a
    regime transition — that inequality is the whole reason we emit filtered as live
    history. Smoothing peeks at the future and is sharper across the transition."""
    from hmmlearn.hmm import GaussianHMM
    scores = _overlapping_scores()
    feats = ["growth_score", "inflation_score"]
    X = scores[feats].to_numpy(float)
    labels = scores["quad"].to_numpy()
    present = list(dict.fromkeys(labels))
    k = len(present)
    idx = {q: j for j, q in enumerate(present)}
    means = np.array([X[labels == q].mean(0) for q in present])
    covs = np.array([np.cov(X[labels == q].T) + np.eye(2) * 1e-3 for q in present])
    tm = np.full((k, k), 1e-6)
    for a, b in zip(labels[:-1], labels[1:]):
        tm[idx[a], idx[b]] += 1.0
    tm /= tm.sum(1, keepdims=True)
    sp = np.array([(labels == q).mean() for q in present]); sp /= sp.sum()
    m = GaussianHMM(n_components=k, covariance_type="full", init_params="", params="")
    m.startprob_, m.transmat_, m.means_, m.covars_ = sp, tm, means, covs
    smoothed = m.predict_proba(X)               # forward-backward (uses future)
    out = R._causal_filtered_pquad(scores)
    hist = out["history_filtered"]
    assert len(hist) > 10
    diffs = []
    for h in hist[1:]:
        d = scores.index.get_loc(pd.Timestamp(h["date"]))
        filt_vec = np.array([h[q] for q in present])
        sm_vec = smoothed[d]
        diffs.append(float(np.abs(filt_vec - sm_vec).max()))
    assert max(diffs) > 0.02, \
        f"filtered must diverge from smoothed somewhere; max diff {max(diffs):.4f}"


# --------------------------------------------------------------------------- #
# 3. Fused risk — confidence degrades at inflation inflection
# --------------------------------------------------------------------------- #
def test_confidence_degrades_on_inflation_axis_disagreement():
    # AGREE case: tape & macro both inflation -0.5 -> low uncertainty
    tape_ag = _read({}, {}, 0.5, -0.5)
    macro_ag = _read({}, {}, 0.5, -0.5)
    flip_ag = R.attribute_flip(None, tape_ag, macro_ag, "Q1")
    fused_ag = R._fused_risk(tape_ag, macro_ag, "Q1", flip_ag, base_conf=0.8)
    # DISAGREE case: tape inflation +0.5, macro inflation -0.5 -> inflection
    tape_dis = _read({}, {}, 0.5, 0.5)
    macro_dis = _read({}, {}, 0.5, -0.5)
    flip_dis = R.attribute_flip(None, tape_dis, macro_dis, "Q2")
    fused_dis = R._fused_risk(tape_dis, macro_dis, "Q2", flip_dis, base_conf=0.8)
    assert fused_dis["inflation_inflection"]["disagree"] is True
    assert fused_ag["inflation_inflection"]["disagree"] is False
    assert fused_dis["confidence"] < fused_ag["confidence"], \
        "inflation-axis inflection must drop confidence"


def test_degraded_read_holds_gross_at_caution_or_tighter():
    tape = _read(_legs(R._TAPE_GROWTH, value=1), _legs(R._TAPE_INFL, value=-1), 0.5, -0.5)
    macro = _read({}, {}, 0.5, -0.5)
    degraded = {"degraded": True, "label_quad": "Q1", "asof": "2026-06-30"}
    fused = R._fused_risk(tape, macro, "Q1", degraded, base_conf=0.9)
    assert fused["gross_factor"] <= R.RISK_STATE_GROSS["caution"]
    assert fused["degraded"] is True


# --------------------------------------------------------------------------- #
# 4. Freshness ledger — compact bitmask
# --------------------------------------------------------------------------- #
def test_freshness_bitmask_roundtrips():
    macro = {
        "growth_legs": {
            "payrolls_trend": {"value": 1, "weight": 0.5, "freshness": {"state": "fresh"}},
            "indpro_trend": {"value": 1, "weight": 0.5, "freshness": {"state": "dead"}},
            "wei_trend": {"value": 1, "weight": 0.5, "freshness": {"state": "slow"}},
            "gdpnow_trend": {"value": 1, "weight": 0.5, "freshness": {"state": "stale"}},
        },
        "inflation_legs": {
            "sticky_cpi_direction": {"value": 1, "weight": 0.5, "freshness": {"state": "fresh"}},
        },
    }
    mask = R.freshness_bitmask(macro, degraded=True)
    dec = R.decode_bitmask(mask)
    assert dec["payrolls"] is True     # fresh
    assert dec["indpro"] is False      # dead
    assert dec["wei"] is True          # slow counts as available
    assert dec["gdpnow"] is False      # stale drops out
    assert dec["sticky_cpi"] is True
    assert dec["degraded"] is True


def test_bitmask_is_a_small_int():
    macro = {"growth_legs": {}, "inflation_legs": {}}
    assert R.freshness_bitmask(macro, degraded=False) == 0
    # every bit set stays well within an int16
    full = {"growth_legs": {k + "_trend": {"value": 1, "weight": 1,
                                           "freshness": {"state": "fresh"}}
                            for k in ("payrolls", "indpro", "wei", "gdpnow")},
            "inflation_legs": {"sticky_cpi_direction": {"value": 1, "weight": 1,
                                                        "freshness": {"state": "fresh"}}}}
    assert 0 < R.freshness_bitmask(full, degraded=True) < 2 ** 16


# --------------------------------------------------------------------------- #
# 5. Passports on every number
# --------------------------------------------------------------------------- #
def test_passport_shape():
    p = R._passport(basis="release", frame="pit",
                    freshness={"asof": "2026-06-30", "expected_cadence": "M",
                               "state": "fresh"}, n=42)
    assert set(p) >= {"basis", "frame", "freshness", "n", "validation"}
    assert p["basis"] == "release" and p["frame"] == "pit" and p["n"] == 42


def test_gross_mapping_is_single_versioned_table():
    # the fused gross for every state must come from RISK_STATE_GROSS, floored
    for st, gf in R.RISK_STATE_GROSS.items():
        assert R._GROSS_FLOOR <= gf <= 1.0
    assert R.RISK_STATE_GROSS_VERSION   # a version string exists


# --------------------------------------------------------------------------- #
# 6. Full compute smoke on a synthetic classify-shaped frame (no store I/O for the
#    tape/HMM; macro falls back to reference legs)
# --------------------------------------------------------------------------- #
def test_compute_smoke_with_synthetic_frame(tmp_path):
    scores = _synthetic_scores()
    # add the c_ leg columns the tape read needs (all +/-1 matching the quad)
    frame = scores.copy()
    for leg in R._TAPE_GROWTH + R._MACRO_GROWTH:
        frame[f"c_growth_{leg}"] = 1
    for leg in R._TAPE_INFL + R._MACRO_INFL:
        frame[f"c_inflation_{leg}"] = -1
    frame["regime_confidence"] = 0.4
    out = R.compute(frame, release_axis_row=None, base_effect=None,
                    legacy_latest={}, prev=None, data_dir=tmp_path)
    assert out["schema"] == R.SCHEMA
    assert out["shadow"] is True
    for key in ("tape", "macro", "forward", "fused_risk", "flip_attribution"):
        assert key in out
    # passports present on the decision-facing reads
    assert "passport" in out["tape"] and "passport" in out["fused_risk"]
    assert out["fused_risk"]["gross_mapping_version"] == R.RISK_STATE_GROSS_VERSION


# --------------------------------------------------------------------------- #
# 7. FRED-OUTAGE CHAOS TEST end-to-end through compute() — the masterplan
#    acceptance: a dead payrolls/indpro feed must FREEZE the label, not flip the quad.
# --------------------------------------------------------------------------- #
def _classify_frame_from_row(gscore, iscore, growth_leg_vals, infl_leg_vals):
    """Build a minimal classify()-shaped one-row frame (with the c_ leg columns and a
    2y history so the HMM can fit) whose LAST row carries the given leg values."""
    scores = _synthetic_scores()            # 2y+ history so the causal HMM fits
    # append one crafted final row
    last_idx = scores.index[-1] + pd.tseries.offsets.BDay(1)
    row = {"growth_score": gscore, "inflation_score": iscore,
           "quad": R.raw_quad(gscore, iscore)}
    for leg in R._TAPE_GROWTH + R._MACRO_GROWTH:
        row[f"c_growth_{leg}"] = growth_leg_vals.get(leg)
    for leg in R._TAPE_INFL + R._MACRO_INFL:
        row[f"c_inflation_{leg}"] = infl_leg_vals.get(leg)
    row["regime_confidence"] = 0.4
    frame = scores.copy()
    for leg in R._TAPE_GROWTH + R._MACRO_GROWTH:
        frame[f"c_growth_{leg}"] = 1
    for leg in R._TAPE_INFL + R._MACRO_INFL:
        frame[f"c_inflation_{leg}"] = -1
    frame.loc[last_idx] = pd.Series(row)
    return frame


def test_fred_outage_chaos_freezes_label_not_flips(tmp_path):
    """END-TO-END: a prior regime_one on Q1 (payrolls/indpro alive) meets a session where
    payrolls & indpro are DEAD (NaN) and the raw growth axis renormalizes negative -> the
    legacy quad would read Q4. regime_one.compute() must VETO the flip, freeze label at Q1,
    and publish degraded=True — proving an outage cannot flip the quad (#3)."""
    # tape growth mixed -> slightly negative alone; infl legs all -1.
    tape_g = {"copper_gold": 1, "xly_xlp": 1, "us2y_direction": 1,
              "iwm_spy": -1, "cyclical_defensive": -1, "breadth_direction": -1}
    infl = {leg: -1 for leg in R._TAPE_INFL + R._MACRO_INFL}

    # PREV read: payrolls/indpro alive (+1) hold growth positive -> Q1.
    prev_growth = {**tape_g, "payrolls_trend": 1, "indpro_trend": 1,
                   "wei_trend": None, "gdpnow_trend": None}
    prev_frame = _classify_frame_from_row(0.08, -0.5, prev_growth, infl)
    prev_out = R.compute(prev_frame, release_axis_row=None, base_effect=None,
                         legacy_latest={}, prev=None, data_dir=tmp_path)
    assert prev_out["legacy_quad"] == "Q1"

    # CUR read: SAME tape values, payrolls & indpro DEAD (None). Renormalized growth axis
    # is now negative -> the legacy quad reads Q4.
    cur_growth = {**tape_g, "payrolls_trend": None, "indpro_trend": None,
                  "wei_trend": None, "gdpnow_trend": None}
    cur_frame = _classify_frame_from_row(-0.09, -0.5, cur_growth, infl)
    assert str(cur_frame["quad"].iloc[-1]) == "Q4", "raw legacy quad should have flipped to Q4"

    cur_out = R.compute(cur_frame, release_axis_row=None, base_effect=None,
                        legacy_latest={}, prev=prev_out, data_dir=tmp_path)

    # THE PROOF: legacy quad flipped to Q4, but the LABEL is frozen at Q1 and degraded.
    assert cur_out["legacy_quad"] == "Q4"
    assert cur_out["label_quad"] == "Q1", "label must FREEZE at Q1, not follow the renorm flip"
    assert cur_out["degraded"] is True
    assert "degraded_reason" in cur_out
    fa = cur_out["flip_attribution"]["components"]
    assert set(fa["vanished_legs"]) >= {"payrolls_trend", "indpro_trend"}
    assert fa["renorm_share"] > 0.50
    # fused risk on a degraded read holds gross no looser than caution
    assert cur_out["fused_risk"]["gross_factor"] <= R.RISK_STATE_GROSS["caution"]
