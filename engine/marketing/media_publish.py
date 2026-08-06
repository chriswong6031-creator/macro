"""engine.marketing.media_publish — publish marketing chart PNGs to R2.

Buffer hosts no uploads: to attach a chart to an X post the PNG must live at a
publicly reachable https URL. This module puts a rendered PNG into the SAME R2
data plane every build_* script already reads publicly
(config.yml r2_data_plane.public_base → https://pub-…​.r2.dev), under a
`marketing/charts/<as_of>/<chart_id>.png` key, and returns that public URL.

DARK BY DEFAULT / fail-soft (mirrors scripts/publish_r2.py + social_publisher):
  * R2_* creds absent  → publish_chart_png returns None + one log line (no raise).
  * boto3 missing / any upload error → None + log.warning.
The caller (content_studio) writes the PNG to a local repo path regardless, so a
None here just means "no public URL this run" — the post degrades to text-only.

We invent NO new bucket and touch NO ACLs: the object rides the existing public
data plane. The operator arms this by providing the same R2_ENDPOINT /
R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET the oracle/data lanes use.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# R2 key prefix for marketing chart images (public data plane).
R2_MARKETING_PREFIX = "marketing/charts"

# Fallback public base if config.yml lacks r2_data_plane.public_base. This is the
# same bucket domain every build_* script hard-codes (build_flow_enrich.py,
# build_chain_heat.py, build_prophet_marks.py, audit_r2.py).
_DEFAULT_PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"


def _public_base() -> str:
    """Resolve the R2 public base URL (no trailing slash). Config → fallback const."""
    base = ""
    try:
        from lib import config  # noqa: PLC0415
        base = str(config.load().get("r2_data_plane", {}).get("public_base", "") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: config public_base read failed (%s) — fallback", exc)
    return (base or _DEFAULT_PUBLIC_BASE).rstrip("/")


def _r2_client():
    """S3 client for R2, or None when creds are absent. Mirrors publish_r2._client()."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kw: dict[str, Any] = dict(
            region_name="auto", signature_version="s3v4",
            max_pool_connections=8, retries={"max_attempts": 4, "mode": "standard"},
            connect_timeout=15, read_timeout=60)
        try:  # newer botocore: keep R2 happy (it rejects the default CRC32 trailer)
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except ImportError:
        log.warning("media_publish: boto3 not installed — cannot upload chart PNG")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: R2 client init failed: %s", exc)
        return None


def chart_key(as_of: str, chart_id: str) -> str:
    """The R2 key for a chart PNG: marketing/charts/<as_of>/<chart_id>.png."""
    safe_as_of = (str(as_of or "").strip() or "unknown").replace("/", "-")
    safe_id = (str(chart_id or "").strip() or "chart").replace("/", "-")
    return f"{R2_MARKETING_PREFIX}/{safe_as_of}/{safe_id}.png"


def public_url_for_key(key: str) -> str:
    """The public https URL a given R2 key resolves to on the data plane."""
    return f"{_public_base()}/{key.lstrip('/')}"


def publish_chart_png(png_bytes: bytes, key: str, *, s3=None) -> str | None:
    """Upload PNG bytes to R2 under `key`; return the public https URL or None.

    Fail-soft: creds absent (no client) → None + log line; any upload error →
    None + log.warning. `s3` may be injected for tests (a stub with put_object).
    Content-Type is image/png. `key` is the full R2 key (see chart_key()).
    """
    if not png_bytes:
        log.warning("media_publish: empty png_bytes for key %s — skip", key)
        return None

    client = s3 if s3 is not None else _r2_client()
    if client is None:
        log.info("media_publish: no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY"
                 "/R2_BUCKET) — chart PNG stays local (no public URL this run)")
        return None

    bucket = os.environ.get("R2_BUCKET", "").strip()
    if not bucket:
        log.warning("media_publish: R2_BUCKET not set — cannot upload %s", key)
        return None

    try:
        client.put_object(Bucket=bucket, Key=key, Body=png_bytes,
                          ContentType="image/png")
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: upload failed for %s: %s", key, exc)
        return None

    url = public_url_for_key(key)
    log.info("media_publish: uploaded chart PNG → %s (%d bytes)", url, len(png_bytes))
    return url


