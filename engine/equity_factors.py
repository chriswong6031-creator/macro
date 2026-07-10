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
    "sue": "Earnings momentum (SUE)",
}


# SUE panel is read once per process (the backtest calls compute_factors per date).
_SUE_PANEL_CACHE: list = []


def _load_ic_scorecard() -> dict:
    """Read data/edgar/ic_scorecard.json — the deep-history (leak-free) per-factor IC/FDR
    verdict. Absent/malformed -> {} (then the ranking composite falls back to the safe legs
    hard-list). Audit #25: the RANKING composite may only consume legs this scorecard blesses."""
    try:
        import json
        p = config.data_dir() / "edgar" / "ic_scorecard.json"
        if p.exists():
            d = json.loads(p.read_text())
            if isinstance(d, dict):
                return d
    except Exception as e:  # noqa: BLE001 — a missing/broken scorecard must never break the build
        log.warning("equity_factors: ic_scorecard read failed (%s)", e)
    return {}


def _rank_leg_weights(candidate_legs: list[str], scorecard: dict) -> dict[str, float]:
    """Audit #25 firewall — the legs allowed into the RANK-facing composite, IC-weighted with
    a SIGN constraint. A leg qualifies only if its measured mean_ic is POSITIVE (a negative-IC
    leg like low_vol -0.021 or investment -0.003 would rank names in an anti-predictive
    direction). Weight = positive mean_ic (magnitude-aware); FDR-survivors get a small bonus.
    Empty -> the caller keeps the display composite out of the rank path entirely."""
    facs = (scorecard or {}).get("factors") or {}
    weights: dict[str, float] = {}
    for leg in candidate_legs:
        meta = facs.get(leg)
        if not isinstance(meta, dict):
            continue                              # unmeasured leg -> excluded from rank key
        mic = meta.get("mean_ic")
        if mic is None or float(mic) <= 0:
            continue                              # negative / zero IC -> excluded (sign constraint)
        w = float(mic)
        if meta.get("survives_fdr"):
            w *= 1.5                               # the lone FDR survivor leads
        weights[leg] = w
    return weights


def _sue_signal(asof, price_date, index) -> "pd.Series | None":
    """Point-in-time raw SUE per ticker, reindexed to the factor universe. `asof` (a
    date) is the backtest rebalance; live mode (asof=None) uses the latest price date.
    Returns None when the quarterly EPS panel has not been built."""
    if not _SUE_PANEL_CACHE:
        from engine.sue import load_panel
        _SUE_PANEL_CACHE.append(load_panel())
    panel = _SUE_PANEL_CACHE[0]
    if panel is None:
        return None
    from engine.sue import sue_cross_section
    when = pd.Timestamp(asof) if asof is not None else (
        pd.Timestamp(price_date) if price_date is not None else None)
    if when is None:
        return None
    return sue_cross_section(panel, when).reindex(index)


def _short_interest() -> pd.DataFrame | None:
    p = config.data_dir() / "finra" / "short_interest.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    return df if not df.empty else None


def _insider_block(ns: dict, mktcap: pd.Series | None = None) -> dict | None:
    """Insider-conviction leaderboard from SEC Form-4. Prefers the point-in-time
    per-transaction PANEL ranked by net buying as a FRACTION OF MARKET CAP — the
    construction validated in research/INSIDER_FACTOR.md (Phase-0 PIT FDR survivor;
    orthogonal to momentum/size). That removes the large-cap dollar bias of a raw
    net-$ sum, so a high-conviction small/mid-cap buy isn't drowned by megacap noise,
    and adds the distinct-insider CLUSTER count.

    Fallback chain (Amendment 2 §C4 dead-path fix):
      1. Flat insider_panel.parquet exists → use it (may include intra-quarter data).
      2. Flat absent → concat data/sec_insider/panel/*.parquet on read (always
         available on any worktree that ran the backfill; gitignored flat is not).
      3. Neither panel path works → fall back to single-quarter aggregate (no
         6-month window, no cluster count, cluster=False in output)."""
    panel_p = config.data_dir() / "sec_insider" / "insider_panel.parquet"
    panel_dir = config.data_dir() / "sec_insider" / "panel"

    # Resolve the best panel path available: flat file preferred (may be fresher),
    # per-quarter directory as the worktree-safe fallback.
    effective_panel_p: object = None
    if panel_p.exists():
        effective_panel_p = panel_p
    elif panel_dir.exists() and any(panel_dir.glob("*.parquet")):
        effective_panel_p = panel_dir  # sentinel: directory → concat in _insider_block_panel

    if mktcap is not None and effective_panel_p is not None:
        blk = _insider_block_panel(ns, mktcap, effective_panel_p)
        if blk:
            return blk
    # No panel: still size-normalise the single-quarter aggregate when we have caps
    # (the core "% of cap" upgrade, live in CI without the heavy panel) — only the
    # 6-month window and true distinct-buyer clusters need the panel.
    return _insider_block_aggregate(ns, mktcap)


