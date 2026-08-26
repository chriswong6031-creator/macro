"""Recover the US Prophet-Live event spool the 2026-08 outage never published.

Between 2026-07-30T17:20:56Z and 2026-08-26 the live evaluator ran ~1,500 in-window
passes, evaluated a correct armed pack against a correct quote tape, produced correct
verdicts -- and published none of them, because the cutover never seeded its R2
credentials (research/PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md).

THIS IS RECOVERY, NOT REPLAY. Every row here was emitted by the production evaluator
at the time, to its own journal, and is read back verbatim. Nothing is re-derived from
prices, no state machine is re-run, and no armed pack is reconstructed -- which matters
because no historical pack bytes survive (R2 versioning is off and ListObjectVersions
is unimplemented), so a replay would have had to MINT a cohort production never armed.

WHY THE JOURNAL IS A SOUND SOURCE. Each pass logs its own event count and then its
event lines. Those two are independent statements by the same process, so they check
each other: across the whole outage, 672 passes and 672 exact matches, zero mismatched,
zero orphaned event lines. A truncated log could not produce that.

WHAT THE JOURNAL CANNOT GIVE, and is therefore left NULL rather than guessed:

  ``via``     never logged. Optional on genuine rows too.
  ``entered`` "board" vs "cross" -- derived from the armed pack's ``center_buyable``,
              and the packs are gone. It IS recovered where production's own output
              settles it: ``at_risk``/``at_risk_unconfirmed`` are emitted only inside
              the ``if on_board:`` branch of live_states._resolve_state, and
              ``crossing_unconfirmed`` only in the cross branch, so one such event
              fixes that name's whole session (``entered`` is carried forward by
              ``prev.get("entered")``). Names that only ever emitted ``forming`` or
              ``confirming_into_close`` are genuinely undetermined and stay null.
              Measured on this incident: 168 of 333 names determined, 0 contradictions.

Emitting a reconstructed ``entered`` for the rest would be a provenance claim this
evidence cannot back (commission §14, §16 -- absence means no claim, never a default).

    python -m scripts.prophet_live_journal_recovery --journal FILE --out DIR [--execute]

The output is a bounded PENDING input staged outside canonical data/prophet_live/.
It writes no ledger: scripts/reconcile_prophet_live.py stays the sole writer of
data/prophet_live/forward.parquet (LEDGER LAW D10).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

SCHEMA = "prophet_live.recovered_events/v1"

#: Emitted ONLY inside the ``if on_board:`` branch (live_states.py:616-654).
BOARD_ONLY_KINDS = frozenset({"at_risk", "at_risk_unconfirmed"})
#: Emitted ONLY in the cross branch (live_states.py:698).
CROSS_ONLY_KINDS = frozenset({"crossing_unconfirmed"})

_PID = re.compile(r"python\[(\d+)\]:")
_PASS = re.compile(
    r"prophet-live pass=(?P<pass_ts>\S+)\s+pack_as_of=(?P<pack_as_of>\S+)\s+"
    r"quotes=(?P<quotes_n>\d+)@(?P<quote_asof>\S+)\s+src=(?P<src>\S+).*?events=(?P<events_n>\d+)"
)
_EVENT = re.compile(
    r"prophet-live EVENT (?P<kind>[a-z_]+) (?P<ticker>[A-Za-z0-9._\-]+) "
    r"px=(?P<px>\S+) from=(?P<frm>\S+) passes=(?P<passes>\S+) age=(?P<age>\S+)m\s*$"
)


def _num(raw: str) -> float | None:
    if raw in ("None", "", "nan", "NaN"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int(raw: str) -> int | None:
    v = _num(raw)
    return int(v) if v is not None else None


def _opt(raw: str) -> str | None:
    return None if raw == "None" else raw


def parse(journal: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """``({session: [event rows]}, stats)`` from a captured journal.

    Grouped by PID, which is unique per pass: the pass line and its event lines share
    one process, so a pass's declared ``events=N`` and its printed lines can be checked
    against each other without relying on line adjacency or log ordering.
    """
    from engine.prophet_live.live_states import session_phase  # noqa: PLC0415

    passes: dict[str, dict[str, Any]] = {}
    per_pid: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for line in journal.splitlines():
        pid_m = _PID.search(line)
        if not pid_m:
            continue
        pid = pid_m.group(1)
        pass_m = _PASS.search(line)
        if pass_m:
            passes[pid] = pass_m.groupdict()
            continue
        ev_m = _EVENT.search(line)
        if ev_m:
            per_pid[pid].append(ev_m.groupdict())

    mismatched: list[str] = []
    orphans = 0
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for pid, meta in sorted(passes.items(), key=lambda kv: kv[1]["pass_ts"]):
        printed = per_pid.get(pid, [])
        declared = int(meta["events_n"])
        if len(printed) != declared:
            mismatched.append(f"pid={pid} declared={declared} printed={len(printed)}")
            continue  # fail CLOSED: never accrue a pass whose own count disagrees
        if not printed:
            continue
        pass_ts = meta["pass_ts"]
        stamp = datetime.fromisoformat(pass_ts.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        session = _session_of(stamp)
        phase = session_phase(stamp)
        for ev in printed:
            sessions[session].append({
                "ticker": ev["ticker"].upper(),
                "kind": ev["kind"],
                "ts": pass_ts,
                "session_phase": phase,
                "price": _num(ev["px"]),
                "quote_age_min": _num(ev["age"]),
                "passes": _int(ev["passes"]),
                "from": _opt(ev["frm"]),
                # entered/via are filled (or left null) below; never defaulted.
                "entered": None,
                # Same shape load_events() yields for a genuine spool row, so the
                # reconciler's merge path cannot tell the two apart structurally and
                # needs no special case downstream of ingestion.
                "session_et": session,
                "pack_as_of": meta["pack_as_of"],
            })

    for pid in per_pid:
        if pid not in passes:
            orphans += len(per_pid[pid])

    determined = _infer_entered(sessions)
    stats = {
        "passes_parsed": len(passes),
        "passes_with_events": sum(1 for p in passes if per_pid.get(p)),
        "mismatched_passes": mismatched,
        "orphan_event_lines": orphans,
        "events_total": sum(len(v) for v in sessions.values()),
        **determined,
    }
    return dict(sorted(sessions.items())), stats


def _session_of(stamp: datetime) -> str:
    from engine.prophet_live.live_states import et_clock  # noqa: PLC0415
    return et_clock(stamp).date().isoformat()


def _infer_entered(sessions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Fill ``entered`` only where production's OWN emitted kind settles it.

    A contradiction (one name emitting both a board-only and a cross-only kind in one
    session) would mean the branch mapping is wrong, so it is reported and the name is
    left null rather than resolved by precedence.
    """
    verdict: dict[tuple[str, str], set[str]] = defaultdict(set)
    for session, rows in sessions.items():
        for row in rows:
            key = (session, row["ticker"])
            if row["kind"] in BOARD_ONLY_KINDS:
                verdict[key].add("board")
            elif row["kind"] in CROSS_ONLY_KINDS:
                verdict[key].add("cross")

    contradictions = sorted(f"{s}/{t}" for (s, t), v in verdict.items() if len(v) > 1)
    resolved = {k: next(iter(v)) for k, v in verdict.items() if len(v) == 1}
    for session, rows in sessions.items():
        for row in rows:
            row["entered"] = resolved.get((session, row["ticker"]))

    names = {(s, r["ticker"]) for s, rows in sessions.items() for r in rows}
    return {
        "names_total": len(names),
        "entered_determined": len(resolved),
        "entered_board": sum(1 for v in resolved.values() if v == "board"),
        "entered_cross": sum(1 for v in resolved.values() if v == "cross"),
        "entered_null": len(names) - len(resolved),
        "entered_contradictions": contradictions,
    }


