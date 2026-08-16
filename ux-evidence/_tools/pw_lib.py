#!/usr/bin/env python3
"""Playwright capture helpers. Capture fidelity is separate from product layout."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import relpath  # noqa: E402
from selector_contract import RESOLVE_JS, SECTION_CHILDREN_JS, as_resolve_spec  # noqa: E402

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
    """Import session cookies into memory only. Never write values to disk."""
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


def cookie_names(cookies: list[dict]) -> list[str]:
    return [c.get("name") for c in cookies if c.get("name")]


def launch_browser(p):
    return p.chromium.launch(channel="chrome", headless=True, args=["--disable-dev-shm-usage"])


def new_page(browser, w: int, h: int, cookies=None):
    ctx = browser.new_context(
        viewport={"width": w, "height": h},
        device_scale_factor=DPR,
        is_mobile=False,
    )
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
          scrollH: document.documentElement.scrollHeight,
          clientW: document.documentElement.clientWidth,
          clientH: document.documentElement.clientHeight
        })"""
    )


def _fidelity_record(path: Path, req_w: int, req_h: int, full: bool, m: dict, img: Image.Image) -> dict:
    overflow_px = max(0, int(m.get("scrollW") or 0) - req_w)
    png_ok = True
    if not full:
        png_ok = abs(img.width - req_w) <= 2 and abs(img.height - req_h) <= 2
    else:
        png_ok = img.height >= req_h - 2
    return {
        "repo_relative_path": relpath(path),
        "capture_fidelity": {
            "requested_width": req_w,
            "requested_height": req_h,
            "inner_width": m.get("innerWidth"),
            "inner_height": m.get("innerHeight"),
            "DPR": m.get("dpr"),
            "PNG_width": img.width,
            "PNG_height": img.height,
            "png_dimensions_valid": png_ok,
            "full_page": full,
        },
        "product_layout": {
            "document_scroll_width": m.get("scrollW"),
            "document_scroll_height": m.get("scrollH"),
            "horizontal_overflow": overflow_px > 2,
            "horizontal_overflow_px": overflow_px,
            "vertical_page_length": m.get("scrollH"),
        },
        "requested": {"w": req_w, "h": req_h, "full": full},
        "inner": {"w": m.get("innerWidth"), "h": m.get("innerHeight")},
        "visual": {"w": m.get("visualW"), "h": m.get("visualH")},
        "outer": {"w": m.get("outerWidth"), "h": m.get("outerHeight")},
        "dpr": m.get("dpr"),
        "scroll": {"x": m.get("scrollX"), "y": m.get("scrollY"), "w": m.get("scrollW"), "h": m.get("scrollH")},
        "screenshot_px": {"w": img.width, "h": img.height},
        "horizontal_overflow": overflow_px > 2,
        "pass": True,
    }


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
    if full:
        if img.height < req_h - 2:
            path.unlink(missing_ok=True)
            raise CaptureFidelityError("full-page shorter than viewport")
        if abs(img.height - req_h) <= 2 and m["scrollH"] > req_h * 1.4:
            path.unlink(missing_ok=True)
            raise CaptureFidelityError("full-page collapsed to a single viewport")
    kind = detect_corruption(img, req_h, full)
    if kind:
        path.unlink(missing_ok=True)
        raise CaptureFidelityError(f"{kind} in {path.name}")
    rec = _fidelity_record(path, req_w, req_h, full, m, img)
    rec["path"] = rec["repo_relative_path"]
    return rec


def capture_segments(page, dest_dir: Path, prefix: str, req_w: int, req_h: int) -> list[dict]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    scroll_h = int(viewport_metrics(page)["scrollH"])
    recs = []
    y = 0
    i = 0
    last_observed = -1
    while i < 40:
        requested = y
        page.evaluate(f"window.scrollTo(0, {requested})")
        page.wait_for_timeout(120)
        observed = int(viewport_metrics(page)["scrollY"])
        if last_observed >= 0 and abs(observed - last_observed) < 8:
            break
        rec = assert_and_shot(page, dest_dir / f"{prefix}_seg_{i:02d}_y{requested}.png", req_w, req_h)
        rec["segment_index"] = i
        rec["requested_scroll_y"] = requested
        rec["observed_scroll_y"] = observed
        rec["scroll_y"] = observed
        recs.append(rec)
        last_observed = observed
        if observed + req_h >= scroll_h - 2:
            break
        y = requested + req_h
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
        lab = el.get("stable_id") or el.get("id") or "?"
        draw.rectangle([x, max(0, y - 12), x + max(28, 6 * len(lab)), max(12, y)], fill=(0, 200, 255, 210))
        draw.text((x + 2, max(0, y - 12)), lab, fill=(0, 0, 0, 255), font=font)
        n += 1
        if n > 80:
            break
    Image.alpha_composite(im, overlay).convert("RGB").save(dest)
    return n


