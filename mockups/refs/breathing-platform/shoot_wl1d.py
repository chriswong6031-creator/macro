"""W-L1d — provisional CARD renderer: real-page crop shooter + measurement rig.

    python3 mockups/refs/breathing-platform/shoot_wl1d.py [--out DIR]

Unlike ``shoot_wl1.py``, which shoots the hand-built mockups in this directory, this one
shoots THE REAL PAGE: ``dashboard.html.j2`` rendered through the house test harness, served
over http next to a fixture ``live/prophet_live.json``, with the client renderer doing the
actual mount. Spec gate §0-1 asks for crops "taken from the real page (not the mockup)" and
for W-L1d the whole subject under test is client-side, so a mockup would prove nothing.

Shoots, per (lang × theme × width):
  · the mounted provisional board — stamp, note and cards in one frame
  · the DEGRADED board — every card missing name / sector / spark

and measures, without eyeballing:
  · the §0-4 height contract: .nbgrid's offset from the panel top, nightly vs. provisional
  · composited contrast for the two words this surface introduces (Room value, verb chip)
  · that the stage filter, the view toggle and the nightly grid are actually gone
  · that nothing on the glance tier says a banned word, in either language
"""
from __future__ import annotations

import argparse
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT))

ASSETS = [
    "theme.css", "theme.js", "dashboard-icons.css", "dashboard-icons.js",
    "tier_preview.css", "tier_preview.js", "chart_i18n.js", "charts.js",
    "release_publications_live.js", "risk_state_live.js", "stocktable.js",
    "tablesort.js", "timemachine.js", "live.js",
]

BANNED = [
    "W-L1", "close-pass", "close pass", "armed", "reconciler", "admission",
    "gauntlet", "prereg", "provisional", "display-tier", "expected-null",
    "falsifier", "falsified", "refuted", "invalidated", "证伪",
]

SPARK = ('<svg viewBox="0 0 240 74" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
         '<path d="M0 58 L30 54 L60 60 L90 44 L120 48 L150 33 L180 37 L210 22 L240 16" '
         'fill="none" stroke="#888" stroke-width="1.6"/></svg>')

NAMES = [
    ("Apple Inc.", "苹果公司", "Technology", "科技"),
    ("Vertex Pharmaceuticals", "福泰制药", "Health Care", "医疗保健"),
    ("Freeport-McMoRan", "自由港麦克莫兰", "Materials", "原材料"),
    ("Cheniere Energy", "切尼尔能源", "Energy", "能源"),
    ("Builders FirstSource", "建筑第一资源", "Industrials", "工业"),
    ("Arista Networks", "阿里斯塔网络", "Technology", "科技"),
    ("Cencora", "森科拉", "Health Care", "医疗保健"),
    ("Targa Resources", "塔加资源", "Energy", "能源"),
    ("Steel Dynamics", "钢铁动力", "Materials", "原材料"),
    ("Interactive Brokers", "盈透证券", "Financials", "金融"),
    ("Axon Enterprise", "阿克森企业", "Industrials", "工业"),
    ("Royal Caribbean", "皇家加勒比", "Consumer Discretionary", "非必需消费"),
]
TICKERS = ["AAPL", "VRTX", "FCX", "LNG", "BLDR", "ANET", "COR", "TRGP",
           "STLD", "IBKR", "AXON", "RCL"]
# runway spread chosen to exercise all three bands and both verbs
RUNWAY = [0.91, 0.83, 0.78, 0.71, 0.64, 0.55, 0.52, 0.44, 0.36, 0.22, 0.08, 0.00]
PRICES = ["$228.14", "$471.02", "$44.87", "$213.60", "$168.29", "$402.55",
          "$247.31", "$176.44", "$131.08", "$228.90", "$742.16", "$258.73"]


def _cards(as_of: str, *, degraded: bool = False) -> list:
    out = []
    for i, tk in enumerate(TICKERS):
        en, zh, sec, sec_zh = NAMES[i]
        c = {"tk": tk, "sym": tk, "mkt": "us", "href": f"stocks/{tk}.html",
             "date": as_of, "price_txt": PRICES[i],
             "signal": round(0.95 - i * 0.03, 3), "runway": RUNWAY[i]}
        if degraded:
            # nothing optional survives: no name, no sector, no spark
            c.update({"name": None, "name_zh": None, "sec": None, "sec_zh": None,
                      "spark": None})
        else:
            # THE REAL EVENING SHAPE (producer ruling 2026-08-10): `spark` is null on
            # every card — sparks are 86% of the payload on a 120s poll for a key that
            # changes once a day, and the evening spark would render bandless anyway
            # because the band derives from the omitted `entry` leg. `name_zh` is null
            # too, so ZH falls back to the English company name — the NIGHTLY board
            # passes no name_zh for US cards either, and a card whose company name
            # changes language overnight is worse than one that never translates it.
            c.update({"name": en, "name_zh": None, "sec": sec, "sec_zh": sec_zh,
                      "spark": None})
        out.append(c)
    return out


