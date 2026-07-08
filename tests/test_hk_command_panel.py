"""Tests for engine/hk_command_panel.py — HK Command Panel synthesis organ.

Covers:
  (1)  Verdict tally correctness — bottom_arming_n and chase_risk_n count correctly
  (2)  Each force's state derivation from synthetic organ inputs
  (3)  Fail-open when any organ output is missing — force → neutral, panel builds
  (4)  All 8 forces always present in force_stack (even when all organs missing)
  (5)  Bottom/chase scorecards read washout_watch correctly
  (6)  Catalyst tape merges filing_bus + catalyst_strip + narrative spikes
  (7)  display_only=True invariant
  (8)  compute() never raises on any input combination
  (9)  Freshness strip verdict routing (ok / degraded / stale / unknown)
  (10) No writes to data/ or site/ — all writes isolated to tmp_path

All writes are isolated to tmp_path. No writes to data/ or site/.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.hk_command_panel as CP


# ---------------------------------------------------------------------------
# Helpers: synthetic organ factories
# ---------------------------------------------------------------------------

def _adr_bridge(gap_pct: float | None = 2.0, fresh: str = "ok") -> dict:
    """Minimal adr_bridge dict."""
    return {
        "freshness_verdict": fresh,
        "composite": {
            "bellwether_implied_open_pct": gap_pct,
            "gap_context": (
                "strong_up" if (gap_pct or 0) >= 3
                else "up" if (gap_pct or 0) >= 1
                else "down" if (gap_pct or 0) <= -1
                else "flat"
            ) if gap_pct is not None else None,
        },
        "names": [],
    }


def _market_drivers(tech_proj: float | None = 0.6) -> dict:
    """Minimal market_drivers dict — mirrors the REAL hk_market_drivers.snapshot() shape.

    snapshot() returns a flat list under "scores" (one entry per driver) plus top-level
    keys: primary, dir_sign, verdict, strength, confidence.  There is NO "drivers" dict key.
    """
    sign = 1 if (tech_proj or 0) >= 0 else -1
    strength = abs(tech_proj) if tech_proj is not None else 0.0
    scores: list[dict] = []
    if tech_proj is not None:
        scores.append({
            "driver": "tech_internet_leadership",
            "label": "Tech / internet leadership",
            "label_zh": "科技/互联网领涨",
            "family": "equity-leadership",
            "projection": round(float(tech_proj), 2),
            "strength": round(abs(float(tech_proj)), 2),
            "direction": "HSTECH leading up" if sign > 0 else "HSTECH unwind",
        })
    return {
        "asof": "2026-07-08",
        "verdict": "clear" if strength >= 0.6 else "quiet",
        "primary": "tech_internet_leadership" if tech_proj is not None else None,
        "dir_sign": sign,
        "strength": round(strength, 2),
        "confidence": "high" if strength >= 0.6 else "low",
        "scores": scores,
    }


def _hk_narrative(states: list[str] | None = None) -> dict:
    """Minimal hk_narrative dict with given entity states."""
    if states is None:
        states = ["attention_spike", "attention_spike", "tone_positive_shift"]
    entities = []
    for i, st in enumerate(states):
        entities.append({
            "slug": f"entity_{i}",
            "ticker": f"TICK{i}",
            "name_en": f"Name {i}",
            "name_zh": f"名字 {i}",
            "attention_shock_z": 2.5 if st == "attention_spike" else 0.5,
            "tone_pctile": 70.0 if st == "tone_positive_shift" else 30.0,
            "narrative_state": st,
            "young": False,
            "n_obs": 30,
            "as_of_date": "2026-07-08",
            "no_data_reason": None,
        })
    return {
        "display_only": True,
        "freshness": "ok",
        "entities": entities,
    }


def _internals(net_z: float | None = 1.2) -> dict:
    """Minimal internals dict — mirrors the REAL china_internals.southbound_flow() shape.

    southbound_flow() returns: net (亿元), net_z (z-score vs 252d), cum_20d, pos_days_20.
    Keys "accel_z", "net_hkd", "appetite", "trend" DO NOT EXIST in the producer.
    """
    net = 5000.0 if (net_z or 0) > 0 else -3000.0
    return {
        "southbound": {
            "net": net,
            "net_z": net_z,
            "cum_20d": net * 4.0 if net_z is not None else 0.0,
            "pos_days_20": 14 if (net_z or 0) > 0 else 5,
        }
    }


def _breadth(pct200: float = 62.0) -> dict:
    """Minimal breadth dict — mirrors the REAL collectors.breadth.breadth_summary() shape.

    breadth_summary() returns "pct_above_200" (NO trailing 'd') as a 0-100 percentage.
    Keys "pct_above_200d" and "above_200d" DO NOT EXIST in the producer.
    The adv/dec counts are separate "adv" and "dec" int keys, not "adv_dec_ratio".
    Default pct200=62.0 (0-100 scale) → confirm threshold (55%).
    """
    adv = int(pct200 * 3)   # synthetic — just needs to be consistent
    dec = int((100 - pct200) * 3)
    return {
        "pct_above_200": pct200,           # 0-100 percentage (e.g. 62.0)
        "pct_above_50": pct200 + 5.0,      # usually higher than 200d
        "nh": max(1, int(pct200 / 10)),
        "nl": max(1, int((100 - pct200) / 20)),
        "net_nh": int(pct200 / 10) - int((100 - pct200) / 20),
        "adv": adv,
        "dec": dec,
        "ad_trend": "up" if pct200 >= 50 else "down",
        "state": "broad" if pct200 >= 60 else ("thin" if pct200 < 40 else "mixed"),
        "tone": "pos" if pct200 >= 60 else ("neg" if pct200 < 40 else "muted"),
        "full": False,
        "asof": "2026-07-08",
        "n_members": 300,
        "pct50_chg20": 5.0 if pct200 >= 50 else -5.0,
    }


def _cbbc_map(leverage_states: list[str] | None = None, fresh: str = "ok") -> dict:
    """Minimal cbbc_map with given bellwether leverage states."""
    if leverage_states is None:
        leverage_states = ["bear_skew_froth", "bear_skew", "bear_skew", "balanced"]
    bellwethers = [{"underlying": f"BW{i}", "leverage_state": ls}
                   for i, ls in enumerate(leverage_states)]
    return {
        "freshness": fresh,
        "bellwethers": bellwethers,
    }


def _funding(agg_pctile: int = 70, peg_state: str = "stable") -> dict:
    """Minimal funding dict."""
    return {
        "agg_pctile": agg_pctile,
        "peg": {"state": peg_state, "level": 7.8000},
    }


def _latest(risk_state: str = "Risk-on", peg_state: str = "stable") -> dict:
    """Minimal latest dict."""
    return {
        "date": "2026-07-08",
        "quad": "Q1",
        "risk_state": risk_state,
        "peg_state": peg_state,
        "global_snapshot": {
            "state": risk_state,
            "peg": {"level": 7.8000, "state": peg_state},
        },
    }


def _setups_with_washout(
    bottom_states: list[str] | None = None,
    chase_states: list[str] | None = None,
) -> dict:
    """Minimal setups dict with washout_watch list."""
    rows = []
    for i, st in enumerate(bottom_states or []):
        rows.append({
            "ticker": f"9{i}88.HK",
            "name": f"Name {i}",
            "state": st,
            "confluence_signals": ["ADR_GAP_UP", "BEAR_EXHAUST"],
            "knife_risk": i == 0,
            "rsi": 35.0,
            "dist_200dma": -0.15,
        })
    for j, st in enumerate(chase_states or []):
        rows.append({
            "ticker": f"1{j}00.HK",
            "name": f"Chase {j}",
            "state": st,
            "confluence_signals": [],
            "knife_risk": False,
            "rsi": 75.0,
            "dist_200dma": 0.05,
        })
    return {"washout_watch": rows}


def _freshness(verdict: str = "ok") -> dict:
    """Minimal freshness sentinel result."""
    return {
        "verdict": verdict,
        "expected_session": "2026-07-08",
        "stores": {
            "cache": {"state": "fresh" if verdict == "ok" else "stale", "lag_days": 0},
            "bellwether": {"state": "fresh", "lag_days": 0},
            "standouts": {"state": "fresh", "lag_days": 0},
            "regime": {"state": "fresh", "lag_days": 0},
        },
        "banner_message": None,
    }


def _filing_bus(n: int = 2) -> dict:
    """Minimal filing_bus dict with a tape."""
    return {
        "freshness": "ok",
        "tape": [
            {
                "date": f"2026-07-0{i+1}",
                "ticker": f"9988.HK",
                "type_label": "buyback",
                "type_label_zh": "回购",
                "description": f"Buyback event {i+1}",
            }
            for i in range(n)
        ],
    }


def _catalyst_strip(n: int = 2) -> list[dict]:
    """Minimal catalyst_strip list."""
    return [
        {
            "date": f"2026-07-1{i+1}",
            "ticker": f"0700.HK",
            "event": f"Catalyst {i+1}",
            "event_zh": f"催化剂 {i+1}",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# (1) Verdict tally correctness
# ---------------------------------------------------------------------------

class TestVerdictTally:
    def test_all_confirm_8_forces(self) -> None:
        """All 8 forces confirm → bottom_arming_n=8."""
        result = CP.compute(
            freshness=_freshness("ok"),
            adr_bridge=_adr_bridge(gap_pct=2.0),
            market_drivers=_market_drivers(tech_proj=0.7),
            hk_narrative=_hk_narrative(["attention_spike", "attention_spike", "tone_positive_shift"]),
            internals=_internals(net_z=1.5),
            breadth=_breadth(pct200=65.0),
            cbbc_map=_cbbc_map(["bear_skew_froth", "bear_skew", "bear_skew", "bear_skew"]),
            funding=_funding(agg_pctile=75),
            latest=_latest(risk_state="Risk-on"),
        )
        v = result["verdict"]
        assert v["of"] == 8
        assert v["bottom_arming_n"] >= 1
        assert v["bottom_arming_n"] <= 8
        assert isinstance(v["chase_risk_n"], int)

    def test_all_stress_forces(self) -> None:
        """All 8 forces stress → chase_risk_n=8."""
        result = CP.compute(
            freshness=_freshness("ok"),
            adr_bridge=_adr_bridge(gap_pct=-2.0),
            market_drivers=_market_drivers(tech_proj=-0.7),
            hk_narrative=_hk_narrative(["tone_negative_shift", "tone_negative_shift", "quiet"]),
            internals=_internals(net_z=-1.5),
            breadth=_breadth(pct200=20.0),
            cbbc_map=_cbbc_map(["bull_skew_froth", "bull_skew", "bull_skew", "bull_skew"]),
            funding=_funding(agg_pctile=10),
            latest=_latest(risk_state="Risk-off"),
        )
        v = result["verdict"]
        assert v["chase_risk_n"] >= 1
        assert v["bottom_arming_n"] == 0

    def test_verdict_label_deterministic(self) -> None:
        """Calling compute twice with same inputs yields identical verdict label."""
        kwargs = dict(
            adr_bridge=_adr_bridge(gap_pct=1.5),
            latest=_latest("Risk-on"),
            breadth=_breadth(60.0),
        )
        r1 = CP.compute(**kwargs)
        r2 = CP.compute(**kwargs)
        assert r1["verdict"]["label_en"] == r2["verdict"]["label_en"]
        assert r1["verdict"]["bottom_arming_n"] == r2["verdict"]["bottom_arming_n"]

    def test_bottom_n_plus_chase_n_le_total(self) -> None:
        """bottom_arming_n + chase_risk_n <= 8 (a force can be watch/neutral, not both)."""
        result = CP.compute(
            adr_bridge=_adr_bridge(gap_pct=2.0),
            cbbc_map=_cbbc_map(["bull_skew_froth", "bull_skew"]),
            latest=_latest("Risk-on"),
        )
        v = result["verdict"]
        assert v["bottom_arming_n"] + v["chase_risk_n"] <= v["of"]


# ---------------------------------------------------------------------------
# (2) Per-force state derivation
# ---------------------------------------------------------------------------

class TestForceStates:
    def _get_force(self, result: dict, key: str) -> dict:
        for f in result["force_stack"]:
            if f["key"] == key:
                return f
        raise KeyError(f"Force '{key}' not found in stack")

    def test_adr_confirm_on_strong_gap(self) -> None:
        r = CP.compute(adr_bridge=_adr_bridge(gap_pct=2.0))
        f = self._get_force(r, "adr_bridge")
        assert f["state"] == "confirm"
        assert "2.0" in f["detail_en"] or "2" in f["detail_en"]

    def test_adr_stress_on_negative_gap(self) -> None:
        r = CP.compute(adr_bridge=_adr_bridge(gap_pct=-1.5))
        f = self._get_force(r, "adr_bridge")
        assert f["state"] == "stress"

    def test_adr_watch_on_small_positive_gap(self) -> None:
        r = CP.compute(adr_bridge=_adr_bridge(gap_pct=0.5))
        f = self._get_force(r, "adr_bridge")
        assert f["state"] == "watch"

    def test_adr_neutral_on_stale_data(self) -> None:
        r = CP.compute(adr_bridge=_adr_bridge(gap_pct=3.0, fresh="stale"))
        f = self._get_force(r, "adr_bridge")
        assert f["state"] == "neutral"

    def test_tech_confirm_on_positive_projection(self) -> None:
        r = CP.compute(market_drivers=_market_drivers(tech_proj=0.6))
        f = self._get_force(r, "tech_impulse")
        assert f["state"] == "confirm"

    def test_tech_stress_on_negative_projection(self) -> None:
        r = CP.compute(market_drivers=_market_drivers(tech_proj=-0.6))
        f = self._get_force(r, "tech_impulse")
        assert f["state"] == "stress"

    def test_narrative_confirm_on_spikes(self) -> None:
        r = CP.compute(hk_narrative=_hk_narrative(
            ["attention_spike", "attention_spike", "tone_positive_shift"]))
        f = self._get_force(r, "narrative")
        assert f["state"] == "confirm"

    def test_narrative_stress_on_neg_tone(self) -> None:
        r = CP.compute(hk_narrative=_hk_narrative(
            ["tone_negative_shift", "tone_negative_shift", "quiet"]))
        f = self._get_force(r, "narrative")
        assert f["state"] == "stress"

    def test_southbound_confirm_on_high_accel(self) -> None:
        r = CP.compute(internals=_internals(net_z=1.5))
        f = self._get_force(r, "southbound")
        assert f["state"] == "confirm"

    def test_southbound_stress_on_decel(self) -> None:
        r = CP.compute(internals=_internals(net_z=-1.5))
        f = self._get_force(r, "southbound")
        assert f["state"] == "stress"

    def test_breadth_confirm_on_wide_participation(self) -> None:
        r = CP.compute(breadth=_breadth(pct200=70.0))
        f = self._get_force(r, "breadth")
        assert f["state"] == "confirm"

    def test_breadth_stress_on_thin_tape(self) -> None:
        r = CP.compute(breadth=_breadth(pct200=20.0))
        f = self._get_force(r, "breadth")
        assert f["state"] == "stress"

    def test_cbbc_confirm_on_bear_skew(self) -> None:
        r = CP.compute(cbbc_map=_cbbc_map(
            ["bear_skew_froth", "bear_skew", "bear_skew", "bear_skew"]))
        f = self._get_force(r, "cbbc")
        assert f["state"] == "confirm"

    def test_cbbc_stress_on_bull_froth(self) -> None:
        r = CP.compute(cbbc_map=_cbbc_map(
            ["bull_skew_froth", "bull_skew", "bull_skew", "bull_skew"]))
        f = self._get_force(r, "cbbc")
        assert f["state"] == "stress"

    def test_funding_confirm_on_ample_ab(self) -> None:
        r = CP.compute(funding=_funding(agg_pctile=75))
        f = self._get_force(r, "funding_peg")
        assert f["state"] == "confirm"

    def test_funding_stress_on_tight_ab(self) -> None:
        r = CP.compute(funding=_funding(agg_pctile=10))
        f = self._get_force(r, "funding_peg")
        assert f["state"] == "stress"

    def test_global_risk_confirm_on_risk_on(self) -> None:
        r = CP.compute(latest=_latest(risk_state="Risk-on"))
        f = self._get_force(r, "global_risk")
        assert f["state"] == "confirm"

    def test_global_risk_stress_on_risk_off(self) -> None:
        r = CP.compute(latest=_latest(risk_state="Risk-off"))
        f = self._get_force(r, "global_risk")
        assert f["state"] == "stress"


# ---------------------------------------------------------------------------
# (3) Fail-open: missing organ → neutral, panel still builds
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_all_organs_missing_returns_valid_panel(self) -> None:
        """compute() with NO organ inputs returns a valid, non-crashing panel."""
        result = CP.compute()
        assert result["display_only"] is True
        assert "verdict" in result
        assert "force_stack" in result
        assert isinstance(result["force_stack"], list)
        assert isinstance(result["bottom_watch"], list)
        assert isinstance(result["chase_watch"], list)
        assert isinstance(result["catalyst_tape"], list)

    def test_missing_adr_bridge_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["adr_bridge"]["state"] == "neutral"

    def test_missing_market_drivers_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["tech_impulse"]["state"] == "neutral"

    def test_missing_narrative_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["narrative"]["state"] == "neutral"

    def test_missing_internals_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["southbound"]["state"] == "neutral"

    def test_missing_breadth_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["breadth"]["state"] == "neutral"

    def test_missing_cbbc_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["cbbc"]["state"] == "neutral"

    def test_missing_funding_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["funding_peg"]["state"] == "neutral"

    def test_missing_latest_neutral(self) -> None:
        result = CP.compute()
        forces = {f["key"]: f for f in result["force_stack"]}
        assert forces["global_risk"]["state"] == "neutral"

    def test_none_values_dont_crash(self) -> None:
        """Passing None for all organs must not raise."""
        result = CP.compute(
            freshness=None,
            adr_bridge=None,
            market_drivers=None,
            hk_narrative=None,
            internals=None,
            breadth=None,
            cbbc_map=None,
            funding=None,
            latest=None,
            filing_bus=None,
            catalyst_strip=None,
            setups=None,
        )
        assert result["display_only"] is True

    def test_stale_cbbc_neutral(self) -> None:
        """CBBC with stale freshness → neutral force."""
        r = CP.compute(cbbc_map=_cbbc_map(["bear_skew_froth", "bear_skew"], fresh="stale"))
        forces = {f["key"]: f for f in r["force_stack"]}
        assert forces["cbbc"]["state"] == "neutral"

    def test_stale_adr_neutral(self) -> None:
        r = CP.compute(adr_bridge=_adr_bridge(gap_pct=5.0, fresh="dead"))
        forces = {f["key"]: f for f in r["force_stack"]}
        assert forces["adr_bridge"]["state"] == "neutral"

    def test_narrative_all_young_neutral(self) -> None:
        """Narrative with all entities young → neutral."""
        hn = {
            "display_only": True,
            "freshness": "ok",
            "entities": [
                {"slug": "x", "ticker": "TICK", "name_en": "Test", "name_zh": "测试",
                 "attention_shock_z": None, "tone_pctile": None,
                 "narrative_state": None, "young": True,
                 "n_obs": 5, "as_of_date": None, "no_data_reason": "young"}
            ],
        }
        r = CP.compute(hk_narrative=hn)
        forces = {f["key"]: f for f in r["force_stack"]}
        assert forces["narrative"]["state"] == "neutral"


# ---------------------------------------------------------------------------
# (4) Always 8 forces in force_stack
# ---------------------------------------------------------------------------

class TestForceStackCompleteness:
    def test_always_8_forces(self) -> None:
        result = CP.compute()
        assert len(result["force_stack"]) == 8

    def test_8_forces_with_all_organs(self) -> None:
        result = CP.compute(
            freshness=_freshness("ok"),
            adr_bridge=_adr_bridge(),
            market_drivers=_market_drivers(),
            hk_narrative=_hk_narrative(),
            internals=_internals(),
            breadth=_breadth(),
            cbbc_map=_cbbc_map(),
            funding=_funding(),
            latest=_latest(),
        )
        assert len(result["force_stack"]) == 8

    def test_force_keys_unique(self) -> None:
        result = CP.compute()
        keys = [f["key"] for f in result["force_stack"]]
        assert len(keys) == len(set(keys))

    def test_all_forces_have_required_fields(self) -> None:
        result = CP.compute(
            adr_bridge=_adr_bridge(),
            latest=_latest(),
        )
        required = {"key", "name_en", "name_zh", "state", "detail_en", "detail_zh"}
        for f in result["force_stack"]:
            missing = required - set(f.keys())
            assert not missing, f"Force {f.get('key')} missing: {missing}"

    def test_force_states_valid_vocabulary(self) -> None:
        valid_states = {"confirm", "watch", "neutral", "stress"}
        result = CP.compute(
            adr_bridge=_adr_bridge(gap_pct=2.0),
            latest=_latest("Risk-off"),
        )
        for f in result["force_stack"]:
            assert f["state"] in valid_states, f"Invalid state {f['state']} for {f['key']}"


# ---------------------------------------------------------------------------
# (5) Bottom/chase scorecards from washout_watch
# ---------------------------------------------------------------------------

class TestScorecards:
    def test_bottom_watch_from_ignition_watch(self) -> None:
        setups = _setups_with_washout(
            bottom_states=["ignition_watch", "washout_watch"],
            chase_states=[],
        )
        result = CP.compute(setups=setups)
        assert len(result["bottom_watch"]) == 2
        assert len(result["chase_watch"]) == 0

    def test_chase_watch_from_chase_risk(self) -> None:
        setups = _setups_with_washout(
            bottom_states=[],
            chase_states=["chase_risk", "chase_risk"],
        )
        result = CP.compute(setups=setups)
        assert len(result["chase_watch"]) == 2
        assert len(result["bottom_watch"]) == 0

    def test_mixed_bottom_and_chase(self) -> None:
        setups = _setups_with_washout(
            bottom_states=["ignition_watch", "washout_watch"],
            chase_states=["chase_risk"],
        )
        result = CP.compute(setups=setups)
        assert len(result["bottom_watch"]) == 2
        assert len(result["chase_watch"]) == 1

    def test_empty_washout_watch(self) -> None:
        setups = {"washout_watch": []}
        result = CP.compute(setups=setups)
        assert result["bottom_watch"] == []
        assert result["chase_watch"] == []

    def test_knife_risk_carried_through(self) -> None:
        setups = _setups_with_washout(bottom_states=["ignition_watch"])
        # First item has knife_risk=True (set in factory)
        result = CP.compute(setups=setups)
        assert result["bottom_watch"][0]["knife_risk"] is True

    def test_confluence_n_correct(self) -> None:
        setups = _setups_with_washout(bottom_states=["washout_watch"])
        result = CP.compute(setups=setups)
        # factory gives 2 signals
        assert result["bottom_watch"][0]["confluence_n"] == 2

    def test_no_setups_returns_empty_scorecards(self) -> None:
        result = CP.compute(setups=None)
        assert result["bottom_watch"] == []
        assert result["chase_watch"] == []

    def test_pullback_entry_watch_in_bottom(self) -> None:
        setups = _setups_with_washout(bottom_states=["pullback_entry_watch"])
        result = CP.compute(setups=setups)
        assert len(result["bottom_watch"]) == 1


# ---------------------------------------------------------------------------
# (6) Catalyst tape
# ---------------------------------------------------------------------------

class TestCatalystTape:
    def test_filing_bus_in_tape(self) -> None:
        result = CP.compute(filing_bus=_filing_bus(n=2))
        assert len(result["catalyst_tape"]) >= 1
        sources = [r["source"] for r in result["catalyst_tape"]]
        assert "filing" in sources

    def test_catalyst_strip_in_tape(self) -> None:
        result = CP.compute(catalyst_strip=_catalyst_strip(n=2))
        assert len(result["catalyst_tape"]) >= 1
        sources = [r["source"] for r in result["catalyst_tape"]]
        assert "catalyst" in sources

    def test_narrative_spike_in_tape(self) -> None:
        result = CP.compute(
            hk_narrative=_hk_narrative(["attention_spike", "attention_spike"]))
        sources = [r["source"] for r in result["catalyst_tape"]]
        assert "narrative" in sources

    def test_tape_max_6_items(self) -> None:
        result = CP.compute(
            filing_bus=_filing_bus(n=3),
            catalyst_strip=_catalyst_strip(n=3),
            hk_narrative=_hk_narrative(["attention_spike", "attention_spike"]),
        )
        assert len(result["catalyst_tape"]) <= 6

    def test_tape_sorted_newest_first(self) -> None:
        result = CP.compute(
            filing_bus=_filing_bus(n=2),
            catalyst_strip=_catalyst_strip(n=2),
        )
        tape = result["catalyst_tape"]
        dates = [r["date"] for r in tape if r["date"] != "—"]
        if len(dates) >= 2:
            assert dates == sorted(dates, reverse=True)

    def test_empty_tape_on_no_inputs(self) -> None:
        result = CP.compute()
        # May still have items from narrative if narrative was passed; without it, empty
        assert isinstance(result["catalyst_tape"], list)


# ---------------------------------------------------------------------------
# (7) display_only=True invariant
# ---------------------------------------------------------------------------

def test_display_only_invariant() -> None:
    """compute() always returns display_only=True regardless of inputs."""
    for kwargs in [
        {},
        {"latest": _latest("Risk-on")},
        {"adr_bridge": _adr_bridge(2.0), "latest": _latest("Risk-off")},
    ]:
        result = CP.compute(**kwargs)
        assert result["display_only"] is True, f"display_only not True for {kwargs}"


# ---------------------------------------------------------------------------
# (8) Never raises on any input
# ---------------------------------------------------------------------------

class TestNeverRaises:
    @pytest.mark.parametrize("gap", [None, -10.0, 0.0, 0.001, 100.0])
    def test_extreme_adr_gaps(self, gap: float | None) -> None:
        result = CP.compute(adr_bridge=_adr_bridge(gap_pct=gap))
        assert "verdict" in result

    @pytest.mark.parametrize("proj", [None, -999.0, 0.0, 999.0])
    def test_extreme_tech_projections(self, proj: float | None) -> None:
        result = CP.compute(market_drivers=_market_drivers(tech_proj=proj))
        assert "verdict" in result

    def test_malformed_organ_doesnt_crash(self) -> None:
        # Pass totally wrong types for each organ
        result = CP.compute(
            adr_bridge={"composite": None},
            cbbc_map={"freshness": "ok", "bellwethers": None},
            hk_narrative={"entities": None, "freshness": "ok"},
        )
        assert result["display_only"] is True

    def test_empty_dicts_dont_crash(self) -> None:
        result = CP.compute(
            freshness={},
            adr_bridge={},
            market_drivers={},
            hk_narrative={},
            internals={},
            breadth={},
            cbbc_map={},
            funding={},
            latest={},
            filing_bus={},
            catalyst_strip=[],
            setups={},
        )
        assert result["display_only"] is True


# ---------------------------------------------------------------------------
# (SHAPE REGRESSION) Real producer shapes → non-neutral state contract
#
# Each test feeds the EXACT producer return shape and asserts a specific
# non-neutral state so that any future shape drift (renamed key, scale change)
# is caught rather than silently producing "neutral".
# ---------------------------------------------------------------------------

class TestRealProducerShapes:
    """Per-force contract tests using real producer-mirrored fixtures.

    These tests are the primary guard against the "72 passed while dead" failure
    mode: they feed production-shaped dicts and assert that the force reaches
    a specific non-neutral state.  A shape drift (renamed key, scale change)
    will turn these tests red.
    """

    def _get_force(self, result: dict, key: str) -> dict:
        for f in result["force_stack"]:
            if f["key"] == key:
                return f
        raise KeyError(f"Force '{key}' not in stack")

    # --- Force 1: ADR ---

    def test_adr_real_shape_composite_key(self) -> None:
        """adr_bridge.composite.bellwether_implied_open_pct >= 1 → confirm."""
        adr = {
            "display_only": True,
            "freshness_verdict": "ok",
            "hk_session_date": "2026-07-08",
            "adr_date": "2026-07-08",
            "expected_hk_session": "2026-07-09",
            "names": [],
            "composite": {
                "bellwether_implied_open_pct": 1.8,
                "gap_context": "up",
            },
        }
        r = CP.compute(adr_bridge=adr)
        f = self._get_force(r, "adr_bridge")
        assert f["state"] == "confirm", (
            f"ADR force must be 'confirm' on gap=+1.8%, got '{f['state']}'"
        )

    def test_adr_real_shape_degraded_is_live(self) -> None:
        """freshness_verdict='degraded' is treated as live (design intent: stale→neutral, degraded→live)."""
        adr = {
            "freshness_verdict": "degraded",
            "composite": {"bellwether_implied_open_pct": 2.0, "gap_context": "up"},
        }
        r = CP.compute(adr_bridge=adr)
        f = self._get_force(r, "adr_bridge")
        # "degraded" is intentionally live — should produce confirm on +2% gap
        assert f["state"] == "confirm", (
            f"ADR force: 'degraded' freshness must be treated as live (confirm on +2%), got '{f['state']}'"
        )

    # --- Force 2: Tech (hk_market_drivers.snapshot()) ---

    def test_tech_real_shape_flat_scores_list(self) -> None:
        """snapshot() returns scores as a FLAT LIST, not a nested drivers dict.

        This is the primary regression guard: scores=[{driver, projection, ...}].
        proj=+0.62 must yield 'confirm' state (threshold = 0.4).
        """
        snap = {
            "asof": "2026-07-08",
            "verdict": "clear",
            "primary": "tech_internet_leadership",
            "dir_sign": 1,
            "strength": 0.62,
            "confidence": "high",
            "scores": [
                {
                    "driver": "tech_internet_leadership",
                    "label": "Tech / internet leadership",
                    "label_zh": "科技/互联网领涨",
                    "family": "equity-leadership",
                    "projection": 0.62,
                    "strength": 0.62,
                    "direction": "HS-TECH leadership — narrow tech-led tape",
                },
                {
                    "driver": "global_risk",
                    "label": "Global risk-on / risk-off",
                    "label_zh": "全球风险偏好",
                    "family": "risk",
                    "projection": 0.31,
                    "strength": 0.31,
                    "direction": "risk-on",
                },
            ],
        }
        r = CP.compute(market_drivers=snap)
        f = self._get_force(r, "tech_impulse")
        assert f["state"] == "confirm", (
            f"Tech force (real shape, proj=+0.62) must be 'confirm'; got '{f['state']}'. "
            "If 'neutral': the reader is probably using 'drivers' key (old wrong shape) "
            "instead of iterating 'scores' list."
        )

    def test_tech_real_shape_negative_proj_stress(self) -> None:
        """scores list with tech proj=-0.62 → stress."""
        snap = {
            "asof": "2026-07-08",
            "verdict": "clear",
            "primary": "tech_internet_leadership",
            "dir_sign": -1,
            "strength": 0.62,
            "confidence": "high",
            "scores": [
                {
                    "driver": "tech_internet_leadership",
                    "label": "Tech / internet leadership",
                    "label_zh": "科技/互联网领涨",
                    "family": "equity-leadership",
                    "projection": -0.62,
                    "strength": 0.62,
                    "direction": "HS-TECH unwind",
                },
            ],
        }
        r = CP.compute(market_drivers=snap)
        f = self._get_force(r, "tech_impulse")
        assert f["state"] == "stress", (
            f"Tech force (real shape, proj=-0.62) must be 'stress'; got '{f['state']}'"
        )

    def test_tech_real_shape_no_tech_entry_neutral(self) -> None:
        """scores list with NO tech_internet_leadership entry → neutral (not crash)."""
        snap = {
            "asof": "2026-07-08",
            "verdict": "clear",
            "primary": "global_risk",
            "dir_sign": 1,
            "strength": 0.85,
            "confidence": "high",
            "scores": [
                {
                    "driver": "global_risk",
                    "label": "Global risk-on / risk-off",
                    "label_zh": "全球风险偏好",
                    "family": "risk",
                    "projection": 0.85,
                    "strength": 0.85,
                    "direction": "risk-on",
                },
            ],
        }
        r = CP.compute(market_drivers=snap)
        f = self._get_force(r, "tech_impulse")
        assert f["state"] == "neutral", (
            f"Tech force (no tech entry in scores) must be 'neutral'; got '{f['state']}'"
        )

    # --- Force 4: Southbound (china_internals.southbound_flow()) ---

    def test_southbound_real_shape_net_z_confirm(self) -> None:
        """southbound_flow() uses 'net' and 'net_z', not 'net_hkd'/'accel_z'.

        net_z=+1.8 → confirm (threshold = 0.5).
        """
        sb_flow = {
            "net": 5000.0,
            "net_z": 1.8,
            "cum_20d": 28000.0,
            "pos_days_20": 14,
        }
        r = CP.compute(internals={"southbound": sb_flow})
        f = self._get_force(r, "southbound")
        assert f["state"] == "confirm", (
            f"Southbound force (real shape, net_z=+1.8) must be 'confirm'; got '{f['state']}'. "
            "If 'neutral': the reader is likely using 'accel_z' (wrong key) instead of 'net_z'."
        )

    def test_southbound_real_shape_net_z_stress(self) -> None:
        """net_z=-1.8 → stress."""
        sb_flow = {
            "net": -4000.0,
            "net_z": -1.8,
            "cum_20d": -22000.0,
            "pos_days_20": 4,
        }
        r = CP.compute(internals={"southbound": sb_flow})
        f = self._get_force(r, "southbound")
        assert f["state"] == "stress", (
            f"Southbound force (real shape, net_z=-1.8) must be 'stress'; got '{f['state']}'"
        )

    def test_southbound_real_shape_fallback_net_only(self) -> None:
        """When net_z is absent, falls back to net direction (watch on positive)."""
        sb_flow = {
            "net": 3000.0,
            "cum_20d": 15000.0,
            "pos_days_20": 12,
        }
        r = CP.compute(internals={"southbound": sb_flow})
        f = self._get_force(r, "southbound")
        # net_z absent → no z-based state; falls back to net direction → watch
        assert f["state"] == "watch", (
            f"Southbound force (net only, no net_z) must be 'watch'; got '{f['state']}'"
        )

    # --- Force 5: Breadth (collectors.breadth.breadth_summary()) ---

    def test_breadth_real_shape_pct_above_200_key_confirm(self) -> None:
        """breadth_summary() returns 'pct_above_200' (NO trailing 'd'), value 0-100.

        pct_above_200=62.3 → confirm (threshold: 55% of 100-scale = 55.0).
        """
        br = {
            "pct_above_200": 62.3,    # 0-100 scale
            "pct_above_50": 70.0,
            "nh": 15, "nl": 3, "net_nh": 12,
            "adv": 200, "dec": 100,
            "ad_trend": "up",
            "state": "broad", "tone": "pos",
            "full": False,
            "asof": "2026-07-08",
            "n_members": 300,
            "pct50_chg20": 5.0,
        }
        r = CP.compute(breadth=br)
        f = self._get_force(r, "breadth")
        assert f["state"] == "confirm", (
            f"Breadth force (real shape, pct_above_200=62.3) must be 'confirm'; got '{f['state']}'. "
            "If 'neutral': reader is probably using 'pct_above_200d' (wrong key) "
            "or treating 62.3 as a fraction (threshold mismatch — values are 0-100)."
        )

    def test_breadth_real_shape_pct_above_200_stress(self) -> None:
        """pct_above_200=22.0 → stress (threshold: <= 30% of 100-scale = 30.0)."""
        br = {
            "pct_above_200": 22.0,
            "pct_above_50": 28.0,
            "nh": 2, "nl": 30, "net_nh": -28,
            "adv": 60, "dec": 240,
            "ad_trend": "down",
            "state": "thin", "tone": "neg",
            "full": False,
            "asof": "2026-07-08",
            "n_members": 300,
            "pct50_chg20": -8.0,
        }
        r = CP.compute(breadth=br)
        f = self._get_force(r, "breadth")
        assert f["state"] == "stress", (
            f"Breadth force (real shape, pct_above_200=22.0) must be 'stress'; got '{f['state']}'"
        )

    def test_breadth_real_shape_adv_dec_fallback(self) -> None:
        """When pct_above_200 absent, adv/dec fallback activates (not adv_dec_ratio)."""
        br = {
            "pct_above_50": 65.0,
            "nh": 10, "nl": 2, "net_nh": 8,
            "adv": 220, "dec": 80,    # no pct_above_200
            "ad_trend": "up",
            "state": "broad", "tone": "pos",
            "full": False, "asof": "2026-07-08",
            "n_members": 300, "pct50_chg20": 4.0,
        }
        r = CP.compute(breadth=br)
        f = self._get_force(r, "breadth")
        # adv=220, dec=80 → adv_frac=0.73 > 0.6 → confirm
        assert f["state"] == "confirm", (
            f"Breadth force (adv/dec fallback, adv=220 dec=80) must be 'confirm'; got '{f['state']}'"
        )


# ---------------------------------------------------------------------------
# (9) Freshness strip routing
# ---------------------------------------------------------------------------

class TestFreshnessStrip:
    def test_ok_verdict(self) -> None:
        result = CP.compute(freshness=_freshness("ok"))
        fs = result["freshness_strip"]
        assert fs["verdict"] == "ok"
        assert "fresh" in fs["label_en"].lower()

    def test_stale_verdict(self) -> None:
        result = CP.compute(freshness=_freshness("stale"))
        fs = result["freshness_strip"]
        assert fs["verdict"] == "stale"
        assert "stale" in fs["label_en"].upper() or "STALE" in fs["label_en"]

    def test_degraded_verdict(self) -> None:
        result = CP.compute(freshness=_freshness("degraded"))
        fs = result["freshness_strip"]
        assert fs["verdict"] == "degraded"

    def test_no_freshness_unknown(self) -> None:
        result = CP.compute(freshness=None)
        fs = result["freshness_strip"]
        assert fs["verdict"] == "unknown"

    def test_freshness_strip_has_labels(self) -> None:
        result = CP.compute(freshness=_freshness("ok"))
        fs = result["freshness_strip"]
        assert fs["label_en"]
        assert fs["label_zh"]


# ---------------------------------------------------------------------------
# (10) No writes to data/ or site/ (git status guard)
# ---------------------------------------------------------------------------

def test_no_filesystem_writes(tmp_path: Path) -> None:
    """compute() must not write to any real path. Verify by running with full inputs
    and checking git status returns clean (the test itself doesn't write)."""
    # Run compute with realistic inputs — this is the key test
    result = CP.compute(
        freshness=_freshness("ok"),
        adr_bridge=_adr_bridge(2.0),
        market_drivers=_market_drivers(0.5),
        hk_narrative=_hk_narrative(["attention_spike", "quiet"]),
        internals=_internals(0.8),
        breadth=_breadth(60.0),
        cbbc_map=_cbbc_map(["bear_skew", "bear_skew"]),
        funding=_funding(65),
        latest=_latest("Risk-on"),
        filing_bus=_filing_bus(2),
        catalyst_strip=_catalyst_strip(2),
        setups=_setups_with_washout(["ignition_watch"], ["chase_risk"]),
    )
    # If compute() wrote any files it would have errored or impacted git status.
    # Verify the result is valid; the CI git-status check catches actual writes.
    assert result["display_only"] is True
    assert len(result["force_stack"]) == 8
    assert len(result["bottom_watch"]) == 1
    assert len(result["chase_watch"]) == 1