def publish_card(
    svg: str,
    *,
    chart_id: str,
    as_of: str,
    root: "Any" = None,
    legacy_png: "Any" = None,
) -> dict:
    """Persist ONE chart card (SVG + its PNG raster) and publish the PNG to R2.

    This is the single seam every lane goes through so the POSTED image is always
    a raster of the SAME SVG the Content Studio preview shows. Before the
    2026-07-26 incident each lane rastered its own lookalike and they drifted:
    the preview promised the full candlestick card with the mastermind-x.com
    footer + "Try Pro free for 7 days" button, the account posted a bare line
    chart with neither. One seam, one renderer, no drift.

    Writes:
      data/marketing/outbox/media/<as_of>/<chart_id>.svg   (the artifact/preview)
      data/marketing/outbox/media/<as_of>/<chart_id>.png   (what X actually gets)

    legacy_png: optional zero-arg callable returning PNG bytes, used ONLY when no
    Chrome is available to raster the SVG (CI, the ubuntu publish runner). A
    missing rasteriser must degrade the image, never drop the post.

    Returns {svg_path, media_png_path, media_url, media_render} — any of which
    may be None/absent. NEVER raises: a card that cannot be written leaves the
    post text-only rather than failing the run.
    """
    from pathlib import Path as _Path  # noqa: PLC0415

    out: dict[str, Any] = {}
    if not svg or not chart_id:
        return out

    repo_root = _Path(root) if root is not None else _Path(__file__).resolve().parents[2]
    media_dir = repo_root / "data" / "marketing" / "outbox" / "media" / str(as_of)
    rel_svg = f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"
    rel_png = f"data/marketing/outbox/media/{as_of}/{chart_id}.png"

    # ── SVG (the artifact the admin preview renders) ──────────────────────────
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        svg_path = media_dir / f"{chart_id}.svg"
        tmp = svg_path.with_suffix(".svg.tmp")
        tmp.write_text(svg, encoding="utf-8")
        tmp.replace(svg_path)
        out["svg_path"] = rel_svg
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_card: SVG write failed for %s: %s", chart_id, exc)

    # ── PNG (what X actually receives) ────────────────────────────────────────
    png = b""
    render_mode = "svg_raster"
    # RETRY ONCE BEFORE ACCEPTING A WORSE PICTURE (2026-07-30).
    #
    # A fallback is one failed launch away, and the fallback is a visibly worse
    # image — no candles, no indicators, no footer CTA — on a live account.
    #
    # Measured on this host: a card rasters in 3 to 4 seconds when asked on its
    # own, and 15 of 23 took the fallback on a local plan build competing with
    # other Chrome work. Production's own PNGs are all the real card (2026-07-29:
    # 21 of 21 at 2000x1760), so this is contention, not an absent binary — the
    # exact failure a retry is for, and the exact failure a single attempt turns
    # into a permanently worse picture.
    #
    # rasterize_svg is deterministic, writes only inside its own temp dir and is
    # already fail-soft, so a second attempt is safe and idempotent. It costs
    # nothing on the happy path and is only paid where the alternative was
    # shipping the degraded card anyway. Bounded at ONE retry: if Chrome is
    # genuinely missing (CI, the ubuntu publish runner) this must not turn every
    # card into two doomed launches.
    for _attempt in (1, 2):
        try:
            from engine.marketing.chart_render import rasterize_svg  # noqa: PLC0415
            png = rasterize_svg(svg)
        except Exception as exc:  # noqa: BLE001
            log.warning("publish_card: raster attempt %d failed for %s: %s",
                        _attempt, chart_id, exc)
        if png:
            break
        if _attempt == 1:
            from engine.marketing.chart_render import find_chrome  # noqa: PLC0415
            if not find_chrome():
                break      # no binary — a retry cannot help, and would double the cost
            log.warning("publish_card: raster produced nothing for %s — retrying "
                        "once before accepting the degraded legacy PNG", chart_id)
    if not png and legacy_png is not None:
        log.warning("publish_card: no SVG raster for %s — falling back to the legacy "
                    "PNG (no footer CTA); install Chrome on this host", chart_id)
        try:
            png = legacy_png() or b""
            render_mode = "legacy_png"
        except Exception as exc:  # noqa: BLE001
            log.warning("publish_card: legacy PNG failed for %s: %s", chart_id, exc)
            png = b""
    if not png:
        return out

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        png_path = media_dir / f"{chart_id}.png"
        # Deterministic bytes → idempotent; overwrite is safe.
        tmp = png_path.with_suffix(".png.tmp")
        tmp.write_bytes(png)
        tmp.replace(png_path)
        out["media_png_path"] = rel_png
        out["media_render"] = render_mode
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_card: PNG write failed for %s: %s", chart_id, exc)
        return out

    # ── Public URL (Buffer hosts no uploads; absent creds → text-only post) ───
    try:
        out["media_url"] = publish_chart_png(png, chart_key(str(as_of), str(chart_id)))
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_card: upload failed for %s: %s", chart_id, exc)
        out["media_url"] = None
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Card/ticker agreement — the last thing between a wrong chart and a live post
# ─────────────────────────────────────────────────────────────────────────────
#
# THE DEFECT (live, flagship, 2026-08-05). A post reading "$DVN 45.1. Signals are
# lining up..." shipped with a chart of RMBS. The outbox item was RIGHT (ticker
# DVN, chart-088); the FILE at that id was another company's. `chart_id` is the
# whole storage key — this module writes <as_of>/<chart_id>.svg and uploads the
# PNG to the matching public path — and content_studio's id counter restarted at
# 1 every run, so the second run of a day overwrote the first run's charts at the
# same paths and the same URLs. content_studio._next_chart_id now makes the day's
# namespace append-only, which stops NEW collisions.
#
# This is the other half, and the half the operator actually asked for: "if
# someone didn't catch this then we wouldn't even know". A reader caught it. An
# audit of every single-ticker card since 08-01 then found a second one nobody
# had: 08-01, meagan, $AMCR posted over an AMZN chart. Two live posts, one
# noticed. So the pipeline needs a check that SEES this, not just a fix that
# prevents the known cause — the next cause will be different.
#
# THE TEST IS "DOES THE CLAIMED TICKER APPEAR", not "what ticker is this chart".
# Deliberate: several renderers draw the symbol differently (v2 header text, the
# ghost watermark, the signal-chart label), so picking THE ticker out of the
# markup is a guess that would quarantine good posts when a renderer changes.
# Presence is unambiguous, and it is exactly what fails in the real defect: DVN
# appears nowhere in an RMBS chart.

