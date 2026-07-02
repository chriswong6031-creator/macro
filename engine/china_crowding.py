"""Multi-leg crowding / fragility map for A-share names (Stage 6c).

A CONTRARIAN FRAGILITY read, not a signal. The single ``leverage_crowded`` flag the
alt-data desk carries today is too thin — leverage alone is noisy, and China has
fragility legs the US has no analogue for (share-pledge tails, limit-up froth). This
fuses FIVE independent froth legs into one k-of-N conjunction (fires at >=3 of 5),
mirroring the US ``engine/crowding.fragility`` conjunction but tuned looser because the
A-share legs are noisier and the pledge tail is China-specific.

  margin_froth     tushare margin →      per-name financing balance pctile >= 80
                   china_margin_detail   (Tushare daily_basic preferred; free cache is the fallback)
  pledge_tail      china_pledge          share-pledge ratio >= 50  (China-specific)
  limitup_froth    china_zt_pool         consec boards >= 2 OR turnover > 25
  attention_spike  china_comment         Eastmoney 关注指数 attention pctile >= 85
  rich_valuation   tushare valuation →   per-name mean(PE,PB) pctile >= 80 (Tushare daily_basic
                   china_a_valuation     preferred); fallback: whole-A market level when no per-name

DISPLAY-ONLY. ``china_crowding.v1`` carries a NOTE: this is a latest-snapshot contrarian
fragility read with NO forward edge proven — it is ORDERING context (which crowded names
are most fragile), never a scored axis into any allocation. Reads the on-disk parquets via
pandas, matches columns by SUBSTRING (akshare column names drift across versions), and
degrades to {} whenever a source is missing — never raises into a build.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors.china_analyst import _num
from engine.tushare_freshness import prefer_tushare

log = logging.getLogger("china_crowding")

SCHEMA = "china_crowding.v1"

# Display-only honesty stamp — every consumer surfaces this verbatim.
NOTE = (
    "Contrarian fragility, latest-snapshot. NOT scored, no forward edge proven — "
    "ordering context only, never an allocation axis."
)
NOTE_ZH = "逆向脆弱度（最新快照）。非评分、未验证前瞻性 — 仅排序上下文，绝不进入配置。"

# k-of-5: fragility fires when at least this many legs are lit.
_K_OF_N = 3
_N_LEGS = 5

# pctile / threshold knobs (per the Stage-6c spec)
_MARGIN_PCTILE = 80.0
_PLEDGE_RATIO = 50.0
_LIMITUP_CONSEC = 2
_LIMITUP_TURNOVER = 25.0
_ATTENTION_PCTILE = 85.0
_VALUATION_PCTILE = 80.0
_MARKET_RICH_PCTILE = 80.0   # whole-A fallback when no per-name PE/PB

# Bilingual leg labels (keys are English; zh shown in templates).
FLAG_LABELS: dict[str, tuple[str, str]] = {
    "margin_froth": ("Margin froth", "融资拥挤"),
    "pledge_tail": ("Pledge tail-risk", "质押尾部风险"),
    "limitup_froth": ("Limit-up froth", "涨停拥挤"),
    "attention_spike": ("Attention spike", "关注度飙升"),
    "rich_valuation": ("Rich valuation", "估值偏高"),
}


# --------------------------------------------------------------------------- io
# append-only drip caches carry a PIT history now; this engine wants the latest single-day snapshot.
_DRIP_DATE_COL = {"china_zt_pool": "date", "china_margin_detail": "date", "china_lhb": "asof"}


def _read(group: str, file: str) -> pd.DataFrame | None:
    """Read data/<group>/<file>.parquet, or None on any miss/error."""
    p = config.data_dir() / group / f"{file}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — a broken cache must never break a build
        log.warning("china_crowding: %s/%s unreadable (%s)", group, file, e)
        return None
    dc = _DRIP_DATE_COL.get(group)
    if dc and df is not None and dc in df.columns:
        from collectors._drip import latest_snapshot
        df = latest_snapshot(df, dc)                        # single-day snapshot from PIT history
    return df if df is not None and len(df) else None


def _valuation_df() -> pd.DataFrame | None:
    """Per-name (preferred) or whole-A (fallback) valuation frame with pe_pctile / pb_pctile (0..100).

    PREFERS the GATED Tushare daily_basic snapshot (data/tushare/valuation.parquet) — a per-NAME
    cross-section that lets ``rich_valuation`` fire stock-by-stock; its pe_pctile/pb_pctile are
    already 0..100 — but ONLY when it is not stale relative to the free anchor (asof-aware; a
    frozen Tushare token must not beat a fresh free source, masterplan §W6-CN fix 4). Falls back
    to the free whole-MARKET china_a_val anchor (one row/day) otherwise. None if neither."""
    tv = _read("tushare", "valuation")
    tv_ok = (tv is not None and "ticker" in tv.columns
             and ("pe_pctile" in tv.columns or "pb_pctile" in tv.columns))
    free = _market_valuation_df()
    if tv_ok:
        chosen, src = prefer_tushare(tv, _read("china_a_val", "pe"))
        if src == "tushare":
            return tv                                 # per-name path, fresh enough
    return free


def _market_valuation_df() -> pd.DataFrame | None:
    """Whole-A valuation anchor (one row): china_a_val pe + pb latest 10y percentiles on a 0..100
    scale (the collector stores them as 0..1 fractions). None if absent. Drives the market-regime
    fallback leg only — never per-name."""
    pe = _read("china_a_val", "pe")
    pb = _read("china_a_val", "pb")
    if pe is None and pb is None:
        return None
    row = {}
    for df, pct_col, out_col in ((pe, "pe_pctile_10y", "pe_pctile"), (pb, "pb_pctile_10y", "pb_pctile")):
        if df is None or df.empty:
            continue
        c = _col(df, pct_col, "pe_pctile" if out_col == "pe_pctile" else "pb_pctile")
        if not c:
            continue
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(s):
            v = float(s.iloc[-1])
            row[out_col] = v * 100.0 if v <= 1.0 else v   # 0..1 fraction → 0..100
    if not row:
        return None
    return pd.DataFrame([row])


def _col(df: pd.DataFrame, *needles: str) -> str | None:
    """First column whose name contains ANY needle as a substring (drift-tolerant)."""
    for c in df.columns:
        s = str(c)
        for n in needles:
            if n in s:
                return c
    return None


def _ticker_col(df: pd.DataFrame) -> str | None:
    return _col(df, "ticker", "代码", "code")


def _pctile_flags(series: pd.Series, thr: float) -> set[str]:
    """Tickers (index) whose value is at/above the cross-sectional `thr` percentile."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 5:
        return set()
    cut = s.quantile(thr / 100.0)
    return set(s[s >= cut].index.astype(str))