def _insider_block_panel(ns: dict, mktcap: pd.Series, panel_p) -> dict | None:
    cfg = config.load()["sec_insider"]
    months = int(cfg.get("panel_window_months", 6))
    n = int(cfg["panel_top_n"])
    # panel_p may be a Path to a flat .parquet file OR a Path to the per-quarter
    # directory (sent by _insider_block when the flat file is absent).
    import pathlib
    _cols = ["ticker", "filing_date", "code", "usd", "rptownercik"]
    if isinstance(panel_p, pathlib.Path) and panel_p.is_dir():
        parts = []
        for qp in sorted(panel_p.glob("*.parquet")):
            try:
                parts.append(pd.read_parquet(qp, columns=_cols))
            except Exception as exc:  # noqa: BLE001
                log.warning("_insider_block_panel: skipping %s — %s", qp.name, exc)
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_cols)
    else:
        df = pd.read_parquet(panel_p, columns=_cols)
    if df.empty:
        return None
    win = df[df["filing_date"] > df["filing_date"].max() - pd.DateOffset(months=months)]
    win = win[win["ticker"].isin(ns)]
    if win.empty:
        return None
    buys, sells = win[win["code"] == "P"], win[win["code"] == "S"]
    agg = pd.DataFrame({
        "buy_usd": buys.groupby("ticker")["usd"].sum(),
        "sell_usd": sells.groupby("ticker")["usd"].sum(),
        "n_buyers": buys.groupby("ticker")["rptownercik"].nunique(),
        "n_sellers": sells.groupby("ticker")["rptownercik"].nunique(),
    }).reindex(sorted(set(win["ticker"]))).fillna(0.0)
    agg["net_usd"] = agg["buy_usd"] - agg["sell_usd"]
    mc = mktcap.reindex(agg.index)
    agg["net_mcap_bps"] = (agg["net_usd"] / mc.where(mc > 0)) * 1e4   # net buying, bps of mcap
    agg = agg[agg["net_mcap_bps"].notna()]

    def rows(sub: pd.DataFrame) -> list[dict]:
        out = []
        for t, r in sub.iterrows():
            out.append({"ticker": t, "name": ns.get(t, (t, "—"))[0],
                        "sector": ns.get(t, (t, "—"))[1],
                        "net_usd_mn": round(float(r["net_usd"]) / 1e6, 2),
                        "net_mcap_bps": round(float(r["net_mcap_bps"]), 1),
                        "n_buyers": int(r["n_buyers"]), "n_sellers": int(r["n_sellers"]),
                        "buys": int(r["n_buyers"]), "sells": int(r["n_sellers"])})
        return out
    buying = agg[agg["net_usd"] > 0].nlargest(n, "net_mcap_bps")
    selling = agg[agg["net_usd"] < 0].nsmallest(n, "net_mcap_bps")
    label = f"{months}mo to {df['filing_date'].max():%Y-%m}"
    return {"quarter": label, "n_issuers": int(len(agg)), "basis": "net_mcap_bps",
            "cluster": True,   # n_buyers = distinct insiders
            "top_buying": rows(buying), "top_selling": rows(selling)}


