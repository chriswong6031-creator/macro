"""Publish the heavy per-ticker site stores to Cloudflare R2 (S3-compatible).

The daily/asia builds regenerate ~700 MB of per-ticker OHLC + search-library JSON.
Committing that to git bloats the history AND the GitHub-Pages deploy (approaching
Pages' 1 GB limit). Instead we sync those dirs to R2 (zero-egress object storage) and
the browser fetches them from `window.DATA_BASE` (see templates: dataUrl()).

Key layout mirrors the site path: site/ohlc/AAPL.json -> R2 key `ohlc/AAPL.json`, so
the client just prepends DATA_BASE. Content-hash skip (compare local md5 to the R2
ETag) means unchanged files aren't re-uploaded — most daily runs push only the deltas.

Resilient by design: no-op (exit 0) when the R2_* creds are absent, like the other
builders. Reads: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.

Partial-tree invocations MUST pass --no-manifest: the manifest is rebuilt from the
local tree, so a checkout holding only a dir's few git-committed files (the heavy
store is R2-only) would replace the full ~5000-name manifest with a 2-name one —
and bulk consumers prune against it. A guard blocks any manifest that shrinks the
remote list by more than half (--force-manifest overrides for intentional culls).

Usage: python -m scripts.publish_r2 [--dirs ohlc,stockdata,...] [--dry-run]
                                    [--no-manifest] [--force-manifest]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("publish_r2")

# The heavy per-ticker stores that dominate site/ size (see the site-size audit:
# OHLC candles + per-market search libraries + intraday bars). Small shared JSON /
# HTML / JS stays on Pages — only these bulk per-ticker trees move to R2.
DEFAULT_DIRS = [
    "ohlc", "chinaohlc", "hkohlc", "intlohlc", "canadaohlc",
    "subsectorohlc", "subsectorohlc_china", "subsectorohlc_russell", "subsectorohlc_nasdaq",
    "stockdata", "chinastockdata", "hkstockdata", "canadastockdata", "intlstockdata",
    "intraday",
    "feeds",  # machine-consumable contract plane (scripts/build_feeds.py) — small,
              # but R2-only so bulk consumers (Mastermind bot) read ONE data plane
]
_CT = {".json": "application/json", ".js": "application/javascript",
       ".html": "text/html; charset=utf-8", ".csv": "text/csv"}


def _client():
    """S3 client for R2, or None when creds are absent (graceful no-op)."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    import boto3
    from botocore.config import Config
    kw = dict(region_name="auto", signature_version="s3v4",
              max_pool_connections=64, retries={"max_attempts": 4, "mode": "standard"})
    try:  # newer botocore: keep R2 happy (it rejects the default CRC32 trailer)
        cfg = Config(**kw, request_checksum_calculation="when_required",
                     response_checksum_validation="when_required")
    except TypeError:
        cfg = Config(**kw)
    return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                        aws_secret_access_key=sk, config=cfg)


def _md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remote_etags(s3, bucket: str, prefix: str) -> dict:
    """key -> ETag (== md5 for our small single-part objects) already under prefix."""
    out, tok = {}, None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = o["ETag"].strip('"')
        if not r.get("IsTruncated"):
            return out
        tok = r.get("NextContinuationToken")


def _remote_manifest(s3, bucket: str, d: str) -> dict | None:
    """The manifest currently on R2 for dir `d` (via the S3 API — the public r2.dev
    host 403s non-browser UAs), or None when absent/unparsable."""
    try:
        r = s3.get_object(Bucket=bucket, Key=f"{d}/_manifest.json")
        return json.loads(r["Body"].read())
    except Exception:
        return None


