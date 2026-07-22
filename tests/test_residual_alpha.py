"""Sector-neutral residual-momentum engine tests (engine/residual_alpha.py).
Synthetic-universe checks (no disk needed) on the core claims — the residual
removes systematic moves, the engineered idiosyncratic leader ranks #1 in its
sector, the reversal/entry overlay classifies correctly — plus one cache-gated
integration check. See research/RESIDUAL_ALPHA_MOMENTUM.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import residual_alpha as ra  # noqa: E402
from lib import config  # noqa: E402

WIN, FORM, SKIP, MIN_SECTOR, MIN_NAMES = 30, 40, 5, 3, 6
ENTRY_VALUES = {"extended", "pullback", "intact", "laggard", "neutral", None}


def _synthetic():
    """6 stocks in 2 sectors over 200 bdays. 'AL' carries a persistent positive
    idiosyncratic drift (beyond market+sector) → it should win its sector on the
    residual; everything else is market+sector with ~zero idio."""
    rng = np.random.default_rng(0)
    n = 200
    dates = pd.bdate_range("2022-01-03", periods=n)
    m_ret = rng.normal(0.0003, 0.010, n)
    secA = rng.normal(0.0, 0.006, n)
    secB = rng.normal(0.0, 0.006, n)

    def s(beta, sec, drift):
        return beta * m_ret + sec + rng.normal(drift, 0.006, n)

    rets = pd.DataFrame({
        "AL": s(1.0, secA, 0.0015),   # the engineered idiosyncratic leader
        "A1": s(1.0, secA, 0.0),
        "A2": s(0.9, secA, 0.0),
        "B1": s(1.0, secB, 0.0),
        "B2": s(1.1, secB, 0.0),
        "B3": s(0.8, secB, -0.0005),
    }, index=dates)
    closes = (1.0 + rets).cumprod() * 100.0
    market = pd.Series(m_ret, index=dates)        # injected as a RETURN series
    tkr_sector = {"AL": "A-tech", "A1": "A-tech", "A2": "A-tech",
                  "B1": "B-fin", "B2": "B-fin", "B3": "B-fin"}
    return closes, market, tkr_sector


def _run():
    closes, market, tkr_sector = _synthetic()
    return ra.compute_residual_alpha(closes, market, tkr_sector, win=WIN, form=FORM,
                                     skip=SKIP, top_n=5, min_sector=MIN_SECTOR, min_names=MIN_NAMES)


def test_entry_overlay_classification() -> None:
    assert ra._entry(1.0, 90) == "extended"     # leader, ran hot → reversal risk
    assert ra._entry(1.0, 20) == "pullback"     # leader on a dip → constructive
    assert ra._entry(1.0, 60) == "intact"
    assert ra._entry(-1.0, 50) == "laggard"
    assert ra._entry(0.0, 50) == "neutral"
    assert ra._entry(None, 50) is None and ra._entry(1.0, None) is None


def test_residual_removes_systematic() -> None:
    """Residualizing strips the market+sector variance from a pure-systematic name,
    and the engineered leader's idiosyncratic drift survives."""
    closes, market, tkr_sector = _synthetic()
    eps = ra.residuals(closes, market, tkr_sector, win=WIN, shrink=0.66)
    R = closes.pct_change(fill_method=None)
    valid = eps.dropna()
    # A1 is pure market+sector → its residual variance is far below its raw variance
    assert valid["A1"].std() < R["A1"].loc[valid.index].std() * 0.75
    # the leader's positive idiosyncratic drift survives and beats the flat peer
    assert valid["AL"].mean() > 0
    assert valid["AL"].mean() > valid["A1"].mean()


def test_leader_ranks_first_in_sector() -> None:
    r = _run()
    assert r is not None
    a = r["by_sector"]["A-tech"]
    assert a["leaders"][0]["ticker"] == "AL"          # engineered winner on top
    pt = r["per_ticker"]
    assert pt["AL"]["sector_rank"] == 1
    assert pt["AL"]["alpha"] > pt["A1"]["alpha"] > -3.1
    assert r["top"][0]["ticker"] == "AL"              # also the cross-sector leader


def test_schema_and_bounds() -> None:
    r = _run()
    assert {"as_of", "n", "note", "windows", "by_sector", "top", "per_ticker"} <= set(r)
    assert r["n"] >= 6
    for sec in r["by_sector"].values():
        assert sec["n"] >= MIN_SECTOR
        for x in sec["leaders"]:
            assert {"ticker", "name", "sector", "alpha", "sector_rank", "sector_n", "entry"} <= set(x)
            assert -3.0 <= x["alpha"] <= 3.0
            assert x["entry"] in ENTRY_VALUES
    for v in r["per_ticker"].values():
        assert v["entry"] in ENTRY_VALUES
        assert v["alpha"] is None or -3.0 <= v["alpha"] <= 3.0


def test_rs_pctile_bounds_and_monotone() -> None:
    """The derived IBD-style RS column is in 1-99 and the headline rs is monotone
    with total_mom (so it reads as a familiar momentum lens, never the alpha score)."""
    r = _run()
    recs = list(r["per_ticker"].values())
    for v in recs:
        for k in ("rs", "rs3m", "rs6m", "rs12m"):
            assert k in v
            if v[k] is not None:
                assert 1 <= v[k] <= 99
    paired = [(v["total_mom"], v["rs"]) for v in recs
              if v.get("total_mom") is not None and v.get("rs") is not None]
    xs = [p[0] for p in paired]
    ys = [p[1] for p in paired]
    # same ordering by total_mom and by rs ⇒ rs is monotone in total_mom
    assert sorted(range(len(xs)), key=lambda i: xs[i]) == \
           sorted(range(len(ys)), key=lambda i: ys[i])


