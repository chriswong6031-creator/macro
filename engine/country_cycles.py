"""Country Cycle Intelligence — data-driven cycle map for international markets.

Sibling of engine/sector_cycles.py. Where that engine derives each US GICS sector
ETF's cycle from its real price tape, THIS one derives each COUNTRY / REGION's cycle
from its USD-listed ETF tape — the iShares MSCI single-country family (EWJ, EWG,
EWZ…) plus the regional/bloc aggregates (EFA, EEM, VGK…). USD denomination is the
deliberate choice: it is a US investor's actual experience, strips out local-FX
noise, and lets every market overlay cleanly on one shared rebased axis. The
single-country ETFs date to 1996, so each market carries ~30y of survivorship-free
history — far cleaner for cycle study than reconstructing a basket from today's
index membership.

Two families, exactly like sector_cycles' sectors-vs-baskets split:
  • COUNTRIES (kind="sector") — ~24 single-country ETFs grouped by region (Europe,
    Developed ex-Europe, EM Asia, EM LatAm, EM EMEA), the default overlay;
  • AGGREGATES (kind="basket") — ~7 regional/bloc ETFs (Developed ex-US, Emerging
    Markets, Europe, Pacific, Asia ex-Japan, Latin America, All-World ex-US), their
    own tab.

The cycle math — rebased price + 0-100 detrended oscillator, ZigZag turns, the
weekly/3-day MACD-confirmed 5-phase wheel, the median-half-cycle next-turn
projection, and RS vs SPY — is reused VERBATIM from engine.sector_cycles, so this
page reads identically to the US and China cycle pages. RS is measured vs SPY: the
honest "are you beating just owning America?" benchmark for an ex-US allocation.

Output JSON is the single source of truth for scripts/build_intl_cycles.py ->
site/intl_cycles.html. Narratives/DNA layer in from data/intl_cycles/. Pure-read +
additive: any failure on one market is logged and skipped, never fatal.
"""
from __future__ import annotations

import logging

import pandas as pd

from engine import sector_cycles as sc
from engine.inputs import yahoo_closes
from lib import config

log = logging.getLogger(__name__)

