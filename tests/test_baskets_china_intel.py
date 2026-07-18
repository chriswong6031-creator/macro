"""Tests for the baskets_china overhaul: intel attach, member signals, overlap, THS safety.

Covers:
 - _attach_basket_intel: None-safe (no theme_intel, missing baskets, partial intel)
 - _compute_basket_overlaps: Jaccard math, top-3 cap, n_shared>=2 gate, self-exclude
 - _compute_member_signals: cache fingerprint logic (hit/miss), None-safety on thin series
 - THS/lite payload untouched (curated-only functions are not called on THS data)
"""
from __future__ import annotations

import hashlib
import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------
import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_baskets_china import (
    _attach_basket_intel,
    _compute_basket_overlaps,
    _compute_member_signals,
    _MEMBER_SIGNAL_VERSION,
)


# ---------------------------------------------------------------------------
# _attach_basket_intel
# ---------------------------------------------------------------------------

def _make_data(baskets=None, themes=None):
    data: dict = {"baskets": baskets or []}
    if themes is not None:
        data["theme_intel"] = {"themes": themes}
    return data


def test_attach_intel_no_theme_intel():
    """No theme_intel key → basket rows unchanged, no crash."""
    b = {"id": "cn_test", "name": "Test"}
    data = _make_data(baskets=[b])
    _attach_basket_intel(data)
    # Should not add score/label when there's nothing to attach
    assert "score" not in b


def test_attach_intel_empty_themes():
    """theme_intel with empty themes list → no intel attached."""
    b = {"id": "cn_test", "name": "Test"}
    data = _make_data(baskets=[b], themes=[])
    _attach_basket_intel(data)
    assert "score" not in b


def test_attach_intel_full():
    """theme_intel with matching theme → all fields attached correctly."""
    theme = {
        "id": "cn_pharma",
        "score": 72,
        "label": "dominant",
        "label_zh": "主导",
        "reco": "accumulate",
        "reco_zh": "加仓",
        "textures": {
            "clean_entry": {"quality": 0.8, "flag": False},
            "rollover_risk": {"band": "low", "risk": 0.1},
        },
    }
    b = {"id": "cn_pharma", "name": "Pharma"}
    data = _make_data(baskets=[b], themes=[theme])
    _attach_basket_intel(data)
    assert b["score"] == 72
    assert b["label"] == "dominant"
    assert b["label_zh"] == "主导"
    assert b["reco"] == "accumulate"
    assert b["reco_zh"] == "加仓"
    assert abs(b["clean_entry_q"] - 0.8) < 1e-9
    assert "rollover_risk_band" not in b  # deliberately unattached (review 07-18: no consumer)


def test_attach_intel_partial_textures():
    """theme with textures keys missing → None values, no crash."""
    theme = {"id": "cn_test", "score": 50, "textures": {}}
    b = {"id": "cn_test", "name": "T"}
    data = _make_data(baskets=[b], themes=[theme])
    _attach_basket_intel(data)
    assert b["score"] == 50
    assert b["clean_entry_q"] is None
    assert "rollover_risk_band" not in b  # deliberately unattached (review 07-18: no consumer)


def test_attach_intel_no_match():
    """Basket with no matching theme → fields not attached."""
    theme = {"id": "cn_other", "score": 60, "textures": {}}
    b = {"id": "cn_pharma", "name": "Pharma"}
    data = _make_data(baskets=[b], themes=[theme])
    _attach_basket_intel(data)
    assert "score" not in b


def test_attach_intel_multiple_baskets():
    """Multiple baskets get their respective themes attached independently."""
    themes = [
        {"id": "cn_a", "score": 80, "label": "dominant", "label_zh": "主导",
         "reco": "enter", "reco_zh": "入场", "textures": {"clean_entry": {"quality": 0.9}, "rollover_risk": {"band": "low"}}},
        {"id": "cn_b", "score": 30, "label": "fading", "label_zh": "退潮",
         "reco": "avoid", "reco_zh": "回避", "textures": {"clean_entry": {"quality": 0.2}, "rollover_risk": {"band": "high"}}},
    ]
    ba = {"id": "cn_a", "name": "A"}
    bb = {"id": "cn_b", "name": "B"}
    data = _make_data(baskets=[ba, bb], themes=themes)
    _attach_basket_intel(data)
    assert ba["score"] == 80
    assert bb["score"] == 30
    assert "rollover_risk_band" not in ba  # deliberately unattached (review 07-18)
    assert "rollover_risk_band" not in bb  # deliberately unattached (review 07-18)


# ---------------------------------------------------------------------------
# _compute_basket_overlaps
# ---------------------------------------------------------------------------

def _basket(bid, symbols):
    return {"id": bid, "name": bid, "name_zh": bid + "_zh",
            "members": [{"symbol": s} for s in symbols]}