def _payload(as_of: str, now_ms: int, *, degraded: bool = False) -> dict:
    import datetime

    def iso(ms):
        return (datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"))

    cards = _cards(as_of, degraded=degraded)
    return {
        "schema": "prophet_live.states/1",
        "board_state": {
            "rel": "ahead", "note": "ahead",
            "generated_at": iso(now_ms - 1800000),
            "valid_until": iso(now_ms + 43200000),
            "board": {"as_of": as_of, "lane": "closepass",
                      "tickers": [c["tk"] for c in cards],
                      "card_complete": True, "cards": cards},
        },
    }


def _render_page(n_rows: int = 9) -> str:
    from tests.test_dashboard_template_render import _base_vm, _board_row, _env
    vm = _base_vm()
    rows = []
    for i in range(n_rows):
        tk = f"NB{i}"
        rows.append(_board_row(ticker=tk, name=f"Nightly Name {i}", stage="live",
                               lane="bottoming", score_rank=i + 1, display_rank=i + 1,
                               prophet={"version": "us_prophet_v1", "score": 78 - i}))
    vm["us_standouts"] = {"buy": rows, "eligible": len(rows), "as_of": "2026-08-09"}
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _stage(tmp: Path, page: str, payload: dict) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "index.html").write_text(page)
    for a in ASSETS:
        src = ROOT / "templates" / a
        if src.exists():
            shutil.copyfile(src, tmp / a)
    (tmp / "live").mkdir(exist_ok=True)
    (tmp / "live" / "prophet_live.json").write_text(json.dumps(payload))
    # THE ENTITLEMENT GATE IS STUBBED FOR THE CROPS, and that is a statement about the
    # crops, not about the gate. tier_preview.js resolves a signed-out visitor to "anon"
    # (cap 1) and cannot reach /api/me from a static harness, so shooting with it live
    # reviews the paywall's blur teaser instead of the board. It was verified separately
    # to still gate these cards: it runs a MutationObserver over document.body, so the
    # client-injected evening cards are capped exactly like the server-rendered nightly
    # ones — evidence crop wl1d_entitlement_gate_en_dark_1280.png.
    (tmp / "tier_preview.js").write_text(
        "/* stubbed for design crops — see _stage() in shoot_wl1d.py */\n"
        "window.dispatchEvent(new CustomEvent('mmx-access-tier',"
        "{detail:{tier:'pro',cap:Infinity}}));\n")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D102
        pass


def _serve(directory: Path):
    handler = lambda *a, **k: _Quiet(*a, directory=str(directory), **k)  # noqa: E731
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


_PROBE = r"""
() => {
  const panel = document.getElementById('us-standouts');
  const grid  = panel.querySelector('.nbgrid:not([hidden])');
  const cards = grid ? grid.querySelectorAll('.pvcard[data-ticker]') : [];
  const stamp = panel.querySelector('.pbs[data-bs="ahead"]');
  const night = panel.querySelector('.nbgrid[data-showmore-rows]:not([data-provboard])');
  const cs = el => el ? getComputedStyle(el) : null;
  const pick = (sel) => { const e = grid && grid.querySelector(sel); return e ? {
      color: cs(e).color, bg: cs(e).backgroundColor, text: e.innerText.trim() } : null; };
  return {
    mounted: !!(grid && grid.getAttribute('data-provboard')),
    n_cards: cards.length,
    tickers: [].map.call(cards, c => c.getAttribute('data-ticker')).join('|'),
    stamp_shown: !!(stamp && !stamp.hidden),
    stamp_text: stamp ? stamp.innerText.trim() : null,
    night_hidden: !!(night && night.hidden),
    filter_hidden: (() => { const f = document.getElementById('us-stage-filter');
                            return !f || f.hidden; })(),
    toggle_hidden: (() => { const v = document.getElementById('us-st-view-toggle');
                            return !v || v.hidden; })(),
    sub_hidden: (() => { const v = document.getElementById('us-board-sub');
                         return !v || v.hidden; })(),
    fn_hidden: (() => { const v = panel.querySelector('.pb-fn'); return !v || v.hidden; })(),
    grid_offset: grid ? Math.round((grid.getBoundingClientRect().top -
                        panel.getBoundingClientRect().top) * 100) / 100 : null,
    card_h: cards.length ? Math.round(cards[0].getBoundingClientRect().height * 100) / 100 : null,
    verb_chip: pick('.pvcard .pv-chip'),
    room_val:  pick('.pvcard .pv-edn'),
    room_lab:  pick('.pvcard .pv-edl'),
    has_stage_rail: !!(grid && grid.querySelector('.pvcard .pv-stp')),
    has_marks:      !!(grid && grid.querySelector('.pvcard .pv-mk')),
    has_live_slot:  !!(grid && grid.querySelector('.pvcard .pv-live')),
    panel_text: panel.innerText,
    verbs: (() => { const o = {}; [].forEach.call(cards, c => {
              const m = (c.className.match(/pv-(buy|near|wait|hold|avoid)/) || [])[1];
              o[m] = (o[m] || 0) + 1; }); return o; })(),
    rooms: (() => { const o = {}; [].forEach.call(cards, c => {
              const e = c.querySelector('.pv-edn'); if (!e) return;
              const t = e.innerText.trim(); o[t] = (o[t] || 0) + 1; }); return o; })(),
  };
}
"""

