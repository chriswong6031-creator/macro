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
from lib.pages import write_page

log = logging.getLogger(__name__)

OHLC_DIR = "subsectorohlc"
SIG_DIR = "subsector_signals"
DETAIL_DIR = "subsector"
BOARD_JSON = "marketdata/subsector_confluence.json"
BASKET_JSON = "marketdata/basket_confluence.json"

# China 同花顺 (THS) concept desk — namespaced so it never clobbers the US outputs.
CN_OHLC_DIR = "subsectorohlc_china"
CN_SIG_DIR = "subsector_signals_china"
CN_DETAIL_DIR = "subsector_china"
CN_BOARD_JSON = "marketdata/subsector_confluence_china.json"


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
    """Detail-page/file key within a desk's own dirs. US curated baskets are namespaced ('b-') so
    they never collide with a sub-industry slug in the SHARED US dirs. China concepts live in their
    OWN dirs (subsector_china/, …) and carry a 'ths-' slug already, so no extra prefix is needed."""
    return ("b-" + g["key"]) if g.get("kind") == "basket" else g["key"]


def _prune_orphan_details(out_dir: Path, live_keys: set[str]) -> int:
    """Delete detail `*.html` in ``out_dir`` whose key is no longer on the board.

    Correct-by-construction: ``live_keys`` is the exact set of keys written in the
    SAME render pass, so only true orphans — a concept/subsector dropped from the
    board (e.g. the THS 344->248 curation left 99 dead pages) — are removed, never
    a live page. Callers MUST guard on ``n > 0`` so an empty/failed render (missing
    board JSON) can never nuke a live directory."""
    removed = 0
    for f in out_dir.glob("*.html"):
        if f.stem not in live_keys:
            f.unlink()
            removed += 1
    return removed


def _emit_group_files(site: Path, g: dict, ohlc_dir: str = OHLC_DIR, sig_dir: str = SIG_DIR) -> None:
    """Write a group's chart OHLC + §7 signal file into the given desk dirs; mutate g to drop the
    heavy series and record the keys the detail page chart will mount."""
    key = _detail_key(g)
    cand = g.pop("_candle", None)
    markers = g.pop("_markers", None) or {}
    if cand is not None:
        _write_json(site / ohlc_dir / f"{key}.json", {"t": key, "o": 1, "src": "subsector",
                                                      "bars": _bars_from_candle(cand)})
        g["chart_key"] = key
    if markers.get("markers"):
        # RC-R2 append-only marker law: merge with the previously RENDERED file so a
        # nightly recompute can never re-date or delete a marker the site already showed
        # (engine/marker_integrity.py — divergence disclosed in payload["pit"]).
        sig_path = site / sig_dir / f"{key}.json"
        try:
            prev = json.loads(sig_path.read_text()) if sig_path.exists() else None
        except Exception:  # noqa: BLE001 — unreadable prior file → treat as new
            prev = None
        from engine import marker_integrity
        markers = marker_integrity.merge_payload(prev, markers)
        _write_json(sig_path, markers)
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
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    return env


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
    write_page(site / "subsectors.html",
        env.get_template("subsectors.html.j2").render(generated_utc=generated_utc))

    # one detail page per group (subsectors + curated baskets)
    out_dir = site / DETAIL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("subsector_detail.html.j2")
    n = 0
    live: set[str] = set()
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
        write_page(out_dir / f"{key}.html", html)
        live.add(key)
        n += 1
    if n:  # never prune on an empty/failed render
        pruned = _prune_orphan_details(out_dir, live)
        if pruned:
            log.info("subsector_confluence: pruned %d orphaned detail page(s)", pruned)
    log.info("subsector_confluence: rendered subsectors.html + %d detail pages", n)
    return n


def build(site: Path, generated_utc: str | None = None) -> int:
    """build_site entrypoint (render lane)."""
    return render_pages(site, _env(), generated_utc)


# ----------------------------------------------------- China 同花顺 (THS) desk ----

