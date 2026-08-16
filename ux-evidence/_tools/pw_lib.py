#!/usr/bin/env python3
"""Playwright capture helpers with viewport self-check. Cookie values never written to disk."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

DPR = 1


class CaptureFidelityError(RuntimeError):
    pass


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _similar(a: Image.Image, b: Image.Image, thresh: float = 6.0) -> bool:
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a.convert("L"), b.convert("L"))
    return ImageStat.Stat(diff).mean[0] < thresh


def detect_corruption(img: Image.Image, viewport_h_px: int, full: bool) -> str | None:
    w, h = img.size
    if full and h >= int(viewport_h_px * 1.85):
        band_h = min(viewport_h_px, h // 2)
        top = img.crop((0, 0, w, band_h))
        nxt = img.crop((0, band_h, w, min(h, band_h * 2)))
        if _similar(top, nxt):
            return "vertical_tile_repeat"
    return None


def load_aionui_cookies() -> list[dict]:
    port = os.environ.get("AIONUI_CDP_ACTIVE_PORT")
    token = os.environ.get("AIONUI_CDP_BRIDGE_TOKEN")
    if not port or not token:
        return []
    try:
        import websocket
    except Exception:
        return []
    ws = websocket.create_connection(
        f"ws://127.0.0.1:{port}/aionui-cdp?token={token}", timeout=8
    )
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    deadline = time.time() + 8
    data = None
    while time.time() < deadline:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            data = msg
            break
    ws.close()
    raw = ((data or {}).get("result") or {}).get("cookies") or []
    out = []
    for c in raw:
        domain = c.get("domain") or ""
        if "mastermind-x.com" not in domain:
            continue
        ss = {"strict": "Strict", "lax": "Lax", "none": "None"}.get(
            str(c.get("sameSite") or "Lax").lower(), "Lax"
        )
        item = {
            "name": c["name"],
            "value": c["value"],
            "domain": domain,
            "path": c.get("path") or "/",
            "httpOnly": bool(c.get("httpOnly")),
            "secure": bool(c.get("secure")),
            "sameSite": ss,
        }
        if c.get("expires") and c["expires"] > 0:
            item["expires"] = int(c["expires"])
        out.append(item)
    return out


def launch_browser(p):
    return p.chromium.launch(channel="chrome", headless=True, args=["--disable-dev-shm-usage"])


def new_page(browser, w: int, h: int, cookies=None):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=DPR)
    if cookies:
        ctx.add_cookies(cookies)
    page = ctx.new_page()
    page.set_default_timeout(20000)
    return ctx, page


def goto(page, url: str, wait_ms: int = 1500):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(wait_ms)


def viewport_metrics(page) -> dict:
    return page.evaluate(
        """() => ({
          innerWidth, innerHeight, outerWidth, outerHeight,
          dpr: devicePixelRatio,
          visualW: window.visualViewport ? visualViewport.width : null,
          visualH: window.visualViewport ? visualViewport.height : null,
          scrollX, scrollY,
          scrollW: document.documentElement.scrollWidth,
          scrollH: document.documentElement.scrollHeight
        })"""
    )


def assert_and_shot(page, path: Path, req_w: int, req_h: int, full: bool = False) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    m = viewport_metrics(page)
    if abs(m["innerWidth"] - req_w) > 1 or (not full and abs(m["innerHeight"] - req_h) > 1):
        raise CaptureFidelityError(
            f"viewport mismatch requested={req_w}x{req_h} inner={m['innerWidth']}x{m['innerHeight']}"
        )
    if abs((m.get("dpr") or 1) - DPR) > 0.05:
        raise CaptureFidelityError(f"dpr mismatch {m.get('dpr')} != {DPR}")
    page.screenshot(path=str(path), full_page=full, type="png", scale="css")
    img = Image.open(path)
    if not full and (abs(img.width - req_w) > 2 or abs(img.height - req_h) > 2):
        path.unlink(missing_ok=True)
        raise CaptureFidelityError(f"shot {img.size} != {req_w}x{req_h} ({path.name})")
    overflow = False
    if full:
        if img.height < req_h - 2:
            path.unlink(missing_ok=True)
            raise CaptureFidelityError("full-page shorter than viewport")
        if abs(img.height - req_h) <= 2 and m["scrollH"] > req_h * 1.4:
            path.unlink(missing_ok=True)
            raise CaptureFidelityError("full-page collapsed to a single viewport")
        overflow = abs(img.width - req_w) > 2
    kind = detect_corruption(img, req_h, full)
    if kind:
        path.unlink(missing_ok=True)
        raise CaptureFidelityError(f"{kind} in {path.name}")
    return {
        "path": str(path),
        "requested": {"w": req_w, "h": req_h, "full": full},
        "inner": {"w": m["innerWidth"], "h": m["innerHeight"]},
        "visual": {"w": m.get("visualW"), "h": m.get("visualH")},
        "dpr": m.get("dpr"),
        "scroll": {"x": m.get("scrollX"), "y": m.get("scrollY"), "w": m.get("scrollW"), "h": m.get("scrollH")},
        "screenshot_px": {"w": img.width, "h": img.height},
        "horizontal_overflow": overflow,
        "pass": True,
    }


def capture_segments(page, dest_dir: Path, prefix: str, req_w: int, req_h: int) -> list[dict]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    scroll_h = int(viewport_metrics(page)["scrollH"])
    recs, y, i = [], 0, 0
    while y < scroll_h - 2 and i < 40:
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(120)
        rec = assert_and_shot(page, dest_dir / f"{prefix}_seg_{i:02d}_y{y}.png", req_w, req_h)
        rec["segment_index"] = i
        rec["scroll_y"] = y
        recs.append(rec)
        y += req_h
        i += 1
    page.evaluate("window.scrollTo(0,0)")
    return recs


def annotate(src: Path, dest: Path, elements: list[dict], box_key: str = "viewport_box"):
    im = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    n = 0
    for el in elements:
        bb = el.get(box_key) or {}
        if not el.get("visible"):
            continue
        x, y, w, h = bb.get("x", 0), bb.get("y", 0), bb.get("w", 0), bb.get("h", 0)
        if w < 6 or h < 6 or y > im.size[1] or x > im.size[0]:
            continue
        draw.rectangle([x, y, x + w, y + h], outline=(0, 200, 255, 180), width=1)
        lab = el.get("id") or "?"
        draw.rectangle([x, max(0, y - 12), x + max(28, 6 * len(lab)), max(12, y)], fill=(0, 200, 255, 210))
        draw.text((x + 2, max(0, y - 12)), lab, fill=(0, 0, 0, 255), font=font)
        n += 1
        if n > 80:
            break
    Image.alpha_composite(im, overlay).convert("RGB").save(dest)
    return n


EXTRACT_JS = """
({catalog}) => {
  const vis = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const txt = (el) => ((el && el.innerText) || '').replace(/\\s+/g, ' ').trim();
  const boxes = (el) => {
    const r = el.getBoundingClientRect();
    const sx = scrollX || 0, sy = scrollY || 0;
    const vb = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    return {viewport_box: vb, page_box: {x: Math.round(r.x+sx), y: Math.round(r.y+sy), w: vb.w, h: vb.h, scrollX: sx, scrollY: sy}};
  };
  const elements = [];
  for (const spec of catalog) {
    let el = null;
    try { el = spec.selector ? document.querySelector(spec.selector) : null; } catch (e) {}
    const item = {
      id: spec.id, section: spec.section || null, selector: spec.selector || null,
      found: !!el, visible: vis(el), visible_label: el ? txt(el).slice(0,240) : null,
      tag: el ? el.tagName.toLowerCase() : null,
      href: el ? el.getAttribute('href') : null,
      aria_expanded: el ? el.getAttribute('aria-expanded') : null,
      aria_pressed: el ? el.getAttribute('aria-pressed') : null,
      aria_selected: el ? el.getAttribute('aria-selected') : null,
      data_ticker: el ? el.getAttribute('data-ticker') : null
    };
    if (el) Object.assign(item, boxes(el));
    else { item.viewport_box = null; item.page_box = null; }
    elements.push(item);
  }
  const i18n = [];
  document.querySelectorAll('.l-en').forEach((en, i) => {
    if (i > 250) return;
    const zh = en.parentElement && en.parentElement.querySelector(':scope > .l-zh');
    i18n.push({en: (en.textContent||'').trim(), zh: zh ? (zh.textContent||'').trim() : null});
  });
  return {
    href: location.href, title: document.title,
    lang: document.documentElement.getAttribute('data-lang') || 'en',
    theme: document.documentElement.getAttribute('data-theme') || 'dark',
    elements, i18n_pairs: i18n, visible_text_active: document.body.innerText,
    auth_hint: {
      user_attr: document.documentElement.getAttribute('data-user'),
      lock_cta: !!document.querySelector('.lock-cta')
    }
  };
}
"""


def extract(page, catalog):
    return page.evaluate(EXTRACT_JS, {"catalog": catalog})
