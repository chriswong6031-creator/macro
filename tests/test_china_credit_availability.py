"""China TSF credit-impulse publication-availability stamping (audit #27).

The bug: the collector stamps TSF at reference-month START (April data -> 2026-04-01)
and the consumers shifted it a fixed 22 trading days, landing the impulse ~10 days
BEFORE the real ~day 9-15 release — a systematic look-ahead on China's most market-
moving macro print, feeding the 0.45-weight credit leg of the leveraged China book.

The fix re-stamps the TSF-derived series onto its publication-availability date
(day 16 of the following month, conservative bound) so a value can only be acted on
AFTER it was released. These tests are pure-function / synthetic-store — no network.

Run: python -m pytest tests/test_china_credit_availability.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_credit import (  # noqa: E402
    TSF_RELEASE_DOM,
    _find_flow_htm,
    _find_link_by_text,
    _parse_one,
    tsf_availability_date,
)
from engine import china_strategies as S  # noqa: E402


# --------------------------------------------------------------------------- #
# the availability-date model
# --------------------------------------------------------------------------- #
def test_availability_is_day16_of_following_month():
    # April data (reference-month start) becomes actable day 16 of MAY.
    assert tsf_availability_date(pd.Timestamp("2026-04-01")) == pd.Timestamp("2026-05-16")
    # December rolls into the next year.
    assert tsf_availability_date(pd.Timestamp("2025-12-01")) == pd.Timestamp("2026-01-16")
    # January.
    assert tsf_availability_date(pd.Timestamp("2026-01-01")) == pd.Timestamp("2026-02-16")
    assert TSF_RELEASE_DOM == 16


def test_availability_never_precedes_the_real_release_window():
    """NBS/PBoC release the prior month's TSF ~day 9-15 of the following month.
    The conservative availability bound (day 16) must be on/after the LATEST of
    that window for every month — so a backtest can never peek early."""
    for m in pd.date_range("2015-01-01", "2026-04-01", freq="MS"):
        avail = tsf_availability_date(m)
        latest_real_release = (m + pd.offsets.MonthBegin(1)).replace(day=15)
        assert avail >= latest_real_release, f"{m.date()} avail {avail.date()} precedes real release"


def test_availability_is_strictly_later_than_old_22bd_guess():
    """Guard-the-guard: the OLD fixed 22-trading-day shift from month-start landed
    BEFORE the availability date for recent months — proving the leak existed and
    the fix moves the actable date later (never earlier)."""
    moved_later = 0
    for m in pd.date_range("2024-01-01", "2026-04-01", freq="MS"):
        new_avail = tsf_availability_date(m)
        old_avail = pd.bdate_range(m, periods=23)[-1]     # month-start + 22 business days
        assert new_avail >= old_avail, f"{m.date()}: fix must not move the print EARLIER"
        if new_avail > old_avail:
            moved_later += 1
    assert moved_later >= 20, "the fix should push most prints materially later (the closed leak)"


# --------------------------------------------------------------------------- #
# the engine re-stamper (synthetic store — no network)
# --------------------------------------------------------------------------- #
def _synthetic_tsf_frame():
    """A reference-month-start-indexed TSF frame with the additive
    availability_date column, exactly as the patched collector emits."""
    idx = pd.date_range("2015-01-01", periods=36, freq="MS")
    df = pd.DataFrame({"tsf_total": np.linspace(1000, 2000, len(idx))}, index=idx)
    df["availability_date"] = [tsf_availability_date(d) for d in idx]
    return df


def test_availability_stamp_moves_index_to_release_dates(monkeypatch):
    df = _synthetic_tsf_frame()
    monkeypatch.setattr(S.store, "read",
                        lambda g, k: df if (g, k) == ("china_credit", "tsf") else None)
    # a reference-month-start-indexed derived series (as _credit_derisk builds)
    ref_series = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    stamped = S._tsf_availability_stamp(ref_series)
    # every stamped date must be a day-16 availability date, strictly AFTER its ref month
    for ref, avail in zip(df.index, stamped.index):
        assert avail.day == TSF_RELEASE_DOM
        assert avail > ref
    # values are preserved, just re-dated
    assert list(stamped.to_numpy()) == list(ref_series.to_numpy())


def test_availability_stamp_falls_back_without_column(monkeypatch):
    """A parquet written before this change (no availability_date column) must
    still de-leak via the conservative model, never fall back to reference dates."""
    idx = pd.date_range("2020-01-01", periods=6, freq="MS")
    df = pd.DataFrame({"tsf_total": np.arange(6.0)}, index=idx)   # NO availability_date
    monkeypatch.setattr(S.store, "read",
                        lambda g, k: df if (g, k) == ("china_credit", "tsf") else None)
    ref_series = pd.Series(np.arange(6.0), index=idx)
    stamped = S._tsf_availability_stamp(ref_series)
    for ref, avail in zip(idx, stamped.index):
        assert avail == tsf_availability_date(ref)
        assert avail > ref


def test_credit_leg_lag_is_small_not_22(monkeypatch):
    """The consumers must now use the small residual execution lag, not the old
    22-trading-day peek (the availability stamp already carries the release lag)."""
    assert S._CREDIT_EXEC_LAG <= 2
    # both consumers key on the shared constant, so they stay in lockstep
    from engine import china_masterminds as MM
    assert MM._LAG_CREDIT == S._CREDIT_EXEC_LAG


# --------------------------------------------------------------------------- #
# the PBoC 增量统计表 parser (2026-07 repair: mofcom mirror froze at 2026-04)
# --------------------------------------------------------------------------- #
def _synthetic_pbc_table():
    """Mimics pandas.read_html output for the PBoC flow attachment: banner rows,
    a merged CN header row (with &nbsp; padding), an EN header row, month rows,
    and all-NaN rows for months not yet published."""
    nan = np.nan
    return pd.DataFrame([
        ["社会融资规模增量统计表"] * 12,
        ["单位：亿元人民币"] * 12,
        ["项目 Items 月份 Month", "社会融资\xa0规模增量", "人民币贷款", "外币贷款（折合人民币）",
         "委托贷款", "信托贷款", "未贴现银行承兑汇票", "企业债券", "政府债券",
         "非金融企业境内股票融资", "存款类金融机构资产支持证券", "贷款核销"],
        ["项目 Items 月份 Month", "AFRE(flow)", "RMB loans", "FX loans", "Entrusted",
         "Trust", "Undiscounted", "Corp bonds", "Gov bonds", "Equity", "ABS", "W/O"],
        ["2026.01", "72185", "49016", "468", "-192", "-4", "6293", "5033", "9764", "291", "1", "2"],
        ["2026.05", "20264", "4965", "117", "-90", "53", "-685", "1680", "12236", "298", "3", "4"],
        ["2026.06", nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan],
    ])


def test_pbc_parser_extracts_month_rows_and_components():
    out = _parse_one(_synthetic_pbc_table())
    assert list(out.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-05-01")]
    assert out.loc["2026-05-01", "tsf_total"] == 20264
    assert out.loc["2026-05-01", "rmb_loans"] == 4965
    assert out.loc["2026-01-01", "accept_bills"] == 6293
    assert out.loc["2026-01-01", "govt_bonds"] == 9764   # additive vs mofcom feed
    assert out.loc["2026-05-01", "equity"] == 298
    # unpublished trailing month (all-NaN row) must be dropped, not stored as NaN
    assert pd.Timestamp("2026-06-01") not in out.index


def test_pbc_parser_rejects_stock_table():
    """The 存量 (stock) table on the same page must parse to None so the collector
    keeps scanning instead of storing 400-万亿 stocks as monthly flows."""
    stock = _synthetic_pbc_table().replace("社会融资\xa0规模增量", "社会融资规模存量")
    assert _parse_one(stock) is None


def test_flow_htm_picked_after_flow_heading_not_stock():
    html = (
        '<div>社会融资规模增量统计表</div>'
        '<a href="/attach/flow_table.htm">htm</a><a href="/attach/flow.xlsx">xls</a>'
        '<div>社会融资规模存量统计表</div>'
        '<a href="/attach/stock_table.htm">htm</a>'
    )
    assert _find_flow_htm(html) == "/attach/flow_table.htm"
    assert _find_flow_htm("<a href='/x.htm'>no heading</a>") is None


# --- PBoC layout-drift tolerance (all shapes PBoC has shipped historically) --- #
def test_pbc_parser_tolerates_qizhong_prefix():
    """Some vintages prefix loan sub-components as 其中：人民币贷款 — the mapper
    must still bind rmb_loans/fx_loans (they feed china_internals' tsf_mix bank
    bucket, which would silently collapse to 0 if unmapped)."""
    t = _synthetic_pbc_table().replace({
        "人民币贷款": "其中：人民币贷款",
        "外币贷款（折合人民币）": "其中:外币贷款（折合人民币）",
    })
    out = _parse_one(t)
    assert out.loc["2026-05-01", "rmb_loans"] == 4965
    assert out.loc["2026-05-01", "fx_loans"] == 117


def test_pbc_parser_handles_promoted_thead():
    """A clean <thead> table makes read_html promote CN headers into columns —
    the parser must fall back to scanning raw.columns, not fail the source."""
    body = _synthetic_pbc_table()
    hdr_cells = body.iloc[2].tolist()
    data = body.iloc[4:].reset_index(drop=True)
    data.columns = hdr_cells
    out = _parse_one(data)
    assert out.loc["2026-01-01", "tsf_total"] == 72185
    assert out.loc["2026-05-01", "govt_bonds"] == 12236


def test_pbc_parser_accepts_nian_yue_month_labels():
    t = _synthetic_pbc_table().replace({"2026.01": "2026年1月", "2026.05": "2026年5月"})
    out = _parse_one(t)
    assert list(out.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-05-01")]


def test_link_finders_tolerate_single_quoted_href():
    assert _find_link_by_text(
        "<a href='/dcs/2026.html'>2026年统计数据</a>", "2026年统计数据") == "/dcs/2026.html"
    assert _find_flow_htm("增量统计表 <a href='/attach/f.htm'>htm</a>") == "/attach/f.htm"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
