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

from engine import country_fx as cfx
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
    """One market ETF -> its full cycle record.

    W3.9 (D4-W5b): for a SINGLE-COUNTRY ETF with a known FX pair the PRIMARY record is
    now the **local-currency equity cycle** (the honest "is this market's equity cheap"),
    with the USD-ETF cycle demoted to `rec['usd_record']` (the "USD view" drawer) and a
    separate `rec['fx']` currency-cycle leg + per-turn `fx_share` attribution.  Blocs and
    single-country ETFs whose local series can't be built stay USD-only (the pre-W3.9
    behaviour) with an honest null-FX / usd-basis marker.

    The USD cycle is still computed exactly as before (W2.2: structure on the ETF's USD
    `close_price`, RS-vs-SPY on the TR panel; tr_fallback when the price panel lacks the
    ticker).  W3.9 adds the local leg ON TOP; it never removes the USD leg."""
    full = closes[ticker].dropna() if ticker in closes else pd.Series(dtype=float)
    if len(full) < 300:
        log.warning("intl_cycles: %s too thin (%d rows) — skipped", ticker, len(full))
        return None
    # vol-scaled ZigZag: a 14% reversal is a "major" swing for a calm market
    # (Switzerland) but a wild EM (Brazil/Turkey) swings that much in weeks — scale the
    # threshold up with realised vol so the turn count stays an intermediate-cycle read,
    # not noise. Calm markets stay near the 14% baseline.
    usd_price = sc._price_series(closes_px, ticker, full)
    usd_core = sc._record_core(full, win_start, full.index[-1], pct=sc._zz_pct_for(full),
                               price=usd_price)
    if usd_core is None:
        return None
    flag = meta.get("flag", "")
    name = f"{flag} {meta['name']}".strip()
    name_zh = f"{flag} {meta['name_zh']}".strip() if meta.get("name_zh") else name
    ident = {
        "id": ticker.lower(), "ticker": ticker, "kind": kind,
        "name": name, "short": name, "name_zh": name_zh, "short_zh": name_zh,
        "group": group, "group_zh": GROUP_ZH.get(group, group), "accent": accent,
        "dev": meta.get("dev"), "dev_zh": DEV_ZH.get(meta.get("dev"), meta.get("dev")),
        "desc": meta.get("desc"),
    }

    # ── W3.9 FX decomposition (single-country ETFs only; blocs are null-FX per §5.4) ──
    fxmeta = cfx.FX_REGISTRY.get(ticker) if kind == "sector" else None
    local_rec = None
    fx_leg = None
    if fxmeta is not None:
        try:
            local_rec, fx_leg = _build_fx_decomposition(
                ticker, fxmeta, full, usd_price, win_start)
        except Exception as e:  # noqa: BLE001 — degrade to USD-only, never fatal
            log.warning("intl_cycles: %s FX decomposition failed (%s) — USD-only", ticker, e)
            local_rec = fx_leg = None

    if local_rec is not None:
        # LOCAL cycle is PRIMARY: the card/chart/position render off the top-level fields.
        # The USD cycle is nested for the "USD view" toggle + the checker keeps its own
        # (ticker, price) tape identity through `usd_record` (markets.html reads THAT).
        rec = dict(local_rec)
        rec.update(ident)
        usd_nested = dict(usd_core)
        usd_nested.update(ident)
        sc._apply_leadership(usd_nested, sc._leadership(closes, ticker))
        # markets.html + the cross-page checker read this nested USD record (basis 'price').
        # Carry ticker/id so the consistency checker keys it as the (EWJ, price) tape — it
        # then AGREES with markets.html's USD reading (same tape) and is DECLARED cross-tape
        # against the local primary (EWJ, local_*), exactly as R3-M3 requires.
        rec["usd_record"] = {
            "id": ident["id"], "ticker": ident["ticker"], "kind": ident["kind"],
            "price": usd_nested["price"], "osc": usd_nested["osc"],
            "turns": usd_nested["turns"], "proj": usd_nested["proj"],
            "basis": usd_nested.get("basis"), "now": usd_nested["now"],
        }
        rec["fx"] = fx_leg
        rec["lc_source"] = local_rec.get("_lc_source")
        rec.pop("_lc_source", None)
        # RS-vs-SPY (a US-investor relative-strength read) stays a USD/TR concept — attach
        # it to the PRIMARY now so the leadership rail + card RS chip keep working.
        sc._apply_leadership(rec, sc._leadership(closes, ticker))
    else:
        # USD-only (blocs, or a single-country ETF whose local series couldn't be built).
        rec = dict(usd_core)
        rec.update(ident)
        sc._apply_leadership(rec, sc._leadership(closes, ticker))
        if kind == "sector":
            # single-country ETF with no decomposition → disclosed null-FX + reason.
            rec["fx"] = {"note": "USD basis — FX pair unavailable, currency not decomposed",
                         "note_zh": "美元计价 — 缺汇率数据，未拆分货币"}
            rec["lc_source"] = "none"
        else:
            # bloc: multi-currency, decomposition not defined (§5.4).
            rec["fx"] = {"note": "multi-currency bloc — FX decomposition not defined",
                         "note_zh": "多货币区域 — 未定义汇率拆分"}
            rec["lc_source"] = None
    return rec


