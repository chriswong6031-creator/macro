#!/usr/bin/env python3
"""Render the @mastermindx001 launch card (the account's intro / pinned post art).

One-off marketing asset, not a nightly lane: it makes no market claim, quotes no
price and names no ticker, so it never goes stale and needs no tape gate. The
chart is a labelled DIAGRAM of what one of our setup posts contains, which is the
one thing a stranger scrolling X needs to know about this account.

House chrome is imported, not re-drawn: the footer brand bar and the favicon
logomark come from engine.marketing.chart_render, the same helpers every signal
card already posts through, so the intro card and the feed are visibly one family.

Type is the brand's own stack. Note the landing links 'Archivo Expanded', which
is NOT a Google Fonts family (the request 400s and the page silently falls back
to plain Archivo) - here we ask for the real thing, Archivo at font-stretch 125%.
Faces are downloaded once, cached, and base64-embedded so the SVG is
self-contained and the raster reproduces offline.

Output lands in site/assets/landing/ because app/deploy/Caddyfile is DEFAULT-DENY
for static assets: its @reg_asset / @reg_asset_err allowlists name /assets/css/*
and /assets/landing/* and nothing else, so a public marketing image written
anywhere else under site/assets/ answers 401 {"locked":true} to every visitor and
every crawler.

Usage:
    python3 scripts/make_launch_card.py [--out-dir site/assets/landing]
"""
from __future__ import annotations

import argparse
import base64
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.marketing.chart_render import (  # noqa: E402
    _brand_bar,
    _favicon_logomark,
    find_chrome,
)

# ── canvas ───────────────────────────────────────────────────────────────────
W, H = 1600, 960
HEADER_H = 84
FOOTER_H = 58

# ── palette (house card family - see chart_render.render_chart_v2) ───────────
NAVY = "#0E1420"        # card body
BAND = "#0A1020"        # header / footer bands
HAIR = "#1C2537"        # structural hairline
UP = "#4CAF50"          # directional green
DOWN = "#E23B3B"        # directional red
BLUE = "#5B9DFF"        # brand blue (logomark gradient stop 1)
INK_DIM = "#93A7CC"     # secondary text
INK_FAINT = "#6B7A99"   # tertiary text
INK_CAPTION = "#8496B8"  # diagram caption: must stay legible at phone width

FONT_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Archivo:wdth,wght@125,700;125,800"
    "&family=Inter:wght@500;600;700"
    "&display=swap"
)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read()


def font_face_css(cache: Path) -> str:
    """Google-Fonts @font-face blocks for the latin subset, woff2 inlined base64.

    Latin only: every glyph on this card is ASCII, and dragging the cyrillic /
    greek / vietnamese subsets in would multiply the SVG size for nothing.
    Downloads are cached under *cache* so re-renders work offline.
    """
    cache.mkdir(parents=True, exist_ok=True)
    css_file = cache / "fonts.css"
    if not css_file.exists():
        css_file.write_bytes(_get(FONT_CSS_URL))
    css = css_file.read_text(encoding="utf-8")

    out: list[str] = []
    # css2 emits "/* latin */" immediately before each @font-face it labels.
    for subset, block in re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})", css):
        if subset != "latin":
            continue
        m = re.search(r"src:\s*url\((https://[^)]+\.woff2)\)", block)
        if not m:
            continue
        url = m.group(1)
        blob = cache / url.rsplit("/", 1)[-1]
        if not blob.exists():
            blob.write_bytes(_get(url))
        b64 = base64.b64encode(blob.read_bytes()).decode("ascii")
        out.append(
            re.sub(
                r"src:\s*url\(https://[^)]+\.woff2\)",
                f"src:url(data:font/woff2;base64,{b64})",
                block,
            ).replace("\n", "")
        )
    if not out:
        raise RuntimeError("no latin @font-face blocks parsed from Google Fonts CSS")
    return "".join(out)


