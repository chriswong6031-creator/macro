#!/usr/bin/env python3
"""scripts/seal_levels_ledger.py — seal the day's levels boards before the open.

Voltick Gamma-Levels program, WP-C3. For a session date, compute each root's named-level
board from data known at the open (greeks + t-1 OI, per the OI timing law — point-in-time),
project it to the sealed prediction, write one canonical file, SHA-256 seal it, and append
the hash to a public, permanent manifest. After the close the WP-C1 grader scores it. The
hash is the tamper-evident proof that the map came first — anyone can re-hash the downloaded
file with `shasum -a 256` and reproduce the published hash.

DISPLAY-TIER: a record of where the positioning map sat before each session — a measurement,
never a forecast, never a reason to trade.

Usage:
    python -m scripts.seal_levels_ledger --roots SPY,AAPL,MSFT --date 2024-06-14 --sealed-at 2024-06-14T13:12:00Z
    python -m scripts.seal_levels_ledger --universe stocks --date 2024-06-14 --publish
    python -m scripts.seal_levels_ledger --verify 2024-06-14      # re-hash + check against the manifest
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date as _date, timezone, datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.config import data_dir  # noqa: E402
from engine.thetadata_store import resolve_thetadata_store, clear_parquet_cache  # noqa: E402
from engine.levels_ledger import (  # noqa: E402
    seal, seal_board, verify, index_entry, canonical_bytes, sha256_hex, INDEX_SCHEMA,
)
# reuse the WP-C1 reconstruction (compute_gex -> compute_levels for a past date)
from scripts.build_levels_track_record import _reconstruct, _resolve_roots  # noqa: E402

log = logging.getLogger("seal_levels_ledger")

_LEDGER_DIR = Path(data_dir()) / "levels" / "ledger"
_INDEX = _LEDGER_DIR / "index.json"
R2_PREFIX = "levels_ledger/"


def _load_index() -> dict:
    if _INDEX.exists():
        try:
            return json.loads(_INDEX.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"schema": INDEX_SCHEMA, "entries": []}


def _save_index(idx: dict) -> None:
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _INDEX.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(idx, separators=(",", ":")))
    tmp.replace(_INDEX)


def _publish_r2(local: Path, key: str) -> bool:
    ak = os.environ.get("R2_ACCESS_KEY_ID"); sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    ep = os.environ.get("R2_ENDPOINT"); bucket = os.environ.get("R2_BUCKET", "mastermindx")
    if not (ak and sk and ep):
        log.warning("R2 creds absent — skipping publish")
        return False
    try:
        import boto3  # noqa: PLC0415
        s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                          aws_secret_access_key=sk, region_name="auto")
        s3.upload_file(str(local), bucket, key, ExtraArgs={"ContentType": "application/json"})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("R2 publish failed for %s — %s", key, e)
        return False


def _verify_date(session_date: str) -> int:
    """Re-hash the on-disk sealed file and compare to the manifest hash."""
    f = _LEDGER_DIR / f"{session_date}.json"
    if not f.exists():
        log.error("no sealed file for %s at %s", session_date, f)
        return 2
    idx = _load_index()
    entry = next((e for e in idx["entries"] if e.get("session_date") == session_date), None)
    if not entry:
        log.error("no manifest entry for %s", session_date)
        return 2
    obj = json.loads(f.read_text())
    ok = verify(obj, entry["sha256"])
    recomputed = sha256_hex(canonical_bytes(obj))
    log.info("%s: published=%s recomputed=%s -> %s", session_date, entry["sha256"][:16],
             recomputed[:16], "MATCH ✓" if ok else "MISMATCH ✗ (file changed since sealing)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Seal the day's levels boards (SHA-256, pre-open).")
    ap.add_argument("--roots", default="")
    ap.add_argument("--universe", choices=["stocks"], default=None)
    ap.add_argument("--date", default=_date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--sealed-at", default="")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--verify", default="", help="re-hash the sealed file for a date and exit")
    args = ap.parse_args(argv)

    if args.verify:
        return _verify_date(args.verify)

    roots = _resolve_roots(args)
    if not roots:
        log.error("no roots (pass --roots or --universe stocks)")
        return 2
    try:
        store = Path(resolve_thetadata_store(required=True, purpose="levels ledger seal"))
    except Exception as e:  # noqa: BLE001
        log.error("no thetadata store: %s", e)
        return 3

    sealed_at = args.sealed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sealed_boards = []
    skipped = 0
    for root in roots:
        rec, why = _reconstruct(root, args.date, store)
        clear_parquet_cache()
        if rec is None:
            skipped += 1
            continue
        sb = seal_board(rec["levels"])
        if sb is not None and sb["nodes"]:
            sealed_boards.append(sb)
        else:
            skipped += 1
    if not sealed_boards:
        log.error("nothing to seal for %s (%d roots skipped — no reconstructable board)",
                  args.date, skipped)
        return 4

    ledger_file, sha = seal(args.date, sealed_boards, sealed_at=sealed_at)
    _LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    out = _LEDGER_DIR / f"{args.date}.json"
    out.write_text(json.dumps(ledger_file, separators=(",", ":")))

    # append/replace the manifest entry (idempotent by session_date)
    idx = _load_index()
    idx["entries"] = [e for e in idx["entries"] if e.get("session_date") != args.date]
    idx["entries"].append(index_entry(ledger_file, sha))
    idx["entries"].sort(key=lambda e: e.get("session_date") or "", reverse=True)
    _save_index(idx)

    if args.publish:
        _publish_r2(out, f"{R2_PREFIX}{args.date}.json")
        _publish_r2(_INDEX, f"{R2_PREFIX}index.json")

    # self-verify immediately (the sealed bytes must reproduce the hash)
    assert verify(ledger_file, sha), "internal seal self-check failed"
    log.info("sealed %s: %d boards, %d skipped · sha256=%s · sealed_at=%s",
             args.date, ledger_file["n_boards"], skipped, sha, sealed_at)
    log.info("  verify anytime:  shasum -a 256 %s   → compare to the manifest hash above", out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