def _insider_block_aggregate(ns: dict, mktcap: pd.Series | None = None,
                             path=None) -> dict | None:
    """Single-quarter aggregate leaderboard. When market caps are available, ranks by
    net buying as a FRACTION OF MARKET CAP (the size-normalised upgrade — works in CI
    from the quarterly insider.parquet alone, no panel needed); otherwise the legacy
    raw net-$ ranking. Counts here are buy/sell TRANSACTIONS (n_buys/n_sells), not
    distinct insiders — true clusters need the panel, so `cluster` is False."""
    import os
    p = path or config.data_dir() / "sec_insider" / "insider.parquet"
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    if df.empty or "net_usd" not in df.columns:
        return None
    norm = mktcap is not None
    if norm:
        mc = mktcap.reindex(df.index)
        df = df.copy()
        df["net_mcap_bps"] = (df["net_usd"] / mc.where(mc > 0)) * 1e4
        ranked = df[df["net_mcap_bps"].notna()]
    else:
        ranked = df

    def rows(sub: pd.DataFrame) -> list[dict]:
        out = []
        for t, r in sub.iterrows():
            row = {"ticker": t, "name": ns.get(t, (t, "—"))[0],
                   "sector": ns.get(t, (t, "—"))[1],
                   "net_usd_mn": round(float(r["net_usd"]) / 1e6, 2),
                   "buys": int(r.get("n_buys", 0)), "sells": int(r.get("n_sells", 0))}
            if norm:
                row["net_mcap_bps"] = round(float(r["net_mcap_bps"]), 1)
            out.append(row)
        return out
    n = config.load()["sec_insider"]["panel_top_n"]
    key = "net_mcap_bps" if norm else "net_usd"
    buying = ranked[ranked["net_usd"] > 0].nlargest(n, key)
    selling = ranked[ranked["net_usd"] < 0].nsmallest(n, key)
    return {"quarter": str(df["quarter"].iloc[0]) if "quarter" in df else None,
            "n_issuers": int(len(df)), "basis": ("net_mcap_bps" if norm else None),
            "cluster": False,
            "top_buying": rows(buying), "top_selling": rows(selling)}


def insider_signals(mktcap: pd.Series | None, *, months: int | None = None) -> dict[str, dict]:
    """Per-ticker insider-conviction read for the standout/setup CONFIRMER chip.

    Net open-market Form-4 buying over a trailing window as basis points of market
    cap (the validated ``net_mcap_bps`` construction — research/INSIDER_FACTOR.md, a
    Phase-0 PIT FDR survivor, orthogonal to momentum/size) plus the distinct-insider
    CLUSTER count. Returns ``{ticker: {bps, buyers, sellers, net_mn}}`` for every name
    with activity in the window (``bps`` is ``None`` when no market cap is available,
    so a cluster still surfaces); empty dict if the panel is missing. Reuses the same
    panel→aggregate logic as :func:`_insider_block_panel`. A confirmer leg only —
    orthogonal long-only conviction, NOT a standalone sizer."""
    panel_p = config.data_dir() / "sec_insider" / "insider_panel.parquet"
    panel_dir = config.data_dir() / "sec_insider" / "panel"
    cfg = config.load().get("sec_insider", {})
    months = int(cfg.get("panel_window_months", 6)) if months is None else months
    _cols = ["ticker", "filing_date", "code", "usd", "rptownercik"]
    if panel_p.exists():
        df = pd.read_parquet(panel_p, columns=_cols)
    elif panel_dir.exists() and any(panel_dir.glob("*.parquet")):
        # Flat file is gitignored — concat per-quarter directory (Amendment 2 §C4 fix).
        parts = []
        for qp in sorted(panel_dir.glob("*.parquet")):
            try:
                parts.append(pd.read_parquet(qp, columns=_cols))
            except Exception as exc:  # noqa: BLE001
                log.warning("insider_signals: skipping %s — %s", qp.name, exc)
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_cols)
    else:
        return {}
    if df.empty:
        return {}
    win = df[df["filing_date"] > df["filing_date"].max() - pd.DateOffset(months=months)]
    if win.empty:
        return {}
    buys, sells = win[win["code"] == "P"], win[win["code"] == "S"]
    agg = pd.DataFrame({
        "buy_usd": buys.groupby("ticker")["usd"].sum(),
        "sell_usd": sells.groupby("ticker")["usd"].sum(),
        "n_buyers": buys.groupby("ticker")["rptownercik"].nunique(),
        "n_sellers": sells.groupby("ticker")["rptownercik"].nunique(),
    }).fillna(0.0)
    agg["net_usd"] = agg["buy_usd"] - agg["sell_usd"]
    if mktcap is not None:
        mc = mktcap.reindex(agg.index)
        bps = (agg["net_usd"] / mc.where(mc > 0)) * 1e4
    else:
        bps = pd.Series(np.nan, index=agg.index)
    out: dict[str, dict] = {}
    for t in agg.index:
        b = bps.get(t)
        out[str(t)] = {
            "bps": (round(float(b), 1) if b is not None and np.isfinite(b) else None),
            "buyers": int(agg.at[t, "n_buyers"]), "sellers": int(agg.at[t, "n_sellers"]),
            "net_mn": round(float(agg.at[t, "net_usd"]) / 1e6, 2),
        }
    return out