def main_china() -> dict:
    """Nightly (cl_china band): compute the China 同花顺 concept confluence desk + write its
    namespaced JSON / chart / signal files + render its pages. Mirrors main() for the US desk."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    site = config.ROOT / config.load()["storage"]["site_dir"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cn = sc.compute_china_ths_confluence()
    for g in cn.get("baskets", []):
        _emit_group_files(site, g, ohlc_dir=CN_OHLC_DIR, sig_dir=CN_SIG_DIR)
    cn["generated_utc"] = generated
    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # subsectors_china JSON header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        cn["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("subsectors_china: sleeve chip failed (%s)", e)
    # Validated AI-semis slice confirmer (W6-CN Fix 3 — #773) — wire global AI-semis
    # (SMH/SOXX/TSM 4w-mom) → next-week CN CPO/PCB/storage_chip tailwind chip on the
    # subsectors_china board. Display chip + JSON field; no name-level gating.
    try:
        from engine.cn_ai_semis_confirmer import compute as _semis_compute, is_target_basket
        semis_chip = _semis_compute()
        cn["ai_semis_confirmer"] = semis_chip
        # Annotate each AI-supply THS concept basket with the chip
        for b in cn.get("baskets", []):
            if is_target_basket(b.get("id", "") or b.get("key", "")):
                b["ai_semis_confirmer"] = semis_chip
        log.info("subsectors_china AI-semis confirmer: %s (mom_4w=%s)",
                 semis_chip.get("state"), semis_chip.get("semis_mom_4w"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("subsectors_china: AI-semis confirmer failed (%s)", e)
    _write_json(site / CN_BOARD_JSON, cn)
    n = render_china_pages(site, _env(), generated)
    log.info("subsector_confluence[CHINA]: %d THS concepts (%d entry-now), %d pages — as_of %s",
             len(cn.get("baskets", [])), len(cn.get("entry_now", [])), n, cn.get("as_of"))
    return {"baskets": len(cn.get("baskets", [])), "entry_now": cn.get("entry_now", []),
            "pages": n, "as_of": cn.get("as_of")}


def render_china_pages(site: Path, env=None, generated_utc: str | None = None) -> int:
    """Render the China board (subsectors_china.html) + one detail page per THS concept FROM the
    committed China JSON. Render-lane safe (no recompute). Reuses the bilingual detail template."""
    env = env or _env()
    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        cn = json.loads((site / CN_BOARD_JSON).read_text())
    except Exception as e:  # noqa: BLE001
        log.error("china confluence board JSON missing (%s) — run main_china() first", e)
        return 0
    write_page(site / "subsectors_china.html",
        env.get_template("subsectors_china.html.j2").render(generated_utc=generated_utc))

    out_dir = site / CN_DETAIL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("subsector_detail.html.j2")
    n = 0
    live: set[str] = set()
    for g in cn.get("baskets", []):
        key = _detail_key(g)
        detail = {
            "group": g, "kind": "concept", "as_of": g.get("as_of"),
            "ohlc_dir": CN_OHLC_DIR, "sig_dir": CN_SIG_DIR,
            "back": "../subsectors_china.html",
            "stock_base": "../china_lookup.html#",
            "generated_utc": generated_utc,
        }
        html = tmpl.render(detail_json=json.dumps(_clean(detail), separators=(",", ":"), allow_nan=False),
                           group_name=g.get("label_zh") or g.get("label", key),
                           chart_key=g.get("chart_key"), has_signals=bool(g.get("has_signals")),
                           back_href="../subsectors_china.html", generated_utc=generated_utc)
        write_page(out_dir / f"{key}.html", html)
        live.add(key)
        n += 1
    if n:  # never prune on an empty/failed render
        pruned = _prune_orphan_details(out_dir, live)
        if pruned:
            log.info("subsector_confluence[CHINA]: pruned %d orphaned detail page(s)", pruned)
    log.info("subsector_confluence[CHINA]: rendered subsectors_china.html + %d detail pages", n)
    return n


def build_china(site: Path, generated_utc: str | None = None) -> int:
    """build_site entrypoint (render lane) for the China desk."""
    return render_china_pages(site, _env(), generated_utc)


# ------------------------------------- US index desks (Nasdaq-100 / Russell-2000) ----
# Generic namespaced desk: same data/render split as the US + China desks, parameterised by a
# namespace so Nasdaq and Russell share one code path. The board UI is the SHARED subsectors.html
# (extra tabs fetch these JSONs client-side); here we only compute the JSON, emit the per-group
# chart/signal files into namespaced dirs, and render the per-group DETAIL pages.

INDEX_DESKS = {
    "nasdaq": {"compute": sc.compute_nasdaq_confluence, "label": "Nasdaq-100",
               "label_zh": "纳斯达克100", "kind_en": "Nasdaq-100 sub-industry",
               "kind_zh": "纳斯达克100子行业"},
    "russell": {"compute": sc.compute_russell_confluence, "label": "Russell-2000",
                "label_zh": "罗素2000", "kind_en": "Russell-2000 sub-industry",
                "kind_zh": "罗素2000子行业"},
}


def _index_dirs(ns: str) -> dict:
    return {"ohlc": f"subsectorohlc_{ns}", "sig": f"subsector_signals_{ns}",
            "detail": f"subsector_{ns}", "board": f"marketdata/subsector_confluence_{ns}.json"}


def main_index(ns: str) -> dict:
    """Nightly (cl_baskets band): compute the index desk + write its namespaced JSON / chart /
    signal files + render its detail pages. Mirrors main_china() for the Nasdaq/Russell desks."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    site = config.ROOT / config.load()["storage"]["site_dir"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    d = _index_dirs(ns)
    out = INDEX_DESKS[ns]["compute"]()
    for g in out.get("subsectors", []) + out.get("sectors", []):
        _emit_group_files(site, g, ohlc_dir=d["ohlc"], sig_dir=d["sig"])
    out["generated_utc"] = generated
    _write_json(site / d["board"], out)
    n = render_index_pages(ns, site, _env(), generated)
    log.info("subsector_confluence[%s]: %d subsectors (%d entry-now), %d amalgamations, %d pages — as_of %s",
             ns.upper(), len(out.get("subsectors", [])), len(out.get("entry_now", [])),
             len(out.get("sectors", [])), n, out.get("as_of"))
    return {"subsectors": len(out.get("subsectors", [])), "entry_now": out.get("entry_now", []),
            "amalgamations": len(out.get("sectors", [])), "pages": n, "as_of": out.get("as_of")}


