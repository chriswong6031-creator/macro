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
from datetime import date
from functools import lru_cache

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
# W1 — FLOW vs SELECTION (research/ETF_PAGE_UPGRADE_MASTERPLAN_BY_FABLE.md §2).
#
# A snapshot pair carries TWO signals the share-diff path collapses into one.
# Creation/redemption scales every constituent's share count by a common factor
# k (investors arriving in / leaving the theme, which mechanically buys or sells
# the constituents); whatever a position does beyond k is the manager's own
# decision:
#
#     Δshares = s1 - s0 = s0·(k-1)   +   (s1 - s0·k)
#                         └─ FLOW ─┘     └ SELECTION ┘
#
# k is the MEDIAN share ratio across continuing constituents: a split, a rename
# or one outsized position cannot move a median the way it moves the SUM ratio
# `active_changes_dir` uses. In pp-of-fund-weight the two parts share the basis
# the shipped conviction score already uses — pp(x) = w·x/s1 — so `selection_pp`
# IS `conviction_pp` re-derived on the robust k, and flow_pp + selection_pp =
# total_pp. `conviction_pp` itself is left exactly as it was.
# --------------------------------------------------------------------------- #

# A snapshot whose weights sum far from 100 is a broken parse, not a portfolio:
# decomposing against it prints an invented rebalance across every constituent.
WEIGHT_SUM_BOUNDS = (80.0, 120.0)
FLOW_COLS = ["s0", "s1", "flow_shares", "selection_shares", "total_shares",
             "implied_price", "flow_usd", "selection_usd", "total_usd",
             "split_adjusted"]

# Bounded per-process cache of parsed snapshots. Dated snapshot files are
# immutable once written, so path identity is a sound key; it also collapses the
# double read of the newest snapshot (pair + streak window) into one.
_SNAP_CACHE: dict[str, dict | None] = {}
_SNAP_CACHE_MAX = 4096
_FLEET_LATEST: dict[str, str | None] = {}


def _flow_cfg() -> dict:
    return config.load().get("etf_holdings", {}) or {}


def _numeric(s: pd.Series | None) -> pd.Series:
    """Sponsor columns arrive as '9.23%' / '$1,234.56' as often as plain floats."""
    if s is None:
        return pd.Series(dtype=float)
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    return pd.to_numeric(s.astype(str).str.replace(r"[,%$]", "", regex=True),
                         errors="coerce")