# universe → which breadth caches define the price/name set. 'broad' = the full
# S&P 1500 (large+mid+small); 'narrow' = the S&P 500 large-cap (breadth cache only).
# 'deep' = the survivorship-BIASED deep-history close panel (data/edgar/sue_deep_closes
# .parquet — max-history adjusted closes for the EDGAR EPS universe, ~2011-2026), used by
# the deep-history factor IC scorecard so the whole zoo's IC/FDR is judged on >10y rather
# than the ~3y rolling breadth cache. Delisted names are absent (yahoo only serves the
# currently-listed), so the deep read is an OPTIMISTIC bound — see scripts/sue_deep_phase0.py
# + reports/sue-deep-history-phase0.md. The keyword default is 'broad' so every existing
# caller is unchanged.
_UNIVERSE_GROUPS = {"broad": ("breadth", "smallcap_breadth", "midcap_breadth"),
                    "narrow": ("breadth",)}

# Deep-history close panel — an offline backfill (not one of the daily breadth caches).
_DEEP_CLOSES_REL = ("edgar", "sue_deep_closes.parquet")


def _closes(universe: str = "broad") -> pd.DataFrame:
    """Close matrix from the breadth caches. 'broad' = combined S&P 1500;
    'narrow' = the S&P 500 large-cap cache only; 'deep' = the survivorship-biased
    deep-history panel (~2011-2026) used by the deep factor IC scorecard. The 'deep'
    panel is an offline artifact — returns an empty frame when it is not present (the
    caller then keeps the committed deep scorecard rather than writing a shallow one)."""
    if universe == "deep":
        p = config.data_dir().joinpath(*_DEEP_CLOSES_REL)
        if not p.exists():
            return pd.DataFrame()
        out = pd.read_parquet(p)
        out.index = pd.to_datetime(out.index)
        return out.loc[:, ~out.columns.duplicated()].sort_index()
    if universe == "debiased":
        # survivor breadth closes + recovered DEAD-name closes (Phase 1A). Self-gating:
        # when dead-price coverage is ~0 this returns exactly the broad cache, so the
        # de-biased scorecard equals the survivor one until CI accrues delisted prices.
        base = _closes("broad")
        try:
            from collectors.edgar_deadname_prices import dead_name_closes
            dead = dead_name_closes()
        except Exception:  # noqa: BLE001 — additive, never fatal
            dead = pd.DataFrame()
        if dead.empty:
            return base
        out = pd.concat([base, dead], axis=1)            # dead names are new columns
        return out.loc[:, ~out.columns.duplicated()].sort_index()
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
    # the deep panel carries no constituents table of its own → reuse the broad S&P 1500
    # labels (best-effort; the IC math only needs the numeric factor columns, so any
    # unlabeled deep-only ticker simply falls back to its symbol).
    groups = (_UNIVERSE_GROUPS["broad"] if universe == "deep"
              else _UNIVERSE_GROUPS.get(universe, _UNIVERSE_GROUPS["broad"]))
    out: dict[str, tuple[str, str]] = {}
    for grp in groups:
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