# ── market universe ─────────────────────────────────────────────────────────
# group = region facet (drives the cross-market filter pills, the analogue of the US
# page's Growth/Cyclical/Defensive). dev = MSCI development tag (shown on the card,
# NOT a facet). flag is prefixed onto the display name so every chip/card/tooltip
# carries it with zero JS change. Regions follow MSCI's own DM/EM classification so
# Korea/Taiwan/China sit in EM Asia and HK/Singapore in Developed ex-Europe.
COUNTRIES: dict[str, dict] = {
    # ── Europe (developed) ──
    "EWG": {"name": "Germany",      "region": "Europe",              "dev": "DM", "flag": "🇩🇪", "name_zh": "德国"},
    "EWU": {"name": "United Kingdom","region": "Europe",             "dev": "DM", "flag": "🇬🇧", "name_zh": "英国"},
    "EWQ": {"name": "France",       "region": "Europe",              "dev": "DM", "flag": "🇫🇷", "name_zh": "法国"},
    "EWL": {"name": "Switzerland",  "region": "Europe",              "dev": "DM", "flag": "🇨🇭", "name_zh": "瑞士"},
    "EWP": {"name": "Spain",        "region": "Europe",              "dev": "DM", "flag": "🇪🇸", "name_zh": "西班牙"},
    "EWI": {"name": "Italy",        "region": "Europe",              "dev": "DM", "flag": "🇮🇹", "name_zh": "意大利"},
    "EWN": {"name": "Netherlands",  "region": "Europe",              "dev": "DM", "flag": "🇳🇱", "name_zh": "荷兰"},
    "EWD": {"name": "Sweden",       "region": "Europe",              "dev": "DM", "flag": "🇸🇪", "name_zh": "瑞典"},
    # ── Developed ex-Europe ──
    "EWJ": {"name": "Japan",        "region": "Developed ex-Europe", "dev": "DM", "flag": "🇯🇵", "name_zh": "日本"},
    "EWA": {"name": "Australia",    "region": "Developed ex-Europe", "dev": "DM", "flag": "🇦🇺", "name_zh": "澳大利亚"},
    "EWH": {"name": "Hong Kong",    "region": "Developed ex-Europe", "dev": "DM", "flag": "🇭🇰", "name_zh": "香港"},
    "EWS": {"name": "Singapore",    "region": "Developed ex-Europe", "dev": "DM", "flag": "🇸🇬", "name_zh": "新加坡"},
    "EWC": {"name": "Canada",       "region": "Developed ex-Europe", "dev": "DM", "flag": "🇨🇦", "name_zh": "加拿大"},
    # ── EM Asia ──
    "FXI": {"name": "China",        "region": "EM Asia",             "dev": "EM", "flag": "🇨🇳", "name_zh": "中国"},
    "INDA":{"name": "India",        "region": "EM Asia",             "dev": "EM", "flag": "🇮🇳", "name_zh": "印度"},
    "EWT": {"name": "Taiwan",       "region": "EM Asia",             "dev": "EM", "flag": "🇹🇼", "name_zh": "台湾"},
    "EWY": {"name": "South Korea",  "region": "EM Asia",             "dev": "EM", "flag": "🇰🇷", "name_zh": "韩国"},
    "EIDO":{"name": "Indonesia",    "region": "EM Asia",             "dev": "EM", "flag": "🇮🇩", "name_zh": "印尼"},
    # ── EM Latin America ──
    "EWZ": {"name": "Brazil",       "region": "EM LatAm",            "dev": "EM", "flag": "🇧🇷", "name_zh": "巴西"},
    "EWW": {"name": "Mexico",       "region": "EM LatAm",            "dev": "EM", "flag": "🇲🇽", "name_zh": "墨西哥"},
    "ECH": {"name": "Chile",        "region": "EM LatAm",            "dev": "EM", "flag": "🇨🇱", "name_zh": "智利"},
    # ── EM EMEA ──
    "EZA": {"name": "South Africa", "region": "EM EMEA",             "dev": "EM", "flag": "🇿🇦", "name_zh": "南非"},
    "TUR": {"name": "Turkey",       "region": "EM EMEA",             "dev": "EM", "flag": "🇹🇷", "name_zh": "土耳其"},
    "EPOL":{"name": "Poland",       "region": "EM EMEA",             "dev": "EM", "flag": "🇵🇱", "name_zh": "波兰"},
}

# regional / bloc aggregates — the "altitude" view; their own tab (kind="basket"),
# grouped into Developed / Emerging / Global blocs for the basket rail.
AGGREGATES: dict[str, dict] = {
    "EFA":  {"name": "Developed ex-US",   "flag": "🌍", "name_zh": "发达市场(除美)", "desc": "MSCI EAFE",            "group": "Developed blocs"},
    "VGK":  {"name": "Europe",            "flag": "🇪🇺", "name_zh": "欧洲",          "desc": "FTSE Dev. Europe",     "group": "Developed blocs"},
    "VPL":  {"name": "Developed Pacific", "flag": "🌏", "name_zh": "发达亚太",       "desc": "FTSE Dev. Pacific",    "group": "Developed blocs"},
    "EEM":  {"name": "Emerging Markets",  "flag": "🌏", "name_zh": "新兴市场",       "desc": "MSCI EM",             "group": "Emerging blocs"},
    "AAXJ": {"name": "Asia ex-Japan",     "flag": "🌏", "name_zh": "亚洲(除日本)",   "desc": "MSCI AC Asia ex-JP",  "group": "Emerging blocs"},
    "ILF":  {"name": "Latin America",     "flag": "🌎", "name_zh": "拉丁美洲",       "desc": "S&P Latin America 40", "group": "Emerging blocs"},
    "VXUS": {"name": "All-World ex-US",   "flag": "🌐", "name_zh": "全球(除美)",     "desc": "FTSE Global ex-US",    "group": "Global"},
}

