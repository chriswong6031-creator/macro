"""Pure-function tests for engine/radar_plus.py — no network, no real disk I/O.

Covers:
  - _num / _sign: coerce numbers, return None/0 for dict/str/bool/None.
  - _alt_lean: smart-money lean, drivers, empty case.
  - _flow_lean: accumulation vs distribution net.
  - _options_lean: monkeypatch _load for GEX; non-numeric skew does not raise.
  - _crowd_penalty: dpi_lean distribution + wsb_mentions.
  - _decay_for: days_in_state, flip_7d.
  - enrich(): full pipeline with all _load / _regime / _state_history monkeypatched.

No conftest, no network, no fixtures. All assertions use plain assert.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.radar_plus as rp  # noqa: E402

_TODAY = date(2026, 6, 20)

# ============================================================================ #
# _num / _sign
# ============================================================================ #

def test_num_dict_is_none():
    assert rp._num({}) is None


def test_num_str_is_none():
    assert rp._num("x") is None


def test_num_bool_is_none():
    assert rp._num(True) is None
    assert rp._num(False) is None


def test_num_none_is_none():
    assert rp._num(None) is None


def test_num_int_coerces():
    assert rp._num(5) == 5.0


def test_num_float_coerces():
    assert rp._num(3.14) == 3.14


def test_num_zero_int():
    assert rp._num(0) == 0.0


def test_sign_str_is_zero():
    assert rp._sign("x") == 0


def test_sign_dict_is_zero():
    assert rp._sign({}) == 0


def test_sign_none_is_zero():
    assert rp._sign(None) == 0


def test_sign_positive():
    assert rp._sign(5) == 1


def test_sign_negative():
    assert rp._sign(-3.2) == -1


def test_sign_zero():
    assert rp._sign(0) == 0


# ============================================================================ #
# _alt_lean
# ============================================================================ #

_SYNTH_ALT_BT = {
    "tickers": {
        "NVDA": {
            "congress_net": 19,
            "insider_net_usd": 5000,
        }
    }
}

_SYNTH_MM_INDEX = {
    "NVDA": {"signal_score": 80}
}


def test_alt_lean_present_with_nvda():
    result = rp._alt_lean(["NVDA"], _SYNTH_ALT_BT, _SYNTH_MM_INDEX)
    assert result["present"] is True


def test_alt_lean_lean_positive():
    result = rp._alt_lean(["NVDA"], _SYNTH_ALT_BT, _SYNTH_MM_INDEX)
    assert result["lean"] == 1


def test_alt_lean_drivers_includes_nvda():
    result = rp._alt_lean(["NVDA"], _SYNTH_ALT_BT, _SYNTH_MM_INDEX)
    assert "NVDA" in result["drivers"]


def test_alt_lean_avg_signal():
    result = rp._alt_lean(["NVDA"], _SYNTH_ALT_BT, _SYNTH_MM_INDEX)
    assert result["avg_signal"] == 80.0


def test_alt_lean_empty_covered():
    result = rp._alt_lean([], {}, {})
    assert result == {"present": False}


def test_alt_lean_empty_bt_and_mm():
    result = rp._alt_lean(["NVDA"], {}, {})
    assert result == {"present": False}


def test_alt_lean_lowercase_ticker():
    # covered tickers get uppercased internally
    result = rp._alt_lean(["nvda"], _SYNTH_ALT_BT, _SYNTH_MM_INDEX)
    assert result["present"] is True
    assert "NVDA" in result["drivers"]


# ============================================================================ #
# _flow_lean
# ============================================================================ #

_SYNTH_FF = {
    "NVDA": [{"direction": "accumulating"}, {"direction": "accumulating"}],
    "X": [{"direction": "distributing"}],
}


def test_flow_lean_net_accumulating():
    # 2 accumulating for NVDA vs 1 distributing for X, but covered is only NVDA
    result = rp._flow_lean(["NVDA"], _SYNTH_FF)
    assert result["present"] is True
    assert result["lean"] == 1


def test_flow_lean_net_distributing():
    result = rp._flow_lean(["X"], _SYNTH_FF)
    assert result["present"] is True
    assert result["lean"] == -1


def test_flow_lean_both_covered_reflects_net():
    # NVDA has 2 accum, X has 1 dist → net accum wins
    result = rp._flow_lean(["NVDA", "X"], _SYNTH_FF)
    assert result["present"] is True
    assert result["lean"] == 1


def test_flow_lean_empty_covered():
    result = rp._flow_lean([], _SYNTH_FF)
    assert result == {"present": False}


def test_flow_lean_ticker_not_in_ff():
    result = rp._flow_lean(["ZZZZZ"], _SYNTH_FF)
    assert result == {"present": False}


# ============================================================================ #
# _options_lean (monkeypatch _load)
# ============================================================================ #

_SYNTH_GEX = {
    "summary": {
        "skew": 1.5,
        "put_call_oi_ratio": 0.8,
        "regime": "positive gamma",
    }
}


def test_options_lean_present_bullish(monkeypatch):
    monkeypatch.setattr(rp, "_load", lambda _path: _SYNTH_GEX)
    result = rp._options_lean(["NVDA"])
    assert result["present"] is True
    assert result["lean"] == 1


def test_options_lean_no_gex(monkeypatch):
    monkeypatch.setattr(rp, "_load", lambda _path: None)
    result = rp._options_lean(["NVDA"])
    assert result == {"present": False}


def test_options_lean_empty_covered(monkeypatch):
    monkeypatch.setattr(rp, "_load", lambda _path: _SYNTH_GEX)
    result = rp._options_lean([])
    assert result == {"present": False}


def test_options_lean_dict_skew_does_not_raise(monkeypatch):
    """Non-numeric (dict) skew must not raise — _num guards it and treats as absent."""
    bad_gex = {"summary": {"skew": {"nested": "oops"}, "put_call_oi_ratio": 0.8, "regime": "positive gamma"}}
    monkeypatch.setattr(rp, "_load", lambda _path: bad_gex)
    # Should not raise
    result = rp._options_lean(["NVDA"])
    # present because put_call_oi_ratio and regime are still valid
    assert isinstance(result, dict)
    assert "present" in result


def test_options_lean_str_skew_does_not_raise(monkeypatch):
    """String skew must not raise."""
    bad_gex = {"summary": {"skew": "N/A", "put_call_oi_ratio": None, "regime": ""}}
    monkeypatch.setattr(rp, "_load", lambda _path: bad_gex)
    result = rp._options_lean(["NVDA"])
    assert isinstance(result, dict)


def test_options_lean_bearish_skew(monkeypatch):
    bearish_gex = {"summary": {"skew": -2.0, "put_call_oi_ratio": 1.5, "regime": "negative gamma"}}
    monkeypatch.setattr(rp, "_load", lambda _path: bearish_gex)
    result = rp._options_lean(["NVDA"])
    assert result["present"] is True
    assert result["lean"] == -1


# ============================================================================ #
# _crowd_penalty
# ============================================================================ #

def test_crowd_penalty_distribution_and_wsb():
    alt_bt = {"tickers": {"NVDA": {"dpi_lean": "distribution", "wsb_mentions": 25}}}
    result = rp._crowd_penalty(["NVDA"], alt_bt)
    assert result["penalty"] > 0
    assert result["dark_pool_distribution"] == 1
    assert result["retail_buzz"] == 1


def test_crowd_penalty_dpi_only():
    alt_bt = {"tickers": {"NVDA": {"dpi_lean": "distribution", "wsb_mentions": 0}}}
    result = rp._crowd_penalty(["NVDA"], alt_bt)
    assert result["penalty"] == 5.0
    assert result["dark_pool_distribution"] == 1
    assert result["retail_buzz"] == 0


def test_crowd_penalty_wsb_threshold_below():
    # 19 mentions < 20 → no wsb penalty
    alt_bt = {"tickers": {"NVDA": {"dpi_lean": "accumulation", "wsb_mentions": 19}}}
    result = rp._crowd_penalty(["NVDA"], alt_bt)
    assert result["retail_buzz"] == 0
    assert result["penalty"] == 0.0


def test_crowd_penalty_wsb_threshold_at():
    # exactly 20 → wsb penalty kicks in
    alt_bt = {"tickers": {"NVDA": {"dpi_lean": "accumulation", "wsb_mentions": 20}}}
    result = rp._crowd_penalty(["NVDA"], alt_bt)
    assert result["retail_buzz"] == 1
    assert result["penalty"] > 0


def test_crowd_penalty_none():
    result = rp._crowd_penalty(["NVDA"], {})
    assert result["penalty"] == 0.0


def test_crowd_penalty_capped_at_15():
    # Many tickers with distribution + wsb → capped at 15
    many = {t: {"dpi_lean": "distribution", "wsb_mentions": 100} for t in ["A", "B", "C", "D", "E"]}
    alt_bt = {"tickers": many}
    result = rp._crowd_penalty(["A", "B", "C", "D", "E"], alt_bt)
    assert result["penalty"] <= 15.0


# ============================================================================ #
# _decay_for
# ============================================================================ #

def _make_hist(basket: str, state: str, n_prior: int, today: date, same_state_recent: int = 0) -> dict:
    """Build synthetic hist dict with n_prior consecutive same-state rows, plus
    same_state_recent rows all in the past 7 days (for flip counting)."""
    rows = []
    # prior consecutive rows (older, same state)
    for i in range(n_prior, 0, -1):
        d = (today - timedelta(days=i + 10)).isoformat()
        rows.append({"date": d, "basket": basket, "state": state})
    # recent rows for flip counting (last 7 days), alternating state
    alt_state = "QUIET" if state != "QUIET" else "POSITIVE_DIVERGENCE"
    for i in range(same_state_recent, 0, -1):
        d = (today - timedelta(days=i)).isoformat()
        rows.append({"date": d, "basket": basket, "state": alt_state if i % 2 == 0 else state})
    return {"_rows": rows, "_path": Path("/tmp/fake_history.jsonl"), "_today": today}


def test_decay_for_days_in_state_accumulates():
    hist = _make_hist("basket_x", "CONFIRMED_UP", n_prior=3, today=_TODAY)
    result = rp._decay_for("basket_x", "CONFIRMED_UP", hist)
    # 3 prior consecutive same-state rows → days_in_state = 4 (1 + 3)
    assert result["days_in_state"] == 4


def test_decay_for_no_prior_rows():
    hist = {"_rows": [], "_path": Path("/tmp/fake_history.jsonl"), "_today": _TODAY}
    result = rp._decay_for("basket_x", "CONFIRMED_UP", hist)
    assert result["days_in_state"] == 1
    assert result["flip_7d"] == 0


def test_decay_for_flip_7d_counted():
    today = _TODAY
    rows = []
    # alternating states in the last 7 days → many flips
    states = ["POSITIVE_DIVERGENCE", "QUIET", "POSITIVE_DIVERGENCE", "QUIET"]
    for i, s in enumerate(states):
        d = (today - timedelta(days=i + 1)).isoformat()
        rows.append({"date": d, "basket": "basket_x", "state": s})
    hist = {"_rows": rows, "_path": Path("/tmp/fake.jsonl"), "_today": today}
    result = rp._decay_for("basket_x", "POSITIVE_DIVERGENCE", hist)
    assert result["flip_7d"] >= 1


def test_decay_for_different_basket_ignored():
    rows = [
        {"date": (_TODAY - timedelta(days=2)).isoformat(), "basket": "other_basket", "state": "CONFIRMED_UP"},
        {"date": (_TODAY - timedelta(days=1)).isoformat(), "basket": "other_basket", "state": "CONFIRMED_UP"},
    ]
    hist = {"_rows": rows, "_path": Path("/tmp/fake.jsonl"), "_today": _TODAY}
    result = rp._decay_for("basket_x", "CONFIRMED_UP", hist)
    # no rows for basket_x → starts at 1
    assert result["days_in_state"] == 1


# ============================================================================ #
# enrich()
# ============================================================================ #

def test_enrich_full_pipeline(monkeypatch, tmp_path):
    """Feed a synthetic radar through enrich() with all I/O monkeypatched."""
    # Monkeypatch _load to return synthetic data for any path
    def fake_load(rel):
        if "by_ticker" in str(rel):
            return {"tickers": {"NVDA": {"congress_net": 10, "insider_net_usd": 3000}}}
        if "mastermind" in str(rel):
            return {"signals": [{"ticker": "NVDA", "signal_score": 75}]}
        if "fund_flows" in str(rel):
            return {"NVDA": [{"direction": "accumulating"}]}
        if "gex/NVDA" in str(rel):
            return {"summary": {"skew": 1.0, "put_call_oi_ratio": 0.85, "regime": "positive gamma"}}
        return {}

    monkeypatch.setattr(rp, "_load", fake_load)

    # Monkeypatch _regime to a known value
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": "q1", "quad_name": "Goldilocks",
                                                 "liquidity": None})

    # Monkeypatch _state_history so it returns a hist pointing to tmp_path and never
    # writes to the real data/radar/state_history.jsonl
    fake_hist_path = tmp_path / "state_history.jsonl"

    def fake_state_history(today):
        return {"_rows": [], "_path": fake_hist_path, "_today": today}

    monkeypatch.setattr(rp, "_state_history", fake_state_history)

    radar = {
        "flags": [
            {
                "basket": "x",
                "name": "Test Basket",
                "state": "CONFIRMED_UP",
                "salience": 2.0,
                "observable": {"dir": 1, "covered": ["NVDA"]},
            }
        ]
    }

    result = rp.enrich(radar, today=_TODAY)

    # top-level markers
    assert result["enriched"] is True
    assert "regime" in result
    assert "edge_ranked" in result

    # flag received enrichment fields
    flag = result["flags"][0]
    assert "edge_score" in flag
    edge = flag["edge_score"]
    assert isinstance(edge, int)
    assert 0 <= edge <= 100

    assert "confirm" in flag
    assert "alt" in flag["confirm"]
    assert "flows" in flag["confirm"]
    assert "options" in flag["confirm"]
    assert "crowd" in flag["confirm"]

    assert "regime" in flag
    assert "decay" in flag
    assert "drivers" in flag

    # edge_ranked is sorted descending
    ranked = result["edge_ranked"]
    scores = [r["edge_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_enrich_no_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "_load", lambda _: {})
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})

    fake_hist_path = tmp_path / "state_history.jsonl"
    monkeypatch.setattr(rp, "_state_history", lambda today: {"_rows": [], "_path": fake_hist_path, "_today": today})

    radar = {"flags": []}
    result = rp.enrich(radar, today=_TODAY)
    assert result["enriched"] is True
    assert result["edge_ranked"] == []


def test_enrich_dict_skew_does_not_raise(monkeypatch, tmp_path):
    """Non-numeric GEX skew must not crash enrich()."""
    def fake_load(rel):
        if "gex" in str(rel):
            return {"summary": {"skew": {"bad": "value"}, "regime": ""}}
        return {}

    monkeypatch.setattr(rp, "_load", fake_load)
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})

    fake_hist_path = tmp_path / "state_history.jsonl"
    monkeypatch.setattr(rp, "_state_history", lambda today: {"_rows": [], "_path": fake_hist_path, "_today": today})

    radar = {
        "flags": [
            {"basket": "y", "name": "Y", "state": "POSITIVE_DIVERGENCE",
             "salience": 1.0, "observable": {"dir": 1, "covered": ["NVDA"]}}
        ]
    }
    result = rp.enrich(radar, today=_TODAY)
    assert result["enriched"] is True
    assert "edge_score" in result["flags"][0]


def test_enrich_does_not_write_real_state_history(monkeypatch, tmp_path):
    """Critical: enrich() must not write to data/radar/state_history.jsonl."""
    import os
    real_path = Path(__file__).resolve().parent.parent / "data" / "radar" / "state_history.jsonl"

    monkeypatch.setattr(rp, "_load", lambda _: {})
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})

    fake_hist_path = tmp_path / "state_history.jsonl"
    monkeypatch.setattr(rp, "_state_history", lambda today: {"_rows": [], "_path": fake_hist_path, "_today": today})

    was_present_before = real_path.exists()
    mtime_before = real_path.stat().st_mtime if was_present_before else None

    radar = {"flags": [{"basket": "z", "state": "CONFIRMED_UP", "salience": 1.0,
                        "observable": {"dir": 1, "covered": []}}]}
    rp.enrich(radar, today=_TODAY)

    if was_present_before and mtime_before is not None:
        assert real_path.stat().st_mtime == mtime_before, "enrich() must not modify the real state_history.jsonl"


# ============================================================================ #
# _prev_state_and_strip
# ============================================================================ #

def _make_hist_for_strip(basket: str, prior_rows: list, today: date) -> dict:
    """Build a hist dict from explicit prior rows + a fake path."""
    return {"_rows": prior_rows, "_path": Path("/tmp/fake_strip.jsonl"), "_today": today}


def test_prev_state_no_history():
    hist = _make_hist_for_strip("basket_a", [], _TODAY)
    prev, strip = rp._prev_state_and_strip("basket_a", hist)
    assert prev is None
    assert strip == []  # no prior rows; today entry appended by enrich(), not _prev_state_and_strip


def test_prev_state_returns_last_prior_date():
    rows = [
        {"date": "2026-06-18", "basket": "basket_a", "state": "QUIET"},
        {"date": "2026-06-19", "basket": "basket_a", "state": "POSITIVE_DIVERGENCE"},
        # today row should be excluded (date == _TODAY)
        {"date": _TODAY.isoformat(), "basket": "basket_a", "state": "CONFIRMED_UP"},
    ]
    hist = _make_hist_for_strip("basket_a", rows, _TODAY)
    prev, strip = rp._prev_state_and_strip("basket_a", hist)
    # most recent PRIOR to today is 2026-06-19
    assert prev == "POSITIVE_DIVERGENCE"


def test_prev_state_today_rows_excluded():
    """Rows with date == today must not influence prev_state."""
    rows = [
        {"date": "2026-06-15", "basket": "basket_a", "state": "QUIET"},
        {"date": _TODAY.isoformat(), "basket": "basket_a", "state": "CONFIRMED_UP"},
    ]
    hist = _make_hist_for_strip("basket_a", rows, _TODAY)
    prev, strip = rp._prev_state_and_strip("basket_a", hist)
    assert prev == "QUIET"  # today's row excluded


def test_state_strip_oldest_first():
    rows = [
        {"date": "2026-06-01", "basket": "basket_a", "state": "QUIET"},
        {"date": "2026-06-10", "basket": "basket_a", "state": "POSITIVE_DIVERGENCE"},
        {"date": "2026-06-19", "basket": "basket_a", "state": "CONFIRMED_UP"},
    ]
    hist = _make_hist_for_strip("basket_a", rows, _TODAY)
    _, strip = rp._prev_state_and_strip("basket_a", hist)
    # Strip from _prev_state_and_strip is prior rows only (oldest→newest), no today entry yet
    assert strip[0]["d"] == "06-01"
    assert strip[-1]["d"] == "06-19"
    assert strip[-1]["s"] == "CONFIRMED_UP"


def test_state_strip_max_14():
    # Create 20 prior rows
    rows = [
        {"date": (date(2026, 5, 1) + timedelta(days=i)).isoformat(), "basket": "basket_a", "state": "QUIET"}
        for i in range(20)
    ]
    hist = _make_hist_for_strip("basket_a", rows, _TODAY)
    _, strip = rp._prev_state_and_strip("basket_a", hist)
    assert len(strip) == 14  # max 14 prior rows


def test_state_strip_different_basket_excluded():
    rows = [
        {"date": "2026-06-18", "basket": "other_basket", "state": "QUIET"},
        {"date": "2026-06-19", "basket": "basket_a", "state": "POSITIVE_DIVERGENCE"},
    ]
    hist = _make_hist_for_strip("basket_a", rows, _TODAY)
    prev, strip = rp._prev_state_and_strip("basket_a", hist)
    assert prev == "POSITIVE_DIVERGENCE"
    assert len(strip) == 1


# ============================================================================ #
# enrich() — prev_state, state_strip, changes
# ============================================================================ #

def _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows: list, today: date = _TODAY):
    """Helper: wire up monkeypatches for enrich() with seeded history."""
    monkeypatch.setattr(rp, "_load", lambda _: {})
    monkeypatch.setattr(rp, "_regime", lambda: {"mult": 1.0, "quad": None, "quad_name": None, "liquidity": None})
    fake_hist_path = tmp_path / "state_history.jsonl"

    def fake_state_history(td):
        return {"_rows": hist_rows, "_path": fake_hist_path, "_today": td}

    monkeypatch.setattr(rp, "_state_history", fake_state_history)


def test_enrich_prev_state_and_strip_from_history(monkeypatch, tmp_path):
    """prev_state reflects the prior date; state_strip ends with today's state."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-23", "basket": "basket_a", "state": "QUIET"},
        {"date": "2026-06-24", "basket": "basket_a", "state": "POSITIVE_DIVERGENCE"},
        # today row already present in history — must be excluded from prev computation
        {"date": today.isoformat(), "basket": "basket_a", "state": "QUIET"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "state": "CONFIRMED_UP",
             "salience": 1.0, "observable": {"dir": 1, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=today)
    flag = result["flags"][0]

    # prev_state should be from 2026-06-24 (today row excluded)
    assert flag["prev_state"] == "POSITIVE_DIVERGENCE"
    # state_strip ends with today entry
    assert flag["state_strip"][-1]["d"] == "06-25"
    assert flag["state_strip"][-1]["s"] == "CONFIRMED_UP"
    # strip has 2 prior rows + today
    assert len(flag["state_strip"]) == 3


def test_enrich_state_strip_empty_history(monkeypatch, tmp_path):
    """With no history, state_strip is just today's entry."""
    _make_enrich_monkeypatches(monkeypatch, tmp_path, [], _TODAY)

    radar = {
        "flags": [
            {"basket": "basket_b", "name": "B", "state": "QUIET",
             "salience": 0.5, "observable": {"dir": 0, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=_TODAY)
    flag = result["flags"][0]

    assert flag["prev_state"] is None
    assert len(flag["state_strip"]) == 1
    assert flag["state_strip"][0]["s"] == "QUIET"
    assert flag["state_strip"][0]["d"] == _TODAY.isoformat()[5:]


def test_enrich_changes_new_divergence(monkeypatch, tmp_path):
    """Basket that was NOT a _DIVERGENCE and now IS one → new_divergences."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-24", "basket": "basket_a", "state": "QUIET"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "name_zh": "A中", "state": "POSITIVE_DIVERGENCE",
             "salience": 1.0, "observable": {"dir": 1, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=today)
    changes = result["changes"]

    assert changes["prev_date"] == "2026-06-24"
    assert len(changes["new_divergences"]) == 1
    assert changes["new_divergences"][0]["basket"] == "basket_a"
    assert changes["new_divergences"][0]["from"] == "QUIET"
    assert changes["new_divergences"][0]["to"] == "POSITIVE_DIVERGENCE"
    assert len(changes["resolved"]) == 0
    assert len(changes["flips"]) == 0


def test_enrich_changes_resolved(monkeypatch, tmp_path):
    """Basket that WAS a _DIVERGENCE and now is NOT → resolved."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-24", "basket": "basket_a", "state": "NEGATIVE_DIVERGENCE"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "name_zh": "", "state": "QUIET",
             "salience": 0.5, "observable": {"dir": 0, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=today)
    changes = result["changes"]

    assert len(changes["resolved"]) == 1
    assert changes["resolved"][0]["from"] == "NEGATIVE_DIVERGENCE"
    assert changes["resolved"][0]["to"] == "QUIET"
    assert len(changes["new_divergences"]) == 0
    assert len(changes["flips"]) == 0


def test_enrich_changes_flip(monkeypatch, tmp_path):
    """Any other prev!=now change (neither new divergence nor resolved) → flips."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-24", "basket": "basket_a", "state": "CONFIRMED_UP"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "name_zh": "", "state": "QUIET",
             "salience": 0.0, "observable": {"dir": 0, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=today)
    changes = result["changes"]

    assert len(changes["flips"]) == 1
    assert changes["flips"][0]["from"] == "CONFIRMED_UP"
    assert changes["flips"][0]["to"] == "QUIET"
    assert len(changes["new_divergences"]) == 0
    assert len(changes["resolved"]) == 0


def test_enrich_changes_unchanged_not_in_any_list(monkeypatch, tmp_path):
    """Unchanged state appears in none of the change lists."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-24", "basket": "basket_a", "state": "QUIET"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "name_zh": "", "state": "QUIET",
             "salience": 0.0, "observable": {"dir": 0, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=today)
    changes = result["changes"]

    assert len(changes["new_divergences"]) == 0
    assert len(changes["resolved"]) == 0
    assert len(changes["flips"]) == 0


def test_enrich_changes_empty_history(monkeypatch, tmp_path):
    """No history → prev_date None, all change lists empty."""
    _make_enrich_monkeypatches(monkeypatch, tmp_path, [], _TODAY)

    radar = {
        "flags": [
            {"basket": "basket_a", "name": "A", "name_zh": "", "state": "POSITIVE_DIVERGENCE",
             "salience": 1.0, "observable": {"dir": 1, "covered": []}}
        ]
    }
    result = rp.enrich(radar, today=_TODAY)
    changes = result["changes"]

    assert changes["prev_date"] is None
    assert changes["new_divergences"] == []
    assert changes["resolved"] == []
    assert changes["flips"] == []


def test_enrich_changes_mixed_baskets(monkeypatch, tmp_path):
    """Multiple baskets: one new div, one resolved, one unchanged, one flip."""
    today = date(2026, 6, 25)
    hist_rows = [
        {"date": "2026-06-24", "basket": "basket_new_div", "state": "QUIET"},
        {"date": "2026-06-24", "basket": "basket_resolved", "state": "POSITIVE_DIVERGENCE"},
        {"date": "2026-06-24", "basket": "basket_unchanged", "state": "QUIET"},
        {"date": "2026-06-24", "basket": "basket_flip", "state": "CONFIRMED_UP"},
    ]
    _make_enrich_monkeypatches(monkeypatch, tmp_path, hist_rows, today)

    radar = {
        "flags": [
            {"basket": "basket_new_div", "name": "ND", "name_zh": "", "state": "NEGATIVE_DIVERGENCE",
             "salience": 1.0, "observable": {"dir": -1, "covered": []}},
            {"basket": "basket_resolved", "name": "R", "name_zh": "", "state": "QUIET",
             "salience": 0.5, "observable": {"dir": 0, "covered": []}},
            {"basket": "basket_unchanged", "name": "U", "name_zh": "", "state": "QUIET",
             "salience": 0.0, "observable": {"dir": 0, "covered": []}},
            {"basket": "basket_flip", "name": "F", "name_zh": "", "state": "CONFIRMED_DOWN",
             "salience": 0.5, "observable": {"dir": -1, "covered": []}},
        ]
    }
    result = rp.enrich(radar, today=today)
    changes = result["changes"]

    assert len(changes["new_divergences"]) == 1
    assert changes["new_divergences"][0]["basket"] == "basket_new_div"
    assert len(changes["resolved"]) == 1
    assert changes["resolved"][0]["basket"] == "basket_resolved"
    assert len(changes["flips"]) == 1
    assert changes["flips"][0]["basket"] == "basket_flip"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