#: Text that is drawn on cards and is not a symbol. Kept small on purpose — the
#: check only has to avoid claiming a card names a ticker it does not.
#: A word left OUT of this set cannot create a false NEGATIVE, but it can create
#: a false POSITIVE: a card whose only ticker-shaped token is an unlisted label
#: reads as "names a symbol, and not the claimed one" and would quarantine a good
#: post. So pills and axis labels belong here. `SETUP` is the live example — the
#: v2 chart draws a SETUP pill, and without it a card that labels nothing else
#: would fire.
_CARD_TEXT_NOISE = frozenset({
    "MASTERMIND", "DAILY", "WEEKLY", "AI", "POC", "SMA", "EMA", "MACD", "RSI",
    "VOL", "ATR", "HIGH", "LOW", "OPEN", "CLOSE", "PRO", "FREE", "TRY", "NEW",
    "SETUP", "ENTRY", "STOP", "TARGET", "BUY", "SELL", "HOLD", "LONG", "SHORT",
    "GAP", "AVG", "YTD", "EPS", "PE", "IV", "OI", "USD", "ETF", "NA", "TBD",
})


def card_symbols(svg_text: str) -> set[str]:
    """Every ticker-shaped token this card DRAWS. Empty when it names none.

    TEXT NODE contents only, so a symbol inside an attribute, a URL or the footer
    link cannot vouch for a card. Punctuation-normalised, because a card may draw
    `BRK.B` where the item says `BRK-B`.
    """
    import re  # noqa: PLC0415

    out = set()
    for node in re.findall(r">([A-Z][A-Z0-9.\-]{1,5})<", str(svg_text or "")):
        tok = re.sub(r"[^A-Z0-9]", "", node)
        if tok and tok not in _CARD_TEXT_NOISE:
            out.add(tok)
    return out


def card_ticker_mismatch(media: list[dict] | None, *, root: Any = None) -> str | None:
    """Reason string when a card contradicts the ticker its item claims; None if OK.

    Only SINGLE-name cards are judged. A `tickers` list (sector/theme cards) is
    skipped: those legitimately draw a subset of their members, so absence proves
    nothing and a check that fired on it would be noise.

    THREE WAYS TO ABSTAIN, one way to fire. Absent/unreadable SVG, a card that
    draws NO symbol at all, and a multi-name card are all UNANSWERABLE, not
    evidence — the publish runner is not guaranteed to carry the media tree, and
    a post must never be quarantined because a file was not fetched or because a
    renderer does not label its chart. The check fires only when the card names
    at least one symbol AND the claimed one is not among them, which is exactly
    the live defect: chart-088 names RMBS, the item claimed DVN.
    """
    import re  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    repo_root = _Path(root) if root is not None else _Path(__file__).resolve().parents[2]
    for entry in (media or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("tickers"):
            continue
        ticker = str(entry.get("ticker") or "").strip()
        rel = str(entry.get("path") or "").strip()
        if not ticker or not rel:
            continue
        try:
            svg_text = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue  # absent artifact is not evidence of a mismatch
        drawn = card_symbols(svg_text)
        if not drawn:
            continue  # card labels no symbol; nothing to disagree with
        want = re.sub(r"[^A-Z0-9]", "", ticker.upper())
        if want and want not in drawn:
            return (f"card/ticker mismatch: the item claims {ticker} but "
                    f"{rel} draws {sorted(drawn)}")
    return None
