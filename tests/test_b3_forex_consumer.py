"""B3 Lane — None-safety tests for the forex consumer edits.

Covers:
1. lib.forex_link: stance() / dollar_day() / transmission_asset() degrade to
   {} / None / None when the file is absent.
2. engine.cross_asset_confirm: display_reasons empty-list when triple_red absent
   / usd_liquidity_draining fires on "supportive" dir.
3. engine.china_market_state._build_external_block: DXY read from pairs.DXY
   when present; degrades to None (gap logged) when absent.
4. engine.theme_scoring._macro_context: display.dollar_stance_word_en/zh keys
   present for all regions; never raises on absent forex store.
5. scripts.build_pick_lab._stamp_context: fx_regime_at_entry / usd_stance_at_entry
   stamps are None when forex absent, never fatal.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# 1. lib.forex_link — degrade to safe nulls when file absent
# ─────────────────────────────────────────────────────────────────────────────

def test_forex_link_stance_returns_empty_when_absent(tmp_path, monkeypatch):
    """stance() must return {} (not raise) when forex/latest.json is absent."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from lib import forex_link
    # reset module-level cache if any
    result = forex_link.stance()
    assert result == {} or isinstance(result, dict)


def test_forex_link_dollar_day_returns_none_when_absent(tmp_path, monkeypatch):
    """dollar_day() must return None when forex/latest.json is absent."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from lib import forex_link
    result = forex_link.dollar_day()
    assert result is None


def test_forex_link_transmission_asset_returns_none_when_absent(tmp_path, monkeypatch):
    """transmission_asset() must return None when file absent."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    from lib import forex_link
    assert forex_link.transmission_asset("GC=F") is None


def test_forex_link_stance_parses_when_present(tmp_path, monkeypatch):
    """stance() returns the stance block from latest.json when present."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    forex_dir = tmp_path / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "stance": {"word_en": "Watch — don't chase", "word_zh": "观望，别追", "tone": "calm"},
    }))
    from lib import forex_link
    result = forex_link.stance()
    assert result.get("word_en") == "Watch — don't chase"
    assert result.get("word_zh") == "观望，别追"


def test_forex_link_dollar_day_parses_when_present(tmp_path, monkeypatch):
    """dollar_day() returns {z, flag, dir} when present."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    forex_dir = tmp_path / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "dollar_day": {"z": 2.3, "flag": True, "dir": "up"},
    }))
    from lib import forex_link
    result = forex_link.dollar_day()
    assert isinstance(result, dict)
    assert result.get("flag") is True
    assert result.get("z") == pytest.approx(2.3)