def write_pending(sessions: dict[str, list[dict[str, Any]]], out: Path,
                  *, source_sha256: str, stats: dict[str, Any]) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for session, rows in sessions.items():
        payload = {
            "schema": SCHEMA,
            "session_et": session,
            "pack_as_of": rows[0]["pack_as_of"] if rows else None,
            "source": "systemd journal, macro-live-prophet.service (production evaluator output)",
            "source_sha256": source_sha256,
            "recovered_n": len(rows),
            "events": rows,
        }
        path = out / f"{session}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    (out / "_recovery_receipt.json").write_text(
        json.dumps({"schema": SCHEMA, "source_sha256": source_sha256,
                    "sessions": sorted(sessions), **stats}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journal", required=True, help="captured journal text")
    ap.add_argument("--out", required=True, help="pending output directory")
    ap.add_argument("--execute", action="store_true",
                    help="write the pending files (default: report only)")
    args = ap.parse_args(argv)

    raw = Path(args.journal).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    sessions, stats = parse(raw.decode("utf-8", errors="replace"))

    print(f"prophet-live recovery: source sha256={sha}")
    print(f"  passes parsed        : {stats['passes_parsed']}")
    print(f"  passes with events   : {stats['passes_with_events']}")
    print(f"  events recovered     : {stats['events_total']}")
    print(f"  sessions             : {', '.join(sorted(sessions)) or '(none)'}")
    print(f"  names                : {stats['names_total']}")
    print(f"  entered determined   : {stats['entered_determined']} "
          f"(board={stats['entered_board']} cross={stats['entered_cross']}) "
          f"null={stats['entered_null']}")
    for session, rows in sorted(sessions.items()):
        keys = {(r["ticker"], r["kind"]) for r in rows}
        print(f"    {session}: events={len(rows)} distinct(ticker,kind)={len(keys)}")

    if stats["mismatched_passes"]:
        print(f"::error title=prophet-live-recovery::{len(stats['mismatched_passes'])} "
              "pass(es) disagree with their own declared event count — REFUSING", flush=True)
        for row in stats["mismatched_passes"][:5]:
            print(f"    {row}")
        return 3
    if stats["orphan_event_lines"]:
        print(f"::error title=prophet-live-recovery::{stats['orphan_event_lines']} event "
              "line(s) have no pass line — REFUSING", flush=True)
        return 3
    if stats["entered_contradictions"]:
        print("::error title=prophet-live-recovery::branch inference contradicted itself "
              f"on {len(stats['entered_contradictions'])} name(s) — REFUSING", flush=True)
        return 3

    if not args.execute:
        print("  (report only — pass --execute to stage the pending input)")
        return 0
    written = write_pending(sessions, Path(args.out), source_sha256=sha, stats=stats)
    print(f"  staged {len(written)} session file(s) in {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