def render_index_pages(ns: str, site: Path, env=None, generated_utc: str | None = None) -> int:
    """Render one detail page per group (subsector + amalgamation) FROM the committed namespaced
    JSON. Render-lane safe (no recompute). Reuses the bilingual detail template. The board page
    itself is the shared subsectors.html (rendered by render_pages)."""
    env = env or _env()
    generated_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    d = _index_dirs(ns)
    meta = INDEX_DESKS[ns]
    try:
        out = json.loads((site / d["board"]).read_text())
    except Exception as e:  # noqa: BLE001
        log.error("%s confluence board JSON missing (%s) — run main_index('%s') first", ns, e, ns)
        return 0
    out_dir = site / d["detail"]
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("subsector_detail.html.j2")
    n = 0
    live: set[str] = set()
    for g in out.get("subsectors", []) + out.get("sectors", []):
        key = _detail_key(g)
        is_amalg = g.get("kind") == "sector"
        klab_en = (f"{meta['label']} complex" if is_amalg else meta["kind_en"])
        klab_zh = ((meta['label_zh'] + "综合体") if is_amalg else meta["kind_zh"])
        detail = {
            "group": g, "kind": g.get("kind", "subsector"),
            "kind_label_en": klab_en, "kind_label_zh": klab_zh,
            "as_of": g.get("as_of"), "ohlc_dir": d["ohlc"], "sig_dir": d["sig"],
            "back": "../subsectors.html", "stock_base": "../stock.html#",
            "generated_utc": generated_utc,
        }
        html = tmpl.render(detail_json=json.dumps(_clean(detail), separators=(",", ":"), allow_nan=False),
                           group_name=g.get("label", key), chart_key=g.get("chart_key"),
                           has_signals=bool(g.get("has_signals")), back_href="../subsectors.html",
                           generated_utc=generated_utc)
        write_page(out_dir / f"{key}.html", html)
        live.add(key)
        n += 1
    if n:  # never prune on an empty/failed render
        pruned = _prune_orphan_details(out_dir, live)
        if pruned:
            log.info("subsector_confluence[%s]: pruned %d orphaned detail page(s)", ns.upper(), pruned)
    log.info("subsector_confluence[%s]: rendered %d detail pages", ns.upper(), n)
    return n


def build_index(ns: str, site: Path, generated_utc: str | None = None) -> int:
    """build_site entrypoint (render lane) for an index desk."""
    return render_index_pages(ns, site, _env(), generated_utc)


def build_nasdaq(site: Path, generated_utc: str | None = None) -> int:
    return build_index("nasdaq", site, generated_utc)


def build_russell(site: Path, generated_utc: str | None = None) -> int:
    return build_index("russell", site, generated_utc)


def main_nasdaq() -> dict:
    return main_index("nasdaq")


def main_russell() -> dict:
    return main_index("russell")


if __name__ == "__main__":
    import sys
    if "--china" in sys.argv:
        main_china()
    elif "--nasdaq" in sys.argv:
        main_index("nasdaq")
    elif "--russell" in sys.argv:
        main_index("russell")
    else:
        main()
