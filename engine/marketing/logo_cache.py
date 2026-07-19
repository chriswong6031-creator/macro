"""engine.marketing.logo_cache — Company logo whitening + caching for chart overlays.

Public API:
    white_logo_datauri(ticker, root, *, fetch=True, max_px=420) -> str | None
    cached_only(ticker, root) -> str | None

Treatment: fetch the nvstly/icons CDN PNG, convert every non-transparent pixel to
pure white (preserving alpha). This is the TrendSpider monochrome-overlay treatment.
Cached in data/marketing/logos/<TICKER>_white.png after first fetch.

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
