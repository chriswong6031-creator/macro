"""engine.marketing.logo_cache — Company logo whitening + caching for chart overlays.

Public API:
    white_logo_datauri(ticker, root, *, fetch=True, max_px=420) -> str | None
    cached_only(ticker, root) -> str | None
    color_logo_datauri(ticker, root, *, fetch=True, max_px=256) -> str | None
    cached_only_color(ticker, root) -> str | None
    relative_luminance(r, g, b) -> float           (WCAG 2.x sRGB)
    contrast_ratio(lum_a, lum_b) -> float          (WCAG 2.x)
    mark_legible_fraction(png_bytes, plate_hexes, *, min_ratio=3.0) -> float | None

Two treatments, two caches, one CDN source (nvstly/icons):
  - WHITE: every non-transparent pixel → pure white (preserving alpha). The
    TrendSpider monochrome chart-watermark look. Cached as <TICKER>_white.png.
  - COLOR: the ORIGINAL full-color RGBA icon, only downscaled — for avatar chips
    where the brand hue is the point. Cached as <TICKER>_color.png.

The whitening is deliberate (chart watermarks); the color path never touches
that pipeline or its cache — they are independent by file suffix.

WHAT THE SOURCE SET ACTUALLY IS (measured 2026-08-03, defect: invisible logos on
the live watchlist card). nvstly/icons is a DARK-THEME icon set: a large share of
its marks are pure-white-on-transparent knockouts authored to sit on a dark chart
background. Over a 70-ticker sample fetched straight from the CDN, 36 of 70 (51%)
of the marks put LESS THAN HALF of their ink above a 3:1 contrast ratio against a
near-white backplate; 16 of them measured mean relative luminance 1.000 — i.e.
literally every opaque pixel is pure white (COHR, AXON, RBLX, AAPL, UNH, V, PLTR,
BA, IBM, LMT, PM, BLK, ABBV, UBER, LITE≈0.97, INTC≈0.97). "Full-colour icon" is
therefore NOT a synonym for "has a visible hue" — a third of this set is a white
silhouette, and a consumer that assumes otherwise renders a blank chip.

That is a property of the source, so the measurement of it belongs here next to
the pixel code, and every consumer that mounts one of these marks on a surface
must decide the surface FROM the measurement rather than from an assumption.
`mark_legible_fraction` is that measurement.

Never raises — fail-soft None on any error.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path


_CDN = "https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/{ticker}.png"
_TIMEOUT = 6

# Alpha above which a pixel counts as "ink" the eye has to resolve. Below this the
# pixel is effectively transparent and contributes nothing to legibility, so
# including it would let a huge transparent margin dilute (or flatter) the score.
_INK_ALPHA = 40

# sRGB → linear-light lookup, WCAG 2.x §relative luminance. Built once at import
# (256 entries) so a per-pixel scan is three list indexes, not three pow() calls.
_SRGB_LINEAR: tuple[float, ...] = tuple(
    (c / 255.0) / 12.92 if (c / 255.0) <= 0.04045
    else (((c / 255.0) + 0.055) / 1.055) ** 2.4
    for c in range(256)
)


def _cache_path(ticker: str, root: Path) -> Path:
    return root / "data" / "marketing" / "logos" / f"{ticker.upper()}_white.png"


def _color_cache_path(ticker: str, root: Path) -> Path:
    return root / "data" / "marketing" / "logos" / f"{ticker.upper()}_color.png"


def _to_datauri(img_bytes: bytes) -> str:
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _whiten(png_bytes: bytes, max_px: int = 420) -> bytes | None:
    """Convert PNG: every pixel with alpha > 8 → pure white, preserve alpha.

    Returns PNG bytes or None on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        # Downscale to max_px wide (maintain aspect ratio)
        w, h = img.size
        if w > max_px:
            new_h = int(h * max_px / w)
            img = img.resize((max_px, new_h), Image.LANCZOS)
        # Whiten: for each pixel, if alpha > 8 → set RGB to white
        pixels = img.load()
        width, height = img.size
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a > 8:
                    pixels[x, y] = (255, 255, 255, a)
        # Save to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _downscale(png_bytes: bytes, max_px: int = 256) -> bytes | None:
    """Downscale a PNG to *max_px* wide, preserving the ORIGINAL RGBA colors.

    The color-avatar mirror of _whiten: same decode/resize path, but the pixels
    are left untouched — the brand hue and transparency are the whole point.
    Returns PNG bytes or None on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        w, h = img.size
        if w > max_px:
            new_h = int(h * max_px / w)
            img = img.resize((max_px, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def white_logo_datauri(
    ticker: str,
    root: Path | str,
    *,
    fetch: bool = True,
    max_px: int = 420,
) -> str | None:
    """Return a data: URI for the whitened company logo, or None.

    Checks cache first. If absent and fetch=True, fetches from nvstly CDN,
    whitens, caches, and returns URI. Deterministic once cached.

    Never raises.
    """
    try:
        root = Path(root)
        cpath = _cache_path(ticker, root)
        if cpath.exists():
            return _to_datauri(cpath.read_bytes())
        if not fetch:
            return None
        # Fetch from CDN
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError:
            return None
        url = _CDN.format(ticker=ticker.upper())
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
        except Exception:  # noqa: BLE001
            return None
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("content-type", "")
        if "image" not in ctype:
            return None
        white_bytes = _whiten(resp.content, max_px=max_px)
        if white_bytes is None:
            return None
        # Cache
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_bytes(white_bytes)
        return _to_datauri(white_bytes)
    except Exception:  # noqa: BLE001
        return None


def cached_only(ticker: str, root: Path | str) -> str | None:
    """Return data URI from cache only — no network. Returns None if not cached."""
    return white_logo_datauri(ticker, root, fetch=False)


def color_logo_datauri(
    ticker: str,
    root: Path | str,
    *,
    fetch: bool = True,
    max_px: int = 256,
) -> str | None:
    """Return a data: URI for the ORIGINAL full-color company logo, or None.

    The color mirror of white_logo_datauri: same cache-first / fetch-if-absent /
    deterministic-once-cached contract, but the icon keeps its brand hue and
    transparency (only downscaled). Cached as <TICKER>_color.png — a file
    independent from the whitened cache, so the two treatments never collide.

    Never raises.
    """
    try:
        root = Path(root)
        cpath = _color_cache_path(ticker, root)
        if cpath.exists():
            return _to_datauri(cpath.read_bytes())
        if not fetch:
            return None
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError:
            return None
        url = _CDN.format(ticker=ticker.upper())
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
        except Exception:  # noqa: BLE001
            return None
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("content-type", "")
        if "image" not in ctype:
            return None
        color_bytes = _downscale(resp.content, max_px=max_px)
        if color_bytes is None:
            return None
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_bytes(color_bytes)
        return _to_datauri(color_bytes)
    except Exception:  # noqa: BLE001
        return None


def cached_only_color(ticker: str, root: Path | str) -> str | None:
    """Return color data URI from cache only — no network. None if not cached."""
    return color_logo_datauri(ticker, root, fetch=False)


# ─────────────────────────────────────────────────────────────────────────────
# Legibility measurement — "can this mark actually be seen on that surface?"
#
# WHY THIS EXISTS (defect, live 2026-08-03): the watchlist share card mounted every
# fetched mark on ONE fixed near-white avatar disc, on the assumption that a
# "full-colour" icon has a hue dark enough to read against it. Half this source set
# is a white knockout (see module docstring), so half the rows shipped a blank
# white circle where a logo belonged — COHR / LITE / AXON / RBLX went out on the
# flagship as literally-invisible marks at contrast ratio 1.00:1.
#
# The lesson generalises past that one card: a backplate under a third-party mark
# is not a style choice, it is a contrast decision, and a contrast decision has to
# be COMPUTED from the mark's own pixels. These three functions are that
# computation, kept in the module that already owns the pixel domain so no
# consumer has to re-derive WCAG from scratch (and get it wrong).
# ─────────────────────────────────────────────────────────────────────────────

def relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG 2.x relative luminance of an 8-bit sRGB triple, in [0, 1].

    Deliberately the real linearised formula, not the naive 0.2126*r/255 weighted
    average: the naive form overstates the luminance of dark saturated brand inks
    (a mid-blue mark reads far darker to the eye than its raw byte value), which is
    exactly the region where a plate decision flips. Getting this wrong would keep
    dark marks on dark plates.
    """
    return (
        0.2126 * _SRGB_LINEAR[r & 0xFF]
        + 0.7152 * _SRGB_LINEAR[g & 0xFF]
        + 0.0722 * _SRGB_LINEAR[b & 0xFF]
    )


