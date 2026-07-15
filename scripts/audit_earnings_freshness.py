"""MLC-W5 earnings freshness tripwire (dead-man's switch for the earnings calendar store).

The earnings store (data/earnings/earnings.parquet) is written nightly by the
collectors/equity_earnings.py sweep that was wired in MLC-W5.  If that step is
bot-walled (Akamai 403 from a CI IP), the existing cache is retained untouched —
which means the as_of age keeps climbing.  This tripwire surfaces that silently,
emitting a ::warning:: so CI shows a gap without failing the build.

The SLA is 2 trading days: if the store's most-recent as_of is older than 2 td,
we emit a warning.  The trading-day calendar uses the same bdate_range fallback
as engine/earnings_blackout.py (holiday-blind, same documented imprecision).

Writes data/quality/earnings_freshness_audit.json for observability (read by
healthcheck / committee pages that scan for data-quality artifacts).

Usage:  python -m scripts.audit_earnings_freshness [--strict] [--max-age-td 2]
        --strict: exit 1 when stale (default: warn + exit 0)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

DEFAULT_MAX_AGE_TD = 2       # trading days: warn when as_of older than this
# Plausibility floor: fewer than this many tickers in the store indicates a
# near-empty sweep (the documented bug wrote 4 rows from a ~1363-name universe).
# 50 is intentionally conservative — any real sweep will far exceed it.
MIN_TICKER_PLAUSIBILITY = 50


def _bdate_range_age(from_date: date, to_date: date) -> int | None:
    """Approximate trading-day distance from from_date to to_date via bdate_range.

    Returns None when either date is out of range.  Holiday-blind (same known
    imprecision as engine/earnings_blackout._build_td_calendar — errs toward
    reporting fresh, never toward false-stale alarms).
    """
    import pandas as pd
    try:
        cal = pd.bdate_range(from_date, to_date)
        # bdate_range includes both endpoints; distance = len - 1
        return max(0, len(cal) - 1)
    except Exception:  # noqa: BLE001
        return None


def audit(max_age_td: int = DEFAULT_MAX_AGE_TD) -> dict:
    """Return {ok, fail_reasons, warnings, detail}."""
    data_root = config.data_dir()
    store_path = data_root / "earnings" / "earnings.parquet"
    today_utc = datetime.now(timezone.utc).date()

    fail: list[str] = []
    warn: list[str] = []
    detail: dict = {
        "today_utc": str(today_utc),
        "store_path": str(store_path),
        "store_present": store_path.exists(),
        "as_of_str": None,
        "as_of_age_td": None,
        "ticker_count": None,
        "with_next_date": None,
        "max_age_td": max_age_td,
    }

    if not store_path.exists():
        fail.append("earnings.parquet not found — collector has never run on this runner")
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    try:
        import pandas as pd
        df = pd.read_parquet(store_path)
    except Exception as exc:  # noqa: BLE001
        fail.append(f"earnings.parquet unreadable: {exc}")
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    detail["ticker_count"] = len(df)
    if "next_date" in df.columns:
        detail["with_next_date"] = int(df["next_date"].notna().sum())

    # ── Emptiness guards (the postmortem "store_stale: true, count: 0" failure shape) ──
    # These fire BEFORE the as_of age check so a fresh-but-empty store is caught
    # even when the timestamp looks recent (the exact failure mode from 07-13).
    if len(df) == 0:
        warn.append(
            "earnings store present but EMPTY (ticker_count=0) — the calendar sweep "
            "may have written a zero-row result; check equity_earnings collector logs"
        )
        # Cannot check as_of age with 0 rows — emit the warning and short-circuit.
        return {"ok": True, "fail_reasons": fail, "warnings": warn, "detail": detail}
    elif len(df) < MIN_TICKER_PLAUSIBILITY:
        warn.append(
            f"earnings store suspiciously small: ticker_count={len(df)} "
            f"(plausibility floor={MIN_TICKER_PLAUSIBILITY}) — the collector may have "
            "written a near-empty result (historical bug: 1363-name sweep wrote 4 rows)"
        )
    if ("next_date" in df.columns
            and int(df["next_date"].notna().sum()) == 0):
        warn.append(
            "earnings store has rows but with_next_date=0 — the calendar sweep "
            "collected tickers but found no upcoming dates; collector may be bot-walled "
            "or the date-carry logic failed"
        )

    # Determine the store's as_of age
    as_of_col = df.get("as_of") if hasattr(df, "get") else None
    if as_of_col is None or (hasattr(as_of_col, "empty") and as_of_col.empty):
        fail.append("as_of column missing or empty — store is structurally incomplete")
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    try:
        most_recent_str = as_of_col.dropna().max()
        import pandas as pd
        as_of_ts = pd.Timestamp(str(most_recent_str))
        if as_of_ts.tzinfo is not None:
            as_of_ts = as_of_ts.tz_convert(None)
        as_of_date = as_of_ts.date()
    except Exception as exc:  # noqa: BLE001
        fail.append(f"as_of value unparseable: {exc}")
        return {"ok": False, "fail_reasons": fail, "warnings": warn, "detail": detail}

    detail["as_of_str"] = str(most_recent_str)
    age_td = _bdate_range_age(as_of_date, today_utc)
    detail["as_of_age_td"] = age_td

    if age_td is None:
        warn.append(f"could not compute trading-day age for as_of={as_of_date}")
    elif age_td > max_age_td:
        warn.append(
            f"earnings store stale: as_of={as_of_date} is {age_td} trading days old "
            f"(>{max_age_td} td SLA) — the earnings calendar sweep may be bot-walled "
            f"or the collector step is not reaching the store write"
        )
    else:
        detail["sla_ok"] = True

    return {"ok": len(fail) == 0, "fail_reasons": fail, "warnings": warn, "detail": detail}


def run_as_main(strict: bool = False, max_age_td: int = DEFAULT_MAX_AGE_TD) -> int:
    """Entry point for `python -m scripts.audit_earnings_freshness`."""
    result = audit(max_age_td=max_age_td)

    # Write the observability artifact to data/quality/
    try:
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            **result,
        }
        (out_dir / "earnings_freshness_audit.json").write_text(
            json.dumps(doc, indent=2, default=str) + "\n"
        )
        print("audit_earnings_freshness: wrote earnings_freshness_audit.json")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::audit_earnings_freshness: could not write audit json: {exc}")

    # Surface warnings to CI
    for w in result["warnings"]:
        print(f"::warning::earnings_freshness: {w}")

    for f in result["fail_reasons"]:
        if strict:
            print(f"::error::earnings_freshness: {f}")
        else:
            print(f"::warning::earnings_freshness: {f}")

    if not result["ok"] and strict:
        return 1
    if result["warnings"] and strict:
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Earnings freshness tripwire")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when stale (default: warn + exit 0)")
    parser.add_argument("--max-age-td", type=int, default=DEFAULT_MAX_AGE_TD,
                        help=f"Max trading-day age before warning (default: {DEFAULT_MAX_AGE_TD})")
    args = parser.parse_args()
    sys.exit(run_as_main(strict=args.strict, max_age_td=args.max_age_td))
