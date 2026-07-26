"""collectors/china_funding.py — fixture-pinned parser + aggregate tests.

ZERO NETWORK: every HTTP path is monkeypatched at the adapter's own http_get/_post
helpers, so nothing here can reach chinamoney.com.cn, cdn.jin10.com, or EastMoney.
Fixtures are the VERIFIED live response shapes (masterplan W2 probe anchors).

Covers:
  - FrrHis records[].frValueMap -> exact FR/FDR columns, numeric dtypes, datetime index
  - the nightly single-window call (window ≤ 1 month, the server constraint)
  - the frr-chrt.csv fallback: FR-only columns + the warning that says why FDR is absent
  - month_windows never straddling a month boundary
  - il_1.json -> 8 tenor columns, "--" -> NaN, full-span parse
  - the EastMoney SHIBOR fallback narrowing to the 'on' tenor
  - CbMktMakQuot aggregate math (medians, spread bp, 国债/policy split), malformed-row
    skipping, the weekend skip, and the zero-parseable-quotes raise
  - per-series isolation: one failing leg still returns the others; all-fail -> RuntimeError
  - adapter registration in scripts.collect.all_adapters()
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_funding as cfu  # noqa: E402


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


def _frr_rec(d: str, fr1: str, fr7: str, fr14: str,
             fdr1: str, fdr7: str, fdr14: str) -> dict:
    return {"frTenor": "", "frValueMap": {
        "date": d, "FR001": fr1, "FR007": fr7, "FR014": fr14,
        "FDR001": fdr1, "FDR007": fdr7, "FDR014": fdr14}}


_FRRHIS_RECORDS = [
    _frr_rec("2026-07-22", "1.3900", "1.4000", "1.4200", "1.3700", "1.3900", "1.3700"),
    _frr_rec("2026-07-23", "1.3950", "1.4050", "1.4250", "1.3750", "1.3950", "1.3750"),
    _frr_rec("2026-07-24", "1.4000", "1.4100", "1.4300", "1.3800", "1.4000", "1.3800"),
]
_FRRHIS_PAYLOAD = {"data": {}, "head": {"rep_code": "200"}, "records": _FRRHIS_RECORDS}

# frr-chrt.csv: headerless date + the three FR fixings (no FDR set at all)
_FRR_CSV_TEXT = (
    "2026-07-22,1.39,1.40,1.42\n"
    "2026-07-23,1.395,1.405,1.425\n"
    "2026-07-24,1.40,1.41,1.43\n"
)

# il_1.json: element [0] = fixing %, [1] = change in bp; "--" where a tenor did not fix
_IL1_PAYLOAD = {
    "keys": [], "products": [],
    "values": {
        "2015-05-08": {"O/N": ["1.0000", "0.10"], "1W": ["1.1000", "0.20"],
                       "2W": ["1.2000", "0.30"], "1M": ["1.3000", "0.40"],
                       "3M": ["1.4000", "0.50"], "6M": ["1.5000", "0.60"],
                       "9M": ["1.6000", "0.70"], "1Y": ["1.7000", "0.80"]},
        "2026-07-23": {"O/N": ["1.3700", "-0.50"], "1W": ["1.3900", "0.10"],
                       "2W": ["1.4100", "0.20"], "1M": ["1.4300", "0.30"],
                       "3M": ["1.4500", "0.40"], "6M": ["1.4700", "0.50"],
                       "9M": ["1.4800", "0.60"], "1Y": ["--", "--"]},
        "2026-07-24": {"O/N": ["1.3812", "1.62"], "1W": ["1.4000", "1.00"],
                       "2W": ["1.4200", "1.00"], "1M": ["1.4400", "1.00"],
                       "3M": ["1.4600", "1.00"], "6M": ["1.4750", "1.00"],
                       "9M": ["1.4780", "1.00"], "1Y": ["1.4791", "1.00"]},
    },
}

# CbMktMakQuot: contraRate = "bid / ask" YIELD %, '---' and one-sided quotes are junk
_MM_RECORDS = [
    {"abdAssetEncdShrtDesc": "26附息国债05", "emaEntyEncdShrtDesc": "工商银行",
     "contraRate": "1.7000 / 1.6800", "bondcode": "260005", "tradeAmnt": "1000"},
    {"abdAssetEncdShrtDesc": "26国开清发02", "emaEntyEncdShrtDesc": "中信证券",
     "contraRate": "1.5400 / 1.4500", "bondcode": "260202", "tradeAmnt": "500"},
    {"abdAssetEncdShrtDesc": "26农发清发01", "emaEntyEncdShrtDesc": "建设银行",
     "contraRate": "1.6000 / 1.5600", "bondcode": "260401", "tradeAmnt": "300"},
    {"abdAssetEncdShrtDesc": "25进出06", "emaEntyEncdShrtDesc": "招商银行",
     "contraRate": "---", "bondcode": "250306", "tradeAmnt": "0"},           # no quote
    {"abdAssetEncdShrtDesc": "26附息国债05", "emaEntyEncdShrtDesc": "农业银行",
     "contraRate": "1.7100", "bondcode": "260005", "tradeAmnt": "200"},      # one-sided
    {"abdAssetEncdShrtDesc": "26贴现国债30", "emaEntyEncdShrtDesc": "兴业银行",
     "contraRate": "abc / 1.5000", "bondcode": "260030", "tradeAmnt": "100"},  # malformed
]
_MM_PAYLOAD = {"data": {}, "head": {"rep_code": "200"}, "records": _MM_RECORDS}

_SATURDAY = date(2026, 7, 25)
_FRIDAY = date(2026, 7, 24)


def _adapter(today: date = _FRIDAY) -> cfu.ChinaFundingAdapter:
    a = cfu.ChinaFundingAdapter()
    a._today_cn = lambda: today       # type: ignore[method-assign]
    return a


# --------------------------------------------------------------------------- #
# repo fixings — FrrHis
# --------------------------------------------------------------------------- #

class TestFrrHis:
    def test_frame_columns_dtypes_index(self):
        df = cfu.parse_frr_records(_FRRHIS_RECORDS)
        assert list(df.columns) == ["FR001", "FR007", "FR014", "FDR001", "FDR007", "FDR014"]
        assert isinstance(df.index, pd.DatetimeIndex)
        assert all(df[c].dtype.kind == "f" for c in df.columns)
        assert len(df) == 3
        assert df.loc[pd.Timestamp("2026-07-24"), "FR007"] == pytest.approx(1.41)
        assert df.loc[pd.Timestamp("2026-07-24"), "FDR007"] == pytest.approx(1.40)

    def test_undated_and_junk_records_dropped(self):
        recs = list(_FRRHIS_RECORDS) + [
            {"frValueMap": {"date": "", "FR001": "9.9"}},
            {"frValueMap": {"date": "not-a-date", "FR001": "9.9"}},
            {"noValueMap": True},
            "not-a-dict",
        ]
        df = cfu.parse_frr_records(recs)   # type: ignore[arg-type]
        assert len(df) == 3

    def test_unparseable_rate_becomes_nan_not_zero(self):
        df = cfu.parse_frr_records([_frr_rec("2026-07-24", "--", "1.41", "", "-", "1.40", "1.38")])
        assert pd.isna(df.loc[pd.Timestamp("2026-07-24"), "FR001"])
        assert pd.isna(df.loc[pd.Timestamp("2026-07-24"), "FR014"])
        assert pd.isna(df.loc[pd.Timestamp("2026-07-24"), "FDR001"])
        assert df.loc[pd.Timestamp("2026-07-24"), "FR007"] == pytest.approx(1.41)

    def test_nightly_is_one_call_with_a_sub_month_window(self):
        a = _adapter()
        calls: list[dict] = []

        def fake_post(url, **kw):
            calls.append({"url": url, "params": kw.get("params")})
            return FakeResponse(payload=_FRRHIS_PAYLOAD)

        a._post = fake_post          # type: ignore[method-assign]
        df = a._repo_fixings(full_history=False)
        assert len(calls) == 1, "nightly repo_fixings must be a single window call"
        params = calls[0]["params"]
        assert params["lang"] == "CN"
        span = date.fromisoformat(params["endDate"]) - date.fromisoformat(params["startDate"])
        assert span.days <= 31, "FrrHis rejects windows longer than one month"
        assert params["endDate"] == _FRIDAY.isoformat()
        assert len(df) == 3

    def test_deep_pull_walks_month_windows_and_tolerates_empties(self, monkeypatch):
        a = _adapter()
        monkeypatch.setattr(cfu.time, "sleep", lambda *_: None)
        windows: list[tuple[str, str]] = []

        def fake_post(url, **kw):
            p = kw.get("params") or {}
            windows.append((p["startDate"], p["endDate"]))
            # only the final window carries data; every earlier one comes back empty
            if p["endDate"] == _FRIDAY.isoformat():
                return FakeResponse(payload=_FRRHIS_PAYLOAD)
            return FakeResponse(payload={"records": []})

        a._post = fake_post          # type: ignore[method-assign]
        df = a._repo_fixings(full_history=True)
        assert len(windows) == len(cfu.month_windows(cfu._FRR_INCEPTION, _FRIDAY))
        assert windows[0][0] == "2015-01-01"
        assert len(df) == 3, "empty windows are tolerated, the good one still lands"


class TestMonthWindows:
    def test_windows_never_straddle_a_month(self):
        wins = cfu.month_windows(date(2026, 1, 15), date(2026, 3, 3))
        assert wins == [(date(2026, 1, 15), date(2026, 1, 31)),
                        (date(2026, 2, 1), date(2026, 2, 28)),
                        (date(2026, 3, 1), date(2026, 3, 3))]

    def test_single_day_span(self):
        assert cfu.month_windows(date(2026, 7, 24), date(2026, 7, 24)) == [
            (date(2026, 7, 24), date(2026, 7, 24))]


# --------------------------------------------------------------------------- #
# repo fixings — documented CSV fallback
# --------------------------------------------------------------------------- #

class TestFrrCsvFallback:
    def test_fallback_is_fr_only_and_warns_why(self, caplog):
        a = _adapter()

        def boom(*_a, **_kw):
            raise RuntimeError("FrrHis HTTP 502")

        a._post = boom               # type: ignore[method-assign]
        a.http_get = lambda url, **kw: FakeResponse(text=_FRR_CSV_TEXT)  # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING, logger="collectors.china_funding"):
            df = a._repo_fixings(full_history=False)
        assert list(df.columns) == ["FR001", "FR007", "FR014"]
        assert not any(c.startswith("FDR") for c in df.columns), "FDR must stay ABSENT"
        assert len(df) == 3
        assert df.loc[pd.Timestamp("2026-07-24"), "FR014"] == pytest.approx(1.43)
        text = caplog.text
        assert "frr-chrt.csv" in text and "FDR" in text, "the warning must say why FDR is gone"
        assert "fdr-chrt.csv" in text, "the frozen sibling must be named as never-fetched"

    def test_csv_header_row_is_dropped(self):
        df = cfu.parse_frr_csv("date,FR001,FR007,FR014\n" + _FRR_CSV_TEXT)
        assert len(df) == 3
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_csv_shape_drift_raises_instead_of_mismapping(self):
        with pytest.raises(ValueError, match="populated columns"):
            cfu.parse_frr_csv("2026-07-24,1.40,1.41\n2026-07-23,1.39,1.40\n")


# --------------------------------------------------------------------------- #
# SHIBOR
# --------------------------------------------------------------------------- #

class TestShibor:
    def test_eight_tenors_full_span_and_dashes_are_nan(self):
        a = _adapter()
        seen: list[dict] = []

        def fake_get(url, **kw):
            seen.append({"url": url, "params": kw.get("params")})
            return FakeResponse(payload=_IL1_PAYLOAD)

        a.http_get = fake_get        # type: ignore[method-assign]
        df = a._shibor(full_history=False)
        assert list(df.columns) == ["on", "w1", "w2", "m1", "m3", "m6", "m9", "y1"]
        assert len(seen) == 1 and "cdn.jin10.com" in seen[0]["url"]
        assert "_" in (seen[0]["params"] or {}), "cache-buster param must be sent"
        # full span: the 2015 inception row and today's row are both present
        assert df.index.min() == pd.Timestamp("2015-05-08")
        assert df.index.max() == pd.Timestamp("2026-07-24")
        assert df.loc[pd.Timestamp("2026-07-24"), "on"] == pytest.approx(1.3812)
        assert df.loc[pd.Timestamp("2026-07-24"), "y1"] == pytest.approx(1.4791)
        # "--" -> NaN, never 0.0
        assert pd.isna(df.loc[pd.Timestamp("2026-07-23"), "y1"])
        assert df.loc[pd.Timestamp("2026-07-23"), "m9"] == pytest.approx(1.48)
        assert all(df[c].dtype.kind == "f" for c in df.columns)

    def test_full_history_is_identical_to_nightly(self):
        a = _adapter()
        a.http_get = lambda url, **kw: FakeResponse(payload=_IL1_PAYLOAD)  # type: ignore[method-assign]
        pd.testing.assert_frame_equal(a._shibor(True), a._shibor(False))

    def test_change_bp_element_is_dropped(self):
        df = cfu.parse_shibor_values(_IL1_PAYLOAD["values"])
        # element [1] (the bp change) must never leak into a column
        assert df.loc[pd.Timestamp("2026-07-24"), "on"] == pytest.approx(1.3812)
        assert 1.62 not in set(df.loc[pd.Timestamp("2026-07-24")].tolist())

    def test_em_fallback_narrows_to_on_tenor_and_logs_it(self, caplog):
        a = _adapter()

        def fake_get(url, **kw):
            if "jin10" in url:
                raise RuntimeError("CDN HTTP 502")
            return FakeResponse(payload={"result": {"data": [
                {"REPORT_DATE": "2026-07-24 00:00:00", "IR_RATE": "1.3812",
                 "CHANGE_RATE": "1.62"},
                {"REPORT_DATE": "2026-07-23 00:00:00", "IR_RATE": "1.3700",
                 "CHANGE_RATE": "-0.50"},
            ]}})

        a.http_get = fake_get        # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING, logger="collectors.china_funding"):
            df = a._shibor(full_history=False)
        assert list(df.columns) == ["on"]
        assert len(df) == 2
        assert df.loc[pd.Timestamp("2026-07-24"), "on"] == pytest.approx(1.3812)
        assert "narrow" in caplog.text.lower(), "the narrowing must be logged"

    def test_empty_values_map_triggers_the_fallback_not_an_empty_store(self):
        # An empty payload must NOT be written as an empty/zero frame: the leg treats it
        # as a failure and hands over to the documented fallback.
        assert cfu.parse_shibor_values({}).empty
        a = _adapter()
        calls: list[str] = []

        def fake_get(url, **kw):
            calls.append(url)
            if "jin10" in url:
                return FakeResponse(payload={"values": {}})
            return FakeResponse(payload={"result": {"data": [
                {"REPORT_DATE": "2026-07-24 00:00:00", "IR_RATE": "1.3812"}]}})

        a.http_get = fake_get        # type: ignore[method-assign]
        df = a._shibor(full_history=False)
        assert len(calls) == 2 and "datacenter-web" in calls[1]
        assert list(df.columns) == ["on"]


# --------------------------------------------------------------------------- #
# CGB / policy-bank market-maker quotes
# --------------------------------------------------------------------------- #

class TestCgbMm:
    def test_aggregate_math_and_family_split(self):
        agg = cfu.aggregate_mm_quotes(_MM_RECORDS)
        # 3 of 6 rows are parseable two-way quotes
        assert agg["n_quotes"] == 3.0
        assert agg["n_bonds"] == 3.0
        assert agg["bid_yield_med"] == pytest.approx(1.60)
        assert agg["ask_yield_med"] == pytest.approx(1.56)
        # spreads in bp: 2.0, 9.0, 4.0 -> median 4.0
        assert agg["spread_bp_med"] == pytest.approx(4.0)
        # 国债 family: only the parseable 26附息国债05 quote -> mid (1.70+1.68)/2
        assert agg["cgb_n"] == 1.0
        assert agg["cgb_mid_med"] == pytest.approx(1.69)
        # policy family: 国开 (1.495) + 农发 (1.58) -> median 1.5375
        assert agg["policy_n"] == 2.0
        assert agg["policy_mid_med"] == pytest.approx(1.5375)

    def test_malformed_rows_are_skipped_not_guessed(self):
        assert cfu.split_contra_rate("---") is None
        assert cfu.split_contra_rate("1.7100") is None
        assert cfu.split_contra_rate("abc / 1.5000") is None
        assert cfu.split_contra_rate("1.5 / 1.4 / 1.3") is None
        assert cfu.split_contra_rate(None) is None
        assert cfu.split_contra_rate("1.5400 / 1.4500") == (1.54, 1.45)

    def test_zero_parseable_quotes_raises(self):
        junk = [r for r in _MM_RECORDS if "/" not in str(r["contraRate"])]
        with pytest.raises(ValueError, match="no parseable two-way quotes"):
            cfu.aggregate_mm_quotes(junk)

    def test_leg_dates_by_collection_date(self, monkeypatch):
        a = _adapter(_FRIDAY)
        monkeypatch.setattr(cfu.time, "sleep", lambda *_: None)
        posted: list[dict] = []

        def fake_post(url, **kw):
            posted.append({"url": url, "data": kw.get("data")})
            return FakeResponse(payload=_MM_PAYLOAD)

        a._post = fake_post          # type: ignore[method-assign]
        df = a._cgb_mm(full_history=False)
        assert list(df.index) == [pd.Timestamp(_FRIDAY)]
        assert posted[0]["data"] == {"flag": "1", "lang": "cn"}
        assert df.loc[pd.Timestamp(_FRIDAY), "n_quotes"] == 3.0

    def test_weekend_yields_no_frame(self, monkeypatch):
        a = _adapter(_SATURDAY)
        monkeypatch.setattr(cfu.time, "sleep", lambda *_: None)

        def must_not_call(*_a, **_kw):
            raise AssertionError("no HTTP call may happen on a weekend")

        a._post = must_not_call      # type: ignore[method-assign]
        assert a._cgb_mm(full_history=False) is None

    def test_zero_quotes_propagates_out_of_the_leg(self, monkeypatch):
        a = _adapter(_FRIDAY)
        monkeypatch.setattr(cfu.time, "sleep", lambda *_: None)
        a._post = lambda url, **kw: FakeResponse(payload={"records": []})  # type: ignore[method-assign]
        with pytest.raises(ValueError):
            a._cgb_mm(full_history=False)


# --------------------------------------------------------------------------- #
# per-series isolation
# --------------------------------------------------------------------------- #

class TestFetchIsolation:
    def _stub(self, a, *, repo=True, shibor=True, cgb=True):
        def ok_repo(_fh):
            return cfu.parse_frr_records(_FRRHIS_RECORDS)

        def ok_shibor(_fh):
            return cfu.parse_shibor_values(_IL1_PAYLOAD["values"])

        def ok_cgb(_fh):
            return pd.DataFrame(cfu.aggregate_mm_quotes(_MM_RECORDS),
                                index=[pd.Timestamp(_FRIDAY)])

        def fail(name):
            def _f(_fh):
                raise RuntimeError(f"{name} upstream down")
            return _f

        a._repo_fixings = ok_repo if repo else fail("repo_fixings")   # type: ignore[method-assign]
        a._shibor = ok_shibor if shibor else fail("shibor")           # type: ignore[method-assign]
        a._cgb_mm = ok_cgb if cgb else fail("cgb_mm")                 # type: ignore[method-assign]

    def test_all_three_legs_ok(self):
        a = _adapter()
        self._stub(a)
        frames = a.fetch()
        assert set(frames) == {"repo_fixings", "shibor", "cgb_mm"}

    def test_one_failing_leg_still_returns_the_others(self, caplog):
        a = _adapter()
        self._stub(a, shibor=False)
        with caplog.at_level(logging.WARNING, logger="collectors.china_funding"):
            frames = a.fetch()
        assert set(frames) == {"repo_fixings", "cgb_mm"}
        assert "shibor" in caplog.text

    def test_all_legs_failing_raises_runtimeerror(self):
        a = _adapter()
        self._stub(a, repo=False, shibor=False, cgb=False)
        with pytest.raises(RuntimeError, match="china_funding"):
            a.fetch()

    def test_weekend_skip_is_not_an_error(self):
        a = _adapter(_SATURDAY)
        self._stub(a)
        a._cgb_mm = lambda _fh: None    # type: ignore[method-assign]
        frames = a.fetch()
        assert set(frames) == {"repo_fixings", "shibor"}, "weekend skip drops only its leg"


# --------------------------------------------------------------------------- #
# adapter registration (import-light: no akshare, no heavy deps)
# --------------------------------------------------------------------------- #

def test_w2_adapters_are_registered():
    from scripts.collect import all_adapters
    reg = all_adapters()
    for key, cls_name in (("china_funding", "ChinaFundingAdapter"),
                          ("china_cb", "ChinaCbAdapter"),
                          ("china_fund_issuance", "ChinaFundIssuanceAdapter")):
        assert key in reg, f"{key} missing from all_adapters()"
        assert reg[key].__name__ == cls_name


def test_adapter_contract():
    a = cfu.ChinaFundingAdapter()
    assert a.name == "china_funding" and a.group == "china_funding"
    assert a.stale_after_days == 6
