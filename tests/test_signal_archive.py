"""Tests for the append-only signal-layer archive (engine/signal_archive.py)."""
from __future__ import annotations

import json

import pandas as pd

from engine import signal_archive as sa


def test_flatten_scalars_walks_dicts_and_skips_lists():
    snap = {
        "quad": "Q2",
        "growth_score": 0.41,
        "recession": False,
        "note": None,
        "macro_risk": {"score": 0.7, "band": "elevated"},   # nested scalars -> flattened
        "sector_rs": [{"ticker": "XLK", "rs": 1.2}],          # list -> skipped
        "conditions": {"credit": {"oas_z": -0.5}},             # deeper nesting -> flattened
    }
    flat = sa.flatten_scalars(snap)
    assert flat["quad"] == "Q2"
    assert flat["growth_score"] == 0.41
    assert flat["recession"] is False
    assert flat["note"] is None
    assert flat["macro_risk_score"] == 0.7
    assert flat["macro_risk_band"] == "elevated"
    assert flat["conditions_credit_oas_z"] == -0.5
    assert not any(k.startswith("sector_rs") for k in flat)  # lists never flattened


def test_flatten_scalars_depth_guard():
    # build a chain deeper than the cap; nothing past the cap should appear
    d: dict = {"v": 1}
    for _ in range(20):
        d = {"x": d}
    flat = sa.flatten_scalars(d, _max_depth=8)
    assert len(flat) <= 1  # the leaf is buried below the cap -> dropped, no crash


def test_normalize_asof_handles_iso_and_human_and_junk():
    assert sa.normalize_asof("2026-06-16") == "2026-06-16"
    assert sa.normalize_asof("Jun 17, 2026") == "2026-06-17"   # human format dashboards emit
    assert sa.normalize_asof(None) == ""
    assert sa.normalize_asof("not-a-date") == "not-a-date"     # falls back to raw string


def test_find_asof_prefers_key_then_falls_through():
    assert sa.find_asof({"date": "2026-06-16"}, prefer="date") == "2026-06-16"
    assert sa.find_asof({"as_of": "2026-06-16"}, prefer="as_of") == "2026-06-16"
    assert sa.find_asof({"as_of": "2026-06-16"}) == "2026-06-16"   # auto-discovered
    assert sa.find_asof({"verdict": "calm"}) is None                # no date anywhere


def test_archive_snapshot_is_lossless_and_keep_first(tmp_path):
    snap1 = {"date": "2026-06-16", "quad": "Q2", "score": 0.4,
             "sector_rs": [{"t": "XLK"}], "nested": {"v": 1}}

    # first write: creates the parquet with flat scalar cols + a lossless blob
    assert sa.archive_snapshot("us", snap1, "2026-06-16", archive_dir=tmp_path) is True
    parquet = tmp_path / "us.parquet"
    assert parquet.exists()
    df = pd.read_parquet(parquet)
    assert list(df["asof"]) == ["2026-06-16"]
    assert df.loc[0, "quad"] == "Q2" and df.loc[0, "nested_v"] == 1
    assert "sector_rs" not in df.columns                       # list not in flat cols
    assert json.loads(df.loc[0, "snapshot_json"]) == snap1     # lossless: list survives

    # same as-of again (e.g. a same-day re-run) -> keep-first no-op, value unchanged
    assert sa.archive_snapshot("us", {"date": "2026-06-16", "quad": "Q9"}, "2026-06-16",
                               archive_dir=tmp_path) is False
    assert pd.read_parquet(parquet)["quad"].tolist() == ["Q2"]   # original value kept

    # a new as-of appends a second row; schema drift (a new column) is tolerated
    assert sa.archive_snapshot("us", {"date": "2026-06-17", "quad": "Q3", "new_col": 5},
                               "2026-06-17", archive_dir=tmp_path) is True
    df2 = pd.read_parquet(parquet)
    assert df2["asof"].tolist() == ["2026-06-16", "2026-06-17"]
    assert df2.set_index("asof").loc["2026-06-17", "new_col"] == 5

    # load_archive recovers the full snapshot dict from snapshot_json
    recovered = sa.load_archive("us", archive_dir=tmp_path)
    assert recovered.set_index("asof").loc["2026-06-16", "snapshot"] == snap1


def test_archive_snapshot_no_usable_asof_is_noop(tmp_path):
    assert sa.archive_snapshot("x", {"quad": "Q2"}, "", archive_dir=tmp_path) is False
    assert not (tmp_path / "x.parquet").exists()
    assert sa.load_archive("x", archive_dir=tmp_path) is None
