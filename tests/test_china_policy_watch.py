"""China Central Bank & Government Policy Watch — contract tests (network-free).

Covers the PBoC collector's pure parsers, the deterministic stance classifier, the
policy-watch assembler shape + the compact bus contract, and the curated intel substrate.
"""
from __future__ import annotations

import json

import pandas as pd

from collectors import china_pboc as cp
from engine import china_pboc_stance as ps
from engine import china_policy_watch as pw
from lib import config


# ---- collector pure parsers ------------------------------------------------ #
def test_parse_month_variants():
    assert cp._parse_month("2026年05月份") == pd.Timestamp(2026, 5, 1)
    assert cp._parse_month("2026-05") == pd.Timestamp(2026, 5, 1)
    assert cp._parse_month("garbage") is None


def test_col_fuzzy_match():
    df = pd.DataFrame(columns=["国家外汇储备-数值", "黄金储备-数值", "月份"])
    assert cp._col(df, "外汇储备-数值") == "国家外汇储备-数值"
    assert cp._col(df, "不存在") is None


# ---- stance classifier (pure) ---------------------------------------------- #
def test_classify_easing_neutral_tightening():
    # two easing legs -> easing
    assert ps._classify(-0.10, -0.5, -0.20)[1] == "easing"
    # two tightening legs -> tightening
    assert ps._classify(0.10, 0.5, 0.20)[1] == "tightening"
    # mixed / flat -> neutral
    assert ps._classify(0.0, -0.5, 0.0)[1] == "neutral"
    assert ps._classify(None, None, None)[1] == "neutral"


def test_stance_snapshot_shape_and_none_safe():
    s = ps.snapshot()
    if s is not None:
        assert s["schema"] == ps.SCHEMA
        assert s["stance"] in ("easing", "neutral", "tightening")
        assert isinstance(s["corridor"], list)
        assert "fx" in s and "last_moves" in s


# ---- policy-watch assembler ------------------------------------------------ #
def test_policy_snapshot_structure():
    vm = pw.snapshot()
    if vm is None:
        return
    assert vm["schema"] == pw.SCHEMA
    for k in ("pboc", "nbs_prints", "policy_feed", "intel", "latest"):
        assert k in vm
    # compact contract keys the intel bus reads
    lc = vm["latest"]
    for k in ("stance", "lpr_1y", "lpr_5y", "rrr", "fx_reserves", "last_moves", "predictions"):
        assert k in lc


def test_compact_predictions_only_open():
    intel = {"predictions": [
        {"text_en": "A", "status": "open"}, {"text_en": "B", "status": "hit"}]}
    c = pw._compact({"corridor": [], "fx": {}}, intel)
    assert c["predictions"] == ["A"]


# ---- intel_dates staleness plumbing --------------------------------------- #
def test_snapshot_intel_dates_stale_flag(monkeypatch):
    """Audit fix B6b: snapshot() must wire policy_dates.annotate(intel) into intel_dates,
    and intel_dates.staleness.stale must be True when intel.as_of is >14d old."""
    from datetime import date, timedelta
    import engine.china_pboc_stance as ps

    stale_as_of = (date.today() - timedelta(days=20)).isoformat()
    stale_intel = {"as_of": stale_as_of, "thesis": {"en": "x", "zh": "x"},
                   "predictions": [], "sector_policy": []}

    monkeypatch.setattr(pw, "_intel", lambda: stale_intel)
    monkeypatch.setattr(pw, "_nbs_prints", lambda: [])
    monkeypatch.setattr(pw, "_policy_feed", lambda: [])
    # provide minimal pboc so snapshot doesn't return None
    monkeypatch.setattr(ps, "snapshot", lambda asof=None: {
        "schema": ps.SCHEMA, "stance": "neutral", "stance_en": "Neutral",
        "stance_zh": "中性", "rationale": {"en": "flat", "zh": "平稳"},
        "corridor": [], "fx": {}, "last_moves": [], "asof": stale_as_of,
    })

    vm = pw.snapshot()
    assert vm is not None, "snapshot must not return None with valid pboc stub"
    assert "intel_dates" in vm, "intel_dates key must be present in snapshot output"
    staleness = vm["intel_dates"]["staleness"]
    assert staleness["stale"] is True, "intel staleness must be True for as_of >14d ago"
    assert staleness["as_of"] == stale_as_of


def test_snapshot_intel_dates_none_safe(monkeypatch):
    """Audit fix B6b: snapshot() must not crash when intel.json has no as_of field."""
    import engine.china_pboc_stance as ps

    monkeypatch.setattr(pw, "_intel", lambda: {"thesis": {"en": "x", "zh": "x"}})
    monkeypatch.setattr(pw, "_nbs_prints", lambda: [])
    monkeypatch.setattr(pw, "_policy_feed", lambda: [])
    monkeypatch.setattr(ps, "snapshot", lambda asof=None: {
        "schema": ps.SCHEMA, "stance": "neutral", "stance_en": "Neutral",
        "stance_zh": "中性", "rationale": {"en": "flat", "zh": "平稳"},
        "corridor": [], "fx": {}, "last_moves": [], "asof": "2026-01-01",
    })

    vm = pw.snapshot()
    assert vm is not None
    # intel with no as_of → staleness.stale must be False (None age treated as not-stale)
    assert vm["intel_dates"]["staleness"]["stale"] is False


# ---- curated intel substrate ----------------------------------------------- #
def test_intel_json_loads_and_has_sections():
    p = config.ROOT / "data" / "china_policy" / "intel.json"
    d = json.loads(p.read_text())
    assert d["schema"] == "china_policy_intel.v1"
    assert d["thesis"]["en"] and d["thesis"]["zh"]
    assert len(d["sector_policy"]) >= 8
    assert all(s["stance"] in ("supportive", "restrictive", "neutral")
               for s in d["sector_policy"])
    assert len(d["npc_targets_2026"]) >= 3
    assert all(p.get("check_by") for p in d["predictions"])
