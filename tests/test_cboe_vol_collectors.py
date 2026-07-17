"""collectors/cboe_indices.CboeVvixAdapter + collectors/cboe_vix_futures (the full
M1..M6 VX curve) — the collect-first data infra for engine/vol_regime's VVIX leg and the
future curve-slope/carry leg. Pure parse/shape tests; no network (http_get is stubbed)."""
import datetime as dt

import pandas as pd
import pytest

from collectors.cboe_indices import CboeVvixAdapter
from collectors.cboe_vix_futures import CboeVixFuturesAdapter


class _Resp:
    """Minimal stand-in for a requests.Response (the bits the adapters read)."""
    def __init__(self, text: str, ctype: str = "text/csv"):
        self.text = text
        self.headers = {"Content-Type": ctype}


# --------------------------------------------------------------------------- VVIX
VVIX_CSV = "DATE,VVIX\n03/06/2006,71.730000\n06/17/2026,94.530000\n06/18/2026,88.430000\n"


def test_vvix_parses_full_history(monkeypatch):
    a = CboeVvixAdapter()
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp(VVIX_CSV))
    out = a.fetch()
    assert "vvix" in out
    df = out["vvix"]
    assert list(df.columns) == ["vvix"]
    # full history is returned in ONE fetch (backfill + accrual in one shot)
    assert str(df.index.min().date()) == "2006-03-06"
    assert df.loc["2026-06-18", "vvix"] == pytest.approx(88.43)


def test_vvix_rejects_unexpected_response(monkeypatch):
    a = CboeVvixAdapter()
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp("oops,not,vvix\n1,2,3\n"))
    with pytest.raises(ValueError):
        a.fetch()


# ---------------------------------------------------------------------- VX curve
# The settlement CSV mixes WEEKLY VX (week-number-prefixed symbols, e.g. VX25/M6) with the
# standard MONTHLY contracts (bare VX/{Mon}{Yr}). VX26/N6 (weekly, 07-01) deliberately
# precedes the monthly VX/N6 (07-22) to prove the curve picks the MONTHLY as M1, not the
# nearer weekly. ZB is a non-VX product that must be dropped.
SETTLE_CSV = (
    "Product,Symbol,Expiration Date,Price\n"
    "VX,VX/M6,2026-06-17,16.20\n"       # monthly, already expired vs 06-18
    "VX,VX25/M6,2026-06-24,19.255\n"    # WEEKLY -> front of the sanitizer, NOT a curve point
    "VX,VX26/N6,2026-07-01,19.255\n"    # WEEKLY before the July monthly
    "VX,VX/N6,2026-07-22,19.255\n"      # monthly M1
    "VX,VX/Q6,2026-08-19,20.31\n"       # monthly M2
    "VX,VX/U6,2026-09-16,21.05\n"
    "VX,VX/V6,2026-10-21,21.79\n"
    "VX,VX/X6,2026-11-18,22.00\n"
    "VX,VX/Z6,2026-12-16,22.10\n"       # monthly M6
    "ZB,ZB/M6,2026-06-20,100.0\n"       # non-VX -> dropped
)
D = dt.date(2026, 6, 18)


def _rows(monkeypatch):
    a = CboeVixFuturesAdapter()
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp(SETTLE_CSV))
    return a, a._vx_rows(D)


def test_vx_rows_keeps_vx_and_flags_monthlies(monkeypatch):
    _, rows = _rows(monkeypatch)
    assert rows is not None and len(rows) == 9            # ZB dropped
    monthly = rows.set_index("Symbol")["monthly"].to_dict()
    assert monthly["VX/M6"] and monthly["VX/N6"]          # bare VX/ = monthly
    assert not monthly["VX25/M6"] and not monthly["VX26/N6"]  # week-prefixed = weekly


def test_vx_front_is_nearest_contract_unchanged(monkeypatch):
    """front_settle = nearest non-expired contract (weekly here) — the sanitizer's read,
    preserved exactly from the single-series collector."""
    a, rows = _rows(monkeypatch)
    front = a._front(rows, D)
    assert front["front_settle"] == pytest.approx(19.255)
    assert front["days_to_expiry"] == 6                  # 06-18 -> 06-24 weekly


def test_vx_curve_is_monthly_ladder(monkeypatch):
    a, rows = _rows(monkeypatch)
    curve = a._curve(rows, D)
    # M1 must be the MONTHLY VX/N6 (07-22, 34d out), NOT the earlier weekly VX26/N6 (07-01)
    assert curve["m1_settle"] == pytest.approx(19.255)
    assert curve["m1_dte"] == 34
    assert curve["m2_settle"] == pytest.approx(20.31)
    assert curve["m6_settle"] == pytest.approx(22.10)
    # ascending DTEs = a proper ~monthly ladder (weeklies would collapse the spacing)
    dtes = [curve[f"m{i}_dte"] for i in range(1, 7)]
    assert dtes == sorted(dtes) and dtes[1] - dtes[0] > 20