def _f(x) -> float | None:
    """JSON-safe float — NaN/inf become a printed null, never a NaN literal."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (pd.isna(v) or v in (float("inf"), float("-inf"))) else v


def _scale_factor(s0: pd.Series, s1: pd.Series, min_n: int) -> tuple[float, str, int]:
    """Common share-scale factor k between two snapshots — the creation/redemption
    estimate. Median ratio over continuing constituents; below `min_n` continuing
    names a median is not robust either, so fall back to the sum ratio (what the
    shipped diff path uses) and say so. Returns (k, basis, n_constituents)."""
    common = s0.index.intersection(s1.index)
    base, cur = s0.reindex(common), s1.reindex(common)
    ok = base.notna() & cur.notna() & (base > 0) & (cur > 0)
    n = int(ok.sum())
    if n >= min_n:
        k = float((cur[ok] / base[ok]).median())
        if k > 0 and pd.notna(k):
            return k, "median", n
    tot = float(base[ok].sum()) if n else 0.0
    if tot > 0:
        k = float(cur[ok].sum() / tot)
        if k > 0 and pd.notna(k):
            return k, "sum", n
    return 1.0, "none", n


def _implied_price(mv: pd.Series, shares: pd.Series) -> pd.Series:
    p = mv / shares.where(shares > 0)
    return p.replace([float("inf"), float("-inf")], float("nan")).where(p > 0)


def _simple_split_factor(ratio: pd.Series, tol: float) -> pd.Series:
    """True where a share ratio looks like a re-denomination rather than a trade:
    a whole number of new shares per old one (2:1, 3:1, 7:1…), the inverse of one
    (a reverse split), or the two common half-integer cases (3:2, 5:2)."""
    x = ratio.where(ratio >= 1.0, 1.0 / ratio.where(ratio > 0))
    whole = x.round()
    near = ((x / whole - 1.0).abs() <= tol) & (whole >= 2)
    for half in (1.5, 2.5):
        near = near | ((x / half - 1.0).abs() <= tol)
    return near.fillna(False)


def _split_adjust(s0: pd.Series, s1: pd.Series, mv0: pd.Series | None,
                  mv1: pd.Series | None, *, min_ratio: float,
                  mv_tol: float, ratio_tol: float = 0.04
                  ) -> tuple[pd.Series, pd.Series]:
    """Restate the PRIOR share count of a constituent that split between the two
    snapshots. A k-for-1 split multiplies shares by k while the position's market
    value is unchanged; left alone the fund reads as having bought k× the stock.
    Needs the market-value column — sponsors that omit it (the SSGA sector SPDRs)
    are undetectable here, which is why `mv_available` is published.

    Tuned DELIBERATELY tight, because the two error directions are not
    symmetrical: a missed split leaves the board exactly where it already is
    (conviction_pp has always read it as an add), while a false positive DELETES
    a real manager decision that ships today. Measured on this repo's own data
    2026-08-12, a ±25% market-value window over the 60-day scoring window flagged
    8 positions of which only 2 were splits — the other 6 were dip-buys and
    sell-into-strength trims where a 40% share move happened to sit near a 40%
    price move (ARKW/NET: shares ×0.665, price ×1.37, value ×0.91). Over a
    two-month window those coincidences are routine, so a split must clear BOTH
    tests it can be held to: it preserves the position's VALUE (within `mv_tol`,
    because a re-denomination cannot create or destroy any), and it happens at a
    simple factor."""
    no_split = pd.Series(False, index=s0.index)
    if mv0 is None or mv1 is None:
        return s0, no_split
    ratio = s1 / s0.where(s0 > 0)
    mv_ratio = mv1 / mv0.where(mv0 > 0)
    jump = (ratio >= min_ratio) | (ratio <= 1.0 / min_ratio)
    flat = (mv_ratio - 1.0).abs() <= mv_tol
    mask = (jump & flat & _simple_split_factor(ratio, ratio_tol)).fillna(False).astype(bool)
    return s0.where(~mask, s0 * ratio), mask


def flow_selection(s0: pd.Series, s1: pd.Series, *, mv0: pd.Series | None = None,
                   mv1: pd.Series | None = None, min_scale_n: int | None = None,
                   split_min_ratio: float | None = None,
                   split_mv_tol: float | None = None) -> dict:
    """Split one snapshot pair's share change into flow and selection components.

    s0, s1   : shares indexed by ticker (either side may omit a ticker — a new
               position has no s0, a full exit has no s1).
    mv0, mv1 : market_value indexed by ticker; supplies the implied price the
               dollar estimates are built on, and the split guard's evidence.
               Omit them and the frame's $ columns are NaN, never invented.

    Returns {scale, scale_basis, scale_n, mv_available, n_split, frame} where
    `frame` carries FLOW_COLS per ticker and flow+selection == total by
    construction. Pure function — no store access, no config beyond thresholds.
    """
    # min_count=1 everywhere: an all-NaN column (the SSGA sector SPDRs publish no
    # market values) sums to 0.0 by default, which would price every position at
    # zero and publish a confident $0 instead of an honest null.
    def prep(s):
        return None if s is None else _numeric(s).groupby(level=0).sum(min_count=1)

    return _decompose(prep(s0), prep(s1), prep(mv0), prep(mv1),
                      min_scale_n=min_scale_n, split_min_ratio=split_min_ratio,
                      split_mv_tol=split_mv_tol)


def _align(s0, s1, mv0, mv1):
    """Both snapshots on one ticker index, absences as zero shares."""
    idx = s0.index.union(s1.index)
    return (idx, s0.reindex(idx).fillna(0.0), s1.reindex(idx).fillna(0.0),
            None if mv0 is None else mv0.reindex(idx),
            None if mv1 is None else mv1.reindex(idx))


def _scaled(s0, s1, mv0, mv1, min_scale_n, split_min_ratio, split_mv_tol):
    """Split-adjusted prior shares + the common scale factor — the two things
    both the full decomposition and the streak walk need."""
    cfg = _flow_cfg()
    min_n = min_scale_n if min_scale_n is not None else cfg.get("flow_min_scale_n", 5)
    ratio = split_min_ratio or cfg.get("flow_split_min_ratio", 1.5)
    tol = split_mv_tol if split_mv_tol is not None else cfg.get("flow_split_mv_tol", 0.03)
    rtol = cfg.get("flow_split_ratio_tol", 0.04)
    s0_adj, split = _split_adjust(s0, s1, mv0, mv1, min_ratio=ratio, mv_tol=tol,
                                  ratio_tol=rtol)
    k, basis, n = _scale_factor(s0_adj[s0_adj > 0], s1[s1 > 0], min_n)
    return s0_adj, split, k, basis, n


def _decompose(s0, s1, mv0=None, mv1=None, *, min_scale_n=None,
               split_min_ratio=None, split_mv_tol=None) -> dict:
    """`flow_selection` on inputs already collapsed to one row per ticker."""
    if s0 is None or s1 is None or (len(s0.index.union(s1.index)) == 0):
        return {"scale": 1.0, "scale_basis": "none", "scale_n": 0,
                "mv_available": False, "n_split": 0,
                "frame": pd.DataFrame(columns=FLOW_COLS)}
    idx, s0, s1, mv0, mv1 = _align(s0, s1, mv0, mv1)
    s0_adj, split, k, basis, n = _scaled(s0, s1, mv0, mv1, min_scale_n,
                                         split_min_ratio, split_mv_tol)
    flow = s0_adj * (k - 1.0)
    selection = s1 - s0_adj * k
    total = s1 - s0_adj

    # implied price: the current snapshot's, falling back to the prior one for a
    # position that is gone now (an exit still has to be priced to be counted).
    # A non-positive implied price is not a price — it is a blank cell.
    price = pd.Series(float("nan"), index=idx)
    if mv1 is not None:
        price = _implied_price(mv1, s1)
    if mv0 is not None:
        price = price.fillna(_implied_price(mv0, s0))

    frame = pd.DataFrame({
        "s0": s0_adj, "s1": s1,
        "flow_shares": flow, "selection_shares": selection, "total_shares": total,
        "implied_price": price,
        "flow_usd": flow * price, "selection_usd": selection * price,
        "total_usd": total * price,
        "split_adjusted": split.reindex(idx).fillna(False).astype(bool),
    })
    return {"scale": k, "scale_basis": basis, "scale_n": n,
            "mv_available": bool(price.notna().any()),
            "n_split": int(frame["split_adjusted"].sum()), "frame": frame}


def _read_snapshot(path) -> dict | None:
    """Parse one holdings snapshot into {asof, shares, mv, wsum, n_rows}.

    Applies the SAME cash/FX hygiene gate the diff path applies
    (collectors.holdings._drop_non_equity) — decomposing a different constituent
    set than the one being scored is how the two reads drift apart — and collapses
    duplicate ticker lines, which sponsors emit when one position is filed on two
    lots. Returns None if the file is unreadable or carries no share column."""
    from collectors.holdings import _drop_non_equity
    key = str(path)
    if key in _SNAP_CACHE:
        return _SNAP_CACHE[key]
    snap: dict | None = None
    try:
        df = _drop_non_equity(pd.read_parquet(path))
    except Exception as e:  # noqa: BLE001 — a corrupt snapshot must not kill the fund
        log.warning("flow decomposition: %s unreadable: %s", path, e)
        df = None
    if df is not None and not df.empty and {"ticker", "shares"} <= set(df.columns):
        tk = df["ticker"].astype(str)
        shares = _numeric(df["shares"]).groupby(tk).sum(min_count=1)
        mvcol = next((c for c in df.columns if c.lower() in ("market_value", "market value")), None)
        mv = _numeric(df[mvcol]).groupby(tk).sum(min_count=1) if mvcol else None
        # a column that is present but empty is NOT a market-value column: 21 of
        # the 76 tracked funds ship the header with nothing under it.
        if mv is not None and not (mv > 0).any():
            mv = None
        wcol = next((c for c in df.columns if "weight" in c.lower()), None)
        wsum = float(_numeric(df[wcol]).sum()) if wcol else None
        asof = str(path.stem)
        if "as_of" in df.columns:
            vals = df["as_of"].dropna().astype(str)
            if not vals.empty:
                asof = vals.iloc[0]
        snap = {"asof": asof, "shares": shares.dropna(), "mv": mv, "wsum": wsum,
                "path": path.stem}
    if len(_SNAP_CACHE) >= _SNAP_CACHE_MAX:
        _SNAP_CACHE.clear()
    _SNAP_CACHE[key] = snap
    return snap


def _usable_snapshots(paths, want: int, *, newest_first: bool = True
                      ) -> tuple[list[dict], list[str]]:
    """Up to `want` usable snapshots from `paths`, always returned oldest→newest,
    plus the as-of dates quarantined on the way.

    Two guards run here so every consumer of the decomposition inherits them:
    duplicate as-of dates collapse to ONE snapshot (a re-fetch written under a
    second filename must not read as a zero-change day), and a snapshot whose
    weight column sums outside WEIGHT_SUM_BOUNDS is quarantined rather than
    silently used. `newest_first` picks which end of the range to take from —
    the streak window takes the newest, the scoring pair's far end the oldest."""
    lo, hi = WEIGHT_SUM_BOUNDS
    ordered = list(paths)[::-1] if newest_first else list(paths)
    keep: list[dict] = []
    quarantined: list[str] = []
    seen: set[str] = set()
    for p in ordered:
        if len(keep) >= want:
            break
        snap = _read_snapshot(p)
        if snap is None or snap["asof"] in seen:
            continue
        seen.add(snap["asof"])
        wsum = snap["wsum"]
        if wsum is not None and wsum > 0 and not (lo <= wsum <= hi):
            quarantined.append(snap["asof"])
            continue
        keep.append(snap)
    return (keep[::-1] if newest_first else keep), quarantined


