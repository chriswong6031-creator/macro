#!/usr/bin/env python3
"""scripts/build_levels.py — standalone levels.v1 publisher lane.

Voltick Gamma-Levels program, WP-A2.5 (see
research/VOLTICK_COMPETITIVE_SWEEP_AND_BUILD_PLAN.md §5/§7).

The nightly options-hub builder already publishes the named-level board
(levels/{root}.json) inline, right after each root's gex payload is computed — that
is the production path and it goes live on the next hub run with no new process. This
script is the STANDALONE / BACKFILL lane for the same transform: read one or more
already-computed ``options_hub.gex/v1`` payloads (from the local hub output, or from
R2 with ``--from-r2``), run the pure ``engine.levels_engine`` translation, write
``levels/{root}.json`` locally, and (with ``--publish``) upload them to the R2
``levels/`` plane plus a ``levels/index.json`` manifest.

Pure downstream transform of gex payloads — it reads no options store and computes no
exposure itself, so it is INERT with respect to every deployed lane. Levels are
LOCATIONS where dealer hedging concentrates (positioning, not prophecy); the
dealer-sign passport is inherited verbatim from the gex payload.

Usage:
    python -m scripts.build_levels --roots SPY,QQQ,NVDA           # local gex -> local levels
    python -m scripts.build_levels --roots SPY --from-r2 --publish
    python -m scripts.build_levels --all --publish                # every local gex/*.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_publish import levels_payload_from_gex, LEVELS_PREFIX  # noqa: E402

log = logging.getLogger("build_levels")

# Default local planes (mirror the hub's out_dir layout under data/live_flow_out).
_DEF_GEX_DIR = _REPO / "data" / "live_flow_out" / "options_hub" / "gex"
_DEF_OUT_DIR = _REPO / "data" / "live_flow_out" / "levels"
_R2_GEX_PREFIX = "options_hub/gex/"


# ── R2 helpers (mirrored from scripts/build_options_hub_nightly / live_flow_poller) ──
def _r2_client():
    """Build a boto3 S3 client for Cloudflare R2, or None if creds absent."""
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("R2_ENDPOINT")
    if not (ak and sk and endpoint):
        return None
    try:
        import boto3  # noqa: PLC0415
        return boto3.client(
            "s3", endpoint_url=endpoint,
            aws_access_key_id=ak, aws_secret_access_key=sk, region_name="auto",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("build_levels: R2 client init failed — %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    try:
        s3.upload_file(str(local_path), bucket, r2_key,
                       ExtraArgs={"ContentType": "application/json"})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("build_levels: R2 upload failed for %s — %s", r2_key, e)
        return False


def _download_r2_json(s3, bucket: str, r2_key: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=bucket, Key=r2_key)
        return json.loads(obj["Body"].read())
    except Exception as e:  # noqa: BLE001
        log.warning("build_levels: R2 fetch failed for %s — %s", r2_key, e)
        return None


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def _load_gex(root: str, gex_dir: Path, s3, bucket: str | None,
              from_r2: bool) -> dict | None:
    """Read one root's options_hub.gex/v1 payload, local-first then R2 fallback."""
    local = gex_dir / f"{root}.json"
    if local.exists():
        try:
            return json.loads(local.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("build_levels: bad local gex for %s — %s", root, e)
    if from_r2 and s3 and bucket:
        return _download_r2_json(s3, bucket, f"{_R2_GEX_PREFIX}{root}.json")
    return None


def _resolve_roots(args, gex_dir: Path) -> list[str]:
    if args.roots:
        return [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    if args.all and gex_dir.exists():
        return sorted(p.stem.upper() for p in gex_dir.glob("*.json"))
    return []


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Publish the levels.v1 board from gex payloads.")
    ap.add_argument("--roots", default="", help="comma-separated roots (e.g. SPY,QQQ)")
    ap.add_argument("--all", action="store_true", help="every gex/*.json in the gex dir")
    ap.add_argument("--gex-dir", default=str(_DEF_GEX_DIR), help="local options_hub gex dir")
    ap.add_argument("--out-dir", default=str(_DEF_OUT_DIR), help="local levels output dir")
    ap.add_argument("--from-r2", action="store_true", help="fall back to R2 for missing gex")
    ap.add_argument("--publish", action="store_true", help="upload levels/* to R2")
    ap.add_argument("--colorblind", action="store_true", help="blue/orange palette hint")
    ap.add_argument("--asof", default="", help="asof stamp for the index manifest (no clock here)")
    args = ap.parse_args(argv)

    gex_dir = Path(args.gex_dir)
    out_dir = Path(args.out_dir)
    roots = _resolve_roots(args, gex_dir)
    if not roots:
        log.error("build_levels: no roots (pass --roots or --all with a populated --gex-dir)")
        return 2

    s3 = _r2_client() if (args.publish or args.from_r2) else None
    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    if (args.publish or args.from_r2) and s3 is None:
        log.warning("build_levels: R2 creds absent — running local-only")

    published: list[str] = []
    empty: list[str] = []
    missing: list[str] = []
    for root in roots:
        gex_payload = _load_gex(root, gex_dir, s3, bucket, args.from_r2)
        if gex_payload is None:
            missing.append(root)
            continue
        levels_payload = levels_payload_from_gex(gex_payload, colorblind=args.colorblind)
        if levels_payload is None:
            empty.append(root)
            continue
        levels_path = out_dir / f"{root}.json"
        _write_json(levels_path, levels_payload)
        if args.publish and s3:
            _upload_r2(s3, bucket, levels_path, f"{LEVELS_PREFIX}{root}.json")
        published.append(root)

    # index manifest (asof passed in — this module keeps no clock)
    index = {
        "schema": "levels.index/v1",
        "asof": args.asof or None,
        "roots": published,
        "count": len(published),
        "empty": empty,
        "missing": missing,
    }
    idx_path = out_dir / "index.json"
    _write_json(idx_path, index)
    if args.publish and s3:
        _upload_r2(s3, bucket, idx_path, f"{LEVELS_PREFIX}index.json")

    log.info("build_levels: %d published, %d empty, %d missing (of %d roots)",
             len(published), len(empty), len(missing), len(roots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