_NIGHTLY_PROBE = r"""
() => {
  const panel = document.getElementById('us-standouts');
  const grid  = panel.querySelector('.nbgrid:not([hidden])');
  return { grid_offset: grid ? Math.round((grid.getBoundingClientRect().top -
                          panel.getBoundingClientRect().top) * 100) / 100 : null };
}
"""


_DIAG = r"""
() => {
  const s = (typeof _plvData === 'object' && _plvData) ? _plvData.board_state : null;
  const out = { fetched: !!s };
  try { out.cards = s ? (typeof _pvcCards === 'function' ? !!_pvcCards(s.board) : 'nofn') : null; }
  catch (e) { out.cards_err = String(e); }
  try { out.wanted = s ? !!_pvcWanted(s, Date.now(), '') : null; }
  catch (e) { out.wanted_err = String(e); }
  try { out.qualify = s ? _bsQualify(s, _pvcKey(_pvcCards(s.board) || []), Date.now()) : null; }
  catch (e) { out.qualify_err = String(e); }
  out.dom = typeof _bsDomTickers === 'function' ? _bsDomTickers() : 'nofn';
  out.refused = typeof _pvcRefused !== 'undefined' ? _pvcRefused : 'undef';
  return out;
}
"""


def key_hint(degraded, lang, theme, width):
    return f"{'degraded' if degraded else 'full'}_{lang}_{theme}_{width}"


def _lum(c):
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _rgb(s):
    """Computed colour -> [r,g,b,a]. Chromium serialises color-mix() as
    ``color(srgb 0.57 0.72 0.90)`` (0..1 floats) and plain values as ``rgb(...)``;
    reading the first naively crushes every mixed colour to ~0 luminance and makes
    every pair measure a phantom 1.00:1 (shoot_wl1.py's note, same trap)."""
    s = (s or "").strip()
    if s.startswith("color(srgb"):
        parts = s[s.index("srgb") + 4:].rstrip(")").replace("/", " ").split()
        v = [float(x) for x in parts[:3]]
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return [v[0] * 255, v[1] * 255, v[2] * 255, a]
    nums = [float(x) for x in
            s.replace("rgba(", "").replace("rgb(", "").rstrip(")")
             .replace("/", " ").replace(",", " ").split()]
    return (nums + [1.0])[:4] if len(nums) >= 3 else [0, 0, 0, 1]


def _over(fg, bg):
    a = fg[3]
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)]


def _ratio(ink, fill, page):
    i, f = _rgb(ink), _rgb(fill)
    base = _over(f, _rgb(page))
    l1, l2 = _lum(_over(i, base)), _lum(base)
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


