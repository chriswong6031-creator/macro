"""Restore R2-hosted per-ticker stores into the local tree — the download leg
of scripts/publish_r2.

Why: the heavy per-ticker stores are gitignored and live on Cloudflare R2 (the
R2 data plane), so a fresh CI checkout holds NONE of their files. Jobs that
read a store locally restore it with this script first. For incremental
stores (data/attention: SLF-048 Wikipedia pageviews, deep history 2015-07→)
the collect job restores BEFORE the collector runs, so lib.store.upsert
extends the deep history with the day's fetch window instead of rebuilding a
shallow window from scratch.

Key layout mirrors publish_r2: R2 key `attention/AAPL.parquet` maps to
data/<dir>/ for data-dir stores (publish_r2._DATA_DIRS) and site/<dir>/
otherwise. `_manifest.json` keys are SKIPPED: the manifest is a publish-side
artifact — restoring it locally would be re-embedded under `store` by the
next publish's manifest doc (nested-manifest growth), and for site dirs it
would shadow the collector-written store manifest.

Content-hash skip (local md5 vs R2 ETag) means a warm tree costs one LIST and
zero GETs. Downloads land via a temp file + rename so a killed run never
leaves a truncated parquet. Local files absent on R2 are NEVER pruned.

Exit codes: 0 = restored (or graceful no-op when the R2_* creds are absent,
matching publish_r2); 1 = creds present but a requested dir yielded zero
objects or a download failed. Callers gate publish-back steps on this exit
code — "restore failed" must mean "do not publish the local tree over the
deep store" (see daily.yml's attention_restore/publish pair).

Usage: python -m scripts.fetch_r2 --dirs attention [--workers 16]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.publish_r2 import _DATA_DIRS, _client, _md5, _remote_etags  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_r2")


def fetch(dirs, workers: int = 16) -> int:
    s3 = _client()
    if s3 is None:
        log.info("no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY) — skip")
        return 0
    from lib import config
    bucket = os.environ["R2_BUCKET"]
    cfg = config.load()["storage"]
    site = config.ROOT / cfg["site_dir"]
    data = config.ROOT / cfg["data_dir"]
    rc = 0
    for d in dirs:
        base = (data if d in _DATA_DIRS else site) / d
        try:
            remote = _remote_etags(s3, bucket, d + "/")
        except Exception as e:  # noqa: BLE001 — per-dir failure, keep going
            log.error("%s: R2 list failed (%s)", d, e)
            rc = 1
            continue
        remote = {k: v for k, v in remote.items() if not k.endswith("_manifest.json")}
        if not remote:
            log.error("%s: ZERO objects under %s/ on R2 — nothing to restore "
                      "(store never published, or wrong bucket?)", d, d)
            rc = 1
            continue
        base.mkdir(parents=True, exist_ok=True)
        todo, current = [], 0
        for key, (etag, _size) in remote.items():
            p = base / key[len(d) + 1:]
            if p.is_file() and _md5(p) == etag:
                current += 1
            else:
                todo.append((key, p))

        def _down(kp):
            key, p = kp
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.parent / (p.name + ".r2tmp")
            s3.download_file(bucket, key, str(tmp))
            tmp.replace(p)

        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(_down, todo))
        except Exception as e:  # noqa: BLE001 — partial restore = failed restore
            log.error("%s: download failed (%s) — restore INCOMPLETE", d, e)
            rc = 1
            continue
        log.info("%s: %d restored, %d already current (bucket=%s)",
                 d, len(todo), current, bucket)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", required=True,
                    help="comma-separated store dirs to restore (e.g. attention)")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    return fetch([d for d in a.dirs.split(",") if d], workers=a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
