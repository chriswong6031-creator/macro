"""Holdings accumulation signals — decompose ETF weight changes into a price
component and a residual (genuine rebalance / accumulation) component.

For a market-cap-weighted index fund a holding's weight rises mostly because its
price rose versus peers, NOT because anyone "favored" it. So each holding's
weight change is split:

    w_price = w0 * (1 + r_stock) / (1 + r_fund)   # weight if the basket were untouched
    active  = w1 - w_price                          # the signal: pp of weight beyond price

On the PASSIVE sector SPDRs the residual is real institutional flow — index funds
worldwide must buy when a name's float-adjusted index weight rises (reconstitution
/ float updates) — but it is NOT discretionary manager conviction. That reading
belongs to ACTIVE funds (Phase 2), where the same residual is genuine conviction.
See DECISIONS D70 and LIMITATIONS.md.

Needs >= 2 daily snapshots in data/sector_holdings/<FUND>.parquet to produce
anything; returns None / [] gracefully until history accumulates. The math core,
`decompose`, is a pure function (directly unit-tested); everything else is a thin
store-backed reader on top of it.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# Cycle-ladder states that confirm an accumulation read (the stock is also
# basing / turning up technically) — keys match engine.cycles STATE_STYLES.
BULLISH_STATES = {"FRESH BUY", "TURN SIGNALED", "RALLY ON", "BOTTOM WATCH"}

DECOMP_COLS = ["w0", "w1", "raw_change", "w_price", "active_change", "active_pct"]


def _cfg() -> dict:
    return config.load().get("holdings_signals", {})


def decompose(w0: pd.Series, w1: pd.Series, r_stock: pd.Series,
              r_fund: float) -> pd.DataFrame:
    """Split each holding's weight change into price-driven and residual parts.

    w0, w1   : weight_pct (0-100) indexed by ticker, the two snapshots.
    r_stock  : fractional return of each stock over [t0, t1], indexed by ticker.
    r_fund   : fractional return of the fund itself over [t0, t1] (scalar).

    Returns one row per ticker present in BOTH snapshots that also has a return:
    w0, w1, raw_change, w_price, active_change, active_pct. `active_change`
    (percentage points) is weight growth beyond what price action alone explains —
    the accumulation/rebalance signal — and `active_pct` expresses it relative to
    the price-implied weight. Sorted by active_change desc.
    """
    common = w0.index.intersection(w1.index).intersection(r_stock.dropna().index)
    if len(common) == 0:
        return pd.DataFrame(columns=DECOMP_COLS)
    w0c, w1c, rc = w0[common].astype(float), w1[common].astype(float), r_stock[common].astype(float)
    denom = 1.0 + r_fund
    w_price = w0c * (1.0 + rc) / denom
    raw = w1c - w0c
    active = w1c - w_price
    active_pct = 100.0 * active / w_price.where(w_price != 0)
    out = pd.DataFrame({
        "w0": w0c.round(4), "w1": w1c.round(4), "raw_change": raw.round(4),
        "w_price": w_price.round(4), "active_change": active.round(4),
        "active_pct": active_pct.round(2),
    })
    return out.sort_values("active_change", ascending=False)


def _period_return(close: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> float | None:
    """Fractional return between the closes nearest to (<=) t0 and t1."""
    s = close.dropna()
    if s.empty:
        return None
    s1 = s[s.index <= t1]
    s0 = s[s.index <= t0]
    if s0.empty or s1.empty:
        return None
    p0, p1 = s0.iloc[-1], s1.iloc[-1]
    if pd.isna(p0) or pd.isna(p1) or p0 == 0:
        return None
    return float(p1 / p0 - 1.0)


def _latest_aum(fund: str, asof: pd.Timestamp) -> float | None:
    fl = store.read("flows", fund)
    if fl is None or "aum_mn" not in fl:
        return None
    fl = fl.dropna(subset=["aum_mn"])
    fl = fl[fl.index <= asof]
    if fl.empty:
        return None
    return float(fl["aum_mn"].iloc[-1])


def weight_decomposition(fund: str, lookback_days: int | None = None) -> pd.DataFrame | None:
    """Price-decomposed weight changes for one sector fund's top-10 holdings.
    Returns None until >= 2 snapshots exist or if the fund's own return can't be
    computed (we never fabricate the denominator)."""
    cfg = _cfg()
    lookback_days = lookback_days or cfg.get("lookback_days", 5)
    df = store.read("sector_holdings", fund)
    if df is None or df.empty or "ticker" not in df.columns:
        return None
    df.index = pd.to_datetime(df.index)
    dates = sorted(df.index.unique())
    if len(dates) < 2:
        return None
    t1 = dates[-1]
    cutoff = t1 - pd.Timedelta(days=lookback_days)
    earlier = [d for d in dates if d <= cutoff]
    t0 = earlier[-1] if earlier else dates[0]

    w0 = df.loc[[t0]].set_index("ticker")["weight_pct"].astype(float)
    snap1 = df.loc[[t1]].set_index("ticker")
    w1 = snap1["weight_pct"].astype(float)
    names = snap1["name"] if "name" in snap1.columns else pd.Series(dtype=str)

    etf = store.read("yahoo", fund)
    if etf is None or "close" not in etf:
        return None
    r_fund = _period_return(etf["close"], t0, t1)
    if r_fund is None:
        return None

    r_stock: dict[str, float] = {}
    for tk in w0.index.union(w1.index):
        px = store.read("stocks", str(tk).replace(".", "-"))
        if px is None or "close" not in px:
            continue
        r = _period_return(px["close"], t0, t1)
        if r is not None:
            r_stock[tk] = r
    r_stock_s = pd.Series(r_stock, dtype=float)
    if r_stock_s.empty:
        return None

    dec = decompose(w0, w1, r_stock_s, r_fund)
    if dec.empty:
        return None
    dec["name"] = [str(names.get(t, "")) for t in dec.index]
    dec["r_stock"] = r_stock_s.reindex(dec.index)
    dec["r_fund"] = r_fund
    dec["t0"], dec["t1"] = str(t0.date()), str(t1.date())
    aum = _latest_aum(fund, t1)
    dec["est_flow_mn"] = (dec["active_change"] / 100.0 * aum) if aum else float("nan")
    return dec


def _live_macro_context() -> tuple[str | None, float | None]:
    """(net-liquidity regime, macro-risk drag) from regime/latest.json; (None,None)
    if unavailable. Lets the accumulation/ETF overlays pass the SAME macro context
    into analyze() that the sector cards use, so the overlay ladder can no longer
    disagree with the card for the same stock."""
    import json
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None, None
    try:
        j = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None, None
    liq = j.get("liquidity_overlay")
    liq = liq if liq in ("expanding", "contracting", "neutral") else None
    drag = (j.get("macro_risk") or {}).get("score")
    return liq, (float(drag) if isinstance(drag, (int, float)) else None)


def _ladder_for(ticker: str, min_hist: int, *, liquidity: str | None = None,
                macro_drag: float | None = None, macro_beta: float = 0.0) -> dict | None:
    """The stock's calibrated cycle/ladder state — the 'is a buy signal forming?'
    confirmation layer. Reuses engine.cycles.analyze; None if too little history.

    Threads the live macro context (net-liquidity regime, macro-risk drag × this
    name's sector beta) so this overlay ladder matches the sector-card ladder for
    the same stock; defaults keep it a no-op. Crypto tickers (-USD) get the crypto
    cycle preset, mirroring build_stock_library."""
    px = store.read("stocks", str(ticker).replace(".", "-"))
    if px is None or "close" not in px or len(px) < min_hist:
        return None
    try:
        from engine.cycles import analyze
        kind = "crypto" if str(ticker).endswith("-USD") else "equity"
        lad = analyze(px["close"], px.get("high"), kind=kind, liquidity=liquidity,
                      macro_drag=macro_drag, macro_beta=macro_beta).get("ladder")
    except Exception as e:  # noqa: BLE001 — confirmation is additive, never fatal
        log.debug("cycle read failed for %s: %s", ticker, e)
        return None
    if not lad:
        return None
    return {"state": lad["state"], "label": lad["label"], "action": lad["action"],
            "urgency": lad["entry"]["urgency"], "tag": lad["entry"]["tag"]}


def volume_surge(ticker: str, recent: int = 5, base: int = 20) -> dict | None:
    """Is the stock trading on rising volume? Ratio of the last `recent` days'
    average volume to the prior `base` days' average. Volume is captured by
    StockPriceAdapter going forward (older parquets lack it until a full-history
    backfill), so this returns None until enough volume history exists — a
    confirmation enhancer, never required."""
    px = store.read("stocks", str(ticker).replace(".", "-"))
    if px is None or "volume" not in px.columns:
        return None
    v = pd.to_numeric(px["volume"], errors="coerce").dropna()
    if len(v) < recent + base:
        return None
    recent_avg = v.iloc[-recent:].mean()
    base_avg = v.iloc[-(recent + base):-recent].mean()
    if not base_avg or base_avg <= 0:
        return None
    ratio = float(recent_avg / base_avg)
    x = config.load()["holdings_signals"].get("volume_surge_x", 1.5)
    return {"ratio": round(ratio, 2), "surging": ratio >= x}


def accumulation_signals(fund: str, *, liquidity: str | None = None,
                         macro_drag: float | None = None,
                         macro_beta: float | None = None) -> list[dict]:
    """Holdings whose residual weight change clears the config threshold, each
    enriched with the stock's cycle state. `confirmed` = accumulating AND the
    stock is technically basing/turning up (the strongest combination).

    `liquidity`/`macro_drag`/`macro_beta` are threaded into each holding's ladder
    so the overlay matches the sector card. macro_beta defaults to the FUND's
    sector sensitivity (all holdings sit in that sector)."""
    cfg = _cfg()
    pp = cfg.get("active_change_pp", 0.15)
    pct = cfg.get("active_change_pct", 8)
    min_hist = cfg.get("min_price_history", 60)
    if macro_beta is None:
        try:
            from engine.conditions import sector_macro_beta
            macro_beta = sector_macro_beta(fund)
        except Exception:  # noqa: BLE001 — macro overlay is additive; absent on some builds
            macro_beta = 0.0
    dec = weight_decomposition(fund)
    if dec is None:
        return []
    flagged = dec[(dec["active_change"].abs() >= pp) | (dec["active_pct"].abs() >= pct)]
    out = []
    for tk, row in flagged.iterrows():
        ladder = _ladder_for(str(tk), min_hist, liquidity=liquidity,
                             macro_drag=macro_drag, macro_beta=macro_beta)
        direction = "accumulating" if row["active_change"] > 0 else "distributing"
        confirmed = bool(
            direction == "accumulating" and ladder
            and (ladder["state"] in BULLISH_STATES
                 or ladder["urgency"] in ("now", "imminent", "soon")))
        out.append({
            "fund": fund, "ticker": str(tk), "name": str(row.get("name", "")).title(),
            "w0": float(row["w0"]), "w1": float(row["w1"]),
            "raw_change": float(row["raw_change"]),
            "active_change": float(row["active_change"]),
            "active_pct": float(row["active_pct"]) if pd.notna(row["active_pct"]) else None,
            "est_flow_mn": float(row["est_flow_mn"]) if pd.notna(row["est_flow_mn"]) else None,
            "t0": row["t0"], "t1": row["t1"],
            "direction": direction, "ladder": ladder, "confirmed": confirmed,
            "vol": volume_surge(str(tk)),
        })
    return sorted(out, key=lambda r: -abs(r["active_change"]))


def all_accumulation_signals() -> list[dict]:
    """Flattened, magnitude-sorted accumulation signals across every sector SPDR."""
    funds = config.load()["sponsors"]["sector_funds"]
    liq, drag = _live_macro_context()
    out: list[dict] = []
    for fund in funds:
        try:
            out.extend(accumulation_signals(fund, liquidity=liq, macro_drag=drag))
        except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
            log.error("accumulation_signals %s failed: %s", fund, e)
    return sorted(out, key=lambda r: -abs(r["active_change"]))


def top_sector_residuals(n: int = 12) -> list[dict]:
    """The strongest residual ('active') weight movers across every sector SPDR,
    ranked by |active_change| and enriched with each name's cycle state — for the
    display-only Accumulation-watch panel.

    Unlike ``all_accumulation_signals`` this does NOT gate on the alert threshold:
    on passive sector SPDRs the residual (weight growth beyond price) is small by
    construction (~0.01–0.05pp), so the thresholded list is almost always empty and
    the panel reads as broken. This always surfaces the top movers so the panel
    shows the genuine 'where is weight accumulating beyond price' read, however
    small — honestly labelled as index-reconstitution flow, never scored.

    Cheap-then-rich: rank on the already-computed decompositions (cheap) and only
    run the per-name cycle/ladder lookup on the top ``n`` (the expensive part)."""
    funds = config.load()["sponsors"]["sector_funds"]
    pool: list[tuple[str, str, "pd.Series"]] = []
    for fund in funds:
        try:
            dec = weight_decomposition(fund)
        except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
            log.error("weight_decomposition %s failed: %s", fund, e)
            continue
        if dec is None or dec.empty:
            continue
        for tk, row in dec.iterrows():
            ac = row.get("active_change")
            if ac is None or pd.isna(ac) or float(ac) == 0.0:
                continue
            pool.append((fund, str(tk), row))
    pool.sort(key=lambda x: -abs(float(x[2]["active_change"])))
    pool = pool[:n]

    liq, drag = _live_macro_context()
    min_hist = _cfg().get("min_price_history", 60)
    betas: dict[str, float] = {}
    out: list[dict] = []
    for fund, tk, row in pool:
        if fund not in betas:
            try:
                from engine.conditions import sector_macro_beta
                betas[fund] = sector_macro_beta(fund)
            except Exception:  # noqa: BLE001 — macro overlay is additive
                betas[fund] = 0.0
        ladder = _ladder_for(tk, min_hist, liquidity=liq, macro_drag=drag,
                             macro_beta=betas[fund])
        direction = "accumulating" if row["active_change"] > 0 else "distributing"
        confirmed = bool(
            direction == "accumulating" and ladder
            and (ladder["state"] in BULLISH_STATES
                 or ladder["urgency"] in ("now", "imminent", "soon")))
        out.append({
            "fund": fund, "ticker": tk, "name": str(row.get("name", "")).title(),
            "w0": float(row["w0"]), "w1": float(row["w1"]),
            "raw_change": float(row["raw_change"]),
            "active_change": float(row["active_change"]),
            "active_pct": float(row["active_pct"]) if pd.notna(row["active_pct"]) else None,
            "est_flow_mn": float(row["est_flow_mn"]) if pd.notna(row["est_flow_mn"]) else None,
            "t0": row["t0"], "t1": row["t1"],
            "direction": direction, "ladder": ladder, "confirmed": confirmed,
            "vol": volume_surge(tk),
        })
    return out


# --------------------------------------------------------------------------- #
# Sector lookup — the GICS sector each stock belongs to, so the radar can show it
# and the per-stock page can answer "which sector fund is buying me". Reuses the
# breadth/midcap/smallcap constituents tables (symbol -> name, sector) that the
# stock library already builds; cached once per process.
# --------------------------------------------------------------------------- #
_SECTOR_MAP: dict[str, str] | None = None


def _sector_map() -> dict[str, str]:
    global _SECTOR_MAP
    if _SECTOR_MAP is not None:
        return _SECTOR_MAP
    m: dict[str, str] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001 — a corrupt cache must not break the radar
            log.warning("sector map %s unreadable: %s", grp, e)
            continue
        if "sector" not in df.columns:
            continue
        for sym, sec in df["sector"].items():
            key = str(sym).replace(".", "-").upper()
            if key not in m and isinstance(sec, str) and sec:
                m[key] = sec
    _SECTOR_MAP = m
    return m


def _sector_for(ticker: str, fallback: str = "") -> str:
    """GICS sector for a US-listed ticker, else the fund's theme as a fallback
    (foreign holdings have no GICS row)."""
    return _sector_map().get(str(ticker).replace(".", "-").upper(), fallback)


# --------------------------------------------------------------------------- #
# Phase 2 — broad ETF universe. SHARE-BASED flow-normalized active decisions
# (collectors.holdings.active_changes_dir): needs no per-stock prices, so it
# scales across the whole universe. On ACTIVE funds (ARK) the signal is genuine
# manager conviction; on PASSIVE index/sector ETFs it is index reconstitution /
# rebalance flow — the page labels each honestly. See D71.
# --------------------------------------------------------------------------- #

def etf_signals(etf: str, *, base_dir=None, is_active: bool = False,
                meta: dict | None = None) -> list[dict]:
    """Flagged holdings for one ETF from full-holdings snapshots: positions whose
    flow-normalized share change clears `active_change_alert_pct` and whose weight
    clears `min_position_pct`, each tagged active/passive + (where the stock has
    price history) its cycle state."""
    from pathlib import Path

    from collectors.holdings import active_changes_dir
    cfg = config.load()["etf_holdings"]
    thresh = cfg.get("active_change_alert_pct", 15)
    min_w = cfg.get("min_position_pct", 0.20)
    min_conv = cfg.get("min_conviction_pp", 0.05)
    min_base_frac = cfg.get("min_base_frac", 1e-6)
    window = cfg.get("active_change_window_d", 5)
    min_hist = config.load()["holdings_signals"].get("min_price_history", 60)
    meta = meta or {}
    # match the sector cards' macro context; per-holding sector beta is unknown for
    # the mixed ETF universe, so only the liquidity/drag context is threaded here.
    liq, drag = _live_macro_context()

    base = Path(base_dir or config.data_dir() / "etf_holdings") / etf
    ch = active_changes_dir(base, window, min_base_frac=min_base_frac,
                            include_lifecycle=True)
    if ch is None or ch.empty:
        return []
    snaps = sorted(base.glob("*.parquet"))
    latest = pd.read_parquet(snaps[-1]).copy()
    # weight + name columns differ by sponsor (etf_holdings: weight_pct/name;
    # ARK watchlist: weight/company) — resolve both.
    wcol = next((c for c in latest.columns if "weight" in c.lower()), None)
    ncol = next((c for c in latest.columns if c.lower() in ("name", "company")), None)
    if wcol:
        latest["_w"] = pd.to_numeric(
            latest[wcol].astype(str).str.replace(r"[,%$]", "", regex=True), errors="coerce")
        wmap = latest.groupby("ticker")["_w"].last()
    else:
        wmap = pd.Series(dtype=float)
    nmap = latest.groupby("ticker")[ncol].last() if ncol else pd.Series(dtype=str)
    # fully-exited positions are absent from `latest`, so resolve their name from the
    # window-start snapshot active_changes_dir compared against.
    prior = pd.read_parquet(snaps[-(window + 1)] if len(snaps) > window else snaps[0])
    pncol = next((c for c in prior.columns if c.lower() in ("name", "company")), None)
    pnmap = prior.groupby("ticker")[pncol].last() if pncol else pd.Series(dtype=str)
    theme = meta.get("category", "")

    out = []
    for tk, row in ch.iterrows():
        is_new = bool(row.get("is_new", False))
        is_exit = bool(row.get("is_exit", False))
        pct = row["active_chg_pct"]
        # Existing positions must clear the share-% threshold; brand-new positions
        # and full exits have no meaningful % but are the strongest signals — pass.
        if not is_new and not is_exit and (pd.isna(pct) or abs(pct) < thresh):
            continue
        # Conviction needs a real weight (pp of fund committed) — a tiny position
        # doubling (0.1%->0.2%) is a big % but trivial conviction. For exits the
        # position is gone from `latest`, so use its carried PRIOR weight.
        w = row.get("prior_weight_pct") if is_exit else wmap.get(tk)
        if w is None or pd.isna(w) or abs(float(w)) < min_w:
            continue
        w = float(w)
        if is_new:
            conviction_pp, direction = round(w, 4), "accumulating"   # full weight in
        elif is_exit:
            conviction_pp, direction = round(-w, 4), "trimming"       # full weight out
        else:
            # active share of the CURRENT position (bounded), then expressed as pp
            # of fund weight: frac = (pct/100)/(1+pct/100); conviction_pp = w*frac.
            denom = 1.0 + pct / 100.0
            frac = -1.0 if abs(denom) < 1e-9 else (pct / 100.0) / denom
            conviction_pp = round(w * frac, 4)
            direction = "accumulating" if pct > 0 else "trimming"
        if abs(conviction_pp) < min_conv:
            continue
        ladder = _ladder_for(str(tk), min_hist, liquidity=liq, macro_drag=drag)
        confirmed = bool(direction == "accumulating" and ladder
                         and (ladder["state"] in BULLISH_STATES
                              or ladder["urgency"] in ("now", "imminent", "soon")))
        name = nmap.get(tk) or pnmap.get(tk, "") if is_exit else nmap.get(tk, "")
        out.append({
            "etf": etf, "etf_name": meta.get("name", etf),
            "category": theme, "is_active": is_active,
            "ticker": str(tk), "name": str(name or "").title(),
            "sector": _sector_for(str(tk), theme),
            "weight_pct": w,
            "active_chg_pct": (None if is_new else float(pct)),
            "conviction_pp": conviction_pp, "is_new": is_new, "is_exit": is_exit,
            "active_share_chg": float(row["active_share_chg"]),
            "window": f"{row['window_start']}..{row['window_end']}",
            "direction": direction, "ladder": ladder, "confirmed": confirmed,
            "vol": volume_surge(str(tk)),
        })
    return out


def all_etf_signals() -> list[dict]:
    """Every flagged, conviction-scored holding decision across the curated
    thematic/active ETF universe (data/etf_holdings) plus the active watchlist
    (data/holdings, e.g. ARK). Unsorted; callers split into accumulation / trims."""
    cfg = config.load()
    out: list[dict] = []
    for etf, spec in cfg["etf_holdings"].get("universe", {}).items():
        try:
            out.extend(etf_signals(etf, is_active=bool(spec.get("active", False)), meta=spec))
        except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
            log.error("etf_signals %s failed: %s", etf, e)
    holdings_dir = config.ROOT / cfg["storage"]["holdings_dir"]
    for etf in cfg["holdings"].get("watchlist", {}):
        try:
            out.extend(etf_signals(etf, base_dir=holdings_dir, is_active=True,
                                   meta={"name": etf, "category": "Active / Innovation"}))
        except Exception as e:  # noqa: BLE001
            log.error("etf_signals %s (watchlist) failed: %s", etf, e)
    return out


def split_by_conviction(rows: list[dict], n: int | None = None,
                        trims_n: int | None = None) -> dict[str, list[dict]]:
    """Split signal rows into a positive-first accumulation list (the actionable
    side the user cares about) and a smaller, de-emphasized trims list, each
    ranked by conviction (pp of fund weight committed), NOT raw share %."""
    cfg = config.load()["etf_holdings"]
    n = n or cfg.get("page_top_n", 40)
    trims_n = trims_n if trims_n is not None else cfg.get("trims_top_n", 12)
    acc = sorted((r for r in rows if (r.get("conviction_pp") or 0) > 0),
                 key=lambda r: -r["conviction_pp"])[:n]
    trims = sorted((r for r in rows if (r.get("conviction_pp") or 0) < 0),
                   key=lambda r: r["conviction_pp"])[:trims_n]
    return {"accumulation": acc, "trims": trims}


def top_etf_accumulation(n: int | None = None, trims_n: int | None = None) -> dict[str, list[dict]]:
    """Conviction-ranked fund decisions for the radar page: {accumulation, trims}.
    Accumulation (positive conviction) is the headline; trims are secondary."""
    return split_by_conviction(all_etf_signals(), n=n, trims_n=trims_n)
