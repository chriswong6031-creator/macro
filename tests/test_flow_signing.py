"""engine/flow_signing.py + collectors/massive_flatfiles.py — signing math + OCC parsing."""
import numpy as np
import pandas as pd

from collectors import massive_flatfiles as mf
from engine import flow_signing as fs


# --- signing rules --------------------------------------------------------- #
def test_quote_rule_sign():
    # price above mid -> buy(+1); below -> sell(-1); at mid -> tick test
    s = fs.quote_rule_sign([1.2, 0.8, 1.0], [0.9, 0.9, 0.9], [1.1, 1.1, 1.1], [1.0, 1.0, 0.9])
    assert list(s) == [1.0, -1.0, 1.0]   # 1.2>1.0 mid buy; 0.8<1.0 sell; 1.0==mid -> tick 1.0>0.9 buy


def test_tick_rule_sign_carries():
    s = fs.tick_rule_sign([1.0, 1.1, 1.1, 1.05], [np.nan, 1.0, 1.1, 1.1])
    # row0 no prev -> 0; up +1; flat -> carry +1; down -1
    assert list(s) == [0.0, 1.0, 1.0, -1.0]


def test_compare_and_recovery_on_known_sample():
    # build a tiny tbbo-like sample where quote rule is unambiguous
    rows = []
    base = pd.Timestamp("2026-06-18 14:00:00")
    px = [1.0, 1.2, 1.1, 1.3, 1.25, 1.4]      # mostly upticks = buying
    for i, p in enumerate(px):
        rows.append({"ticker": "O:X260717C00100000", "ts": base + pd.Timedelta(seconds=i),
                     "price": p, "size": 10, "bid": p - 0.1, "ask": p + 0.1})
    trades = pd.DataFrame(rows)
    pt = fs.compare_trade_signs(trades)
    assert pt and pt["agreement"] is not None and 0 <= pt["agreement"] <= 1
    rec = fs.minute_sign_recovery(trades, freq="1min")
    assert rec and 0 <= rec["net_sign_recovery"] <= 1
    v = fs.verdict(pt, rec, bar=0.5)
    assert isinstance(v["scored"], bool) and v["note"]


def test_verdict_no_sample():
    v = fs.verdict({}, {})
    assert v["scored"] is False and "no calibration sample" in v["note"]


def test_delta_adjusted_sign():
    # option up +0.50 while underlying up +1.0 at delta 0.5 -> residual 0 (all delta, no flow);
    # option up +0.80 on the same move -> residual +0.30 (buying pressure beyond delta)
    s = fs.delta_adjusted_sign([0.50, 0.80, 0.20], [1.0, 1.0, 1.0], [0.5, 0.5, 0.5])
    assert list(s) == [0.0, 1.0, -1.0]


# --- OCC parsing + cache key ----------------------------------------------- #
def test_parse_occ():
    u, exp, is_call, strike = mf.parse_occ("O:SPY260620C00680000")
    assert u == "SPY" and is_call is True and strike == 680.0
    assert exp.year == 2026 and exp.month == 6 and exp.day == 20
    assert mf.parse_occ("AAPL") is None


def test_add_occ_cols():
    df = pd.DataFrame({"ticker": ["O:NVDA260117P00120000", "O:SPY260620C00680000", "junk"],
                       "volume": [1, 2, 3], "close": [1.0, 2.0, 3.0]})
    out = mf._add_occ_cols(df).dropna(subset=["underlying", "strike"])
    assert set(out["underlying"]) == {"NVDA", "SPY"}
    assert out[out["underlying"] == "NVDA"]["is_call"].iloc[0] == False  # noqa: E712
    assert out[out["underlying"] == "NVDA"]["strike"].iloc[0] == 120.0


def test_uni_tag_is_universe_specific():
    # different universes -> different cache tags (the bug the build hit)
    assert mf._uni_tag(["SPY", "NVDA"]) != mf._uni_tag(["SPY", "NVDA", "AAPL"])
    assert mf._uni_tag(["SPY", "NVDA"]) == mf._uni_tag(["NVDA", "SPY"])   # order-insensitive
    assert mf._uni_tag(None) == "all"


def test_enabled_false_without_creds(monkeypatch):
    for k in ("MASSIVE_S3_ENDPOINT", "MASSIVE_S3_ACCESS_KEY_ID", "MASSIVE_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert mf.enabled() is False
