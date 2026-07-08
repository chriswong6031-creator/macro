"""Smoke + shape tests for the admin Context Lobe panel (admin/context_lobe.py).

Follows the tests/test_admin_long_hold.py convention: import the module, call
panel(), assert graceful degradation on missing artifacts, and a synthetic
happy-path via monkeypatched module-level path constants.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from admin import context_lobe


def test_panel_smoke():
    """panel() never raises and always returns ok=True with the top-level shape."""
    d = context_lobe.panel()
    assert d["ok"] is True
    for key in ("schema", "as_of", "produced_at", "is_context_only",
                "freshness", "age_hours", "lobes", "lobe_manifest",
                "candidates", "n_candidates_total", "n_candidates_shown",
                "gap_notes"):
        assert key in d, f"missing key: {key}"


def test_graceful_degradation_both_missing(tmp_path, monkeypatch):
    """With no artifacts, panel() is still ok=True with an error note."""
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(context_lobe, "_CTX_PRIMARY",  missing)
    monkeypatch.setattr(context_lobe, "_CTX_FALLBACK", missing)

    d = context_lobe.panel()
    assert d["ok"] is True
    assert "error" in d
    assert d["lobes"] == {}
    assert d["lobe_manifest"] == []
    assert d["candidates"] == []
    assert d["n_candidates_total"] == 0
    assert d["n_candidates_shown"] == 0


def test_fallback_path_used(tmp_path, monkeypatch):
    """When primary is missing, fallback is used."""
    obj = {
        "schema": "mastermind_context.v1",
        "as_of": "2026-07-07",
        "produced_at": "2026-07-08T09:00:00Z",
        "is_context_only": True,
        "lobes": {},
        "lobe_manifest": [],
        "candidate_context": {},
        "gap_notes": [],
    }
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps(obj))

    monkeypatch.setattr(context_lobe, "_CTX_PRIMARY",  tmp_path / "nope.json")
    monkeypatch.setattr(context_lobe, "_CTX_FALLBACK", fallback)

    d = context_lobe.panel()
    assert d["ok"] is True
    assert "error" not in d
    assert d["as_of"] == "2026-07-07"
    assert d["produced_at"] == "2026-07-08T09:00:00Z"


def test_synthetic_happy_path(tmp_path, monkeypatch):
    """A conforming mastermind_context.json is surfaced through the panel."""
    obj = {
        "schema": "mastermind_context.v1",
        "as_of": "2026-07-07",
        "produced_at": "2026-07-08T09:05:36Z",
        "is_context_only": True,
        "lobes": {
            "market": {
                "verdict": {
                    "verdict": "RISK_OFF",
                    "score": 40,
                    "label_en": "Risk-off",
                },
                "radar": {"state": "caution"},
            },
            "bottom_sensors": {
                "as_of": "2026-07-07",
                "n_rows": 231,
                "counts": {"WATCH": 45, "CLEAN": 3},
            },
        },
        "lobe_manifest": [
            {
                "artifact_id": "site-us-standouts",
                "path": "site/factordata/us_standouts.json",
                "asof": "2026-07-07",
                "stale": True,
                "tier": "display",
                "horizon_role": "tactical_entry",
                "storage": "git",
                "has_rich_summary": False,
            }
        ],
        "candidate_context": {
            "AAL": {
                "bottom": {
                    "as_of": "2026-07-07",
                    "bottom_state": "WATCH",
                    "trigger_age_ticks": 21.0,
                    "coiled": False,
                    "star": False,
                    "earnings_days_to": 15.0,
                },
                "options": {
                    "iv30": 0.63,
                    "gex_confirm_verdict": "neutral",
                },
                "allowed_behavior": "annotate_only",
            },
            "AMZN": {
                "bottom": {
                    "as_of": "2026-07-07",
                    "bottom_state": "WATCH",
                    "trigger_age_ticks": 23.0,
                    "coiled": False,
                    "star": False,
                    "earnings_days_to": 22.0,
                },
                "options": {
                    "iv30": 0.43,
                    "gex_confirm_verdict": "caution",
                },
                "graph_conflicts": [{"pair_id": "briefing-divergences", "severity": "note"}],
                "allowed_behavior": "annotate_only",
            },
        },
        "gap_notes": ["test gap note"],
    }
    p = tmp_path / "mastermind_context.json"
    p.write_text(json.dumps(obj))
    monkeypatch.setattr(context_lobe, "_CTX_PRIMARY",  p)
    monkeypatch.setattr(context_lobe, "_CTX_FALLBACK", tmp_path / "nope.json")

    d = context_lobe.panel()
    assert d["ok"] is True
    assert "error" not in d
    assert d["as_of"] == "2026-07-07"
    assert d["produced_at"] == "2026-07-08T09:05:36Z"
    assert d["is_context_only"] is True
    assert d["schema"] == "mastermind_context.v1"

    # lobes
    assert "market" in d["lobes"]
    assert d["lobes"]["market"]["verdict"] == "RISK_OFF"
    assert d["lobes"]["market"]["score"] == 40
    assert d["lobes"]["bottom_sensors"]["n_rows"] == 231

    # lobe_manifest
    assert len(d["lobe_manifest"]) == 1
    assert d["lobe_manifest"][0]["artifact_id"] == "site-us-standouts"

    # candidates — AMZN has more sub-blocks (graph_conflicts), should rank first
    assert d["n_candidates_total"] == 2
    assert d["n_candidates_shown"] == 2
    tickers = [r["ticker"] for r in d["candidates"]]
    assert "AMZN" in tickers
    assert "AAL" in tickers
    # AMZN richest (has graph_conflicts), should appear first
    assert tickers[0] == "AMZN"

    # gap_notes passthrough
    assert d["gap_notes"] == ["test gap note"]


def test_candidate_cap(tmp_path, monkeypatch):
    """candidate_context is capped at _CANDIDATE_CAP rows."""
    cc = {
        f"T{i:04d}": {
            "bottom": {"bottom_state": "WATCH", "trigger_age_ticks": float(i)},
            "allowed_behavior": "annotate_only",
        }
        for i in range(100)
    }
    obj = {
        "schema": "mastermind_context.v1",
        "as_of": "2026-07-07",
        "produced_at": "2026-07-08T09:00:00Z",
        "is_context_only": True,
        "lobes": {},
        "lobe_manifest": [],
        "candidate_context": cc,
        "gap_notes": [],
    }
    p = tmp_path / "mastermind_context.json"
    p.write_text(json.dumps(obj))
    monkeypatch.setattr(context_lobe, "_CTX_PRIMARY",  p)
    monkeypatch.setattr(context_lobe, "_CTX_FALLBACK", tmp_path / "nope.json")

    d = context_lobe.panel()
    assert d["n_candidates_total"] == 100
    assert d["n_candidates_shown"] == context_lobe._CANDIDATE_CAP
    assert len(d["candidates"]) == context_lobe._CANDIDATE_CAP