# Split-staleness guard on EDGAR share counts. The EDGAR frames cover-page
# share count only updates on the issuer's next 10-Q/K, so for the weeks after
# a stock split the live path multiplies a POST-split price by PRE-split shares
# and understates mktcap by the split ratio (BKNG 25:1 2026-04-06 -> cap ~25x
# low; KLAC 10:1 2026-06-12 -> ~10x; poisons mktcap_bn, value yields, si_pct
# and every profile.mktcap_bn consumer downstream). The committed Polygon
# reference the S&P 500 heatmap already trusts for tile sizing
# (data/sp500_heatmap/reference.parquet, weekly nightly sweep) carries CURRENT
# split-adjusted shares — prefer it when it materially disagrees with the
# filing (>= _SHARES_DISAGREE_X either way, which also catches reverse splits
# and large issuance EDGAR hasn't printed yet) and use it to fill names whose
# frames serve no share count at all (META / BRK-B multi-class quirks).
# S&P 500 coverage only; other names keep EDGAR shares and self-heal on the
# issuer's next filing. LIVE PATH ONLY — the point-in-time panel must never
# see today's share counts (that would be look-ahead).
_SHARES_DISAGREE_X = 1.5


def _reference_shares() -> pd.Series | None:
    """ticker -> current shares outstanding from the Polygon reference cache.
    None when the cache is absent (fresh checkout before the first nightly
    sweep) or unusable — callers then keep the EDGAR share counts."""
    p = config.data_dir() / "sp500_heatmap" / "reference.parquet"
    if not p.exists():
        return None
    try:
        ref = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — a broken cache must never break factors
        log.warning("equity_factors: shares reference unreadable (%s)", e)
        return None
    if "shares" not in ref.columns:
        return None
    s = pd.to_numeric(ref["shares"], errors="coerce").dropna()
    s = s[s > 0]
    return s if not s.empty else None


