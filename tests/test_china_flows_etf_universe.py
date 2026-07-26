"""Fixture-based tests for the W2-widened etf_shares leg of collectors/china_flows.py.

No network: every test monkeypatches ``adapter.http_get`` and hands back FakeResponse
objects (``.json()`` for the SSE/EastMoney JSON legs, ``.content`` for the SZSE xlsx,
which is BUILT here with openpyxl rather than checked in as a binary fixture).

What is pinned:
  * unit continuity across the old->new seam — SSE TOT_VOL is 万份 and needs x10000,
    SZSE 当前规模(份) is already raw 份.  ``sh_510300 == 24_380_587_700.0`` exactly.
  * the SSE walk-back: an unpublished STAT_DATE returns an empty ``result`` list, the
    next candidate weekday is tried, and successive calls are 1.0s apart (<=1 req/s).
  * the degrade ladder: one exchange down -> the other alone; both down -> the legacy
    21-code EastMoney basket; all three down -> ValueError for fetch() to isolate.
  * the <_MIN_UNIVERSE_COLS partial-pull guard.
  * the consumer contract: engine/china_participation.py::_load_etf_flows still computes
    a non-null etf_share_chg across a synthetic legacy-rows + wide-rows seam, unedited.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import pytest

from collectors import china_flows as CF


# --------------------------------------------------------------------------- #
# Fake HTTP plumbing
# --------------------------------------------------------------------------- #
class FakeResponse:
    """Minimal stand-in for requests.Response (json body OR raw bytes)."""

    def __init__(self, payload: dict | None = None, content: bytes = b"",
                 status_code: int = 200) -> None:
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("FakeResponse has no JSON body")
        return self._payload


class _Router:
    """Dispatch fake http_get calls by URL fragment; records every call."""

    def __init__(self, *legs) -> None:
        # legs: (url_fragment, handler(params) -> FakeResponse | raises)
        self._legs = legs
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: dict | None = None, **kw) -> FakeResponse:
        self.calls.append((url, dict(params or {})))
        for fragment, handler in self._legs:
            if fragment in url:
                return handler(dict(params or {}))
        raise AssertionError(f"unexpected URL in test: {url}")

    def urls(self) -> list[str]:
        return [u for u, _ in self.calls]

    def sse_dates(self) -> list[str]:
        return [p.get("STAT_DATE") for u, p in self.calls if "commonQuery" in u]


def _raises(exc: Exception):
    def _handler(_params):
        raise exc
    return _handler


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #
_SSE_ROWS = [
    # (SEC_CODE, SEC_NAME, TOT_VOL in 万份 — verbatim string shapes from the live API)
    ("510300", "300ETF", "2438058.77"),
    ("510050", "50ETF", "744006.68"),
]

# 基金类别 values seen live: ETF / LOF / 不动产基金.  Only ETF is in contract.
_SZSE_ROWS = [
    ("159915", "创业板ETF易方达", "ETF", "2011-12-09", "16,653,454,936"),
    ("159919", "沪深300ETF嘉实", "ETF", "2012-05-28", "6,244,416,676"),
    ("160105", "南方高增LOF", "LOF", "2009-06-10", "1,234,567,890"),
]


def _sse_payload(stat_date: str, rows=_SSE_ROWS) -> dict:
    return {
        "isPagination": True,
        "pageHelp": {"pageSize": 10000, "total": len(rows)},
        "result": [
            {"STAT_DATE": stat_date, "ETF_TYPE": "跨市", "SEC_CODE": code,
             "NUM": "1", "SEC_NAME": name, "TOT_VOL": vol}
            for code, name, vol in rows
        ],
    }


def _szse_xlsx(rows=_SZSE_ROWS) -> bytes:
    """Build the SZSE fund report xlsx in-test (no checked-in binary fixture)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["基金代码", "基金简称", "基金类别", "上市日期", "当前规模(份)"])
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _em_payload(codes=("510300", "159915")) -> dict:
    """Legacy RPT_FUND_ETFLIST shape: nested result.data with raw-份 DEC_TOTALSHARE."""
    return {"result": {"data": [
        {"SECURITY_CODE": c, "DEC_TOTALSHARE": 1_000_000_000 + i}
        for i, c in enumerate(codes)
    ]}}


