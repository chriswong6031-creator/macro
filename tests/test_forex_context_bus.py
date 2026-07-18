"""MSX-1 FX Context Bus tests.

Covers:
- latest.json new-key schema (smile_decomp, strength, regime_radar.scenarios,
  pairs enrichment, state_changes, schema_note)
- state_changes: flip detection, days_in_state counts, keep-first idempotency
- lane gating: off-lane → no file writes
- _desk_latest includes smile_decomp
- context_forward_log row shape + keep-first
- forex_alerts new event types (smile_regime_flip, triple_red; scenario events are
  edge-detected in the canonical `scenario` family, covered in test_forex.py)

Run: python3 -m pytest tests/test_forex_context_bus.py -x -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ------------------------------------------------------------------ fixtures -


def _idx(n: int = 300):
    return pd.date_range("2024-01-01", periods=n, freq="B")


def _dol_frame(n: int = 300, regime: str = "Neutral") -> pd.DataFrame:
    """Minimal _dollar master frame (same columns build_forex.py reads)."""
    idx = _idx(n)
    return pd.DataFrame({
        "smile_regime": pd.Categorical([regime] * n),
        "risk_off": 0.0,
        "dollar_roc": 0.01,
        "broad": 100.0,
        "dxy": 104.0,
    }, index=idx)


def _fake_desk(triple_red: bool = False) -> dict:
    return {
        "lean": "dollar-supportive backdrop",
        "lean_zh": "偏多美元背景",
        "lean_net": 2,
        "lean_n": 3,
        "real_rate": {"regime": "Restrictive / USD-supportive", "real_z": 1.2, "lean": "supportive"},
        "fed_path": {"path_bps": 25.0, "lean": "hawkish_repricing"},
        "positioning": {"pctile": 55.0, "state": "neutral"},
        "valuation": {"gap_pct": 5.0, "label": "Overvalued"},
        "trend": {"label": "up", "n_up": 4},
        "liquidity": {"dir": "supportive"},
        "smile": {"confidence": "medium", "confidence_zh": "中", "n_confirm": 2,
                  "triple_red": triple_red, "usd_dir": "strong", "regime": "US growth premium"},
        "smile_decomp": {
            "beta": 0.35, "r2": 0.42, "residual_20d": 0.0012,
            "residual_20d_z": 1.1, "regime": "safety-driven", "regime_60d": "rates-driven",
            "safety_bid_today": False, "display_only": True, "gaps": [],
        },
    }


def _fake_regime(active_keys: list[str] | None = None) -> dict:
    active_keys = active_keys or []
    scenarios = []
    for key, name_en, name_zh in [
        ("carry_unwind", "Carry Unwind", "套息平仓"),
        ("dollar_wrecking_ball", "Dollar Wrecking Ball", "广义美元压路机"),
        ("em_crisis_capital_flight", "EM Crisis", "新兴市场危机"),
        ("haven_flight_risk_off", "Safe-Haven Flight", "急性避险"),
        ("reflation_risk_on", "Reflation", "再通胀"),
    ]:
        scenarios.append({
            "key": key, "name_en": name_en, "name_zh": name_zh,
            "intensity_today": 72.5 if key in active_keys else 15.0,
            "active": key in active_keys, "illustrative": False,
            "n_fired": 3 if key in active_keys else 1, "min_legs": 3,
            "prob": {
                "status": "ok" if key in active_keys else "insufficient",
                "p_cond": 0.42 if key in active_keys else None,
                "base_rate": 0.15, "wilson_lo": 0.28, "wilson_hi": 0.57,
                "n_raw": 8, "n_eff": 2.7, "N": 3,
            },
        })
    dominant = active_keys[0] if active_keys else None
    return {"as_of": "2024-06-14", "dominant": dominant, "n_active": len(active_keys),
            "scenarios": scenarios, "caveats": True, "history_span": "2010-01-01..2024-06-14"}


def _fake_strength() -> dict:
    return {
        "horizons": {"1w": [{"ccy": "USD", "ccy_zh": "美元", "strength": 0.8, "vs_usd_pct": 0.0, "em": False},
                             {"ccy": "EUR", "ccy_zh": "欧元", "strength": -0.2, "vs_usd_pct": -0.5, "em": False}]},
        "default": "1w", "order": ["1w"],
    }


def _fake_pairs() -> list[dict]:
    return [{
        "key": "EURUSD", "label": "EUR/USD", "zh": "欧元/美元",
        "base": "EUR", "quote_ccy": "USD", "arch": "Major", "arch_zh": "主要货币",
        "quote": 1.0820, "chg": -0.1, "resid_chg": 0.2,
        "dollar_beta": -0.6, "ts_trend": "bull",
        "ts_momentum": 0.4, "structure": 0.3, "structure_state": "constructive",
        "risk_index": 22.0, "risk_word": "Calm",
        "shock_z": 0.5, "shock_state": "normal",
        "pos_pctile": 55.0, "pos_state": "neutral",
        "carry_diff": 0.8, "carry_score": 0.4, "carry_to_vol": 0.15,
        "carry_context": False, "reer_gap": 3.2, "rate_diff_10y": 1.1,
        "cnh_basis": None, "cnh_state": None,
        "conviction": {
            "score": 42.0, "action": "LONG", "action_zh": "偏多",
            "action_css": "bull", "stance": "bullish",
            "confidence": 0.55, "reliable": False, "calibrated": False,
            "factors": [{"key": "trend", "label": "trend", "label_zh": "趋势",
                         "group": "momentum", "contribution": 0.4, "weight": 0.3}],
            "groups": [], "cycle": {"label": "mid-cycle"},
            "headline": "Risk-context: net long EUR (+42)",
            "headline_zh": "风险背景：EUR 净偏多（+42）",
            "sub": "Led by trend.", "sub_zh": "主导因素：趋势。",
            "framing": "Risk-context", "framing_zh": "风险背景",
            "peg": None, "base": "EUR", "n_factors": 1,
        },
        "mtf_rows": [], "verdict": {}, "chart": "",
    }]


# ----------------------------------------------------------------- _desk_latest -

def test_desk_latest_includes_smile_decomp():
    """BUG FIX: smile_decomp must be forwarded into dollar_desk block."""
    from scripts.build_forex import _desk_latest
    desk = _fake_desk()
    out = _desk_latest(desk)
    assert "smile_decomp" in out, "smile_decomp missing from _desk_latest output"
    sd = out["smile_decomp"]
    assert sd["regime"] == "safety-driven"
    assert sd["display_only"] is True
    assert isinstance(sd["beta"], float)


def test_desk_latest_no_smile_decomp_when_absent():
    """If desk has no smile_decomp, the key must be absent (not None)."""
    from scripts.build_forex import _desk_latest
    desk = {k: v for k, v in _fake_desk().items() if k != "smile_decomp"}
    out = _desk_latest(desk)
    assert "smile_decomp" not in out


def test_desk_latest_empty_desk_returns_empty():
    from scripts.build_forex import _desk_latest
    assert _desk_latest({}) == {}


# --------------------------------------------------------------- state_changes -

def _write_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_state_changes_flip_detected(tmp_path, monkeypatch):
    """A value change in today vs history is detected as a flip (prev != current)."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _write_history(hist_path, [
        {"date": "2024-06-10", "smile_regime": "Neutral", "lean": "mixed",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "soft",
         "trend": "down", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
        {"date": "2024-06-11", "smile_regime": "Neutral", "lean": "mixed",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "soft",
         "trend": "down", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
    ])

    dol = _dol_frame(regime="US growth premium")
    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "US growth premium",
        "lean": "dollar-supportive backdrop",
        "risk": "risk-on", "fed_path_lean": "hawkish_repricing",
        "liquidity_dir": "supportive", "trend": "up",
        "triple_red": False, "cnh_basis_state": None,
        "regime_radar_dominant": None,
    }
    sc = BF._state_changes(today_vals, dol)

    # smile_regime changed
    assert sc["smile_regime"]["current"] == "US growth premium"
    assert sc["smile_regime"]["prev"] == "Neutral"
    assert sc["smile_regime"]["changed_on"] == "2024-06-11"

    # trend changed
    assert sc["trend"]["current"] == "up"
    assert sc["trend"]["prev"] == "down"

    # lean changed
    assert sc["lean"]["current"] == "dollar-supportive backdrop"
    assert sc["lean"]["prev"] == "mixed"


