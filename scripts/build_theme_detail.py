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

log = logging.getLogger("build_theme_detail")

# region -> (per-stock conviction dir, output dir under site/, per-stock link base or "").
# Paths are relative to the detail page (site/<out>/<id>.html). China & HK have no per-stock
# page (only a board) → empty base renders the ticker plain (no broken link).
REGIONS = {
    "us":     ("stockdata",        "basket",        "../stock.html#"),
    "china":  ("chinastockdata",   "basket_china",  ""),
    "hk":     ("hkstockdata",      "basket_hk",     ""),
    "canada": ("canadastockdata",  "basket_canada", "../canada_stock.html#"),
    "intl":   ("intlstockdata",    "basket_intl",   "../intl_stock.html#"),
}


def _conviction(ticker: str, stockdata_dir: str, cache: dict) -> dict | None:
    if ticker in cache:
        return cache[ticker]
    val = None
    p = config.ROOT / "site" / stockdata_dir / (ticker + ".json")
    if p.exists():
        try:
            rec = json.loads(p.read_text())
            c = rec.get("conviction") or {}
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
                       "trust": (c.get("trust_tier") or {}).get("tier"),
                       # the same theme/sector spotlight tilt the standout board ranks by,
                       # so the theme page and the board can never disagree on a name.
                       "spotlight": sp.get("dir") if sp else None}
        except Exception:  # noqa: BLE001
            val = None
    cache[ticker] = val
    return val


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
    n = 0
    for b in data.get("baskets", []):
        bid = b["id"]
        members = [{**m, "conviction": _conviction(m["symbol"], sd_dir, cache),
                    "on_board": m["symbol"] in board} for m in b.get("members", [])]
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
        }
        html = tmpl.render(detail_json=json.dumps(detail, separators=(",", ":"), default=str),
                           basket_name=b.get("name", bid), generated_utc=built,
                           back_href=detail["back"])
        (out_dir / (bid + ".html")).write_text(html)
        n += 1
    log.info("[%s] wrote %d theme detail pages -> site/%s/", region, n, out_name)
    return n