def test_forex_link_transmission_asset_parses_when_present(tmp_path, monkeypatch):
    """transmission_asset() returns per-asset block from transmission.assets."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    forex_dir = tmp_path / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "transmission": {
            "assets": {
                "GC=F": {"corr_fast": -0.6, "corr_slow": -0.5, "effect": "headwind", "stability": "stable"},
            }
        }
    }))
    from lib import forex_link
    result = forex_link.transmission_asset("GC=F")
    assert isinstance(result, dict)
    assert result.get("effect") == "headwind"


# ─────────────────────────────────────────────────────────────────────────────
# 2. engine.cross_asset_confirm — display_reasons
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_asset_display_reasons_empty_when_no_desk():
    """display_reasons is always a list; empty when dollar_desk absent."""
    from engine.cross_asset_confirm import snapshot
    out = snapshot(
        {"quad": "Q1", "cycle_tag": "mid", "conditions": {"risk_appetite": {"roro_state": "risk-on"},
                                                            "drawdown_risk": {"band": "low"}}},
        bonds={"cycle_phase": "mid", "as_of": "2026-07-18",
               "pillars": {"curve": {}, "credit": {"distress_band": "tight", "direction": "tightening"},
                           "stress": {}, "cross_asset": {}, "sovereign": {}, "real_inflation": {}}},
        fx={"date": "2026-07-18", "regime": "US growth premium", "risk": "risk-on",
            "pairs": {"USDMXN": {"action": "SHORT", "score": -40},
                      "USDBRL": {"action": "FLAT", "score": -5}}},
    )
    assert "display_reasons" in out
    assert isinstance(out["display_reasons"], list)
    assert "usd_triple_red" not in out["display_reasons"]
    assert "usd_liquidity_draining" not in out["display_reasons"]


def test_cross_asset_display_reasons_triple_red_fires():
    """display_reasons contains usd_triple_red when triple_red=True."""
    from engine.cross_asset_confirm import snapshot
    out = snapshot(
        {"quad": "Q1", "cycle_tag": "mid", "conditions": {"risk_appetite": {"roro_state": "risk-on"},
                                                            "drawdown_risk": {"band": "low"}}},
        bonds={"cycle_phase": "mid", "as_of": "2026-07-18",
               "pillars": {"curve": {}, "credit": {"distress_band": "tight", "direction": "tightening"},
                           "stress": {}, "cross_asset": {}, "sovereign": {}, "real_inflation": {}}},
        fx={"date": "2026-07-18", "regime": "US growth premium", "risk": "risk-on",
            "pairs": {}, "dollar_desk": {"triple_red": True}},
    )
    assert "usd_triple_red" in out.get("display_reasons", [])


def test_cross_asset_display_reasons_liquidity_draining_fires():
    """display_reasons contains usd_liquidity_draining when liquidity_dir='supportive'."""
    from engine.cross_asset_confirm import snapshot
    out = snapshot(
        {"quad": "Q1", "cycle_tag": "mid", "conditions": {"risk_appetite": {"roro_state": "risk-on"},
                                                            "drawdown_risk": {"band": "low"}}},
        bonds={"cycle_phase": "mid", "as_of": "2026-07-18",
               "pillars": {"curve": {}, "credit": {"distress_band": "tight", "direction": "tightening"},
                           "stress": {}, "cross_asset": {}, "sovereign": {}, "real_inflation": {}}},
        fx={"date": "2026-07-18", "regime": "US growth premium", "risk": "risk-on",
            "pairs": {}, "dollar_desk": {"liquidity_dir": "supportive"}},
    )
    assert "usd_liquidity_draining" in out.get("display_reasons", [])


def test_cross_asset_display_reasons_no_crash_on_empty_fx():
    """snapshot never raises and display_reasons is a list even when fx={}."""
    from engine.cross_asset_confirm import snapshot
    out = snapshot({}, bonds={}, fx={})
    assert isinstance(out, dict)
    # display_reasons absent (unknown path) or empty list — never raises
    dr = out.get("display_reasons", [])
    assert isinstance(dr, list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. engine.china_market_state — DXY from pairs.DXY
# ─────────────────────────────────────────────────────────────────────────────

def test_china_external_block_dxy_from_pairs(tmp_path):
    """_build_external_block reads dxy from pairs.DXY when present."""
    from engine.china_market_state import _build_external_block
    forex_dir = tmp_path / "data" / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "date": "Jul 18, 2026",
        "pairs": {
            "USDCNH": {"quote": 7.10, "chg": 0.1},
            "DXY": {"quote": 103.5, "chg": 0.3, "label": "DXY"},
        },
    }))
    data_dir = tmp_path / "data"
    block, gaps = _build_external_block(data_dir)
    assert block is not None
    assert block.get("dxy") is not None
    assert block["dxy"]["quote"] == pytest.approx(103.5)
    assert block["dxy"]["chg"] == pytest.approx(0.3)
    # No "DXY not yet in" gap when key present
    assert not any("DXY not yet" in g for g in gaps)


def test_china_external_block_dxy_none_when_absent(tmp_path):
    """_build_external_block sets dxy=None (gap logged) when DXY key absent from pairs."""
    from engine.china_market_state import _build_external_block
    forex_dir = tmp_path / "data" / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "date": "Jul 18, 2026",
        "pairs": {
            "USDCNH": {"quote": 6.77, "chg": -0.1},
        },
    }))
    data_dir = tmp_path / "data"
    block, gaps = _build_external_block(data_dir)
    assert block is not None
    # dxy should be None when not in pairs
    assert block.get("dxy") is None
    # A gap must be logged mentioning DXY
    assert any("DXY" in g for g in gaps)


# ─────────────────────────────────────────────────────────────────────────────
# 4. engine.theme_scoring — dollar_stance_word for all regions
# ─────────────────────────────────────────────────────────────────────────────

def test_theme_scoring_macro_context_has_stance_keys():
    """_macro_context must have dollar_stance_word_en/zh in display for all regions."""
    from engine import theme_scoring as ts
    for region in ("us", "cn", "hk", "ca"):
        mc = ts._macro_context(region)
        disp = mc.get("display") or {}
        # Keys must be PRESENT (value may be None if forex absent, but key must exist)
        assert "dollar_stance_word_en" in disp, f"missing dollar_stance_word_en for {region}"
        assert "dollar_stance_word_zh" in disp, f"missing dollar_stance_word_zh for {region}"
        assert "dollar_regime" in disp, f"missing dollar_regime for {region}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. scripts.build_pick_lab._stamp_context — fx stamps None-safe
# ─────────────────────────────────────────────────────────────────────────────

def test_pick_lab_stamp_context_fx_stamps_present(tmp_path, monkeypatch):
    """_stamp_context must stamp fx_regime_at_entry and usd_stance_at_entry (None when absent)."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)

    # No forex file → should stamp None without raising
    from scripts.build_pick_lab import _stamp_context
    stamps = _stamp_context("AAPL", {}, None, "2026-07-18")
    assert "fx_regime_at_entry" in stamps
    assert "usd_stance_at_entry" in stamps
    # Values may be None when forex absent — that is expected
    assert stamps["fx_regime_at_entry"] is None
    assert stamps["usd_stance_at_entry"] is None


def test_pick_lab_stamp_context_fx_stamps_populated(tmp_path, monkeypatch):
    """_stamp_context reads fx regime + stance word from forex/latest.json when present."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    forex_dir = tmp_path / "forex"
    forex_dir.mkdir(parents=True)
    (forex_dir / "latest.json").write_text(json.dumps({
        "stance": {"word_en": "Watch — don't chase", "word_zh": "观望，别追", "tone": "calm"},
        "dollar_desk": {
            "smile_decomp": {"regime": "US growth premium"},
        },
    }))
    from scripts.build_pick_lab import _stamp_context
    stamps = _stamp_context("AAPL", {}, None, "2026-07-18")
    assert stamps.get("fx_regime_at_entry") == "US growth premium"
    assert stamps.get("usd_stance_at_entry") == "Watch — don't chase"