# ------------------------------------------------------------------- leg builders
def _margin_froth() -> set[str]:
    """Per-name financing crowding: top-pctile financing-balance NORMALIZED BY float market cap.

    W6-CN Fix 6 (research/CHINA_ENGINE_REASSESSMENT.md §medium-problems):
    The original implementation ranked RAW 融资余额 (financing balance in CNY) cross-sectionally,
    which is purely a large-cap detector (~1,100 names 'crowded' just by size). Fix: normalize
    margin balance by circulating market cap (circ_mv_yi from tushare/valuation.parquet) to get
    a float-leverage ratio. Falls back to fin_pct_float if available, then to raw balance only
    as a last resort (with a degradation note). This measures ACTUAL leverage intensity per name.

    Source selection is ASOF-AWARE (masterplan §W6-CN fix 4): prefer the GATED Tushare
    margin_detail snapshot only when it is not stale relative to the free china_margin_detail
    cache — a frozen Tushare token must not beat a fresh free source.
    """
    tv = _read("tushare", "margin")
    free = _read("china_margin_detail", "detail")
    df, _src = prefer_tushare(tv if (tv is not None and _ticker_col(tv) is not None) else None, free)
    if df is None:
        return set()
    tcol = _ticker_col(df)
    if not tcol:
        return set()
    df = df.copy()
    df.index = df[tcol].astype(str)

    # Prefer fin_pct_float (already normalized) if present
    vcol = _col(df, "fin_pct_float", "pct_float")
    if vcol:
        return _pctile_flags(df[vcol], _MARGIN_PCTILE)

    # No float-normalized column: compute fin_balance / circ_mv ourselves.
    bal_col = _col(df, "fin_balance", "融资余额", "balance")
    if not bal_col:
        return set()

    # Read circ_mv from tushare/valuation.parquet — asof-aware (masterplan §W6-CN fix 4):
    # a frozen valuation plane must not silently supply stale float caps. If it is stale vs
    # the free anchor, prefer_tushare returns None and we fall back to raw balance below.
    val, _vsrc = prefer_tushare(_read("tushare", "valuation"), _read("china_a_val", "pe"))
    if _vsrc != "tushare":
        val = None
    circ_mv = None
    if val is not None:
        vtcol = _ticker_col(val)
        mvcol = _col(val, "circ_mv_yi", "circ_mv", "流通市值")
        if vtcol and mvcol:
            val = val.copy()
            val.index = val[vtcol].astype(str)
            circ_mv = pd.to_numeric(val[mvcol], errors="coerce")

    bal = pd.to_numeric(df[bal_col], errors="coerce")
    if circ_mv is not None and not circ_mv.empty:
        # Align on common tickers and compute leverage ratio
        common = bal.index.intersection(circ_mv.index)
        if len(common) >= 50:
            ratio = bal.loc[common] / circ_mv.loc[common].replace(0, float("nan"))
            ratio = ratio.dropna()
            if len(ratio) >= 50:
                log.debug("china_crowding margin_froth: normalized by circ_mv (%d names)", len(ratio))
                return _pctile_flags(ratio, _MARGIN_PCTILE)
        log.debug("china_crowding margin_froth: circ_mv join too sparse (%d common) — using raw balance", len(common))

    # Last resort: raw balance (known to be a large-cap detector; logged)
    log.debug("china_crowding margin_froth: no circ_mv available — raw balance (size proxy caveat)")
    return _pctile_flags(bal, _MARGIN_PCTILE)