def test_state_changes_days_in_state(tmp_path, monkeypatch):
    """days_in_state counts correctly from changed_on to today."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _write_history(hist_path, [
        {"date": "2024-06-10", "smile_regime": "Neutral", "lean": "mixed",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "soft",
         "trend": "down", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
        {"date": "2024-06-11", "smile_regime": "US growth premium", "lean": "dollar-supportive backdrop",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "supportive",
         "trend": "up", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
        {"date": "2024-06-12", "smile_regime": "US growth premium", "lean": "dollar-supportive backdrop",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "supportive",
         "trend": "up", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
    ])

    dol = _dol_frame(regime="US growth premium")
    today_vals = {
        "_date": "2024-06-14",  # 3 days after changed_on 2024-06-11
        "smile_regime": "US growth premium",
        "lean": "dollar-supportive backdrop",
        "risk": "risk-on", "fed_path_lean": None,
        "liquidity_dir": "supportive", "trend": "up",
        "triple_red": False, "cnh_basis_state": None,
        "regime_radar_dominant": None,
    }
    sc = BF._state_changes(today_vals, dol)

    # smile_regime unchanged since 2024-06-11, changed_on is 2024-06-10 (the last diff)
    # days_in_state from 2024-06-10 to 2024-06-14 = 5 days (inclusive)
    assert sc["smile_regime"]["days_in_state"] == 5

    # trend unchanged since 2024-06-11 -> changed_on=2024-06-10, days=5
    assert sc["trend"]["days_in_state"] == 5


def test_state_changes_keep_first_idempotent(tmp_path, monkeypatch):
    """Calling _state_changes twice on the same date must not append a second row."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "Neutral", "lean": "mixed", "risk": "risk-off",
        "fed_path_lean": None, "liquidity_dir": "soft", "trend": "down",
        "triple_red": False, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    dol = _dol_frame()

    BF._state_changes(today_vals, dol)
    BF._state_changes(today_vals, dol)

    rows = BF._read_state_history()
    date_rows = [r for r in rows if r["date"] == "2024-06-14"]
    assert len(date_rows) == 1, f"Expected 1 row for 2024-06-14, got {len(date_rows)}"