def contrast_ratio(lum_a: float, lum_b: float) -> float:
    """WCAG 2.x contrast ratio between two relative luminances. 1.0 … 21.0."""
    hi, lo = (lum_a, lum_b) if lum_a >= lum_b else (lum_b, lum_a)
    return (hi + 0.05) / (lo + 0.05)


def _hex_luminance(hex_color: str) -> float:
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return relative_luminance(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mark_legible_fraction(
    png_bytes: bytes,
    plate_hexes: "list[str] | tuple[str, ...]",
    *,
    min_ratio: float = 3.0,
) -> float | None:
    """Fraction of a mark's ink that clears *min_ratio* against a plate, in [0, 1].

    Args:
        png_bytes: the raw PNG of the brand mark (RGBA; transparency expected).
        plate_hexes: EVERY colour the plate takes underneath the mark — for a
            gradient chip that means both stops, not the average. A pixel must
            clear the ratio against the WORST of them, so a mark can never be
            scored legible on the strength of the friendlier half of a gradient.
        min_ratio: the contrast floor. Default 3.0 = WCAG 2.1 SC 1.4.11
            (non-text contrast), the published floor for graphical objects whose
            shape has to be identifiable. A logo is exactly that object: nobody
            reads it, they recognise its silhouette, so the text floors (4.5/3.0
            by size) do not apply and 3:1 is the right published minimum to cite.

    Returns:
        The fraction of ink pixels clearing the floor, or **None** when the mark
        cannot be measured at all (Pillow absent, undecodable bytes, or an image
        with no ink). None means "unknown", never "illegible" — callers must not
        collapse the two, because an unmeasurable mark still has to be drawn
        somewhere sensible rather than thrown away.

    Never raises.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    try:
        plate_lums = [_hex_luminance(h) for h in (plate_hexes or ())]
        if not plate_lums:
            return None
        # Scanning at native size is ~62k pixels per mark; the score is a
        # PROPORTION, so a bounded thumbnail carries the same answer for a
        # fraction of the work. BILINEAR (not NEAREST) so hairline strokes in a
        # wordmark survive the downscale instead of being sampled away — a
        # dropped stroke would bias the proportion toward whatever fills the
        # background of the mark.
        if max(img.size) > 96:
            w, h = img.size
            scale = 96.0 / max(w, h)
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR
            )
        # .tobytes() rather than .getdata(): getdata() is deprecated for removal in
        # Pillow 14 and its replacement does not exist on older Pillow, so the raw
        # RGBA buffer is the form that works on every version in the fleet.
        buf = img.tobytes()
        ink = 0
        clears = 0
        for i in range(0, len(buf), 4):
            if buf[i + 3] <= _INK_ALPHA:
                continue
            ink += 1
            lum = relative_luminance(buf[i], buf[i + 1], buf[i + 2])
            worst = min(contrast_ratio(lum, pl) for pl in plate_lums)
            if worst >= min_ratio:
                clears += 1
        if ink == 0:
            return None
        return clears / ink
    except Exception:  # noqa: BLE001
        return None