# ── the specimen series ──────────────────────────────────────────────────────
# Deterministic, hand-drawn OHLC in abstract 0-100 units. No ticker, no prices,
# no axis: this is the ANATOMY of a setup, not a call on anything. Shape is a
# base, a flush that holds, then a climb back into the entry band.
BARS: list[tuple[float, float, float, float]] = [
    (44, 47, 42, 45), (45, 46, 41, 42), (42, 45, 40, 44), (44, 48, 43, 47),
    (47, 49, 44, 45), (45, 46, 40, 41), (41, 43, 38, 39), (39, 42, 37, 41),
    (41, 44, 40, 43), (43, 45, 39, 40), (40, 41, 35, 36), (36, 38, 33, 34),
    (34, 36, 31, 32), (32, 37, 32, 36), (36, 39, 35, 38), (38, 40, 36, 37),
    (37, 42, 36, 41), (41, 44, 40, 43), (43, 47, 42, 46), (46, 48, 44, 45),
    (45, 50, 44, 49), (49, 53, 48, 52), (52, 54, 50, 51), (51, 56, 50, 55),
    (55, 59, 54, 58), (58, 60, 55, 56), (56, 62, 56, 61), (61, 65, 60, 64),
    (64, 66, 62, 63), (63, 68, 62, 67), (67, 70, 66, 69), (69, 72, 68, 71),
    (71, 73, 69, 70), (70, 74, 69, 73),
]
P_TARGET = 88.0
P_ENTRY_HI, P_ENTRY_LO = 75.0, 67.0
P_WRONG = 28.0

MARGIN_L, MARGIN_R = 64, 1536  # card content margins
PLOT_X0, PLOT_X1 = 64, 1330    # candles
PLOT_Y0, PLOT_Y1 = 436, 772    # price band top / bottom
P_MIN, P_MAX = 20.0, 95.0


def py(p: float) -> float:
    return PLOT_Y1 - (p - P_MIN) * (PLOT_Y1 - PLOT_Y0) / (P_MAX - P_MIN)


def level_pill(y: float, text: str, color: str, *, emphasis: bool = False) -> tuple[str, float]:
    """A level label riding the right edge, the way a price axis reads.

    Right-aligned to MARGIN_R so the three of them form one clean column.
    Returns (svg, left_x) so the caller can stop its rule short of the label.
    """
    w = len(text) * 9.9 + 26
    x = MARGIN_R - w
    h = 30 if emphasis else 28
    svg = (
        f'<rect x="{x:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2:.0f}" '
        f'fill="{color}" opacity="{0.22 if emphasis else 0.15}"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + 5:.1f}" class="lbl" fill="{color}" '
        f'text-anchor="middle">{text}</text>'
    )
    return svg, x