@lru_cache(maxsize=4096)
def _as_date(s: str):
    """Snapshot dates are ISO stems; pd.to_datetime costs ~0.6ms a call and this
    runs once per interval per fund on the render path."""
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        try:
            return pd.to_datetime(s).date()
        except Exception:  # noqa: BLE001 — a sponsor date we cannot parse is not fatal
            return None


def _interval_days(a: str, b: str) -> int | None:
    d0, d1 = _as_date(a), _as_date(b)
    if d0 is None or d1 is None:
        return None
    d = (d1 - d0).days
    return int(d) if d > 0 else None


def _fleet_latest_asof(root) -> str | None:
    """Newest snapshot date under a snapshot ROOT — the reference staleness is
    measured against, matching engine.etf_consensus.fund_coverage (the fleet's own
    edge, never a wall clock)."""
    key = str(root)
    if key in _FLEET_LATEST:
        return _FLEET_LATEST[key]
    latest = None
    try:
        for d in root.iterdir():
            if not d.is_dir():
                continue
            stems = sorted(p.stem for p in d.glob("*.parquet"))
            if stems and (latest is None or stems[-1] > latest):
                latest = stems[-1]
    except Exception:  # noqa: BLE001 — freshness is additive
        latest = None
    _FLEET_LATEST[key] = latest
    return latest