def test_too_few_names_returns_none() -> None:
    closes, market, tkr_sector = _synthetic()
    r = ra.compute_residual_alpha(closes[["AL", "A1"]], market,
                                  {k: tkr_sector[k] for k in ("AL", "A1")},
                                  win=WIN, form=FORM, skip=SKIP, min_sector=MIN_SECTOR)
    assert r is None                                  # below the 20-name floor → None, not a crash


def _extras_env(monkeypatch, index):
    """Fake config + yahoo store so _extras_closes / the live merge are exercised
    without disk. Four extras probe every branch of the qualifying rule:
      XSEC = sectored + long history  → ADMIT
      XETF = no extra_names sector    → SKIP (ETF/macro proxy)
      XSHORT = sectored but too few obs → SKIP (< _EXTRA_MIN_OBS)
      XDUP = sectored + long, but already a broad column → SKIP (no overwrite)."""
    n = len(index)
    cfg = {"stock_search": {
        "extra_tickers": ["XSEC", "XETF", "XSHORT", "XDUP"],
        "extra_names": {
            "XSEC":  {"name": "Extra Sectored Co", "sector": "Financials"},
            "XSHORT": {"name": "Extra Short Co", "sector": "Financials"},
            "XDUP":  {"name": "Dup Co", "sector": "B-fin"},
            # XETF deliberately omitted → falls back to "—" sector → skipped
        }}}
    monkeypatch.setattr(ra.config, "load", lambda: cfg)
    long_close = pd.Series(np.linspace(100.0, 130.0, n), index=index)
    short_close = long_close.iloc[-50:]                     # < _EXTRA_MIN_OBS

    def fake_read(group, name):
        if group != "yahoo":
            return None
        if name in ("XSEC", "XDUP"):
            return pd.DataFrame({"close": long_close.values}, index=index)
        if name == "XSHORT":
            return pd.DataFrame({"close": short_close.values}, index=short_close.index)
        if name == "SPY":                                   # market series for the live path
            return pd.DataFrame({"close": long_close.values}, index=index)
        return None
    monkeypatch.setattr(ra.store, "read", fake_read)


def test_extras_closes_qualifying_rule(monkeypatch) -> None:
    idx = pd.bdate_range("2022-01-03", periods=300)
    _extras_env(monkeypatch, idx)
    monkeypatch.setattr(ra, "_EXTRA_MIN_OBS", 200)
    cols, meta = ra._extras_closes(idx)
    assert set(cols) == {"XSEC", "XDUP"}                    # XETF (no sector) + XSHORT (obs) skipped
    assert meta["XSEC"] == ("Extra Sectored Co", "Financials")
    assert list(cols["XSEC"].index) == list(idx)           # reindexed onto the broad index
    assert cols["XSEC"].notna().sum() == len(idx)


def test_live_merge_admits_extra_and_scores_it(monkeypatch) -> None:
    """End-to-end on the live path (closes loaded internally): a qualifying extra is
    concatenated onto the broad matrix, keeps its real name+sector, and earns a
    per-ticker alpha; an already-present column is NOT duplicated/overwritten."""
    closes, market, tkr_sector = _synthetic()
    idx = closes.index
    _extras_env(monkeypatch, idx)
    monkeypatch.setattr(ra, "_EXTRA_MIN_OBS", 100)          # synthetic panel is 200 bdays
    # live path: _closes() returns our synthetic broad matrix; _names_sectors() its labels.
    # XDUP shares B-fin sector AND (below) a column name already in the matrix.
    dup = closes.rename(columns={"B1": "XDUP"})             # make XDUP an existing broad column
    monkeypatch.setattr(ra, "_closes", lambda *a, **k: dup)
    monkeypatch.setattr(ra, "_names_sectors",
                        lambda *a, **k: {t: (t, tkr_sector.get(t if t != "XDUP" else "B1", "—"))
                                         for t in dup.columns})
    r = ra.compute_residual_alpha(win=WIN, form=FORM, skip=SKIP,
                                  min_sector=MIN_SECTOR, min_names=MIN_NAMES)
    assert r is not None
    pt = r["per_ticker"]
    assert "XSEC" in pt and pt["XSEC"]["alpha"] is not None  # admitted + scored
    # XDUP was already a broad column → merge must not add a second one (no overwrite)
    assert list(dup.columns).count("XDUP") == 1
    # real display name flows through rec(): XSEC appears with its company name somewhere
    named = {x["ticker"]: x["name"]
             for sec in r["by_sector"].values() for x in sec["leaders"] + sec["laggards"]}
    named.update({x["ticker"]: x["name"] for x in r["top"]})
    assert named.get("XSEC") == "Extra Sectored Co"


def test_compute_on_live_cache_if_present() -> None:
    cache = config.data_dir() / "breadth" / "_closes_cache.parquet"
    spy = config.data_dir() / "yahoo" / "SPY.parquet"
    if not (cache.exists() and spy.exists()):
        return  # no live cache in this environment — synthetic tests cover the math
    r = ra.compute_residual_alpha()
    assert r is not None and r["n"] > 50
    assert r["top"] and {"ticker", "alpha", "sector_rank"} <= set(r["top"][0])
    assert r["by_sector"]                              # at least one GICS sector populated
