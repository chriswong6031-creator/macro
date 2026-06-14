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


# underlyings scored daily for the GEX/magnets layer (engine/gex_engine.py). Indices
# + a small set of the most-liquid optionable single-names (dealer-sign is least
# unreliable where the chain is deep). Overridable via config cboe.gex.symbols.
DEFAULT_GEX_SYMBOLS = ["_SPX", "SPY", "QQQ", "IWM",
                       "NVDA", "AAPL", "TSLA", "AMD", "META", "MSFT"]
GEX_Q = {"_SPX": 0.013, "SPY": 0.013, "QQQ": 0.006, "IWM": 0.013}  # div yields; names -> 0


class GexAdapter(Adapter):
    """Dealer-gamma summaries for SPX + liquid underlyings. Persists a 1-row/day
    summary per symbol (regime/flip/magnets/IV30 history -> feeds the board's regime
    panel, the per-stock context overlay, and the realized-vol validation). The rich
    per-strike chain is NOT stored (the runner is a date-indexed time series); the
    board/stock builds re-fetch the live chain for the strike-ladder detail. The
    legacy `gex` (SPX) frame is preserved byte-for-byte for build_site + the
    gex_flip_cross alert. A VOL-REGIME + LEVELS MAP, not alpha (see LIMITATIONS.md)."""

    name = "cboe_gex"
    group = "cboe"

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def _chain(self, symbol: str) -> tuple[pd.DataFrame, float]:
        """Fetch + parse one underlying's delayed chain -> per-strike DataFrame
        [K, T, iv(decimal), oi, gamma, is_call, expiry] + spot."""
        url = self.cfg["chain_url"].replace("_SPX", symbol)
        r = self.http_get(url, retries=self.cfg["retries"], timeout=120)
        data = r.json()["data"]
        spot = float(data.get("close") or data.get("current_price"))
        o = pd.DataFrame(data["options"])
        m = o["option"].str.extract(r"^[A-Z]+W?(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")
        o["is_call"] = m["cp"] == "C"
        o["K"] = pd.to_numeric(m["strike"], errors="coerce") / 1000.0
        exp = pd.to_datetime(m["exp"], format="%y%m%d", errors="coerce")
        o["expiry"] = exp
        o["T"] = (exp - pd.Timestamp(date.today())).dt.days / 365.0
        o["iv"] = pd.to_numeric(o.get("iv"), errors="coerce")
        o["oi"] = pd.to_numeric(o.get("open_interest"), errors="coerce")
        o["gamma"] = pd.to_numeric(o.get("gamma"), errors="coerce")
        return o.dropna(subset=["K", "T", "is_call", "oi"]), spot

    def _legacy_spx(self, o: pd.DataFrame, spot: float, gcfg: dict) -> pd.DataFrame:
        """Original SPX frame (net_gex_bn, flip_strike, spot, spot_vs_flip_pct) —
        UNCHANGED math, so build_site + gex_flip_cross are unaffected."""
        c = o.dropna(subset=["gamma"]).copy()
        horizon = pd.Timestamp(date.today()) + pd.Timedelta(days=gcfg["max_expiry_days"])
        win = gcfg["strike_window_pct"]
        c = c[(c["expiry"] <= horizon) & c["K"].between(spot * (1 - win), spot * (1 + win))]
        mult = gcfg["contract_multiplier"] * spot ** 2 * gcfg["pct_move"]
        sign = np.where(c["is_call"], 1.0, -1.0)
        c = c.assign(gex=sign * c["gamma"] * c["oi"] * mult)
        by_strike = c.groupby("K")["gex"].sum().sort_index()
        cum = by_strike.cumsum()
        flip = np.nan
        crossings = cum[np.sign(cum).diff().abs() > 0]
        near = crossings[np.abs(crossings.index / spot - 1) <= 0.15]
        if not near.empty:
            flip = float(near.index[np.argmin(np.abs(near.index - spot))])
        svf = (spot / flip - 1) * 100 if not np.isnan(flip) else np.nan
        return pd.DataFrame({"net_gex_bn": [by_strike.sum() / 1e9], "flip_strike": [flip],
                             "spot": [spot], "spot_vs_flip_pct": [svf]},
                            index=[pd.Timestamp(date.today())])

    @staticmethod
    def _row(summ: dict) -> pd.DataFrame:
        """1-row/day summary frame (the per-strike detail is re-fetched at build)."""
        keep = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")
        return pd.DataFrame({k: [summ.get(k)] for k in keep},
                            index=[pd.Timestamp(date.today())])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        from engine.gex_engine import compute_gex     # lazy — keep the collector light
        gcfg = self.cfg["gex"]
        symbols = gcfg.get("symbols", DEFAULT_GEX_SYMBOLS)
        ecfg = {k: gcfg[k] for k in ("contract_multiplier", "pct_move",
                                     "strike_window_pct", "max_expiry_days") if k in gcfg}
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                chain, spot = self._chain(sym)
                summ = compute_gex(chain, spot, cfg={**ecfg, "r": gcfg.get("r", 0.043),
                                                     "q": GEX_Q.get(sym, 0.0)})
                out[f"gex_{sym.lstrip('_')}"] = self._row(summ)
                if sym == "_SPX":
                    out["gex"] = self._legacy_spx(chain, spot, gcfg)
            except Exception as e:  # noqa: BLE001 — partial coverage still useful
                log.warning("gex: %s failed: %s", sym, e)
        return out