def fund_flow_decomposition(base, window: int, *, fund: str = "",
                            only: set[str] | None = None,
                            streak_snaps: int | None = None,
                            fleet_latest: str | None = None) -> dict | None:
    """Flow/selection decomposition + persistence for ONE fund's snapshot store.

    `base` is the fund's snapshot directory, `window` the same snapshot count the
    shipped diff path compares over, so the headline pair is the same pair
    `conviction_pp` was scored on — unless a guard rejected one end, in which case
    this steps to the nearest usable snapshot and publishes the quarantine.

    Returns None when fewer than two usable snapshots exist. `only` restricts the
    per-ticker mapping to the tickers the caller will actually publish (the frame
    is computed for all of them either way — the filter is on materialization).
    """
    from pathlib import Path
    base = Path(base)
    if not base.exists():
        return None
    cfg = _flow_cfg()
    streak_snaps = streak_snaps or cfg.get("flow_streak_snaps", 4)
    stale_after = cfg.get("flow_stale_days", 7)
    snaps = sorted(base.glob("*.parquet"))
    if len(snaps) < 2:
        return None

    # tail = the streak window (newest end); head = the far end of the scoring
    # window. Both resolve through the guards, and the cache means a snapshot both
    # ends reach for is parsed once.
    win = snaps[-(window + 1):]
    tail, q_tail = _usable_snapshots(win, streak_snaps)
    head, q_head = _usable_snapshots(win, 1, newest_first=False)
    if not tail or not head:
        return None
    first, last = head[0], tail[-1]
    quarantined = sorted(set(q_tail) | set(q_head))
    if first["asof"] >= last["asof"]:
        return None

    dec = flow_selection(first["shares"], last["shares"],
                         mv0=first["mv"], mv1=last["mv"])
    frame = dec["frame"]
    window_days = _interval_days(first["asof"], last["asof"])

    # persistence: per-interval selection sign over the streak window, plus the
    # newest interval's per-day pace against the earlier ones (acceleration).
    streak, accel = _streaks(tail, cfg)

    if quarantined:
        print(f"::warning title=etf-snapshot-quarantine::{fund or base.name}: "
              f"{len(quarantined)} snapshot(s) rejected by the weight-sum sanity "
              f"check ({', '.join(quarantined)}) — excluded from the flow/selection "
              f"read", flush=True)
        log.warning("flow decomposition %s: quarantined %s (weight sum outside %s)",
                    fund or base.name, quarantined, WEIGHT_SUM_BOUNDS)

    # continuity: a name absent from ONE snapshot is a feed hiccup, not an exit.
    present_last2 = set(tail[-2]["shares"].index) if len(tail) >= 2 else set()
    gone_now = set(frame.index[frame["s1"] <= 0])
    unconfirmed = gone_now & present_last2

    rows = frame if only is None else frame[frame.index.isin({str(t) for t in only})]
    by_ticker: dict[str, dict] = {}
    for tk, r in rows.iterrows():
        tk = str(tk)
        by_ticker[tk] = {
            "s0": _f(r["s0"]), "s1": _f(r["s1"]),
            "flow_shares": _f(r["flow_shares"]),
            "selection_shares": _f(r["selection_shares"]),
            "total_shares": _f(r["total_shares"]),
            "implied_price": _f(r["implied_price"]),
            "flow_usd": _f(r["flow_usd"]), "selection_usd": _f(r["selection_usd"]),
            "total_usd": _f(r["total_usd"]),
            "split_adjusted": bool(r["split_adjusted"]),
            "streak": int(streak.get(tk, 0)),
            "accel_pct_per_day": _f(accel.get(tk)),
            "exit_confirmed": (tk not in unconfirmed) if tk in gone_now else None,
        }

    asof = last["asof"]
    stale_days = _interval_days(asof, fleet_latest) if fleet_latest else None
    if fleet_latest and stale_days is None:
        stale_days = 0
    return {
        "fund": fund or base.name,
        "t0": first["asof"], "t1": asof, "window_days": window_days,
        "scale": dec["scale"], "scale_pct": round((dec["scale"] - 1.0) * 100.0, 4),
        "scale_basis": dec["scale_basis"], "scale_n": dec["scale_n"],
        "mv_available": dec["mv_available"], "n_split": dec["n_split"],
        "n_snapshots": len(snaps), "quarantined": quarantined,
        "stale_days": stale_days,
        "is_stale": bool(stale_days is not None and stale_days >= stale_after),
        "by_ticker": by_ticker,
    }


