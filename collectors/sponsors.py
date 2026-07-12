"""Sector SPDR daily shares outstanding -> ETF flows, computed not scraped.

One fetch of SSGA's fundfinder JSON covers all US SSGA ETFs. Shares
outstanding is exact from AUM/NAV (AUM = SO x NAV, same as-of date). The
engine/report computes flow(t) = delta(SO) x NAV(t), the same
creation/redemption signal paid vendors sell, at T+1.

Stored per fund (data/flows/<TICKER>.parquet): nav, aum_mn, so_mn.
History accumulates one row per trading day from first deployment — there is
no free historical SO source, so percentile work matures as data accrues.

``BroadFlowAdapter`` (RLT-R3) uses the same schema for the 5 broad-market
index ETFs (SPY, QQQ, IWM, RSP, DIA).  It fetches AUM/NAV/SO from yfinance
(``Ticker.info``) which covers all sponsors without bot-blocking — iShares
direct is Akamai-blocked (project notes) and Invesco's cache API surfaces
holdings, not fund-level AUM.  The data written is identical in schema to
the sector-SPDR parquets so ``engine/etf_flows.rebuild_broad()`` can reuse
``_derive_flow`` unchanged.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

FUNDFINDER = ("https://www.ssga.com/bin/v1/ssmp/fund/fundfinder"
              "?country=us&language=en&role=intermediary&product=etfs&ui=fund-finder")

# RLT-R3: broad-market index ETFs.  One per sponsor; yfinance is the single
# source because it avoids Akamai blocking (iShares) and returns fund-level
# AUM/NAV uniformly across SSGA/Invesco/iShares funds.
BROAD_ETF_TICKERS = ("SPY", "QQQ", "IWM", "RSP", "DIA")


class SectorFlowAdapter(Adapter):
    name = "sector_flows"
    group = "flows"

    def __init__(self) -> None:
        self.cfg = config.load()["sponsors"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(FUNDFINDER, retries=self.cfg["retries"], timeout=90,
                          headers={"User-Agent": "Mozilla/5.0 (research)"})
        funds = r.json()["data"]["funds"]["etfs"]["datas"]
        wanted = set(self.cfg["sector_funds"])
        frames: dict[str, pd.DataFrame] = {}
        for d in funds:
            tick = str(d.get("fundTicker", "")).strip()
            if tick not in wanted:
                continue
            try:
                nav = float(d["nav"][1])
                aum_mn = float(d["aum"][1])
                asof = pd.Timestamp(d["asOfDate"][1])
                if nav <= 0 or aum_mn <= 0:
                    raise ValueError(f"bad nav/aum {nav}/{aum_mn}")
                frames[tick] = pd.DataFrame(
                    {"nav": [nav], "aum_mn": [aum_mn], "so_mn": [aum_mn / nav]},
                    index=[asof])
            except Exception as e:  # noqa: BLE001
                log.warning("sector_flows: %s parse failed: %s", tick, e)
        missing = wanted - set(frames)
        if missing:
            log.warning("sector_flows: missing funds %s", sorted(missing))
        if len(frames) < len(wanted) * 0.7:
            raise RuntimeError(f"only {len(frames)}/{len(wanted)} sector funds parsed")
        return frames


def flows_table() -> pd.DataFrame | None:
    """Daily flow estimate per sector fund: delta(SO) x NAV ($mn)."""
    from lib import store
    cfg = config.load()["sponsors"]
    rows = []
    for t in cfg["sector_funds"]:
        df = store.read("flows", t)
        if df is None or len(df) < 2:
            continue
        d_so = df["so_mn"].diff()
        flow_mn = d_so * df["nav"]
        rows.append(pd.DataFrame({f"{t}_flow_mn": flow_mn}))
    if not rows:
        return None
    return pd.concat(rows, axis=1)


# Trading-day windows the multi-period flow board sums over. Each window caps at
# the available history, so until enough days accrue the wider windows simply hold
# fewer days (and 2W/1M can coincide). Order = display order.
FLOW_PERIODS: tuple[tuple[str, int], ...] = (
    ("1D", 1), ("3D", 3), ("1W", 5), ("2W", 10), ("1M", 21),
)


def sector_flow_periods(
        periods: tuple[tuple[str, int], ...] = FLOW_PERIODS) -> dict | None:
    """Multi-window sector-ETF flow: for each sector SPDR, the SUM of daily
    creation/redemption flow ($mn) over each trailing window (1D/3D/1W/2W/1M).

    This is the multi-day view of where money is rotating across the sector
    complex — far more readable than the day-by-day grid. Each window sums the
    trailing N trading days that exist (so wider windows hold fewer days until
    history matures). Returns ``{asof, depth, labels, rows, net}`` where ``rows``
    is one ``{ticker, vals: {label: $mn|None}}`` per fund and ``net`` is the
    across-complex sum per window. None until at least two daily snapshots exist.
    """
    ft = flows_table()
    if ft is None:
        return None
    ft = ft.dropna(how="all")
    if ft.empty:
        return None
    labels = [lbl for lbl, _ in periods]
    rows: list[dict] = []
    net = {lbl: 0.0 for lbl in labels}
    depth = 0
    for col in ft.columns:
        ticker = col.replace("_flow_mn", "")
        s = ft[col].dropna()
        depth = max(depth, len(s))
        vals: dict[str, float | None] = {}
        for lbl, n in periods:
            if len(s):
                v = float(s.tail(n).sum())
                vals[lbl] = v
                net[lbl] += v
            else:
                vals[lbl] = None
        rows.append({"ticker": ticker, "vals": vals})
    return {
        "asof": str(ft.index.max().date()),
        "depth": int(depth),
        "labels": labels,
        "rows": rows,
        "net": net,
    }


class BroadFlowAdapter(Adapter):
    """RLT-R3: daily AUM/NAV/SO snapshot for broad-market index ETFs.

    Uses yfinance ``Ticker.info`` as the single data source across all five
    ETF sponsors (SSGA/Invesco/iShares) — avoids iShares Akamai bot-block
    and provides a uniform interface.  Writes to ``data/flows/<T>.parquet``
    with the same schema as ``SectorFlowAdapter`` so ``engine/etf_flows``
    reuses ``_derive_flow`` unchanged.

    Display/context only — never feeds a score or allocation path.
    """
    name = "broad_flows"
    group = "flows"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is required for BroadFlowAdapter") from exc

        asof = pd.Timestamp(date.today())
        frames: dict[str, pd.DataFrame] = {}
        errors = []
        for tick in BROAD_ETF_TICKERS:
            try:
                info = yf.Ticker(tick).info
                # navPrice is the official per-share NAV; fall back to lastPrice
                nav = info.get("navPrice") or info.get("regularMarketPrice")
                aum_mn = (info.get("totalAssets") or 0) / 1e6
                so_shares = info.get("sharesOutstanding") or 0
                if not nav or nav <= 0:
                    raise ValueError(f"no valid nav (navPrice={info.get('navPrice')})")
                if aum_mn <= 0 or so_shares <= 0:
                    raise ValueError(f"bad aum_mn={aum_mn:.0f} or so={so_shares}")
                so_mn = so_shares / 1e6
                frames[tick] = pd.DataFrame(
                    {"nav": [float(nav)], "aum_mn": [aum_mn], "so_mn": [so_mn]},
                    index=[asof],
                )
            except Exception as e:  # noqa: BLE001
                log.warning("broad_flows: %s fetch failed: %s", tick, e)
                errors.append(tick)

        missing = set(BROAD_ETF_TICKERS) - set(frames)
        if missing:
            log.warning("broad_flows: missing tickers %s", sorted(missing))
        if len(frames) < len(BROAD_ETF_TICKERS) * 0.6:
            raise RuntimeError(
                f"broad_flows: only {len(frames)}/{len(BROAD_ETF_TICKERS)} tickers "
                f"succeeded (errors: {errors})"
            )
        return frames