def _pledge_tail() -> set[str]:
    """Share-pledge ratio >= 50 (forced-liquidation overhang). China-specific."""
    df = _read("china_pledge", "pledge")
    if df is None:
        return set()
    tcol = _ticker_col(df)
    rcol = _col(df, "pledge_ratio", "质押比例", "pledge")
    if not tcol or not rcol:
        return set()
    out: set[str] = set()
    for _, r in df.iterrows():
        v = _num(r.get(rcol))
        if v is not None and v >= _PLEDGE_RATIO:
            out.add(str(r.get(tcol)))
    return out


def _limitup_froth() -> set[str]:
    """In the limit-up pool with consec boards >= 2 OR turnover > 25%."""
    df = _read("china_zt_pool", "pool")
    if df is None:
        return set()
    tcol = _ticker_col(df)
    if not tcol:
        return set()
    ccol = _col(df, "consec_boards", "consec", "连板", "连续")
    ucol = _col(df, "turnover_pct", "turnover", "换手")
    out: set[str] = set()
    for _, r in df.iterrows():
        t = str(r.get(tcol))
        consec = _num(r.get(ccol)) if ccol else None
        turn = _num(r.get(ucol)) if ucol else None
        if (consec is not None and consec >= _LIMITUP_CONSEC) or \
           (turn is not None and turn > _LIMITUP_TURNOVER):
            out.add(t)
    return out


def _attention_spike() -> set[str]:
    """Eastmoney 关注指数 attention in the top pctile cross-sectionally."""
    df = _read("china_comment", "detail")
    if df is None:
        return set()
    tcol = _ticker_col(df)
    acol = _col(df, "attention", "关注指数", "关注")
    if not tcol or not acol:
        return set()
    df = df.copy()
    df.index = df[tcol].astype(str)
    return _pctile_flags(df[acol], _ATTENTION_PCTILE)