def _streaks(snaps: list[dict], cfg: dict) -> tuple[dict[str, int], dict[str, float]]:
    """Per-ticker directional streak and acceleration over consecutive snapshots.

    streak = signed count of the most recent consecutive intervals in which the
    fund MOVED the position the same way (+3 = three adds running, -2 = two trims).
    Intervals where nothing happened are skipped, not counted and not treated as a
    break: real funds rebalance weekly-to-monthly but snapshot daily, so letting a
    quiet Wednesday end the run would report 0 for almost every position on the
    board. A move under `flow_flat_frac` of the position counts as nothing
    happening, so float noise on an untouched passive book cannot manufacture a
    run either. accel = the newest interval's selection %-per-day minus the mean of
    the earlier intervals' — per-DAY so a weekly-reporting fund and a
    daily-reporting one are on the same footing."""
    if len(snaps) < 2:
        return {}, {}
    flat_frac = cfg.get("flow_flat_frac", 1e-4)
    signs: list[pd.Series] = []
    rates: list[pd.Series] = []
    for a, b in zip(snaps[:-1], snaps[1:]):
        # the $ frame is not needed here, only the selection component — and the
        # streak walk runs once per interval per fund, so it stays off that path.
        _, s0, s1, mv0, mv1 = _align(a["shares"], b["shares"], a["mv"], b["mv"])
        s0_adj, _, k, _, _ = _scaled(s0, s1, mv0, mv1, None, None, None)
        base = s0_adj * k
        sel = (s1 - base).fillna(0.0)
        flat = sel.abs() <= flat_frac * pd.concat([s0_adj, s1], axis=1).max(axis=1)
        signs.append((sel.gt(0).astype(int) - sel.lt(0).astype(int)).where(~flat, 0))
        days = _interval_days(a["asof"], b["asof"]) or 1
        rates.append(100.0 * sel / base.where(base > 0) / days)

    idx = signs[-1].index
    latest = pd.Series(0, index=idx)     # sign of the most recent interval that moved
    run = pd.Series(0, index=idx)
    alive = pd.Series(True, index=idx)   # the trailing run is still extending
    for s in reversed(signs):
        s = s.reindex(idx).fillna(0).astype(int)
        moved = s != 0
        latest = latest.where(~(moved & (latest == 0)), s)
        run = run + (alive & moved & (s == latest)).astype(int)
        alive = alive & ~(moved & (s != latest))
    streak = (run * latest).astype(int)

    rate_now = rates[-1]
    if len(rates) > 1:
        prior = pd.concat([r.reindex(idx) for r in rates[:-1]], axis=1).mean(axis=1)
        accel = (rate_now - prior).round(4)
    else:
        accel = pd.Series(float("nan"), index=idx)
    return (streak[streak != 0].to_dict(),
            {str(k): _f(v) for k, v in accel.items() if pd.notna(v)})


