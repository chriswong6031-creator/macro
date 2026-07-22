"""Signal governor — the de-escalation-only measure→act loop. Tests enforce the
non-negotiable invariants from research/INTEL_HUB_V3_LOOP_CLOSING.md §6:

  1. Governor absent/corrupt ⇒ identity (all trust 1.0) ⇒ hub byte-identical to ungoverned.
  2. trust ≤ 1.0 ALWAYS; a governed opportunity ≤ ungoverned opportunity ALWAYS.
  3. A signal is demoted ONLY through the rigorous daily-HAC gate (n≥MIN_N, |t|≥T_SIG,
     wrong-sign IC) — never the pooled Spearman, never a short horizon that merely matured more.
  4. No track record ever sizes a position (asserted by construction — nothing here sizes).
"""
import json

import pytest

from engine import signal_governor as G


def _write(root, parts, obj):
    p = root.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))
    return p


def _radar_ic(by_horizon):
    return {"schema": "radar_ic.v1", "by_horizon": by_horizon}


def _hz(n_matured, mean_ic, t_hac, n_days):
    return {"n_matured": n_matured, "ic_daily_hac": {"mean_ic": mean_ic, "t_hac": t_hac, "n": n_days}}


# --------------------------------------------------------------------------- #
# 1. cold-start / degrade-safe = identity
# --------------------------------------------------------------------------- #
def test_cold_start_is_identity(tmp_path):
    out = G.compute(root=tmp_path, persist=True)
    assert out["n_demoted"] == 0
    assert all(v == 1.0 for v in out["trust"].values())
    # persisted, and load_trust reads back the identity map (or empty — both are no-ops)
    trust = G.load_trust(tmp_path)
    assert all(v == 1.0 for v in trust.values())


def test_absent_governor_file_load_is_empty(tmp_path):
    # nothing written ⇒ load_trust is {} ⇒ the hub ranks ungoverned
    assert G.load_trust(tmp_path) == {}


def test_corrupt_files_degrade_to_identity(tmp_path):
    (tmp_path / "data" / "radar").mkdir(parents=True)
    (tmp_path / "data" / "radar" / "radar_ic.json").write_text("{ this is not json")
    out = G.compute(root=tmp_path, persist=False)
    assert out["n_demoted"] == 0
    assert out["signals"]["radar"]["trust"] == 1.0


# --------------------------------------------------------------------------- #
# 2. the gate — demote ONLY on significant, sufficiently-matured, wrong-sign IC
# --------------------------------------------------------------------------- #
def test_gate_demotes_significant_wrong_sign(tmp_path):
    # PROPERLY matured: 25 daily ICs ≥ the lag-21 requirement ⇒ a valid, non-degenerate HAC
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(1977, -0.267, -8.29, 25)}))
    out = G.compute(root=tmp_path, persist=False)
    r = out["signals"]["radar"]
    assert r["demoted"] is True
    # trust = clamp(1 + 1.5*(-0.267), 0.25, 1) = 0.60 — a proportionate de-escalation, not deletion
    assert r["trust"] == pytest.approx(0.60, abs=0.005)
    assert out["n_demoted"] == 1


def test_gate_respects_min_n(tmp_path):
    # valid HAC (25 days), strongly inverted + significant, but too few matured obs ⇒ NOT demoted
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(G.MIN_N - 1, -0.30, -9.0, 25)}))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["demoted"] is False and r["trust"] == 1.0


def test_gate_respects_significance(tmp_path):
    # valid HAC, inverted but NOT significant (|t| < T_SIG) ⇒ NOT demoted
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(2000, -0.10, -1.4, 25)}))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["demoted"] is False and r["trust"] == 1.0


def test_gate_ignores_right_sign(tmp_path):
    # a HEALTHY signal (positive IC, significant) is never touched — de-escalation only
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(2000, 0.12, 6.0, 25)}))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["demoted"] is False and r["trust"] == 1.0


def test_trust_floor_never_deletes(tmp_path):
    # a wildly inverted signal floors at TRUST_FLOOR — de-escalate, never zero out
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(2000, -0.90, -12.0, 25)}))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["demoted"] is True and r["trust"] == G.TRUST_FLOOR


# --------------------------------------------------------------------------- #
# 3. rigor — a DEGENERATE HAC (lag > n_days) is refused, even when it looks significant
# --------------------------------------------------------------------------- #
def test_degenerate_long_horizon_is_refused(tmp_path):
    # THE live-data trap: 21d reads t=-8.3 but has only 11 daily ICs vs a lag-21 window
    # (lag > n ⇒ degenerate); the clean 10d HAC (19 ICs) reads t=-0.9, NOT significant.
    # The governor must REFUSE the degenerate 21d, read the valid 10d, and NOT demote.
    _write(tmp_path, G._RADAR_IC, _radar_ic({
        "10": _hz(3911, -0.0965, -0.896, 19),
        "21": _hz(1977, -0.267, -8.29, 11),
    }))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["horizon"] == "10"        # the valid, non-degenerate horizon governs
    assert r["demoted"] is False and r["trust"] == 1.0


