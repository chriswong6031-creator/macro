"""Heal data/basket_turn/ledger.jsonl — data-plane session stamps + dupe quarantine.

One-time-but-idempotent data heal (forward-ledger audit 2026-08-05, sibling of
the Ignition Radar heal in #4568).  The pre-fix writer stamped ledger rows from
the calendar (`session_date()`), not from the tape the legs actually read, so a
nightly run against a frozen store re-described an already-recorded session
under a fresh date.  That defeats the ledger's own (basket_id, date)
idempotency AND mis-bases the downstream forward-return graders
(basket_turn_cohort._cohort_ew_vs_spy, tape_disagreement._basket_ew_vs_spy_return),
which resolve the base close FORWARD from the row date — a row stamped one
session late grades from the wrong entry bar.

Confirmed wound: rows dated 2026-08-03 (mag7 + ai_software) were computed from
member stores whose newest bar is 2026-07-31.

This script, per row:

1. CHECKS the row's `date` against the UNION of index dates across its basket's
   ACTIVE member frames in data/stocks/.  A date present in that union is
   HONEST — the tape really had that session and the row is left alone.

2. INFERS the true session of a mislabeled row as the latest union date <= the
   row's date (the newest tape the run could actually have read).

3. QUARANTINES a mislabeled row whose true session ALREADY carries a row for
   the same basket (an honest row, or an earlier restamp — honest rows win,
   then first-writer by file order) into ledger_quarantine.jsonl with a
   quarantine_reason and a pointer to the kept row.  Nothing is ever deleted.

4. RESTAMPS in place a mislabeled row whose true session carries no row yet:
   `date` and `as_of` := the true session, plus session_inferred=true.

5. MERGES a provenance block into ledger_meta.json: the quarantine pointer plus
   one known_gaps entry per distinct original date, recording that the session
   the calendar named is not evidence about that session at all.

FAIL-CLOSED: a basket with zero readable member frames, or a row with no union
date at or before its stamp, aborts the entire heal (nothing written) — its
true session cannot be known from committed data.

Usage:
    python3 scripts/heal_basket_turn_ledger.py [--root DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_QUARANTINE_REASON = (
    "duplicate re-description of an already-recorded session stamped under a "
    "fresh calendar date (store-frozen run; forward-ledger audit 2026-08-05, "
    "#4568 sibling)"
)


# ── data-plane session index ───────────────────────────────────────────────────

def _ticker_sessions(stocks_dir: Path, ticker: str, cache: dict[str, set[str]]) -> set[str]:
    """ISO index dates of data/stocks/<ticker>.parquet.  Empty set when unreadable."""
    if ticker in cache:
        return cache[ticker]
    sessions: set[str] = set()
    p = stocks_dir / f"{ticker}.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p, columns=["close"])
            idx = pd.to_datetime(df.index)
            sessions = {str(ts.date()) for ts in idx}
        except Exception:  # noqa: BLE001 — an unreadable frame contributes nothing
            sessions = set()
    cache[ticker] = sessions
    return sessions


def _basket_sessions(
    basket_id: str,
    membership: dict,
    stocks_dir: Path,
    basket_cache: dict[str, set[str]],
    ticker_cache: dict[str, set[str]],
) -> set[str]:
    """UNION of index dates across a basket's ACTIVE member frames.

    The union (not the intersection) is the honest reach: a session the legs
    could read for at least one member is a session the tape really had.
    """
    if basket_id in basket_cache:
        return basket_cache[basket_id]
    basket = (membership.get("baskets") or {}).get(basket_id) or {}
    tickers = [
        m["ticker"]
        for m in (basket.get("members") or [])
        if m.get("removed") is None and m.get("ticker")
    ]
    union: set[str] = set()
    for tk in tickers:
        union |= _ticker_sessions(stocks_dir, tk, ticker_cache)
    basket_cache[basket_id] = union
    return union


# ── heal ───────────────────────────────────────────────────────────────────────

def heal(root: Path, dry_run: bool = False) -> dict:
    """Run the heal.  Returns a summary dict.  Idempotent: a healed file no-ops."""
    ledger_dir = root / "data" / "basket_turn"
    main_p = ledger_dir / "ledger.jsonl"
    quar_p = ledger_dir / "ledger_quarantine.jsonl"
    meta_p = ledger_dir / "ledger_meta.json"

    if not main_p.exists():
        return {"error": f"{main_p} not found"}

    membership_p = root / "data" / "baskets" / "membership.json"
    if not membership_p.exists():
        return {"error": f"{membership_p} not found"}
    membership = json.loads(membership_p.read_text(encoding="utf-8"))
    stocks_dir = root / "data" / "stocks"

    rows: list[dict] = []
    for line in main_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    basket_cache: dict[str, set[str]] = {}
    ticker_cache: dict[str, set[str]] = {}

    def _sessions_for(basket_id: str) -> set[str]:
        sessions = _basket_sessions(
            basket_id, membership, stocks_dir, basket_cache, ticker_cache)
        if not sessions:
            raise SystemExit(
                f"FAIL-CLOSED: basket {basket_id!r} has no readable member frame "
                f"under {stocks_dir} — its rows' true sessions cannot be known; "
                "heal aborted, nothing written."
            )
        return sessions

    # Pass 1 — classify every row against the data plane.  Honest rows occupy
    # their (basket_id, date) slot first; a restamp may never displace one.
    honest: list[dict] = []
    mislabeled: list[tuple[dict, str]] = []   # (row, true_session)
    occupied: set[tuple[str, str]] = set()
    for r in rows:
        bid = str(r.get("basket_id") or "")
        stamp = str(r.get("date") or r.get("as_of") or "")
        sessions = _sessions_for(bid)
        if stamp in sessions:
            honest.append(r)
            occupied.add((bid, stamp))
            continue
        candidates = [s for s in sessions if s <= stamp]
        if not candidates:
            raise SystemExit(
                f"FAIL-CLOSED: row basket={bid!r} date={stamp!r} has no member bar "
                "at or before its stamp — its true session cannot be known; "
                "heal aborted, nothing written."
            )
        mislabeled.append((r, max(candidates)))

    # Pass 2 — restamp or quarantine, in file order (first writer keeps the slot).
    quarantined: list[dict] = []
    restamped: list[dict] = []            # summary entries (from -> to)
    original_dates: list[str] = []
    pulled_ids: set[int] = set()          # identity of rows leaving the main ledger
    for r, true_session in mislabeled:
        bid = str(r.get("basket_id") or "")
        original = str(r.get("date") or r.get("as_of") or "")
        if original not in original_dates:
            original_dates.append(original)
        key = (bid, true_session)
        if key in occupied:
            q = dict(r)
            q["quarantine_reason"] = _QUARANTINE_REASON
            q["quarantined_kept_row"] = {"date": true_session, "basket_id": bid}
            q["quarantined_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            quarantined.append(q)
            pulled_ids.add(id(r))
            continue
        r["date"] = true_session
        r["as_of"] = true_session
        r["session_inferred"] = True
        occupied.add(key)
        restamped.append({"basket_id": bid, "from": original, "to": true_session})

    # Survivors keep the ledger's original file order (restamps happen in place).
    survivors = [r for r in rows if id(r) not in pulled_ids]

    newest_bar = max((max(s) for s in basket_cache.values() if s), default=None)

    summary = {
        "n_rows_in": len(rows),
        "n_honest": len(honest),
        "n_restamped": len(restamped),
        "n_quarantined_now": len(quarantined),
        "n_survivors": len(survivors),
        "quarantined": [
            {"basket_id": q.get("basket_id"), "date": q.get("date"),
             "true_session": q["quarantined_kept_row"]["date"]}
            for q in quarantined
        ],
        "restamped": restamped,
        "newest_member_bar": newest_bar,
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    if not quarantined and not restamped:
        summary["note"] = "already healed — nothing to do"
        return summary

    # ── write: main ledger, quarantine (append-preserving), meta merge ──
    def _dump(rs: list[dict]) -> str:
        return "\n".join(json.dumps(r, default=str) for r in rs) + "\n"

    existing_quar: list[dict] = []
    if quar_p.exists():
        for line in quar_p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                existing_quar.append(json.loads(line))
    already = {(q.get("basket_id"), q.get("date")) for q in existing_quar}
    new_quar = [
        q for q in quarantined if (q.get("basket_id"), q.get("date")) not in already
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
        "healed_by": "scripts/heal_basket_turn_ledger.py",
        "last_heal": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    gap_reason = (
        "engine ran against a frozen store (no member bar after "
        f"{newest_bar}); whether this session had real candidates is "
        "unknowable from committed data"
    )
    gaps = {
        str(g.get("session")): g
        for g in (meta.get("known_gaps") or [])
        if g.get("session")
    }
    for d in original_dates:
        gaps[d] = {"session": d, "reason": gap_reason}
    meta["known_gaps"] = [gaps[k] for k in sorted(gaps)]
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

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
