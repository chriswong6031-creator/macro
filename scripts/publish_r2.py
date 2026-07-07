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

Append-only stores (_APPEND_ONLY_DIRS, e.g. attention/) additionally refuse per-file
uploads SMALLER than the R2 object, plus a per-dir total-bytes floor: when the
fetch_r2 restore fails, the collector rebuilds the same ~966 filenames as
real-but-short files, so a runner tree can pass the min-files guard yet must never
clobber the deep-history objects. Restore the download leg with scripts/fetch_r2.

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
    "hk_stocks_ext",  # expanded HSCI universe (~380 new names) deep OHLCV parquets
                      # (data/hk_stocks_ext/*.parquet, gitignored); ~65 MB initial
                      # — masterplan §3 H4, §8 W1 (collectors/hk_universe.py)
    "massive_stock_day",  # whole-market daily OHLCV per-ticker parquets
                          # (data/massive_stock_day/*.parquet, gitignored); ~240 MB
                          # — Setup-Species §7 W0.6a (collectors/massive_stock_day.py)
    "thetadata_eod",      # ThetaData EOD options chain parquets — one per root per year
                          # (data/thetadata_eod/<root>/<year>.parquet, gitignored); ~GB-class
                          # — Options Alpha masterplan ruling A4 (raw vendor pulls are never
                          # git-committed — local cache + R2 with manifest + audit tripwire).
                          # Store lives on the ops host; publish via:
                          #   THETADATA_STORE env (default data/thetadata_eod) + --dirs thetadata_eod
                          # Must run from the ops host (store host) where the parquets are
                          # materialised; the _DATA_DIR_MIN_FILES guard refuses CI partial checkouts.
    "stock_personality",  # Stock-personality panel monthly partitions — gitignored-local,
                          # published to R2 via this script (stock-personality program).
                          # Source: data/stock_personality/panel/YYYY-MM/panel.parquet
]

# Dirs whose source lives under data/ rather than site/ (per-ticker parquet stores
# that are never rendered into site/ — published straight from the data plane).
_DATA_DIRS = {
    "hk_stocks_ext", "massive_stock_day", "thetadata_eod", "stock_personality",
    "attention",  # SLF-048 Wikipedia pageview store (data/attention/*.parquet,
                  # gitignored since 2026-07-06): deep history 2015-07→ lives on R2,
                  # kept CURRENT by daily.yml's collect job (fetch_r2 restore ->
                  # wiki_pageviews upsert -> outcome-gated publish-back). See
                  # reports/slf048-wiki-attention-phase0.md §Nightly wiring.
}
# A data-dir tree with fewer files than this is a PARTIAL CHECKOUT (the parquets are
# gitignored — a CI runner checkout holds just the committed _manifest.json +
# _backfill_state.json), not the store. Syncing it would overwrite R2's full-history
# objects with 2-file stubs; refuse instead. Only the store host (the Mac main
# checkout, where the backfill materialises the parquets) may publish these dirs.
_DATA_DIR_MIN_FILES = 100
# History-append stores whose R2 objects hold DEEP history (data/attention/*.parquet:
# backfilled 2015-07→ SLF-048 2026-07-06; gitignored since same day). The nightly
# collect job materialises the store via scripts/fetch_r2 BEFORE the wiki_pageviews
# collector upserts its ~120d window, then publishes back (gated on the restore step's
# outcome — see daily.yml). If that restore silently failed, the collector rebuilds
# all ~966 filenames as real-but-SHORT files that sail past _DATA_DIR_MIN_FILES, so
# two more fences catch the shape:
#  - per FILE, a changed file uploads only when the local object is at least as
#    large as the remote one (_APPEND_ONLY_DIRS);
#  - per DIR, the whole tree is refused when its total bytes sit under the floor
#    (_DATA_DIR_MIN_BYTES: shallow ~120d rebuild ≈7 MB vs deep store ≈45 MB) —
#    this also covers the empty-remote case the per-file guard can't compare against.
# Deliberately NOT in DEFAULT_DIRS: only the collect job's gated lane (or a host-side
# ATTENTION_STORE publish) touches it.
_APPEND_ONLY_DIRS = {"attention"}
_DATA_DIR_MIN_BYTES = {"attention": 15_000_000}
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
    """key -> (ETag, Size) already under prefix (ETag == md5 for our small
    single-part objects; Size feeds the append-only guard)."""
    out, tok = {}, None
    while True:
        kw = {"Bucket": bucket, "Prefix": prefix}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = (o["ETag"].strip('"'), o["Size"])
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


