#!/usr/bin/env python3
"""Evidence shooter — Added-date chip FOLD (2026-09-02).

Serves the real built site/ tree.
  mode=head  → the CSS as shipped at HEAD (the defect)
  mode=fold  → the CSS as the CURRENT template renders it (proven byte-identical
               to the real `scripts.build_canada` output; see EVIDENCE addendum)
  layout=native   → the page's own grid
  layout=floor246 → grid pinned to the shipped rule's minmax FLOOR
                    (repeat(auto-fill,246px)) — the densest column the live
                    grid rule permits, i.e. the Chairman's crowded case.
"""
from __future__ import annotations
import functools, http.server, json, socketserver, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
ASSET = "3f6de652.css"

SUBS = {
 ".pv-zn{display:flex;align-items:center;gap:5px;":
 ".pv-zn{display:flex;flex-wrap:wrap;align-items:center;gap:2px 5px;",
 ".pv-znm{color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis}":
 ".pv-znm{color:var(--muted);flex:none;max-width:100%;overflow:hidden;text-overflow:ellipsis}",
 ".pv-added{margin-left:auto;color:var(--muted);flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;font-size:9.5px;padding-left:5px}":
 ".pv-added{margin-left:auto;color:var(--muted);flex:0 0 auto;font-size:9.5px;line-height:1.3}",
 ".pv-added{max-width:32%}": "",
}

FLOOR246 = """
.nbgrid:has(> .pvcard),.cards:has(> .pvcard),.rip-grid:has(> .pvcard){
  grid-template-columns:repeat(auto-fill,246px)!important}
"""

