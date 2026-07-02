"""Placeholder-mktcap sentinel + adversarial ST screen — masterplan §W6-CN fix 5.

Two verified bugs on the live china_stocks build path:
  (1) 46% of members.parquet mktcap_yi == 30.0 EXACTLY (a china_universe placeholder the
      build itself distrusts), yet it was fed into Altman-Z distress zones and P/S coloring —
      fabricating half the analyzer's distress readings from a CONSTANT.
  (2) the ST/*ST/退 screen keyed on the Sina name_zh, which DROPS the ST prefix (0/1494
      matches), so a known-ST name in the universe read as clean. Tushare's moneyflow name
      field preserves the prefix.

These tests lock in the sentinel-drop and the prefix-carrying ST source, and assert the
downstream Altman-Z engine ignores an unknown (None) cap instead of fabricating a zone.

Run: .venv/bin/python -m pytest tests/test_china_mktcap_st.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.china_reversal import is_st  # noqa: E402

_PLACEHOLDER = 30.0


def _mktcap_map(members: pd.DataFrame) -> dict:
    """The build's sentinel-aware mktcap comprehension (mirrors build_china_library)."""
    return {str(r["ticker"]): float(r["mktcap_yi"])
            for _, r in members.iterrows()
            if pd.notna(r.get("mktcap_yi")) and float(r["mktcap_yi"]) != _PLACEHOLDER}


def test_placeholder_mktcap_is_dropped_not_fed_as_real():
    members = pd.DataFrame({
        "ticker": ["600519.SS", "000001.SZ", "301234.SZ"],
        "mktcap_yi": [23000.0, 30.0, 30.0],          # two placeholders
    })
    caps = _mktcap_map(members)
    assert "600519.SS" in caps and caps["600519.SS"] == 23000.0   # real cap kept
    assert "000001.SZ" not in caps and "301234.SZ" not in caps    # sentinels dropped → unknown


def test_tushare_total_mv_fills_placeholder_gaps():
    """Real per-name caps overlay the placeholder-dropped names (asof-gated in the build)."""
    members = pd.DataFrame({"ticker": ["A.SS", "B.SZ"], "mktcap_yi": [500.0, 30.0]})
    caps = _mktcap_map(members)                       # B.SZ dropped
    tushare_real = {"B.SZ": 88.0}                     # Tushare total_mv_yi
    merged = {**tushare_real, **caps}                 # real fills gap, Sina real kept
    assert merged["A.SS"] == 500.0
    assert merged["B.SZ"] == 88.0                     # no longer a fabricated 30.0


def test_altman_ignores_unknown_cap_instead_of_fabricating():
    from engine import china_fundamentals as cf
    # a row with all four Altman legs derivable (equity/equity_multiplier → total assets,
    # retained_earnings_ps × shares, revenue, ebit_margin) so a real cap yields a zone.
    row = {"equity": 100.0, "equity_multiplier": 2.0, "revenue": 120.0,
           "retained_earnings_ps": 1.0, "bvps": 5.0, "ebit_margin": 10.0}
    with_cap = cf._altman(row, 300.0)
    without = cf._altman(row, None)
    assert without is None, "unknown cap must not fabricate an Altman-Z distress zone"
    assert isinstance(with_cap, dict) and "zone" in with_cap, "a real cap still yields a zone"


def test_st_screen_blind_on_sina_names_but_sees_tushare_prefix():
    # the exact adversarial case found live: 600777.SS
    sina_name_zh = "新潮能源"                          # Sina drops the prefix
    tushare_name = "*ST新潮"                           # Tushare carries it
    assert not is_st(sina_name_zh, None), "Sina name is silently clean (the bug)"
    assert is_st(tushare_name, None), "Tushare name field carries the ST flag (the fix source)"


def test_st_flag_sourced_from_tushare_moneyflow_name_field():
    """Mirror the build's ST-flag sourcing from the prefix-carrying moneyflow name field."""
    mf = pd.DataFrame({
        "ticker": ["600777.SS", "600519.SS", "000662.SZ"],
        "name": ["*ST新潮", "贵州茅台", "ST天成"],
        "trade_date": ["20260618", "20260618", "20260618"],
    })
    mf = mf.sort_values("trade_date").drop_duplicates("ticker", keep="last")
    st_flag_by = {str(r["ticker"]): is_st(str(r["name"]), None) for _, r in mf.iterrows()}
    assert st_flag_by["600777.SS"] is True
    assert st_flag_by["000662.SZ"] is True
    assert st_flag_by["600519.SS"] is False
    assert sum(st_flag_by.values()) == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
