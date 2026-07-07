"""Assemble the daily feature frame from the parquet store.

Everything downstream (axes, transition detector, sector ranks, backtest)
reads this one aligned business-day DataFrame. Missing sources simply yield
NaN columns — the engine renormalizes weights over what exists and degrades
confidence instead of crashing.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from lib import config, store

log = logging.getLogger(__name__)


def _yahoo_close(name: str, basis: str = "tr") -> pd.Series | None:
    """Read one yahoo close series by basis.

    basis="tr"    — total-return (split+div adjusted).  Reads the ``close``
                    column.  This is the default and is byte-identical to all
                    callers written before W1.3 — no caller behaviour changes
                    without an explicit opt-in.
    basis="price" — split-adjusted, dividend-UNadjusted (the structure-math
                    basis for ZigZag / detrended-osc / DCL).  Reads the
                    ``close_price`` column added by the W1.3 backfill.  Raises
                    KeyError with guidance if the column is absent (pre-backfill
                    ticker or dead name).
    """
    df = store.read("yahoo", name)
    if df is None:
        return None
    if basis == "price":
        if "close_price" in df.columns:
            s = df["close_price"]
            s.attrs["price_basis"] = "price"
            return s
        # Pre-backfill or dead-name ticker: fall back to TR with a loud warning.
        # The caller can detect degraded basis via .attrs['price_basis'] == 'tr_fallback'.
        if "close" in df.columns:
            log.warning(
                "yahoo/%s: close_price column absent (pre-backfill); "
                "falling back to close (TR basis) — run scripts/backfill_price_basis.py",
                name,
            )
            s = df["close"]
            s.attrs["price_basis"] = "tr_fallback"
            return s
        return None
    # default basis="tr"
    if "close" not in df.columns:
        return None
    s = df["close"]
    s.attrs["price_basis"] = "tr"
    return s


def _fred(col_by_sid: dict[str, str]) -> dict[str, pd.Series]:
    out = {}
    for sid, col in col_by_sid.items():
        df = store.read("fred", sid)
        if df is not None and not df.empty:
            out[col] = df.iloc[:, 0]
    return out


def yahoo_closes(basis: str = "tr") -> pd.DataFrame:
    """Return a wide DataFrame of yahoo EOD closes aligned on a business-day index.

    basis="tr" (default) — total-return adjusted close.  Byte-identical to all
        callers written before W1.3; every existing caller continues to work
        without changes.
    basis="price" — split-adjusted, dividend-UNadjusted close (W1.3 addition).
        Requires the ``close_price`` column to exist in the yahoo parquets
        (populated by scripts/backfill_price_basis.py).  Tickers that lack the
        column fall back to TR and are tagged with .attrs['price_basis']='tr_fallback'.
    """
    cfg = config.load()["yahoo"]["tickers"]
    cols = {}
    for grp in cfg.values():
        for t in grp:
            s = _yahoo_close(t.replace("^", "_").replace("=", "_").replace("/", "_"),
                             basis=basis)
            if s is not None:
                cols[t] = s
    return pd.DataFrame(cols).sort_index()


def build_features(pit_basis: str | None = None,
                   pit_as_of: pd.Timestamp | str | None = None,
                   overrides: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    """Assemble the daily feature frame.

    pit_basis : SHADOW point-in-time control (audit #5/#14/#39, masterplan W1a).
        None (default) -> current live behaviour, BYTE-IDENTICAL output (the live
        render/collect path never passes this argument). 'release' -> the leak-free
        frame: monthly/weekly revision-prone FRED econ columns are routed through
        engine.pit so each historical row carries only what was available (and
        initial-release, not latest-revised) on that day. 'reference'/'latest' route
        the same columns through pit for A/B symmetry but reproduce current stamping.
        Market data (rates/OAS/VIX/FX/equities) is never revised and is untouched by
        any basis, so the frame stays internally consistent (avoids the partial-PIT
        hazard of #14 for the SHADOW frame — a full leg set moves together).
    pit_as_of : optional hard as-of cut passed through to engine.pit.series.
    overrides : SHADOW injection seam (CPI P-D5-1, regime_v2_pit). Optional
        {column_name: raw series} replacing the store read for that column before
        the normal dedupe/union-reindex/ffill contract in put() — the injected
        series flows through EXACTLY the same alignment as the store series, so
        axes/regime run unchanged on top. None/{} (default) -> live behaviour,
        byte-identical (the live path never passes this argument). An overridden
        column bypasses the pit_basis router (the caller injected it explicitly).
        Used by scripts/build_regime_v2_pit.py to feed vintage-as-of macro legs.
    """
    cfg = config.load()
    ecfg = cfg["engine"]
    closes = yahoo_closes()
    if closes.empty:
        raise RuntimeError("no yahoo data in store — run collectors first")

    # futures rows can be stamped one day ahead of the equity session — the
    # frame ends on the last day the equity benchmark actually printed
    end = closes["SPY"].last_valid_index() if "SPY" in closes else closes.index.max()
    idx = pd.bdate_range(closes.index.min(), end)
    f = pd.DataFrame(index=idx)

    # SHADOW PIT re-router: when pit_basis is set, the named revision-prone FRED econ
    # columns are supplied by engine.pit on the requested basis instead of the live
    # reference-stamped store series. Kept lazy so the default path never imports pit.
    _pit_cols: set[str] = set()
    _pit_series = None
    if pit_basis is not None:
        from engine import pit as _pitmod
        _pit_series = _pitmod
        _pit_cols = set(_pitmod.VINTAGED_SID_TO_COL.values()) | set(_pitmod.DEFAULT_RELEASE_LAGS)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if overrides is not None and name in overrides:
            # injected series replaces the store read; falls through to the same
            # dedupe/union-reindex/ffill contract below (and skips the pit router —
            # the caller supplied this column explicitly).
            s = overrides[name]
        elif _pit_series is not None and name in _pit_cols:
            # route this revision-prone column through the PIT accessor at the same
            # reindex/ffill contract used below, so axes/regime run unchanged.
            f[name] = _pit_series.series(name, as_of=pit_as_of, basis=pit_basis,
                                         index=idx, ffill_limit=ffill_limit)
            return
        if s is None or s.empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index()
        # fill on the union first: monthly series stamped on weekends/holidays
        # (e.g. PAYEMS on a Sunday the 1st) must survive the business-day reindex
        union = idx.union(s.index)
        s = s.reindex(union)
        s = s.ffill(limit=ffill_limit) if ffill_limit else s
        f[name] = s.reindex(idx)

    # --- price levels & ratios -------------------------------------------------
    for t in ["SPY", "IWM", "RSP", "QQQ", "XLY", "XLP", "XLE", "XLK", "XLU",
              "HYG", "LQD", "SPHB", "SPLV"]:
        put(t, closes.get(t))
    # US equity size & style: small (Russell 2000), mid (S&P 400), growth/value
    put("RUT", closes.get("^RUT"))        # true Russell 2000 index level
    put("IJH", closes.get("IJH"))         # S&P MidCap 400 — mid-cap leg
    put("IWF", closes.get("IWF"))         # Russell 1000 Growth
    put("IWD", closes.get("IWD"))         # Russell 1000 Value
    put("oil", closes.get("CL=F"))
    put("copper", closes.get("HG=F"))
    put("gold", closes.get("GC=F"))
    put("dxy", closes.get("DX-Y.NYB"))
    put("vix", closes.get("^VIX"))
    # intraday VIX high (daily wick = high vs close — a washout / thin-quote tell);
    # yahoo_closes() carries only close, so read the high column directly
    _vixs = store.read("yahoo", "_VIX")
    put("vix_high", _vixs["high"] if _vixs is not None and "high" in _vixs.columns else None)
    put("vix3m", closes.get("^VIX3M"))
    put("vix9d", closes.get("^VIX9D"))
    put("move", closes.get("^MOVE"))
    put("zq_front", closes.get("ZQ=F"))

    f["copper_gold"] = f["copper"] / f["gold"]
    f["xly_xlp"] = f["XLY"] / f["XLP"]
    f["iwm_spy"] = f["IWM"] / f["SPY"]          # small caps vs large (risk appetite / breadth)
    f["mid_spy"] = f["IJH"] / f["SPY"]          # mid caps vs large
    f["growth_value"] = f["IWF"] / f["IWD"]     # growth vs value leadership (style rotation)
    f["energy_rs"] = f["XLE"] / f["SPY"]
    f["xlk_xlu"] = f["XLK"] / f["XLU"]
    f["sphb_splv"] = f["SPHB"] / f["SPLV"]
    f["hyg_lqd"] = f["HYG"] / f["LQD"]
    from engine import canon
    f["vix_ratio"] = canon.vix_term(f["vix"], f["vix3m"])  # canon VIX/VIX3M (audit #12)

    g = ecfg["growth_axis"]
    cyc = basket_index(closes, g["cyclical_basket"]).reindex(idx).ffill(limit=5)
    dfn = basket_index(closes, g["defensive_basket"]).reindex(idx).ffill(limit=5)
    f["cyc_def"] = cyc / dfn
    ia = ecfg["inflation_axis"]
    ib_long = basket_index(closes, ia["inflation_long_basket"]).reindex(idx).ffill(limit=5)
    ib_short = basket_index(closes, ia["inflation_short_basket"]).reindex(idx).ffill(limit=5)
    f["infl_basket"] = ib_long / ib_short

    # --- FRED ------------------------------------------------------------------
    fred_map = {}
    for grp in cfg["fred"]["series"].values():
        fred_map.update(grp)
    series = _fred(fred_map)
    for col in ["us2y", "us10y", "spread_2s10s", "us10y_real", "breakeven_10y",
                "breakeven_5y5y", "fed_funds", "hy_oas", "ig_oas", "vix_close"]:
        put(col, series.get(col))
    # archived OAS history (pre rolling-window) is merged underneath live data
    for col, arch in [("hy_oas", "BAMLH0A0HYM2"), ("ig_oas", "BAMLC0A0CM")]:
        a = store.read("archive", arch)
        if a is not None and not a.empty:
            s = a.iloc[:, 0].reindex(idx).ffill(limit=5)
            f[col] = f[col].combine_first(s)
    # monthly econ confirmations: step-fill forward (released with lag; we use
    # direction only, ffill across the month is the honest representation)
    # 60 bdays: INDPRO is stamped on the reference month but published ~6 weeks
    # later, so the previous print must carry until its successor arrives
    put("payrolls", series.get("payrolls"), ffill_limit=60)
    put("indpro", series.get("indpro" if "indpro" in series else "industrial_prod"), ffill_limit=60)
    # derived fallbacks when the published composite series is unavailable
    effr = store.read("nyfed", "effr")
    if effr is not None:
        f["fed_funds"] = f["fed_funds"].combine_first(
            effr.iloc[:, 0].reindex(idx).ffill(limit=5))
    f["spread_2s10s"] = f["spread_2s10s"].combine_first(f["us10y"] - f["us2y"])
    f["tips_nominal_spread"] = f["us10y"] - f["us10y_real"]
    f["breakeven_10y"] = f["breakeven_10y"].combine_first(f["tips_nominal_spread"])
    # rate-cut pricing proxy (LOW CONFIDENCE — no free FedWatch API): negative
    # values = market prices cuts over the next ~2y; ZQ front adds a 30d view
    f["rate_expectations_proxy"] = f["us2y"] - f["fed_funds"]
    f["zq_implied_rate"] = 100 - f["zq_front"]
    # Fed policy path (DISPLAY-ONLY, research/DATA_SIGNAL_EXPANSION_2026.md #2): the
    # live target range (daily) + the FOMC dot-plot median. The range gives the policy
    # midpoint; the dot is future-dated (each SEP overwrites the series) so ffill only
    # carries the latest projection forward — engine/fed_path.py reads the RAW store
    # series for the full forward dot path. Never scored, never an MRS leg.
    put("fed_target_upper", series.get("fed_target_upper"))
    put("fed_target_lower", series.get("fed_target_lower"))
    put("fed_dot_median", series.get("fed_dot_median"), ffill_limit=400)

    # --- Quant-factor expansion: Fed-research feeds (research/QUANT_FACTOR_EXPANSION.md)
    # Financial-conditions indices (weekly) — a ready broad risk gauge.
    for col in ["nfci", "anfci", "nfci_risk", "nfci_credit", "nfci_leverage", "stlfsi"]:
        put(col, series.get(col), ffill_limit=7)
    # OFR Financial Stress Index (daily, ~2-bday lag) — level + 5 functional + 3
    # regional legs (data/ofr/). The functional decomposition lets the read name the
    # stress CHANNEL; the Funding leg embeds a free x-ccy-basis proxy, the EM leg is
    # additive vs the US-centric NFCI. See research/DATA_SIGNAL_EXPANSION_2026.md.
    for col, sid in [("ofr_fsi", "fsi"), ("ofr_fsi_credit", "fsi_credit"),
                     ("ofr_fsi_equity", "fsi_equity"), ("ofr_fsi_safe", "fsi_safe_assets"),
                     ("ofr_fsi_funding", "fsi_funding"), ("ofr_fsi_vol", "fsi_volatility"),
                     ("ofr_fsi_us", "fsi_us"), ("ofr_fsi_oae", "fsi_oae"),
                     ("ofr_fsi_em", "fsi_em")]:
        o = store.read("ofr_fsi", sid)
        put(col, o.iloc[:, 0] if o is not None and not o.empty else None, ffill_limit=7)
    # Commercial-paper spreads (daily): A2/P2 = credit-quality stress, CP-bill = funding
    # stress. The bill leg (us3m) is loaded with the fuller curve below.
    put("aa_cp_90d", series.get("aa_cp_90d"), ffill_limit=7)
    put("a2p2_cp_90d", series.get("a2p2_cp_90d"), ffill_limit=7)
    # Recession reads: Sahm + smoothed prob (monthly, ~6wk publication lag), ACM
    # term premium (daily). 70 bdays carries a monthly print until its successor.
    put("sahm", series.get("sahm"), ffill_limit=70)
    put("recession_prob", series.get("recession_prob"), ffill_limit=70)
    put("term_premium_10y", series.get("term_premium_10y"), ffill_limit=5)
    # Real-time growth nowcasts: WEI (weekly), GDPNow (quarterly on FRED).
    put("wei", series.get("wei"), ffill_limit=10)
    put("gdpnow", series.get("gdpnow"), ffill_limit=95)
    # Underlying-inflation indices (monthly): persistent (sticky) vs transitory (flexible).
    for col in ["sticky_cpi", "core_sticky_cpi", "flex_cpi"]:
        put(col, series.get(col), ffill_limit=45)
    put("median_cpi", series.get("median_cpi"), ffill_limit=45)
    # 3-month-smoothed sticky CPI rate — the inflation axis reads its DIRECTION as a
    # persistent-inflation confirmation (raw monthly prints are noisy).
    if "sticky_cpi" in f:
        f["sticky_cpi_3m"] = f["sticky_cpi"].rolling(63, min_periods=21).mean()
    # Household sentiment / inflation expectations (monthly).
    put("umich_sentiment", series.get("umich_sentiment"), ffill_limit=45)
    put("umich_infl_exp", series.get("umich_infl_exp"), ffill_limit=45)
    # --- Official inflation RELEASES (research/RATE_INFLATION_TRANSMISSION.md) ------
    # The actual CPI/PCE/PPI/ECI prints (not the model nowcasts above), stored on FRED
    # as index LEVELS. We derive YoY (12-month %) and a 3-month-annualized momentum
    # read here so the transmission engine + UI read ready numbers. Monthly prints
    # publish with a ~2-week (CPI/PPI) to ~1-month (PCE) lag; ffill carries the last
    # print until its successor (60 bdays = the honest step representation).
    def _rel(col: str) -> pd.Series | None:
        s = series.get(col)
        if s is None or s.empty:
            return None
        return s[~s.index.duplicated(keep="last")].sort_index()

    for col in ["headline_cpi", "core_cpi", "headline_pce", "core_pce",
                "ppi_final_demand", "ppi_core", "cpi_core_services", "cpi_shelter"]:
        s = _rel(col)
        put(f"{col}_yoy", (s.pct_change(12) * 100.0) if s is not None and len(s) > 12 else None,
            ffill_limit=60)
        # 3-month annualized run-rate — the momentum read (is inflation re-accelerating?)
        put(f"{col}_3m_ann", (((s / s.shift(3)) ** 4 - 1.0) * 100.0)
            if s is not None and len(s) > 3 else None, ffill_limit=60)
    # ECI is QUARTERLY (publish ~1 month after quarter-end) → YoY = 4-period change,
    # carried a full quarter (130 bdays) until the next release.
    for col in ["eci_comp", "eci_wages"]:
        s = _rel(col)
        put(f"{col}_yoy", (s.pct_change(4) * 100.0) if s is not None and len(s) > 4 else None,
            ffill_limit=130)
    # Cleveland MODEL expected-inflation curve (already %, no transform) — the third
    # leg of the market(breakevens) / survey(UMich) / model expectations triangle.
    for col in ["infl_exp_1y", "infl_exp_5y", "infl_exp_10y"]:
        put(col, series.get(col), ffill_limit=45)
    # Fuller curve + 5y inflation leg. (us1y/us3y/us7y added for the Bonds
    # dashboard's near-term-forward spread + curve interpolation; additive — the
    # macro engine does not read them.)
    for col in ["us3m", "us6m", "us1y", "us3y", "us5y", "us7y", "us30y",
                "spread_10y3m", "breakeven_5y", "us5y_real"]:
        put(col, series.get(col))
    f["spread_10y3m"] = f["spread_10y3m"].combine_first(f["us10y"] - f["us3m"])
    # term-premium-adjusted curve slope: strips the term-premium distortion that
    # mechanically inverted the curve in 2019 and 2022-24 without a recession.
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"].fillna(0)

    # CBOE SKEW (tail-risk pricing) + EBP (credit risk appetite).
    skew = store.read("cboe", "skew")
    put("skew", skew["skew"] if skew is not None and "skew" in skew.columns else None)
    ebp = store.read("fedboard", "ebp")
    if ebp is not None:
        put("ebp", ebp["ebp"] if "ebp" in ebp.columns else None, ffill_limit=45)
        put("ebp_recession_prob", ebp["est_prob"] if "est_prob" in ebp.columns else None, ffill_limit=45)
    else:
        f["ebp"] = np.nan
        f["ebp_recession_prob"] = np.nan

    # --- high-frequency real-activity nowcast (research/REAL_ACTIVITY_NOWCAST.md) -
    # Weekly jobless claims + Indeed postings are LEVELS (ffill across the week);
    # the conditions layer reads their trend. Augur-style leading labor reads that
    # front-run the monthly, revised PAYEMS.
    put("initial_claims", series.get("initial_claims"), ffill_limit=10)
    put("initial_claims_4wk", series.get("initial_claims_4wk"), ffill_limit=10)
    put("continued_claims", series.get("continued_claims"), ffill_limit=12)
    put("indeed_postings", series.get("indeed_postings"), ffill_limit=14)
    put("indeed_new_postings", series.get("indeed_new_postings"), ffill_limit=14)
    # Daily withheld income & employment taxes ($mn) — a FLOW, so it is NOT ffilled
    # (carrying a deposit forward would double-count); conditions sums the raw days.
    wt = store.read("treasury", "withheld_taxes")
    put("withheld_taxes", wt.iloc[:, 0] if wt is not None and not wt.empty else None,
        ffill_limit=None)
    # SF Fed Daily News Sentiment — a quant complement to the LLM news digests.
    ns = store.read("frbsf", "news_sentiment")
    put("news_sentiment", ns.iloc[:, 0] if ns is not None and not ns.empty else None,
        ffill_limit=7)

    # --- liquidity ($bn) — FRED merged with official NY Fed / Board sources -------
    walcl = series.get("fed_balance_sheet")
    h41 = store.read("nyfed", "h41_assets")
    if h41 is not None:
        walcl = h41.iloc[:, 0].combine_first(walcl) if walcl is not None else h41.iloc[:, 0]
    put("walcl_bn", walcl / 1000 if walcl is not None else None, ffill_limit=7)  # weekly
    rrp = series.get("on_rrp")
    nyrrp = store.read("nyfed", "rrp")
    if nyrrp is not None:
        rrp = nyrrp.iloc[:, 0].combine_first(rrp) if rrp is not None else nyrrp.iloc[:, 0]
    put("rrp_bn", rrp, ffill_limit=5)
    tga = store.read("treasury", "tga")
    put("tga_bn", tga.iloc[:, 0] / 1000 if tga is not None else None, ffill_limit=5)
    # Net Fed liquidity — the CANONICAL 3-term billions definition (audit #12/#28), now
    # delegated to engine.canon so every surface reads the SAME series. Delta vs the prior
    # inline formula: canon also fills a missing TGA with 0 (was: NaN propagated), so early
    # history / TGA-gap rows now carry the balance-sheet trend instead of going NaN — a
    # strict improvement, identical wherever TGA is present.
    from engine import canon
    f["net_liquidity_bn"] = canon.net_liquidity_bn(f["walcl_bn"], f["rrp_bn"], f["tga_bn"])
    iss = store.read("treasury", "net_issuance")
    if iss is not None:
        put("net_issuance_mn", iss.iloc[:, 0], ffill_limit=None)

    # --- breadth -----------------------------------------------------------------
    br = store.read("breadth", "breadth")
    if br is not None:
        for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
            if col in br.columns:
                put(col, br[col])
    else:
        for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
            f[col] = np.nan
    # small-cap participation (S&P 600) — same columns, sc_ prefix. Stays NaN
    # through history until the collector has run; engine degrades gracefully.
    scb = store.read("smallcap_breadth", "breadth")
    for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
        alias = f"sc_{col}"
        if scb is not None and col in scb.columns:
            put(alias, scb[col])
        else:
            f[alias] = np.nan

    # --- GEX (live only; NaN through history) --------------------------------------
    gex = store.read("cboe", "gex")
    if gex is not None:
        for col in ["net_gex_bn", "flip_strike", "spot_vs_flip_pct"]:
            if col in gex.columns:
                put(col, gex[col], ffill_limit=3)
    else:
        for col in ["net_gex_bn", "flip_strike", "spot_vs_flip_pct"]:
            f[col] = np.nan

    return f
