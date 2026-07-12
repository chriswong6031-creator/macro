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
    for key in ("winner_autopsy", "thesis_funnel", "labels", "delivery_waterfall",
                "falsifier_packets"):
        assert key in d
        assert isinstance(d[key], dict)


def test_graceful_degradation_all_missing(tmp_path, monkeypatch):
    """With no artifacts present, every sub-block fails open, panel still ok."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(long_hold, "_WINNER_PANEL", missing)
    monkeypatch.setattr(long_hold, "_THESIS_FUNNEL", missing)
    monkeypatch.setattr(long_hold, "_LABELS", missing)
    monkeypatch.setattr(long_hold, "_WATERFALL", missing)
    monkeypatch.setattr(long_hold, "_FALSIFIER_PACKETS_MANIFEST", missing)

    d = long_hold.panel()
    assert d["ok"] is True
    assert d["generated_at"] is None
    assert d["winner_autopsy"]["available"] is False
    assert "reason" in d["winner_autopsy"]
    assert d["thesis_funnel"]["available"] is False
    assert d["labels"]["available"] is False
    assert d["delivery_waterfall"]["available"] is False
    assert d["falsifier_packets"]["available"] is False


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


def test_waterfall_block_missing(tmp_path, monkeypatch):
    """_waterfall_block() fails open when delivery_waterfall_panel.json is missing."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(long_hold, "_WATERFALL", missing)

    d = long_hold.panel()
    assert d["ok"] is True
    assert "delivery_waterfall" in d
    assert d["delivery_waterfall"]["available"] is False
    assert "reason" in d["delivery_waterfall"]


def test_waterfall_block_happy_path(tmp_path, monkeypatch):
    """A conforming delivery_waterfall_panel.json is surfaced through the panel."""
    panel_obj = {
        "schema": "delivery_waterfall_panel.v1",
        "generated_at": "2026-07-12T08:00:00+00:00",
        "as_of": "2026-07-12",
        "counts": {
            "n_episodes": 120,
            "n_ok": 80,
            "n_refused": 40,
            "by_refusal_reason": {"no_fundamentals_at_anchor": 20, "share_basis_break": 10},
            "by_path": {"pe_identity": 60, "ev_revenue": 20},
        },
        "coverage_notes": ["display-only"],
        "rows": [
            {
                "ticker": "NVDA",
                "t0": "2023-06-01",
                "path": "pe_identity",
                "dlog_price": 1.2,
                "legs_pct": {"rev_ps_delivery": 45.0, "valuation_mix_accounting_residual": 55.0},
                "warnings": [],
                "price_source": "yahoo",
                "basis_mismatch": False,
            }
        ],
        "refused_examples": [
            {"ticker": "XYZ", "t0": "2023-03-01", "refusal_reasons": ["no_fundamentals_at_anchor"]}
        ],
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
    }
    p = tmp_path / "delivery_waterfall_panel.json"
    p.write_text(json.dumps(panel_obj))
    monkeypatch.setattr(long_hold, "_WATERFALL", p)

    d = long_hold.panel()
    assert d["ok"] is True
    wf = d["delivery_waterfall"]
    assert wf["available"] is True
    assert wf["generated_at"] == "2026-07-12T08:00:00+00:00"
    assert wf["as_of"] == "2026-07-12"
    assert wf["counts"]["n_episodes"] == 120
    assert wf["counts"]["n_ok"] == 80
    assert len(wf["rows"]) == 1
    assert wf["rows"][0]["ticker"] == "NVDA"
    assert len(wf["refused_examples"]) == 1
    assert wf["refused_examples"][0]["ticker"] == "XYZ"


def test_panel_smoke_includes_waterfall():
    """panel() returns delivery_waterfall key (fail-open ok)."""
    d = long_hold.panel()
    assert d["ok"] is True
    assert "delivery_waterfall" in d
    assert isinstance(d["delivery_waterfall"], dict)


# ---------------------------------------------------------------------------
# falsifier_packets sub-block (LHB-W3 A1 packet manifest)
# ---------------------------------------------------------------------------

def test_panel_smoke_includes_falsifier_packets():
    """panel() returns falsifier_packets key (fail-open ok)."""
    d = long_hold.panel()
    assert d["ok"] is True
    assert "falsifier_packets" in d
    assert isinstance(d["falsifier_packets"], dict)


