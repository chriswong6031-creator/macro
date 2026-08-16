"""CN-PR-1 — armed pack: universe screen, per-class band, frozen legs, isolation."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine.prophet_live import cn_clock
from engine.prophet_live import cn_pack as CP
from engine.prophet_live import r2io
from engine.prophet_live.interval import ADJUSTED

ROOT = Path(__file__).resolve().parent.parent
IDX = pd.bdate_range("2024-01-02", periods=80)
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _close(last: float = 10.0) -> pd.Series:
    vals = [float(last) * (1.0 + 0.001 * (i % 5 - 2)) for i in range(len(IDX))]
    vals[-1] = float(last)
    return pd.Series(vals, index=IDX)


def _gate(threshold: float = 10.0):
    def g(_ticker: str, close) -> dict:
        px = float(close.iloc[-1])
        buy = px >= threshold
        return {"eligible": True, "tier": "T2", "tier_cascade": "T2" if buy else None,
                "sub": "confirmed"}
    return g


def test_is_cn_stock_drops_etfs_indices_and_bj() -> None:
    assert CP.is_cn_stock("600519.SS", "Consumer")
    assert CP.is_cn_stock("300750.SZ", "Industrials")
    assert not CP.is_cn_stock("510300.SS", "Sector ETF")
    assert not CP.is_cn_stock("000300.SS", "Index")
    assert not CP.is_cn_stock("920000.BJ", "Consumer")
    assert not CP.is_cn_stock("AAPL", "Tech")


def test_filter_universe_keeps_only_mainland_stocks() -> None:
    rows = [
        ("600519.SS", _close(), None, "Kweichow", "Consumer"),
        ("510300.SS", _close(), None, "CSI300", "Sector ETF"),
        ("000001.SZ", _close(), None, "PAB", "Financials"),
        ("920001.BJ", _close(), None, "BJ", "Consumer"),
    ]
    kept = [r[0] for r in CP.filter_universe(rows)]
    assert kept == ["600519.SS", "000001.SZ"]


def test_band_pct_follows_the_board_class() -> None:
    assert CP.band_pct_for("600519.SS") == 10.0
    assert CP.band_pct_for("688981.SS") == 20.0
    assert CP.band_pct_for("300750.SZ") == 20.0
    assert CP.band_pct_for("301269.SZ") == 20.0


def test_centre_record_uses_the_class_band_not_the_us_15() -> None:
    rec = CP.centre_record("301269.SZ", _close(20.0), cfg=CP.pack_cfg(None),
                           gate_fn=_gate(99.0))
    assert rec["band_pct"] == 20.0
    lo, hi = rec["span"]
    # Up-only (not buyable at 20 vs threshold 99): span is [as_of, as_of * 1.20]
    assert abs(lo - 20.0) < 1e-9
    assert abs(hi - 24.0) < 1e-6


def test_assemble_stamps_cn_schema_and_frozen_legs() -> None:
    rec = CP.centre_record("600519.SS", _close(10.0), cfg=CP.pack_cfg(None),
                           gate_fn=_gate(5.0))
    entry = __import__("engine.prophet_live.armed_pack", fromlist=["name_entry"]).name_entry(
        rec, None)
    payload = CP.assemble(
        {"600519.SS": entry}, as_of="2026-08-14", cfg=CP.pack_cfg(None),
        universe_n=1, wanted_n=1, gate_calls=1, build_seconds=0.1, skipped={},
        frozen={"600519.SS": {"prophet_score": 81.2, "prophet_rank": 3,
                              "lane": "featured"}},
        now=NOW,
    )
    assert payload["schema"] == CP.SCHEMA
    assert payload["market"] == "CN"
    assert payload["price_adjustment"] == ADJUSTED
    frozen = payload["names"]["600519.SS"]["frozen"]
    assert frozen["score"] == 81.2 and frozen["lane"] == "featured"
    assert payload["names"]["600519.SS"]["repaint_disclosure"]["live_derived"]


def test_r2_keys_are_distinct_from_the_us_lane() -> None:
    assert r2io.CN_PACK_KEY == "live_flow/cn_prophet_live_armed.json"
    assert r2io.CN_LIVE_KEY == "live_flow/cn_prophet_live.json"
    assert r2io.CN_PACK_KEY != r2io.PACK_KEY
    assert r2io.CN_LIVE_KEY != r2io.LIVE_KEY
    assert r2io.PACK_KEY == "live_flow/prophet_live_armed.json"


def test_cn_modules_import_no_limit_alpha_research() -> None:
    forbidden = ("cn_prophet_audit", "china_intelligence", "washout_program")
    for rel in ("engine/prophet_live/cn_pack.py", "engine/prophet_live/cn_states.py",
                "engine/prophet_live/cn_clock.py", "scripts/build_cn_live_pack.py",
                "scripts/cn_live_evaluator.py"):
        src = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(src):
            if isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        blob = " ".join(imported)
        for token in forbidden:
            assert token not in blob, f"{rel} imports {token}"


def test_stock_tradability_ok_matches_the_nightly_predicate() -> None:
    from scripts.build_china_library import stock_tradability_ok

    assert stock_tradability_ok("600000.SS") is None
    assert stock_tradability_ok("600000.SS", st_flag=True) == "st"
    assert stock_tradability_ok("600000.SS", name_zh="*ST 示例") == "st"
    assert stock_tradability_ok("600000.SS", mktcap=10.0) == "mcap"
    assert stock_tradability_ok("600000.SS", mktcap=30.0) is None  # placeholder
    assert stock_tradability_ok("600000.SS", adv_yi=0.01) == "adv"