PROBE = r"""
() => {
  const lum = (c) => { const m = c.match(/[\d.]+/g).map(Number);
    const f = v => { v/=255; return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
    return 0.2126*f(m[0]) + 0.7152*f(m[1]) + 0.0722*f(m[2]); };
  const ratio = (a,b) => { const [x,y]=[lum(a),lum(b)].sort((p,q)=>q-p); return (x+0.05)/(y+0.05); };
  const out = {vw: innerWidth, docW: document.documentElement.scrollWidth,
               theme: document.documentElement.dataset.theme,
               lang: document.documentElement.dataset.lang, rows: []};
  for (const card of document.querySelectorAll('a.pvcard')) {
    if (card.offsetParent === null) continue;
    const zn = card.querySelector('.pv-zn'); if (!zn) continue;
    const cr = card.getBoundingClientRect(), zr = zn.getBoundingClientRect();
    const csZ = getComputedStyle(zn), csC = getComputedStyle(card);
    const padR = parseFloat(csZ.paddingRight);
    const add = card.querySelector('.pv-added');
    const val = zn.querySelector('.pv-znr') || zn.querySelector('.pv-znm');
    const r = {tk: (card.querySelector('.pv-tk')||{}).textContent,
      cardW:+cr.width.toFixed(1), znW:+zr.width.toFixed(1), znH:+zr.height.toFixed(1),
      rowOverflows: zn.scrollWidth > zn.clientWidth + 1,
      cardBg: csC.backgroundColor, shelfBg: csZ.backgroundColor,
      lumCard:+lum(csC.backgroundColor).toFixed(4), lumShelf:+lum(csZ.backgroundColor).toFixed(4),
      docRect:[Math.round(cr.left+scrollX),Math.round(cr.top+scrollY),Math.round(cr.width),Math.round(cr.height)],
      znRect:[Math.round(zr.left+scrollX),Math.round(zr.top+scrollY),Math.round(zr.width),Math.round(zr.height)]};
    { let n = card, g = false;
      while (n && n !== document.body) { const f = getComputedStyle(n).filter;
        if (f && f !== 'none') { g = true; break; } n = n.parentElement; }
      r.ghosted = g; }
    r.lumStep = +(r.lumShelf - r.lumCard).toFixed(4);
    if (val) { const vr = val.getBoundingClientRect(), cs = getComputedStyle(val);
      r.valTxt = val.textContent.trim(); r.valCls = val.className; r.valW=+vr.width.toFixed(1);
      r.valSelfEllipsized = val.scrollWidth > val.clientWidth + 1;
      r.valClippedByShelf = vr.right > zr.right - padR + 0.5;
      r.valInk = cs.color; r.valWeight = cs.fontWeight;
      r.valRatio = +ratio(cs.color, csZ.backgroundColor).toFixed(2); }
    if (add) { const ar = add.getBoundingClientRect(), cs = getComputedStyle(add);
      r.chipTxt = add.innerText.trim(); r.chipW=+ar.width.toFixed(1);
      r.chipNeeds = add.scrollWidth;
      r.chipTruncated = add.scrollWidth > add.clientWidth + 1;
      const vt = val ? val.getBoundingClientRect().top : zr.top;
      r.chipFolded = Math.abs(ar.top - vt) > 6;
      r.chipInk = cs.color; r.chipSize = cs.fontSize; r.chipWeight = cs.fontWeight;
      r.chipRatio = +ratio(cs.color, csZ.backgroundColor).toFixed(2);
      r.chipClipped = ar.right > zr.right - padR + 0.5 || ar.bottom > zr.bottom + 0.5;
      r.subordination = +(r.valRatio / r.chipRatio).toFixed(2); }
    out.rows.push(r);
  }
  return out;
}
"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    class Q(socketserver.TCPServer):
        allow_reuse_address = True
        def handle_error(self, *a): pass
    s = Q(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    # spec: board:mode:layout:viewports  (viewports comma-joined)
    specs = [s.split(":") for s in sys.argv[2:]]
    head_css = (SITE / "assets" / "css" / ASSET).read_text(encoding="utf-8")
    fold_css = head_css
    for a, b in SUBS.items():
        assert fold_css.count(a) == 1, a[:50]
        fold_css = fold_css.replace(a, b)
    man = {}
    srv, port = serve(SITE)
    with sync_playwright() as p:
        br = p.chromium.launch()
        for board, mode, layout, vps in specs:
            css = fold_css if mode == "fold" else head_css
            for theme in ("dark", "light"):
                for lang in ("en", "zh"):
                    for vp in vps.split(","):
                        w = int(vp)
                        ctx = br.new_context(viewport={"width": w, "height": 1000},
                                             device_scale_factor=2)
                        ctx.add_init_script(
                            "try{localStorage.setItem('theme','%s');localStorage.setItem('lang','%s')}catch(e){}"
                            % (theme, lang))
                        pg = ctx.new_page()
                        # canada_stocks ships pv_css INLINE from the real rebuild — never swap it
                        if board != "canada_stocks":
                            pg.route("**/" + ASSET + "*", lambda r: r.fulfill(
                                status=200, content_type="text/css", body=css))
                        pg.goto(f"http://127.0.0.1:{port}/{board}.html", wait_until="networkidle")
                        pg.wait_for_timeout(1500)
                        if layout == "floor246":
                            pg.add_style_tag(content=FLOOR246)
                            pg.wait_for_timeout(400)
                        elif layout == "metric8":
                            # Disclosed synthetic stress: widen every glyph in the
                            # shelf by 8%, the way a wider real font stack does on
                            # the Chairman's machine vs headless Chromium.
                            pg.add_style_tag(content=".pv-zn{font-size:11.34px!important}")
                            pg.wait_for_timeout(400)
                        prev = -1
                        for _ in range(10):
                            cur = pg.evaluate("document.body.scrollHeight")
                            if cur == prev: break
                            prev = cur; pg.wait_for_timeout(300)
                        d = pg.evaluate(PROBE)
                        assert (d["theme"], d["lang"]) == (theme, lang), (d["theme"], d["lang"])
                        key = f"{board}_{mode}_{layout}_{theme}_{lang}_{vp}"
                        rows = d["rows"]
                        chipped = [r for r in rows if "chipTxt" in r]
                        _pool = [r for r in (chipped or rows) if not r.get("ghosted")] or (chipped or rows)
                        frame = _pool[:3] if len(_pool) >= 2 else (chipped or rows)[:3]
                        if frame:
                            x0 = min(r["docRect"][0] for r in frame); y0 = min(r["docRect"][1] for r in frame)
                            x1 = max(r["docRect"][0] + r["docRect"][2] for r in frame)
                            y1 = max(r["docRect"][1] + r["docRect"][3] for r in frame)
                            pg.screenshot(path=str(out / f"{key}_cards.png"), full_page=True,
                                          clip={"x": max(0, x0 - 8), "y": max(0, y0 - 8),
                                                "width": x1 - x0 + 16, "height": y1 - y0 + 16})
                        lit = [r for r in (chipped or rows) if not r.get("ghosted")] or (chipped or rows)
                        tgt = max(lit, key=lambda r: r.get("valW", 0)) if rows else None
                        if tgt:
                            x, y, ww, hh = tgt["znRect"]
                            pg.screenshot(path=str(out / f"{key}_zoneshelf.png"), full_page=True,
                                          clip={"x": max(0, x - 3), "y": max(0, y - 3),
                                                "width": ww + 6, "height": hh + 6})
                        man[key] = d
                        ctx.close()
        br.close()
    srv.shutdown()
    (out / "measurements.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))
    for k, d in man.items():
        ch = [r for r in d["rows"] if "chipTxt" in r]
        print(f"{k}: rows={len(d['rows'])} chips={len(ch)} docW={d['docW']}/{d['vw']} "
              f"cardW={sorted({r['cardW'] for r in d['rows']})} "
              f"shelfH={sorted({r['znH'] for r in d['rows']})} "
              f"trunc={sum(1 for r in ch if r['chipTruncated'])} "
              f"folded={sum(1 for r in ch if r['chipFolded'])} "
              f"valClip={sum(1 for r in d['rows'] if r.get('valClippedByShelf'))} "
              f"chipClip={sum(1 for r in ch if r['chipClipped'])}")


main()
