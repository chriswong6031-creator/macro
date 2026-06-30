"""scripts/build_subsector_confluence.py — the Subsector Confluence desk.

Two halves, matching the house data/render split (build_stock_library is heavy-nightly,
build_site renders from the committed JSON):

  main()         HEAVY (nightly engine band). Runs engine.subsector_confluence over the
                 S&P-500 sub-industries + the curated thematic baskets, and writes:
                   • site/marketdata/subsector_confluence.json   (the board: subsectors,
                     11-sector rollup, double-gated funnel, coverage — member tables inline)
                   • site/marketdata/basket_confluence.json      (the thematic-basket desk)
                   • site/subsectorohlc/<key>.json               (per-group synthetic index
                     OHLC bars, the chart contract — same shape as site/ohlc/<T>.json)
                   • site/subsector_signals/<key>.json           (per-group §7 BUY/SELL markers)

  render_pages() LIGHT (build_site render lane). Reads the committed JSON and renders
                 site/subsectors.html (the board) + site/subsector/<key>.html (one detail
                 page per group, with the index chart + member table). No recompute.

DISPLAY-ONLY, additive, never fatal. See engine/subsector_confluence.py for the honesty
contract (equal-weight, today's membership, EOD daily, calendar 3D buckets, not alpha).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine import subsector_confluence as sc
from lib import config

log = logging.getLogger(__name__)

OHLC_DIR = "subsectorohlc"
SIG_DIR = "subsector_signals"
DETAIL_DIR = "subsector"
BOARD_JSON = "marketdata/subsector_confluence.json"
BASKET_JSON = "marketdata/basket_confluence.json"


# ----------------------------------------------------------------- helpers ----

def _clean(o):
    """Recursively coerce numpy scalars to native and replace NaN/Inf with None so the payload is
    strict JSON (json.dumps allow_nan=False safe; JS JSON.parse safe)."""
    if isinstance(o, np.generic):          # np.int64 / np.bool_ / np.float64 -> native python
        o = o.item()
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _bars_from_candle(cand) -> list[list]:
    """The §7 chart contract: [[YYYY-MM-DD, open, high, low, close, dollar_vol], ...]."""
    rows = []
    for ts, r in cand.iterrows():
        c = r.get("close")
        if c is None or (isinstance(c, float) and math.isnan(c)):
            continue
        def _n(x, nd=4):
            return None if (x is None or (isinstance(x, float) and math.isnan(x))) else round(float(x), nd)
        rows.append([ts.strftime("%Y-%m-%d"), _n(r.get("open")), _n(r.get("high")),
                     _n(r.get("low")), _n(r.get("close")), _n(r.get("dollar_vol"), 0)])
    return rows


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), separators=(",", ":"), allow_nan=False))


def _detail_key(g: dict) -> str:
    """Detail-page/file key. Baskets are namespaced ('b-') so they never collide with a
    sub-industry slug."""
    return ("b-" + g["key"]) if g.get("kind") == "basket" else g["key"]


def _emit_group_files(site: Path, g: dict) -> None:
    """Write a group's chart OHLC + §7 signal file; mutate g to drop the heavy series and
    record the keys the detail page chart will mount."""
    key = _detail_key(g)
    cand = g.pop("_candle", None)
    markers = g.pop("_markers", None) or {}
    if cand is not None:
        _write_json(site / OHLC_DIR / f"{key}.json", {"t": key, "o": 1, "src": "subsector",
                                                       "bars": _bars_from_candle(cand)})
        g["chart_key"] = key
    if markers.get("markers"):
        _write_json(site / SIG_DIR / f"{key}.json", markers)
        g["has_signals"] = True


# ----------------------------------------------------------- heavy: data -------

def _build_payloads(site: Path, generated_utc: str) -> tuple[dict, dict]:
    """Run both engines, emit the per-group chart/signal files, return the two board payloads
    (with the heavy series stripped, ready to serialise)."""
    subs = sc.compute_subsector_confluence()
    for g in subs.get("subsectors", []) + subs.get("sectors", []):
        _emit_group_files(site, g)
    subs["generated_utc"] = generated_utc

    baskets_payload = {"ok": False, "baskets": [], "double_gated": {"double_buy": [], "headwind_warn": []}}
    try:
        mp = config.data_dir() / "baskets" / "membership.json"
        mem = json.loads(mp.read_text())
        baskets_payload = sc.compute_basket_confluence(mem.get("baskets") or mem)
        for g in baskets_payload.get("baskets", []):
            _emit_group_files(site, g)
    except Exception as e:  # noqa: BLE001 — themes desk is additive
        log.error("basket confluence failed: %s", e)
    baskets_payload["generated_utc"] = generated_utc
    return subs, baskets_payload


def main() -> dict:
    """Nightly: compute + write all JSON / chart / signal files. Returns a small summary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    site = config.ROOT / config.load()["storage"]["site_dir"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subs, baskets = _build_payloads(site, generated)
    _write_json(site / BOARD_JSON, subs)
    _write_json(site / BASKET_JSON, baskets)
    # render the board + detail pages from the FRESH data (so the nightly desk-band run is
    # self-contained; build_site's render hook covers the render-only express lane separately)
    n = render_pages(site, _env(), generated)
    log.info("subsector_confluence: %d subsectors (%d entry-now), %d baskets, %d pages — as_of %s",
             len(subs.get("subsectors", [])), len(subs.get("entry_now", [])),
             len(baskets.get("baskets", [])), n, subs.get("as_of"))
    return {"subsectors": len(subs.get("subsectors", [])), "entry_now": subs.get("entry_now", []),
            "baskets": len(baskets.get("baskets", [])), "pages": n, "as_of": subs.get("as_of")}


# --------------------------------------------------------- light: render -------

def _env():
    from jinja2 import Environment, FileSystemLoader
    return Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)