GROUP_ORDER = ["Europe", "Developed ex-Europe", "EM Asia", "EM LatAm", "EM EMEA"]
GROUP_ZH = {
    "Europe": "欧洲", "Developed ex-Europe": "发达市场(除欧)", "EM Asia": "新兴亚洲",
    "EM LatAm": "新兴拉美", "EM EMEA": "新兴欧非中东",
    "Developed blocs": "发达区域", "Emerging blocs": "新兴区域", "Global": "全球",
}
DEV_ZH = {"DM": "发达", "EM": "新兴"}
# per-region hue base — members fan out around it so the chart reads by region while
# every line stays distinct.
REGION_HUE = {"Europe": 212, "Developed ex-Europe": 168, "EM Asia": 32,
              "EM LatAm": 130, "EM EMEA": 318}


def _accent(region: str, k: int, n: int) -> str:
    """Region-coherent, member-distinct line colour (dark-bg legible HSL)."""
    base = REGION_HUE.get(region, 200)
    spread = 50.0
    hue = (base - spread / 2 + (spread * k / max(1, n - 1) if n > 1 else 0)) % 360
    return f"hsl({round(hue)} 70% 62%)"


def _agg_accent(i: int, n: int) -> str:
    hue = round((i * 360.0 / max(n, 1) + 28) % 360)
    return f"hsl({hue} 30% 70%)"


def _build_one(ticker: str, meta: dict, closes: pd.DataFrame, win_start: pd.Timestamp,
               *, kind: str, group: str, accent: str,
               closes_px: pd.DataFrame | None = None) -> dict | None:
    """One market ETF -> its full cycle record, off the ETF's own USD close tape.
    Reuses engine.sector_cycles._record_core (identical turn/phase/projection math).

    W2.2: structure math runs on the ETF's USD close_price (from `closes_px`) when
    present; RS-vs-SPY stays on the TR panel.  A ticker absent from the price panel is
    stamped tr_fallback (declared close_price gap) — never silent.  NB: the USD-ETF price
    basis is still USD-denominated (FX decomposition to a local-currency cycle is the
    SEPARATE D4-W5 wave); W2.2 only removes the dividend-total-return inflation from the
    structure math, not the FX confound."""
    full = closes[ticker].dropna() if ticker in closes else pd.Series(dtype=float)
    if len(full) < 300:
        log.warning("intl_cycles: %s too thin (%d rows) — skipped", ticker, len(full))
        return None
    # vol-scaled ZigZag: a 14% reversal is a "major" swing for a calm market
    # (Switzerland) but a wild EM (Brazil/Turkey) swings that much in weeks — scale the
    # threshold up with realised vol so the turn count stays an intermediate-cycle read,
    # not noise. Calm markets stay near the 14% baseline.
    price = sc._price_series(closes_px, ticker, full)
    core = sc._record_core(full, win_start, full.index[-1], pct=sc._zz_pct_for(full),
                           price=price)
    if core is None:
        return None
    flag = meta.get("flag", "")
    name = f"{flag} {meta['name']}".strip()
    name_zh = f"{flag} {meta['name_zh']}".strip() if meta.get("name_zh") else name
    rec = dict(core)
    rec.update({
        "id": ticker.lower(), "ticker": ticker, "kind": kind,
        "name": name, "short": name, "name_zh": name_zh, "short_zh": name_zh,
        "group": group, "group_zh": GROUP_ZH.get(group, group), "accent": accent,
        "dev": meta.get("dev"), "dev_zh": DEV_ZH.get(meta.get("dev"), meta.get("dev")),
        "desc": meta.get("desc"),
    })
    sc._apply_leadership(rec, sc._leadership(closes, ticker))
    return rec


