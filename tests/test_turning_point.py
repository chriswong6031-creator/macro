"""Tests for engine/turning_point.py — the display-only turning-point fragility
guardrail. Engineered `latest`-shaped dicts + graceful degradation + the
load-bearing 'never scored' invariant. See reports/factor-exposure-phase0 sibling
docs and DECISIONS for the display-only discipline."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.turning_point import (snapshot, _gate, MACRO_SHOCK_CLUSTER,  # noqa: E402
                                   append_log, last_active)
from engine import conditions as C  # noqa: E402


def _latest(*, concentrated=True, primary="oil_shock", strength=2.6,
            cluster=("oil_shock", "real_rate_shock"), roro=-1.4, cap_strong=False,
            transition="STABLE", gap_bp=40, put_state="put-present",
            absorption_pctile=0.94):
    """A latest.json-shaped dict with knobs for each gate input."""
    scores = [{"driver": d, "strength": (strength if d == primary else 1.7),
               "projection": -(strength if d == primary else 1.7)}
              for d in cluster]
    return {
        "transition_state": transition,
        "cross_asset": {"asof": "2026-06-15",
                        "verdict": "concentrated" if concentrated else "diversified",
                        "absorption_pctile_5y": absorption_pctile},
        "market_drivers": {"asof": "2026-06-15", "verdict": "clear", "primary": primary,
                           "primary_label": "oil spiking", "primary_label_zh": "油价飙升",
                           "strength": strength, "scores": scores},
        "conditions": {"risk_appetite": {"roro": roro, "roro_state": "risk-off"},
                       "capitulation": {"score": 2 if cap_strong else 0, "strong": cap_strong}},
        "dislocation": {"put_state": put_state},
        "fed_path": {"gap": {"gap_bp": gap_bp}},
    }


# --- the gate: conjunction only -------------------------------------------------

def test_gate_fires_on_full_conjunction() -> None:
    g = _gate(_latest(), "STABLE")
    assert g["raw_fire"] is True
    assert g["one_factor"] is True and g["macro_shock"] is True
    assert g["stretched"]  # at least one stretch tag


def test_gate_silent_without_one_factor() -> None:
    # a diversified tape is the everyday case — must NOT fire
    assert _gate(_latest(concentrated=False), "STABLE")["raw_fire"] is False


def test_gate_silent_without_macro_shock() -> None:
    # an AI/semis or crypto driver is not a macro-shock cluster member
    lt = _latest(primary="ai_semis", cluster=("ai_semis",), strength=3.0)
    g = _gate(lt, "STABLE")
    assert g["macro_shock"] is False and g["raw_fire"] is False


def test_gate_silent_without_stretch() -> None:
    # one-factor + macro driver but calm positioning (no RORO tail / cap / transition / pinned)
    lt = _latest(roro=-0.2, cap_strong=False, transition="STABLE", gap_bp=80)
    g = _gate(lt, "STABLE")
    assert g["one_factor"] and g["macro_shock"]
    assert g["stretched"] == [] and g["raw_fire"] is False


def test_macro_shock_via_cluster_cofire() -> None:
    # primary below the strong bar, but two cluster legs co-fire above the cluster bar
    lt = _latest(primary="usd_shock", strength=1.6,
                 cluster=("usd_shock", "real_rate_shock"))
    assert _gate(lt, "STABLE")["macro_shock"] is True
    assert set(MACRO_SHOCK_CLUSTER) >= {"oil_shock", "usd_shock"}


# --- the Fed-put guard ----------------------------------------------------------

def test_put_present_is_reversible_no_meanreversion_claim() -> None:
    s = snapshot(_latest(put_state="put-present"), "STABLE")
    assert s["present"] and s["state"] == "fragile-reversible"
    assert s["defer_to"] is None
    body = (s["message_en"] + " " + s["size_note_en"]).lower()
    # the reversible copy must NEVER promise a bounce / a buy
    for banned in ("bounce", "rebound", "buyable", "buy the", "mean-revert", "snap back up"):
        assert banned not in body


def test_put_absent_upgrades_to_structural_and_defers() -> None:
    s = snapshot(_latest(put_state="put-absent"), "STABLE")
    assert s["state"] == "fragile-structural"
    assert s["defer_to"] == "dislocation"
    assert "fed put absent" in s["headline_en"].lower()


def test_missing_fedput_defaults_to_safe_reversible() -> None:
    # no dislocation block at all -> must NOT claim the structural (falling-knife) case
    lt = _latest()
    lt.pop("dislocation")
    s = snapshot(lt, "STABLE")
    assert s["state"] == "fragile-reversible" and s["defer_to"] is None


# --- hysteresis / cooldown ------------------------------------------------------

def test_cooldown_shows_one_more_day() -> None:
    calm = _latest(concentrated=False)  # gate off today
    assert snapshot(calm, "STABLE", prev_active=False)["state"] == "normal"
    assert snapshot(calm, "STABLE", prev_active=False)["present"] is False
    cooling = snapshot(calm, "STABLE", prev_active=True)
    assert cooling["state"] == "cooling" and cooling["present"] is True
    assert cooling["active"] is False  # cooling does not re-arm the cooldown


def test_active_flag_tracks_raw_fire() -> None:
    assert snapshot(_latest(), "STABLE")["active"] is True


# --- robustness -----------------------------------------------------------------

def test_empty_latest_degrades_quietly() -> None:
    for arg in ({}, {"cross_asset": None, "market_drivers": None}):
        s = snapshot(arg, None, prev_active=False)
        assert s["present"] is False and s["state"] == "normal"


def test_snapshot_is_json_safe() -> None:
    import json
    json.dumps(snapshot(_latest(), "TRANSITIONING"), default=str)


# --- the load-bearing invariant: NEVER scored -----------------------------------

def test_turning_point_is_display_only_never_scored() -> None:
    # No scoring surface may read turning_point — not the axes, not the quad, not the
    # macro-risk score. (Same discipline as the complacency gauge.)
    root = Path(__file__).resolve().parent.parent
    axes_src = (root / "engine" / "axes.py").read_text()
    regime_src = (root / "engine" / "regime.py").read_text()
    cond_src = (root / "engine" / "conditions.py").read_text()
    mrs_region = cond_src[cond_src.index("def _macro_risk_legs"):]
    for src in (axes_src, regime_src, mrs_region):
        assert "turning_point" not in src


# --- the MRS transition-leg clamp scaffold (default == byte-identical) -----------

def test_mrs_transition_high_default_is_one() -> None:
    # The A/B scaffold must default to the pre-existing 1.0 — no live behaviour change.
    assert C._mrs_transition_high() == 1.0
    assert C._mrs_transition_val("TRANSITIONING") == 1.0
    assert C._mrs_transition_val("NEW_REGIME") == 1.0
    assert C._mrs_transition_val("WEAKENING") == 0.5
    assert C._mrs_transition_val("STABLE") == 0.0


def test_mrs_transition_high_is_config_driven(monkeypatch) -> None:
    # Flipping the knob to 0.5 is the calibration A/B; prove it flows through.
    monkeypatch.setattr(C.config, "load",
                        lambda: {"engine": {"macro_overlay": {"transition_high": 0.5}}})
    assert C._mrs_transition_high() == 0.5
    assert C._mrs_transition_val("TRANSITIONING") == 0.5
    assert C._mrs_transition_val("WEAKENING") == 0.5  # unchanged