# --------------------------------------------------------------------------- #
# Phase 2 — broad ETF universe. SHARE-BASED flow-normalized active decisions
# (collectors.holdings.active_changes_dir): needs no per-stock prices, so it
# scales across the whole universe. On ACTIVE funds (ARK) the signal is genuine
# manager conviction; on PASSIVE index/sector ETFs it is index reconstitution /
# rebalance flow — the page labels each honestly. See D71.
# --------------------------------------------------------------------------- #

def etf_signals(etf: str, *, base_dir=None, is_active: bool = False,
                meta: dict | None = None, fleet_latest: str | None = None) -> list[dict]:
    """Flagged holdings for one ETF from full-holdings snapshots: positions whose
    flow-normalized share change clears `active_change_alert_pct` and whose weight
    clears `min_position_pct`, each tagged active/passive + (where the stock has
    price history) its cycle state.

    Each row also carries the W1 flow/selection decomposition of the same snapshot
    pair (flow_pp/selection_pp, the $ estimates, persistence and the guard flags).
    Those fields are ADDITIVE: `conviction_pp` and everything the shipped board
    ranks on are computed exactly as before. `fleet_latest` is the newest snapshot
    date across the tracked universe — staleness is measured against the fleet's
    own edge, matching fund_coverage; omitted, it falls back to this store's."""
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

    # W1: flow/selection on the SAME pair, materialized only for flagged tickers.
    decomp: dict = {}
    try:
        decomp = fund_flow_decomposition(
            base, window, fund=etf, only={str(t) for t in ch.index},
            fleet_latest=fleet_latest or _fleet_latest_asof(base.parent)) or {}
    except Exception as e:  # noqa: BLE001 — the decomposition is additive, never fatal
        log.error("flow decomposition %s failed: %s", etf, e)
    dec_rows = decomp.get("by_ticker", {})
    fund_flags = {
        "fund_scale_pct": _f(decomp.get("scale_pct")),
        "fund_scale_basis": decomp.get("scale_basis"),
        "mv_available": bool(decomp.get("mv_available")),
        "window_days": decomp.get("window_days"),
        "stale_days": decomp.get("stale_days"),
        "is_stale": bool(decomp.get("is_stale")),
        "n_quarantined": len(decomp.get("quarantined") or []),
    }

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
            **fund_flags,
            **_decomp_fields(dec_rows.get(str(tk)), w, is_exit=is_exit,
                             window_days=fund_flags["window_days"]),
        })
    return out


