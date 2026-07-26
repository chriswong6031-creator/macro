"""collectors/china_fund_issuance.py — fixture-pinned JS-unwrap + weekly aggregate tests.

ZERO NETWORK: the adapter's http_get is monkeypatched, so nothing here reaches
fund.eastmoney.com. The fixture is the VERIFIED live shape: a `var newfunddata={...};`
JS-variable payload whose datas[] rows are 19 strings.

Covers:
  - the exact JS-unwrap transform (strip to '=', drop ';', quote bare keys, json.loads)
  - W-FRI weekly grouping (two equity rows in one week aggregate into one row)
  - the equity / bond / other split and its documented overlap precedence
  - rows still raising (empty 募集份额 / empty 成立日期) excluded
  - empty weeks dropped rather than written as zero rows
  - nightly page window "1,400" vs --full-history "1,50000"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_fund_issuance as cfi  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures — copied from the VERIFIED live shape
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


def _row(code: str, name: str, issuer: str, typ: str, shares: str,
         established: str) -> list[str]:
    """One datas[] row: 19 strings, only the read positions carry real values."""
    r = [""] * 19
    r[cfi._I_CODE] = code
    r[cfi._I_NAME] = name
    r[cfi._I_ISSUER] = issuer
    r[3] = "2026-07-01"                 # 认购起始日 (unused)
    r[cfi._I_TYPE] = typ
    r[cfi._I_SHARES] = shares
    r[cfi._I_ESTABLISHED] = established
    r[7] = "1.0000"                     # 单位净值 (unused)
    r[cfi._I_MANAGER] = "某经理"
    r[cfi._I_STATUS] = "开放申购"
    r[cfi._I_WINDOW] = "2026-07-01~2026-07-15"
    return r


_ROWS = [
    # two EQUITY funds established in the same W-FRI week (Mon 07-20 and Wed 07-22)
    _row("028369", "易方达新常态混合C", "易方达", "混合型-灵活", "12.34", "2026-07-20"),
    _row("028370", "某沪深300指数A", "某基金", "指数型-股票", "5.66", "2026-07-22"),
    # a BOND fund in the same week
    _row("028371", "某中长期纯债A", "某基金", "债券型-长债", "30.00", "2026-07-21"),
    # still raising: EMPTY 募集份额 and no 成立日期 -> excluded entirely
    _row("028372", "仍在募集混合A", "某基金", "混合型-灵活", "", ""),
    # an 'other' fund six weeks earlier -> its own bin, with empty weeks between
    _row("028373", "某QDII基金", "某基金", "QDII", "2.00", "2026-06-05"),
]

_JS_PAYLOAD = (
    "var newfunddata={datas:"
    + str([[str(c) for c in row] for row in _ROWS]).replace("'", '"')
    + ",curpage:1,pages:1,record:5};"
)

_WEEK = pd.Timestamp("2026-07-24")          # Friday of the 07-20..07-24 week
_EARLIER_WEEK = pd.Timestamp("2026-06-05")


# --------------------------------------------------------------------------- #
# JS unwrap
# --------------------------------------------------------------------------- #

class TestUnwrapJsPayload:
    def test_bare_keys_are_quoted_and_body_parses(self):
        payload = cfi.unwrap_js_payload(_JS_PAYLOAD)
        assert set(payload) == {"datas", "curpage", "pages", "record"}
        assert payload["record"] == 5
        assert len(payload["datas"]) == 5
        assert payload["datas"][0][cfi._I_CODE] == "028369"

    def test_trailing_semicolon_and_whitespace_tolerated(self):
        assert cfi.unwrap_js_payload("var x={datas:[],record:0} ;  ")["record"] == 0

    def test_nested_bare_keys_quoted(self):
        out = cfi.unwrap_js_payload("var x={datas:[[\"a\"]],meta:{page:2,size:400}};")
        assert out["meta"] == {"page": 2, "size": 400}

    def test_non_assignment_raises(self):
        with pytest.raises(ValueError, match="not a JS variable assignment"):
            cfi.unwrap_js_payload("<html>blocked</html>")

    def test_unparseable_body_raises(self):
        with pytest.raises(ValueError, match="not JSON"):
            cfi.unwrap_js_payload("var x={datas:[[unquoted]]};")


# --------------------------------------------------------------------------- #
# type classification
# --------------------------------------------------------------------------- #

class TestClassifyType:
    def test_equity_families(self):
        for t in ("混合型-灵活", "指数型-股票", "股票型"):
            assert cfi.classify_type(t) == "equity"

    def test_bond_family(self):
        for t in ("债券型-长债", "债券型-中短债", "可转债"):
            assert cfi.classify_type(t) == "bond"

    def test_bond_wins_the_hybrid_overlap(self):
        # 偏债混合 carries both keyword families; bond precedence keeps the three share
        # columns a partition of shares_yi (other_ can never go negative).
        assert cfi.classify_type("偏债混合型") == "bond"

    def test_other(self):
        for t in ("QDII", "FOF", "", None):
            assert cfi.classify_type(t) == "other"   # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# weekly aggregate
# --------------------------------------------------------------------------- #

class TestAggregateWeekly:
    def test_wfri_grouping_and_splits(self):
        out = cfi.aggregate_weekly([[str(c) for c in r] for r in _ROWS])
        assert list(out.index) == [_EARLIER_WEEK, _WEEK]
        assert isinstance(out.index, pd.DatetimeIndex)
        assert list(out.columns) == ["n_funds", "shares_yi", "equity_n",
                                     "equity_shares_yi", "bond_shares_yi",
                                     "other_shares_yi"]
        wk = out.loc[_WEEK]
        assert wk["n_funds"] == 3.0, "the still-raising row must be excluded"
        assert wk["shares_yi"] == pytest.approx(48.00)          # 12.34+5.66+30.00
        assert wk["equity_n"] == 2.0
        assert wk["equity_shares_yi"] == pytest.approx(18.00)   # 12.34+5.66
        assert wk["bond_shares_yi"] == pytest.approx(30.00)
        assert wk["other_shares_yi"] == pytest.approx(0.0)
        early = out.loc[_EARLIER_WEEK]
        assert early["n_funds"] == 1.0
        assert early["other_shares_yi"] == pytest.approx(2.00)
        # the split always partitions the weekly total exactly
        for _, r in out.iterrows():
            assert (r["equity_shares_yi"] + r["bond_shares_yi"]
                    + r["other_shares_yi"]) == pytest.approx(r["shares_yi"])

    def test_empty_weeks_are_dropped_not_zero_filled(self):
        out = cfi.aggregate_weekly([[str(c) for c in r] for r in _ROWS])
        # 06-05 -> 07-24 spans 8 W-FRI bins; only the two populated ones survive
        assert len(out) == 2
        assert (out["n_funds"] > 0).all()

    def test_saturday_establishment_falls_into_the_next_friday_bin(self):
        rows = [_row("1", "n", "i", "混合型", "1.00", "2026-07-25")]   # Saturday
        out = cfi.aggregate_weekly([[str(c) for c in r] for r in rows])
        assert list(out.index) == [pd.Timestamp("2026-07-31")]

    def test_all_rows_unparseable_raises(self):
        rows = [_row("1", "n", "i", "混合型", "", ""),
                _row("2", "n", "i", "债券型", "abc", "not-a-date")]
        with pytest.raises(ValueError, match="成立日期"):
            cfi.aggregate_weekly([[str(c) for c in r] for r in rows])

    def test_short_and_malformed_rows_skipped(self):
        rows = [["028369", "短行"],                     # truncated row
                "not-a-list",                           # junk
                _row("028370", "某混合A", "某基金", "混合型-灵活", "3.00", "2026-07-20")]
        out = cfi.aggregate_weekly(rows)                 # type: ignore[arg-type]
        assert out.loc[_WEEK, "n_funds"] == 1.0

    def test_shares_without_establishment_excluded(self):
        rows = [_row("1", "n", "i", "混合型", "9.99", ""),
                _row("2", "n", "i", "混合型", "1.00", "2026-07-20")]
        out = cfi.aggregate_weekly([[str(c) for c in r] for r in rows])
        assert out.loc[_WEEK, "shares_yi"] == pytest.approx(1.00)


# --------------------------------------------------------------------------- #
# leg wiring: page window + params
# --------------------------------------------------------------------------- #

class TestIssuanceLeg:
    def _capture(self, full_history: bool) -> tuple[dict, pd.DataFrame]:
        a = cfi.ChinaFundIssuanceAdapter()
        seen: dict = {}

        def fake_get(url, **kw):
            seen["url"] = url
            seen["params"] = kw.get("params")
            return FakeResponse(text=_JS_PAYLOAD)

        a.http_get = fake_get        # type: ignore[method-assign]
        return seen, a._issuance(full_history=full_history)

    def test_nightly_window_is_the_400_row_page(self):
        seen, df = self._capture(False)
        assert seen["params"]["page"] == "1,400"
        assert seen["params"]["t"] == "xcln" and seen["params"]["isbuy"] == "1"
        assert seen["params"]["sort"] == "jzrgq,desc"
        assert seen["url"].endswith("/data/FundNewIssue.aspx")
        # Boundary-week guard: the OLDEST bin the rolling window reaches is cut
        # mid-week, so nightly drops it rather than overwriting the fuller value
        # the store earned while that week was fully inside the window.
        assert len(df) == 1
        assert df.index[0] == _WEEK          # the newer (fully covered) bin survives

    def test_nightly_boundary_bin_is_dropped_but_full_history_keeps_it(self):
        _, nightly = self._capture(False)
        _, deep = self._capture(True)
        assert len(deep) == 2                 # deep pull covers the whole list: no cut
        dropped = set(deep.index) - set(nightly.index)
        assert dropped == {deep.index.min()}  # exactly the oldest (boundary) bin

    def test_full_history_asks_for_the_whole_list(self):
        seen, df = self._capture(True)
        assert seen["params"]["page"] == "1,50000"
        assert len(df) == 2

    def test_fetch_returns_the_issuance_frame(self):
        a = cfi.ChinaFundIssuanceAdapter()
        a.http_get = lambda url, **kw: FakeResponse(text=_JS_PAYLOAD)  # type: ignore[method-assign]
        frames = a.fetch()
        assert set(frames) == {"issuance"}
        assert frames["issuance"].loc[_WEEK, "n_funds"] == 3.0

    def test_fetch_raises_when_the_only_leg_fails(self):
        a = cfi.ChinaFundIssuanceAdapter()

        def boom(url, **kw):
            raise RuntimeError("EastMoney down")

        a.http_get = boom            # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="china_fund_issuance"):
            a.fetch()


def test_adapter_contract_and_registration():
    a = cfi.ChinaFundIssuanceAdapter()
    assert a.name == "china_fund_issuance" and a.group == "china_fund_issuance"
    assert a.stale_after_days == 12
    from scripts.collect import all_adapters
    assert all_adapters()["china_fund_issuance"].__name__ == "ChinaFundIssuanceAdapter"