def build_svg(font_css: str) -> str:
    uid = "lc"
    slot = (PLOT_X1 - PLOT_X0) / len(BARS)
    body_w = max(2.0, slot * 0.62)
    y_target, y_hi, y_lo, y_wrong = py(P_TARGET), py(P_ENTRY_HI), py(P_ENTRY_LO), py(P_WRONG)
    y_entry_mid = (y_hi + y_lo) / 2

    parts: list[str] = []
    defs: list[str] = []

    # ── header lockup ────────────────────────────────────────────────────────
    lm_defs, lm_group = _favicon_logomark(64 + 17, HEADER_H / 2, size=34, uid=f"{uid}hd")
    defs.append(lm_defs)
    parts.append(f'<rect x="0" y="0" width="{W}" height="{HEADER_H}" fill="{BAND}"/>')
    parts.append(lm_group)
    parts.append(
        f'<text x="118" y="{HEADER_H / 2 + 8:.0f}" class="wm">MASTERMIND</text>'
        f'<text x="{MARGIN_R}" y="{HEADER_H / 2 + 7:.0f}" class="handle" '
        f'text-anchor="end">@mastermindx001</text>'
        f'<rect x="0" y="{HEADER_H - 1}" width="{W}" height="1" fill="{HAIR}"/>'
    )

    # ── body ─────────────────────────────────────────────────────────────────
    parts.append(
        f'<rect x="0" y="{HEADER_H}" width="{W}" height="{H - HEADER_H - FOOTER_H}" fill="{NAVY}"/>'
    )
    parts.append(f'<text x="{MARGIN_L}" y="152" class="eyebrow">WHAT THIS ACCOUNT POSTS</text>')
    parts.append(
        f'<text x="{MARGIN_L}" y="232" class="h1">We post the price</text>'
        f'<text x="{MARGIN_L}" y="306" class="h1">that proves us wrong.</text>'
    )
    parts.append(
        f'<text x="{MARGIN_L}" y="360" class="sub">Setups with entry, target and the exit. '
        "What&#8217;s moving today. Results posted win or lose.</text>"
    )

    # ── the diagram ──────────────────────────────────────────────────────────
    # Captioned so nobody can read it as a live call: no ticker, no prices, no axis.
    parts.append(
        f'<rect x="{MARGIN_L}" y="396" width="{MARGIN_R - MARGIN_L}" height="1" fill="{HAIR}"/>'
        f'<text x="{MARGIN_L}" y="430" class="chip">ANATOMY OF EVERY SETUP WE POST</text>'
    )

    # TARGET - where we would take it off.
    tgt_pill, tgt_x = level_pill(y_target, "TARGET", UP)
    parts.append(
        f'<line x1="{PLOT_X0}" y1="{y_target:.1f}" x2="{tgt_x - 12:.1f}" y2="{y_target:.1f}" '
        f'stroke="{UP}" stroke-width="2" stroke-dasharray="9 7" opacity="0.5"/>'
    )
    parts.append(tgt_pill)

    # ENTRY - a zone, not a line: it is a band price has to work into.
    ent_pill, ent_x = level_pill(y_entry_mid, "ENTRY ZONE", BLUE)
    band_x1 = ent_x - 12
    parts.append(
        f'<rect x="{PLOT_X0}" y="{y_hi:.1f}" width="{band_x1 - PLOT_X0:.1f}" '
        f'height="{y_lo - y_hi:.1f}" fill="{BLUE}" opacity="0.10"/>'
        f'<line x1="{PLOT_X0}" y1="{y_hi:.1f}" x2="{band_x1:.1f}" y2="{y_hi:.1f}" '
        f'stroke="{BLUE}" stroke-width="1.5" stroke-dasharray="7 6" opacity="0.6"/>'
        f'<line x1="{PLOT_X0}" y1="{y_lo:.1f}" x2="{band_x1:.1f}" y2="{y_lo:.1f}" '
        f'stroke="{BLUE}" stroke-width="1.5" stroke-dasharray="7 6" opacity="0.6"/>'
    )
    parts.append(ent_pill)

    # ── candles ──────────────────────────────────────────────────────────────
    for i, (o, hi, lo, c) in enumerate(BARS):
        cx = PLOT_X0 + (i + 0.5) * slot
        col = UP if c >= o else DOWN
        yo, yc = py(o), py(c)
        top, bot = min(yo, yc), max(yo, yc)
        parts.append(
            f'<line x1="{cx:.1f}" y1="{py(hi):.1f}" x2="{cx:.1f}" y2="{py(lo):.1f}" '
            f'stroke="{col}" stroke-width="2"/>'
            f'<rect x="{cx - body_w / 2:.1f}" y="{top:.1f}" width="{body_w:.1f}" '
            f'height="{max(2.5, bot - top):.1f}" fill="{col}" rx="1.5"/>'
        )

    # WRONG BELOW - THE signature. The only line that bleeds off both edges of the
    # card, because it is the one the whole desk is built on. Everything else is
    # contained by the plot; this one refuses to be. It breaks only for its own
    # label, which is the single thing on the card allowed to interrupt it.
    wr_pill, wr_x = level_pill(y_wrong, "WRONG BELOW", DOWN, emphasis=True)
    parts.append(
        f'<line x1="0" y1="{y_wrong:.1f}" x2="{wr_x - 13:.1f}" y2="{y_wrong:.1f}" '
        f'stroke="{DOWN}" stroke-width="2.5" stroke-dasharray="12 7" opacity="0.6"/>'
        f'<line x1="{MARGIN_R + 13}" y1="{y_wrong:.1f}" x2="{W}" y2="{y_wrong:.1f}" '
        f'stroke="{DOWN}" stroke-width="2.5" stroke-dasharray="12 7" opacity="0.6"/>'
    )
    parts.append(wr_pill)

    # ── coverage strip ───────────────────────────────────────────────────────
    parts.append(
        f'<rect x="{MARGIN_L}" y="810" width="{MARGIN_R - MARGIN_L}" height="1" fill="{HAIR}"/>'
        f'<text x="{MARGIN_L}" y="850" class="strip">US &#183; CHINA &#183; HONG KONG &#183; CANADA '
        f'&#183; 1,600+ STOCK DOSSIERS &#183; REBUILT EVERY NIGHT</text>'
    )

    # ── house footer bar (imported verbatim from the signal-card family) ─────
    bb_defs, bb = _brand_bar(
        W, H, uid,
        tagline="AI stock signals",
        button_label="Try Pro free for 7 days",
        band_h=FOOTER_H,
    )
    defs.append(bb_defs)
    parts.append(bb)

    style = (
        f"{font_css}"
        ".wm{font-family:Archivo,sans-serif;font-stretch:125%;font-weight:800;"
        "font-size:22px;letter-spacing:2.6px;fill:#fff}"
        f".handle{{font-family:Inter,sans-serif;font-weight:600;font-size:17px;fill:{INK_DIM}}}"
        f".eyebrow{{font-family:Inter,sans-serif;font-weight:700;font-size:14px;"
        f"letter-spacing:2.8px;fill:{BLUE}}}"
        ".h1{font-family:Archivo,sans-serif;font-stretch:125%;font-weight:800;"
        "font-size:62px;letter-spacing:-1.2px;fill:#fff}"
        f".sub{{font-family:Inter,sans-serif;font-weight:500;font-size:23px;fill:{INK_DIM}}}"
        ".lbl{font-family:Inter,sans-serif;font-weight:700;font-size:15px;letter-spacing:1.7px}"
        f".chip{{font-family:Inter,sans-serif;font-weight:700;font-size:14px;"
        f"letter-spacing:1.9px;fill:{INK_CAPTION}}}"
        f".strip{{font-family:Inter,sans-serif;font-weight:600;font-size:14px;"
        f"letter-spacing:2.2px;fill:{INK_FAINT}}}"
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Mastermind: we post the price that proves us wrong. '
        f'A setup diagram labelled target, entry zone and wrong below here.">'
        f"<defs>{''.join(defs)}</defs><style>{style}</style>"
        f'<rect width="{W}" height="{H}" fill="{NAVY}"/>'
        f"{''.join(parts)}</svg>"
    )