def _decomp_fields(d: dict | None, w: float, *, is_exit: bool,
                   window_days: int | None = None) -> dict:
    """The flow/selection fields for one flagged position, in the same pp basis
    the conviction score uses: pp(x) = w·x/s1, so flow_pp + selection_pp equals
    the position's whole weight change and `selection_pp` is `conviction_pp`
    re-derived on the robust scale factor. A full exit has no s1, so its pp basis
    is the PRIOR weight (w is already the carried prior weight there) against s0 —
    which lands on -w for the total, exactly as conviction_pp does."""
    blank = {"flow_shares": None, "selection_shares": None, "flow_pp": None,
             "selection_pp": None, "total_pp": None, "flow_usd": None,
             "selection_usd": None, "total_usd": None, "implied_price": None,
             "usd_per_day": None, "driver": None, "split_adjusted": False,
             "streak": 0, "accel_pct_per_day": None, "exit_confirmed": None}
    if not d:
        return blank
    basis = d.get("s0") if is_exit else d.get("s1")
    scale = (w / basis) if basis else None
    flow_sh, sel_sh = d.get("flow_shares"), d.get("selection_shares")
    out = dict(blank, **{
        "flow_shares": flow_sh, "selection_shares": sel_sh,
        "flow_usd": d.get("flow_usd"), "selection_usd": d.get("selection_usd"),
        "total_usd": d.get("total_usd"), "implied_price": d.get("implied_price"),
        "split_adjusted": bool(d.get("split_adjusted")),
        "streak": int(d.get("streak") or 0),
        "accel_pct_per_day": d.get("accel_pct_per_day"),
        "exit_confirmed": d.get("exit_confirmed"),
    })
    if scale is not None and flow_sh is not None and sel_sh is not None:
        out["flow_pp"] = round(flow_sh * scale, 4)
        out["selection_pp"] = round(sel_sh * scale, 4)
        out["total_pp"] = round(out["flow_pp"] + out["selection_pp"], 4)
    if flow_sh is not None and sel_sh is not None and (flow_sh or sel_sh):
        out["driver"] = "flow" if abs(flow_sh) > abs(sel_sh) else "selection"
    if out["total_usd"] is not None and window_days:
        out["usd_per_day"] = round(out["total_usd"] / window_days, 2)
    return out


