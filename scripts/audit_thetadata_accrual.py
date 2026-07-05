"""ThetaData EOD store freshness audit (dead-man's switch for options chain accrual).

The thetadata_eod store (data/thetadata_eod/) accumulates EOD option chains, open
interest, and Greeks pulled from the local Theta Terminal (collectors/thetadata.py,
scripts/backfill_thetadata_eod.py).  Because the Terminal is a local Java process and
its collect step is a manually scheduled Mac-only operation, a stale store is
otherwise invisible.  This audit is the circuit-breaker visibility layer.

Two operating modes:
  BACKFILL IN PROGRESS — store present but universe incomplete (n_roots == 0 in the
    manifest, or no parquet files yet).  This is the expected state during the initial
    multi-day/multi-week backfill.  Health check emits INFO and returns OK (no screaming)
    so the heartbeat does not red-flag a legitimately in-progress backfill.
    Detection: _backfill_state.json present AND (n_roots == 0 OR no .parquet files).

  STEADY STATE — at least one root has been completed (parquets exist).  Freshness
    check: newest parquet mtime must be ≤ max_age_days behind now.  Stale → WARN/FAIL.

Writes data/quality/thetadata_accrual_audit.json (observability; read-only over stores).
Stdlib-only on purpose (same pattern as audit_options_accrual.py).

Usage: python -m scripts.audit_thetadata_accrual [--strict] [--max-age-days 3]
       --strict: exit 1 on STALE/DARK findings (default: report-only)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

DEFAULT_MAX_AGE_DAYS = 3   # newest parquet mtime must be ≤ 3 days old in steady state
STORE_SUBDIR = "thetadata_eod"


def _store_dir(data_root: Path | None = None) -> Path:
    root = data_root or config.data_dir()
    return root / STORE_SUBDIR


def _newest_parquet_mtime(store: Path) -> datetime | None:
    """Return the mtime of the most recently modified .parquet in the store tree, or None."""
    files = glob.glob(str(store / "**" / "*.parquet"), recursive=True)
    if not files:
        return None
    newest_ts = max(os.path.getmtime(f) for f in files)
    return datetime.fromtimestamp(newest_ts, tz=timezone.utc)


def _load_manifest(store: Path) -> dict | None:
    """Return the parsed _manifest.json, or None if absent/unparsable."""
    p = store / "_manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def audit(max_age_days: int = DEFAULT_MAX_AGE_DAYS,
          data_root: Path | None = None) -> dict:
    """Return {ok, fail_reasons, warnings, detail}."""
    store = _store_dir(data_root)
    now = datetime.now(timezone.utc)

    fail: list[str] = []
    warn: list[str] = []
    detail: dict = {
        "now_utc": now.isoformat(),
        "store_dir": str(store),
    }

    # ── store present? ───────────────────────────────────────────────────────
    state_path = store / "_backfill_state.json"
    detail["store_exists"] = store.is_dir()
    detail["state_file_exists"] = state_path.exists()

    if not store.is_dir():
        fail.append(
            "THETADATA DARK: data/thetadata_eod/ directory absent — "
            "backfill has never run or store is missing from this host"
        )
        return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}

    # ── load manifest ─────────────────────────────────────────────────────────
    manifest = _load_manifest(store)
    n_roots = (manifest or {}).get("n_roots", 0)
    detail["manifest_n_roots"] = n_roots
    detail["manifest_updated_at"] = (manifest or {}).get("updated_at")

    # ── parquet inventory ─────────────────────────────────────────────────────
    parquet_files = glob.glob(str(store / "**" / "*.parquet"), recursive=True)
    n_parquets = len(parquet_files)
    detail["n_parquets"] = n_parquets

    # ── never initialized: no state file and no parquets ─────────────────────
    # The state file is git-tracked and committed as an empty skeleton when the store is
    # set up.  Its absence means the store dir was created manually but backfill_thetadata_eod
    # has never run.  Treat as DARK (not in-progress) — no state = not started.
    if not state_path.exists() and n_parquets == 0:
        fail.append(
            "THETADATA DARK: data/thetadata_eod/ exists but _backfill_state.json is absent "
            "and no parquets found — backfill_thetadata_eod has never been run on this host"
        )
        detail["backfill_in_progress"] = False
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    # ── backfill-in-progress grace ─────────────────────────────────────────────
    # Condition: state file exists but no parquets yet (backfill started but not complete),
    # OR manifest shows n_roots == 0 (no root has been fully written yet).
    # In this state we emit INFO and return ok — no screaming during the initial backfill.
    backfill_in_progress = state_path.exists() and (n_parquets == 0 or n_roots == 0)
    detail["backfill_in_progress"] = backfill_in_progress

    if backfill_in_progress:
        detail["status"] = "backfill_in_progress"
        warn.append(
            "THETADATA BACKFILL IN PROGRESS: state file present but store has "
            f"n_roots={n_roots}, n_parquets={n_parquets} — "
            "initial backfill is underway; freshness check skipped until first root completes"
        )
        return {"ok": True, "fail_reasons": [], "warnings": warn, "detail": detail}

    # ── steady-state freshness check ──────────────────────────────────────────
    newest_mtime = _newest_parquet_mtime(store)
    detail["newest_parquet_mtime"] = newest_mtime.isoformat() if newest_mtime else None

    if newest_mtime is None:
        # State file present + n_roots > 0 but no actual parquets — unusual (possible if
        # parquets were deleted but state/manifest were not); treat as stale, not backfill.
        fail.append(
            "THETADATA STALE: manifest claims roots are completed but no parquets found — "
            "store may have been wiped; re-run backfill from this host"
        )
        return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}

    age_days = (now - newest_mtime).total_seconds() / 86400.0
    detail["newest_parquet_age_days"] = round(age_days, 2)
    detail["max_age_days"] = max_age_days

    if age_days > max_age_days:
        fail.append(
            f"THETADATA STALE: newest parquet is {age_days:.1f} days old "
            f"(limit {max_age_days}d, n_roots={n_roots}, n_parquets={n_parquets}) — "
            "nightly collect may have missed or Theta Terminal may be down"
        )
    else:
        detail["status"] = "ok"

    # ── state file mtime cross-check ─────────────────────────────────────────
    if state_path.exists():
        state_mtime_ts = os.path.getmtime(state_path)
        state_mtime = datetime.fromtimestamp(state_mtime_ts, tz=timezone.utc)
        state_age_days = (now - state_mtime).total_seconds() / 86400.0
        detail["state_mtime"] = state_mtime.isoformat()
        detail["state_age_days"] = round(state_age_days, 2)
        # If state file hasn't been touched in >2× max_age_days but parquets exist, warn.
        if state_age_days > max_age_days * 2 and not fail:
            warn.append(
                f"THETADATA STATE STALE: _backfill_state.json last updated "
                f"{state_age_days:.1f} days ago (> {max_age_days * 2}d) — "
                "nightly incremental collect may not be running"
            )

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on any STALE/DARK finding (default: report-only)")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                    help=f"max days since newest parquet before STALE (default: {DEFAULT_MAX_AGE_DAYS})")
    args = ap.parse_args()

    report = audit(max_age_days=args.max_age_days)

    # Write observability artifact (non-fatal if it fails)
    try:
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": datetime.now(timezone.utc).isoformat(), **report}
        (out_dir / "thetadata_accrual_audit.json").write_text(
            json.dumps(doc, indent=2) + "\n"
        )
    except Exception as e:  # noqa: BLE001
        print(f"::warning::thetadata_accrual_audit: could not write audit json: {e}")

    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"] and not report["fail_reasons"]:
        print("ThetaData accrual OK")
    for f in report["fail_reasons"]:
        print(f"::error::{f}")
    if not report["ok"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