def _adapter(monkeypatch, router: _Router) -> CF.ChinaFlowsAdapter:
    """Adapter with a stubbed http_get.  Built via __new__ so the test never reads
    config/synapse.yml (owned by other lanes); etf_codes is set explicitly because the
    EastMoney fallback needs it."""
    a = CF.ChinaFlowsAdapter.__new__(CF.ChinaFlowsAdapter)
    a.name = CF.ChinaFlowsAdapter.name
    a.group = CF.ChinaFlowsAdapter.group
    a.etf_codes = ["159915", "510300"]
    monkeypatch.setattr(a, "http_get", router)
    return a


@pytest.fixture
def no_sleep(monkeypatch):
    """Record every collector sleep instead of taking it."""
    slept: list[float] = []
    monkeypatch.setattr(CF.time, "sleep", lambda s: slept.append(s))
    return slept


@pytest.fixture
def fixed_today(monkeypatch):
    """Pin exchange-local 'today' so STAT_DATE candidates are deterministic."""
    def _set(d: date) -> None:
        monkeypatch.setattr(CF, "_today_cn", lambda: d)
    return _set


# --------------------------------------------------------------------------- #
# Happy path: both exchanges, merged into one wide row
# --------------------------------------------------------------------------- #
def test_happy_path_merges_both_exchanges(monkeypatch, no_sleep, fixed_today):
    """SSE (x10000) + SZSE (raw) union into one row dated at the official STAT_DATE."""
    fixed_today(date(2026, 7, 24))
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 3)
    router = _Router(
        ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
        ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())),
    )
    df = _adapter(monkeypatch, router)._etf_shares(False)

    assert len(df) == 1
    assert df.index[0] == pd.Timestamp("2026-07-24")

    # ---- the unit-continuity pins (SSE 万份 x 10000 == the stored legacy basis) ----
    assert df.iloc[0]["sh_510300"] == 24_380_587_700.0
    assert df.iloc[0]["sh_510050"] == 7_440_066_800.0
    # ---- SZSE values are already raw 份: comma-strip only, no scaling ----
    assert df.iloc[0]["sh_159915"] == 16_653_454_936.0
    assert df.iloc[0]["sh_159919"] == 6_244_416_676.0

    # LOF rows are out of contract; only the two SSE + two SZSE ETFs survive.
    assert "sh_160105" not in df.columns
    assert set(df.columns) == {"sh_510300", "sh_510050", "sh_159915", "sh_159919"}
    assert len(df.columns) == 4

    # One SSE call (first candidate published) + one SZSE call, no throttle sleep needed.
    assert router.sse_dates() == ["2026-07-24"]
    assert no_sleep == []


def test_column_names_and_dtype_match_the_store_contract(monkeypatch, no_sleep, fixed_today):
    """Frame stays a wide date-indexed row of float sh_<code> columns (store contract)."""
    fixed_today(date(2026, 7, 24))
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 3)
    router = _Router(
        ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
        ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())),
    )
    df = _adapter(monkeypatch, router)._etf_shares(False)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert all(c.startswith("sh_") and c[3:].isdigit() for c in df.columns)
    assert all(str(dt).startswith("float") for dt in df.dtypes.astype(str))


def test_sse_x10000_leaves_no_binary_float_residue(monkeypatch, no_sleep, fixed_today):
    """744006.68 * 1e4 is 7440066800.000001 in raw binary float — must land on the
    integer 份 count, or the downstream diff() invents phantom 1-unit creations."""
    fixed_today(date(2026, 7, 24))
    router = _Router(
        ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
        ("ShowReport", _raises(RuntimeError("szse down"))),
    )
    row, as_of = _adapter(monkeypatch, router)._etf_shares_sse()
    assert row["sh_510050"] == 7_440_066_800.0
    assert row["sh_510050"].is_integer()
    assert as_of == pd.Timestamp("2026-07-24")


def test_szse_excludes_lof_and_reit_rows(monkeypatch, no_sleep):
    """基金类别 filter keeps ETF only — LOFs and 不动产基金 (REITs) are out of contract."""
    rows = list(_SZSE_ROWS) + [("180101", "某REIT", "不动产基金", "2021-06-21", "500,000,000")]
    router = _Router(("ShowReport", lambda p: FakeResponse(content=_szse_xlsx(rows))))
    out = _adapter(monkeypatch, router)._etf_shares_szse()
    assert set(out) == {"sh_159915", "sh_159919"}