def _build_fx_decomposition(ticker: str, fxmeta: dict,
                            full: pd.Series, usd_price: pd.Series | None,
                            win_start: pd.Timestamp,
                            ) -> tuple[dict | None, dict | None]:
    """Build the LOCAL-currency primary cycle record + the separate FX leg for one country.

    Returns (local_rec, fx_leg).  local_rec is None when neither a native local index nor
    a synthetic ETF/FX series can be constructed → the caller falls back to USD-only."""
    # the structure basis for the ETF (close_price when present, else the TR series).
    usd_struct = usd_price.dropna() if (usd_price is not None) else full.dropna()
    fx = cfx.fx_ccy_per_usd(fxmeta)
    local_px, lc_source = cfx.build_local_series(ticker, fxmeta, usd_struct, fx)
    if local_px is None or lc_source == "none":
        return None, None
    local_px = local_px.dropna()
    if local_px.empty or len(local_px[local_px.index >= win_start]) < 60:
        return None, None

    # ── PRIMARY: the local-currency equity cycle (same kernel, price basis) ──
    last_ts = local_px.index[-1]
    local_core = sc._record_core(local_px, win_start, last_ts,
                                 pct=sc._zz_pct_for(local_px), price=local_px)
    if local_core is None:
        return None, None
    local_core = dict(local_core)
    # declare the tape: local_native (clean native index) vs local_synth (ETF×FX). This is
    # the R3-M3 cross-tape basis label — it is what lets the consistency checker allow the
    # local record to differ from the USD/markets record without flagging silent drift.
    basis_label = "local_native" if lc_source == "native" else "local_synth"
    local_core["basis"] = basis_label
    local_core["now"]["basis"] = basis_label
    local_core["_lc_source"] = lc_source

    # ── the separate, graded FX-cycle leg (§5.2): the SAME kernel on the FX price line ──
    fx_leg = None
    if fx is not None and not fx.empty:
        fx_win = fx[fx.index >= win_start]
        fx_leg = {
            "pair": fxmeta["pair"], "quote": "ccy_per_usd", "source": fxmeta["fx_source"],
            "basis": "fx_spot", "lc_source": lc_source,
        }
        if len(fx_win) >= 60:
            try:
                fx_core = sc._record_core(fx, win_start, fx.index[-1],
                                          pct=sc._zz_pct_for(fx), price=fx)
            except Exception as e:  # noqa: BLE001
                log.warning("intl_cycles: %s FX-leg cycle failed (%s)", ticker, e)
                fx_core = None
            if fx_core is not None:
                fxn = fx_core["now"]
                # a RISING ccy_per_usd = the currency WEAKENING → note the direction so the
                # drawer reads "currency stretched/washed" in the right sense.
                fx_leg.update({
                    "cycle_pos": fxn.get("pos"), "cycle_pos_v2": fxn.get("pos_v2"),
                    "cycle_phase": fxn.get("phase"), "cycle_phase_label": fxn.get("phaseLabel"),
                    "leg_return_63d": _leg_return(fx, 63),
                    "leg_return_252d": _leg_return(fx, 252),
                    "price": fx_core["price"], "osc": fx_core["osc"],
                    "turns": fx_core["turns"],
                })
        # HKD-style hard peg → a distance annotation instead of a decomposition (§5.4).
        fx_leg["peg"] = cfx.peg_annotation(fxmeta, fx)

    # ── per-turn equity-vs-FX attribution on the LOCAL turns (§5.3) ──
    # Decompose over the ETF's own USD PRICE tape (structure basis) so the residual is
    # FX (+ any ETF/index tracking gap when local is the native index) — the honest
    # "how much of the USD move was currency" the card badges.
    if fx is not None and not fx.empty:
        _attach_turn_attribution(local_core, local_px, usd_struct, fx)
    return local_core, fx_leg


def _leg_return(s: pd.Series, n: int) -> float | None:
    """Trailing n-bar % change of a level series (labeled FX contribution over a horizon)."""
    s = s.dropna()
    if len(s) <= n:
        return None
    return round((float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1.0) * 100.0, 1)


def _attach_turn_attribution(local_core: dict, local_px: pd.Series,
                             usd_px: pd.Series, fx: pd.Series) -> None:
    """Attach `fx_share` / `fx_flag` to each LOCAL turn by decomposing the USD-tape move
    over the leg since the prior turn (§5.3).  Mutates `local_core['turns']` in place and
    stamps the latest currency-driven turn onto `now` for the card flag."""
    turns = local_core.get("turns", [])
    prev_ts = None
    latest_flag = None
    for t in turns:
        cur_ts = pd.Timestamp(t["date"])
        if prev_ts is not None:
            attr = cfx.attribute_turn(local_px, usd_px, fx, prev_ts, cur_ts)
            if attr is not None:
                t.update(attr)
                if attr.get("fx_flag"):
                    latest_flag = attr
        prev_ts = cur_ts
    # surface the most-recent currency-driven turn on `now` so the card can render the
    # one-glance chip without re-scanning turns JS-side.
    nw = local_core.get("now", {})
    nw["fx_driven_last"] = bool(latest_flag is not None)
    nw["fx_share_last"] = latest_flag.get("fx_share") if latest_flag else None


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
