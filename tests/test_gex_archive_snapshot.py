"""Tests for the GEX -> signal_archive snapshot (scripts/build_gex_board)."""
from __future__ import annotations

import json

import pandas as pd

from engine import signal_archive as sa
from scripts import build_gex_board as bg


def _manifest() -> list[dict]:
    """One index, one ETF, one single name — the single name must be dropped (dealer
    sign is only robust for broad indices)."""
    return [
        {"key": "SPX", "spot": 7500.0, "regime": "long", "tier": "full",
         "net_gex_bn": 26.2, "gamma_flip": 7443.0, "dist_to_flip_pct": 0.77,
         "iv30": 13.7, "put_call_oi_ratio": 1.07, "call_wall": 7700.0,
         "put_wall": 7300.0, "max_pain": 7075.0, "daily_move_pct": 0.86},
        {"key": "SPY", "spot": 745.0, "regime": "long", "tier": "full",
         "net_gex_bn": 5.1, "gamma_flip": 743.0, "dist_to_flip_pct": 0.3,
         "iv30": 13.0, "put_call_oi_ratio": 1.2, "call_wall": 770.0,
         "put_wall": 730.0, "max_pain": 707.0, "daily_move_pct": 0.8},
        {"key": "TSLA", "spot": 250.0, "regime": "short", "tier": "full",
         "net_gex_bn": -0.4, "gamma_flip": 255.0, "dist_to_flip_pct": -2.0,
         "iv30": 55.0, "put_call_oi_ratio": 0.9, "call_wall": 300.0,
         "put_wall": 200.0, "max_pain": 240.0, "daily_move_pct": 3.5},
    ]


def test_snapshot_keeps_index_etf_excludes_single_names(tmp_path):
    bg._write_archive_snapshot(_manifest(), tmp_path)
    snap = json.loads((tmp_path / "gex" / "latest.json").read_text())
    assert set(snap["indices"]) == {"SPX", "SPY"}          # TSLA (single name) excluded
    assert snap["indices"]["SPX"]["net_gex_bn"] == 26.2
    assert snap["indices"]["SPX"]["regime"] == "long"
    assert snap["source"] == "cboe_delayed" and snap["asof"]
    assert isinstance(snap["market"], dict)                # no cboe parquets -> {} (no crash)


def test_market_context_reads_cboe(tmp_path):
    cboe = tmp_path / "cboe"
    cboe.mkdir()
    pd.DataFrame({"skew": [120.0, 146.72]},
                 index=pd.to_datetime(["2026-06-17", "2026-06-18"])).to_parquet(cboe / "skew.parquet")
    # 2026-06-19 is JUNETEENTH — the exchange is closed. _market_context session-filters
    # these cboe stores now (the #3721 weekend-row class: putcall.parquet held 13
    # non-session rows of 39, and both the published level AND the *_asof stamp come off
    # the last row), so a holiday-dated fixture row is correctly discarded. Use the next
    # real session, 2026-06-22, so "the latest row" is unambiguous.
    pd.DataFrame({"index_pc_ratio": [1.1, 1.333], "equity_pc_ratio": [1.0, 1.339]},
                 index=pd.to_datetime(["2026-06-18", "2026-06-22"])).to_parquet(cboe / "putcall.parquet")
    ctx = bg._market_context(tmp_path)
    assert ctx["skew"] == 146.72 and ctx["skew_asof"] == "2026-06-18"
    assert ctx["index_pc_ratio"] == 1.333 and ctx["put_call_asof"] == "2026-06-22"


def test_snapshot_flattens_and_dedups_in_archive(tmp_path):
    bg._write_archive_snapshot(_manifest(), tmp_path)
    snap = json.loads((tmp_path / "gex" / "latest.json").read_text())
    asof = sa.find_asof(snap, prefer="asof")
    arch = tmp_path / "arch"
    assert sa.archive_snapshot("options_gex", snap, asof, archive_dir=arch) is True
    assert sa.archive_snapshot("options_gex", snap, asof, archive_dir=arch) is False   # keep-first
    df = sa.load_archive("options_gex", archive_dir=arch)
    assert df.iloc[0]["indices_SPX_net_gex_bn"] == 26.2           # queryable flat column
    assert df.iloc[0]["snapshot"]["indices"]["SPY"]["regime"] == "long"  # lossless backstop


def test_empty_or_nonindex_manifest_writes_nothing(tmp_path):
    bg._write_archive_snapshot([{"key": "TSLA", "net_gex_bn": -0.4}], tmp_path)
    assert not (tmp_path / "gex" / "latest.json").exists()        # no index/ETF -> no snapshot