def test_full_history_matches_nightly(monkeypatch, no_sleep, fixed_today):
    """full_history is a documented no-op: the exchanges publish daily snapshots only,
    so depth accrues forward one session at a time (CN-SYS accrual clock)."""
    fixed_today(date(2026, 7, 24))
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 3)

    def _build(flag: bool) -> pd.DataFrame:
        router = _Router(
            ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
            ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())),
        )
        return _adapter(monkeypatch, router)._etf_shares(flag)

    pd.testing.assert_frame_equal(_build(True), _build(False))


# --------------------------------------------------------------------------- #
# SSE walk-back + throttle
# --------------------------------------------------------------------------- #
def test_walkback_skips_unpublished_stat_date(monkeypatch, no_sleep, fixed_today):
    """An empty ``result`` list (non-trading / not-yet-published) advances to the next
    candidate weekday, one 1.0s sleep between successive commonQuery calls."""
    fixed_today(date(2026, 7, 24))          # Friday
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 3)

    def _sse(params):
        if params["STAT_DATE"] == "2026-07-24":
            return FakeResponse({"result": []})     # not published yet
        return FakeResponse(_sse_payload(params["STAT_DATE"]))

    router = _Router(("commonQuery", _sse),
                     ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())))
    df = _adapter(monkeypatch, router)._etf_shares(False)

    assert router.sse_dates() == ["2026-07-24", "2026-07-23"]
    assert no_sleep == [1.0]                 # exactly one inter-call throttle
    assert df.index[0] == pd.Timestamp("2026-07-23")


def test_walkback_candidates_skip_the_weekend(monkeypatch, no_sleep, fixed_today):
    """From a Saturday the candidates start at Friday and never include Sat/Sun."""
    fixed_today(date(2026, 7, 25))          # Saturday
    router = _Router(("commonQuery", lambda p: FakeResponse({"result": []})))
    a = _adapter(monkeypatch, router)
    assert a._cn_weekdays_back(4) == [date(2026, 7, 24), date(2026, 7, 23),
                                      date(2026, 7, 22), date(2026, 7, 21)]


def test_walkback_is_today_inclusive(monkeypatch, fixed_today):
    """Today itself is candidate #1 — the asia lane runs after the A-share close, so a
    yesterday-first walk would permanently lag the store one session."""
    fixed_today(date(2026, 7, 23))          # Thursday
    router = _Router(("commonQuery", lambda p: FakeResponse({"result": []})))
    assert _adapter(monkeypatch, router)._cn_weekdays_back(1) == [date(2026, 7, 23)]


def test_worst_case_call_budget_is_six(monkeypatch, no_sleep, fixed_today):
    """Nightly request budget: <=4 SSE walk-back + 1 SZSE + 1 EastMoney fallback."""
    fixed_today(date(2026, 7, 24))
    router = _Router(
        ("commonQuery", lambda p: FakeResponse({"result": []})),   # never published
        ("ShowReport", _raises(RuntimeError("szse down"))),
        ("datacenter-web", lambda p: FakeResponse(_em_payload())),
    )
    _adapter(monkeypatch, router)._etf_shares(False)

    assert len(router.calls) == 6
    assert len(router.sse_dates()) == CF._SSE_WALKBACK_DAYS == 4
    assert no_sleep == [1.0, 1.0, 1.0]      # only BETWEEN the 4 SSE calls


# --------------------------------------------------------------------------- #
# Degrade ladder
# --------------------------------------------------------------------------- #
def test_sse_down_ships_szse_alone(monkeypatch, no_sleep, fixed_today, caplog):
    """One exchange down is a logged gap, not a failure: the other leg still ships,
    stamped at the most recent completed CN weekday (no STAT_DATE to borrow)."""
    fixed_today(date(2026, 7, 24))
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 2)
    router = _Router(
        ("commonQuery", _raises(RuntimeError("sse tls reset"))),
        ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())),
    )
    with caplog.at_level("INFO", logger="collectors.china_flows"):
        df = _adapter(monkeypatch, router)._etf_shares(False)

    assert set(df.columns) == {"sh_159915", "sh_159919"}
    assert df.index[0] == pd.Timestamp("2026-07-24")
    assert "SSE leg unavailable" in caplog.text
    assert "Shanghai funds gap" in caplog.text


def test_szse_down_ships_sse_alone(monkeypatch, no_sleep, fixed_today, caplog):
    fixed_today(date(2026, 7, 24))
    monkeypatch.setattr(CF, "_MIN_UNIVERSE_COLS", 2)
    router = _Router(
        ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
        ("ShowReport", _raises(RuntimeError("szse tls reset"))),
    )
    with caplog.at_level("INFO", logger="collectors.china_flows"):
        df = _adapter(monkeypatch, router)._etf_shares(False)

    assert set(df.columns) == {"sh_510300", "sh_510050"}
    assert df.index[0] == pd.Timestamp("2026-07-24")
    assert "SZSE leg unavailable" in caplog.text
    assert "Shenzhen funds gap" in caplog.text


