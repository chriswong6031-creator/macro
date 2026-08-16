#!/usr/bin/env python3
"""Read-only CDP evidence collector for Mastermind-X (AionUi in-app browser)."""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import websocket
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("/Users/chriswong/Documents/Cluade/macro-main/ux-evidence")


def connect():
    port = os.environ["AIONUI_CDP_ACTIVE_PORT"]
    token = os.environ["AIONUI_CDP_BRIDGE_TOKEN"]
    ws = websocket.create_connection(
        f"ws://127.0.0.1:{port}/aionui-cdp?token={token}", timeout=20
    )
    return ws


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        self.events = []

    def call(self, method, params=None, timeout=30):
        self._id += 1
        mid = self._id
        payload = {"id": mid, "method": method}
        if params:
            payload["params"] = params
        self.ws.send(json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            data = json.loads(raw)
            if "method" in data and "id" not in data:
                self.events.append(data)
                continue
            if data.get("id") == mid:
                if data.get("error"):
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result") or {}
        raise TimeoutError(method)

    def ev(self, expression, await_promise=False):
        r = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "timeout": 15000,
            },
            timeout=20,
        )
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"])
        return (r.get("result") or {}).get("value")

    def enable(self):
        for d in (
            "Page",
            "Runtime",
            "DOM",
            "CSS",
            "Accessibility",
            "Network",
            "Log",
            "Overlay",
        ):
            try:
                self.call(f"{d}.enable")
            except Exception as e:
                print("enable fail", d, e)

    def navigate(self, url, wait=4.0):
        self.call("Page.navigate", {"url": url})
        time.sleep(wait)
        try:
            self.call("Page.waitForNetworkIdle", {"idleTime": 800, "timeout": 12000}, timeout=14)
        except Exception:
            time.sleep(2.0)
        self.ev("document.fonts && document.fonts.ready ? document.fonts.ready.then(()=>1) : 1", True)

    def viewport(self, w, h, mobile=False):
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": w,
                "height": h,
                "deviceScaleFactor": 1,
                "mobile": mobile,
                "screenWidth": w,
                "screenHeight": h,
            },
        )
        time.sleep(0.6)

    def screenshot(self, path: Path, full=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        params = {"format": "png", "fromSurface": True}
        if full:
            params["captureBeyondViewport"] = True
        r = self.call("Page.captureScreenshot", params, timeout=45)
        path.write_bytes(base64.b64decode(r["data"]))
        return path

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


EXTRACT_JS = r"""
(() => {
  const lang = document.documentElement.getAttribute('data-lang') || 'en';
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const txt = (el) => (el.innerText || '').replace(/\s+/g, ' ').trim();
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  const sel = (el) => {
    if (el.id) return '#' + el.id;
    const dt = el.getAttribute('data-ticker');
    if (dt && el.classList.contains('pvcard')) return `a.pvcard[data-ticker="${dt}"]`;
    const cls = [...el.classList].slice(0,3).join('.');
    return (el.tagName.toLowerCase() + (cls ? '.' + cls : '')).slice(0, 120);
  };

  const elements = [];
  const push = (id, el, extra={}) => {
    if (!el) return;
    elements.push({
      id, visible_label: txt(el).slice(0, 240),
      role: el.getAttribute('role') || el.tagName.toLowerCase(),
      selector: sel(el), tag: el.tagName.toLowerCase(),
      bounding_box: box(el), visible: vis(el),
      state: {
        hidden: el.hidden || el.hasAttribute('hidden'),
        aria_expanded: el.getAttribute('aria-expanded'),
        aria_selected: el.getAttribute('aria-selected'),
        disabled: !!el.disabled,
        href: el.getAttribute('href'),
        data_ticker: el.getAttribute('data-ticker'),
        data_stage: el.getAttribute('data-stage'),
        className: el.className && String(el.className).slice(0, 180)
      },
      ...extra
    });
  };

  push('E001', document.querySelector('.brand, .logo, a[href="index.html"], a[href="/"]'), {section:'shell', note:'brand'});
  document.querySelectorAll('nav a, .nav a, .menu a, header a').forEach((a,i) => {
    if (i < 40) push(`E1${String(i+1).padStart(2,'0')}`, a, {section:'shell-nav'});
  });
  push('E040', document.querySelector('#q, input[type="search"], .search input, input[placeholder*="NVDA" i], input[placeholder*="search" i]'), {section:'shell', note:'global-search'});
  push('E041', document.querySelector('button.settings, .gear, [aria-label*="Settings" i], .icon-settings, a[href*="settings"]'), {section:'shell'});
  push('E042', document.getElementById('prophet-live'), {section:'prophet-live'});
  push('E043', document.getElementById('us-standouts'), {section:'board'});
  push('E044', document.querySelector('#us-standouts h2'), {section:'board', note:'board-title'});
  push('E045', document.getElementById('us-st-view-toggle'), {section:'board-tools'});
  push('E046', document.getElementById('us-st-btn-grid'), {section:'board-tools'});
  push('E047', document.getElementById('us-st-btn-table'), {section:'board-tools'});
  push('E048', document.getElementById('us-board-sub'), {section:'board'});
  push('E049', document.querySelector('.pbs-note'), {section:'board'});
  push('E050', document.getElementById('trd-btn'), {section:'board-tools'});
  push('E051', document.getElementById('trd-dlg'), {section:'board-tools'});
  push('E052', document.querySelector('.prophet-board-tools'), {section:'board-tools'});
  push('E053', document.querySelector('.pb-fn'), {section:'board'});

  const filters = document.querySelectorAll('#us-standouts button, #us-standouts [role="tab"], #us-standouts .chip, #us-standouts .pill, #us-standouts [data-stage], .pb-filters button, .st-filter, [data-filter]');
  filters.forEach((el,i) => {
    if (i < 30) push(`E2${String(i+1).padStart(2,'0')}`, el, {section:'filters'});
  });

  const cards = [...document.querySelectorAll('a.pvcard')];
  cards.slice(0, 24).forEach((el,i) => {
    push(`E3${String(i+1).padStart(2,'0')}`, el, {section:'card-grid', note:'prophet-card'});
  });

  const headings = [...document.querySelectorAll('h1,h2,h3')].slice(0, 30);
  headings.forEach((el,i) => push(`E4${String(i+1).padStart(2,'0')}`, el, {section:'headings'}));

  const interactive = [...document.querySelectorAll('button, [role="button"], a.pvcard, select, input, [aria-haspopup], summary')];
  const inter = interactive.filter(vis).slice(0, 80).map((el,i) => ({
    idx: i, tag: el.tagName.toLowerCase(), id: el.id || null,
    text: txt(el).slice(0,160), href: el.getAttribute('href'),
    aria: el.getAttribute('aria-label'), role: el.getAttribute('role'),
    type: el.getAttribute('type'), box: box(el), selector: sel(el)
  }));

  const styleSample = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    const keys = ['display','position','width','maxWidth','height','padding','margin','gap','overflow','fontSize','fontWeight','lineHeight','color','backgroundColor','borderRadius','boxShadow','zIndex','top','gridTemplateColumns'];
    const o = {};
    keys.forEach(k => o[k] = cs[k]);
    return o;
  };

  const tokens = {colors:new Set(), fontSizes:new Set(), radii:new Set(), shadows:new Set(), spacings:new Set()};
  [...document.querySelectorAll('#us-standouts *, header *, nav *, .pvcard')].slice(0, 400).forEach(el => {
    const cs = getComputedStyle(el);
    tokens.colors.add(cs.color); tokens.colors.add(cs.backgroundColor);
    tokens.fontSizes.add(cs.fontSize); tokens.radii.add(cs.borderRadius);
    tokens.shadows.add(cs.boxShadow);
    tokens.spacings.add(cs.padding); tokens.spacings.add(cs.margin);
  });
  const set2list = (s) => [...s].filter(x => x && x !== 'none' && x !== 'rgba(0, 0, 0, 0)').slice(0, 80);

  return {
    href: location.href,
    title: document.title,
    lang, theme,
    ready: document.readyState,
    viewport: {w: innerWidth, h: innerHeight, dpr: devicePixelRatio, scrollY: scrollY, scrollH: document.documentElement.scrollHeight},
    auth_hint: {
      has_account_chip: !!document.querySelector('.acct, .account, [data-auth], #mdx-acct'),
      body_class: document.body.className,
      html_attrs: {
        lang: document.documentElement.getAttribute('data-lang'),
        theme: document.documentElement.getAttribute('data-theme'),
        user: document.documentElement.getAttribute('data-user')
      }
    },
    counts: {
      pvcards: cards.length,
      featured: document.querySelectorAll('a.pvcard.pv-featured').length,
      buy: document.querySelectorAll('a.pvcard.pv-buy').length,
      near: document.querySelectorAll('a.pvcard.pv-near').length,
      wait: document.querySelectorAll('a.pvcard.pv-wait').length,
      hold: document.querySelectorAll('a.pvcard.pv-hold').length,
      avoid: document.querySelectorAll('a.pvcard.pv-avoid').length,
      headings: document.querySelectorAll('h1,h2,h3,h4').length,
      buttons: document.querySelectorAll('button').length,
      links: document.querySelectorAll('a[href]').length
    },
    cards: cards.map(el => ({
      ticker: el.getAttribute('data-ticker'),
      stage: el.getAttribute('data-stage'),
      href: el.getAttribute('href'),
      verb: [...el.classList].find(c => c.startsWith('pv-') && !['pvcard','pv-featured','pv-triage'].includes(c)),
      featured: el.classList.contains('pv-featured'),
      text: txt(el).slice(0, 280),
      box: box(el)
    })),
    elements,
    interactive: inter,
    styles: {
      board: styleSample(document.getElementById('us-standouts')),
      first_card: styleSample(document.querySelector('a.pvcard')),
      header: styleSample(document.querySelector('header, .topbar, .site-header, nav')),
      h2: styleSample(document.querySelector('#us-standouts h2')),
      track: styleSample(document.getElementById('trd-btn'))
    },
    token_proliferation: {
      color_count: set2list(tokens.colors).length,
      font_size_count: set2list(tokens.fontSizes).length,
      radius_count: set2list(tokens.radii).length,
      shadow_count: set2list(tokens.shadows).length,
      colors: set2list(tokens.colors),
      font_sizes: set2list(tokens.fontSizes),
      radii: set2list(tokens.radii),
      shadows: set2list(tokens.shadows).slice(0,40)
    },
    visible_text: (document.querySelector('#us-standouts') || document.body).innerText
  };
})()
"""


def annotate(src: Path, dest: Path, elements: list[dict]):
    im = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    used = 0
    for el in elements:
        bb = el.get("bounding_box") or {}
        if not el.get("visible"):
            continue
        x, y, w, h = bb.get("x", 0), bb.get("y", 0), bb.get("w", 0), bb.get("h", 0)
        if w < 8 or h < 8:
            continue
        if y < 0 or x < 0 or y > im.size[1] or x > im.size[0]:
            continue
        color = (0, 200, 255, 180)
        draw.rectangle([x, y, x + w, y + h], outline=color, width=1)
        label = el["id"]
        tw, th = 36, 12
        draw.rectangle([x, max(0, y - th), x + tw, max(th, y)], fill=(0, 200, 255, 210))
        draw.text((x + 2, max(0, y - th)), label, fill=(0, 0, 0, 255), font=font)
        used += 1
        if used > 70:
            break
    out = Image.alpha_composite(im, overlay).convert("RGB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, quality=90)
    return used


def dump_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("cmd")
    p.add_argument("--url")
    p.add_argument("--out")
    p.add_argument("--w", type=int, default=1440)
    p.add_argument("--h", type=int, default=1000)
    p.add_argument("--full", action="store_true")
    p.add_argument("--name", default="shot")
    p.add_argument("--mobile", action="store_true")
    p.add_argument("--js")
    args = p.parse_args()

    cdp = CDP(connect())
    cdp.enable()
    if args.cmd == "nav":
        cdp.navigate(args.url)
        print(json.dumps(cdp.ev("({href:location.href,title:document.title})")))
    elif args.cmd == "shot":
        cdp.viewport(args.w, args.h, mobile=args.mobile)
        out = Path(args.out)
        cdp.screenshot(out, full=args.full)
        print(str(out), out.stat().st_size)
    elif args.cmd == "extract":
        data = cdp.ev(EXTRACT_JS)
        dump_json(Path(args.out), data)
        print("ok", Path(args.out))
    elif args.cmd == "eval":
        print(json.dumps(cdp.ev(args.js), ensure_ascii=False)[:8000])
    elif args.cmd == "click":
        cdp.ev(args.js)
        time.sleep(0.8)
        print(json.dumps(cdp.ev("({href:location.href,title:document.title})")))
    elif args.cmd == "info":
        print(json.dumps(cdp.ev("({href:location.href,title:document.title,ready:document.readyState,w:innerWidth,h:innerHeight})")))
    cdp.close()


if __name__ == "__main__":
    main()
