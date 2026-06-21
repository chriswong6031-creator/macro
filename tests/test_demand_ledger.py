"""Tests for engine/demand_ledger.py — the demand-chain scored ledger (Phase 2)."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from engine import demand_ledger as dl


def _read(tkr, ahead=True, leading=True):
    return {"chain_key": "ai_datacenter", "leading": leading, "tier": "compute",
            "divergence": "ahead_of_consensus" if ahead else "consensus_at_risk",
            "trend": "accelerating", "yoy_pct": 69.0, "fy_latest": 2025, "horizon_d": 126}


def test_thesis_ahead_of_consensus_is_bullish():
    th = dl._thesis_for("NVDA", _read("NVDA", ahead=True), "2026-06-19", 100.0, 750.0)
    assert th is not None
    chk = th["falsifier"]["check"]
    assert chk["kind"] == "rel_return" and chk["subject_ticker"] == "NVDA" and chk["vs"] == "SPY"
    assert chk["op"] == "<" and chk["threshold"] == -0.05
    assert th["lean"] == "outperform" and th["conviction"] == "low"
    assert th["vintage"] == "ai_datacenter:NVDA:2025:ahead_of_consensus"
    assert th["entry_levels"] == {"NVDA": 100.0, "SPY": 750.0}
    assert th["status"] == "open" and th["check_by"]


def test_thesis_consensus_at_risk_is_bearish():
    th = dl._thesis_for("AMAT", _read("AMAT", ahead=False), "2026-06-19", 200.0, 750.0)
    chk = th["falsifier"]["check"]
    assert chk["op"] == ">" and chk["threshold"] == 0.05
    assert th["lean"] == "underperform"


def test_thesis_none_for_non_actionable_or_non_leading():
    aligned = {**_read("NVDA"), "divergence": "aligned"}
    assert dl._thesis_for("NVDA", aligned, "2026-06-19", 100.0, 750.0) is None
    coincident = {**_read("BLDR"), "leading": False}
    assert dl._thesis_for("BLDR", coincident, "2026-06-19", 100.0, 750.0) is None


def test_thesis_none_without_prices():
    assert dl._thesis_for("NVDA", _read("NVDA"), "2026-06-19", None, 750.0) is None
    assert dl._thesis_for("NVDA", _read("NVDA"), "2026-06-19", 100.0, None) is None


def test_emit_dedupes_by_vintage(tmp_path, monkeypatch):
    d = tmp_path / "data" / "demand_chain"
    d.mkdir(parents=True)
    existing = dl._thesis_for("NVDA", _read("NVDA"), "2026-06-01", 90.0, 700.0)
    (d / "theses.jsonl").write_text(json.dumps(existing) + "\n")
    # build_theses returns the SAME vintage (NVDA) + a NEW one (QCOM) → only QCOM appends
    nvda_again = dl._thesis_for("NVDA", _read("NVDA"), "2026-06-19", 100.0, 750.0)
    qcom = dl._thesis_for("QCOM", _read("QCOM"), "2026-06-19", 150.0, 750.0)
    monkeypatch.setattr(dl, "build_theses", lambda root=None, today=None: [nvda_again, qcom])
    fresh = dl.emit(root=tmp_path, today=date(2026, 6, 19))
    assert [t["subject"] for t in fresh] == ["QCOM"]
    lines = (d / "theses.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2                      # original NVDA + new QCOM


def test_close_series_breadth_fallback(tmp_path):
    from engine import ai_desk as _desk
    (tmp_path / "data" / "yahoo").mkdir(parents=True)
    (tmp_path / "data" / "breadth").mkdir(parents=True)
    idx = pd.bdate_range("2026-01-01", "2026-03-01")
    # yahoo has SPY only; breadth has NVDA only
    pd.DataFrame({"close": range(len(idx))}, index=idx).to_parquet(tmp_path / "data" / "yahoo" / "SPY.parquet")
    pd.DataFrame({"NVDA": range(len(idx)), "AMD": range(len(idx))}, index=idx).to_parquet(
        tmp_path / "data" / "breadth" / "_closes_cache.parquet")
    _desk._BREADTH_MEMO.clear()
    assert _desk._close_series("SPY", tmp_path) is not None          # yahoo path
    nvda = _desk._close_series("NVDA", tmp_path)                      # breadth fallback
    assert nvda is not None and len(nvda) == len(idx)
    assert _desk._close_series("ZZZZ", tmp_path) is None             # neither


def _price_parquet(path, start, end, ret):
    """Write a data/yahoo parquet: close grows linearly from 100 to 100*(1+ret)."""
    idx = pd.bdate_range(start, end)
    close = pd.Series([100.0 * (1 + ret * i / (len(idx) - 1)) for i in range(len(idx))], index=idx)
    pd.DataFrame({"close": close}).to_parquet(path)


def test_score_hit_when_subject_outperforms(tmp_path):
    yahoo = tmp_path / "data" / "yahoo"
    yahoo.mkdir(parents=True)
    _price_parquet(yahoo / "NVDA.parquet", "2026-01-02", "2026-07-01", 0.20)   # +20%
    _price_parquet(yahoo / "SPY.parquet", "2026-01-02", "2026-07-01", 0.05)    # +5%
    d = tmp_path / "data" / "demand_chain"
    d.mkdir(parents=True)
    th = {"id": "t1", "state_asof": "2026-01-02", "check_by": "2026-06-30",
          "subject": "NVDA", "lean": "outperform", "conviction": "low",
          "entry_levels": {"NVDA": 100.0, "SPY": 100.0},
          "falsifier": {"check": {"kind": "rel_return", "subject_ticker": "NVDA",
                                  "vs": "SPY", "op": "<", "threshold": -0.05}},
          "status": "open"}
    (d / "theses.jsonl").write_text(json.dumps(th) + "\n")
    tr = dl.score(root=tmp_path, today=date(2026, 7, 15))
    assert tr["schema"] == "demand_chain_track_record.v1"
    assert tr["overall"]["n"] == 1 and tr["overall"]["hits"] == 1   # +15% rel → hit
    scored = [json.loads(x) for x in (d / "scored.jsonl").read_text().splitlines()]
    assert scored[0]["outcome"] == "hit" and scored[0]["realized"] > 0.1
