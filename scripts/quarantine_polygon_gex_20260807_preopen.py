#!/usr/bin/env python3
"""Quarantine the 2026-08-07 Polygon GEX pre-open snapshot.

The snapshot was produced by a long-running daily workflow that checked out before
#4807 fixed UTC run-date stamping, then rebased its data commit onto main after the fix.
The resulting commit therefore contains the fixed writer *and* one row produced by the
old writer.  The 08-07 file was captured at 08:18 ET, before that session opened, and
cannot represent the 08-07 close.

This is a pinned one-shot repair.  It removes the raw chain and its matching summary row
from every underlying, records the exact recovery blob in a manifest, and deliberately
leaves 2026-08-07 as an honest Polygon gap.  It never edits the row to match another
provider and never re-dates it onto the already-populated 2026-08-06 session.

Run::

    python -m scripts.quarantine_polygon_gex_20260807_preopen
    python -m scripts.quarantine_polygon_gex_20260807_preopen --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.migrate_polygon_gex_session_stamps import (  # noqa: E402
    _classify,
    _verify_cross_section,
)

TARGET = "2026-08-07"
TARGET_TS = pd.Timestamp(TARGET)
CHAIN_REL = f"data/polygon_gex/chains/{TARGET}.parquet"
CHAIN_SHA256 = "79107ea700648bc8332679fe7a0a85828ea5ad934191039e710bcf47be7e12df"
CHAIN_GIT_BLOB = "0954bbfe66131737789045142c369722da94f106"
RECOVERY_COMMIT = "08ad4d836d6afeed1d8e61b3df580b1a5176476c"
SOURCE_RUN = 31138544929
SOURCE_JOB = 92833411966
SOURCE_HEAD = "0412deb4d045da8bbe6fe5b4852a8ae26bfdfddc"
MANIFEST = ROOT / "docs/polygon_gex_session_stamp_repair_20260810.json"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _recovery_blob() -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{RECOVERY_COMMIT}:{CHAIN_REL}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def _summary_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted((ROOT / "data/polygon_gex").glob("summary_*.parquet")):
        frame = pd.read_parquet(path)
        if TARGET_TS not in frame.index:
            continue
        symbol = path.stem.removeprefix("summary_")
        row = frame.loc[TARGET_TS]
        if isinstance(row, pd.DataFrame):
            raise SystemExit(f"{path}: duplicate {TARGET} summary rows")
        rows.append(
            {
                "path": path,
                "rel": str(path.relative_to(ROOT)),
                "symbol": symbol,
                "spot": float(row["spot"]),
                "frame": frame,
            }
        )
    return rows


def _already_applied(rows: list[dict]) -> bool:
    chain_absent = not (ROOT / CHAIN_REL).exists()
    if chain_absent and not rows and MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())
        if manifest.get("source", {}).get("chain_sha256") != CHAIN_SHA256:
            raise SystemExit(f"{MANIFEST}: unexpected source hash")
        return True
    if chain_absent or not rows:
        raise SystemExit(
            "partial repair state: chain and all summary rows must be present "
            "before the first apply, or both absent with the pinned manifest afterwards"
        )
    return False


def build_plan() -> dict:
    rows = _summary_rows()
    if _already_applied(rows):
        return {"already_applied": True, "rows": []}

    chain_path = ROOT / CHAIN_REL
    if _sha256_file(chain_path) != CHAIN_SHA256:
        raise SystemExit(f"{CHAIN_REL}: source bytes moved under the pinned repair")
    recovery = _recovery_blob()
    if _sha256_bytes(recovery) != CHAIN_SHA256:
        raise SystemExit(f"{RECOVERY_COMMIT[:12]}:{CHAIN_REL}: recovery blob moved")
    blob = subprocess.run(
        ["git", "hash-object", CHAIN_REL],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if blob != CHAIN_GIT_BLOB:
        raise SystemExit(f"{CHAIN_REL}: git blob {blob} != pinned {CHAIN_GIT_BLOB}")

    chain = pd.read_parquet(chain_path, columns=["underlying", "spot", "asof"])
    if len(chain) != 170_016:
        raise SystemExit(f"{CHAIN_REL}: expected 170016 rows, found {len(chain)}")
    stamps = {
        pd.Timestamp(value).strftime("%Y-%m-%d") for value in chain["asof"].unique()
    }
    if stamps != {TARGET}:
        raise SystemExit(f"{CHAIN_REL}: embedded asof moved: {sorted(stamps)}")
    underlyings = sorted(map(str, chain["underlying"].unique()))
    if len(underlyings) != 372:
        raise SystemExit(
            f"{CHAIN_REL}: expected 372 underlyings, found {len(underlyings)}"
        )

    summary_symbols = sorted(row["symbol"] for row in rows)
    if summary_symbols != underlyings:
        missing = sorted(set(underlyings) - set(summary_symbols))
        extra = sorted(set(summary_symbols) - set(underlyings))
        raise SystemExit(
            f"summary/source mismatch: missing={missing} extra={extra}"
        )
    chain_spots = (
        chain.groupby("underlying", observed=True)["spot"].first().astype(float)
    )
    mismatched = [
        (row["symbol"], row["spot"], float(chain_spots.loc[row["symbol"]]))
        for row in rows
        if abs(row["spot"] - float(chain_spots.loc[row["symbol"]])) > 0.02
    ]
    if mismatched:
        raise SystemExit(
            f"summary rows no longer derive from the pinned chain: {mismatched[:5]}"
        )

    metrics = _verify_cross_section(chain[["underlying", "spot"]], TARGET_TS.date())
    classification = _classify(metrics)
    if classification != "MIXED":
        raise SystemExit(
            f"{CHAIN_REL}: expected the ruled MIXED cross-section, "
            f"got {classification} ({asdict(metrics)})"
        )
    return {
        "already_applied": False,
        "rows": rows,
        "underlyings": underlyings,
        "metrics": asdict(metrics),
        "classification": classification,
    }


def apply(plan: dict) -> dict:
    deleted_empty: list[str] = []
    rewritten: list[str] = []
    for item in plan["rows"]:
        frame = item["frame"].drop(index=TARGET_TS)
        path = item["path"]
        if frame.empty:
            path.unlink()
            deleted_empty.append(item["rel"])
        else:
            frame.to_parquet(path)
            rewritten.append(item["rel"])

    (ROOT / CHAIN_REL).unlink()
    manifest = {
        "what": "quarantine a pre-open Polygon snapshot falsely stamped as 2026-08-07",
        "applied": True,
        "root_cause": {
            "workflow_run": SOURCE_RUN,
            "collect_job": SOURCE_JOB,
            "checkout_head": SOURCE_HEAD,
            "checkout_writer": "scripts.build_polygon_gex._as_date (UTC run-date)",
            "run_created_utc": "2026-08-07T01:36:07Z",
            "snapshot_written_utc": "2026-08-07T12:18:49Z",
            "snapshot_written_et": "2026-08-07T08:18:49-04:00",
            "session_fix_merge_commit": "fc7ad1a6a95724171a99b51ffca1b9a8e560b034",
            "data_commit_after_rebase": RECOVERY_COMMIT,
            "explanation": (
                "the workflow checked out before the session-stamp fix, ran its old "
                "writer after the fix merged, then rebased the data commit onto "
                "fixed main"
            ),
        },
        "source": {
            "chain_path": CHAIN_REL,
            "chain_rows": 170_016,
            "underlyings": len(plan["underlyings"]),
            "chain_sha256": CHAIN_SHA256,
            "chain_git_blob": CHAIN_GIT_BLOB,
            "recovery_commit": RECOVERY_COMMIT,
            "recovery_command": f"git show {RECOVERY_COMMIT}:{CHAIN_REL}",
        },
        "adjudication": {
            "resolved_session": "2026-08-06",
            "claimed_session": TARGET,
            "classification_against_claimed_session": plan["classification"],
            "metrics_against_claimed_session": plan["metrics"],
            "disposition": "quarantine",
            "reason": (
                "captured before the 2026-08-07 open; the valid 2026-08-06 "
                "chain already exists, so re-dating would overwrite evidence; "
                "2026-08-07 remains a gap"
            ),
        },
        "changes": {
            "raw_chain_removed": CHAIN_REL,
            "summary_rows_removed": len(plan["rows"]),
            "summary_files_rewritten": len(rewritten),
            "empty_summary_files_removed": deleted_empty,
            "symbols": plan["underlyings"],
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write the pinned quarantine"
    )
    args = parser.parse_args()
    plan = build_plan()
    if plan["already_applied"]:
        print("2026-08-07 Polygon pre-open snapshot is already quarantined")
        return 0
    report = {
        "classification": plan["classification"],
        "metrics": plan["metrics"],
        "summary_rows": len(plan["rows"]),
        "raw_chain": CHAIN_REL,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not args.apply:
        print("\ndry run -- re-run with --apply to quarantine")
        return 0
    manifest = apply(plan)
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    print(json.dumps(manifest["changes"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