def test_vx_curve_none_without_monthlies():
    a = CboeVixFuturesAdapter()
    rows = pd.DataFrame({"exp": [pd.Timestamp("2026-07-01")], "px": [19.0], "monthly": [False]})
    assert a._curve(rows, D) is None


def test_vx_fetch_raises_when_nothing_fetched(monkeypatch):
    a = CboeVixFuturesAdapter()
    a.cfg = {"vix_request_pace_s": 0}                     # no sleep between the miss probes
    monkeypatch.setattr(a, "http_get", lambda *args, **kw: _Resp("<html/>", ctype="text/html"))
    with pytest.raises(ValueError):
        a.fetch()


# ------------------------------------------------------- VSB W1 cor/vol family
from collectors.cboe_indices import (  # noqa: E402
    COR_VOL_SERIES, CboeCorVolAdapter, _parse_history, check_cor_vol_freshness,
)

COR_CSV = ("DATE,OPEN,HIGH,LOW,CLOSE\n"
           "01/03/2006,23.500000,23.500000,23.500000,23.500000\n"
           "07/13/2026,4.350000,5.940000,4.250000,5.510000\n")
DSPX_CSV = "DATE,DSPX\n06/19/2014,17.810000\n07/13/2026,46.870000\n"


def test_cor_vol_parses_ohlc_shape():
    df = _parse_history(COR_CSV, "cor1m")
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert str(df.index.min().date()) == "2006-01-03"    # full history in ONE fetch
    assert df.loc["2026-07-13", "close"] == pytest.approx(5.51)


def test_cor_vol_parses_single_value_shape():
    df = _parse_history(DSPX_CSV, "dspx")
    # the value column is stored as `close` regardless of the CDN's header name,
    # so every cboe cor/vol parquet carries the same primary-column contract
    assert list(df.columns) == ["close"]
    assert df.loc["2026-07-13", "close"] == pytest.approx(46.87)


def test_cor_vol_rejects_unexpected_response():
    with pytest.raises(ValueError):
        _parse_history("oops,not,cboe\n1,2,3\n", "cor1m")
    with pytest.raises(ValueError):
        _parse_history("DATE,A,B,C\n01/03/2006,1,2,3\n", "cor1m")   # neither OHLC nor single


def test_cor_vol_fetch_is_strict_per_series(monkeypatch):
    """One dead series must fail the WHOLE adapter (loud, breaker-visible) — never a
    partial frames dict that quietly persists only the survivors."""
    a = CboeCorVolAdapter()

    def _get(url, **kw):
        if "COR3M" in url:
            raise RuntimeError("HTTP 404")
        return _Resp(COR_CSV)
    monkeypatch.setattr(a, "http_get", _get)
    with pytest.raises(RuntimeError):
        a.fetch()


def _fake_store(monkeypatch, tmp_path, frames: dict):
    """Point the parquet store at tmp_path and seed data/cboe/<name>.parquet frames.

    Also redirects config.ROOT: store.write_status/read_status resolve
    data/run_status.json off ROOT (no root= param), and the freshness
    tripwire writes that surface — unredirected it dirties the REAL
    data/run_status.json."""
    from lib import config as _config
    _config.load()  # warm the lru cache before ROOT is patched
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)
    (tmp_path / "cboe").mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_parquet(tmp_path / "cboe" / f"{name}.parquet")


def test_cor_vol_freshness_clean_store(monkeypatch, tmp_path):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 13))
    idx = pd.date_range(end="2026-07-13", periods=150, freq="B")
    good = pd.DataFrame({"close": range(150)}, index=idx)
    _fake_store(monkeypatch, tmp_path, {s: good for s in COR_VOL_SERIES})
    assert check_cor_vol_freshness() == []


def test_cor_vol_freshness_flags_stub_stale_and_missing(monkeypatch, tmp_path):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 13))
    stub = pd.DataFrame({"close": [0.0]}, index=pd.DatetimeIndex(["2026-05-27"]))  # the ^COR1M mode
    stale_idx = pd.date_range(end="2026-06-30", periods=150, freq="B")             # 8+ sessions behind
    stale = pd.DataFrame({"close": range(150)}, index=stale_idx)
    fresh_idx = pd.date_range(end="2026-07-13", periods=150, freq="B")
    fresh = pd.DataFrame({"close": range(150)}, index=fresh_idx)
    _fake_store(monkeypatch, tmp_path,
                {"cor1m": stub, "cor3m": stale, "dspx": fresh, "vix1d": fresh})
    # vixeq deliberately absent from the store entirely
    problems = {p["series"]: p["reason"] for p in check_cor_vol_freshness()}
    assert set(problems) == {"cor1m", "cor3m", "vixeq"}
    assert "row floor" in problems["cor1m"]
    assert "stale" in problems["cor3m"]
    assert "missing" in problems["vixeq"]
    # the tripwire rides the existing run_status stale_series health surface
    from lib import store as _store
    surfaced = {e["series"] for e in _store.read_status().get("stale_series", [])}
    assert {"cor1m", "cor3m", "vixeq"} <= surfaced