def _manifest_ok(new_count: int, remote: dict | None, floor: float = 0.5) -> tuple[bool, str]:
    """May a freshly-built manifest replace `remote`? Bulk consumers sync AND PRUNE
    against this list, so a partial-tree invocation must never clobber it: replacing
    a ~5000-name manifest with the 2 git-committed stockdata files would make a
    downstream mirror prune itself empty. Blocks when the new list is under `floor`
    of the remote count; intentional universe culls that deep need --force-manifest."""
    old = (remote or {}).get("count")
    if not isinstance(old, int) or old <= 0:
        return True, "no usable remote manifest"
    if new_count < old * floor:
        return False, f"would shrink the manifest {old} -> {new_count} files"
    return True, f"{new_count} files (was {old})"


def publish(dirs, dry_run: bool = False, workers: int = 32,
            manifest: bool = True, force_manifest: bool = False) -> int:
    s3 = _client()
    if s3 is None:
        log.info("no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY) — skip")
        return 0
    from lib import config
    bucket = os.environ["R2_BUCKET"]
    site = config.ROOT / config.load()["storage"]["site_dir"]
    up = skip = 0
    for d in dirs:
        base = site / d
        if not base.is_dir():
            log.info("%s: absent — skip", d)
            continue
        files = [p for p in base.rglob("*") if p.is_file()]
        remote = _remote_etags(s3, bucket, d + "/")
        todo = []
        for p in files:
            key = f"{d}/{p.relative_to(base).as_posix()}"
            if remote.get(key) == _md5(p):
                skip += 1
            else:
                todo.append((p, key))
        log.info("%s: %d files — %d changed, %d unchanged", d, len(files), len(todo), len(files) - len(todo))
        if dry_run:
            up += len(todo)
            continue

        def _up(pk):
            p, key = pk
            s3.upload_file(str(p), bucket, key,
                           ExtraArgs={"ContentType": _CT.get(p.suffix, "application/octet-stream")})

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_up, todo))
        up += len(todo)
        # Manifest goes up LAST, after every file it lists is in place. The public
        # r2.dev host has no LIST endpoint, so bulk mirrors (e.g. the Mastermind bot's
        # vendored-feed R2 leg) need an authoritative name list to sync and prune against.
        # Only FULL publishes may touch it (audit_r2's freshness tripwire anchors on its
        # Last-Modified, and it takes freshest-of manifest/index — partial lanes skipping
        # the put is fine); the shrink guard catches partial lanes that forget the flag.
        if not manifest:
            log.info("%s: manifest untouched (--no-manifest)", d)
            continue
        names = sorted(p.relative_to(base).as_posix() for p in files)
        ok, why = (True, "forced") if force_manifest else \
            _manifest_ok(len(names), _remote_manifest(s3, bucket, d))
        if not ok:
            log.error("%s: manifest put BLOCKED — %s. This looks like a partial-tree "
                      "invocation; pass --no-manifest for partial syncs "
                      "(or --force-manifest for an intentional cull).", d, why)
            print(f"::warning title=publish_r2 manifest guard::{d}: {why} — "
                  "manifest NOT replaced (partial-tree invocation?)", flush=True)
            continue
        log.info("%s: manifest put — %s", d, why)
        s3.put_object(Bucket=bucket, Key=f"{d}/_manifest.json",
                      Body=json.dumps({"dir": d, "count": len(names), "files": names}).encode(),
                      ContentType="application/json")
    log.info("R2 publish done: %d uploaded, %d unchanged (bucket=%s)", up, skip, bucket)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", default=",".join(DEFAULT_DIRS),
                    help="comma-separated site/ subdirs to sync (default: the heavy stores)")
    ap.add_argument("--dry-run", action="store_true", help="report the delta, upload nothing")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--no-manifest", dest="manifest", action="store_false",
                    help="sync files but leave _manifest.json untouched — REQUIRED for "
                         "partial-tree invocations (checkout lacking the full dir)")
    ap.add_argument("--force-manifest", action="store_true",
                    help="override the shrink guard (intentional deep universe cull)")
    a = ap.parse_args()
    dirs = [d.strip() for d in a.dirs.split(",") if d.strip()]
    return publish(dirs, dry_run=a.dry_run, workers=a.workers,
                   manifest=a.manifest, force_manifest=a.force_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