_RESTORE_PROBE = r"""
() => {
  const panel = document.getElementById('us-standouts');
  const night = panel.querySelector('.nbgrid[data-showmore-rows]:not([data-provboard])');
  const prov  = panel.querySelector('.nbgrid[data-provboard]');
  const bars  = panel.querySelectorAll('.sm-bar');
  const stamp = panel.querySelector('.pbs[data-bs="ahead"]');
  const vis   = el => !!(el && !el.hidden && getComputedStyle(el).display !== 'none');
  return {
    prov_gone:      !prov,
    night_back:     vis(night),
    stamp_gone:     !(stamp && !stamp.hidden),
    filter_back:    vis(document.getElementById('us-stage-filter')),
    toggle_back:    vis(document.getElementById('us-st-view-toggle')),
    sub_back:       vis(document.getElementById('us-board-sub')),
    fn_back:        vis(panel.querySelector('.pb-fn')),
    /* exactly one show-more bar survives — the nightly board's. Its VISIBILITY is not
       asserted: show-more hides its own bar when the grid fits in one page, which is the
       correct state for a 9-card nightly board and not an orphan. */
    one_bar:        bars.length === 1,
    n_bars:         bars.length,
    track_toggle:   (() => { const t = document.getElementById('board-track-toggle');
                             return !t || vis(t); })(),
    stagef:         panel.getAttribute('data-stagef'),
    night_tickers:  [].map.call(night ? night.querySelectorAll('.pvcard[data-ticker]') : [],
                                c => c.getAttribute('data-ticker')).join('|'),
  };
}
"""


