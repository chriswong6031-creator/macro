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
import re
from datetime import date

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class PutCallAdapter(Adapter):
    name = "cboe_putcall"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["putcall_url"], retries=self.cfg["retries"])
        j = r.json()
        # expected: list/dict of {trade_date|date, name|product, ratio fields}
        rows = j.get("data", j) if isinstance(j, dict) else j
        df = pd.json_normalize(rows)
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            raise ValueError(f"no date column in putcall payload: {list(df.columns)[:8]}")
        df = df.set_index(pd.to_datetime(df[date_col]))
        keep = {c: c.lower().replace(" ", "_") for c in df.columns
                if re.search(r"ratio|put|call", c, re.I)}
        out = df[list(keep)].rename(columns=keep).apply(pd.to_numeric, errors="coerce")
        out = out.dropna(how="all")
        return {"putcall": out}


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
        flip = np.nan
        crossings = cum[np.sign(cum).diff().abs() > 0]
        if not crossings.empty:
            # flip strike closest to spot among zero-crossings
            flip = float(crossings.index[np.argmin(np.abs(crossings.index - spot))])
        spot_vs_flip = (spot / flip - 1) * 100 if not np.isnan(flip) else np.nan

        snap = pd.DataFrame({
            "net_gex_bn": [net_gex_bn],
            "flip_strike": [flip],
            "spot": [spot],
            "spot_vs_flip_pct": [spot_vs_flip],
        }, index=[pd.Timestamp(date.today())])
        return {"gex": snap}
