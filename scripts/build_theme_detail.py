"""Shared per-theme DETAIL-PAGE builder, region-parameterized.

Renders one site/<out_dir>/<basket_id>.html per theme from templates/basket_detail.html.j2,
plucking each member's per-stock Conviction Profile from the market's own stockdata
(site/<stockdata_dir>/<T>.json) and attaching the advanced textures + score history +
change timeline. Used by build_baskets (US) and build_baskets_{china,hk,canada}.

Additive + graceful: a missing stockdata record renders a "thin" chip, never a crash.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config
from lib.pages import write_page

log = logging.getLogger("build_theme_detail")

# region -> (per-stock conviction dir, output dir under site/, per-stock link base or "").
# Paths are relative to the detail page (site/<out>/<id>.html). China & HK route to their
# single-stock analyzers (china_lookup.html / hk_lookup.html), which load <dir>/<ticker>.json
# off the URL hash — the same ticker format the membership uses, so the links resolve.
# An empty base would render the ticker plain (no link) for any market lacking a per-stock page.
REGIONS = {
    "us":     ("stockdata",        "basket",        "../stock.html#"),
    "china":  ("chinastockdata",   "basket_china",  "../china_lookup.html#"),
    "hk":     ("hkstockdata",      "basket_hk",     "../hk_lookup.html#"),
    "canada": ("canadastockdata",  "basket_canada", "../canada_stock.html#"),
    "intl":   ("intlstockdata",    "basket_intl",   "../intl_stock.html#"),
}


def _personality_slim(rec: dict) -> dict | None:
    """Extract slim personality slice {chart, mode} from a stockdata rec.

    Returns None (fail-open) when personality block is absent or malformed.
    chart: first chart_personality label (str or None).
    mode: first non-'normal' current_mode label (str or None).
    This is display-only context per R-SP13: context chip in holdings table only.
    """
    try:
        p = rec.get("personality")
        if not p:
            return None
        base = p.get("base") or {}
        chart_labels = (base.get("chart_personality") or {}).get("labels") or []
        modes = (p.get("current_mode") or {}).get("modes") or []
        chart = chart_labels[0] if chart_labels else None
        mode = next((m for m in modes if m != "normal"), None)
        if chart is None and mode is None:
            return None
        return {"chart": chart, "mode": mode}
    except Exception:  # noqa: BLE001 — additive, never fatal
        return None


def _conviction(ticker: str, stockdata_dir: str, cache: dict) -> dict | None:
    if ticker in cache:
        return cache[ticker]
    val = None
    p = config.ROOT / "site" / stockdata_dir / (ticker + ".json")
    if p.exists():
        try:
            rec = json.loads(p.read_text())
            c = rec.get("conviction") or {}
            # the THIRD gauge: the owner's T1->T4 confluence cascade verdict (MACD-2D x
            # StochRSI-3D), persisted per name by the {us,china} library builders. The
            # Holdings table renders it as a tier badge and surfaces a fresh cross to the
            # top — the same gate the standout board ranks by. Only carried when a fresh,
            # eligible tier fired; unrated names -> None (no badge, sorts below rated).
            sg = rec.get("signal") or {}
            signal = ({"tier": sg.get("tier_cascade"), "tier_sub": sg.get("tier_sub"),
                       "ticks": sg.get("ticks"), "bars_to_cross": sg.get("bars_to_cross"),
                       "provisional": bool(sg.get("provisional"))}
                      if sg.get("eligible") and sg.get("tier_cascade") else None)
            if c:
                # the SECOND gauge: a compact entry-timing read (US has it; ex-US
                # gracefully omits until those builders wire entry_signal) so a member
                # reads "own-it conviction + buy now / wait for the pullback to $X".
                es = rec.get("entry_signal") or {}
                entry = None
                if es:
                    bz = es.get("buy_zone") or {}
                    entry = {"status": es.get("status"), "act_level": es.get("act_level"),
                             "headline": es.get("headline"), "headline_zh": es.get("headline_zh"),
                             "zone_low": bz.get("low"), "zone_high": bz.get("high"),
                             "zone_pct": bz.get("pct_from_spot")}
                sp = c.get("spotlight") or {}
                val = {"score": c.get("score"), "band": c.get("band"), "band_zh": c.get("band_zh"),
                       "verdict": c.get("verdict") if isinstance(c.get("verdict"), str) else None,
                       "verdict_zh": c.get("verdict_zh"),
                       "cycle_blocked": bool(c.get("cycle_blocked")),
                       "entry_pct": ((c.get("axes") or {}).get("entry") or {}).get("pct"),
                       "valuation_band": c.get("valuation_band"),
                       "validation_status": c.get("validation_status"),
                       "entry": entry,
                       "signal": signal,
                       "trust": (c.get("trust_tier") or {}).get("tier"),
                       # the same theme/sector spotlight tilt the standout board ranks by,
                       # so the theme page and the board can never disagree on a name.
                       "spotlight": sp.get("dir") if sp else None,
                       # W4 stock-personality slim slice (display-only, context chip only).
                       # Fail-open: None when personality block absent (e.g. ex-US markets).
                       "personality": _personality_slim(rec)}
            elif signal:
                # a rated name whose conviction profile is thin/absent: still carry the
                # tier so it renders a badge and surfaces to the top (score None -> "thin").
                val = {"score": None, "signal": signal}
        except Exception:  # noqa: BLE001
            val = None
    cache[ticker] = val
    return val


# region -> member_context artifact filename under site/basketdata/
# intl has no member_context build; absent file → empty index (graceful).
_MC_FILES = {
    "us":     "member_context.json",
    "china":  "member_context_cn.json",
    "hk":     "member_context_hk.json",
    "canada": "member_context_ca.json",
}


def member_context_index(region: str = "us") -> dict[str, dict[str, dict]]:
    """{basket_id -> {ticker -> member_ctx_record}} from the within-basket artifact.

    Returns a two-level dict keyed first by basket_id then by ticker, so the detail
    page can look up each member's band WITHIN its own basket (not cross-basket).
    The record carries: band, band_en, band_zh, tone, parabolic, ext, ext_rel, rs_rank.
    Absent file or parse error → {} (additive, fail-open).
    """
    fname = _MC_FILES.get(region)
    if not fname:
        return {}
    p = config.ROOT / "site" / "basketdata" / fname
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        out: dict[str, dict[str, dict]] = {}
        for theme in (data.get("themes") or []):
            bid = theme.get("id")
            if not bid:
                continue
            basket_map: dict[str, dict] = {}
            for m in (theme.get("members") or []):
                t = m.get("ticker")
                if t:
                    basket_map[t] = m
            out[bid] = basket_map
        return out
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {}


def standout_index(region: str = "us") -> dict[str, dict]:
    """{ticker -> {score, dir}} from a market's standout BUY board, the cross-reference that
    lets a theme page flag which of its members are CURRENTLY on the standout board (and which
    way the spotlight leans). Only US ships a standout board today; other regions -> {}."""
    if region != "us":
        return {}
    out: dict[str, dict] = {}
    p = config.ROOT / "site" / "factordata" / "us_standouts.json"
    if not p.exists():
        return out
    try:
        for r in (json.loads(p.read_text()).get("buy") or []):
            t = r.get("ticker")
            if not t:
                continue
            conv = r.get("conviction") or {}
            out[t] = {"score": conv.get("score"), "dir": (conv.get("spotlight") or {}).get("dir")}
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return out


def build_detail_pages(data: dict, site: Path, env, region: str = "us") -> int:
    """data carries theme_intel + baskets (the build payload). Returns # pages written."""
    from engine import basket_history, basket_score
    sd_dir, out_name, stock_base = REGIONS.get(region, REGIONS["us"])
    ti = data.get("theme_intel") or {}
    tmap = {t["id"]: t for t in ti.get("themes", [])}
    out_dir = site / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("basket_detail.html.j2")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cache: dict = {}
    board = standout_index(region)          # ticker -> {score, dir} from the standout buy board
    mctx = member_context_index(region)     # basket_id -> {ticker -> within-basket ctx}
    n = 0
    for b in data.get("baskets", []):
        bid = b["id"]
        basket_ctx = mctx.get(bid) or {}    # {ticker -> ctx} for THIS basket only
        members = [{**m, "conviction": _conviction(m["symbol"], sd_dir, cache),
                    "on_board": m["symbol"] in board,
                    "member_ctx": basket_ctx.get(m["symbol"])} for m in b.get("members", [])]
        th = {**tmap.get(bid, {}), "weights": ti.get("weights")}   # weights for the composition bar
        detail = {
            "basket": b, "members": members, "theme": th,
            "act_now": basket_score.act_now_stocks(members, th),
            "history": basket_history.score_series(bid, "score", region),
            "timeline": basket_history.change_timeline(bid, region=region),
            "as_of": ti.get("as_of") or b.get("created"),
            "market_concentration": ti.get("market_concentration") or {},
            "stock_base": stock_base, "back": "../baskets.html" if region == "us" else f"../baskets_{region}.html",
            "region": region,                          # for the cross-market narrative chip lookup
            "bench_label": ti.get("bench_label", "S&P 500"),       # regional benchmark for the "vs <bench>" labels
            "bench_label_zh": ti.get("bench_label_zh", "标普500"),
        }
        html = tmpl.render(detail_json=json.dumps(detail, separators=(",", ":"), default=str),
                           basket_name=b.get("name", bid), generated_utc=built,
                           back_href=detail["back"])
        write_page(out_dir / (bid + ".html"), html)
        n += 1
    log.info("[%s] wrote %d theme detail pages -> site/%s/", region, n, out_name)
    return n
