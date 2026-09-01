#!/usr/bin/env python3
"""Evidence capture for the Prophet candidate "Added date" chip (.pv-added).

Drives the REAL built pages in site/ (never a specimen) over a local static
server, exercising the site's own theme/language mechanism (the `theme` /
`lang` localStorage keys that templates/theme.js reads before paint), and
writes the dark/light x EN/ZH x 1440/390 matrix as PNGs next to this file.

Usage:  <venv-with-playwright>/bin/python capture.py <page> [<page> ...]
        page = a bare site/ filename stem, e.g. hk_stocks
"""
from __future__ import annotations

import http.server
import json
import functools
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SITE = REPO / "site"

VIEWPORTS = {"1440": (1440, 900), "390": (390, 844)}
THEMES = ("dark", "light")
LANGS = ("en", "zh")

# Collect the geometry of the board region and of the specific cards this
# commission requires framed, straight out of the live DOM.
PROBE = """
() => {
  // Visible cards only: this board collapses its tail behind a "See more"
  // control, and a display:none card measures 0x0 — clipping to one yields a
  // blank tile that would read as evidence but prove nothing.
  const cards = [...document.querySelectorAll('a.pvcard')]
    .filter(c => c.querySelector('.pv-zn') && c.offsetParent !== null
                 && c.getBoundingClientRect().height > 1);
  const rect = e => { const r = e.getBoundingClientRect();
    return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height}; };
  const info = cards.map((c, i) => {
    const chip = c.querySelector('.pv-added');
    const zn = c.querySelector('.pv-zn');
    return {
      i,
      ticker: c.getAttribute('data-ticker') || '',
      added: chip ? chip.getAttribute('data-added') : null,
      chipText: chip ? chip.innerText.trim() : null,
      znText: zn ? zn.innerText.replace(/\\s+/g, ' ').trim() : '',
      znLen: zn ? zn.innerText.replace(/\\s+/g, ' ').trim().length : 0,
      rect: rect(c),
      znRect: zn ? rect(zn) : null,
      // How close the quiet chip comes to the actionable zone value, and
      // whether the value is already ellipsizing. `.pv-znr/.pv-znm` carry
      // min-width:0 + text-overflow:ellipsis while `.pv-added` is flex:none,
      // so under pressure the PRICE yields before the metadata does.
      gap: (() => { const v = c.querySelector('.pv-znr,.pv-znm');
        if (!v || !chip) return null;
        return Math.round(chip.getBoundingClientRect().left
                          - v.getBoundingClientRect().right); })(),
      valueClipped: (() => { const v = c.querySelector('.pv-znr,.pv-znm');
        return v ? v.scrollWidth > v.clientWidth + 1 : null; })(),
      znOverflow: zn ? zn.scrollWidth > zn.clientWidth + 1 : null,
    };
  });
  // Measured, not assumed: the chip's painted ink and the surface it is
  // painted on, in whichever theme is live.
  let ink = null;
  { const c0 = cards.find(c => c.querySelector('.pv-added'));
    if (c0) { const chip = c0.querySelector('.pv-added'), zn = c0.querySelector('.pv-zn');
      const val = c0.querySelector('.pv-znr,.pv-znm');
      ink = {chip: getComputedStyle(chip).color,
             chipSize: getComputedStyle(chip).fontSize,
             chipWeight: getComputedStyle(chip).fontWeight,
             row: getComputedStyle(zn).backgroundColor,
             value: val ? getComputedStyle(val).color : null,
             valueWeight: val ? getComputedStyle(val).fontWeight : null,
             panel: getComputedStyle(c0).backgroundColor}; } }
  // The board's OWN vintage stamp: of every "Data through" on the page, the one
  // immediately ABOVE the first candidate card — so a stamp belonging to some
  // other panel can never be framed as if it were this board's. VISIBILITY is
  // recorded, not assumed: HK/CA hand the cards to a client shell and hide the
  // legacy #standouts panel, so a stamp can exist in the HTML and be unseeable.
  const vis = e => e && e.offsetParent !== null && e.getBoundingClientRect().height > 1;
  let hdr = null, hdrText = null;
  const stamps = [];
  for (const p of document.querySelectorAll('p')) {
    const t = p.innerText || '';
    if (!(t.includes('Data through') || t.includes('数据截至'))) continue;
    stamps.push({t: t.replace(/\\s+/g, ' ').trim().slice(0, 60), visible: vis(p)});
    if (!vis(p) || !cards[0]) continue;
    const r = rect(p);
    if (r.y < rect(cards[0]).y && (!hdr || r.y > hdr.y)) {
      hdr = r; hdrText = t.replace(/\\s+/g, ' ').trim();
    }
  }
  // What the user actually meets above the first card: the shell's own board
  // header, whatever owns it.
  let shell = null;
  if (cards[0]) {
    const sec = cards[0].closest('section, .panel, main') || null;
    if (sec) {
      const sr = rect(sec), cr = rect(cards[0]);
      shell = {x: sr.x, y: sr.y, w: sr.w, h: Math.max(24, cr.y - sr.y)};
    }
  }
  const grid = document.querySelector('.nbgrid') || (cards[0] && cards[0].parentElement);
  return {cards: info, header: hdr, headerText: hdrText, stamps, shell, ink,
          standoutsDisplay: (() => { const s = document.querySelector('#standouts');
            return s ? getComputedStyle(s).display : '(absent)'; })(),
          cardsTotal: document.querySelectorAll('a.pvcard').length,
          grid: grid ? rect(grid) : null,
          docW: document.documentElement.scrollWidth,
          winW: window.innerWidth};
}
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # keep the capture log readable
        pass


def serve(port_holder):
    handler = functools.partial(QuietHandler, directory=str(SITE))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port_holder.append(httpd.server_address[1])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def clip(box, pad=10, page_w=None, max_h=None):
    x = max(0, box["x"] - pad)
    y = max(0, box["y"] - pad)
    w = box["w"] + pad * 2
    h = box["h"] + pad * 2
    if page_w:
        w = min(w, page_w - x)
    if max_h:
        h = min(h, max_h)
    return {"x": x, "y": y, "width": max(1, w), "height": max(1, h)}


def union(*boxes):
    boxes = [b for b in boxes if b]
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def run(pages):
    holder: list[int] = []
    serve(holder)
    port = holder[0]
    manifest = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_stem in pages:
            for theme in THEMES:
                for lang in LANGS:
                    for vpname, (w, h) in VIEWPORTS.items():
                        ctx = browser.new_context(
                            viewport={"width": w, "height": h},
                            device_scale_factor=2,
                            reduced_motion="reduce",
                        )
                        # The site's own persisted preference keys, read by
                        # templates/theme.js before first paint.
                        ctx.add_init_script(
                            "try{localStorage.setItem('theme',%r);"
                            "localStorage.removeItem('themeAuto');"
                            "localStorage.setItem('lang',%r);}catch(e){}"
                            % (theme, lang)
                        )
                        pg = ctx.new_page()
                        pg.goto(f"http://127.0.0.1:{port}/{page_stem}.html",
                                wait_until="load", timeout=120000)
                        # These pages mount panels client-side after load; a box
                        # measured too early is invalidated by the reflow. Settle
                        # until the document height stops moving.
                        try:
                            pg.wait_for_load_state("networkidle", timeout=45000)
                        except Exception:
                            pass
                        last, stable = -1, 0
                        for _ in range(60):
                            cur = pg.evaluate("()=>document.documentElement.scrollHeight")
                            stable = stable + 1 if cur == last else 0
                            last = cur
                            if stable >= 4:
                                break
                            pg.wait_for_timeout(400)
                        actual = pg.evaluate(
                            "()=>[document.documentElement.getAttribute('data-theme'),"
                            "document.documentElement.getAttribute('data-lang')]")
                        assert actual[0] == theme and (actual[1] or 'en') == lang, \
                            f"theme/lang not applied: {actual} != {theme}/{lang}"
                        pg.evaluate("()=>{const c=document.querySelector('a.pvcard');"
                                    "if(c)c.scrollIntoView({block:'start'});}")
                        pg.wait_for_timeout(700)
                        d = pg.evaluate(PROBE)
                        basekey = f"{page_stem}_{theme}_{lang}_{vpname}"
                        key = basekey
                        out = {"cards": len(d["cards"]),
                               "chips": sum(1 for c in d["cards"] if c["added"]),
                               "docW": d["docW"], "winW": d["winW"],
                               "cardsTotal": d.get("cardsTotal"),
                               "headerVisibleText": d.get("headerText"),
                               "stampsOnPage": d.get("stamps"),
                               "standoutsDisplay": d.get("standoutsDisplay"),
                               "shots": []}

                        def shot(name, idxs, part="card", **kw):
                            """Re-measure at capture time, then clip.

                            `idxs` are indices into the probed card list (or the
                            literal string 'header'); geometry is re-read from the
                            live DOM immediately before the screenshot so a late
                            reflow cannot desynchronise the clip from the content.
                            """
                            fresh = pg.evaluate(PROBE)
                            boxes = []
                            for ix in idxs:
                                if ix in ("header", "shell"):
                                    if fresh[ix]:
                                        boxes.append(fresh[ix])
                                else:
                                    c = fresh["cards"][ix]
                                    boxes.append(c["znRect"] if part == "zone" else c["rect"])
                            if not boxes:
                                return
                            f = HERE / f"{key}_{name}.png"
                            # full_page so the clip is in DOCUMENT coordinates —
                            # a viewport-relative clip silently frames the wrong
                            # region on a long page.
                            pg.screenshot(path=str(f), full_page=True,
                                          clip=clip(union(*boxes), page_w=fresh["docW"], **kw))
                            out["shots"].append(f.name)

                        if not d["cards"]:
                            manifest[basekey] = out
                            ctx.close()
                            continue
                        n = 3 if vpname == "1440" else 2
                        dated = [c for c in d["cards"] if c["added"]]
                        nulls = [c for c in d["cards"] if not c["added"]]

                        # 1. BOARD — everything the user meets above the first card
                        #    (the shell's own board header, plus this PR's
                        #    "Data through" stamp WHEN it is actually visible)
                        #    through the first cards.
                        shot("board", ["shell"] + (["header"] if d["header"] else [])
                             + [c["i"] for c in d["cards"][:n]], max_h=2600)

                        # 3. LONGEST — the widest ticker/zone case, whole card.
                        widest = max(d["cards"], key=lambda c: c["znLen"])
                        shot("card_longest", [widest["i"]], pad=8)

                        # The default view is Top Picks — every name there has
                        # earned a date. The null (no-chip) candidates live in the
                        # board's own "All candidates" view, so open it the way a
                        # user does rather than inventing a specimen.
                        if len(d["cards"]) < d["cardsTotal"]:
                            pg.evaluate("""()=>{
                              const re=/^(all candidates|all names|全部候选|所有候选|全部|see more|show all|更多)/i;
                              for(const el of document.querySelectorAll('button,a,[role=tab]')){
                                const t=(el.innerText||'').trim();
                                if(re.test(t) && el.offsetParent!==null){ el.click(); return t; }
                              }
                              return null;}""")
                            pg.wait_for_timeout(1500)
                            d2 = pg.evaluate(PROBE)
                            if len(d2["cards"]) > len(d["cards"]):
                                out["expandedCards"] = len(d2["cards"])
                                out["expandedChips"] = sum(1 for c in d2["cards"] if c["added"])
                                d = d2
                                dated = [c for c in d["cards"] if c["added"]]
                                nulls = [c for c in d["cards"] if not c["added"]]
                                key = key + "_all"

                        # 2. ZONE — tight strip over the zone rows: an older
                        #    continuing candidate beside a null (no-chip) one.
                        if dated and nulls:
                            oldest = min(dated, key=lambda c: c["added"])
                            pair = union(oldest["znRect"], nulls[0]["znRect"])
                            if pair["h"] <= 760:
                                # side by side in the grid — one strip proves both
                                shot("zone_dated_vs_null", [oldest["i"], nulls[0]["i"]],
                                     part="zone", pad=14)
                            else:
                                # stacked (mobile) — one strip each, same cell
                                shot("zone_dated", [oldest["i"]], part="zone", pad=14)
                                shot("zone_null", [nulls[0]["i"]], part="zone", pad=14)
                        elif dated:
                            oldest = min(dated, key=lambda c: c["added"])
                            widest = max(dated, key=lambda c: c["znLen"])
                            shot("zone_dated", [oldest["i"], widest["i"]],
                                 part="zone", pad=14)
                        elif nulls:
                            # An all-null market (Intl): frame consecutive zone
                            # rows so the absence reads as a pattern, not a
                            # one-card accident. Keep the strip tight — stacked
                            # (mobile) rows are far apart, so take fewer.
                            grp = nulls[:3]
                            while len(grp) > 1 and union(*[c["znRect"] for c in grp])["h"] > 760:
                                grp = grp[:-1]
                            shot("zone_null", [c["i"] for c in grp], part="zone", pad=14)

                        # 4. COLLISION — where the quiet chip and the actionable
                        #    zone price compete for one row. `.pv-added` is
                        #    flex:none and `.pv-znr` is min-width:0 + ellipsis,
                        #    so the PRICE is what yields. Frame a chipped card
                        #    whose price is ellipsizing beside an unchipped one
                        #    whose price is intact — same board, same viewport.
                        clipped = [c for c in d["cards"] if c["added"] and c["valueClipped"]]
                        clean = [c for c in d["cards"] if not c["added"] and not c["valueClipped"]]
                        if clipped:
                            pick = [clipped[0]["i"]]
                            if clean:
                                near = min(clean, key=lambda c: abs(c["i"] - clipped[0]["i"]))
                                pick.append(near["i"])
                            box = union(*[d["cards"][i]["znRect"] for i in pick])
                            if box["h"] > 900:
                                pick = pick[:1]
                            shot("zone_price_clipped_by_chip", pick, part="zone", pad=14)

                        # 5. LONGEST in the full board (widest ticker/zone case).
                        if key.endswith("_all"):
                            widest = max(d["cards"], key=lambda c: c["znLen"])
                            shot("card_longest", [widest["i"]], pad=8)

                        out["ink"] = d.get("ink")
                        gaps = [c["gap"] for c in d["cards"] if c["gap"] is not None]
                        out["minGapPx"] = min(gaps) if gaps else None
                        out["valuesClipped"] = sum(1 for c in d["cards"] if c["valueClipped"])
                        out["rowsOverflowing"] = sum(1 for c in d["cards"] if c["znOverflow"])
                        out["detail"] = [
                            {k: c[k] for k in ("ticker", "added", "chipText", "znText",
                                               "gap", "valueClipped", "znOverflow")}
                            for c in d["cards"]
                        ]
                        manifest[basekey] = out
                        ctx.close()
                        print(key, out["cards"], "cards /", out["chips"], "chips",
                              "| docW", d["docW"], "winW", d["winW"], flush=True)
        browser.close()
    (HERE / "capture_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run(sys.argv[1:])
