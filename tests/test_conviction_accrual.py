"""Tests for the B2 member-conviction accrual (engine/conviction_accrual.py).

Guards the write-only PIT ledger LABEL_FALTERING_PHASE0 §2 B2 depends on: the
call sites are best-effort try/except, so a silent regression here would only
surface as a hole in the accrued history months later.
"""
from __future__ import annotations

import pandas as pd

from engine import conviction_accrual as ca
from engine import signal_archive as sa

_MEMBERSHIP = {
    "benchmark": "SPY",
    "baskets": {
        "themeA": {"id": "themeA", "members": [
            {"ticker": "AAA"}, {"ticker": "BBB"}, {"ticker": "CCC"}, {"ticker": "DDD"}]},
        "themeB": {"id": "themeB", "members": [
            {"ticker": "CCC"}, {"ticker": "EEE"}, {"ticker": "ZZZ"}]},  # CCC overlaps; ZZZ unscored
    },
}

_PROFILES = {
    "AAA": {"potential": {"score": 10}},
    "BBB": {"potential": {"score": 20}},
    "CCC": {"potential": {"score": 30}},
    "DDD": {"potential": {"score": 40}},
    "EEE": {"potential": {"score": 90}},
    "OFF_BASKET": {"potential": {"score": 99}},   # scored but in no basket -> excluded
    "NO_POT": {"score": 55},                       # no potential block -> skipped
    "BAD": {"potential": {"score": "high"}},       # non-numeric -> skipped
    "NONE": None,                                  # tolerated
}


def _patch_plane(monkeypatch, theme_meta=({"themeA": {"score": 72, "label": "dominant"}}, "2026-07-02")):
    monkeypatch.setattr(
        "engine.narrative_rotation._region_cfg",
        lambda region: {"id": region, "membership": lambda: _MEMBERSHIP} if region == "us" else None)
    monkeypatch.setattr(ca, "_theme_meta", lambda region: theme_meta)


def test_archives_per_basket_and_region_stats(tmp_path, monkeypatch):
    _patch_plane(monkeypatch)
    assert ca.archive_member_conviction("us", _PROFILES, asof="2026-07-03",
                                        archive_dir=tmp_path) is True
    df = sa.load_archive("conviction_us", archive_dir=tmp_path)
    snap = df.iloc[0]["snapshot"]
    a = snap["baskets"]["themeA"]
    assert a["median"] == 25.0 and a["iqr"] == 15.0          # {10,20,30,40}
    assert a["n"] == 4 and a["n_total"] == 4
    assert a["theme_score"] == 72 and a["label"] == "dominant"  # theme join
    b = snap["baskets"]["themeB"]
    assert b["median"] == 60.0 and b["n"] == 2 and b["n_total"] == 3   # ZZZ unscored
    assert b["theme_score"] is None and b["label"] is None   # no theme snapshot for it
    # region roll-up dedups the cross-basket member (CCC counted once) and
    # excludes scored names that sit in no basket
    assert snap["n"] == 5 and snap["n_total"] == 6
    assert snap["median"] == 30.0                             # {10,20,30,40,90}
    assert snap["theme_asof"] == "2026-07-02"
    # flat columns are queryable without parsing the blob
    assert df.iloc[0]["baskets_themeA_median"] == 25.0
    assert df.iloc[0]["baskets_themeB_label"] is None


def test_keep_first_and_degenerate_inputs(tmp_path, monkeypatch):
    _patch_plane(monkeypatch)
    assert ca.archive_member_conviction("us", _PROFILES, asof="2026-07-03",
                                        archive_dir=tmp_path) is True
    # same-day re-run -> keep-first no-op
    assert ca.archive_member_conviction("us", _PROFILES, asof="2026-07-03",
                                        archive_dir=tmp_path) is False
    # an empty/degenerate build must NEVER imprint a zero row under keep-first
    assert ca.archive_member_conviction("us", {}, asof="2026-07-04",
                                        archive_dir=tmp_path) is False
    assert ca.archive_member_conviction("us", {"NONE": None, "BAD": {"potential": {}}},
                                        asof="2026-07-04", archive_dir=tmp_path) is False
    # unknown region -> no-op, no file
    assert ca.archive_member_conviction("mars", _PROFILES, asof="2026-07-04",
                                        archive_dir=tmp_path) is False
    df = sa.load_archive("conviction_us", archive_dir=tmp_path)
    assert df["asof"].tolist() == ["2026-07-03"]


def test_theme_meta_missing_still_archives_stats(tmp_path, monkeypatch):
    _patch_plane(monkeypatch, theme_meta=({}, None))
    assert ca.archive_member_conviction("us", _PROFILES, asof="2026-07-03",
                                        archive_dir=tmp_path) is True
    snap = sa.load_archive("conviction_us", archive_dir=tmp_path).iloc[0]["snapshot"]
    assert snap["baskets"]["themeA"]["median"] == 25.0        # primary series intact
    assert snap["baskets"]["themeA"]["theme_score"] is None
    assert snap["theme_asof"] is None


def test_stats_median_iqr():
    assert ca._stats([]) == {"median": None, "iqr": None}
    assert ca._stats([10.0]) == {"median": 10.0, "iqr": 0.0}
    s = ca._stats([10.0, 20.0, 30.0, 40.0])
    assert s["median"] == 25.0 and s["iqr"] == 15.0