def test_both_exchanges_down_uses_eastmoney_fallback(monkeypatch, no_sleep, fixed_today):
    """Both official legs down -> the legacy 21-code basket, legacy-shaped and stamped
    at the COLLECTION date exactly as before W2 (CNH-R2 documented proxy fallback)."""
    fixed_today(date(2026, 7, 24))
    router = _Router(
        ("commonQuery", _raises(RuntimeError("sse down"))),
        ("ShowReport", _raises(RuntimeError("szse down"))),
        ("datacenter-web", lambda p: FakeResponse(_em_payload())),
    )
    df = _adapter(monkeypatch, router)._etf_shares(False)

    assert list(df.columns) == ["sh_510300", "sh_159915"]
    assert df.iloc[0]["sh_510300"] == 1_000_000_000
    assert df.index[0] == pd.Timestamp(date.today())


def test_partial_universe_falls_through_to_fallback(monkeypatch, no_sleep, fixed_today, caplog):
    """A thin merged row (< _MIN_UNIVERSE_COLS, production default 200) is treated as a
    broken pull — a partial universe would poison the per-fund z-scores with NaN churn."""
    fixed_today(date(2026, 7, 24))
    assert CF._MIN_UNIVERSE_COLS == 200          # production default, not relaxed here
    router = _Router(
        ("commonQuery", lambda p: FakeResponse(_sse_payload(p["STAT_DATE"]))),
        ("ShowReport", lambda p: FakeResponse(content=_szse_xlsx())),
        ("datacenter-web", lambda p: FakeResponse(_em_payload())),
    )
    with caplog.at_level("WARNING", logger="collectors.china_flows"):
        df = _adapter(monkeypatch, router)._etf_shares(False)

    assert list(df.columns) == ["sh_510300", "sh_159915"]     # the fallback frame
    assert "only 4 funds resolved" in caplog.text


def test_all_three_legs_down_raises_value_error(monkeypatch, no_sleep, fixed_today):
    """fetch()'s per-series isolation needs a raise, and it must be a ValueError."""
    fixed_today(date(2026, 7, 24))
    router = _Router(
        ("commonQuery", _raises(RuntimeError("sse down"))),
        ("ShowReport", _raises(RuntimeError("szse down"))),
        ("datacenter-web", _raises(RuntimeError("eastmoney down"))),
    )
    with pytest.raises(ValueError, match="all failed"):
        _adapter(monkeypatch, router)._etf_shares(False)


def test_empty_eastmoney_result_raises_value_error(monkeypatch, no_sleep, fixed_today):
    fixed_today(date(2026, 7, 24))
    router = _Router(
        ("commonQuery", _raises(RuntimeError("sse down"))),
        ("ShowReport", _raises(RuntimeError("szse down"))),
        ("datacenter-web", lambda p: FakeResponse({"result": {"data": []}})),
    )
    with pytest.raises(ValueError):
        _adapter(monkeypatch, router)._etf_shares(False)


