"""scripts/build_options_matrix.py — one-shot strike×expiry matrix publisher (Package E).

Builds options_structure.matrix/v1 payloads for one or more roots from the
ThetaData EOD store and optionally publishes to R2 under the key
    options_structure/matrix/<ROOT>.json

Usage:
    python -m scripts.build_options_matrix [--roots SPY QQQ ...] [--publish]
        [--out DIR] [--date YYYY-MM-DD]

Environment variables:
    THETADATA_STORE   Path to the ThetaData EOD store root (required for real data)
    R2_ENDPOINT       Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID  R2 access key
    R2_SECRET_ACCESS_KEY  R2 secret
    R2_BUCKET         R2 bucket name

Defaults:
    --roots   : SPY QQQ IWM NVDA TSLA AAPL MSFT META AMD GOOGL
    --out     : data/live_flow_out/options_matrix/
    --publish : disabled unless flag is passed

SCHEDULING NOTE:
    Wired as a launchd lane (NOT daily.yml — the GH runner cannot see the theta store).
    ops/launchd/com.macro.optionsmatrix.plist fires weekdays at 19:00 local via
    ops/launchd/run_with_env.sh + /Users/chriswong/flow-ops-wt/.env.
    The runner ops/launchd/run_options_matrix.sh gates on SPY EOD store freshness
    (expected_last_session per lib/nyse_calendar) with bounded retry (20-min sleep,
    max 6 attempts = 2h window) before invoking this script with --publish.
    Set MATRIX_FRESHNESS_BYPASS=1 to skip the wait (one-shot smoke / CI).

INERT per-root: each root failure logs + skips; never aborts the run.
DISPLAY-TIER: no ranking, scoring, or money-path interaction.
OI TIMING LAW: all OI uses OI[t-1]; delta_oi = OI[t-1] − OI[t-2] (both lagged).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.options_matrix import build_matrix
from engine.thetadata_store import clear_parquet_cache

log = logging.getLogger(__name__)

# ── R2 key prefix ─────────────────────────────────────────────────────────────
R2_PREFIX = "options_structure/matrix/"

# ── default roots ─────────────────────────────────────────────────────────────
DEFAULT_ROOTS = [
    "SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "GOOGL",
]


# --------------------------------------------------------------------------- #
# R2 helpers (mirrors scripts/build_options_hub_nightly.py pattern exactly)    #
# --------------------------------------------------------------------------- #

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds are absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=16,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        try:
            cfg = Config(**kw,
                         request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client(
            "s3",
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("options_matrix_builder: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload a local file to R2. Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("options_matrix_builder: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("options_matrix_builder: R2 upload failed for %s: %s", r2_key, e)
        return False


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=False, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Build strike×expiry options matrix (Package E)."
    )
    parser.add_argument(
        "--roots", nargs="+", default=DEFAULT_ROOTS,
        metavar="ROOT",
        help="Option root symbols to process (default: SPY QQQ IWM NVDA TSLA AAPL MSFT META AMD GOOGL)",
    )
    parser.add_argument(
        "--publish", action="store_true", default=False,
        help="Upload outputs to R2 under options_structure/matrix/<ROOT>.json",
    )
    parser.add_argument(
        "--out", default=None,
        help="Local output directory (default: data/live_flow_out/options_matrix/)",
    )
    parser.add_argument(
        "--date", default=None,
        help="Reference date YYYY-MM-DD (default: most recent OI date per root)",
    )
    args = parser.parse_args()

    # ── resolve output dir ───────────────────────────────────────────────────
    out_dir = Path(args.out) if args.out else (_REPO / "data" / "live_flow_out" / "options_matrix")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── store path — canonical resolver (WP-RESOLVER) ─────────────────────────
    # THETADATA_STORE env → data_dir()/thetadata_eod → ops-wt, content-checked.
    # Fail-loud contract: this builder publishes matrices — when no store
    # resolves it exits nonzero instead of writing/uploading no-data payloads.
    from engine.thetadata_store import resolve_thetadata_store
    theta_store = resolve_thetadata_store(required=False, purpose="build_options_matrix")
    if theta_store is None:
        log.error(
            "options_matrix_builder: no ThetaData store resolves — exiting "
            "nonzero WITHOUT writing/publishing no-data matrices "
            "(set THETADATA_STORE or fix the store path)")
        sys.exit(1)

    # ── R2 setup ─────────────────────────────────────────────────────────────
    s3 = None
    bucket = None
    if args.publish:
        s3 = _r2_client()
        bucket = os.environ.get("R2_BUCKET")
        if s3 is None or not bucket:
            log.error(
                "options_matrix_builder: --publish requested but R2 creds incomplete "
                "(need R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET)"
            )
            # Continue — we will still write local JSONs; just skip upload

    # ── per-root loop ─────────────────────────────────────────────────────────
    results: dict[str, dict] = {}   # root → {"n_cells", "uploaded", "error"}

    for root in args.roots:
        root = root.upper()
        try:
            payload = build_matrix(root, store=theta_store, asof=args.date)
        except Exception as e:  # noqa: BLE001
            log.error("options_matrix_builder: build failed for %s — %s", root, e)
            results[root] = {"n_cells": 0, "uploaded": False, "error": str(e)}
            continue

        # write local JSON
        local_path = out_dir / f"{root}.json"
        try:
            _write_json(local_path, payload)
            log.info("options_matrix_builder: wrote %s (%d cells)",
                     local_path, len(payload.get("cells", [])))
        except Exception as e:  # noqa: BLE001
            log.error("options_matrix_builder: write failed for %s — %s", root, e)
            results[root] = {"n_cells": 0, "uploaded": False, "error": str(e)}
            continue

        # upload to R2
        uploaded = False
        if args.publish and s3 and bucket:
            r2_key = f"{R2_PREFIX}{root}.json"
            uploaded = _upload_r2(s3, bucket, local_path, r2_key)

        n_cells = len(payload.get("cells", []))
        results[root] = {
            "n_cells":   n_cells,
            "uploaded":  uploaded,
            "error":     None,
            "no_data":   payload.get("_no_data_reason"),
        }

        # release per-root cache after each root to bound memory on large universes
        clear_parquet_cache()

    # ── summary ───────────────────────────────────────────────────────────────
    published  = [r for r, d in results.items() if d.get("uploaded")]
    failed     = [r for r, d in results.items() if d.get("error")]
    no_data    = [r for r, d in results.items() if d.get("no_data")]

    print("\n--- options_matrix build summary ---")
    for root, d in results.items():
        status = "UPLOADED" if d.get("uploaded") else ("ERROR" if d.get("error") else "local-only")
        no_data_note = f" [{d['no_data']}]" if d.get("no_data") else ""
        print(f"  {root:10s}  cells={d['n_cells']:4d}  {status}{no_data_note}")
    print(f"\npublished={published}  failed={failed}  no_data={no_data}")
    print("---")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