def _lifecycle(tmp: Path, port: int, page_html: str, now_ms: int, report: dict) -> None:
    """Mount, then invalidate — and prove the page comes back the way it started.

    The mount is only half the contract: spec §10.5 says the nightly board is replaced as
    a unit and RESTORED, so a payload that stops qualifying must not leave a stale flip
    behind. Every control the mount put away is asserted back, individually, because a
    teardown that restores the grid but forgets the stage filter is exactly the kind of
    half-swap that ships unnoticed.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1280, "height": 1200})
        ctx.add_cookies([{"name": "sb-shoot-auth-token", "value": "x",
                          "domain": "127.0.0.1", "path": "/"}])
        pg = ctx.new_page()
        pg.add_init_script("try{localStorage.setItem('theme','dark');"
                           "localStorage.setItem('lang','');}catch(e){}")
        pg.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
        pg.wait_for_function(
            "() => !!document.querySelector('#us-standouts .nbgrid[data-provboard]')",
            timeout=15000)
        pg.wait_for_timeout(300)
        before = pg.evaluate(_PROBE)
        nightly_before = pg.evaluate(
            "() => [].map.call(document.querySelectorAll("
            "'#us-standouts .nbgrid[data-showmore-rows]:not([data-provboard])"
            " .pvcard[data-ticker]'), c => c.getAttribute('data-ticker')).join('|')")

        # The payload expires under a reader who is already looking at the board, and the
        # teardown is then driven by the component's OWN 120s poll — not by reaching into
        # its internals. That is deliberate: the page's script does not expose _plvFetch
        # globally, and a harness that pokes a private function proves the harness works,
        # not the surface. Costs one two-minute wait, once.
        stale = _payload("2026-08-10", now_ms)
        stale["board_state"]["valid_until"] = stale["board_state"]["generated_at"]
        (tmp / "live" / "prophet_live.json").write_text(json.dumps(stale))
        pg.wait_for_function(
            "() => !document.querySelector('#us-standouts .nbgrid[data-provboard]')",
            timeout=180000)
        pg.wait_for_timeout(300)
        after = pg.evaluate(_RESTORE_PROBE)
        ctx.close()
        br.close()

    report["lifecycle"] = {"mounted_first": before["mounted"],
                           "cards_first": before["n_cards"], "restored": after}
    if not before["mounted"]:
        report["checks"].append("lifecycle: never mounted")
    for flag in ("prov_gone", "night_back", "stamp_gone", "filter_back", "toggle_back",
                 "sub_back", "fn_back", "one_bar", "track_toggle"):
        if not after[flag]:
            report["checks"].append(f"lifecycle: {flag} FALSE after teardown")
    if after["night_tickers"] != nightly_before:
        report["checks"].append("lifecycle: the nightly grid did not come back intact")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "wl1d_shots"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    page_html = _render_page()
    # the browser reads its own clock, so the fixture's freshness window has to be
    # anchored to real time or `_bsQualify` correctly refuses an expired payload
    import time
    now_ms = int(time.time() * 1000)
    tmp = HERE / "_wl1d_stage"
    if tmp.exists():
        shutil.rmtree(tmp)

    report = {"contrast": {}, "heights": {}, "checks": [], "distribution": {}}
    for degraded in (False, True):
        _stage(tmp, page_html, _payload("2026-08-10", now_ms, degraded=degraded))
        httpd, port = _serve(tmp)
        try:
            with sync_playwright() as p:
                br = p.chromium.launch()
                for lang in ("en", "zh"):
                    for theme in ("dark", "light"):
                        for width in (390, 680, 1280):
                            ctx = br.new_context(viewport={"width": width, "height": 1400},
                                                 device_scale_factor=2)
                            # tier_preview.js short-circuits to "anon" unless a supabase
                            # auth cookie is present; without it the crops would review
                            # the paywall's blur teaser instead of the board.
                            ctx.add_cookies([{"name": "sb-shoot-auth-token", "value": "x",
                                              "domain": "127.0.0.1", "path": "/"}])
                            pg = ctx.new_page()
                            errs = []
                            pg.on("pageerror", lambda e: errs.append(str(e)))
                            pg.on("console", lambda m: errs.append(m.text)
                                  if m.type == "error" else None)
                            pg.add_init_script(
                                f"try{{localStorage.setItem('theme','{theme}');"
                                f"localStorage.setItem('lang','{lang if lang=='zh' else ''}');"
                                # the board is entitlement-gated; a free tier blurs all but
                                # the first card, which would review the paywall, not the design
                                "localStorage.setItem('mm.me.hint',"
                                "JSON.stringify({tier:'pro'}));"
                                "sessionStorage.setItem('mm.me',JSON.stringify("
                                "{me:{tier:'pro',plan:'pro'},t:Date.now()}));"
                                "}catch(e){}")
                            pg.goto(f"http://127.0.0.1:{port}/index.html",
                                    wait_until="load")
                            pg.evaluate("() => { document.documentElement.setAttribute("
                                        f"'data-theme','{theme}');"
                                        "document.documentElement.setAttribute("
                                        f"'data-lang','{lang if lang=='zh' else ''}'); }}")
                            night = pg.evaluate(_NIGHTLY_PROBE)
                            try:
                                pg.wait_for_function(
                                    "() => { const g = document.querySelector("
                                    "'#us-standouts .nbgrid[data-provboard]'); return !!g; }",
                                    timeout=15000)
                            except Exception:
                                print("MOUNT TIMEOUT", key_hint(degraded, lang, theme, width))
                                print("  page errors:", errs[:6])
                                print("  diag:", json.dumps(pg.evaluate(_DIAG), ensure_ascii=False))
                                raise
                            pg.wait_for_timeout(350)
                            got = pg.evaluate(_PROBE)
                            key = f"{'degraded' if degraded else 'full'}_{lang}_{theme}_{width}"
                            report["heights"][key] = {
                                "nightly_grid_offset": night["grid_offset"],
                                "prov_grid_offset": got["grid_offset"],
                                "card_h": got["card_h"]}
                            report["distribution"][key] = {"verbs": got["verbs"],
                                                           "rooms": got["rooms"]}
                            for name, probe in (("verb_chip", got["verb_chip"]),
                                                ("room_val", got["room_val"]),
                                                ("room_lab", got["room_lab"])):
                                if probe:
                                    pagebg = pg.evaluate(
                                        "() => getComputedStyle(document.body).backgroundColor")
                                    report["contrast"][f"{key}:{name}"] = {
                                        "text": probe["text"],
                                        "ratio": _ratio(probe["color"], probe["bg"], pagebg)}
                            for flag in ("mounted", "stamp_shown", "night_hidden",
                                         "filter_hidden", "toggle_hidden",
                                         "sub_hidden", "fn_hidden"):
                                if not got[flag]:
                                    report["checks"].append(f"{key}: {flag} FALSE")
                            for flag in ("has_stage_rail", "has_marks", "has_live_slot"):
                                if got[flag]:
                                    report["checks"].append(f"{key}: {flag} TRUE (should be absent)")
                            if got["n_cards"] != len(TICKERS):
                                report["checks"].append(
                                    f"{key}: {got['n_cards']} cards, expected {len(TICKERS)}")
                            if got["tickers"] != "|".join(TICKERS):
                                report["checks"].append(f"{key}: ticker order mismatch")
                            low = got["panel_text"].lower()
                            for w in BANNED:
                                if w.lower() in low:
                                    report["checks"].append(f"{key}: BANNED WORD {w!r}")
                            if width in (390, 1280):
                                panel = pg.locator("#us-standouts")
                                tag = "degraded" if degraded else "board"
                                panel.screenshot(
                                    path=str(out / f"wl1d_{tag}_{lang}_{theme}_{width}.png"))
                            ctx.close()
                br.close()
        finally:
            httpd.shutdown()

    # mount -> invalidate -> restore, against the real DOM
    _stage(tmp, page_html, _payload("2026-08-10", now_ms))
    httpd, port = _serve(tmp)
    try:
        _lifecycle(tmp, port, page_html, now_ms, report)
    finally:
        httpd.shutdown()

    (out / "wl1d_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\nCHECKS:", "ALL PASS" if not report["checks"] else f"{len(report['checks'])} FAILURES")
    return 1 if report["checks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
