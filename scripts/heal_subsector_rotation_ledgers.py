"""Heal the data/subsector_rotation/ ledgers — NYSE-session stamps + dupe quarantine.

One-time-but-idempotent data heal (forward-ledger calendar-asof audit 2026-08-05;
siblings: the Ignition Radar heal in #4568 and scripts/heal_basket_turn_ledger.py).

THE WOUND.  ``scripts/fetch_finviz_themes.py`` stamped its snapshot's ``asof`` from
the wall clock, and daily.yml runs it ~22:30 UTC SEVEN nights a week against an
end-of-day board.  The Saturday and Sunday runs therefore re-fetched Friday's
UNCHANGED numbers and stamped them with weekend dates.  That ``asof`` flows
straight into ``scripts/build_subsector_rotation.py`` and on into the three PIT
ledgers here, whose dedup keys all begin with ``date`` — so a weekend pass never
looked like a duplicate and appended a full fresh row set instead.  Downstream,
``engine.subsector_track_record.compute()`` graded each of those dates as another
IC day and another batch of by-stage observations: one Friday's calls counted up
to THREE times.

TRUTH SOURCE: ``lib/nyse_calendar`` alone.  Unlike the basket-turn heal — which had
to infer each row's true session from its members' price frames, because the wound
there was a run against a FROZEN store and only the tape knew what it had read —
this ledger family needs no price-store inference at all.  The defect is purely
calendrical: a non-session date cannot describe a tape, and the session a
non-session date re-describes is, by construction, the last session on or before
it.  The calendar is rule-arithmetic with zero data dependencies, so the inference
is exact and reproducible.

POLICY, PER FILE — first-writer-wins in FILE ORDER, so session-dated rows claim
their slots before any restamp can reach them:

* ``snapshots.jsonl`` (slot ``(date, key)``) — RESTAMP-OR-QUARANTINE, where the
  restamp test is the SESSION, not the slot.  A session the engine actually BUILT
  defines its own roster, and a weekend row may never join it: a weekend re-run can
  only contribute a key whose code shipped AFTER that build, so backdating it would
  insert a call the real build provably did not make.  (Committed example: the
  synthetic ``megacapgenerals`` node from ``_inject_megacap_node`` first appears on
  Sunday 2026-07-12 — the 268-name 2026-07-10 build had no such key, and this repo
  dates a coverage cliff to the FEATURE, not the data.)  A weekend row is restamped
  ONLY when the true session carries no pre-heal row at all: there the weekend run
  is the sole record of that session's tape and the code-era counterfactual is
  clean (Friday's fetch failed, Saturday recovered it).  Restamped rows carry
  ``session_inferred=true``.  Quarantine then splits into two honest classes:
    - DUPLICATE — the slot is already taken (by an honest row, or by an earlier
      restamped batch that a later weekend pass re-describes).  Carries a
      ``quarantined_kept_row`` pointer, which always resolves.
    - ROSTER — the true session was built but never carried this key.  There is no
      kept row to point at, so it carries ``quarantined_true_session`` plus
      ``roster_built_without_key: true`` instead of a pointer that would lie.

* ``turns.jsonl`` (slot ``(date, key, state)``) — QUARANTINE ALL, never restamp.
  These are turn-state-machine OUTPUT, evolved forward one fake session at a time,
  and the weekend rows carry claims the true session's own row set does not
  (verified on the committed data: ``cloudhyperscalers``/turn_up and
  ``commagrigrains``/turn_down exist only on 2026-08-01/02, with ``since`` fields
  pointing at those non-sessions).  Restamping would MINT Friday events that no
  Friday build ever produced — a fabrication, not a heal.

* ``universe_nominations.jsonl`` (slot ``(date, donor, receiver)``) — QUARANTINE
  ALL, same rationale: nominations are derived from the turn read, so a weekend
  nomination inherits the fake-session evolution above.

QUARANTINE, DON'T DELETE.  Nothing is ever dropped: every pulled row lands in
``<stem>_quarantine.jsonl`` with its ORIGINAL stamp intact plus the reason it was
pulled, so the defect stays auditable.  Untouched survivors keep their exact
original line bytes (only restamped rows are re-serialised), which keeps the git
diff to removals plus the in-place restamps.

FAIL-CLOSED: a missing ledger file, an unparseable JSON line, or a row whose
``date`` cannot be read aborts the ENTIRE heal across all three files before a
single byte is written — a row we cannot classify must not be silently kept OR
silently pulled.

IDEMPOTENT: a healed tree yields "already healed — nothing to do" and writes
nothing at all (byte-identical files, and ``last_heal`` is not refreshed on a
no-op).  Quarantine files are append-preserving across runs, deduped by each
file's own slot key.  No wall clock is read anywhere except the ``quarantined_at``
/ ``last_heal`` provenance stamps.

Usage:
    python3 scripts/heal_subsector_rotation_ledgers.py [--root DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import nyse_calendar  # noqa: E402 — must follow the sys.path bootstrap above

_HEALED_BY = "scripts/heal_subsector_rotation_ledgers.py"
_LEDGER_DIR = ("data", "subsector_rotation")

_DUPE_REASON = (
    "duplicate weekend re-description of an already-recorded session under a fresh "
    "calendar date (clock-stamped fetch; calendar-asof forward-ledger family, "
    "#4568/basket-turn sibling)"
)
_ROSTER_REASON = (
    "first observation of a key absent from the built true-session's roster — the "
    "feature shipped between runs, so this weekend re-run produced a call the real "
    "session's build provably did not make; backdating it would ADD to a roster the "
    "engine actually built, and a coverage cliff dates the FEATURE, not the data "
    "(clock-stamped fetch; calendar-asof forward-ledger family, #4568/basket-turn sibling)"
)
_TURN_REASON = (
    "turn-state-machine OUTPUT evolved on a session that does not exist — the weekend "
    "row set carries state transitions absent from the true session's own rows, so "
    "restamping would mint events no real build produced (clock-stamped fetch; "
    "calendar-asof forward-ledger family, #4568/basket-turn sibling)"
)
_NOM_REASON = (
    "nomination derived from turn-state-machine output evolved on a session that does "
    "not exist — the weekend row set carries pairings absent from the true session's "
    "own rows, so restamping would mint nominations no real build produced "
    "(clock-stamped fetch; calendar-asof forward-ledger family, #4568/basket-turn sibling)"
)
_GAP_REASON = (
    "the nightly logged no snapshot rows for this session (fetch failure or build "
    "abort); the board for that session is unknowable from this ledger"
)


class _Spec:
    """One ledger: its filename, slot key, restamp policy and serialisation dialect."""

    def __init__(self, name: str, slot: tuple[str, ...], restamp: bool,
                 reason: str, ensure_ascii: bool):
        self.name = name
        self.slot = slot                 # slot[0] is always the date field
        self.restamp = restamp
        # The file's PRIMARY quarantine reason. A restamp-policy ledger splits its
        # quarantines into the duplicate and roster classes per row (see _plan), so
        # this is the dominant class rather than the only one.
        self.reason = reason
        self.ensure_ascii = ensure_ascii

    @property
    def quarantine_name(self) -> str:
        return self.name.replace(".jsonl", "_quarantine.jsonl")


_LEDGERS = (
    # ensure_ascii mirrors each ledger's PRODUCING writer, so a re-serialised row is
    # byte-identical to one the nightly would have written:
    #   snapshots  <- engine.subsector_track_record.snapshot()          (default True)
    #   turns/noms <- scripts.build_subsector_rotation._append_jsonl_dedup (False)
    _Spec("snapshots.jsonl", ("date", "key"), True, _DUPE_REASON, True),
    _Spec("turns.jsonl", ("date", "key", "state"), False, _TURN_REASON, False),
    _Spec("universe_nominations.jsonl", ("date", "donor", "receiver"), False,
          _NOM_REASON, False),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slot_of(row: dict, spec: _Spec, date_override: str | None = None) -> tuple[str, ...]:
    d = date_override if date_override is not None else str(row.get(spec.slot[0]))
    return (d, *(str(row.get(f)) for f in spec.slot[1:]))


def _read_date(value) -> date | None:
    """`value` as a plain date, or None when it cannot be read as one."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# ── planning (no writes; every fail-closed abort happens here) ─────────────────