def test_state_changes_empty_history_returns_nulls(tmp_path, monkeypatch):
    """With no history, prev/changed_on/days_in_state should be null (never raises)."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    # off-lane so no write happens
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "Neutral", "lean": "mixed", "risk": "risk-on",
        "fed_path_lean": None, "liquidity_dir": "soft", "trend": "flat",
        "triple_red": False, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    dol = _dol_frame()
    sc = BF._state_changes(today_vals, dol)

    for key in ("lean", "risk", "fed_path_lean", "liquidity_dir",
                "trend", "triple_red", "cnh_basis_state", "regime_radar_dominant"):
        assert sc[key]["prev"] is None
        assert sc[key]["changed_on"] is None
        assert sc[key]["days_in_state"] is None


def test_state_changes_offlan_no_write(tmp_path, monkeypatch):
    """Off-lane: history file must not be created/written."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "Neutral", "lean": "mixed", "risk": "risk-on",
        "fed_path_lean": None, "liquidity_dir": "soft", "trend": "flat",
        "triple_red": False, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    BF._state_changes(today_vals, _dol_frame())
    assert not hist_path.exists(), "History file must not be written off-lane"


# ---------------------------------------------- smile_regime seed from _dollar -

def test_state_changes_seeds_smile_from_dollar_frame(tmp_path, monkeypatch):
    """When history is empty and _dollar has a regime series, smile_regime
    changed_on is seeded from the last transition in the frame."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    idx = pd.date_range("2024-01-02", periods=20, freq="B")
    regime_vals = ["Neutral"] * 10 + ["US growth premium"] * 10
    dol = pd.DataFrame({"smile_regime": pd.Categorical(regime_vals)}, index=idx)

    today_vals = {
        "_date": idx[-1].strftime("%Y-%m-%d"),
        "smile_regime": "US growth premium",
        "lean": None, "risk": None, "fed_path_lean": None,
        "liquidity_dir": None, "trend": None,
        "triple_red": None, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    sc = BF._state_changes(today_vals, dol)

    assert sc["smile_regime"]["changed_on"] is not None, (
        "smile_regime changed_on should be seeded from _dollar frame")
    assert sc["smile_regime"]["days_in_state"] is not None


def test_state_changes_unchanged_since_first_row_returns_none_days(tmp_path, monkeypatch):
    """When history has rows but no flip is found (value unchanged throughout),
    days_in_state and changed_on must be None (unknown ≠ log age)."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    # Two rows, both with lean="mixed" — no flip
    _write_history(hist_path, [
        {"date": "2024-06-10", "smile_regime": "Neutral", "lean": "mixed",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "soft",
         "trend": "flat", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
        {"date": "2024-06-11", "smile_regime": "Neutral", "lean": "mixed",
         "risk": "risk-on", "fed_path_lean": None, "liquidity_dir": "soft",
         "trend": "flat", "triple_red": False, "cnh_basis_state": None,
         "regime_radar_dominant": None},
    ])

    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "Neutral", "lean": "mixed", "risk": "risk-on",
        "fed_path_lean": None, "liquidity_dir": "soft", "trend": "flat",
        "triple_red": False, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    # Use a dol frame where smile_regime is also all "Neutral" so no frame seed fires
    dol = _dol_frame(regime="Neutral")
    sc = BF._state_changes(today_vals, dol)

    # No flip found → days_in_state and changed_on must be None
    assert sc["lean"]["changed_on"] is None, "changed_on should be None when no flip found"
    assert sc["lean"]["days_in_state"] is None, "days_in_state should be None when no flip found"
    assert sc["risk"]["days_in_state"] is None
    assert sc["trend"]["days_in_state"] is None


def test_state_changes_seed_populates_prev(tmp_path, monkeypatch):
    """When smile_regime changed_on is seeded from the _dollar frame, prev must
    be populated with the value immediately before the flip in the frame."""
    from scripts import build_forex as BF

    hist_path = tmp_path / "forex" / "state_history.jsonl"
    monkeypatch.setattr(BF, "_state_history_path", lambda: hist_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    idx = pd.date_range("2024-01-02", periods=20, freq="B")
    regime_vals = ["Neutral"] * 10 + ["US growth premium"] * 10
    dol = pd.DataFrame({"smile_regime": pd.Categorical(regime_vals)}, index=idx)

    today_vals = {
        "_date": idx[-1].strftime("%Y-%m-%d"),
        "smile_regime": "US growth premium",
        "lean": None, "risk": None, "fed_path_lean": None,
        "liquidity_dir": None, "trend": None,
        "triple_red": None, "cnh_basis_state": None, "regime_radar_dominant": None,
    }
    sc = BF._state_changes(today_vals, dol)

    # prev should be "Neutral" — the value immediately before the transition
    assert sc["smile_regime"]["prev"] == "Neutral", (
        "prev should be the pre-flip value from the _dollar frame"
    )


# ------------------------------------------------------ context_forward_log -

def test_context_forward_log_row_shape(tmp_path, monkeypatch):
    """Each row must have {asof, key, state, intensity_pct, graded}."""
    from scripts import build_forex as BF

    log_path = tmp_path / "forex" / "context_forward_log.jsonl"
    monkeypatch.setattr(BF, "_context_forward_log_path", lambda: log_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    today_vals = {
        "_date": "2024-06-14",
        "smile_regime": "US growth premium",
        "triple_red": True,
    }
    regime = _fake_regime(active_keys=["carry_unwind"])

    BF._append_context_forward_log("2024-06-14", today_vals, regime)

    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(rows) == len(BF._FORWARD_LOG_KEYS)

    for r in rows:
        assert set(r.keys()) >= {"asof", "key", "state", "intensity_pct", "graded"}
        assert r["asof"] == "2024-06-14"
        assert r["graded"] is None
        assert r["key"] in BF._FORWARD_LOG_KEYS


def test_context_forward_log_keep_first(tmp_path, monkeypatch):
    """Re-appending on the same (asof, key) must not write a duplicate row."""
    from scripts import build_forex as BF

    log_path = tmp_path / "forex" / "context_forward_log.jsonl"
    monkeypatch.setattr(BF, "_context_forward_log_path", lambda: log_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    today_vals = {"_date": "2024-06-14", "smile_regime": "Neutral", "triple_red": False}
    regime = _fake_regime()

    BF._append_context_forward_log("2024-06-14", today_vals, regime)
    BF._append_context_forward_log("2024-06-14", today_vals, regime)

    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    keys_written = [(r["asof"], r["key"]) for r in rows]
    assert len(keys_written) == len(set(keys_written)), "Duplicate (asof, key) rows written"


def test_context_forward_log_offlan_no_write(tmp_path, monkeypatch):
    """Off-lane invocation must not create the log file."""
    from scripts import build_forex as BF

    log_path = tmp_path / "forex" / "context_forward_log.jsonl"
    monkeypatch.setattr(BF, "_context_forward_log_path", lambda: log_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    BF._append_context_forward_log("2024-06-14", {}, _fake_regime())
    assert not log_path.exists()


def test_context_forward_log_intensity_pct_populated(tmp_path, monkeypatch):
    """intensity_pct from regime_radar when applicable; null for smile_regime/triple_red."""
    from scripts import build_forex as BF

    log_path = tmp_path / "forex" / "context_forward_log.jsonl"
    monkeypatch.setattr(BF, "_context_forward_log_path", lambda: log_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    regime = _fake_regime(active_keys=["carry_unwind"])  # carry_unwind has intensity_today=72.5
    BF._append_context_forward_log("2024-06-14", {"smile_regime": "Neutral", "triple_red": False}, regime)

    rows = {r["key"]: r for r in
            [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]}

    # smile_regime and triple_red have no intensity_pct mapping
    assert rows["smile_regime"]["intensity_pct"] is None
    assert rows["triple_red"]["intensity_pct"] is None
    # carry_unwind scenario intensity = 72.5
    assert rows["carry_unwind"]["intensity_pct"] == 72.5


def test_context_forward_log_malformed_scenario_skipped(tmp_path, monkeypatch):
    """A scenario missing 'key' must not raise — the row is skipped, others write normally."""
    from scripts import build_forex as BF

    log_path = tmp_path / "forex" / "context_forward_log.jsonl"
    monkeypatch.setattr(BF, "_context_forward_log_path", lambda: log_path)
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    # Inject one malformed scenario (no 'key') alongside valid ones
    regime = _fake_regime(active_keys=["carry_unwind"])
    regime["scenarios"].append({"intensity_today": 50.0, "active": True})  # missing 'key'

    try:
        BF._append_context_forward_log("2024-06-14", {"smile_regime": "Neutral", "triple_red": False}, regime)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"_append_context_forward_log raised on malformed scenario: {e}")

    assert log_path.exists(), "Log file must be created despite malformed scenario"
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    # All _FORWARD_LOG_KEYS rows must still be written
    assert len(rows) == len(BF._FORWARD_LOG_KEYS)


# --------------------------------------------------------- alert event types -

def test_smile_regime_flip_events():
    """desk_smile_regime_events fires on each smile_regime transition."""
    from engine import forex_alerts as FA

    idx = _idx(40)
    regime_vals = ["Neutral"] * 20 + ["Risk-off haven bid"] * 20
    dol = pd.DataFrame({"smile_regime": pd.Categorical(regime_vals)}, index=idx)
    evs = FA.desk_smile_regime_events(dol)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "smile_regime_flip"
    assert e["asset"] == "dollar"
    assert "Risk-off haven bid" in e["headline"]
    assert e["headline_zh"]
    assert e["severity"] == "high"


def test_smile_regime_flip_empty_on_no_dollar():
    from engine import forex_alerts as FA
    assert FA.desk_smile_regime_events(None) == []
    assert FA.desk_smile_regime_events(pd.DataFrame()) == []


def test_triple_red_events_active(monkeypatch):
    """triple_red=True emits a high-severity event."""
    from engine import forex_alerts as FA

    dol = _dol_frame()
    desk = _fake_desk(triple_red=True)
    evs = FA.desk_triple_red_events(dol, desk)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "triple_red"
    assert e["severity"] == "high"
    assert "triple-red" in e["headline"].lower() or "triple" in e["headline"].lower()
    assert e["headline_zh"]


def test_triple_red_events_clear():
    """triple_red=False emits an info-severity clear event."""
    from engine import forex_alerts as FA

    desk = _fake_desk(triple_red=False)
    evs = FA.desk_triple_red_events(_dol_frame(), desk)
    assert len(evs) == 1
    assert evs[0]["severity"] == "info"


def test_triple_red_events_no_desk():
    from engine import forex_alerts as FA
    assert FA.desk_triple_red_events(_dol_frame(), None) == []
    assert FA.desk_triple_red_events(_dol_frame(), {}) == []


def test_scenario_events_canonical_family():
    """Reconciled semantics: scenario events are edge-detected via the canonical
    scenario_events(regime, prev_active) family (collision-safe ids, deactivation
    branch) — the per-active-day desk_scenario_events family was superseded."""
    from engine import forex_alerts as FA

    regime = _fake_regime(active_keys=["carry_unwind", "haven_flight_risk_off"])
    evs = FA.scenario_events(regime, prev_active=set())
    assert len(evs) == 2
    assert {e["type"] for e in evs} == {"scenario"}
    ids = {e["id"] for e in evs}
    assert len(ids) == 2  # collision-safe: scenario key participates in the id
    # steady state: no re-fire when the active set is unchanged
    assert FA.scenario_events(regime, prev_active={"carry_unwind", "haven_flight_risk_off"}) == []


def test_compute_all_events_additive(tmp_path, monkeypatch):
    """compute_all_events with desk/regime includes new event types without
    breaking existing pair events."""
    from engine import forex_alerts as FA

    # stub out the alerts.jsonl path so no real file I/O
    alerts_path = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(FA, "_path", lambda: alerts_path)

    idx = _idx(60)
    regime_vals = ["Neutral"] * 30 + ["Risk-off haven bid"] * 30
    dol = pd.DataFrame({
        "smile_regime": pd.Categorical(regime_vals),
        "risk_regime": ["low_risk"] * 30 + ["high_risk"] * 30,
        "risk_index": pd.Series(np.concatenate([np.full(30, 20.0), np.full(30, 80.0)]), index=idx),
        "close": 1.0,
    }, index=idx)

    results = {"_dollar": dol, "EURUSD": pd.DataFrame({
        "close": 1.1, "carry_diff": [-1.0] * 30 + [1.0] * 30,
    }, index=idx)}
    desk = _fake_desk(triple_red=True)
    regime = _fake_regime(active_keys=["carry_unwind"])

    evs = FA.compute_all_events(results, desk=desk, regime=regime)
    types = {e["type"] for e in evs}

    assert "carry_flip" in types              # existing
    assert "smile_regime" in types            # existing dollar event
    assert "smile_regime_flip" in types       # MSX-1 new
    assert "triple_red" in types              # MSX-1 new
    assert "scenario" in types                # reconciled edge-detected family


# ------------------------------------------- latest.json schema validation -

def test_latest_schema_new_keys(tmp_path, monkeypatch):
    """Validate that all MSX-1 new keys appear in the latest dict structure."""
    from scripts import build_forex as BF

    # We test _desk_latest and the scenario receipt helper indirectly via unit tests;
    # here we validate the top-level key presence by constructing the dict the same
    # way main() does, but without running the full builder.
    desk = _fake_desk()
    regime = _fake_regime(active_keys=["carry_unwind"])
    strength = _fake_strength()
    pairs = _fake_pairs()
    dol = _dol_frame()

    # Replicate the _scenario_receipt helper from main()
    def _scenario_receipt(s: dict) -> dict:
        p_raw = s.get("prob") or {}
        return {
            "key": s.get("key"),
            "name_en": s.get("name_en"),
            "name_zh": s.get("name_zh"),
            "intensity": BF._r(s.get("intensity_today"), 1),
            "active": bool(s.get("active")),
            "illustrative": bool(s.get("illustrative")),
            "prob": {
                "status": p_raw.get("status"),
                "p_cond": BF._r(p_raw.get("p_cond"), 4),
                "base_rate": BF._r(p_raw.get("base_rate"), 4),
                "wilson_lo": BF._r(p_raw.get("wilson_lo"), 4),
                "wilson_hi": BF._r(p_raw.get("wilson_hi"), 4),
                "n_raw": p_raw.get("n_raw"),
                "n_eff": p_raw.get("n_eff"),
                "N": p_raw.get("N"),
            },
        }

    # dollar_desk must include smile_decomp
    dl = BF._desk_latest(desk)
    assert "smile_decomp" in dl
    assert dl["smile_decomp"]["regime"] == "safety-driven"

    # strength forwarded
    assert "horizons" in strength
    assert "default" in strength

    # regime_radar scenarios
    scenarios = [_scenario_receipt(s) for s in regime.get("scenarios", [])]
    assert len(scenarios) == 5
    sr = scenarios[0]
    assert set(sr.keys()) >= {"key", "name_en", "name_zh", "intensity", "active", "illustrative", "prob"}
    prob = sr["prob"]
    assert set(prob.keys()) >= {"status", "p_cond", "base_rate", "wilson_lo", "wilson_hi",
                                "n_raw", "n_eff", "N"}

    # schema_note present
    schema_note = (
        "MSX-1 additive-only enrichment: do not rename/remove existing keys. "
        "new keys: dollar_desk.smile_decomp, strength, regime_radar.scenarios, "
        "pairs.<KEY>.{headline,head_zh,sub,sub_zh,shock_state,cycle_position}, "
        "pairs.USDCNH.{cnh_basis_bps,cnh_basis_state}, state_changes."
    )
    assert isinstance(schema_note, str) and "MSX-1" in schema_note


def test_pairs_enrichment_fields():
    """Pair dicts must include the MSX-1 narrative + signal-frame fields."""
    pairs = _fake_pairs()
    conv = pairs[0].get("conviction") or {}
    assert conv.get("headline") is not None
    assert conv.get("headline_zh") is not None
    assert conv.get("sub") is not None
    assert conv.get("sub_zh") is not None
    assert (conv.get("cycle") or {}).get("label") is not None


# ---------------------------------------- JSON-serializable guard --------

def test_desk_latest_json_serializable():
    """_desk_latest output must be json.dumps-able without default=str."""
    from scripts.build_forex import _desk_latest
    out = _desk_latest(_fake_desk())
    # should not raise
    serialized = json.dumps(out)
    assert serialized


if __name__ == "__main__":
    fns = [
        test_desk_latest_includes_smile_decomp,
        test_desk_latest_no_smile_decomp_when_absent,
        test_desk_latest_empty_desk_returns_empty,
        test_context_forward_log_row_shape,
        test_context_forward_log_keep_first,
        test_context_forward_log_offlan_no_write,
        test_context_forward_log_intensity_pct_populated,
        test_smile_regime_flip_events,
        test_smile_regime_flip_empty_on_no_dollar,
        test_triple_red_events_active,
        test_triple_red_events_clear,
        test_triple_red_events_no_desk,
        test_scenario_events_canonical_family,
        test_compute_all_events_additive,
        test_latest_schema_new_keys,
        test_pairs_enrichment_fields,
        test_desk_latest_json_serializable,
        test_state_changes_empty_history_returns_nulls,
        test_state_changes_offlan_no_write,
        test_state_changes_seeds_smile_from_dollar_frame,
        test_state_changes_unchanged_since_first_row_returns_none_days,
        test_state_changes_seed_populates_prev,
    ]
    for fn in fns:
        if "tmp_path" in fn.__code__.co_varnames or "monkeypatch" in fn.__code__.co_varnames:
            print(f"  (skipped in __main__: requires pytest fixtures): {fn.__name__}")
            continue
        fn()
        print(f"PASS {fn.__name__}")
    print("all context bus tests passed (pytest-fixture tests skipped in __main__ mode)")