def resolve_targets(page, catalog: list[dict]) -> list[dict]:
    specs = [as_resolve_spec(item) for item in catalog]
    return page.evaluate(RESOLVE_JS, specs)


def extract(page, catalog):
    """Legacy-compatible extract using the selector contract."""
    elements = resolve_targets(page, catalog)
    for el in elements:
        el.setdefault("id", el.get("stable_id"))
        el.setdefault("selector", el.get("selector_used") or el.get("selector_requested"))
        el.setdefault("section", el.get("evidence_section"))
    i18n = page.evaluate(
        """() => {
          const i18n = [];
          document.querySelectorAll('.l-en').forEach((en, i) => {
            if (i > 250) return;
            const zh = en.parentElement && en.parentElement.querySelector(':scope > .l-zh');
            i18n.push({en: (en.textContent||'').trim(), zh: zh ? (zh.textContent||'').trim() : null});
          });
          return i18n;
        }"""
    )
    meta = page.evaluate(
        """() => ({
          href: location.href, title: document.title,
          lang: document.documentElement.getAttribute('data-lang') || 'en',
          theme: document.documentElement.getAttribute('data-theme') || 'dark',
          visible_text_active: document.body.innerText,
          auth_hint: {
            user_attr: document.documentElement.getAttribute('data-user'),
            lock_cta: !!document.querySelector('.lock-cta')
          }
        })"""
    )
    return {**meta, "elements": elements, "i18n_pairs": i18n}


def extract_sections(page, section_specs: list[dict], viewport_h: int) -> list[dict]:
    resolved = resolve_targets(page, section_specs)
    out = []
    for spec, res in zip(section_specs, resolved):
        children = {"major_children": [], "major_controls": []}
        if res.get("found") and res.get("selector_used"):
            try:
                children = page.evaluate(SECTION_CHILDREN_JS, {"selector": res["selector_used"]})
            except Exception:
                pass
        box = res.get("page_box") or {}
        h = box.get("h") or 0
        geometry_status = "RESOLVED" if res.get("resolution_status") == "RESOLVED" and res.get("found") else "UNRESOLVED"
        if res.get("found") and res.get("resolution_status") == "RESOLVED" and h <= 0:
            geometry_status = "UNRESOLVED"
        rec = {
            "section_id": spec.get("stable_id") or spec.get("id"),
            "id": spec.get("stable_id") or spec.get("id"),
            "label": spec.get("human_label") or spec.get("label"),
            "order": spec.get("order"),
            "found": bool(res.get("found")),
            "visible": bool(res.get("visible")),
            "resolution_status": res.get("resolution_status"),
            "geometry_status": geometry_status,
            "selector_used": res.get("selector_used"),
            "selector_requested": res.get("selector_requested"),
            "match_count": res.get("match_count"),
            "page_box": res.get("page_box"),
            "viewport_box": res.get("viewport_box"),
            "viewport_height_footprint": round(h / viewport_h, 3) if viewport_h else None,
            "major_children": children.get("major_children") or [],
            "major_controls": children.get("major_controls") or [],
            "source_hint": spec.get("source_hint"),
            "source": spec.get("source_hint"),
        }
        out.append(rec)
    return out


def compact_error(exc: BaseException | str) -> dict:
    text = str(exc)
    first = text.splitlines()[0] if text else "error"
    code = "ERROR"
    if "Timeout" in text:
        code = "TIMEOUT"
    elif "UNRESOLVED" in text:
        code = "UNRESOLVED"
    return {"error_code": code, "error_summary": first[:240], "raw_error_ref": None}
