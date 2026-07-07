"""Smoke + shape tests for the admin Long-Hold Lobe panel (admin/long_hold.py).

Follows the tests/test_admin_neural_web.py convention: import the module, call
panel(), assert graceful degradation on missing artifacts, and a synthetic
happy-path via monkeypatched module-level path constants.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from admin import long_hold


def test_panel_smoke():
    """panel() never raises and always returns ok=True with the top-level shape."""
    d = long_hold.panel()
    assert d["ok"] is True
    for key in ("winner_autopsy", "thesis_funnel", "labels"):
        assert key in d
        assert isinstance(d[key], dict)


def test_graceful_degradation_all_missing(tmp_path, monkeypatch):
    """With no artifacts present, every sub-block fails open, panel still ok."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(long_hold, "_WINNER_PANEL", missing)
    monkeypatch.setattr(long_hold, "_THESIS_FUNNEL", missing)
    monkeypatch.setattr(long_hold, "_LABELS", missing)

    d = long_hold.panel()
    assert d["ok"] is True
    assert d["generated_at"] is None
    assert d["winner_autopsy"]["available"] is False
    assert "reason" in d["winner_autopsy"]
    assert d["thesis_funnel"]["available"] is False
    assert d["labels"]["available"] is False


def test_synthetic_happy_path(tmp_path, monkeypatch):
    """A conforming winner_autopsy_panel.json is surfaced through the panel."""
    panel_obj = {
        "schema": "winner_autopsy_panel.v1",
        "generated_at": "2026-07-07T08:00:00Z",
        "display_only": True,
        "horizon_role": "hold_thesis",
        "census": {
            "available": True,
            "n_episodes": 42,
            "date_range": ["2014-08-11", "2026-07-02"],
            "universe_n_tickers": 1500,
            "price_source_coverage": {"yahoo": 10, "massive": 30, "dead_name": 2, "none": 0},
            "outcome_label_counts": {
                "durable_winner": 5, "clean_hold": 8, "blow_off": 12,
                "failed": 10, "unmatured": 7,
            },
            "by_era": [{"era": "2014-2017", "n_episodes": 10, "n_month_clusters": 8,
                        "durable_winner_rate": 0.1, "blow_off_rate": 0.3}],
            "notes": ["descriptive only; base rates not verdicts (WA-R5)"],
        },
        "cases": {
            "n_cases": 1,
            "items": [{
                "ticker": "MRNA", "episode_year": 2026, "case_type": "winner",
                "mechanism": "platform_rerating", "thesis_one_liner": "platform re-rating",
                "n_catalysts": 3, "case_t0": "2026-01-20", "engine_t0": None,
                "case_joined": False, "reconcile": "engine_no_onset",
                "file": "research/winners/cases/MRNA_2026.md",
            }],
        },
        "watch": {
            "available": True,
            "as_of": "2026-07-07",
            "state_counts": {"breakaway": 2, "emerging": 5, "digestion": 1,
                             "continuation": 0, "failed": 3},
            "top": [{
                "ticker": "AAA", "sector": "Health Care", "benchmark": "XBI",
                "state": "breakaway", "excess_21d_pp": 49.2, "excess_42d_pp": 55.0,
                "new_high_63d": True, "dollar_vol_z21": 1.6, "days_in_state": 3,
                "gex_state": "TREND", "hazards": ["extended_after_vertical_move"],
                "context": {"context_only": True, "note": "13F 45d-lagged"},
            }],
        },
        "clocks": [{"id": "winner-autopsy-watch-ledger", "come_back_on": "2026-10-15",
                    "note": "first watch-ledger read", "status": "accruing"}],
    }
    p = tmp_path / "winner_autopsy_panel.json"
    p.write_text(json.dumps(panel_obj))
    monkeypatch.setattr(long_hold, "_WINNER_PANEL", p)

    d = long_hold.panel()
    assert d["ok"] is True
    assert d["generated_at"] == "2026-07-07T08:00:00Z"

    wa = d["winner_autopsy"]
    assert wa["available"] is True
    assert wa["census"]["n_episodes"] == 42
    assert wa["census"]["outcome_label_counts"]["durable_winner"] == 5
    assert wa["cases"]["n_cases"] == 1
    assert wa["cases"]["items"][0]["ticker"] == "MRNA"
    assert wa["watch"]["available"] is True
    assert wa["watch"]["state_counts"]["breakaway"] == 2
    # WA-R1: no composite score leaks into the trimmed watch rows
    assert "score" not in wa["watch"]["top"][0]
    assert wa["watch"]["top"][0]["ticker"] == "AAA"
    assert wa["clocks"][0]["id"] == "winner-autopsy-watch-ledger"


def test_watch_top_trimmed_to_15(tmp_path, monkeypatch):
    """watch.top is capped for display."""
    rows = [{"ticker": f"T{i}", "state": "emerging", "excess_21d_pp": float(i)}
            for i in range(30)]
    panel_obj = {
        "schema": "winner_autopsy_panel.v1",
        "generated_at": "2026-07-07T08:00:00Z",
        "census": {"available": True},
        "cases": {"n_cases": 0, "items": []},
        "watch": {"available": True, "as_of": "2026-07-07",
                  "state_counts": {"emerging": 30}, "top": rows},
        "clocks": [],
    }
    p = tmp_path / "winner_autopsy_panel.json"
    p.write_text(json.dumps(panel_obj))
    monkeypatch.setattr(long_hold, "_WINNER_PANEL", p)

    d = long_hold.panel()
    assert len(d["winner_autopsy"]["watch"]["top"]) == 15