def render_pages(site: Path, env=None, generated_utc: str | None = None) -> int:
    """Render the board page + one detail page per group FROM the committed JSON. Returns the
    number of detail pages written. Safe to call in the render-only express lane (no recompute)."""
    env = env or _env()
    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        subs = json.loads((site / BOARD_JSON).read_text())
    except Exception as e:  # noqa: BLE001
        log.error("subsector_confluence board JSON missing (%s) — run main() first", e)
        return 0
    try:
        baskets = json.loads((site / BASKET_JSON).read_text())
    except Exception:  # noqa: BLE001
        baskets = {"baskets": []}

    # the board page
    (site / "subsectors.html").write_text(
        env.get_template("subsectors.html.j2").render(generated_utc=generated_utc))

    # one detail page per group (subsectors + curated baskets)
    out_dir = site / DETAIL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("subsector_detail.html.j2")
    n = 0
    groups = [("subsector", g) for g in subs.get("subsectors", [])] + \
             [("basket", g) for g in baskets.get("baskets", [])]
    for kind, g in groups:
        key = _detail_key(g)
        detail = {
            "group": g, "kind": kind, "as_of": g.get("as_of"),
            "ohlc_dir": OHLC_DIR, "sig_dir": SIG_DIR,
            "back": "../subsectors.html",
            "stock_base": "../stock.html#",
            "generated_utc": generated_utc,
        }
        html = tmpl.render(detail_json=json.dumps(_clean(detail), separators=(",", ":"), allow_nan=False),
                           group_name=g.get("label", key), chart_key=g.get("chart_key"),
                           has_signals=bool(g.get("has_signals")), generated_utc=generated_utc)
        (out_dir / f"{key}.html").write_text(html)
        n += 1
    log.info("subsector_confluence: rendered subsectors.html + %d detail pages", n)
    return n


def build(site: Path, generated_utc: str | None = None) -> int:
    """build_site entrypoint (render lane)."""
    return render_pages(site, _env(), generated_utc)


if __name__ == "__main__":
    main()
