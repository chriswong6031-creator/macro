"""Options surface accrual liveness audit (dead-man's switch for W2 SURFACE accrual).

Mirrors scripts/audit_thetadata_accrual.py. A dead accrual — state file present but
newest parquet mtime too old — emits an error and exits 1 when --strict is passed.

Two operating states:
  BACKFILL IN PROGRESS — state file exists but parquets are absent or the state
    shows no completed roots. Emits INFO + returns ok (no screaming during initial
    backfill).

  STEADY STATE — at least one parquet is present. Freshness check: newest parquet
    mtime must be ≤ max_age_days behind now. Stale → WARN/FAIL.

Writes data/quality/options_surface_accrual_audit.json.

Usage:
    python -m scripts.audit_options_surface_accrual [--strict] [--max-age-days 3]
    --strict: exit 1 on STALE/DARK findings
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

_STORE_SUBDIR = "options_surface"
DEFAULT_MAX_AGE_DAYS = 3


def _store_dir(data_root: Path | None = None) -> Path:
    root = data_root or config.data_dir()
    return root / _STORE_SUBDIR


def _newest_parquet_mtime(store: Path) -> datetime | None:
    files = glob.glob(str(store / "*.parquet"))
    if not files:
        return None
    newest_ts = max(os.path.getmtime(f) for f in files)
    return datetime.fromtimestamp(newest_ts, tz=timezone.utc)


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

    state_path = store / "_backfill_state.json"
    detail["store_exists"] = store.is_dir()
    detail["state_file_exists"] = state_path.exists()

    if not store.is_dir():
        fail.append(
            "OPTIONS_SURFACE DARK: data/options_surface/ directory absent — "
            "W2 SURFACE builder has never run or output is missing from this host"
        )
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    # Inventory parquets
    parquet_files = glob.glob(str(store / "*.parquet"))
    n_parquets = len(parquet_files)
    detail["n_parquets"] = n_parquets

    # Load state
    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:  # noqa: BLE001
            pass

    n_completed_roots = sum(
        len(yrs) for yrs in state.get("completed", {}).values()
    )
    detail["n_completed_root_years"] = n_completed_roots

    # DARK: no state file, no parquets
    if not state_path.exists() and n_parquets == 0:
        fail.append(
            "OPTIONS_SURFACE DARK: data/options_surface/ exists but _backfill_state.json "
            "absent and no parquets found — build_options_surface has never run"
        )
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    # BACKFILL IN PROGRESS grace
    backfill_in_progress = (
        state_path.exists() and (n_parquets == 0 or n_completed_roots == 0)
    )
    detail["backfill_in_progress"] = backfill_in_progress

    if backfill_in_progress:
        warn.append(
            "OPTIONS_SURFACE BACKFILL IN PROGRESS: state file present but "
            f"n_parquets={n_parquets}, n_completed_root_years={n_completed_roots} — "
            "initial backfill underway; freshness check deferred"
        )
        return {"ok": True, "fail_reasons": [], "warnings": warn, "detail": detail}

    # STEADY STATE freshness check
    newest_mtime = _newest_parquet_mtime(store)
    detail["newest_parquet_mtime"] = newest_mtime.isoformat() if newest_mtime else None

    if newest_mtime is None:
        fail.append(
            "OPTIONS_SURFACE STALE: state claims roots completed but no parquets found — "
            "re-run build_options_surface"
        )
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    age_days = (now - newest_mtime).total_seconds() / 86400.0
    detail["newest_parquet_age_days"] = round(age_days, 2)
    detail["max_age_days"] = max_age_days

    if age_days > max_age_days:
        fail.append(
            f"OPTIONS_SURFACE STALE: newest parquet is {age_days:.1f} days old "
            f"(limit {max_age_days}d) — nightly surface accrual may have missed; "
            "check theta-ops launchd lane (theta_surface_accrual.sh)"
        )
    else:
        detail["status"] = "ok"

    # State mtime cross-check
    if state_path.exists():
        state_age_days = (now - datetime.fromtimestamp(
            os.path.getmtime(state_path), tz=timezone.utc
        )).total_seconds() / 86400.0
        detail["state_age_days"] = round(state_age_days, 2)
        if state_age_days > max_age_days * 2 and not fail:
            warn.append(
                f"OPTIONS_SURFACE STATE STALE: _backfill_state.json last updated "
                f"{state_age_days:.1f} days ago (> {max_age_days * 2}d) — "
                "nightly surface accrual may not be running"
            )

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on any STALE/DARK finding")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    args = ap.parse_args()

    report = audit(max_age_days=args.max_age_days)

    try:
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": datetime.now(timezone.utc).isoformat(), **report}
        (out_dir / "options_surface_accrual_audit.json").write_text(
            json.dumps(doc, indent=2) + "\n"
        )
    except Exception as e:  # noqa: BLE001
        print(f"::warning::options_surface_accrual_audit: could not write json: {e}")

    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"] and not report["fail_reasons"]:
        print("OPTIONS_SURFACE accrual OK")
    for f in report["fail_reasons"]:
        print(f"::error::{f}")
    if not report["ok"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