def rasterize(svg: str, scale: int = 2) -> bytes:
    """SVG -> PNG through headless Chrome, so the raster IS the artwork we wrote."""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("no Chrome/Chromium found")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        page, out = tdp / "w.html", tdp / "out.png"
        page.write_text(
            "<!doctype html><meta charset=utf-8>"
            f"<style>html,body{{margin:0;padding:0;background:{NAVY}}}"
            f"svg{{display:block;width:{W}px;height:{H}px}}</style>{svg}",
            encoding="utf-8",
        )
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", f"--force-device-scale-factor={scale}",
            "--virtual-time-budget=6000", f"--window-size={W},{H}",
            f"--screenshot={out}", f"--user-data-dir={tdp / 'cr'}",
            page.as_uri(),
        ]
        # Chrome writes the screenshot BEFORE it sometimes hangs on exit, so cap
        # the wait and check for the file rather than trust a clean exit (same
        # handling as chart_render.rasterize_svg and scripts/make_favicon.py).
        try:
            subprocess.run(cmd, timeout=60, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-9", "-f", str(tdp / "cr")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)
        if not out.exists():
            raise RuntimeError("Chrome produced no screenshot")
        data = out.read_bytes()
        if not data.startswith(b"\x89PNG"):
            raise RuntimeError("Chrome output was not a PNG")
        return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="site/assets/landing")
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    svg = build_svg(font_face_css(REPO / ".cache" / "launch_card_fonts"))
    png_path = out_dir / "x_launch_card.png"
    png_path.write_bytes(rasterize(svg, scale=args.scale))
    print(f"wrote {png_path} ({png_path.stat().st_size / 1024:.0f} KB, "
          f"{W * args.scale}x{H * args.scale})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