def test_falsifier_packets_block_missing_file(tmp_path, monkeypatch):
    """_falsifier_packets_block() fails open when manifest is missing."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(long_hold, "_FALSIFIER_PACKETS_MANIFEST", missing)

    d = long_hold.panel()
    assert d["ok"] is True
    fp = d["falsifier_packets"]
    assert fp["available"] is False
    assert "reason" in fp


def test_falsifier_packets_block_happy_path(tmp_path, monkeypatch):
    """A conforming falsifier_packets_manifest.json is surfaced through the panel."""
    import json
    manifest_obj = {
        "schema": "falsifier_packets_manifest.v1",
        "generated_at": "2026-07-12T10:00:00+00:00",
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
        "n_tickers": 1703,
        "n_with_signal": 842,
        "n_summary_only": 861,
        "sensor_status_counts": {
            "challenged": 1200,
            "no_break_observed": 900,
            "not_observed": 400,
            "unverifiable": 500,
            "broken": 3,
        },
        "a6_item_counts": {
            "5.02": 420,
            "1.02": 38,
            "2.04": 2,
            "1.03": 3,
        },
        "elapsed_seconds": 12.4,
    }
    p = tmp_path / "falsifier_packets_manifest.json"
    p.write_text(json.dumps(manifest_obj))
    monkeypatch.setattr(long_hold, "_FALSIFIER_PACKETS_MANIFEST", p)

    d = long_hold.panel()
    assert d["ok"] is True
    fp = d["falsifier_packets"]
    assert fp["available"] is True
    assert fp["generated_at"] == "2026-07-12T10:00:00+00:00"
    assert fp["n_tickers"] == 1703
    assert fp["n_with_signal"] == 842
    assert fp["n_summary_only"] == 861
    assert "sensor_status_counts" in fp
    assert fp["sensor_status_counts"]["challenged"] == 1200
    assert "a6_item_counts" in fp
    assert fp["a6_item_counts"]["1.03"] == 3
    assert "ffb_r2_coverage_copy" in fp
    # Verify FFB-R2 copy is present in the admin block
    assert "A6 is a hard-stop bus" in fp["ffb_r2_coverage_copy"]


def test_falsifier_packets_block_packet_vocab_assertion(tmp_path, monkeypatch):
    """Packet status values in manifest must not contain values outside the five-word vocab.

    The manifest carries sensor_status_counts whose keys must be in the valid
    vocabulary (LHB-R3). This test asserts that the panel block exposes those counts
    and that the test fixture itself only uses valid vocab keys.
    """
    import json
    _VALID_STATUSES = {"not_observed", "no_break_observed", "challenged", "broken", "unverifiable"}
    manifest_obj = {
        "schema": "falsifier_packets_manifest.v1",
        "generated_at": "2026-07-12T10:00:00+00:00",
        "n_tickers": 10,
        "n_with_signal": 5,
        "n_summary_only": 5,
        "sensor_status_counts": {
            "challenged": 8,
            "no_break_observed": 12,
            "not_observed": 4,
            "unverifiable": 6,
            "broken": 1,
        },
        "a6_item_counts": {"1.03": 1},
    }
    p = tmp_path / "falsifier_packets_manifest.json"
    p.write_text(json.dumps(manifest_obj))
    monkeypatch.setattr(long_hold, "_FALSIFIER_PACKETS_MANIFEST", p)

    d = long_hold.panel()
    fp = d["falsifier_packets"]
    assert fp["available"] is True

    # Assert all status keys in the surfaced block are in valid vocab
    for status_key in fp["sensor_status_counts"].keys():
        assert status_key in _VALID_STATUSES, (
            f"Invalid status key in sensor_status_counts: {status_key!r}. "
            f"Valid statuses: {_VALID_STATUSES}"
        )


def test_graceful_degradation_includes_falsifier_packets(tmp_path, monkeypatch):
    """With all artifacts missing, falsifier_packets fails open."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(long_hold, "_WINNER_PANEL", missing)
    monkeypatch.setattr(long_hold, "_THESIS_FUNNEL", missing)
    monkeypatch.setattr(long_hold, "_LABELS", missing)
    monkeypatch.setattr(long_hold, "_WATERFALL", missing)
    monkeypatch.setattr(long_hold, "_FALSIFIER_PACKETS_MANIFEST", missing)

    d = long_hold.panel()
    assert d["ok"] is True
    assert "falsifier_packets" in d
    assert d["falsifier_packets"]["available"] is False


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
