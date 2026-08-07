"""Tripwire for the gated Tushare plane going quietly cold.

WHY THIS EXISTS. collectors/tushare_client.py returns ``None`` — never raises —
for every failure mode it has: no token, endpoint error, access denied, credits
short, empty response. Its callers then omit the leg rather than write a zero
(correct: a fabricated 0 flow would be worse than a gap). asia-close's collect
step is `graceful degradation — never fails on one source`. The union of those
three correct decisions is that the whole Tushare plane can die and every signal
we have stays green: the workflow succeeds, the page rebuilds on schedule, and it
prints a three-week-old `as of` date in exactly the same confident type as a
live one.

That is not hypothetical. data/tushare/flow_hist.parquet and moneyflow.parquet
both froze at 2026-07-24 and were still being rendered on flow_velocity.html on
2026-08-06 — thirteen days — while china_lhb, collected by the SAME adapter list
in the SAME run, stayed current. Nobody was told.

ANCHORED TO THE WALL CLOCK, deliberately. The obvious version of this check
compares the store against its own newest row, or against a sibling store — and
both read "fresh" during a total outage, because a frozen feed is perfectly
self-consistent. So the comparison is against the exchange calendar's expected
last session, which keeps advancing whether or not the collector ever runs again.

CALENDAR CAVEAT. There is no mainland A-share calendar in lib/; HKEX is the
closest proxy and shares most holidays. It diverges on mainland-only closures —
Golden Week (Oct 1-7) most notably — where HKEX trades and Shanghai does not, so
this can warn benignly for a few days each October. That is priced in on purpose:
this emits a ::warning, never a failure, and a benign October warning is a much
cheaper error than silently serving stale flow data for a fortnight.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib import config, hk_calendar  # noqa: E402

# The token-gated stores, and the collector that fills each — named so the
# annotation tells the operator which leg to look at, not just "something is old".
STORES: tuple[tuple[str, str], ...] = (
    ("tushare/flow_hist.parquet", "tushare_moneyflow / tushare_history"),
    ("tushare/moneyflow.parquet", "tushare_moneyflow"),
)

# Sessions behind the expected last close before we say anything. 3 absorbs a
# long weekend plus one public holiday and the collector's own once-a-day cadence
# (asia-close gates every slot after the day's first real run to a no-op), so a
# healthy plane never trips it.
MAX_SESSIONS_BEHIND = 3


def _latest_date(rel: str) -> str | None:
    """Newest trade date in a store, or None when it is absent/unreadable/empty."""
    p = config.data_dir() / rel
    if not p.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_parquet(p)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    for col in ("date", "trade_date", "asof", "as_of", "dt"):
        if col in df.columns:
            s = pd.to_datetime(df[col].astype(str), errors="coerce").max()
            return None if s is None or s is pd.NaT else str(s)[:10]
    return None


def sessions_between(newest: str, expected: date) -> int:
    """HKEX sessions strictly after `newest` up to and including `expected`."""
    try:
        d = datetime.strptime(newest, "%Y-%m-%d").date()
    except ValueError:
        return 10_000
    n = 0
    while d < expected and n < 10_000:
        d += timedelta(days=1)
        if hk_calendar.is_session(d):
            n += 1
    return n


def evaluate(newest: str | None, expected: date) -> tuple[str, int]:
    """('fresh'|'stale'|'absent', sessions_behind)."""
    if newest is None:
        return "absent", -1
    behind = sessions_between(newest, expected)
    return ("stale" if behind > MAX_SESSIONS_BEHIND else "fresh"), behind


def run(now: datetime | None = None) -> int:
    expected = hk_calendar.expected_last_session(now)
    bad: list[str] = []
    for rel, owner in STORES:
        newest = _latest_date(rel)
        status, behind = evaluate(newest, expected)
        if status == "fresh":
            print(f"tushare freshness OK: {rel} at {newest} ({behind} session(s) behind {expected})")
            continue
        bad.append(
            f"{rel} at {newest or 'ABSENT'} — {'no readable rows' if behind < 0 else str(behind) + ' sessions'} "
            f"behind expected {expected} (filled by {owner})"
        )
    if not bad:
        return 0
    # Bare print, line-start, flushed: a logger would prefix the line and GitHub
    # would silently drop the annotation (tests/test_gh_annotation_line_start.py).
    print(
        "::warning title=tushare plane cold::"
        + "; ".join(bad)
        + ". The Tushare client returns None and never raises, so the collect step stays green "
        "and pages keep rendering the old as-of date. Check TUSHARE_TOKEN is set and the "
        "membership/积分 tier still covers moneyflow_dc (5000积分).",
        flush=True,
    )
    return 0  # advisory: never red the collection lane over one gated source


def selftest() -> int:
    exp = date(2026, 8, 6)  # a Thursday, HKEX session
    checks = [
        (evaluate(None, exp)[0] == "absent", "a missing store must read absent"),
        (evaluate("2026-08-05", exp)[0] == "fresh", "yesterday must be fresh"),
        (evaluate("2026-07-24", exp)[0] == "stale", "the 2026-07-24 freeze must be stale"),
        # The bug this guard exists for: a self-relative check would call a frozen
        # store fresh because it equals its own newest row. Anchoring to the
        # calendar is what makes the 13-day gap visible.
        (sessions_between("2026-07-24", exp) > MAX_SESSIONS_BEHIND,
         "the real incident must exceed the threshold"),
        (sessions_between("2026-08-06", exp) == 0, "same day is zero sessions behind"),
        (evaluate("not-a-date", exp)[0] == "stale", "an unparseable date must not read fresh"),
    ]
    bad = [m for ok, m in checks if not ok]
    for m in bad:
        print(f"selftest FAIL: {m}")
    print("check_tushare_freshness selftest: " + ("OK" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run calendar/threshold pins and exit")
    a = ap.parse_args(argv)
    return selftest() if a.selftest else run()


if __name__ == "__main__":
    raise SystemExit(main())