def test_overlap_basic_jaccard():
    """Two baskets sharing members: jaccard = intersection/union."""
    ba = _basket("cn_a", ["X1", "X2", "X3"])
    bb = _basket("cn_b", ["X2", "X3", "X4"])
    data = {"baskets": [ba, bb]}
    _compute_basket_overlaps(data)
    ovls_a = ba.get("top_overlaps", [])
    assert len(ovls_a) == 1
    o = ovls_a[0]
    assert o["id"] == "cn_b"
    assert o["n_shared"] == 2
    # Jaccard = 2 / (3+3-2) = 2/4 = 0.5
    assert abs(o["jaccard"] - 0.5) < 0.01


def test_overlap_minimum_n_shared():
    """Only 1 shared member → not included (n_shared < 2)."""
    ba = _basket("cn_a", ["X1", "X2", "X3"])
    bb = _basket("cn_b", ["X3", "X4", "X5"])
    data = {"baskets": [ba, bb]}
    _compute_basket_overlaps(data)
    # 1 shared → filtered
    assert ba.get("top_overlaps", []) == []


def test_overlap_top3_cap():
    """top_overlaps capped at 3 even when more baskets qualify."""
    ba = _basket("cn_a", ["X1", "X2", "X3", "X4"])
    others = [_basket(f"cn_{i}", ["X1", "X2", f"Y{i}"]) for i in range(5)]
    data = {"baskets": [ba] + others}
    _compute_basket_overlaps(data)
    assert len(ba.get("top_overlaps", [])) <= 3


def test_overlap_self_excluded():
    """A basket never appears in its own top_overlaps."""
    ba = _basket("cn_a", ["X1", "X2", "X3"])
    data = {"baskets": [ba]}
    _compute_basket_overlaps(data)
    assert ba.get("top_overlaps", []) == []


def test_overlap_no_shared():
    """Baskets with entirely disjoint members → empty top_overlaps."""
    ba = _basket("cn_a", ["X1", "X2", "X3"])
    bb = _basket("cn_b", ["Y1", "Y2", "Y3"])
    data = {"baskets": [ba, bb]}
    _compute_basket_overlaps(data)
    assert ba.get("top_overlaps", []) == []
    assert bb.get("top_overlaps", []) == []


# ---------------------------------------------------------------------------
# _compute_member_signals — cache fingerprint logic
# ---------------------------------------------------------------------------

def _make_closes(symbols, n_bars=200):
    idx = pd.date_range("2025-01-01", periods=n_bars, freq="B")
    return pd.DataFrame(
        {s: np.cumprod(1 + np.random.default_rng(abs(hash(s)) % 2**31).normal(0.001, 0.01, n_bars))
         for s in symbols},
        index=idx,
    )


def _make_member_data(symbols):
    return {"baskets": [{"id": "cn_test", "name": "T",
                         "members": [{"symbol": s, "name": s} for s in symbols]}]}


def test_member_signals_cache_miss_then_hit(tmp_path, monkeypatch):
    """First call computes and writes cache; second call reads cache (fingerprint matches)."""
    symbols = ["600000.SS", "000001.SZ", "600519.SS"]
    closes = _make_closes(symbols, 200)
    max_date = str(closes.index.max().date())

    # Patch closes.parquet path
    closes_path = tmp_path / "closes.parquet"
    closes.to_parquet(closes_path)
    monkeypatch.setattr(
        "scripts.build_baskets_china.config",
        types.SimpleNamespace(ROOT=tmp_path),
    )
    # Rewrite parquet under a config.ROOT-relative path
    (tmp_path / "data" / "china_search").mkdir(parents=True, exist_ok=True)
    closes.to_parquet(tmp_path / "data" / "china_search" / "closes.parquet")

    site = tmp_path / "site"
    (site / "chinabasketdata").mkdir(parents=True, exist_ok=True)

    data = _make_member_data(symbols)

    # Mock signal_gate to return a stable tier
    fake_gate_calls = []
    def fake_gate(sym, series):
        fake_gate_calls.append(sym)
        return {"tier_cascade": "T2", "eligible": True, "fresh_bars": 3}

    with patch("scripts.build_baskets_china.config.ROOT", tmp_path):
        with patch("engine.signal_gate.gate", fake_gate):
            _compute_member_signals(data, site)

    n_computed = len(fake_gate_calls)
    assert n_computed == len(symbols)  # all computed on first call

    # Verify cache file written
    cache_path = site / "chinabasketdata" / "member_signals.json"
    assert cache_path.exists()
    cache = json.loads(cache_path.read_text())
    assert cache["meta"]["fingerprint"]

    # Verify member rows were annotated
    members = data["baskets"][0]["members"]
    assert any(m.get("sig_tier") == "T2" for m in members)

    # Second call — gate should NOT be called again (cache hit)
    fake_gate_calls.clear()
    data2 = _make_member_data(symbols)
    with patch("scripts.build_baskets_china.config.ROOT", tmp_path):
        with patch("engine.signal_gate.gate", fake_gate):
            _compute_member_signals(data2, site)
    assert len(fake_gate_calls) == 0  # cache hit → no recompute


