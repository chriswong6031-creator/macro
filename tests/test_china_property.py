"""China Property & Fiscal display layer tests.

Two surfaces:
  collector  collectors/china_property.py — the net-new transforms: 70-city price
             diffusion (count rising − falling), Sina futures JSONP parse, CGB field
             map. HTTP is monkeypatched so the parsing logic is exercised offline.
  engine     engine/china_property.py — None-safety, the per-component blocks, and the
             descriptive (display-only) property-cycle regime vote. store.read is
             monkeypatched with synthetic frames (no disk).

DISPLAY discipline: there is deliberately NO scored-signal test here — the property
cycle is regime context, never a sized A-share signal (A-shares mean-revert).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_property import ChinaPropertyAdapter  # noqa: E402
from engine import china_property as cp  # noqa: E402


# --------------------------------------------------------------------------- #
# collector — net-new transforms (HTTP monkeypatched)                         #
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, payload=None, text=None):
        self._payload, self.text = payload, text

    def json(self):
        return self._payload


def _house_payload():
    """Two months × 50 cities (≥ the 40-city partial-month guard). Newest month:
    tier-1 北京/上海/广州 rising + 深圳 flat (MoM mean +0.275pp), then 26 more rising,
    4 flat, 16 falling → new diffusion 29 − 16 = +13; second-hand 10 up / 40 down = −30."""
    rows = []

    def add(d, city, seq, sec):
        rows.append({"REPORT_DATE": d, "CITY": city, "FIRST_COMHOUSE_SAME": 98.0,
                     "FIRST_COMHOUSE_SEQUENTIAL": seq, "SECOND_HOUSE_SAME": 96.0,
                     "SECOND_HOUSE_SEQUENTIAL": sec})

    D2 = "2026-02-01 00:00:00"
    for city, seq in [("北京", 100.4), ("上海", 100.6), ("广州", 100.1), ("深圳", 100.0)]:
        add(D2, city, seq, 99.9)                       # tier-1: 3 rising + 1 flat
    for i in range(26):
        add(D2, f"R{i}", 100.2, 100.1 if i < 9 else 99.9)   # 26 rising; 9 of them 2nd-hand-up
    for i in range(4):
        add(D2, f"F{i}", 100.0, 100.1)                 # 4 flat (1 more 2nd-hand-up → 10 total)
    for i in range(16):
        add(D2, f"D{i}", 99.8, 99.9)                   # 16 falling
    for c in [r["CITY"] for r in rows]:                # older month: all 50 flat
        add("2026-01-01 00:00:00", c, 100.0, 100.0)
    return {"result": {"data": rows, "pages": 1}}


def test_home_price_diffusion():
    a = ChinaPropertyAdapter()
    a.http_get = lambda *args, **kw: _Resp(_house_payload())  # type: ignore[assignment]
    df = a._home_price()
    assert list(df.index.strftime("%Y-%m")) == ["2026-01", "2026-02"]   # sorted ascending
    feb = df.loc[df.index[-1]]
    assert feb["new_rising"] == 29 and feb["new_falling"] == 16 and feb["new_flat"] == 5
    assert feb["new_breadth"] == 13
    assert feb["second_breadth"] == -24        # 13 up (9 risers + 4 flats), 37 down
    assert feb["cities"] == 50
    # tier-1 MoM = mean(100.4,100.6,100.1,100.0) − 100 = +0.275 pp
    assert abs(feb["tier1_new_mom"] - 0.275) < 1e-6


def test_futures_jsonp_parse():
    a = ChinaPropertyAdapter()
    body = ('var _x=([{"d":"2026-06-11","o":"3170","h":"3185","l":"3150","c":"3156",'
            '"v":"672854","p":"1641615","s":"3165"},{"d":"2026-06-12","o":"3155","h":"3190",'
            '"l":"3154","c":"3178","v":"768075","p":"1642243","s":"3173"}]);')
    a.http_get = lambda *args, **kw: _Resp(text=body)  # type: ignore[assignment]
    df = a._futures("RB0")
    assert len(df) == 2 and list(df.columns) == ["close", "volume", "hold"]
    assert df["close"].iloc[-1] == 3178.0 and df["hold"].iloc[-1] == 1642243.0


def test_cgb_field_map(monkeypatch):
    monkeypatch.setenv("EASTMONEY_WEB_TOKEN", "test-token-0")  # HTTP mocked; gate only
    a = ChinaPropertyAdapter()
    payload = {"result": {"pages": 1, "data": [
        {"SOLAR_DATE": "2026-06-12 00:00:00", "EMM00588704": 1.29, "EMM00166462": 1.48,
         "EMM00166466": 1.74, "EMM00166469": 2.22, "EMM01276014": 0.45}]}}
    a.http_get = lambda *args, **kw: _Resp(payload)  # type: ignore[assignment]
    df = a._cgb()
    assert df["cgb_10y"].iloc[-1] == 1.74 and df["cgb_2y"].iloc[-1] == 1.29
    assert df["cgb_10y2y"].iloc[-1] == 0.45


# --------------------------------------------------------------------------- #
# engine — blocks + regime vote (store monkeypatched)                         #
# --------------------------------------------------------------------------- #
def _synthetic_store():
    months = pd.date_range("2011-01-01", periods=184, freq="MS")
    days = pd.bdate_range("2014-01-01", periods=1400)

    # home_price: breadth ramps from −58 to −35 over the last 7 months (improving)
    nb = np.full(184, 5.0)
    nb[-7:] = np.linspace(-58, -35, 7)
    hp = pd.DataFrame({
        "new_rising": 14, "new_falling": 49, "new_flat": 7, "new_breadth": nb,
        "second_breadth": nb - 7, "cities": 70,
        "tier1_new_mom": 0.1, "tier1_new_yoy": -2.0}, index=months)

    climate = pd.DataFrame({
        "climate": np.linspace(101, 91.45, 184),
        "climate_chg": np.r_[np.zeros(183), [-0.48]]}, index=months)

    # constant futures → trailing-return z ≈ 0, so the construction leg stays neutral
    # (matches the live read: rebar/iron soft, not a clean demand signal)
    rebar = pd.DataFrame({"close": 3178.0, "volume": 1.0, "hold": 1.0}, index=days)
    iron = pd.DataFrame({"close": 764.0, "volume": 1.0, "hold": 1.0}, index=days)

    cgb = pd.DataFrame({"cgb_2y": 1.29, "cgb_5y": 1.48,
                        "cgb_10y": np.linspace(2.6, 1.743, len(days)),
                        "cgb_30y": 2.22, "cgb_10y2y": 0.449}, index=days)

    etf = pd.DataFrame({"close": np.r_[np.linspace(1, 1.83, 700), np.linspace(1.83, 1.277, 700)],
                        "volume": 1.0}, index=pd.bdate_range("2018-01-01", periods=1400))

    table = {("china_property", "home_price"): hp, ("china_property", "climate"): climate,
             ("china_property", "rebar"): rebar, ("china_property", "iron_ore"): iron,
             ("china_property", "cgb"): cgb, ("china", "512200.SS"): etf}
    return lambda group, name: table.get((group, name))


def test_blocks_compute(monkeypatch):
    monkeypatch.setattr(cp.store, "read", _synthetic_store())
    b = cp._breadth_block()
    assert b["new"] == -35 and b["trend_6m"] == 23 and b["second"] == -42
    assert b["chart"]["dates"] and len(b["chart"]["vals"]) == len(b["chart"]["dates"])

    c = cp._climate_block()
    assert c["level"] == 91.45 and c["trend"] == "falling"

    k = cp._construction_block()
    assert k["rebar"] == 3178.0 and k["iron_ore"] == 764.0
    assert k["demand_z"] == 0.0                      # flat futures → neutral demand leg

    g = cp._cgb_block()
    assert g["y10"] == 1.743 and g["chg_6m"] < 0 and g["slope"] == 0.449

    e = cp._prop_etf_block()
    assert e["drawdown"] < 0 and abs(e["drawdown"] - (-30.2)) < 1.0   # ~−30% from 1.83 ATH


def test_property_view_and_context(monkeypatch):
    monkeypatch.setattr(cp.store, "read", _synthetic_store())
    v = cp.property_view()
    r = v["regime"]
    # breadth −35 (−1) + climate falling (−1) + construction neutral (0) = pulse −2
    assert r["pulse"] == -2 and "Contraction" in r["label_en"]
    assert "easing" in r["label_en"]                 # breadth 6-mo trend +23 ≥ 12 → easing nuance
    assert r["tone"] == "neg" and len(r["drivers"]) == 3

    ctx = cp.regime_context()
    assert ctx["home_price_breadth"] == -35 and ctx["cgb_10y"] == 1.743
    assert ctx["regime"] == r["label_en"]
    assert "context only" in ctx["note"]             # honest display-only disclaimer


# the regime label is a descriptive DISPLAY vote — test it deterministically as a
# pure function (no z-score wrangling), each leg ∈ {-1,0,+1}, pulse clamped to [-3,3].
def test_regime_vote_pure():
    contraction = cp._regime(
        {"new": -35, "rising": 14, "falling": 49, "trend_6m": 23},
        {"chg": -0.48, "level": 91.5, "trend": "falling"}, {"demand_z": -0.15})
    assert contraction["pulse"] == -2 and contraction["label_en"] == "Contraction (easing)"

    recovery = cp._regime(
        {"new": 35, "rising": 49, "falling": 14, "trend_6m": 15},
        {"chg": 0.5, "level": 98, "trend": "rising"}, {"demand_z": 0.4})
    assert recovery["pulse"] == 3 and recovery["tone"] == "pos"
    assert recovery["label_en"] == "Broad recovery"

    rolling = cp._regime(
        {"new": 3, "rising": 36, "falling": 33, "trend_6m": -15},
        {"chg": 0.0, "level": 99, "trend": "flat"}, {"demand_z": 0.1})
    assert rolling["pulse"] == 1 and "rolling over" in rolling["label_en"]

    empty = cp._regime(None, None, None)
    assert empty["pulse"] == 0 and empty["label_en"] == "Stabilizing" and empty["drivers"] == []


def test_none_safe(monkeypatch):
    monkeypatch.setattr(cp.store, "read", lambda g, n: None)
    assert cp.property_view() is None
    assert cp.regime_context() is None
    assert cp._breadth_block() is None and cp._cgb_block() is None
