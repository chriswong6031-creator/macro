"""Leg computation — the recreated factor inputs, point-in-time by construction.

Every leg is oriented so HIGHER IS BETTER, so `score.py` can percentile them without
per-leg sign bookkeeping.

POINT-IN-TIME LAW: a leg may only read a store that carries a real availability date, and
must filter on it. The two that qualify:

    fundamentals_panel.asof_date   period_end + reporting lag  (436 distinct dates)
    statements_quarterly.filed     the actual filing date      (3,452 distinct dates)

`statements.parquet` is excluded on purpose — its `as_of` holds five FETCH timestamps, so
every row would be "knowable" at every historical rebalance. It is the richest schema we
have (cash, current debt, inventory, receivables) and using it would materially improve
the EV and invested-capital legs; that is exactly why the exclusion has to be explicit
rather than left to whoever writes the next backtest.

COVERAGE IS THE STORY. On the PIT panel: op_income 76.8%, equity 95.3%, debt_lt 48.8%,
gross_profit 42.8%, capex 32.1%. Legs are computed on whatever is present and the realised
coverage is RETURNED alongside the values, because a leg computed on a third of the
universe ranks a different population than one computed on all of it.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# NOPAT tax rate. The US federal statutory rate post-TCJA. Fintel does not state its own,
# and a flat rate misstates NOPAT for names with unusual effective rates — but a flat rate
# at least applies the SAME distortion to every name, which a cross-sectional rank tolerates
# better than a per-name effective rate estimated from a panel missing tax expense.
TAX_RATE = 0.21

AVG_YEARS = 3            # the vendor's stated averaging window ("3 year average")
TRADING_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


# ---------------------------------------------------------------------------------------
# PIT loaders
# ---------------------------------------------------------------------------------------
def _panel() -> pd.DataFrame:
    p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not p.exists():
        raise FileNotFoundError(f"no PIT fundamentals panel at {p}")
    df = pd.read_parquet(p)
    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce", utc=True).dt.tz_localize(None)
    return df.dropna(subset=["asof_date", "ticker", "fy"])


def knowable(asof=None, years: int = AVG_YEARS) -> pd.DataFrame:
    """The last `years` fiscal years per ticker that had been FILED by `asof`.

    Returned long (ticker, fy, ...) with `fy_rank` = 0 for the most recent knowable year,
    1 for the one before it, and so on — so callers can average or difference without
    re-deriving the ordering.
    """
    df = _panel()
    if asof is not None:
        df = df[df["asof_date"] <= pd.Timestamp(asof)]
    if df.empty:
        return df
    df = df.sort_values(["ticker", "fy"])
    df["fy_rank"] = df.groupby("ticker")["fy"].rank(method="first", ascending=False) - 1
    return df[df["fy_rank"] < years].copy()


def _cash_and_debt(asof=None) -> pd.DataFrame:
    """Latest PIT cash / debt per ticker from the quarterly statements (filed-date gated).

    The annual panel has no cash column at all, so EV and invested capital cannot be
    computed without this join. Coverage is the binding limit: cash ~91%, long-term debt
    ~44%, current debt ~40%, net_debt ~51%.
    """
    p = config.data_dir() / "edgar" / "statements_quarterly.parquet"
    if not p.exists():
        log.warning("quant_lab: no statements_quarterly — cash/debt legs degrade to debt_lt only")
        return pd.DataFrame(columns=["ticker", "cash", "total_debt", "net_debt"]).set_index("ticker")
    q = pd.read_parquet(p)
    q["filed"] = pd.to_datetime(q["filed"], errors="coerce", utc=True).dt.tz_localize(None)
    q = q.dropna(subset=["filed", "ticker"])
    if asof is not None:
        q = q[q["filed"] <= pd.Timestamp(asof)]
    if q.empty:
        return pd.DataFrame(columns=["ticker", "cash", "total_debt", "net_debt"]).set_index("ticker")
    q = q.sort_values("filed").groupby("ticker").tail(1).set_index("ticker")

    lt = pd.to_numeric(q.get("long_term_debt"), errors="coerce")
    cur = pd.to_numeric(q.get("current_debt"), errors="coerce")
    # Sum what is present rather than requiring both; a name with only long-term debt
    # reported is levered by at least that much, and treating the missing half as zero is
    # the SAME direction of error as dropping the name, but keeps the name rankable.
    total = lt.add(cur, fill_value=0.0).where(lt.notna() | cur.notna())
    return pd.DataFrame({
        "cash": pd.to_numeric(q.get("cash"), errors="coerce"),
        "total_debt": total,
        "net_debt": pd.to_numeric(q.get("net_debt"), errors="coerce"),
    })


def _closes(asof=None) -> pd.DataFrame:
    """Wide close panel truncated to `asof`. Reuses the equity-factor loader so the Quant
    Lab and the factors page rank the same price universe."""
    from engine.equity_factors import _closes as ef_closes
    px = ef_closes("broad")
    if px is None or px.empty:
        return pd.DataFrame()
    if asof is not None:
        px = px.loc[:pd.Timestamp(asof)]
    return px


# ---------------------------------------------------------------------------------------
# Fundamental legs
# ---------------------------------------------------------------------------------------
def _safe_div(a, b):
    """Ratio guarded on a STRICTLY POSITIVE denominator.

    Negative denominators are the trap: EBIT / negative-EV and NOPAT / negative-invested-
    capital both produce large NEGATIVE ratios for names that are, if anything, extreme on
    the leg. Ranking those as "worst" is a silent mislabel, so they go NaN and are counted
    as uncovered instead.
    """
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return a / b.where(b > 0)


def _fundamental_legs(kn: pd.DataFrame, cd: pd.DataFrame,
                      mktcap: pd.Series) -> pd.DataFrame:
    """Per-ticker legs from the knowable multi-year slice."""
    kn = kn.copy()
    kn["_cash"] = pd.Series(cd["cash"].reindex(kn["ticker"]).to_numpy(), index=kn.index)
    # Prefer the quarterly total debt (long-term + current); fall back to the annual
    # panel's long-term-only figure, which understates leverage but keeps the name rankable.
    kn["_debt"] = pd.Series(cd["total_debt"].reindex(kn["ticker"]).to_numpy(), index=kn.index) \
        .fillna(pd.to_numeric(kn["debt_lt"], errors="coerce"))

    ebit = pd.to_numeric(kn["op_income"], errors="coerce")
    equity = pd.to_numeric(kn["equity"], errors="coerce")
    assets = pd.to_numeric(kn["assets"], errors="coerce")

    # Invested capital = equity + total debt - cash. Cash is netted only when known;
    # otherwise invested capital is overstated and ROIC understated (the conservative side).
    kn["_invcap"] = equity.add(kn["_debt"], fill_value=0.0).sub(kn["_cash"].fillna(0.0))
    kn["_roic"] = _safe_div(ebit * (1.0 - TAX_RATE), kn["_invcap"])
    kn["_ebit"] = ebit
    kn["_gp_assets"] = _safe_div(pd.to_numeric(kn["gross_profit"], errors="coerce"), assets)
    kn["_gross_margin"] = _safe_div(pd.to_numeric(kn["gross_profit"], errors="coerce"),
                                    pd.to_numeric(kn["revenue"], errors="coerce"))
    kn["_accruals"] = -_safe_div(pd.to_numeric(kn["ni"], errors="coerce")
                                 - pd.to_numeric(kn["cfo"], errors="coerce"), assets)
    kn["_fcf"] = (pd.to_numeric(kn["cfo"], errors="coerce")
                  - pd.to_numeric(kn["capex"], errors="coerce").abs())
    kn["_fcf_to_debt"] = _safe_div(kn["_fcf"], kn["_debt"])

    g = kn.groupby("ticker")
    out = pd.DataFrame(index=sorted(kn["ticker"].unique()))

    # --- Quality: 3y average ROIC, and its growth ---------------------------------------
    out["roic_3y"] = g["_roic"].mean()
    latest = kn[kn["fy_rank"] == 0].set_index("ticker")["_roic"]
    oldest = kn.sort_values("fy_rank").groupby("ticker").tail(1).set_index("ticker")["_roic"]
    n_years = g["fy"].nunique()
    # Growth is only meaningful off a POSITIVE base, and only when we actually have a
    # multi-year window — a one-year ticker would otherwise report 0% growth, which reads
    # as "flat" when the truth is "unknown".
    base_ok = (oldest > 0) & (n_years >= 2)
    out["roic_growth"] = ((latest / oldest.where(base_ok)) - 1.0).reindex(out.index)

    # --- Value: 3y average EBIT / EV ----------------------------------------------------
    # EV is priced at the REBALANCE date and held across the averaged years (our market cap
    # is a single cross-section, not a history), so this is "current EV vs multi-year EBIT",
    # not a true 3y average of the ratio. Named in specs.py as the distortion it is.
    dbt = kn.sort_values("fy_rank").groupby("ticker").head(1).set_index("ticker")["_debt"]
    csh = kn.sort_values("fy_rank").groupby("ticker").head(1).set_index("ticker")["_cash"]
    ev = mktcap.reindex(out.index).add(dbt.reindex(out.index), fill_value=0.0) \
               .sub(csh.reindex(out.index).fillna(0.0))
    last = kn[kn["fy_rank"] == 0].set_index("ticker")
    out["ebit_ev_3y"] = _safe_div(g["_ebit"].mean().reindex(out.index), ev)
    out["ebit_ev"] = _safe_div(last["_ebit"].reindex(out.index), ev)   # latest-FY variant

    # --- Cash-generation legs (latest knowable FY) --------------------------------------
    for col, src in (("gross_profitability", "_gp_assets"), ("gross_margin", "_gross_margin"),
                     ("accruals", "_accruals"), ("fcf_to_debt", "_fcf_to_debt")):
        out[col] = last[src].reindex(out.index)
    out["accrual_ratio_cf"] = out["accruals"]
    return out


# ---------------------------------------------------------------------------------------
# Price legs
# ---------------------------------------------------------------------------------------
def _momentum_legs(px: pd.DataFrame, index) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    if px is None or px.empty:
        for k in TRADING_DAYS:
            out[f"momentum_{k}"] = np.nan
        return out
    for k, n in TRADING_DAYS.items():
        if len(px) > n:
            r = px.iloc[-1] / px.iloc[-1 - n] - 1.0
            out[f"momentum_{k}"] = r.reindex(index)
        else:
            out[f"momentum_{k}"] = np.nan
    # The published screen's "combined 3-month and 6-month Price Index".
    m3, m6 = out.get("momentum_3m"), out.get("momentum_6m")
    if m3 is not None and m6 is not None:
        out["momentum_3_6"] = pd.concat([m3.rank(pct=True), m6.rank(pct=True)], axis=1).mean(axis=1)
    return out


def _mktcap(kn: pd.DataFrame, px: pd.DataFrame) -> pd.Series:
    """Shares (latest knowable FY) x last close at/before asof."""
    if px is None or px.empty:
        return pd.Series(dtype=float)
    last_px = px.iloc[-1]
    sh = kn[kn["fy_rank"] == 0].set_index("ticker")
    shares = pd.to_numeric(sh.get("shares"), errors="coerce")
    if "shares_dei" in sh.columns:                    # dei cover-page count is fresher
        shares = pd.to_numeric(sh["shares_dei"], errors="coerce").fillna(shares)
    return (shares * last_px.reindex(shares.index)).replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------------------
# Fund sentiment (proxy)
# ---------------------------------------------------------------------------------------
def _fund_sentiment(asof=None) -> pd.Series:
    """QoQ growth in shares held, summed across the funds we track.

    NOT Fintel's leg. Fintel reads the whole 13F register (444 owners for AMR); we track 53
    curated managers, so this measures what a hand-picked set of funds did. Returned anyway
    because the alternative is a silently missing leg, and a named proxy is auditable while
    an absence is not.
    """
    root = config.data_dir() / "smart_money"
    if not root.exists():
        return pd.Series(dtype=float)
    rows = []
    for fund in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(fund.glob("*.parquet")):
            try:
                d = pd.read_parquet(f, columns=["cusip", "issuer", "shares",
                                                "period_end", "filing_date"])
            except Exception:                          # noqa: BLE001 — a bad shard must not kill the leg
                continue
            rows.append(d)
    if not rows:
        return pd.Series(dtype=float)
    d = pd.concat(rows, ignore_index=True)
    d["filing_date"] = pd.to_datetime(d["filing_date"], errors="coerce", utc=True).dt.tz_localize(None)
    d["period_end"] = pd.to_datetime(d["period_end"], errors="coerce")
    if asof is not None:
        d = d[d["filing_date"] <= pd.Timestamp(asof)]
    d = d.dropna(subset=["period_end"])
    if d.empty:
        return pd.Series(dtype=float)

    # 13F rows key on CUSIP + issuer NAME, never on ticker — reuse the smart-money
    # resolver (CUSIP exact, then normalised issuer name) rather than a second mapper.
    # A private one here would drift from the one the stock pages already use, and
    # "two CUSIP mappers disagree" is a defect class this repo has paid for before.
    try:
        from engine.smart_money import full_cusip_map, name_ticker_map, resolve_tickers
        cusip_map, _ = full_cusip_map()
        d = resolve_tickers(d, name_ticker_map(), cusip_map)
    except Exception as e:                             # noqa: BLE001 — leg degrades to absent, never fatal
        log.warning("quant_lab: 13F ticker resolution failed (%s) — fund_sentiment absent", e)
        return pd.Series(dtype=float)
    d = d.dropna(subset=["ticker"])
    if d.empty:
        return pd.Series(dtype=float)

    tot = d.groupby(["ticker", "period_end"])["shares"].sum().reset_index()
    tot = tot.sort_values("period_end")
    last2 = tot.groupby("ticker").tail(2)
    piv = last2.pivot_table(index="ticker", columns="period_end", values="shares")
    if piv.shape[1] < 2:
        return pd.Series(dtype=float)
    cur, prev = piv.iloc[:, -1], piv.iloc[:, -2]
    return ((cur / prev.where(prev > 0)) - 1.0).dropna()


# ---------------------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------------------
LEG_KEYS = [
    "roic_3y", "roic_growth", "ebit_ev_3y", "ebit_ev", "gross_profitability",
    "gross_margin", "accruals", "accrual_ratio_cf", "fcf_to_debt",
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m", "momentum_3_6",
    "fund_sentiment",
]


def compute_legs(asof=None, *, years: int = AVG_YEARS,
                 with_fund_sentiment: bool = True) -> dict:
    """Point-in-time leg cross-section.

    Returns {"legs": DataFrame(ticker x leg), "coverage": {leg: fraction}, "asof": str,
    "n_universe": int}. Coverage is returned, never inferred by the caller: several legs are
    computable on well under half the panel and a surface that shows the values without the
    coverage invites reading a 300-name rank as a 1,500-name rank.
    """
    kn = knowable(asof, years=years)
    if kn.empty:
        return {"legs": pd.DataFrame(), "coverage": {}, "asof": str(asof), "n_universe": 0}

    px = _closes(asof)
    mcap = _mktcap(kn, px)
    cd = _cash_and_debt(asof)
    legs = _fundamental_legs(kn, cd, mcap)
    legs = legs.join(_momentum_legs(px, legs.index))

    if with_fund_sentiment:
        fs = _fund_sentiment(asof)
        legs["fund_sentiment"] = fs.reindex(legs.index) if len(fs) else np.nan
    else:
        legs["fund_sentiment"] = np.nan

    legs = legs.reindex(columns=[c for c in LEG_KEYS if c in legs.columns])
    legs = legs.replace([np.inf, -np.inf], np.nan)
    n = len(legs)
    coverage = {c: (round(float(legs[c].notna().mean()), 4) if n else 0.0) for c in legs.columns}
    asof_str = (str(pd.Timestamp(asof).date()) if asof is not None
                else (str(px.index[-1].date()) if px is not None and len(px) else "live"))
    return {"legs": legs, "coverage": coverage, "asof": asof_str, "n_universe": n,
            "mktcap": mcap, "years": years, "tax_rate": TAX_RATE}