def _plan(path: Path, spec: _Spec) -> dict:
    """Classify one ledger. Raises SystemExit on anything unclassifiable."""
    entries: list[tuple[str, dict]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        try:
            entries.append((s, json.loads(s)))
        except Exception as e:  # noqa: BLE001
            raise SystemExit(
                f"FAIL-CLOSED: {path} line {n} is not parseable JSON ({e}) — a row that "
                "cannot be read cannot be classified as honest or mislabeled; heal "
                "aborted, nothing written."
            ) from e

    occupied: set[tuple[str, ...]] = set()
    # Sessions the engine actually BUILT, frozen from pass 1 and never extended during
    # pass 2. This — not the slot — is the restamp test: a built session owns its roster.
    built_sessions: set[str] = set()
    mislabeled: list[tuple[int, dict, str]] = []   # (index, row, true_session)
    for idx, (_raw, row) in enumerate(entries):
        d = _read_date(row.get(spec.slot[0]))
        if d is None:
            raise SystemExit(
                f"FAIL-CLOSED: {path} row {idx + 1} carries an unreadable "
                f"{spec.slot[0]}={row.get(spec.slot[0])!r} — its true session cannot be "
                "known; heal aborted, nothing written."
            )
        if nyse_calendar.is_session(d):
            occupied.add(_slot_of(row, spec))
            built_sessions.add(d.isoformat())
            continue
        mislabeled.append(
            (idx, row, nyse_calendar.last_session_on_or_before(d).isoformat()))

    restamped: list[dict] = []
    quarantined: list[dict] = []
    pulled: set[int] = set()
    modified: set[int] = set()
    for idx, row, true_session in mislabeled:
        original = str(row.get(spec.slot[0]))
        slot = _slot_of(row, spec, date_override=true_session)
        # RECOVERY, and only recovery: the true session was never built, so this weekend
        # run is the sole record of that session's tape and no roster is being edited.
        # The slot check still applies, so a Sunday re-description of a batch already
        # restamped onto that session collides and falls through to quarantine.
        if spec.restamp and true_session not in built_sessions and slot not in occupied:
            row[spec.slot[0]] = true_session
            row["session_inferred"] = True
            occupied.add(slot)
            modified.add(idx)
            restamped.append({"slot": list(slot[1:]), "from": original, "to": true_session})
            continue
        q = dict(row)
        q["quarantined_at"] = _now()
        if not spec.restamp:
            q["quarantine_reason"] = spec.reason
            q["quarantined_true_session"] = true_session
            # The load-bearing forensic fact for the quarantine-all files: a slot that
            # exists NOWHERE at the true session is a claim only the fake session ever
            # made, which is precisely why these rows may not be restamped.
            q["quarantined_novel_claim"] = slot not in occupied
        elif slot in occupied:
            # DUPLICATE — the true session carries this exact slot (an honest row, or an
            # earlier restamped batch). The pointer always resolves.
            q["quarantine_reason"] = _DUPE_REASON
            q["quarantined_kept_row"] = dict(zip(spec.slot, slot))
        else:
            # ROSTER — the true session WAS built but never carried this key, so there is
            # no kept row to point at and claiming one would be a lie. Record the session
            # and the roster fact instead.
            q["quarantine_reason"] = _ROSTER_REASON
            q["quarantined_true_session"] = true_session
            q["roster_built_without_key"] = True
        quarantined.append(q)
        pulled.add(idx)

    return {"spec": spec, "path": path, "entries": entries, "occupied": occupied,
            "restamped": restamped, "quarantined": quarantined,
            "pulled": pulled, "modified": modified}


def _known_gaps(plan: dict, spec: _Spec) -> list[dict]:
    """Sessions inside the healed snapshot ledger's span that carry NO rows.

    Derived from the data, never hardcoded: the span is the healed ledger's own
    first→last date, and every calendar session in it that no surviving row claims
    is a night this ledger simply does not describe.
    """
    present = {
        str(row.get(spec.slot[0]))
        for idx, (_raw, row) in enumerate(plan["entries"]) if idx not in plan["pulled"]
    }
    dates = sorted(d for d in (_read_date(p) for p in present) if d is not None)
    if not dates:
        return []
    missing = [s for s in nyse_calendar.sessions_between(dates[0], dates[-1])
               if s.isoformat() not in present]
    return [{"session": s.isoformat(), "reason": _GAP_REASON} for s in missing]


# ── heal ──────────────────────────────────────────────────────────────────────

def heal(root: Path, dry_run: bool = False) -> dict:
    """Run the heal. Returns a summary dict. Idempotent: a healed tree no-ops."""
    ledger_dir = Path(root).joinpath(*_LEDGER_DIR)

    # Existence is checked for EVERY ledger before any planning, so a missing file
    # can never leave one ledger healed and another untouched.
    for spec in _LEDGERS:
        if not (ledger_dir / spec.name).exists():
            return {"error": f"{ledger_dir / spec.name} not found"}

    plans = [_plan(ledger_dir / spec.name, spec) for spec in _LEDGERS]

    files: dict[str, dict] = {}
    for plan in plans:
        spec: _Spec = plan["spec"]
        files[spec.name] = {
            "n_rows_in": len(plan["entries"]),
            "n_restamped": len(plan["restamped"]),
            "n_quarantined_now": len(plan["quarantined"]),
            "n_survivors": len(plan["entries"]) - len(plan["pulled"]),
            "restamped_by_date": _count_by(plan["restamped"], lambda r: f"{r['from']}->{r['to']}"),
            "quarantined_by_date": _count_by(plan["quarantined"],
                                             lambda q: str(q.get(spec.slot[0]))),
            "quarantined_by_class": _count_by(plan["quarantined"], _class_of),
        }

    gaps = _known_gaps(plans[0], _LEDGERS[0])
    summary = {
        "files": files,
        "known_gaps": [g["session"] for g in gaps],
        "dry_run": dry_run,
    }

    touched = any(f["n_restamped"] or f["n_quarantined_now"] for f in files.values())
    if dry_run:
        return summary
    if not touched:
        summary["note"] = "already healed — nothing to do"
        return summary

    # ── write: main ledgers, quarantines (append-preserving), meta merge ──
    meta_p = ledger_dir / "ledgers_meta.json"
    meta: dict = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt meta is rebuilt, never fatal
            meta = {}
    quarantine_meta = dict(meta.get("quarantine") or {})

    for plan in plans:
        spec: _Spec = plan["spec"]
        # Survivors keep their ORIGINAL line bytes; only restamped rows re-serialise.
        out = [
            (json.dumps(row, separators=(",", ":"), ensure_ascii=spec.ensure_ascii)
             if idx in plan["modified"] else raw)
            for idx, (raw, row) in enumerate(plan["entries"]) if idx not in plan["pulled"]
        ]
        (ledger_dir / spec.name).write_text("".join(l + "\n" for l in out), encoding="utf-8")

        quar_p = ledger_dir / spec.quarantine_name
        existing: list[dict] = []
        if quar_p.exists():
            for line in quar_p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
        already = {_slot_of(q, spec) for q in existing}
        fresh = [q for q in plan["quarantined"] if _slot_of(q, spec) not in already]
        rows_out = existing + fresh
        if rows_out:
            quar_p.write_text(
                "".join(json.dumps(q, separators=(",", ":"),
                                   ensure_ascii=spec.ensure_ascii, default=str) + "\n"
                        for q in rows_out),
                encoding="utf-8")
            quarantine_meta[spec.name] = {
                "file": spec.quarantine_name,
                "n_rows": len(rows_out),
                "reason": spec.reason,
                # snapshots.jsonl holds TWO honest classes (duplicate / roster); this
                # breakdown is derived from the rows on disk, so it cannot drift from them.
                "reason_classes": _count_by(rows_out, _class_of),
                "healed_by": _HEALED_BY,
                "last_heal": _now(),
            }

    meta["quarantine"] = quarantine_meta
    merged = {str(g.get("session")): g
              for g in (meta.get("known_gaps") or []) if g.get("session")}
    for g in gaps:
        merged[g["session"]] = g
    meta["known_gaps"] = [merged[k] for k in sorted(merged)]
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    return summary


_CLASS_NAMES = {_DUPE_REASON: "duplicate", _ROSTER_REASON: "roster",
                _TURN_REASON: "fake-session turn output",
                _NOM_REASON: "fake-session nomination"}


def _class_of(q: dict) -> str:
    """Short label for a quarantined row's reason class (summary/reporting only)."""
    return _CLASS_NAMES.get(q.get("quarantine_reason") or "", "unclassified")


def _count_by(rows: list, key) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        k = key(r)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


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
