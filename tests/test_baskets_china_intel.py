"""Tests for the baskets_china overhaul: intel attach, member signals, overlap, THS safety.

Covers:
 - _attach_basket_intel: None-safe (no theme_intel, missing baskets, partial intel)
 - _compute_basket_overlaps: Jaccard math, top-3 cap, n_shared>=2 gate, self-exclude
 - _compute_member_signals: cache fingerprint logic (hit/miss), None-safety on thin series
 - THS/lite payload untouched (curated-only functions are not called on THS data)
 - chinabasketdata/baskets.json write ordering + completeness + organ-crash fail-safety
   (China Sector Intelligence consolidation gate 5 — the merged page FETCHES this artifact)
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


# ---------------------------------------------------------------------------
# chinabasketdata/baskets.json — write ordering, completeness, fail-safety
#
# The merged China Sector Intelligence page FETCHES this artifact instead of
# reading a 774KB inline embed, so the JSON must carry every guarantee the inline
# payload used to get from the #2886 double render:
#   COMPLETENESS — the sector_pulse velocity/heat keys merged into theme_intel,
#                  the china_basket_turn organ's turn_state, and the member
#                  signal / cross-basket overlap merge.
#   FAIL-SAFETY  — an organ or merge crash still leaves a readable, current JSON;
#                  never MISSING and never stale-from-yesterday.
#
# Measured on main 2026-08-02, before the write moved: site/chinabasketdata/
# baskets.json carried 0 of the 6 pulse_* keys across 22 themes (the US sibling
# site/basketdata/baskets.json carried all 6 across 47, having already been
# fixed at scripts/build_baskets.py:152-188), and site/baskets_china.html
# shipped 0 `pulse_heat` while baskets_hk / baskets_canada / baskets_intl
# shipped 56-58 — because every write after the first round-trips through disk,
# so a pre-merge snapshot froze the whole chain.
# ---------------------------------------------------------------------------

_BBC_SRC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_baskets_china.py"

# Written by engine.sector_pulse.merge_pulse_into_theme_intel onto every theme row.
_PULSE_KEYS = ("pulse_heat", "pulse_heat_grade", "pulse_rank_delta_1d",
               "pulse_rank_delta_5d", "pulse_rank_delta_20d", "pulse_score_delta_5d")

# Mirrors templates/baskets_china.html.j2:474-475 so the inlined payload is parseable.
_STUB_TEMPLATE = ("<html><head></head><body><script>\n"
                  "const BASKETS = {{ baskets_json|safe }};\n"
                  "const CHART   = {{ chart_json|safe }};\n"
                  "</script></body></html>\n")


class _InjectedFault(RuntimeError):
    """Fault injected by a test to stand in for anything blowing up mid-build."""


def _synth_baskets_payload():
    """A minimal but structurally faithful engine.baskets_china payload."""
    n = 60
    dates = [f"2026-05-{1 + i % 28:02d}" for i in range(n)]
    def _basket(bid, name, name_zh, symbols):
        return {"id": bid, "name": name, "name_zh": name_zh, "category": "Tech",
                "category_zh": "科技", "n_members": len(symbols),
                "members": [{"symbol": s, "name": s} for s in symbols],
                "perf": {"20d": {"ret": 0.05, "rel": 0.01}}}
    return {
        "as_of": "2026-08-01",
        "benchmark_label": "CSI 300", "benchmark_label_zh": "沪深300",
        "categories": ["Tech"], "categories_zh": ["科技"],
        "baskets": [
            _basket("cn_a", "Alpha", "甲", ["600000.SS", "000001.SZ", "600519.SS"]),
            _basket("cn_b", "Beta", "乙", ["600000.SS", "000001.SZ", "300750.SZ"]),
        ],
        "chart": {"dates": dates, "bench": [100.0] * n,
                  "baskets": {"cn_a": [100.0] * n, "cn_b": [100.0] * n}},
        "story": {}, "construction": {}, "history_note": "", "note": "",
    }


def _drive_full_build(tmp_path, monkeypatch, *, turn_raises=False, merge_raises=False):
    """Run the REAL scripts.build_baskets_china.main() against a throwaway ROOT.

    Only the engine boundaries are stubbed (the China inputs — membership.json, the
    china_search close cache, the CSI 300 store group — are not present on a dev box or
    in the CI packs). Everything the ordering contract is about stays the module's own
    code: the sector_pulse merge, the fail-soft write, the organ annotation, the
    signal/overlap merge, the authoritative write and the re-render all run for real,
    so a re-order shows up here. Returns the tmp site dir.
    """
    from engine import baskets_china as _e_bc
    from engine import basket_freeze as _e_bf
    from engine import china_basket_turn as _e_cbt
    from engine import narrative_emergence as _e_ne
    from engine import risk_radar_intl as _e_rri
    from engine import theme_alerts as _e_ta
    from engine import theme_scoring as _e_ts
    from scripts import build_baskets_china as bbc
    from scripts import build_theme_detail as _s_btd

    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)
    (tmp_path / "templates" / "baskets_china.html.j2").write_text(_STUB_TEMPLATE)
    site = tmp_path / "site"
    site.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bbc.config, "ROOT", tmp_path)
    monkeypatch.setattr(_e_bc, "compute_china_baskets", _synth_baskets_payload)
    monkeypatch.setattr(_e_ts, "compute_theme_intel", lambda region: {
        "as_of": "2026-08-01",
        "themes": [
            {"id": "cn_a", "name": "Alpha", "score": 70, "rank": 1, "label": "dominant",
             "label_zh": "主导", "reco": "accumulate", "reco_zh": "加仓", "textures": {}},
            {"id": "cn_b", "name": "Beta", "score": 30, "rank": 2, "label": "fading",
             "label_zh": "退潮", "reco": "avoid", "reco_zh": "回避", "textures": {}},
        ]})
    monkeypatch.setattr(_e_ta, "rebuild", lambda *a, **k: None)
    monkeypatch.setattr(_e_ne, "compute_emergence", lambda region: None)
    monkeypatch.setattr(_e_rri, "cn_sleeve_chip", lambda: {"factor": 1.0})
    monkeypatch.setattr(_e_bf, "freeze_domain", lambda *a, **k: "test-noop")
    monkeypatch.setattr(_s_btd, "build_detail_pages", lambda *a, **k: None)

    def _turn(**kwargs):
        if turn_raises:
            raise _InjectedFault("china_basket_turn organ down")
        return {"baskets": {"cn_a": {"state": "TURNING", "dd_252": -0.12, "hist_d": 30,
                                     "slope_20d": 0.4, "evidence": ["ev"]}}}
    monkeypatch.setattr(_e_cbt, "run", _turn)

    if merge_raises:
        def _boom(*a, **k):
            raise _InjectedFault("signal/overlap merge down")
        monkeypatch.setattr(bbc, "_compute_member_signals", _boom)

    try:
        bbc.main()
    except _InjectedFault:
        # An unguarded call site propagates. The contract under test is the FILE STATE
        # the fail-soft write already put on disk, not which frame the fault escapes.
        if not merge_raises:
            raise
    return site


def _read_baskets_json(site):
    return json.loads((site / "chinabasketdata" / "baskets.json").read_text())


def _inlined_baskets(site):
    """Parse the BASKETS payload back out of the rendered page."""
    html = (site / "baskets_china.html").read_text()
    body = html.split("const BASKETS = ", 1)[1].rsplit(";\nconst CHART", 1)[0]
    return json.loads(body)


def test_baskets_json_carries_pulse_keys_after_full_build(tmp_path, monkeypatch):
    """theme_intel in the fetched JSON carries the sector_pulse velocity/heat keys.

    These are merged into theme_intel IN PLACE after the pulse is written; a JSON
    snapshot taken before that merge freezes them out forever, and because every
    later write round-trips the artifact through disk, nothing downstream heals it.
    baskets_desk.js reads pulse_heat / pulse_rank_delta_5d / pulse_rank_delta_20d.
    """
    site = _drive_full_build(tmp_path, monkeypatch)
    themes = (_read_baskets_json(site).get("theme_intel") or {}).get("themes") or []
    assert themes, "theme_intel.themes missing from baskets.json"
    for th in themes:
        missing = [k for k in _PULSE_KEYS if k not in th]
        assert not missing, f"theme {th.get('id')} lost pulse keys {missing} on the way to disk"


def test_baskets_json_carries_turn_state_after_full_build(tmp_path, monkeypatch):
    """The china_basket_turn organ's state reaches the fetched JSON (#2829 class).

    A pre-organ-only JSON is the us_stocks one-build-lag bug: the lifecycle chips and
    Entry Radar read turn_state off the payload and would silently never fire.
    """
    site = _drive_full_build(tmp_path, monkeypatch)
    baskets = _read_baskets_json(site)["baskets"]
    turned = [b for b in baskets if b.get("turn_state")]
    assert turned, "no basket carries turn_state — baskets.json is a pre-organ snapshot"
    b = turned[0]
    assert b["turn_state"] == "TURNING"
    # the organ's supporting fields ride along, not just the headline state
    assert b["turn_hist_d"] == 30 and b["turn_evidence"] == ["ev"]


def test_baskets_json_carries_signal_overlap_merge_and_chart(tmp_path, monkeypatch):
    """The authoritative write lands after the signal/overlap merge, and keeps `chart`.

    The merged page fetches ONE artifact for both BASKETS and CHART, so the write must
    stay ahead of `chart = data.pop("chart")`.
    """
    bj = _read_baskets_json(_drive_full_build(tmp_path, monkeypatch))
    assert all("top_overlaps" in b for b in bj["baskets"]), "cross-basket overlap merge missing"
    # cn_a and cn_b share 2 of 3 members in the synthetic payload
    assert bj["baskets"][0]["top_overlaps"][0]["n_shared"] == 2
    assert bj.get("chart", {}).get("dates"), "chart matrix absent — page would fetch a second file"
    assert bj.get("sleeve_chip"), "header chips computed before the write did not reach it"


def test_fetched_json_and_inlined_page_payload_agree(tmp_path, monkeypatch):
    """The JSON the page fetches and the payload the page inlines are the same state.

    While both delivery paths are live (the inline embed dies with the template merge),
    a divergence means one of the two is a stale snapshot.
    """
    site = _drive_full_build(tmp_path, monkeypatch)
    disk = {b["id"]: b for b in _read_baskets_json(site)["baskets"]}
    inline = {b["id"]: b for b in _inlined_baskets(site)["baskets"]}
    assert set(disk) == set(inline)
    for bid in disk:
        assert disk[bid].get("turn_state") == inline[bid].get("turn_state")
        assert disk[bid].get("top_overlaps") == inline[bid].get("top_overlaps")
    inline_themes = (_inlined_baskets(site).get("theme_intel") or {}).get("themes") or []
    assert all(k in inline_themes[0] for k in _PULSE_KEYS)


def test_baskets_json_survives_turn_organ_failure(tmp_path, monkeypatch):
    """An organ crash still ships a complete, current JSON — just without turn_state.

    This is the fail-safety half the pre-organ render used to give the page: the page
    must never be left with a MISSING or stale-from-yesterday artifact.
    """
    site = _drive_full_build(tmp_path, monkeypatch, turn_raises=True)
    bj = _read_baskets_json(site)
    assert len(bj["baskets"]) == 2 and bj.get("chart", {}).get("dates")
    themes = (bj.get("theme_intel") or {}).get("themes") or []
    assert all(k in themes[0] for k in _PULSE_KEYS), "fail-soft write must be post-pulse-merge"
    assert not any(b.get("turn_state") for b in bj["baskets"])   # organ never ran
    assert all("top_overlaps" in b for b in bj["baskets"])       # merge still reached disk


def test_baskets_json_survives_post_write_merge_failure(tmp_path, monkeypatch):
    """A crash in the signal/overlap merge still leaves the fail-soft payload on disk.

    Pins the reason the fail-soft write is unconditional and sits ahead of the organ:
    whatever dies after it, the fetching page finds today's baskets, today's chart and
    today's pulse keys rather than yesterday's committed file.
    """
    site = _drive_full_build(tmp_path, monkeypatch, merge_raises=True)
    bj = _read_baskets_json(site)
    assert len(bj["baskets"]) == 2 and bj.get("chart", {}).get("dates")
    themes = (bj.get("theme_intel") or {}).get("themes") or []
    assert all(k in themes[0] for k in _PULSE_KEYS)


# --- source-level ordering pins --------------------------------------------
# The functional tests above stub the organ, so they prove the payload flows through
# the ordering that exists. These pin the ORDERING ITSELF, so a refactor that quietly
# moves the authoritative write back ahead of the organ fails even if its own stubs
# happen to agree.

def _src_at(src, needle):
    i = src.find(needle)
    assert i != -1, f"ordering marker vanished from build_baskets_china.py: {needle!r}"
    return i


def test_failsoft_baskets_json_write_is_post_pulse_merge_and_pre_chart_pop():
    """The fail-soft write sits AFTER the sector_pulse merge and BEFORE the chart pop."""
    src = _BBC_SRC_PATH.read_text()
    failsoft = '(fdir / "baskets.json").write_text('
    assert src.count(failsoft) == 1, "more than one direct baskets.json payload write"
    i_merge = _src_at(src, '_sp.merge_pulse_into_theme_intel(data["theme_intel"], "china")')
    i_write = _src_at(src, failsoft)
    i_pop = _src_at(src, 'chart = data.pop("chart")')
    assert i_merge < i_write, "baskets.json written before the pulse merge — freezes a pre-merge theme_intel"
    assert i_write < i_pop, "baskets.json written after the chart pop — the fetched artifact loses CHART"
    # unconditional: a top-level statement of main(), not tucked inside a try/if
    line = src[src.rfind("\n", 0, i_write) + 1:src.find("\n", i_write)]
    assert line.startswith("    (") and not line.startswith("     "), \
        "fail-soft write is nested — it must run whatever else fails"


def test_authoritative_baskets_json_write_is_post_organ_and_post_merge():
    """The authoritative write follows the turn organ AND the signal/overlap merge,
    and precedes the re-render that inlines the same payload."""
    src = _BBC_SRC_PATH.read_text()
    auth = "_bj_path2.write_text("
    assert src.count(auth) == 1
    i_failsoft = _src_at(src, '(fdir / "baskets.json").write_text(')
    i_organ = _src_at(src, "_turn_art = _cn_turn_run(")
    i_signals = _src_at(src, "_compute_member_signals(data, site)")
    i_overlaps = _src_at(src, "_compute_basket_overlaps(data)")
    i_auth = _src_at(src, auth)
    i_rerender = _src_at(src, "_render_page(_bj2_render)")
    assert i_failsoft < i_organ, "fail-soft write must precede the organ to be fail-soft"
    assert i_organ < i_signals < i_auth, "authoritative write is not post-organ/post-signals"
    assert i_overlaps < i_auth, "authoritative write is not post-overlap-merge"
    assert i_auth < i_rerender, "page re-renders from a payload the JSON does not have"


def test_authoritative_write_refreshes_theme_intel_from_memory():
    """The authoritative payload takes theme_intel from memory, not the disk round-trip.

    Every write after the fail-soft one re-reads baskets.json from disk, so without this
    refresh the authoritative artifact can only ever be as complete as that first write.
    """
    src = _BBC_SRC_PATH.read_text()
    i_refresh = _src_at(src, '_bj2["theme_intel"] = data["theme_intel"]')
    i_guard = _src_at(src, 'if data.get("theme_intel"):\n            _bj2["theme_intel"]')
    i_auth = _src_at(src, "_bj_path2.write_text(")
    assert i_guard < i_refresh, "unguarded refresh can blank theme_intel on an engine failure"
    assert i_refresh < i_auth, "theme_intel refreshed after the write it was meant to feed"