def test_szse_xlsx_missing_column_is_a_leg_failure(monkeypatch, no_sleep):
    """A silently reshaped xlsx must fail the leg loudly, not ship an empty row."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["基金代码", "基金简称", "上市日期"])       # no 基金类别 / 当前规模(份)
    buf = io.BytesIO()
    wb.save(buf)
    router = _Router(("ShowReport", lambda p: FakeResponse(content=buf.getvalue())))
    with pytest.raises(ValueError, match="missing columns"):
        _adapter(monkeypatch, router)._etf_shares_szse()


# --------------------------------------------------------------------------- #
# fetch() isolation is untouched
# --------------------------------------------------------------------------- #
def test_fetch_isolates_a_dead_etf_leg(monkeypatch, no_sleep):
    """A raising etf_shares leg must not take ah_premium/limit_breadth down with it."""
    a = CF.ChinaFlowsAdapter.__new__(CF.ChinaFlowsAdapter)
    a.name, a.group, a.etf_codes = "china_flows", "china_flows", ["510300"]
    monkeypatch.setattr(a, "_ah_premium",
                        lambda fh: pd.DataFrame({"hsahp": [131.0]},
                                                index=[pd.Timestamp("2026-07-24")]))
    monkeypatch.setattr(a, "_limit_breadth",
                        lambda fh: pd.DataFrame({"zt": [42]},
                                                index=[pd.Timestamp("2026-07-24")]))
    monkeypatch.setattr(a, "_etf_shares", lambda fh: (_ for _ in ()).throw(
        ValueError("etf_shares: SSE, SZSE and the EastMoney fallback basket all failed")))

    frames = a.fetch(full_history=False)
    assert set(frames) == {"ah_premium", "limit_breadth"}


# --------------------------------------------------------------------------- #
# Engine seam contract (engine/china_participation.py must stay unedited)
# --------------------------------------------------------------------------- #
_LEGACY_CODES = [
    "sh_159915", "sh_159928", "sh_159992", "sh_510050", "sh_510300", "sh_510500",
    "sh_512170", "sh_512200", "sh_512400", "sh_512660", "sh_512690", "sh_512760",
    "sh_512800", "sh_512880", "sh_512980", "sh_515000", "sh_515030", "sh_515220",
    "sh_515250", "sh_515790", "sh_588000",
]


def _seam_store() -> pd.DataFrame:
    """3 legacy rows (21 cols, COLLECTION-dated) + 3 wide rows (STAT_DATE-dated) merged
    the way lib.store.upsert merges them (new.combine_first(old)).  Overlapping codes
    keep the same sh_ names, so a legacy fund's history runs straight through the seam."""
    legacy_idx = pd.to_datetime(["2026-07-20", "2026-07-21", "2026-07-22"])
    new_idx = pd.to_datetime(["2026-07-22", "2026-07-23", "2026-07-24"])
    # newly added funds live in a code space disjoint from the 21 legacy codes
    wide_codes = _LEGACY_CODES + [f"sh_5199{i:02d}" for i in range(60)]

    def _vals(seed: int, n: int) -> list[float]:
        # deliberately UNEVEN diffs — constant diffs give std 0 and a NaN z-score
        return [1e10 + seed * 1e7 + (k ** 2) * 3.7e6 for k in range(n)]

    old = pd.DataFrame({c: _vals(i, 3) for i, c in enumerate(_LEGACY_CODES)},
                       index=legacy_idx)
    new = pd.DataFrame({c: _vals(i + 7, 3) for i, c in enumerate(wide_codes)},
                       index=new_idx)
    return new.combine_first(old).sort_index()


def test_engine_seam_keeps_etf_share_chg_non_null(tmp_path, monkeypatch):
    """_load_efs_flows (diff -> 5d per-fund z -> cross-fund median) must still produce a
    non-null etf_share_chg across the old->new seam with NO engine edit."""
    import engine.china_participation as cp

    store = _seam_store()
    (tmp_path / "china_flows").mkdir(parents=True)
    store.to_parquet(tmp_path / "china_flows" / "etf_shares.parquet")
    monkeypatch.setattr(cp, "_ROOT", str(tmp_path))

    series, gaps = cp._load_etf_flows()

    assert isinstance(series, pd.Series)
    assert series.name == "etf_share_chg"
    assert series.notna().sum() >= 1, f"all-null across the seam; gaps={gaps}"
    assert series.abs().max() < 10, "z-scale expected, not a raw cross-fund sum"
    # the seam row itself (first wide row) must carry a value from the legacy funds
    assert pd.notna(series.loc[pd.Timestamp("2026-07-23")])


def test_engine_seam_store_shape_is_wide_and_sparse(tmp_path):
    """Sanity on the fixture itself: legacy rows are NaN in the newly added columns and
    the 21 legacy codes are continuous — that is what keeps the median non-null."""
    store = _seam_store()
    assert len(store.columns) == 81                     # 21 legacy + 60 newly added
    assert pd.isna(store.loc[pd.Timestamp("2026-07-20"), "sh_519900"])
    assert store[_LEGACY_CODES].notna().all().all()


# --------------------------------------------------------------------------- #
# __init__ still feeds the fallback
# --------------------------------------------------------------------------- #
def test_init_still_builds_bare_digit_etf_codes():
    """The EastMoney fallback needs self.etf_codes, so __init__ keeps building it."""
    codes = CF.ChinaFlowsAdapter().etf_codes
    assert codes, "etf_codes must be non-empty for the fallback filter"
    assert codes == sorted(set(codes))
    assert all(c.isdigit() and "." not in c for c in codes)