def _reconcile_shares(edgar: pd.Series) -> pd.Series:
    """EDGAR cover-page shares, overridden by the Polygon reference where the
    two materially disagree (stale post-split filing) or EDGAR has none."""
    ref = _reference_shares()
    if ref is None:
        return edgar
    ref = ref.reindex(edgar.index)
    ratio = ref / edgar.where(edgar > 0)
    stale = ratio.notna() & ((ratio >= _SHARES_DISAGREE_X)
                             | (ratio <= 1.0 / _SHARES_DISAGREE_X))
    fill = ref.notna() & ~(edgar > 0)          # NaN or non-positive filing count
    take = stale | fill
    if not take.any():
        return edgar
    worst = ratio[stale].sort_values(ascending=False)
    log.info("equity_factors: %d share count(s) from Polygon reference "
             "(%d stale vs filing, %d missing in EDGAR); largest gaps: %s",
             int(take.sum()), int(stale.sum()), int(fill.sum()),
             {t: round(float(r), 2) for t, r in worst.head(8).items()})
    return edgar.where(~take, ref)


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
        # de-biased mode: draw the PIT cross-section from the survivor+dead MERGED
        # panel (Phase 1B). Self-gating — dead rows without a recovered price are
        # dropped downstream, so when price coverage is ~0 this equals the survivor
        # cross-section and grows honest as CI accrues dead-name prices.
        merged = None
        if universe == "debiased":
            try:
                from collectors.edgar_deadnames import merged_panel
                merged = merged_panel()
            except Exception:  # noqa: BLE001 — additive, never fatal
                merged = None
        try:
            fund = as_of_cross_section(asof, merged)
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
    if asof is None:
        # live path only: PIT backtests must not see today's share counts
        d["shares"] = _reconcile_shares(d["shares"])
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
    # positioning: FINRA short interest (high days-to-cover / short % = bearish).
    # OMITTED for the deep-history universe AND for ANY point-in-time run (asof set):
    # FINRA SI has no point-in-time panel, so reusing the latest snapshot at a 2013
    # rebalance would be look-ahead — it would contaminate the historical IC scorecard
    # (factor_ic_scorecard runs universe='broad' WITH asof on a grid back to 2011).
    # Only the LIVE (asof=None) page keeps the current snapshot.
    si = None if (universe == "deep" or asof is not None) else _short_interest()
    if si is not None:
        dtc = si["days_to_cover"].reindex(d.index)
        si_pct = si["short_shares"].reindex(d.index) / d["shares"].where(d["shares"] > 0)
        raw["short_interest"] = -pd.concat([_winsor_z(dtc, cap), _winsor_z(si_pct, cap)],
                                           axis=1).mean(axis=1)
    # earnings momentum: SUE (standardized unexpected earnings) from the quarterly
    # EDGAR EPS panel. Standalone leg (not in the value/quality composite, like
    # short_interest) — it survives the leak-free BH-FDR scorecard as the strongest
    # positive factor (research/DATA_SIGNAL_EXPANSION_2026.md). The second-pass z below
    # standardizes the raw d/sigma SUE cross-sectionally.
    sue = _sue_signal(asof, closes.index[-1] if len(closes.index) else None, d.index)
    if sue is not None and sue.notna().any():
        raw["sue"] = sue

    # second-pass z (so each factor is a clean unit-variance score)
    fac = pd.DataFrame({c: _winsor_z(raw[c], cap) for c in raw.columns})

    composite_legs = [c for c in cfg["composite"] if c in fac.columns]
    avail = fac[composite_legs].notna()
    comp = fac[composite_legs].where(avail).mean(axis=1)
    comp[avail.sum(axis=1) < 3] = np.nan                          # need >=3 legs
    fac["composite"] = comp                                       # DISPLAY composite (blind EW mean)

    # Audit #25 — the RANK-facing composite. The blind equal-weight composite carries negative-IC
    # FDR-failing legs (low_vol -0.021, investment -0.003) and its OWN scorecard grades it
    # anti-predictive (ic_ir -0.049). So the board-ranking key is a SEPARATE IC-weighted composite
    # over ONLY the scorecard-passing (positive-IC) legs. Applied on the LIVE path only; a
    # point-in-time backtest run (asof set) keeps the raw composite so it can't contaminate the
    # scorecard that this very firewall reads.
    rank_legs: list[str] = []
    if asof is None:
        rw = _rank_leg_weights(composite_legs, _load_ic_scorecard())
        rank_legs = [c for c in composite_legs if c in rw]
        if rank_legs:
            wser = pd.Series({c: rw[c] for c in rank_legs})
            ravail = fac[rank_legs].notna()
            wsum = ravail.mul(wser, axis=1).sum(axis=1)
            crank = (fac[rank_legs].where(ravail).mul(wser, axis=1).sum(axis=1)) / wsum.where(wsum > 0)
            crank[ravail.sum(axis=1) < min(2, len(rank_legs))] = np.nan
            fac["composite_rank"] = crank
    if "composite_rank" not in fac.columns:
        fac["composite_rank"] = fac["composite"]                  # PIT / no-scorecard fallback
    all_factors = [c for c in fac.columns
                   if c not in ("composite", "composite_rank")]   # incl. standalone accruals / low_beta

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

    # audit #25 — per-leg FDR badges for the DISPLAY leaderboard (keep all legs, badge failers)
    sc_facs = (_load_ic_scorecard().get("factors") or {})
    fdr_badges = {c: {"mean_ic": (sc_facs.get(c) or {}).get("mean_ic"),
                      "ic_ir": (sc_facs.get(c) or {}).get("ic_ir"),
                      "survives_fdr": bool((sc_facs.get(c) or {}).get("survives_fdr")),
                      "negative_ic": ((sc_facs.get(c) or {}).get("mean_ic") is not None
                                      and float((sc_facs.get(c) or {}).get("mean_ic")) < 0)}
                  for c in fac.columns if c not in ("composite_rank",) and c in sc_facs}

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
        # RANK-facing board keys use the IC-weighted, scorecard-passing composite (audit #25).
        "composite_top": top("composite_rank", n),
        "composite_bottom": top("composite_rank", n, asc=True),
        # the blind equal-weight display composite is kept for the leaderboard, honestly badged.
        "composite_display_top": top("composite", n),
        "composite_display_bottom": top("composite", n, asc=True),
        "rank_legs": rank_legs,                       # which legs the rank composite is built from
        "fdr_badges": fdr_badges,                     # per-leg IC/FDR verdict for the leaderboard
        "composite_passport": {
            "rank_basis": "ic_weighted_scorecard_passing" if rank_legs else "display_fallback",
            "excluded_legs": [c for c in composite_legs if c not in rank_legs and asof is None],
            "note": ("board rank uses ONLY positive-IC scorecard legs (IC-weighted, sign-"
                     "constrained); negative-IC / FDR-failing legs are display-only badges "
                     "and cannot order a board a trader sizes from (audit #25)"),
            "artifact": "data/edgar/ic_scorecard.json"},
        "insider": _insider_block(ns, d["mktcap"] if "mktcap" in d.columns else None),
        "table": table.reset_index().rename(columns={"index": "ticker"}).to_dict("records"),
    }