def _data_dir_syncable(d: str, n_files: int, total_bytes: int | None = None) -> tuple[bool, str]:
    """May this dir's local tree be synced to R2?  Data-dir stores (parquets under
    data/<dir>, gitignored) exist in full ONLY on the store host — a CI runner
    checkout holds just the committed JSON stubs, and syncing those would overwrite
    the R2 store's full-history objects.  Site dirs are always syncable."""
    if d in _DATA_DIRS and n_files < _DATA_DIR_MIN_FILES:
        return False, (f"only {n_files} file(s) locally (< {_DATA_DIR_MIN_FILES}) — "
                       "partial checkout, the parquet store is not materialised here")
    floor = _DATA_DIR_MIN_BYTES.get(d)
    if d in _DATA_DIRS and floor and total_bytes is not None and total_bytes < floor:
        return False, (f"local tree is {total_bytes / 1e6:.1f} MB (< {floor / 1e6:.0f} MB floor) — "
                       "looks like a shallow rebuild, not the deep-history store")
    return True, ""


def _append_only_guarded(d: str, local_size: int, remote_size: int | None) -> bool:
    """True when `d` is an append-only history store and the local file is SMALLER
    than the R2 object — a short-window checkout, not a legitimate rewrite; uploading
    would clobber the deep-history object. An intentional shrinking re-export needs
    the R2 objects deleted first."""
    return d in _APPEND_ONLY_DIRS and remote_size is not None and local_size < remote_size


def _manifest_doc(d: str, base: Path, names: list[str]) -> dict:
    """The manifest object to put for dir `d`.  Data-dir stores keep their own
    collector-written _manifest.json (freshness + coverage/anchor blocks — see
    collectors/massive_stock_day._write_manifest); the file-list put would clobber
    it on R2, losing the coverage evidence audit_r2's content probe reads — so it
    is embedded under "store" instead."""
    doc: dict = {"dir": d, "count": len(names), "files": names}
    if d in _DATA_DIRS:
        try:
            doc["store"] = json.loads((base / "_manifest.json").read_text())
        except Exception:  # noqa: BLE001 — no/unparsable local store manifest: plain list
            pass
    return doc


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
    data = config.ROOT / config.load()["storage"]["data_dir"]
    # Per-dir store-path overrides: env vars let the ops host publish stores that live
    # outside the repo checkout (e.g. THETADATA_STORE for the theta-ops worktree).
    # If the env var is absent, the default repo-relative data/<dir> path is used.
    _store_overrides: dict[str, Path] = {}
    if ts := os.environ.get("THETADATA_STORE"):
        _store_overrides["thetadata_eod"] = Path(ts)
    if ts := os.environ.get("ATTENTION_STORE"):
        _store_overrides["attention"] = Path(ts)
    for d in dirs:
        # Per-ticker parquet stores live under data/<dir>, not site/<dir>.
        if d in _DATA_DIRS:
            base = _store_overrides.get(d, data / d)
        else:
            base = site / d
        if not base.is_dir():
            log.info("%s: absent — skip", d)
            continue
        files = [p for p in base.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files) if d in _DATA_DIRS else None
        ok, why = _data_dir_syncable(d, len(files), total)
        if not ok:
            log.error("%s: %s — refusing to sync so the R2 copy isn't clobbered; "
                      "publish from the store host instead.", d, why)
            print(f"::warning title=publish_r2 partial data-dir::{d}: {why} — dir "
                  "skipped", flush=True)
            continue
        remote = _remote_etags(s3, bucket, d + "/")
        todo, guarded = [], 0
        for p in files:
            key = f"{d}/{p.relative_to(base).as_posix()}"
            etag, rsize = remote.get(key, (None, None))
            if etag == _md5(p):
                skip += 1
            elif _append_only_guarded(d, p.stat().st_size, rsize):
                guarded += 1
            else:
                todo.append((p, key))
        log.info("%s: %d files — %d changed, %d unchanged, %d guarded", d, len(files),
                 len(todo), len(files) - len(todo) - guarded, guarded)
        if guarded:
            log.warning("%s: %d local file(s) SMALLER than their R2 object — append-only "
                        "store, short-window checkout? NOT uploaded; publish from the "
                        "deep-history host store instead.", d, guarded)
            print(f"::warning title=publish_r2 append-only guard::{d}: {guarded} "
                  "shorter-than-remote local file(s) skipped", flush=True)
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
        if guarded:
            log.info("%s: manifest untouched (append-only guard tripped — this local "
                     "tree is not authoritative for the store)", d)
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
                      Body=json.dumps(_manifest_doc(d, base, names)).encode(),
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
