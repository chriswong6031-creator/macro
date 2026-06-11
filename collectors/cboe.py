"""CBOE collectors: daily put/call ratios and SPX dealer-gamma (GEX).

GEX methodology (standard open-source convention, e.g. gex-tracker):
  dealers assumed long calls / short puts ->
    call GEX(strike) = +gamma * OI * 100 * spot^2 * 0.01
    put  GEX(strike) = -gamma * OI * 100 * spot^2 * 0.01
  net GEX = sum over strikes (expressed in $bn per 1% move);
  gamma flip = strike where the cumulative-by-strike profile crosses zero.
This is an assumption, not ground truth — see LIMITATIONS.md. Delayed chain,
EOD cadence: a regime/vol-context input, not a day-trading tool.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class PutCallAdapter(Adapter):
    """Put/call volume ratios COMPUTED from CBOE delayed chains (the official
    market-statistics CSV endpoints went behind the SPA in 2025/26). Index P/C
    from SPX; equity-proxy P/C from SPY+QQQ+IWM combined. Not the official
    total-market ratio — a computed proxy from the most liquid underlyings
    (see LIMITATIONS.md), which also obeys the 'compute, don't scrape' rule."""

    name = "cboe_putcall"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def _chain_volumes(self, symbol: str) -> tuple[float, float]:
        url = self.cfg["chain_url"].replace("_SPX", symbol)
        r = self.http_get(url, retries=self.cfg["retries"], timeout=120)
        options = pd.DataFrame(r.json()["data"]["options"])
        cp = options["option"].str.extract(r"\d{6}([CP])\d{8}$")[0]
        vol = pd.to_numeric(options["volume"], errors="coerce").fillna(0)
        return float(vol[cp == "P"].sum()), float(vol[cp == "C"].sum())

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        from datetime import date
        put_idx, call_idx = self._chain_volumes("_SPX")
        put_eq = call_eq = 0.0
        for sym in ("SPY", "QQQ", "IWM"):
            try:
                p, c = self._chain_volumes(sym)
                put_eq += p
                call_eq += c
            except Exception as e:  # noqa: BLE001 — partial proxy still useful
                log.warning("putcall: %s chain failed: %s", sym, e)
        snap = pd.DataFrame({
            "index_pc_ratio": [put_idx / call_idx if call_idx else None],
            "equity_pc_ratio": [put_eq / call_eq if call_eq else None],
            "index_put_vol": [put_idx], "index_call_vol": [call_idx],
            "equity_put_vol": [put_eq], "equity_call_vol": [call_eq],
        }, index=[pd.Timestamp(date.today())])
        return {"putcall": snap.dropna(axis=1, how="all")}


class GexAdapter(Adapter):
    name = "cboe_gex"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["chain_url"], retries=self.cfg["retries"], timeout=120)
        j = r.json()
        data = j["data"]
        spot = float(data.get("close") or data.get("current_price"))
        options = pd.DataFrame(data["options"])
        gcfg = self.cfg["gex"]

        # symbol like 'SPX260620C06000000' -> expiry, type, strike
        sym = options["option"].str.extract(
            r"^[A-Z]+W?(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")
        options["cp"] = sym["cp"]
        options["strike"] = pd.to_numeric(sym["strike"]) / 1000
        options["expiry"] = pd.to_datetime(sym["exp"], format="%y%m%d", errors="coerce")
        options["gamma"] = pd.to_numeric(options["gamma"], errors="coerce")
        options["open_interest"] = pd.to_numeric(options["open_interest"], errors="coerce")
        options = options.dropna(subset=["gamma", "open_interest", "strike", "expiry", "cp"])

        horizon = pd.Timestamp(date.today()) + pd.Timedelta(days=gcfg["max_expiry_days"])
        win = gcfg["strike_window_pct"]
        options = options[(options["expiry"] <= horizon)
                          & (options["strike"].between(spot * (1 - win), spot * (1 + win)))]

        mult = gcfg["contract_multiplier"] * spot ** 2 * gcfg["pct_move"]
        sign = np.where(options["cp"] == "C", 1.0, -1.0)
        options["gex"] = sign * options["gamma"] * options["open_interest"] * mult

        by_strike = options.groupby("strike")["gex"].sum().sort_index()
        net_gex_bn = by_strike.sum() / 1e9
        cum = by_strike.cumsum()
        # flip = zero-crossing of the cumulative profile nearest to spot,
        # considered only within +/-15% of spot — deep-OTM sign flickers in the
        # sparse tails are artifacts, not a gamma flip
        flip = np.nan
        crossings = cum[np.sign(cum).diff().abs() > 0]
        near = crossings[np.abs(crossings.index / spot - 1) <= 0.15]
        if not near.empty:
            flip = float(near.index[np.argmin(np.abs(near.index - spot))])
        spot_vs_flip = (spot / flip - 1) * 100 if not np.isnan(flip) else np.nan

        snap = pd.DataFrame({
            "net_gex_bn": [net_gex_bn],
            "flip_strike": [flip],
            "spot": [spot],
            "spot_vs_flip_pct": [spot_vs_flip],
        }, index=[pd.Timestamp(date.today())])
        return {"gex": snap}
