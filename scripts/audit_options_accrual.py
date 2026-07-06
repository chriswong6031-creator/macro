"""Options accrual freshness tripwire (dead-man's switch for OI + flow accrual).

OI is point-in-time only — every missed snapshot day is permanently lost. This
audit is the circuit-breaker visibility layer described in the Options Alpha
masterplan §W0.4: if the chains/ directory hasn't been updated within 1 trading
day, emit a ::warning:: so the CI run surfaces the gap.

Also checks that the options-flow S3 creds are present (MASSIVE_S3_ACCESS_KEY_ID),
since a missing-creds failure in build_options_flow is otherwise a silent no-op.

Writes data/quality/options_accrual_audit.json (observability; read-only over stores).
Stdlib + pandas only — no heavy deps.

Usage: python -m scripts.audit_options_accrual [--strict] [--max-age-days 1]
       --strict: exit 1 on stale (default: warn + exit 0)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

DEFAULT_MAX_AGE_DAYS = 1   # chains/ latest file must be ≤ 1 trading day old


def _is_trading_day(d: date) -> bool:
    """Rough US trading-day check: Mon–Fri, excluding a small set of fixed holidays.
    Sufficient for the 'stale by 1 day' tripwire; does not need to be exhaustive."""
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    # Fixed-date US market holidays (no need for exact exhaustive list — just the
    # major ones that could cause false alarms)
    year = d.year
    fixed = {
        date(year, 1, 1),   # New Year's Day
        date(year, 7, 4),   # Independence Day
        date(year, 12, 25), # Christmas
    }
    return d not in fixed


def _last_trading_day(ref: date | None = None) -> date:
    """Most recent trading day on or before ref (default: today UTC)."""
    d = ref or datetime.now(timezone.utc).date()
    while not _is_trading_day(d):
        d -= timedelta(days=1)
    return d


def _latest_chain_date(chains_dir: Path) -> date | None:
    """Date of the most recent chains/*.parquet file, or None if no files."""
    files = sorted(glob.glob(str(chains_dir / "*.parquet")))
    if not files:
        return None
    stem = Path(files[-1]).stem   # e.g. "2026-07-02"
    try:
        return datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def audit(max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict:
    """Return {ok, fail_reasons, warnings, detail}."""
    data_root = config.data_dir()
    chains_dir = data_root / "polygon_gex" / "chains"
    today_utc = datetime.now(timezone.utc).date()
    last_td = _last_trading_day(today_utc)

    fail: list[str] = []
    warn: list[str] = []
    detail: dict = {
        "today_utc": str(today_utc),
        "last_trading_day": str(last_td),
        "chains_dir": str(chains_dir),
    }

    # ── chains/ freshness ────────────────────────────────────────────────────
    latest = _latest_chain_date(chains_dir)
    detail["chains_latest_date"] = str(latest) if latest else None
    detail["chains_count"] = len(glob.glob(str(chains_dir / "*.parquet")))

    if latest is None:
        fail.append("CHAINS DARK: data/polygon_gex/chains/ has no parquet files — "
                    "polygon_gex collector has never run or the store is missing")
    else:
        age = (last_td - latest).days
        detail["chains_age_trading_days"] = age
        if age > max_age_days:
            fail.append(
                f"CHAINS STALE: latest chain file is {latest} "
                f"({age} trading day(s) behind last_td={last_td}); "
                f"threshold={max_age_days}d — OI snapshot may have been missed"
            )
        elif age == max_age_days:
            warn.append(
                f"CHAINS AT LIMIT: latest chain file is {latest} "
                f"(exactly {age} trading day(s) behind last_td={last_td}) — "
                "OK today but will trip if tomorrow's accrual is missed"
            )

    # ── options-flow S3 creds ────────────────────────────────────────────────
    ak = os.environ.get("MASSIVE_S3_ACCESS_KEY_ID", "")
    sk = os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY", "")
    ep = os.environ.get("MASSIVE_S3_ENDPOINT", "")
    creds_ok = bool(ak and sk and ep)
    detail["options_flow_creds_present"] = creds_ok
    if not creds_ok:
        warn.append(
            "OPTIONS FLOW CREDS ABSENT: MASSIVE_S3_ACCESS_KEY_ID / "
            "MASSIVE_S3_SECRET_ACCESS_KEY / MASSIVE_S3_ENDPOINT not set — "
            "build_options_flow will no-op silently (F1 from masterplan §1)"
        )

    # ── options-flow summary accrual ─────────────��───────────────────────────
    flow_dir = data_root / "options_flow"
    flow_files = list(flow_dir.glob("summary_*.parquet")) if flow_dir.exists() else []
    detail["options_flow_summary_count"] = len(flow_files)
    if creds_ok and not flow_files:
        warn.append(
            "OPTIONS FLOW SUMMARIES ABSENT: creds are present but "
            "data/options_flow/summary_*.parquet is empty — "
            "build_options_flow may not have run yet"
        )

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on any STALE/DARK finding (default: report-only)")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                    help=f"max trading days behind last_td before STALE (default: {DEFAULT_MAX_AGE_DAYS})")
    args = ap.parse_args()

    report = audit(max_age_days=args.max_age_days)

    # Write observability artifact (non-fatal if it fails)
    try:
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": datetime.now(timezone.utc).isoformat(), **report}
        (out_dir / "options_accrual_audit.json").write_text(json.dumps(doc, indent=2) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"::warning::options_accrual_audit: could not write audit json: {e}")

    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"]:
        print("Options accrual OK")
    for f in report["fail_reasons"]:
        print(f"::error::{f}")
    if not report["ok"] and args.strict:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Collect step hook (W-OC wiring — NEXT3 PR-β)
# ---------------------------------------------------------------------------

def run_as_collect_step() -> None:
    """End-of-collect hook — wraps audit() + write; must never raise.

    Called from scripts/collect.py after the options accrual steps so the
    options entry coverage audit (audit_options_entry_coverage.py) can read the
    freshly updated options_accrual_audit.json for its consistency section.
    Idempotent; non-fatal.
    """
    import logging as _logging
    _log = _logging.getLogger("audit_options_accrual")
    try:
        report = audit()
        # Write observability artifact
        try:
            from datetime import datetime as _dt, timezone as _tz
            import json as _json
            from lib import config as _config
            out_dir = _config.data_dir() / "quality"
            out_dir.mkdir(parents=True, exist_ok=True)
            doc = {"generated_at": _dt.now(_tz.utc).isoformat(), **report}
            (out_dir / "options_accrual_audit.json").write_text(
                _json.dumps(doc, indent=2) + "\n"
            )
            _log.info("audit_options_accrual: wrote options_accrual_audit.json")
        except Exception as write_exc:  # noqa: BLE001
            _log.warning("audit_options_accrual: write failed (non-fatal): %s", write_exc)
        for w in report.get("warnings", []):
            _log.warning("audit_options_accrual: %s", w)
        for f in report.get("fail_reasons", []):
            _log.error("audit_options_accrual: %s", f)
    except Exception as exc:  # noqa: BLE001
        _log.error("[audit_options_accrual] collect step crashed (non-fatal): %s", exc)


if __name__ == "__main__":
    sys.exit(main())
