"""engine.marketing.logo_cache — Company logo whitening + caching for chart overlays.

Public API:
    white_logo_datauri(ticker, root, *, fetch=True, max_px=420) -> str | None
    cached_only(ticker, root) -> str | None
    color_logo_datauri(ticker, root, *, fetch=True, max_px=256) -> str | None
    cached_only_color(ticker, root) -> str | None

Two treatments, two caches, one CDN source (nvstly/icons):
  - WHITE: every non-transparent pixel → pure white (preserving alpha). The
    TrendSpider monochrome chart-watermark look. Cached as <TICKER>_white.png.
  - COLOR: the ORIGINAL full-color RGBA icon, only downscaled — for avatar chips
    where the brand hue is the point. Cached as <TICKER>_color.png.

The whitening is deliberate (chart watermarks); the color path never touches
that pipeline or its cache — they are independent by file suffix.

Never raises — fail-soft None on any error.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path


_CDN = "https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/{ticker}.png"
_TIMEOUT = 6


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
