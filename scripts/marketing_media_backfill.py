"""scripts/marketing_media_backfill.py — republish outbox chart images to R2.

WHY THIS EXISTS. A marketing post attaches a chart only when its outbox item
carries a PUBLIC https `media_url`: Buffer hosts no uploads, so the local
repo path is useless to it (scripts/marketing_publisher._media_paths_for skips
any non-http path). That URL is stamped exactly once, inside the nightly's
content_studio build, and ONLY if R2 creds were present in that process. Miss
that window — R2 hiccup, a build run outside Actions, creds not plumbed into a
lane — and the day's posts are permanently text-only. There was no way back:
the SVGs are committed but the PNGs are gitignored and the stamp never re-runs.

This is the way back. It walks the outbox for media entries with no public URL,
rebuilds the PNG from the COMMITTED SVG, uploads it to the same R2 key
content_studio would have used, and records the resulting URL in an append-only
sidecar the publisher reads as a fallback.

    # what is missing a URL (no network, no writes)
    python -m scripts.marketing_media_backfill --dry-run

    # rebuild + upload today's, then commit the sidecar
    R2_ENDPOINT=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=... \
        python -m scripts.marketing_media_backfill --as-of 2026-07-28

WHY A SIDECAR AND NOT AN items.jsonl REWRITE. items.jsonl is append-only and
outbox.fold_state keeps the FIRST row per id, so an appended "corrected" item is
silently ignored — the only way to stamp in place is a full-file rewrite, which
races the nightly and the publish sweeps that append to it concurrently. The
sidecar (data/marketing/outbox/media_urls.jsonl) is append-only like every other
ledger here, carries merge=union in .gitattributes, and is read last-row-wins so
a re-run simply supersedes. The item itself is never touched.

Fail-soft throughout (mirrors outbox.py / social_publisher.py): a chart that
cannot be rasterized or uploaded is REPORTED and skipped, never fatal — a
partial backfill is strictly better than none, and the post degrades to
text-only exactly as it does today.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:
    sys.path.insert(0, _CODE_ROOT)

log = logging.getLogger("marketing_media_backfill")

# Sidecar filename, relative to the outbox dir. Kept beside the other ledgers so
# the publish workflow's `git add data/marketing/outbox` already stages it.
SIDECAR_NAME = "media_urls.jsonl"


def _repo_root() -> Path:
    return Path(_CODE_ROOT)


def sidecar_path(root: Path | str | None = None) -> Path:
    r = Path(root) if root is not None else _repo_root()
    return r / "data" / "marketing" / "outbox" / SIDECAR_NAME


def load_sidecar(root: Path | str | None = None) -> dict[str, str]:
    """{as_of/chart_id: media_url} folded LAST-row-wins.

    Last-row-wins on purpose: a re-upload (new bucket, corrected render) must be
    able to supersede an earlier row without rewriting the file. Rows missing a
    key or url are skipped — a malformed row must never poison the map.
    """
    from engine.marketing.ledgers import read_jsonl  # noqa: PLC0415

    out: dict[str, str] = {}
    for row in read_jsonl(sidecar_path(root)):
        key = str(row.get("key") or "").strip()
        url = str(row.get("media_url") or "").strip()
        if key and url.lower().startswith(("http://", "https://")):
            out[key] = url
    return out


def media_key(as_of: str, chart_id: str) -> str:
    """Sidecar lookup key. Distinct from the R2 object key so the sidecar stays
    readable if the R2 prefix ever changes."""
    return f"{str(as_of or '').strip()}/{str(chart_id or '').strip()}"


def r2_key_for(as_of: str, chart_id: str, png_bytes: bytes) -> str:
    """CONTENT-ADDRESSED R2 key: .../<as_of>/<chart_id>-<sha8>.png.

    NOT media_publish.chart_key(). chart_id is a per-BUILD counter, not an
    identity: rebuild a day and `chart-001` means a different ticker than it did
    that morning. content_studio's key would then have this backfill PUT the new
    render over the object an already-stamped item points at — the older post
    keeps its URL and silently starts attaching someone else's chart. (Real
    collision, 2026-07-28: chart-001 was EQT to the nightly and CBOE to the
    rebuild; chart-002 was ROST and SONO.) Hashing the bytes makes the clobber
    structurally impossible, keeps re-runs idempotent, and still lets two items
    with a byte-identical card share one object.
    """
    import hashlib

    from engine.marketing import media_publish  # noqa: PLC0415

    digest = hashlib.sha256(png_bytes).hexdigest()[:8]
    safe_as_of = (str(as_of or "").strip() or "unknown").replace("/", "-")
    safe_id = (str(chart_id or "").strip() or "chart").replace("/", "-")
    return f"{media_publish.R2_MARKETING_PREFIX}/{safe_as_of}/{safe_id}-{digest}.png"


def _older_than(as_of: object, max_age_days: int, today: date | None = None) -> bool:
    """Is this item's as_of further back than the age bound? Unparseable → False.

    Fail-OPEN on a bad date (treat it as in range): dropping an item because its
    date did not parse would silently shrink the recovery set, which is the one
    thing this script exists not to do.
    """
    try:
        parts = str(as_of or "")[:10].split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:  # noqa: BLE001
        return False
    return ((today or date.today()) - d).days > max_age_days


def _iter_missing(items: list[dict], as_of: str | None,
                  max_age_days: int | None = None,
                  today: date | None = None) -> list[tuple[dict, dict]]:
    """[(item, media_entry)] for every media entry with no public media_url.

    An entry that already carries an http(s) media_url is left alone — this
    script only ever fills a hole, it never re-uploads a working image.

    `max_age_days` bounds the sweep, and exists because this lane got a SCHEDULE
    (2026-07-30). A hole that could not be filled is retried on every run
    forever: the sidecar records successes, so a chart whose SVG is missing or
    unrasterizable is permanently in `missing` and permanently re-attempted. That
    is harmless once and unbounded growth on a cron. A chart older than the bound
    is not recoverable in any useful sense anyway — its post's slot is long gone.
    None = no bound.

    AN EXPLICIT `as_of` OVERRIDES THE BOUND. Asking for a specific date IS the
    statement that the date is wanted, so combining the two must not silently
    return nothing — an operator rescuing a week-old day would run the lane,
    watch it report "0 to publish", and reasonably conclude the outbox was
    already clean. The bound exists to stop an UNATTENDED sweep chasing dead
    history, and a named date is not unattended.
    """
    out: list[tuple[dict, dict]] = []
    bound = None if as_of else max_age_days
    for it in items:
        if as_of and str(it.get("as_of") or "") != as_of:
            continue
        if bound is not None and _older_than(it.get("as_of"), bound, today):
            continue
        for m in it.get("media") or []:
            if not isinstance(m, dict):
                continue
            url = str(m.get("media_url") or "").strip()
            if url.lower().startswith(("http://", "https://")):
                continue
            out.append((it, m))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None,
                    help="Only items with this as_of date (default: every item).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what is missing; no rasterize, no upload, no write.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Stop after N uploads (0 = no limit).")
    ap.add_argument("--max-age-days", type=int, default=None,
                    help="Ignore items older than N days (default: no bound). "
                         "The scheduled lane passes this so an unfillable hole "
                         "is not re-attempted forever; a manual --as-of rescue "
                         "of an older date is unaffected.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)

    root = _repo_root()
    from engine.marketing import media_publish  # noqa: PLC0415
    from engine.marketing.ledgers import append_jsonl, read_jsonl  # noqa: PLC0415

    items = read_jsonl(root / "data" / "marketing" / "outbox" / "items.jsonl")
    missing = _iter_missing(items, args.as_of, args.max_age_days)
    already = load_sidecar(root)

    # Dedup by R2 key: several items legitimately share one chart_id (the same
    # card reused across a day), and re-uploading identical bytes per item is
    # pure waste. Ordered so the report reads chronologically.
    todo: dict[str, dict] = {}
    for it, m in missing:
        as_of = str(it.get("as_of") or "")
        chart_id = str(m.get("chart_id") or "")
        if not as_of or not chart_id:
            log.warning("skip media entry with no as_of/chart_id on item %s", it.get("id"))
            continue
        k = media_key(as_of, chart_id)
        if k in already:
            continue          # a previous run already published this one
        spec = {"as_of": as_of, "chart_id": chart_id,
                "svg_path": str(m.get("path") or ""),
                "png_path": str(m.get("media_png_path") or "")}
        prior = todo.get(k)
        if prior is not None:
            # The sidecar is a flat as_of/chart_id map, so two UNSTAMPED items
            # sharing a chart_id but pointing at different artwork cannot both be
            # recorded — one would silently inherit the other's chart. Same
            # per-build-counter root cause as the R2 clobber r2_key_for guards
            # (chart_id is not an identity). Publish the first, say so, and leave
            # the second text-only: a missing image beats a wrong one.
            if prior["svg_path"] != spec["svg_path"]:
                print(f"::warning title=media-backfill-chart-id-collision::"
                      f"{k} names two different charts ({prior['svg_path']} and "
                      f"{spec['svg_path']}); publishing the first, second stays "
                      f"text-only", flush=True)
            continue
        todo[k] = spec

    log.info("outbox: %d items, %d media entries lack a public URL, %d already in the "
             "sidecar, %d distinct charts to publish",
             len(items), len(missing), len(already), len(todo))

    if args.dry_run:
        for k, spec in todo.items():
            print(f"WOULD PUBLISH {k}  svg={spec['svg_path']}")
        return 0

    published = failed = 0
    for k, spec in todo.items():
        if args.limit and published >= args.limit:
            log.info("limit %d reached — stopping", args.limit)
            break

        # Prefer a PNG already on disk (the nightly wrote one even when the
        # upload no-opped); fall back to re-rasterizing the committed SVG. The
        # PNG is gitignored, so in CI the SVG path is the one that fires.
        png_bytes = b""
        png_path = root / spec["png_path"] if spec["png_path"] else None
        if png_path and png_path.is_file():
            png_bytes = png_path.read_bytes()
        if not png_bytes:
            svg_path = root / spec["svg_path"] if spec["svg_path"] else None
            if not svg_path or not svg_path.is_file():
                log.warning("%s: no PNG on disk and no committed SVG (%s) — skipping",
                            k, spec["svg_path"] or "<none>")
                failed += 1
                continue
            from engine.marketing.chart_render import rasterize_svg  # noqa: PLC0415
            png_bytes = rasterize_svg(svg_path.read_text(encoding="utf-8"))
            if not png_bytes:
                log.warning("%s: rasterize produced no bytes (no Chrome? timeout?) "
                            "— skipping", k)
                failed += 1
                continue

        r2_key = r2_key_for(spec["as_of"], spec["chart_id"], png_bytes)
        url = media_publish.publish_chart_png(png_bytes, r2_key)
        if not url:
            log.warning("%s: upload returned no URL — skipping", k)
            failed += 1
            continue

        if not append_jsonl(sidecar_path(root),
                            {"key": k, "as_of": spec["as_of"],
                             "chart_id": spec["chart_id"], "media_url": url}):
            log.warning("%s: uploaded but the sidecar append FAILED — the image is "
                        "live in R2 but the publisher will not find it", k)
            failed += 1
            continue
        published += 1
        log.info("%s → %s", k, url)

    # Line-start annotation, bare print, flushed: a logger would prefix it and
    # GitHub would drop it (see CLAUDE.md).
    print(f"::notice title=marketing-media-backfill::published={published} "
          f"failed={failed} already={len(already)}", flush=True)
    log.info("backfill complete | published=%d failed=%d", published, failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
