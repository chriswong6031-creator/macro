"""Cross-sectional equity factor engine (research/QUANT_FACTOR_EXPANSION.md).

Joins the SEC EDGAR XBRL fundamentals (collectors/edgar.py) to the S&P 1500
price universe (breadth close caches) and computes the canonical smart-beta
factors that the dashboard previously only PROXIED with factor ETFs:

  value         earnings yield + book/price + sales/price + CFO yield
  profitability gross profitability (GP / Assets) — Novy-Marx
  quality       ROE, low accruals (Sloan), low leverage
  investment    low asset growth (Fama-French CMA)
  payout        net shareholder yield ((dividends + buybacks) / market cap)
  low_vol       low trailing total volatility (the low-vol anomaly)
  low_beta      low market beta (Betting-Against-Beta, Frazzini-Pedersen)

Each factor is a winsorized cross-sectional z-score (higher = more attractive);
the multi-factor composite is their equal-weight mean over available legs. A
coarse "leadership" read shows which factor's top quintile has beaten its bottom
quintile over a trailing window — descriptive, not predictive.

Honest caveats (shipped on the page): factors have decayed post-publication and
are crowded; free fundamentals are sparse for some tags; book/price is weak for
intangible-heavy firms; values are lagged to the filing period (no look-ahead);
these are ranks/context, not a validated alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

FACTOR_LABELS = {
    "value": "Value", "profitability": "Profitability", "quality": "Quality",
    "investment": "Investment", "payout": "Shareholder yield",
    "low_vol": "Low volatility", "low_beta": "Low beta (BAB)",
    "short_interest": "Low short interest", "accruals": "Low accruals",
}


def _short_interest() -> pd.DataFrame | None:
    p = config.data_dir() / "finra" / "short_interest.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    return df if not df.empty else None


def _insider_block(ns: dict) -> dict | None:
    """Top net insider buying / selling from the SEC Form-4 quarterly dataset."""
    p = config.data_dir() / "sec_insider" / "insider.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty or "net_usd" not in df.columns:
        return None

    def rows(sub: pd.DataFrame, sign: int) -> list[dict]:
        out = []
        for t, r in sub.iterrows():
            out.append({"ticker": t, "name": ns.get(t, (t, "—"))[0],
                        "sector": ns.get(t, (t, "—"))[1],
                        "net_usd_mn": round(float(r["net_usd"]) / 1e6, 2),
                        "buys": int(r.get("n_buys", 0)), "sells": int(r.get("n_sells", 0))})
        return out
    n = config.load()["sec_insider"]["panel_top_n"]
    buying = df[df["net_usd"] > 0].nlargest(n, "net_usd")
    selling = df[df["net_usd"] < 0].nsmallest(n, "net_usd")
    return {"quarter": str(df["quarter"].iloc[0]) if "quarter" in df else None,
            "n_issuers": int(len(df)),
            "top_buying": rows(buying, 1), "top_selling": rows(selling, -1)}


# universe → which breadth caches define the price/name set. 'broad' = the full
# S&P 1500 (large+mid+small); 'narrow' = the S&P 500 large-cap (breadth cache only).
# The keyword default is 'broad' so every existing caller is unchanged.
_UNIVERSE_GROUPS = {"broad": ("breadth", "smallcap_breadth", "midcap_breadth"),
                    "narrow": ("breadth",)}


def _closes(universe: str = "broad") -> pd.DataFrame:
    """Close matrix from the breadth caches. 'broad' = combined S&P 1500;
    'narrow' = the S&P 500 large-cap cache only."""
    frames = []
    for grp in _UNIVERSE_GROUPS.get(universe, _UNIVERSE_GROUPS["broad"]):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    return out.loc[:, ~out.columns.duplicated()].sort_index()


def _names_sectors(universe: str = "broad") -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for grp in _UNIVERSE_GROUPS.get(universe, _UNIVERSE_GROUPS["broad"]):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), (str(row.get("name", t)), str(row.get("sector", "—"))))
    return out


def _winsor_z(s: pd.Series, cap: float) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    mu, sd = s.mean(), s.std()
    if not sd or np.isnan(sd):
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)


def compute_factors(asof=None, universe: str = "broad") -> dict | None:
    """Build the factor table + leaderboards + leadership read. Returns None if
    the fundamentals cache is missing (caller logs and skips).

    `asof` (a date) switches to POINT-IN-TIME mode: fundamentals come from the
    leak-free panel cross-section knowable at `asof` (collectors.edgar.
    as_of_cross_section) and prices are truncated to `asof`. This is the honest
    input for a factor IC backtest (Phase A) — at each rebalance date it sees only
    what had actually been filed. `asof=None` (the live dashboard path) reads the
    latest-FY snapshot and the newest prices, exactly as before."""
    cfg = config.load()["edgar"]["factors"]
    cap = cfg["winsor_z"]
    fpath = config.data_dir() / "edgar" / "fundamentals.parquet"
    if asof is None:
        if not fpath.exists():
            log.warning("equity_factors: no fundamentals cache — run collectors.edgar")
            return None
        fund = pd.read_parquet(fpath)
    else:
        from collectors.edgar import as_of_cross_section
        try:
            fund = as_of_cross_section(asof)
        except Exception as e:  # noqa: BLE001 — no panel yet
            log.warning("equity_factors: point-in-time panel unavailable (%s)", e)
            return None
        if fund.empty:
            log.warning("equity_factors: no fundamentals knowable at %s", asof)
            return None
    closes = _closes(universe)
    if closes.empty:
        log.warning("equity_factors: no close caches")
        return None
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]

    # latest price + trailing return stats, aligned to fundamentals universe
    px = closes.reindex(columns=[t for t in fund.index if t in closes.columns])
    last_px = px.ffill().iloc[-1]
    rets = px.pct_change(fill_method=None)
    win = cfg["low_vol_window_d"]
    minp = cfg["min_price_history_d"]
    vol = rets.tail(win).std() * np.sqrt(252)
    vol[rets.tail(win).count() < minp] = np.nan
    # market beta vs SPY (Betting-Against-Beta)
    spy = store.read("yahoo", "SPY")
    if spy is not None and asof is not None:
        spy = spy.loc[:pd.Timestamp(asof)]
    beta = pd.Series(np.nan, index=px.columns)
    if spy is not None and "close" in spy.columns:
        spy_ret = spy["close"].pct_change(fill_method=None).reindex(px.index)
        sub = rets.tail(win)
        spy_sub = spy_ret.tail(win)
        var_m = spy_sub.var()
        if var_m and not np.isnan(var_m):
            beta = sub.apply(lambda c: c.cov(spy_sub) / var_m)

    d = fund.copy()
    d = d[d.index.isin(last_px.index)]
    d["price"] = last_px.reindex(d.index)
    d["mktcap"] = d["price"] * d["shares"]
    d["vol"] = vol.reindex(d.index)
    d["beta"] = beta.reindex(d.index)

    mc = d["mktcap"].where(d["mktcap"] > 0)
    avg_assets = (d["assets"] + d["assets_prior"]) / 2.0

    # --- raw factor inputs (higher = more attractive) ------------------------
    raw = pd.DataFrame(index=d.index)
    # value: yields (cheap = high)
    ey = d["ni"] / mc
    bp = d["equity"] / mc
    sp = d["revenue"] / mc
    cfoy = d["cfo"] / mc
    raw["value"] = pd.concat([_winsor_z(ey, cap), _winsor_z(bp, cap),
                              _winsor_z(sp, cap), _winsor_z(cfoy, cap)], axis=1).mean(axis=1)
    # profitability: gross profitability (Novy-Marx)
    raw["profitability"] = _winsor_z(d["gross_profit"] / d["assets"], cap)
    # quality: ROE + low accruals + low leverage
    roe = _winsor_z(d["ni"] / d["equity"].where(d["equity"] > 0), cap)
    accr = _winsor_z((d["ni"] - d["cfo"]) / avg_assets, cap)        # high accruals = bad
    lev = _winsor_z(d["debt_lt"] / d["assets"], cap)               # high leverage = bad
    raw["quality"] = pd.concat([roe, -accr, -lev], axis=1).mean(axis=1)
    raw["accruals"] = -accr                                        # standalone leaderboard
    # investment: low asset growth = good
    asset_growth = d["assets"] / d["assets_prior"] - 1.0
    raw["investment"] = -_winsor_z(asset_growth, cap)
    # payout: net shareholder yield
    payout = (d["dividends"].fillna(0) + d["repurchases"].fillna(0)) / mc
    payout[d["dividends"].isna() & d["repurchases"].isna()] = np.nan
    raw["payout"] = _winsor_z(payout, cap)
    # price-only factors
    raw["low_vol"] = -_winsor_z(d["vol"], cap)
    raw["low_beta"] = -_winsor_z(d["beta"], cap)
    # positioning: FINRA short interest (high days-to-cover / short % = bearish)
    si = _short_interest()
    if si is not None:
        dtc = si["days_to_cover"].reindex(d.index)
        si_pct = si["short_shares"].reindex(d.index) / d["shares"].where(d["shares"] > 0)
        raw["short_interest"] = -pd.concat([_winsor_z(dtc, cap), _winsor_z(si_pct, cap)],
                                           axis=1).mean(axis=1)

    # second-pass z (so each factor is a clean unit-variance score)
    fac = pd.DataFrame({c: _winsor_z(raw[c], cap) for c in raw.columns})

    composite_legs = [c for c in cfg["composite"] if c in fac.columns]
    avail = fac[composite_legs].notna()
    comp = fac[composite_legs].where(avail).mean(axis=1)
    comp[avail.sum(axis=1) < 3] = np.nan                          # need >=3 legs
    fac["composite"] = comp
    all_factors = [c for c in fac.columns if c != "composite"]    # incl. standalone accruals / low_beta

    # attach descriptive cols
    ns = _names_sectors(universe)
    meta = pd.DataFrame(index=fac.index)
    meta["name"] = [ns.get(t, (t, "—"))[0] for t in fac.index]
    meta["sector"] = [ns.get(t, (t, "—"))[1] for t in fac.index]
    meta["mktcap_bn"] = (d["mktcap"] / 1e9).reindex(fac.index)

    table = meta.join(fac.round(3))

    # leadership: top-quintile minus bottom-quintile trailing return per factor
    lw = config.load()["engine_equity_factors"]["leadership_window_d"]
    trailing = (px.ffill().iloc[-1] / px.ffill().iloc[-min(lw, len(px) - 1)] - 1.0)
    leadership = []
    for c in all_factors:
        z = fac[c].dropna()
        if len(z) < 50:
            continue
        hi = z[z >= z.quantile(0.8)].index
        lo = z[z <= z.quantile(0.2)].index
        sh = trailing.reindex(hi).mean()
        sl = trailing.reindex(lo).mean()
        if pd.isna(sh) or pd.isna(sl):
            continue
        leadership.append({"factor": c, "label": FACTOR_LABELS.get(c, c),
                           "spread_pct": round(float((sh - sl) * 100), 2)})
    leadership.sort(key=lambda x: -x["spread_pct"])

    def top(col: str, n: int, asc: bool = False) -> list[dict]:
        s = table[col].dropna().sort_values(ascending=asc).head(n)
        return [{"ticker": t, "name": table.at[t, "name"], "sector": table.at[t, "sector"],
                 "z": float(table.at[t, col]),
                 "mktcap_bn": (round(float(table.at[t, "mktcap_bn"]), 1)
                               if pd.notna(table.at[t, "mktcap_bn"]) else None)}
                for t in s.index]

    n = cfg["page_top_n"]
    leaders = {c: top(c, n) for c in all_factors}
    laggards = {c: top(c, n, asc=True) for c in all_factors}

    meta_json = {}
    mp = config.data_dir() / "edgar" / "_meta.json"
    if mp.exists():
        import json
        meta_json = json.loads(mp.read_text())

    return {
        "as_of": str(px.index.max().date()),
        "universe": universe,
        "fy": (int(fund["fy"].max()) if (asof is not None and "fy" in fund.columns)
               else meta_json.get("fy")),
        "n": int(fac["composite"].notna().sum()),
        "factors": composite_legs,
        "factor_labels": {c: FACTOR_LABELS.get(c, c) for c in fac.columns if c in FACTOR_LABELS},
        "leadership": leadership,
        "leaders": leaders,
        "laggards": laggards,
        "composite_top": top("composite", n),
        "composite_bottom": top("composite", n, asc=True),
        "insider": _insider_block(ns),
        "table": table.reset_index().rename(columns={"index": "ticker"}).to_dict("records"),
    }