def _rich_valuation() -> set[str]:
    """mean(PE,PB) pctile >= 80 per-name vs OWN HISTORY; fallback to whole-A market level.

    W6-CN Fix 6 (research/CHINA_ENGINE_REASSESSMENT.md §medium-problems):
    The original implementation used the Tushare CROSS-SECTIONAL pe_pctile/pb_pctile, which
    ranks each name against ALL other A-shares AT ONE MOMENT. Because A-share PE/PB are
    roughly uniformly distributed cross-sectionally, this produced ~1,100 names 'rich' daily
    by construction (the top-quintile of a uniform distribution is exactly 20%). Fix: prefer
    the HISTORICAL percentile (each name's PE/PB vs its OWN trailing history), which measures
    actual richness relative to where that name historically traded.

    The china_valuation percentile cache (data/china_a_valuation/ or tushare/valuation.parquet)
    may carry both cross-sectional and historical variants. We prefer columns ending in '_hist'
    or '_own' before falling back to the cross-sectional ones. If only cross-sectional columns
    are available, we issue a debug note and proceed (behaviour is unchanged from the pre-fix
    code, but the degradation is now explicit).

    If no per-name PE/PB cache exists, falls back to the whole-A valuation anchor: when
    the broad market sits in its top valuation decile, the whole universe inherits the
    rich-valuation leg (so the conjunction can still gate on regime froth).
    """
    df = _valuation_df()
    if df is not None:
        tcol = _ticker_col(df)
        if tcol:
            d = df.copy()
            d.index = d[tcol].astype(str)
            # Prefer vs-own-history percentile columns (suffixed _hist, _own, _10y, or _5y)
            pe_hist = _col(df, "pe_pctile_hist", "pe_pctile_own", "pe_pctile_10y")
            pb_hist = _col(df, "pb_pctile_hist", "pb_pctile_own", "pb_pctile_10y")
            if pe_hist or pb_hist:
                parts = [pd.to_numeric(d[c], errors="coerce") for c in (pe_hist, pb_hist) if c]
                mean_pctile = sum(parts) / len(parts)
                mean_pctile = mean_pctile.dropna()
                if len(mean_pctile) >= 50:
                    log.debug("china_crowding rich_valuation: using vs-own-history pctile (%d names)", len(mean_pctile))
                    return _pctile_flags(mean_pctile, _VALUATION_PCTILE)

            # Fallback: cross-sectional percentile columns (pre-fix behaviour, now explicit)
            pe = _col(df, "pe_pctile", "pe_pctile10y")
            pb = _col(df, "pb_pctile", "pb_pctile10y")
            if pe or pb:
                parts = [pd.to_numeric(d[c], errors="coerce") for c in (pe, pb) if c]
                mean_pctile = sum(parts) / len(parts)
                mean_pctile = mean_pctile.dropna()
                if len(mean_pctile) >= 50:
                    log.debug("china_crowding rich_valuation: only cross-sectional pctile available "
                              "(uniform-rank caveat — ~%d names 'rich' by construction)", len(mean_pctile) // 5)
                    return _pctile_flags(mean_pctile, _VALUATION_PCTILE)

    # Fallback: whole-A market level — if rich, every name inherits the leg.
    anchor = _market_anchor()
    if anchor is not None and anchor >= _MARKET_RICH_PCTILE:
        return {"*"}            # sentinel: applies to every ticker
    return set()


def _market_anchor() -> float | None:
    """Whole-A valuation anchor = mean(PE pctile, PB pctile), 0..100. None if absent. Always the
    whole-MARKET frame (decoupled from the now-per-name _valuation_df)."""
    df = _market_valuation_df()
    if df is None:
        return None
    acol = _col(df, "market_valuation_anchor", "valuation_anchor", "anchor")
    if acol:
        vals = pd.to_numeric(df[acol], errors="coerce").dropna()
        if len(vals):
            return float(vals.iloc[-1])
    pe = _col(df, "pe_pctile", "pe_pctile10y")
    pb = _col(df, "pb_pctile", "pb_pctile10y")
    parts = [pd.to_numeric(df[c], errors="coerce").dropna() for c in (pe, pb) if c]
    parts = [p for p in parts if len(p)]
    if parts:
        return float(sum(p.iloc[-1] for p in parts) / len(parts))
    return None


# ------------------------------------------------------------------- public API
def compute_crowding_map() -> dict[str, dict]:
    """{ticker: {flags:[...], score: float}} for every name with >=3 of 5 froth legs lit.

    ``flags`` are the lit leg keys (English; pair with FLAG_LABELS for bilingual labels);
    ``score`` = (#legs lit)/5 in [0,1], ORDERING ONLY — which crowded names are most
    fragile, never a scored axis. Degrades to {} when no source parquet is present."""
    legs: dict[str, set[str]] = {
        "margin_froth": _margin_froth(),
        "pledge_tail": _pledge_tail(),
        "limitup_froth": _limitup_froth(),
        "attention_spike": _attention_spike(),
        "rich_valuation": _rich_valuation(),
    }
    # Market-wide sentinel (rich_valuation fallback) applies to every named ticker.
    named: set[str] = set()
    for s in legs.values():
        named |= {t for t in s if t and t != "*"}
    market_legs = {k for k, s in legs.items() if "*" in s}

    out: dict[str, dict] = {}
    for t in named:
        lit = [k for k, s in legs.items() if t in s] + sorted(market_legs)
        lit = sorted(set(lit))
        if len(lit) >= _K_OF_N:
            out[t] = {"flags": lit, "score": round(len(lit) / _N_LEGS, 3)}
    return out


def flags_for(ticker: str | None) -> list[str]:
    """Lit fragility flag keys for one ticker ([] if not fragile / sources absent)."""
    if not ticker:
        return []
    return compute_crowding_map().get(str(ticker), {}).get("flags", [])


def build() -> dict:
    """Whole map plus the schema/NOTE envelope for a JSON emit (is_context_only)."""
    cmap = compute_crowding_map()
    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "note_en": NOTE,
        "note_zh": NOTE_ZH,
        "k_of_n": _K_OF_N,
        "n_legs": _N_LEGS,
        "labels": {k: {"en": en, "zh": zh} for k, (en, zh) in FLAG_LABELS.items()},
        "by_ticker": cmap,
        "n": len(cmap),
        "market_anchor": _market_anchor(),
    }
