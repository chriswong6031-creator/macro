"""Membership ↔ close-cache reconciler — prune/guard/skip contract.

tmp_path fixtures in the style of tests/test_data_quality_audit.py: a synthetic data root
with a curated membership.json + a wide close-cache parquet, driven through
scripts.reconcile_membership.run(data_dir=..., out_dir=..., asof=..., cfg=...).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import reconcile_membership as rm

CFG = {"membership_min_present": 3, "membership_max_prune_pct": 20.0,
       "membership_max_prune_abs": 3}
ASOF = date(2026, 7, 1)


def _write_membership(data: Path, suite: str, members_by_basket: dict[str, list[str]],
                      name_key: str = "name") -> Path:
    baskets = {}
    for bid, tickers in members_by_basket.items():
        baskets[bid] = {
            "name": bid,
            "members": [{"ticker": t, "added": "2021-06-15", "removed": None,
                         name_key: f"公司 {t}", "rationale": t} for t in tickers],
            "changelog": [{"date": "2021-06-15", "action": "create", "note": "Seeded."}],
        }
    p = data / suite / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": "2026-06-19", "baskets": baskets},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _write_cache(data: Path, cache_rel: str, cols: list[str]) -> None:
    p = data / cache_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2024-01-02", periods=10, freq="B")
    pd.DataFrame(100.0, index=idx, columns=cols).to_parquet(p)


def _suite(doc: dict, suite: str) -> dict:
    return next(s for s in doc["suites"] if s["suite"] == suite)


def test_prunes_off_cache_member_with_dated_changelog(tmp_path):
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "T3", "GONE.MI"]})
    _write_cache(data, "intl_search/closes.parquet", ["T1", "T2", "T3"])

    doc = rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q")

    assert doc["n_pruned"] == 1
    assert _suite(doc, "baskets_intl")["pruned"] == [{"basket": "b1", "ticker": "GONE.MI"}]
    out = json.loads(mem_p.read_text(encoding="utf-8"))
    b = out["baskets"]["b1"]
    assert [m["ticker"] for m in b["members"]] == ["T1", "T2", "T3"]
    entry = b["changelog"][-1]
    assert entry["date"] == "2026-07-01" and entry["action"] == "remove"
    assert entry["note"].startswith("GONE.MI: removed — ")
    assert "intl_search universe/close cache" in entry["note"]
    assert "3 members remain" in entry["note"]
    # summary doc written for the run-over-run trend
    q = json.loads((tmp_path / "q" / "membership_reconcile.json").read_text())
    assert q["asof"] == "2026-07-01" and q["n_pruned"] == 1


def test_idempotent_and_serialization_preserved(tmp_path):
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_china", {"b1": ["A", "B", "C", "GONE"]},
                              name_key="name_zh")
    _write_cache(data, "china_search/closes.parquet", ["A", "B", "C"])

    rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q")
    first = mem_p.read_text(encoding="utf-8")
    # non-ASCII stays literal (ensure_ascii=False, the seeders' serialization), no trailing \n
    assert "公司 A" in first and "\\u" not in first and not first.endswith("\n")
    # second run: nothing off-cache -> byte-identical file, zero prunes
    doc = rm.run(cfg=CFG, asof=date(2026, 7, 2), data_dir=data, out_dir=tmp_path / "q")
    assert doc["n_pruned"] == 0
    assert mem_p.read_text(encoding="utf-8") == first


def test_refuses_prune_below_min_present_floor(tmp_path):
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "GONE1", "GONE2"]})
    _write_cache(data, "intl_search/closes.parquet", ["T1", "T2"])
    before = mem_p.read_text(encoding="utf-8")

    with pytest.raises(rm.PruneGuardError, match="cache-present"):
        rm.run(cfg={**CFG, "membership_max_prune_pct": 90.0},
               asof=ASOF, data_dir=data, out_dir=tmp_path / "q")
    assert mem_p.read_text(encoding="utf-8") == before   # refused suite left untouched


def test_refuses_mass_prune(tmp_path):
    data = tmp_path / "data"
    keep = [f"T{i}" for i in range(8)]
    mem_p = _write_membership(data, "baskets_intl", {"b1": keep + ["G1", "G2", "G3", "G4"]})
    _write_cache(data, "intl_search/closes.parquet", keep)   # 4/12 = 33% > 20% AND > 3 names
    before = mem_p.read_text(encoding="utf-8")

    with pytest.raises(rm.PruneGuardError, match="cache rebuild looks broken"):
        rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q")
    assert mem_p.read_text(encoding="utf-8") == before


def test_small_absolute_drift_never_trips_mass_guard(tmp_path):
    # 1 off-cache of 4 members = 25% > 20%, but only one name — genuine churn, must heal
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "T3", "GONE"]})
    _write_cache(data, "intl_search/closes.parquet", ["T1", "T2", "T3"])

    doc = rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q")

    assert doc["n_pruned"] == 1
    out = json.loads(mem_p.read_text(encoding="utf-8"))
    assert [m["ticker"] for m in out["baskets"]["b1"]["members"]] == ["T1", "T2", "T3"]


def test_absent_cache_or_membership_skips_not_crashes(tmp_path):
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "T3", "GONE"]})
    before = mem_p.read_text(encoding="utf-8")           # no cache parquet written at all

    doc = rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q")

    assert doc["n_pruned"] == 0
    s = _suite(doc, "baskets_intl")
    assert s["skipped"] and "absent" in s["note"]
    assert _suite(doc, "baskets_hk")["skipped"]          # membership absent -> also a skip
    assert mem_p.read_text(encoding="utf-8") == before   # never prune against a missing cache


def test_healthy_suite_heals_even_when_another_refuses(tmp_path):
    data = tmp_path / "data"
    intl_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "GONE1", "GONE2"]})
    _write_cache(data, "intl_search/closes.parquet", ["T1", "T2"])          # floor violation
    cn_p = _write_membership(data, "baskets_china", {"b1": ["A", "B", "C", "GONE"]})
    _write_cache(data, "china_search/closes.parquet", ["A", "B", "C"])      # healthy prune
    intl_before = intl_p.read_text(encoding="utf-8")

    with pytest.raises(rm.PruneGuardError):
        rm.run(cfg={**CFG, "membership_max_prune_pct": 90.0},
               asof=ASOF, data_dir=data, out_dir=tmp_path / "q")

    assert intl_p.read_text(encoding="utf-8") == intl_before                # refused: untouched
    cn = json.loads(cn_p.read_text(encoding="utf-8"))["baskets"]["b1"]
    assert [m["ticker"] for m in cn["members"]] == ["A", "B", "C"]          # healed anyway
    # the summary doc was written BEFORE the raise, so the evidence survives the abort
    q = json.loads((tmp_path / "q" / "membership_reconcile.json").read_text())
    assert q["n_pruned"] == 1 and q["n_refused"] == 1


def test_dry_run_reports_without_writing(tmp_path):
    data = tmp_path / "data"
    mem_p = _write_membership(data, "baskets_intl", {"b1": ["T1", "T2", "T3", "GONE"]})
    _write_cache(data, "intl_search/closes.parquet", ["T1", "T2", "T3"])
    before = mem_p.read_text(encoding="utf-8")

    doc = rm.run(cfg=CFG, asof=ASOF, data_dir=data, out_dir=tmp_path / "q", dry_run=True)

    assert doc["n_pruned"] == 1                          # reported...
    assert mem_p.read_text(encoding="utf-8") == before   # ...but nothing written
    assert not (tmp_path / "q" / "membership_reconcile.json").exists()


def test_guard_error_aborts_like_the_quality_gate():
    # collect.py re-raises PruneGuardError specifically; it must be the gate's abort type
    assert issubclass(rm.PruneGuardError, RuntimeError)
