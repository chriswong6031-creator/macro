"""One-time heal: re-key 涨停板 pool rows stamped with a RUN date instead of a TRADE date.

WHY THIS EXISTS
---------------
Eastmoney's ``stock_zt_pool_em`` does not 404 on a non-session date — asked for any date at
or after the last PUBLISHED session it CLAMPS and serves that session's pool.  The collector
(``collectors/china_zt_pool.py``) walked back from today over raw CALENDAR days, stopped at
the first non-empty response, and stamped ``date`` with the date it had ASKED for.  So every
weekend run relabelled Friday's pool as Saturday, and the next one relabelled it Sunday.

Measured on 2026-08-08, before the heal: 11 of 47 stored dates were not CN trading sessions
(2026-07-04/05, 07-11/12, 07-18/19, 07-25/26, 08-01/02, 08-08), 818 of 3,920 rows — and every
one of them was byte-identical, across all seven payload columns, to the session immediately
before it.  They are re-serves, not observations: 47 "dates" were 36 sessions.

The producer is fixed (the requested date is now resolved against a session calendar before
the fetch, and a payload fingerprint refuses to stamp an already-stored pool under a second
date).  The store, however, ACCRUES, so the fix alone never rewrites what is already on disk.

WHAT IT DOES
------------
Each row's ``date`` is resolved to the most recent CN trading session ON OR BEFORE it, using
the repo's own session calendar (``collectors.china_zt_pool.session_calendar`` — the dates
present in ``data/china_stocks_raw``; no external calendar).  Rows that already carry a
session date are untouched.  Rows that do not are relabelled onto their true session and then
de-duplicated ``(date, ticker)`` keep-LAST, ordered by ``asof`` so the freshest scrape wins —
exactly what the collector's own ``append_snapshot`` would do.

SAFETY
------
- Idempotent: a second run finds every date already on a session and rewrites nothing.
- Never invents rows and never invents a session: a date that resolves to nothing inside the
  calendar (older than the calendar's first session) aborts the file rather than guessing.
- A relabelled payload that DISAGREES with the session it lands on aborts the heal.  Here
  every one is byte-identical, so the merge is a pure drop of re-serves; a future store where
  they differ is a different defect and must be read by a human before anything is collapsed.
- SESSION COVERAGE IS AN ENFORCED INVARIANT: the set of sessions on disk after the heal must
  be a superset of the session-dated rows before it.  A heal may only ever delete a re-serve,
  never a session.
- ``--check`` reports without writing (exit 1 if anything would change).

Usage:
    python3 scripts/heal_cn_zt_pool_dates.py --check
    python3 scripts/heal_cn_zt_pool_dates.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REL = "china_zt_pool/pool.parquet"          # under lib.config.data_dir(), as the collector writes it

# The payload columns that identify one session's pool. `asof` and `date` are excluded on
# purpose: they are provenance, and they are exactly what differs between a re-serve and the
# session it copies.
PAYLOAD = ("ticker", "name", "consec_boards", "seal_fund_yi",
           "failed_seals", "turnover_pct", "sector")


def resolve_to_session(date_str: str, sessions: list[str]) -> str | None:
    """The most recent trading session on or before ``date_str``. None when there is none."""
    import bisect
    i = bisect.bisect_right(sessions, date_str)
    return sessions[i - 1] if i else None


def _payload(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PAYLOAD if c in df.columns]
    return df[cols].sort_values(cols[:1] or cols).reset_index(drop=True)


def heal(path: Path, sessions: frozenset[str], *, write: bool) -> tuple[int, str]:
    if not path.exists():
        return 0, "missing"
    df = pd.read_parquet(path).reset_index(drop=True)
    if "date" not in df.columns:
        return 0, "no date column"
    if not sessions:
        return 0, "ABORT: no session calendar (data/china_stocks_raw missing) — cannot resolve"

    ordered = sorted(sessions)
    before = df["date"].astype(str)
    off = ~before.isin(sessions)
    n = int(off.sum())
    if not n:
        return 0, "clean"

    mapping: dict[str, str] = {}
    for d in sorted(before[off].unique()):
        tgt = resolve_to_session(d, ordered)
        if tgt is None:
            return 0, f"ABORT: {d} precedes the session calendar — resolve by hand"
        mapping[d] = tgt

    # A relabelled payload must AGREE with the session it lands on, or the collapse would
    # silently pick one of two genuinely different observations.
    for src, tgt in mapping.items():
        if tgt not in set(before):
            continue                                   # recovers a session we never stored
        if not _payload(df[before == src]).equals(_payload(df[before == tgt])):
            return 0, (f"ABORT: {src} carries a pool that DIFFERS from session {tgt} — "
                       "not a re-serve, read it by hand")

    if not write:
        detail = ", ".join(f"{s}->{t}" for s, t in sorted(mapping.items()))
        return n, f"would re-key {n} row(s) across {len(mapping)} date(s): {detail}"

    sessions_before = set(before[~off])
    healed = before.map(lambda d: mapping.get(d, d))
    order = df["asof"].astype(str) if "asof" in df.columns else pd.Series("", index=df.index)
    out = (df.assign(date=healed, _o=order)
             .sort_values(["date", "_o"], kind="stable")
             .drop_duplicates(subset=["date", "ticker"], keep="last")
             .drop(columns="_o")
             .sort_values(["date", "ticker"], kind="stable")
             .reset_index(drop=True))

    after = set(out["date"].astype(str))
    if not after.issubset(sessions):
        return 0, "ABORT: a non-session date survived the heal"
    if not sessions_before.issubset(after):
        return 0, f"ABORT: heal would delete session(s) {sorted(sessions_before - after)}"
    out.to_parquet(path, index=False)
    return n, (f"re-keyed {n} row(s) across {len(mapping)} date(s); "
               f"rows {len(df)} -> {len(out)}, dates {before.nunique()} -> {len(after)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing (exit 1 if anything would)")
    args = ap.parse_args()

    from lib import config
    from collectors.china_zt_pool import session_calendar

    n, note = heal(config.data_dir() / REL, session_calendar(), write=not args.check)
    print(f"  {REL:<40s} {note}")
    if note.startswith("ABORT"):
        print("\nheal ABORTED — nothing written.")
        return 2
    if args.check:
        return 1 if n else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