def _rank_rs(recs: list[dict]) -> None:
    """Leadership rank (best 63d RS vs SPY = 1) for the 'who leads' read."""
    ranked = sorted([r for r in recs if r["now"].get("rs_63d") is not None],
                    key=lambda r: r["now"]["rs_63d"], reverse=True)
    for n, r in enumerate(ranked, 1):
        r["now"]["rs_rank"] = n


def compute(asof: str | None = None) -> dict | None:
    """Top-level: every market's cycle record + page meta. Returns None if the close
    panel can't be loaded (build script then no-ops)."""
    try:
        closes = yahoo_closes()
    except Exception as e:  # noqa: BLE001
        log.error("intl_cycles: cannot load yahoo_closes: %s", e)
        return None
    if closes is None or closes.empty:
        return None
    # W2.2 price-basis panel for the structure math (never fatal).
    try:
        closes_px = yahoo_closes(basis="price")
    except Exception as e:  # noqa: BLE001
        log.warning("intl_cycles: cannot load price-basis panel (%s) — structure math "
                    "falls back to TR (labeled tr_fallback)", e)
        closes_px = None
    if asof:
        closes = closes[closes.index <= pd.Timestamp(asof)]
        if closes_px is not None:
            closes_px = closes_px[closes_px.index <= pd.Timestamp(asof)]
    last_ts = closes.index[-1]
    win_start = last_ts - pd.DateOffset(years=sc.WINDOW_YEARS)

    # ── countries (kind="sector"), grouped by region ──
    countries: list[dict] = []
    by_region: dict[str, list[str]] = {}
    for tk, m in COUNTRIES.items():
        by_region.setdefault(m["region"], []).append(tk)
    for region, tks in by_region.items():
        for k, tk in enumerate(tks):
            try:
                rec = _build_one(tk, COUNTRIES[tk], closes, win_start, kind="sector",
                                 group=region, accent=_accent(region, k, len(tks)),
                                 closes_px=closes_px)
            except Exception as e:  # noqa: BLE001
                log.exception("intl_cycles: %s failed: %s", tk, e)
                rec = None
            if rec:
                countries.append(rec)
    if not countries:
        return None
    _rank_rs(countries)
    gidx = {g: i for i, g in enumerate(GROUP_ORDER)}
    countries.sort(key=lambda r: (gidx.get(r["group"], 99), r["now"].get("rs_rank") or 999))

    # ── regional / bloc aggregates (kind="basket") ──
    aggs: list[dict] = []
    akeys = list(AGGREGATES.keys())
    for i, tk in enumerate(akeys):
        try:
            rec = _build_one(tk, AGGREGATES[tk], closes, win_start, kind="basket",
                             group=AGGREGATES[tk].get("group", "Aggregate"),
                             accent=_agg_accent(i, len(akeys)), closes_px=closes_px)
        except Exception as e:  # noqa: BLE001
            log.exception("intl_cycles: aggregate %s failed: %s", tk, e)
            rec = None
        if rec:
            aggs.append(rec)
    _rank_rs(aggs)

    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    x_lo = round(sc._yf(win_start), 3)
    x_hi = round(sc._yf(last_ts) + sc._TODAY_PAD, 3)
    x_lo_default = round(sc._yf(last_ts - pd.DateOffset(years=sc.DEFAULT_WINDOW_YEARS)), 3)
    return {
        "meta": {
            "region": "intl",                       # JS branch: US/China untouched
            "asOf": str(last_ts.date()),
            "today": round(sc._yf(last_ts), 3),
            "xDomain": [x_lo, x_hi],
            "xDomainDefault": [x_lo_default, x_hi],
            "window_years": sc.WINDOW_YEARS,
            "default_window_years": sc.DEFAULT_WINDOW_YEARS,
            "rebaseDate": str(win_start.date()),
            "benchmark": bench,
            "n_sectors": len(countries),
            "n_baskets": len(aggs),
        },
        "phases": sc.PHASES,
        "sectors": countries,
        "baskets": aggs,
    }