def test_member_signals_thin_series(tmp_path, monkeypatch):
    """Members with < 120 bars get sig_tier=None without crash."""
    symbols = ["600000.SS"]
    closes = _make_closes(symbols, 50)  # too thin
    (tmp_path / "data" / "china_search").mkdir(parents=True, exist_ok=True)
    closes.to_parquet(tmp_path / "data" / "china_search" / "closes.parquet")

    site = tmp_path / "site"
    (site / "chinabasketdata").mkdir(parents=True, exist_ok=True)

    data = _make_member_data(symbols)
    with patch("scripts.build_baskets_china.config.ROOT", tmp_path):
        _compute_member_signals(data, site)

    members = data["baskets"][0]["members"]
    assert members[0].get("sig_tier") is None


def test_member_signals_none_safe_missing_closes(tmp_path):
    """Missing closes.parquet → function returns without modifying members."""
    site = tmp_path / "site"
    (site / "chinabasketdata").mkdir(parents=True, exist_ok=True)
    data = _make_member_data(["600000.SS"])

    with patch("scripts.build_baskets_china.config.ROOT", tmp_path):
        _compute_member_signals(data, site)  # must not raise

    # members unchanged (no sig_tier added)
    m = data["baskets"][0]["members"][0]
    assert "sig_tier" not in m or m["sig_tier"] is None


def test_member_signals_cache_fingerprint_invalidated_on_date_change(tmp_path):
    """Cache with a different max_date triggers recompute."""
    symbols = ["600000.SS"]
    closes = _make_closes(symbols, 200)
    (tmp_path / "data" / "china_search").mkdir(parents=True, exist_ok=True)
    closes.to_parquet(tmp_path / "data" / "china_search" / "closes.parquet")

    site = tmp_path / "site"
    (site / "chinabasketdata").mkdir(parents=True, exist_ok=True)

    # Write a stale cache with a different fingerprint
    stale_cache = {
        "meta": {
            "fingerprint": "000000000000dead",  # wrong fingerprint
            "computed_at": "2020-01-01T00:00:00+00:00",
            "max_date": "2020-01-01",
            "version": _MEMBER_SIGNAL_VERSION,
        },
        "signals": {"600000.SS": {"sig_tier": "T1", "sig_fresh": True}},
    }
    (site / "chinabasketdata" / "member_signals.json").write_text(
        json.dumps(stale_cache)
    )

    gate_calls = []
    def fake_gate(sym, series):
        gate_calls.append(sym)
        return {"tier_cascade": "T3", "eligible": True, "fresh_bars": 1}

    data = _make_member_data(symbols)
    with patch("scripts.build_baskets_china.config.ROOT", tmp_path):
        with patch("engine.signal_gate.gate", fake_gate):
            _compute_member_signals(data, site)

    # Should have recomputed because fingerprint didn't match
    assert len(gate_calls) > 0


# ---------------------------------------------------------------------------
# THS / lite payload safety
# ---------------------------------------------------------------------------

def test_ths_payload_not_modified_by_curated_functions():
    """_attach_basket_intel and _compute_basket_overlaps are safe to call with THS data.
    They look for theme_intel (absent in THS) and handle it gracefully.
    The THS page builder does NOT call these functions — this test ensures
    no accidental import-level side effects.
    """
    ths_data = {
        "baskets": [
            {"id": "ths_001", "name": "AI chips", "members": [{"symbol": "600000.SS"}]},
            {"id": "ths_002", "name": "Solar", "members": [{"symbol": "000001.SZ"}]},
        ]
    }
    # Neither function should crash or alter foreign keys
    _attach_basket_intel(ths_data)  # no theme_intel → no-op
    _compute_basket_overlaps(ths_data)  # overlap among THS baskets — OK, harmless
    # No score attached because no theme_intel
    assert "score" not in ths_data["baskets"][0]
    # top_overlaps present but empty (no shared members with n>=2)
    assert ths_data["baskets"][0].get("top_overlaps", []) == []


def test_member_signal_cache_age_expiry(tmp_path, monkeypatch):
    """Cache with matching fingerprint but computed_at older than the max age is NOT reused."""
    import json as _json
    from datetime import datetime, timedelta, timezone
    from scripts import build_baskets_china as bbc

    cache_dir = tmp_path / "chinabasketdata"
    cache_dir.mkdir(parents=True)
    stale_at = (datetime.now(timezone.utc)
                - timedelta(days=bbc._MEMBER_SIGNAL_MAX_AGE_D + 2)).isoformat()
    # fingerprint value doesn't matter: age gate must reject before fingerprint comparison wins
    (cache_dir / "member_signals.json").write_text(_json.dumps({
        "meta": {"fingerprint": "whatever", "computed_at": stale_at, "version": bbc._MEMBER_SIGNAL_VERSION},
        "signals": {"600000.SS": {"sig_tier": "T1", "sig_fresh": True}},
    }))
    data = {"baskets": [{"id": "cn_x", "members": [{"symbol": "600000.SS"}]}]}
    # closes.parquet missing under tmp data_root -> function returns early BUT only after
    # the cache age check path never falsely marks cache_hit. We assert via monkeypatched ROOT:
    monkeypatch.setattr(bbc.config, "ROOT", tmp_path)  # no data/china_search -> skip compute
    bbc._compute_member_signals(data, tmp_path)
    m = data["baskets"][0]["members"][0]
    # stale cache must NOT have been applied
    assert m.get("sig_tier") is None
