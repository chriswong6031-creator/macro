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
            c = json.loads(p.read_text()).get("conviction") or {}
            if c:
                val = {"score": c.get("score"), "band": c.get("band"), "band_zh": c.get("band_zh"),
                       "verdict": c.get("verdict") if isinstance(c.get("verdict"), str) else None,
                       "verdict_zh": c.get("verdict_zh"),
                       "cycle_blocked": bool(c.get("cycle_blocked")),
                       "entry_pct": ((c.get("axes") or {}).get("entry") or {}).get("pct"),
                       "trust": (c.get("trust_tier") or {}).get("tier")}
        except Exception:  # noqa: BLE001
            val = None
    cache[ticker] = val
    return val


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
    n = 0
    for b in data.get("baskets", []):
        bid = b["id"]
        members = [{**m, "conviction": _conviction(m["symbol"], sd_dir, cache)} for m in b.get("members", [])]
        th = tmap.get(bid, {})
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