def all_etf_signals() -> list[dict]:
    """Every flagged, conviction-scored holding decision across the curated
    thematic/active ETF universe (data/etf_holdings) plus the active watchlist
    (data/holdings, e.g. ARK). Unsorted; callers split into accumulation / trims."""
    cfg = config.load()
    out: list[dict] = []
    holdings_dir = config.ROOT / cfg["storage"]["holdings_dir"]
    # one freshness reference for the whole universe, spanning BOTH stores — the
    # same "fleet's own edge" fund_coverage measures staleness against.
    fleet = max((d for d in (_fleet_latest_asof(config.data_dir() / "etf_holdings"),
                             _fleet_latest_asof(holdings_dir)) if d), default=None)
    for etf, spec in cfg["etf_holdings"].get("universe", {}).items():
        try:
            out.extend(etf_signals(etf, is_active=bool(spec.get("active", False)),
                                   meta=spec, fleet_latest=fleet))
        except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
            log.error("etf_signals %s failed: %s", etf, e)
    for etf in cfg["holdings"].get("watchlist", {}):
        try:
            out.extend(etf_signals(etf, base_dir=holdings_dir, is_active=True,
                                   fleet_latest=fleet,
                                   meta={"name": etf, "category": "Active / Innovation"}))
        except Exception as e:  # noqa: BLE001
            log.error("etf_signals %s (watchlist) failed: %s", etf, e)
    return out


# --------------------------------------------------------------------------- #
# B1 (masterplan §6c) — the split verdict reaches the RANKED path.
#
# `_split_adjust` already identifies a re-denomination and restates the prior
# share count for the decomposition, so flow_pp/selection_pp read it correctly.
# `conviction_pp` never did: it is computed off `active_changes_dir`'s own share
# diff, which sees ARKW's 3:1 CRWD split as +207.93% of the position and books
# +1.6274pp of manager conviction that nobody committed. The guard's own verdict
# was published one column away from the number it disproves.
#
# So a positively-identified split is dropped from every RANKED input —
# accumulation/trims, the consensus counts, the board and the ledger — and kept,
# labeled, in the Tier-2 receipts (`funds[].split_adjusted`, the per-stock feed,
# `n_split_adjusted`). Dropping beats restating: the split guard clears both a
# value test and a simple-factor test before it fires (see `_split_adjust`), but
# it cannot tell a pure split from a split plus a real trade in the same window
# (masterplan §6b R4), so the honest read of a flagged event is "this number is
# not a decision", not "this number is X instead".
# --------------------------------------------------------------------------- #
def is_split_event(row: dict | None) -> bool:
    """True when this fund-ticker event's share change was positively identified
    as a re-denomination rather than a manager decision."""
    return bool((row or {}).get("split_adjusted"))


def drop_split_events(rows: "list[dict] | None") -> list[dict]:
    """Ranked-path filter: every row EXCEPT the positively-identified splits."""
    return [r for r in (rows or []) if not is_split_event(r)]


def split_by_conviction(rows: list[dict], n: int | None = None,
                        trims_n: int | None = None) -> dict[str, list[dict]]:
    """Split signal rows into a positive-first accumulation list (the actionable
    side the user cares about) and a smaller, de-emphasized trims list, each
    ranked by conviction (pp of fund weight committed), NOT raw share %.

    Positively-identified splits are excluded from BOTH lists (B1): a
    re-denomination is not a decision, and it used to rank as one of the largest
    ones on the page."""
    cfg = config.load()["etf_holdings"]
    n = n or cfg.get("page_top_n", 40)
    trims_n = trims_n if trims_n is not None else cfg.get("trims_top_n", 12)
    rows = drop_split_events(rows)
    acc = sorted((r for r in rows if (r.get("conviction_pp") or 0) > 0),
                 key=lambda r: -r["conviction_pp"])[:n]
    trims = sorted((r for r in rows if (r.get("conviction_pp") or 0) < 0),
                   key=lambda r: r["conviction_pp"])[:trims_n]
    return {"accumulation": acc, "trims": trims}


def top_etf_accumulation(n: int | None = None, trims_n: int | None = None) -> dict[str, list[dict]]:
    """Conviction-ranked fund decisions for the radar page: {accumulation, trims}.
    Accumulation (positive conviction) is the headline; trims are secondary."""
    return split_by_conviction(all_etf_signals(), n=n, trims_n=trims_n)
