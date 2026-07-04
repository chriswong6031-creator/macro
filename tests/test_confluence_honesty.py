"""Confluence honesty — the us_sector_health mislabel regression (2026-07-03).

A basket 8 days into a fresh monthly MACD cross-up, trading above a rising 200d,
with EVERY timeframe's MACD up, rendered "Downtrend confirmed across timeframes" /
AVOID and was erased from the act-now board. Three legs, each pinned here:

  1. btc_mtf.confluence_verdict read mtf["ME"] (a BTC-only month-end resample) for
     the long governor — baskets only carry "M", so the monthly trend was invisible
     and cycle-shape penalties (translation/failed-cycle) alone set long_sign=-1.
  2. TOP WATCH / BOTTOM WATCH (daily-driven *warning* states) forced short_sign=-1
     even when the D+3D MACD tape decisively read up.
  3. theme_scoring._long_sign preferred the poisoned confluence long_sign over the
     price-vs-200d proxy — the definition the phase-0 drawdown gate was actually
     validated on (calibrate_baskets: "trend gate stays the price 200d gate").
"""
from __future__ import annotations

from engine import btc_mtf
from engine import theme_scoring as ts


# --------------------------------------------------------------------- fixtures
def _tf(sign: int, cross_up: bool = False) -> dict:
    """A per-timeframe state whose _tf_sign() resolves to the requested sign."""
    if sign > 0:
        return {"macd_pos": True, "rsi14": 60.0, "macd_cross_up": cross_up}
    if sign < 0:
        return {"macd_pos": False, "rsi14": 40.0}
    return {"macd_pos": True, "rsi14": 40.0}   # +1 - 1 -> 0


def _healthcare_like(state: str = "TOP WATCH", regime: str = "neutral") -> dict:
    """The exact contradiction shape: all four basket timeframes up (M freshly crossed),
    no ME/2W keys (baskets feed cycles.analyze output directly), ladder in a daily
    warning state, cycle shape penalised (translation left + failed cycle)."""
    return {
        "mtf": {"D": _tf(1), "3D": _tf(1), "W": _tf(1), "M": _tf(1, cross_up=True)},
        "ladder": {"state": state, "regime": regime},
        "cycle": {"translation": "left", "failed_cycle": True},
    }


# ------------------------------------------------- 1) monthly no longer invisible
def test_long_governor_reads_m_when_me_absent():
    v = btc_mtf.confluence_verdict(_healthcare_like())
    # neutral regime (0) + M sign (+1) - translation (1) - failed cycle (1) = -1 …
    # the monthly is now IN the sum (was 0 + 0 - 1 - 1 = -2 before the fix).
    # per_tf must surface the monthly read instead of a fabricated "flat".
    assert v["per_tf"]["ME"] == "up"


def test_me_still_authoritative_when_present():
    a = _healthcare_like()
    a["mtf"]["ME"] = _tf(-1)                    # BTC-style month-end says down
    v = btc_mtf.confluence_verdict(a)
    assert v["per_tf"]["ME"] == "down"          # ME wins over M when both exist


# ------------------------------------- 2) watch states defer to a decisive tape
def test_top_watch_defers_to_up_tape():
    v = btc_mtf.confluence_verdict(_healthcare_like(state="TOP WATCH"))
    assert v["short_sign"] == 1                 # D+3D both up — warning can't flip it


def test_top_watch_keeps_bear_read_on_flat_tape():
    a = _healthcare_like(state="TOP WATCH")
    a["mtf"]["D"], a["mtf"]["3D"] = _tf(-1), _tf(1)     # tape nets to 0
    v = btc_mtf.confluence_verdict(a)
    assert v["short_sign"] == -1                # prior semantics preserved


def test_decline_stays_authoritative():
    a = _healthcare_like(state="DECLINE", regime="bear")
    v = btc_mtf.confluence_verdict(a)
    assert v["short_sign"] == -1                # confirmed states unchanged


# --------------------------------------------------------- 3) honesty guard
def test_no_downtrend_confirmed_against_all_up_timeframes():
    a = _healthcare_like(state="DECLINE", regime="bear")   # short -1, long -1 -> avoid…
    v = btc_mtf.confluence_verdict(a)
    assert v["grade"] != "AVOID"                # …but every TF reads up -> WAIT
    assert v["grade"] == "WAIT"


def test_avoid_still_fires_when_timeframes_agree_down():
    a = {
        "mtf": {"D": _tf(-1), "3D": _tf(-1), "W": _tf(-1), "M": _tf(-1)},
        "ladder": {"state": "DECLINE", "regime": "bear"},
        "cycle": {},
    }
    v = btc_mtf.confluence_verdict(a)
    assert v["grade"] == "AVOID"
    assert v["long_sign"] == -1 and v["short_sign"] == -1


def test_trend_follow_guard_symmetric():
    a = {
        "mtf": {"D": _tf(-1), "3D": _tf(-1), "W": _tf(-1), "M": _tf(-1)},
        "ladder": {"state": "RALLY ON", "regime": "bull"},
        "cycle": {},
    }
    v = btc_mtf.confluence_verdict(a)
    assert v["grade"] == "WAIT"                 # "aligned uptrend" vs all-down = lie


# --------------------------- 4) the drawdown gate reads the validated 200d proxy
def test_long_sign_prefers_200d_proxy_over_confluence():
    mtf = {"confluence": {"long_sign": -1}}
    assert ts._long_sign(mtf, {"long_sign": 1}) == 1
    assert not ts._long_below_trend(mtf, {"long_sign": 1})


def test_long_sign_falls_back_to_confluence():
    mtf = {"confluence": {"long_sign": -1}}
    assert ts._long_sign(mtf, {}) == -1
    assert ts._long_below_trend(mtf, {})


def test_reco_no_longer_demoted_above_rising_200d():
    """emerging + above rising 200d + benign macro/crowding -> ENTER (was hold)."""
    mtf = {"confluence": {"long_sign": -1}}     # poisoned governor
    fp = {"long_sign": 1, "rs_pctile": 0.5}
    assert ts._reco("emerging", macro=0.0, crowd_pen=0.0, fp=fp, mtf=mtf) == "enter"
