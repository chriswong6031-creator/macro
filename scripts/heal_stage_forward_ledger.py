"""Heal data/stage_analysis/forward_ledger.jsonl — data-plane session stamps.

One-time-but-idempotent data heal (forward-ledger calendar-asof audit
2026-08-05, sibling of the basket-turn and Ignition Radar heals in #4568).

WHY THE DATES MOVE.  The pre-fix writer stamped every ledger row's `date` from
`contract["asof"]`, and `engine.stage_analysis.build_context_feed` defaulted
that to `datetime.now(timezone.utc)`.  The nightly runs 20:00-22:30 **PT**, so
the UTC date is already the NEXT calendar day.  Measured against the row-batch
commits: all 13 committed batches were committed on the PT evening BEFORE the
date they stamped (e.g. commit 2026-08-03T21:30 PT -> rows stamped 2026-08-04;
commit 2026-07-25T20:02 PT -> rows stamped 2026-07-26, a Saturday run wearing a
Sunday date).  180 of the 780 committed rows carry weekend dates.  This file is
the engine's ONLY point-in-time record of which names were fresh Stage 2 on a
given session, and every read of it is date-keyed (the Prophet US §9
"stage-ran shelf" study), so the drift is not cosmetic.

EVIDENCE = THE TICKER'S OWN COMMITTED FRAME.  Per row, the session index is
read the way the engine reads prices (`stage_analysis._load_prices` order):
`data/baskets/ohlcv/<ticker>.parquet` preferred, else
`data/stocks/<ticker>.parquet`.  Session dates are APPEND-ONLY for the past — a
date present in today's index was a real session then, and a date absent from
it was never one — so today's frames are valid evidence about July/August rows.

Per row:

1. The row's `date` is present in that ticker's index -> HONEST, untouched.

2. Otherwise the true session is the latest index date <= `date` (the newest
   tape the run could actually have read).  The row is RESTAMPED in place:
   `date` := the true session, plus `session_inferred=true`,
   `original_date=<old>`, `session_source="ticker_frame"`.

3. A restamp whose (ticker, true session) slot is already taken (by an honest
   row, or by an earlier restamp — honest rows win, then first-writer by file
   order) is QUARANTINED into forward_ledger_quarantine.jsonl with a
   `quarantine_reason`, a `quarantined_kept_row` pointer and `quarantined_at`.
   Nothing is ever deleted.  A re-description of already-recorded tape is not
   an independent observation.

4. MERGES a provenance block into forward_ledger_meta.json: quarantine pointer
   + counts + healed_by + last_heal, the pre-fix stamp explanation above, and
   one `known_gaps` entry per distinct original date recording that the
   calendar date is not evidence about that session.

FAIL-CLOSED: a ticker with no readable frame, or a row with no index date at or
before its stamp, aborts the ENTIRE heal (nothing written) — its true session
cannot be known from committed data.

KNOWN RESIDUAL (deliberate, not a bug).  This rule moves only what committed
data PROVES was never a session for that ticker: weekend/holiday stamps and
stamps past the store's newest bar.  The commit-time evidence says the ledger
is uniformly one session late, but a stamp that happens to name a real session
for that ticker (Tuesday's stamp on Monday's tape) is indistinguishable from an
honest row in the frame index alone, so it is LEFT ALONE.  The heal is
conservative by construction; it is not a claim that the survivors are exact.

Usage:
    python3 scripts/heal_stage_forward_ledger.py [--root DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

_QUARANTINE_REASON = (
    "duplicate re-description of an already-recorded session stamped under a "
    "fresh calendar date (UTC-date-on-a-PT-evening-run stamp; forward-ledger "
    "calendar-asof audit 2026-08-05)"
)

_PRE_FIX_STAMP_NOTE = (
    "pre-fix rows were stamped from contract['asof'] = "
    "datetime.now(timezone.utc); the nightly runs 20:00-22:30 PT so the UTC "
    "date was already the next calendar day — all 13 committed row batches "
    "were committed on the PT evening BEFORE the date they stamped (e.g. "
    "commit 2026-08-03T21:30 PT -> rows stamped 2026-08-04), leaving the "
    "ledger +1 against the tape with 180/780 rows on weekend dates"
)

_RESIDUAL_NOTE = (
    "conservative rule: only stamps that committed frames prove were never a "
    "session for that ticker were moved; a stamp naming a real session one bar "
    "after the tape it describes is indistinguishable in the frame index and "
    "was left in place"
)

#: Price-store preference, mirroring engine.stage_analysis._load_prices.
_STORE_ORDER = ("baskets/ohlcv", "stocks")


# ── data-plane session index ───────────────────────────────────────────────────

def ticker_frame_sessions(root: Path, ticker: str) -> set[str]:
    """ISO index dates of a ticker's committed price frame.

    Reads the stores in `stage_analysis._load_prices` order so the heal sees
    exactly the frame the engine classified from.  Returns an empty set when no
    frame is readable — the caller treats that as fail-closed.
    """
    import pandas as pd  # local: keeps `--help` cheap

    dr = root / "data"
    for sub in _STORE_ORDER:
        p = dr / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p, columns=["close"])
        except Exception:  # noqa: BLE001 — try the next store
            continue
        try:
            idx = pd.to_datetime(df.index)
            sessions = {str(ts.date()) for ts in idx}
        except Exception:  # noqa: BLE001
            continue
        if sessions:
            return sessions
    return set()


# ── heal ───────────────────────────────────────────────────────────────────────

def heal(
    root: Path,
    dry_run: bool = False,
    *,
    frame_sessions: Callable[[Path, str], set[str]] | None = None,
) -> dict:
    """Run the heal.  Returns a summary dict.  Idempotent: a healed file no-ops.

    `frame_sessions(root, ticker) -> set[str]` is injectable so tests can pin
    fixtures; the default is the real committed-frame reader.
    """
    reader = frame_sessions or ticker_frame_sessions

    ledger_dir = root / "data" / "stage_analysis"
    main_p = ledger_dir / "forward_ledger.jsonl"
    quar_p = ledger_dir / "forward_ledger_quarantine.jsonl"
    meta_p = ledger_dir / "forward_ledger_meta.json"

    if not main_p.exists():
        return {"error": f"{main_p} not found"}

    rows: list[dict] = []
    for line in main_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    ticker_cache: dict[str, set[str]] = {}

    def _sessions_for(ticker: str) -> set[str]:
        if ticker not in ticker_cache:
            ticker_cache[ticker] = reader(root, ticker)
        sessions = ticker_cache[ticker]
        if not sessions:
            raise SystemExit(
                f"FAIL-CLOSED: ticker {ticker!r} has no readable frame under "
                f"{root / 'data'}/{{{','.join(_STORE_ORDER)}}} — its rows' true "
                "sessions cannot be known; heal aborted, nothing written."
            )
        return sessions

    # Pass 1 — classify every row against the data plane.  Honest rows occupy
    # their (ticker, date) slot first; a restamp may never displace one.
    honest: list[dict] = []
    mislabeled: list[tuple[dict, str]] = []   # (row, true_session)
    occupied: set[tuple[str, str]] = set()
    for r in rows:
        tk = str(r.get("ticker") or "")
        stamp = str(r.get("date") or "")
        sessions = _sessions_for(tk)
        if stamp in sessions:
            honest.append(r)
            occupied.add((tk, stamp))
            continue
        candidates = [s for s in sessions if s <= stamp]
        if not candidates:
            raise SystemExit(
                f"FAIL-CLOSED: row ticker={tk!r} date={stamp!r} has no frame bar "
                "at or before its stamp — its true session cannot be known; "
                "heal aborted, nothing written."
            )
        mislabeled.append((r, max(candidates)))

    # Pass 2 — restamp or quarantine, in file order (first writer keeps the slot).
    quarantined: list[dict] = []
    restamped: list[dict] = []            # summary entries (from -> to)
    original_dates: list[str] = []
    pulled_ids: set[int] = set()          # identity of rows leaving the main ledger
    # Per-original-date breakdown so the impact on the date-keyed downstream read
    # (the Prophet US §9 "stage-ran shelf" study) is legible without a re-run.
    # NB: engine/oracle/tape_outcomes.py is NOT a consumer — it reads the
    # similarly-named data/oracle/forward_ledger.jsonl, a different ledger.
    breakdown: dict[str, dict] = {}
    for r in rows:
        d = str(r.get("date") or "")
        b = breakdown.setdefault(
            d, {"rows_in": 0, "honest": 0, "restamped": 0, "quarantined": 0,
                "true_sessions": {}})
        b["rows_in"] += 1
    for r in honest:
        breakdown[str(r.get("date") or "")]["honest"] += 1

    for r, true_session in mislabeled:
        tk = str(r.get("ticker") or "")
        original = str(r.get("date") or "")
        if original not in original_dates:
            original_dates.append(original)
        b = breakdown[original]
        b["true_sessions"][true_session] = b["true_sessions"].get(true_session, 0) + 1
        key = (tk, true_session)
        if key in occupied:
            q = dict(r)
            q["quarantine_reason"] = _QUARANTINE_REASON
            q["quarantined_kept_row"] = {"date": true_session, "ticker": tk}
            q["quarantined_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            quarantined.append(q)
            pulled_ids.add(id(r))
            b["quarantined"] += 1
            continue
        r["date"] = true_session
        r["session_inferred"] = True
        r["original_date"] = original
        r["session_source"] = "ticker_frame"
        occupied.add(key)
        restamped.append({"ticker": tk, "from": original, "to": true_session})
        b["restamped"] += 1

    # Survivors keep the ledger's original file order (restamps happen in place).
    survivors = [r for r in rows if id(r) not in pulled_ids]

    newest_bar = max((max(s) for s in ticker_cache.values() if s), default=None)

    # Post-heal observation dates: which sessions the ledger actually covers
    # once the calendar labels are replaced by tape. A date that disappears
    # here is a date a date-keyed reader (the stage-ran shelf study) will no
    # longer see — that is precisely what known_gaps records.
    survivors_by_session: dict[str, int] = {}
    for r in survivors:
        d = str(r.get("date") or "")
        survivors_by_session[d] = survivors_by_session.get(d, 0) + 1

    summary = {
        "n_rows_in": len(rows),
        "n_honest": len(honest),
        "n_restamped": len(restamped),
        "n_quarantined_now": len(quarantined),
        "n_survivors": len(survivors),
        "n_tickers": len(ticker_cache),
        "newest_frame_bar": newest_bar,
        "by_original_date": {
            d: breakdown[d] for d in sorted(breakdown)
        },
        "survivors_by_session": {
            d: survivors_by_session[d] for d in sorted(survivors_by_session)
        },
        "restamped": restamped,
        "quarantined": [
            {"ticker": q.get("ticker"), "date": q.get("date"),
             "true_session": q["quarantined_kept_row"]["date"]}
            for q in quarantined
        ],
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    if not quarantined and not restamped:
        summary["note"] = "already healed — nothing to do"
        return summary

    # ── write: main ledger, quarantine (append-preserving), meta merge ──
    def _dump(rs: list[dict]) -> str:
        return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rs) + "\n"

    existing_quar: list[dict] = []
    if quar_p.exists():
        for line in quar_p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                existing_quar.append(json.loads(line))
    already = {(q.get("ticker"), q.get("date")) for q in existing_quar}
    new_quar = [
        q for q in quarantined if (q.get("ticker"), q.get("date")) not in already
    ]

    ledger_dir.mkdir(parents=True, exist_ok=True)
    main_p.write_text(_dump(survivors), encoding="utf-8")
    if existing_quar or new_quar:
        quar_p.write_text(_dump(existing_quar + new_quar), encoding="utf-8")

    meta: dict = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
    meta["quarantine"] = {
        "file": quar_p.name,
        "n_rows": len(existing_quar) + len(new_quar),
        "reason": _QUARANTINE_REASON,
        "healed_by": "scripts/heal_stage_forward_ledger.py",
        "last_heal": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta["pre_fix_stamp"] = _PRE_FIX_STAMP_NOTE
    meta["residual"] = _RESIDUAL_NOTE
    gap_reason = (
        "the calendar date is not evidence about that session: the run that "
        "wrote these rows read tape no newer than the restamped session (no "
        f"frame bar after {newest_bar}), so whether this session had real "
        "fresh-Stage-2 candidates is unknowable from committed data"
    )
    gaps = {
        str(g.get("session")): g
        for g in (meta.get("known_gaps") or [])
        if g.get("session")
    }
    for d in original_dates:
        gaps[d] = {"session": d, "reason": gap_reason}
    meta["known_gaps"] = [gaps[k] for k in sorted(gaps)]
    meta_p.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (contains data/)")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)
    summary = heal(Path(args.root), dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 1 if summary.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
