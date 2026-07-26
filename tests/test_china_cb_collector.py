"""collectors/china_cb.py — fixture-pinned breadth + index parser tests.

ZERO NETWORK: the adapter's http_get is monkeypatched, so nothing here reaches
datacenter-web.eastmoney.com or jisilu.cn. Fixtures are the VERIFIED live shapes
(masterplan W2 probe anchors); the login-capped jisilu list endpoint is never used
anywhere in the collector, so there is nothing to fixture for it.

Covers:
  - universe filter: unlisted (LISTING_DATE=None) and delisted rows excluded
  - CURRENT_BOND_PRICE "-" coerced to NaN (bond stays unpriced, never zero-filled)
  - exact median / mean / pct math, including the 双低 (double-low) count
  - the n_priced floor raise (a broken quote join must be loud, not a thin aggregate)
  - snapshot dating by collection date + the weekend skip
  - pagination: page count honored, ≤1 req/s pacing between pages
  - jisilu index: aligned parse, numeric coercion, misaligned arrays -> ValueError
  - per-series isolation
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_cb as ccb  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures — copied from the VERIFIED live shapes
# --------------------------------------------------------------------------- #

class FakeResponse:
    """Minimal requests.Response stand-in (.json() / .text / .content / .status_code)."""

    def __init__(self, payload=None, text: str = "", status_code: int = 200):
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError("fixture response carries no JSON payload")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _cb(code: str, listing, delist, price, premium, scale) -> dict:
    """One RPT_BOND_CB_LIST row (only the fields the aggregate reads are populated)."""
    return {
        "SECURITY_CODE": code, "SECURITY_NAME_ABBR": f"债{code}",
        "CONVERT_STOCK_CODE": "600000", "LISTING_DATE": listing, "DELIST_DATE": delist,
        "CURRENT_BOND_PRICE": price, "TRANSFER_PREMIUM_RATIO": premium,
        "ACTUAL_ISSUE_SCALE": scale, "RATING": "AA",
    }


# 1 unlisted new issue + 1 delisted + 4 listed, one of which prices as the STRING "-".
# (The spec's 5-row shape plus one ≥130 row so pct_price_ge_130 is exercised non-trivially.)
_CB_ROWS = [
    _cb("113999", None, None, "120.00", "10.00", "5.00"),            # unlisted: excluded
    _cb("113001", "2020-01-01", "2025-06-30", "128.00", "3.00", "8.00"),  # delisted: excluded
    _cb("113002", "2024-05-06", None, "112.50", "8.00", "12.00"),    # priced, double-low
    _cb("113003", "2023-03-01", None, "-", None, "6.00"),            # listed but UNPRICED
    _cb("113004", "2022-08-08", None, "134.20", "25.40", "20.00"),   # priced, >=130
    _cb("113005", "2021-01-04", None, "96.80", "40.10", "3.50"),     # priced, <100
]

_JSL_DATES = ["2026-07-22", "2026-07-23", "2026-07-24"]
_JSL_PAYLOAD = {
    "code": 200, "msg": "", "rules": [],
    "data": {
        "price_dt": list(_JSL_DATES),
        "price": ["1234.56", "1240.10", "1245.00"],
        "count": ["316", "316", "317"],
        "avg_price": ["118.20", "118.90", "119.40"],
        "mid_price": ["115.10", "115.60", "116.00"],
        "avg_premium_rt": ["32.10", "31.80", "31.20"],
        "mid_premium_rt": ["24.50", "24.10", "23.90"],
        "avg_ytm_rt": ["-1.20", "-1.25", "-1.30"],
        "avg_dblow": ["150.30", "150.70", "150.60"],
        "temperature": ["58", "60", "--"],
        "turnover_rt": ["3.10", "3.40", "3.60"],
        "idx_price": ["1500.00", "1508.00", "1512.00"],
        # extra keys the endpoint also serves and we deliberately do not keep
        "price_dt_str": list(_JSL_DATES),
    },
}

_SATURDAY = date(2026, 7, 25)
_FRIDAY = date(2026, 7, 24)


def _adapter(today: date = _FRIDAY) -> ccb.ChinaCbAdapter:
    a = ccb.ChinaCbAdapter()
    a._today_cn = lambda: today       # type: ignore[method-assign]
    return a


# --------------------------------------------------------------------------- #
# breadth aggregate
# --------------------------------------------------------------------------- #

class TestBreadthAggregate:
    def test_universe_filter_and_exact_math(self, monkeypatch):
        # The live floor is 50 priced bonds; the fixture is deliberately tiny, so the
        # floor is lowered for the MATH test and exercised on its own below.
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        agg = ccb.aggregate_breadth(_CB_ROWS)
        assert agg["n_listed"] == 4.0, "unlisted + delisted rows must be excluded"
        assert agg["n_priced"] == 3.0, '"-" price leaves the bond unpriced'
        assert agg["price_med"] == pytest.approx(112.50)
        assert agg["price_mean"] == pytest.approx(114.50)      # (96.8+112.5+134.2)/3
        assert agg["premium_med"] == pytest.approx(25.40)
        assert agg["premium_mean"] == pytest.approx(24.50)     # (40.1+8.0+25.4)/3
        assert agg["pct_price_lt_100"] == pytest.approx(33.33)
        assert agg["pct_price_ge_130"] == pytest.approx(33.33)
        assert agg["pct_double_low"] == pytest.approx(33.33)   # only 112.50 / 8.00
        assert agg["issue_scale_sum"] == pytest.approx(41.50)  # 12.0+6.0+20.0+3.5

    def test_double_low_thresholds_are_named_constants(self):
        assert ccb.DOUBLE_LOW_PRICE == 115.0
        assert ccb.DOUBLE_LOW_PREMIUM == 15.0

    def test_double_low_boundaries_are_strict(self, monkeypatch):
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        rows = [_cb("1", "2020-01-01", None, "115.00", "8.00", "1.0"),   # price ON the cut
                _cb("2", "2020-01-01", None, "110.00", "15.00", "1.0")]  # premium ON the cut
        assert ccb.aggregate_breadth(rows)["pct_double_low"] == pytest.approx(0.0)

    def test_nan_premium_never_passes_double_low(self, monkeypatch):
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        rows = [_cb("1", "2020-01-01", None, "100.00", None, "1.0"),
                _cb("2", "2020-01-01", None, "112.00", "9.00", "1.0")]
        agg = ccb.aggregate_breadth(rows)
        assert agg["pct_double_low"] == pytest.approx(50.0), "NaN premium is not < 15"

    def test_negative_premium_is_kept(self, monkeypatch):
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        rows = [_cb("1", "2020-01-01", None, "99.00", "-3.50", "1.0"),
                _cb("2", "2020-01-01", None, "101.00", "-1.50", "1.0")]
        assert ccb.aggregate_breadth(rows)["premium_med"] == pytest.approx(-2.50)

    def test_priced_floor_raises_on_a_broken_quote_join(self):
        with pytest.raises(ValueError, match="quote join is broken"):
            ccb.aggregate_breadth(_CB_ROWS)      # 3 priced < MIN_PRICED (50)

    def test_no_remain_size_field_is_invented(self, monkeypatch):
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        agg = ccb.aggregate_breadth(_CB_ROWS)
        assert not any("remain" in k.lower() for k in agg)

    def test_absent_scale_field_is_nan_not_zero(self, monkeypatch):
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        rows = [_cb("1", "2020-01-01", None, "100.00", "1.0", None),
                _cb("2", "2020-01-01", None, "101.00", "1.0", None)]
        assert pd.isna(ccb.aggregate_breadth(rows)["issue_scale_sum"])


# --------------------------------------------------------------------------- #
# breadth leg: pagination, dating, weekend skip
# --------------------------------------------------------------------------- #

class TestBreadthLeg:
    def test_pagination_honors_page_count_and_paces(self, monkeypatch):
        a = _adapter()
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        sleeps: list[float] = []
        monkeypatch.setattr(ccb.time, "sleep", lambda s: sleeps.append(s))
        seen: list[dict] = []

        def fake_get(url, **kw):
            params = kw.get("params") or {}
            seen.append(params)
            page = int(params["pageNumber"])
            rows = _CB_ROWS if page == 1 else [
                _cb(f"11400{page}", "2020-01-01", None, "105.00", "12.00", "2.00")]
            return FakeResponse(payload={"result": {"count": 1038, "pages": 3,
                                                    "data": rows}})

        a.http_get = fake_get        # type: ignore[method-assign]
        df = a._breadth(full_history=False)
        assert [p["pageNumber"] for p in seen] == [1, 2, 3]
        assert sleeps == [ccb._HOST_PACE_S, ccb._HOST_PACE_S], "≤1 req/s between pages"
        p0 = seen[0]
        assert p0["reportName"] == "RPT_BOND_CB_LIST" and p0["columns"] == "ALL"
        assert p0["pageSize"] == 500 and p0["sortColumns"] == "PUBLIC_START_DATE"
        assert p0["sortTypes"] == -1 and p0["source"] == "WEB" and p0["client"] == "WEB"
        assert "CURRENT_BOND_PRICE" in p0["quoteColumns"]
        assert "TRANSFER_PREMIUM_RATIO" in p0["quoteColumns"]
        # 4 listed from page 1 + the two extra listed rows from pages 2 and 3
        assert df.loc[pd.Timestamp(_FRIDAY), "n_listed"] == 6.0
        assert list(df.index) == [pd.Timestamp(_FRIDAY)], "snapshot = collection date"

    def test_page_count_from_count_when_pages_absent(self, monkeypatch):
        a = _adapter()
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        monkeypatch.setattr(ccb.time, "sleep", lambda *_: None)
        pages_seen: list[int] = []

        def fake_get(url, **kw):
            page = int((kw.get("params") or {})["pageNumber"])
            pages_seen.append(page)
            return FakeResponse(payload={"result": {"count": 1038, "data": _CB_ROWS}})

        a.http_get = fake_get        # type: ignore[method-assign]
        a._breadth(full_history=False)
        assert pages_seen == [1, 2, 3], "ceil(1038/500) = 3 pages"

    def test_weekend_yields_no_frame_and_no_http(self):
        a = _adapter(_SATURDAY)

        def must_not_call(*_a, **_kw):
            raise AssertionError("no HTTP call may happen on a weekend")

        a.http_get = must_not_call   # type: ignore[method-assign]
        assert a._breadth(full_history=False) is None


# --------------------------------------------------------------------------- #
# jisilu equal-weight index
# --------------------------------------------------------------------------- #

class TestIndexHistory:
    def test_aligned_parse_and_numeric_coercion(self):
        df = ccb.parse_index_history(_JSL_PAYLOAD)
        assert list(df.index) == [pd.Timestamp(d) for d in _JSL_DATES]
        assert list(df.columns) == list(ccb._JSL_KEEP)
        assert all(df[c].dtype.kind == "f" for c in df.columns)
        assert df.loc[pd.Timestamp("2026-07-24"), "idx_price"] == pytest.approx(1512.0)
        assert df.loc[pd.Timestamp("2026-07-22"), "count"] == pytest.approx(316.0)
        assert df.loc[pd.Timestamp("2026-07-23"), "avg_ytm_rt"] == pytest.approx(-1.25)
        assert pd.isna(df.loc[pd.Timestamp("2026-07-24"), "temperature"]), '"--" -> NaN'
        assert "price_dt_str" not in df.columns, "unkept keys stay out of the store"

    def test_misaligned_arrays_raise(self):
        bad = {"data": dict(_JSL_PAYLOAD["data"])}
        bad["data"]["avg_price"] = ["118.20", "118.90"]    # one entry short
        with pytest.raises(ValueError, match="misaligned arrays"):
            ccb.parse_index_history(bad)

    def test_missing_price_dt_raises(self):
        with pytest.raises(ValueError, match="price_dt"):
            ccb.parse_index_history({"data": {"price": ["1.0"]}})

    def test_absent_optional_key_narrows_the_frame(self, caplog):
        payload = {"data": {k: v for k, v in _JSL_PAYLOAD["data"].items()
                            if k != "temperature"}}
        with caplog.at_level(logging.WARNING, logger="collectors.china_cb"):
            df = ccb.parse_index_history(payload)
        assert "temperature" not in df.columns
        assert "temperature" in caplog.text

    def test_leg_uses_the_keyless_index_endpoint_only(self):
        a = _adapter()
        seen: list[str] = []

        def fake_get(url, **kw):
            seen.append(url)
            return FakeResponse(payload=_JSL_PAYLOAD)

        a.http_get = fake_get        # type: ignore[method-assign]
        df = a._index(full_history=False)
        assert seen == ["https://www.jisilu.cn/webapi/cb/index_history/"]
        assert "cb_list_new" not in " ".join(seen), "the login-capped list is forbidden"
        assert len(df) == 3

    def test_collector_never_calls_the_login_capped_list(self):
        src = Path(ccb.__file__).read_text(encoding="utf-8")
        assert "cb_list_new" in src, "the CNH-R5/R6 ban belongs in the module docs"
        hits = [ln.strip() for ln in src.splitlines() if "cb_list_new" in ln]
        # every mention must be prose (docstring/comment) — never a URL constant or call
        assert all("http" not in ln and not ln.startswith("_") for ln in hits), hits


# --------------------------------------------------------------------------- #
# per-series isolation
# --------------------------------------------------------------------------- #

class TestFetchIsolation:
    def test_breadth_failure_still_returns_index(self, caplog):
        a = _adapter()

        def boom(_fh):
            raise RuntimeError("EastMoney down")

        a._breadth = boom            # type: ignore[method-assign]
        a._index = lambda _fh: ccb.parse_index_history(_JSL_PAYLOAD)  # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING, logger="collectors.china_cb"):
            frames = a.fetch()
        assert set(frames) == {"index"}
        assert "breadth" in caplog.text

    def test_weekend_skip_leaves_index_only(self):
        a = _adapter(_SATURDAY)
        a._index = lambda _fh: ccb.parse_index_history(_JSL_PAYLOAD)  # type: ignore[method-assign]
        frames = a.fetch()
        assert set(frames) == {"index"}

    def test_both_failing_raises_runtimeerror(self):
        a = _adapter()

        def boom(_fh):
            raise RuntimeError("down")

        a._breadth = boom            # type: ignore[method-assign]
        a._index = boom              # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="china_cb"):
            a.fetch()

    def test_both_legs_ok(self, monkeypatch):
        a = _adapter()
        monkeypatch.setattr(ccb, "MIN_PRICED", 2)
        monkeypatch.setattr(ccb.time, "sleep", lambda *_: None)

        def fake_get(url, **kw):
            if "jisilu" in url:
                return FakeResponse(payload=_JSL_PAYLOAD)
            return FakeResponse(payload={"result": {"pages": 1, "count": 6,
                                                    "data": _CB_ROWS}})

        a.http_get = fake_get        # type: ignore[method-assign]
        frames = a.fetch()
        assert set(frames) == {"breadth", "index"}


def test_adapter_contract_and_registration():
    a = ccb.ChinaCbAdapter()
    assert a.name == "china_cb" and a.group == "china_cb"
    assert a.stale_after_days == 6
    from scripts.collect import all_adapters
    assert all_adapters()["china_cb"].__name__ == "ChinaCbAdapter"
