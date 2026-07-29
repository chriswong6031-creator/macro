"""MLC-W5 earnings freshness tripwire (dead-man's switch for the earnings calendar store).

The earnings store (data/earnings/earnings.parquet) is written nightly by the
collectors/equity_earnings.py sweep that was wired in MLC-W5.  If that step is
bot-walled (Akamai 403 from a CI IP), the existing cache is retained untouched —
which means the as_of age keeps climbing.  This tripwire surfaces that silently,
emitting a ::warning:: so CI shows a gap without failing the build.

The SLA is 2 trading days: if the store's most-recent as_of is older than 2 td,
we emit a warning.  The trading-day calendar uses the same bdate_range fallback
as engine/earnings_blackout.py (holiday-blind, same documented imprecision).

COVERAGE (OIP E8, 2026-07-29) — the tripwire was blind to the failure it existed
to catch.  It graded ``max(as_of)`` only, so on 2026-07-29 it returned
``ok: true, warnings: [], sla_ok: true`` over a store where 1361 of 1364 rows
carried a 2026-06-19 stamp and exactly THREE (AAPL/NVDA/JPM) were fresh — the
hardcoded smoke-test trio from ``collectors/equity_earnings.__main__``, which
daily.yml was invoking as if it were the production sweep.  One fresh row is
enough to satisfy a max-based SLA, which is the presence-vs-coverage class: the
audit reported a green that described three tickers and implied 1364.
So the age check is now paired with a FRESH-SHARE check, and a store that is
stale AT SCALE escalates to ``::error`` instead of hiding.  The SLA itself is
NOT widened — a stale store still says so, just louder and with a denominator.

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
# Coverage floor: the share of ROWS whose own as_of is inside the SLA.  A real
# whole-universe sweep leaves the large majority fresh — the 66-weekday calendar
# window covered 1066 of a 1513-name universe on 2026-07-29 (70.5%), and names
# reporting beyond that window legitimately carry their previous stamp forward.
# 0.50 sits well clear of both sides of the observed failure (0.2% fresh) and the
# observed healthy sweep (70.5% fresh).
MIN_FRESH_SHARE = 0.50


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
    """Return {ok, fail_reasons, warnings, errors, detail}.

    ``errors`` is the loud channel: the staleness is real, at scale, and the
    caller should print a line-start ``::error`` for it.  It never fails the
    build (see run_as_main) — the nightly step is non-fatal by design.
    """
    data_root = config.data_dir()
    store_path = data_root / "earnings" / "earnings.parquet"
    today_utc = datetime.now(timezone.utc).date()

    fail: list[str] = []
    warn: list[str] = []
    errors: list[str] = []
    detail: dict = {
        "today_utc": str(today_utc),
        "store_path": str(store_path),
        "store_present": store_path.exists(),
        "as_of_str": None,
        "as_of_age_td": None,
        "ticker_count": None,
        "with_next_date": None,
        "fresh_rows": None,
        "fresh_share": None,
        "min_fresh_share": MIN_FRESH_SHARE,
        "max_age_td": max_age_td,
    }

    if not store_path.exists():
        fail.append("earnings.parquet not found — collector has never run on this runner")
        return {"ok": False, "fail_reasons": fail, "warnings": warn,
                "errors": errors, "detail": detail}

    try:
        import pandas as pd
        df = pd.read_parquet(store_path)
    except Exception as exc:  # noqa: BLE001
        fail.append(f"earnings.parquet unreadable: {exc}")
        return {"ok": False, "fail_reasons": fail, "warnings": warn,
                "errors": errors, "detail": detail}

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
        return {"ok": True, "fail_reasons": fail, "warnings": warn,
                "errors": errors, "detail": detail}
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
        return {"ok": False, "fail_reasons": fail, "warnings": warn,
                "errors": errors, "detail": detail}

    try:
        most_recent_str = as_of_col.dropna().max()
        import pandas as pd
        as_of_ts = pd.Timestamp(str(most_recent_str))
        if as_of_ts.tzinfo is not None:
            as_of_ts = as_of_ts.tz_convert(None)
        as_of_date = as_of_ts.date()
    except Exception as exc:  # noqa: BLE001
        fail.append(f"as_of value unparseable: {exc}")
        return {"ok": False, "fail_reasons": fail, "warnings": warn,
                "errors": errors, "detail": detail}

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

    # ── Coverage: how much of the store is ACTUALLY inside the SLA ──────────
    # The max-based check above passes on a single fresh row.  Grade the share.
    fresh_rows = 0
    for raw in as_of_col.dropna().astype(str):
        try:
            ts = pd.Timestamp(raw)
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        row_age = _bdate_range_age(ts.date(), today_utc)
        if row_age is not None and row_age <= max_age_td:
            fresh_rows += 1
    share = fresh_rows / len(df) if len(df) else 0.0
    detail["fresh_rows"] = fresh_rows
    detail["fresh_share"] = round(share, 4)

    if share < MIN_FRESH_SHARE:
        msg = (
            f"earnings store stale AT SCALE: only {fresh_rows} of {len(df)} rows "
            f"({share:.1%}) carry an as_of inside the {max_age_td}-td SLA "
            f"(floor {MIN_FRESH_SHARE:.0%}). The newest stamp ({as_of_date}) is fresh, so "
            "an age-only check reads green — that is the presence-vs-coverage trap. "
            "Most likely the sweep is running against a tiny ticker list instead of the "
            "full universe, or is bot-walled after its first calls."
        )
        # LOUD when the store is big enough for the share to mean something; a
        # sub-plausibility store already has its own warning above.
        (errors if len(df) >= MIN_TICKER_PLAUSIBILITY else warn).append(msg)
    else:
        detail["coverage_ok"] = True

    return {"ok": len(fail) == 0, "fail_reasons": fail, "warnings": warn,
            "errors": errors, "detail": detail}


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
        print("audit_earnings_freshness: wrote earnings_freshness_audit.json", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=earnings-audit-artifact::audit_earnings_freshness: "
              f"could not write audit json: {exc}", flush=True)

    # Every annotation below is a BARE print starting at column 0 with flush=True —
    # never a logger (a "%(levelname)s " prefix pushes "::" off the line start and
    # GitHub silently drops the whole annotation; tests/test_gh_annotation_line_start.py).
    for e in result.get("errors", ()):
        print(f"::error title=earnings-stale::earnings_freshness: {e}", flush=True)

    for w in result["warnings"]:
        print(f"::warning title=earnings-freshness::earnings_freshness: {w}", flush=True)

    for f in result["fail_reasons"]:
        level = "error" if strict else "warning"
        print(f"::{level} title=earnings-freshness::earnings_freshness: {f}", flush=True)

    if not result["ok"] and strict:
        return 1
    if (result["warnings"] or result.get("errors")) and strict:
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