def test_longest_VALID_horizon_wins_when_both_matured(tmp_path):
    # both horizons carry a valid HAC (n_days ≥ their lag); the longer, significant one governs
    _write(tmp_path, G._RADAR_IC, _radar_ic({
        "10": _hz(4000, -0.05, -0.9, 30),
        "21": _hz(2500, -0.267, -8.0, 30),
    }))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["horizon"] == "21" and r["demoted"] is True


def test_insufficient_hac_days_is_not_gradeable(tmp_path):
    # fewer daily ICs than the lag ⇒ no valid HAC ⇒ measuring, not demoted, honest note
    _write(tmp_path, G._RADAR_IC, _radar_ic({"21": _hz(2000, -0.30, -9.0, 11)}))
    r = G.compute(root=tmp_path, persist=False)["signals"]["radar"]
    assert r["demoted"] is False and r["trust"] == 1.0
    assert "need ≥21" in r["reason"] and "11 daily ICs" in r["reason"]   # distance-to-arming shown


# --------------------------------------------------------------------------- #
# invariant — load_trust can NEVER hand the ranker a boost, even if tampered
# --------------------------------------------------------------------------- #
def test_load_trust_clamps_tampered_values(tmp_path):
    _write(tmp_path, G._OUT, {"trust": {"radar": 1.9, "hub": 0.01, "x": None}})
    trust = G.load_trust(tmp_path)
    assert trust["radar"] == 1.0                 # a boost is clamped down to identity
    assert trust["hub"] == G.TRUST_FLOOR          # below-floor clamped up (still ≤ 1)
    assert "x" not in trust                        # None dropped
    assert all(v <= 1.0 for v in trust.values())


def test_trust_from_ic_monotone_and_bounded():
    assert G._trust_from_ic(0.5) == 1.0           # right sign ⇒ no change
    assert G._trust_from_ic(0.0) == 1.0
    assert G._trust_from_ic(None) == 1.0
    assert G._trust_from_ic(-0.02) < 1.0
    assert G._trust_from_ic(-0.02) > G._trust_from_ic(-0.20)   # more inverted ⇒ lower trust
    assert G._trust_from_ic(-5.0) == G.TRUST_FLOOR
    for ic in (-9, -1, -0.1, 0, 0.1, 5):
        assert G.TRUST_FLOOR <= G._trust_from_ic(ic) <= 1.0


# --------------------------------------------------------------------------- #
# 2 (integration) — a demoted feeder can only LOWER a name's opportunity
# --------------------------------------------------------------------------- #
def _bullish_radar_bundle():
    """A name every present feeder reads bullishly, with radar in POSITIVE_DIVERGENCE — the
    exact shape the inverted radar leg drives up. brain.strength>0 so opportunity is non-zero."""
    return {
        "brain": {"strength": 0.8, "priority": 0.6},
        "news": {"name": "Test", "sentiment_lean": "pos", "sectors": ["Tech"], "n_recent": 1},
        "alt": {"signal_score": 72, "action": "BUY"},
        "radar": {"state": "POSITIVE_DIVERGENCE", "lifecycle": "early", "within_basket_pct": 0.3},
        "standout": {"label": "BUY", "state": "UP", "off_high": -8.0},
    }


def test_dossier_governor_is_downward_only():
    from engine import intel_hub as H
    pidx = H.build_policy_index(None)      # canonical empty policy index (has by_ticker/by_sector)
    v = _bullish_radar_bundle()
    d0 = H._dossier("TEST", v, pidx, {}, gov=None)
    d_heal = H._dossier("TEST", v, pidx, {}, gov={"radar": 1.0})
    d_dem = H._dossier("TEST", v, pidx, {}, gov={"radar": 0.5})
    # invariant: governing NEVER raises opportunity
    assert d_dem["opportunity_score"] <= d0["opportunity_score"]
    assert d_heal["opportunity_score"] == d0["opportunity_score"]     # healthy trust ⇒ no-op
    # this bundle is bullish + radar-driven ⇒ the demotion MUST bite and be attributed
    assert d0["lean"] > 0 and d0["opportunity_score"] > 0
    assert d_dem["governed_by"] == ["radar"]
    assert d_dem["opportunity_score"] == pytest.approx(round(d0["opportunity_score"] * 0.5, 1), abs=0.11)
    assert d0["governed_by"] is None                                 # gov=None ⇒ untouched


def test_dossier_governor_skips_bearish_and_non_radar():
    from engine import intel_hub as H
    v = _bullish_radar_bundle()
    v["radar"]["state"] = "NEGATIVE_DIVERGENCE"    # radar not bullishly driving ⇒ no demotion
    d = H._dossier("TEST", v, H.build_policy_index(None), {}, gov={"radar": 0.4})
    assert d["governed_by"] is None
    assert d["governor_mult"] == 1.0
