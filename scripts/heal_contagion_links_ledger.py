"""Heal the Contagion Links forward ledgers — data-plane session stamps + dupe quarantine.

One-time-but-idempotent data heal (forward-ledger calendar-asof audit
2026-08-05, sibling of scripts/heal_basket_turn_ledger.py / the Ignition Radar
heal in #4568).  The pre-fix ``contagion_links.snapshot()`` stamped ONE
``date.today()`` across all 11 markets, so a weekend or drifted nightly re-run
appended a brand-new row that merely re-described the previous session's tape
under a fresh calendar date.  That defeats each ledger's own first-writer-wins
dedupe — keyed on the session instead, a run against a frozen store re-derives
the session it already recorded and the dedupe refuses it — and it mis-bases any
forward grader, which resolves the base close FORWARD from the row's ``asof``.

Measured on committed data before the fix: every one of the 11 shadow forward
logs carried 6 weekend rows out of 15; history.jsonl carried 66 of 165.

Twelve files are healed:
  data/contagion_links/history.jsonl                          (market per row)
  data/risk_radar/forward_log_contagion.jsonl                 (us)
  data/risk_radar_intl/<mkt>_forward_log_contagion.jsonl      (10 others)

Per row, against the market's own session index — the ISO index dates of its
bench close, loaded with THE ENGINE'S OWN loader so the heal and the writer read
the same plane:

1. ``asof`` present in that market's session index → HONEST.  The tape really
   had that session; the row is left byte-for-byte alone.

2. Otherwise the true session is the latest index date <= ``asof`` (the newest
   tape the run could actually have read).  The row is RESTAMPED in place:
   ``asof`` and ``data_session`` := the true session, plus
   ``session_inferred=true``, ``original_asof=<old>``, ``session_source="bench"``.

3. A mislabeled row whose true session ALREADY carries a row for that market in
   that file (honest rows win, then first-writer by file order) is QUARANTINED
   into a sibling ``*_quarantine.jsonl`` with ``quarantine_reason``, a
   ``quarantined_kept_row`` pointer and ``quarantined_at``.  Nothing is ever
   deleted.

Signal fields are never touched, and neither are ``graded`` / ``bench_path`` —
grading state is not this script's business.

FAIL-CLOSED: a market with an empty or unreadable session index, or a row with
no index date at or before its stamp, aborts the ENTIRE heal — every file, not
just that one — because the row's true session cannot be known from committed
data.  Classification therefore completes for all twelve files before the first
byte is written.

A provenance block is merged into data/contagion_links/ledger_meta.json: the
quarantine pointers, the counts, ``healed_by`` / ``last_heal``, and one
``known_gaps`` entry per distinct original date recording that the calendar date
the row carried is not evidence about that session at all.

Idempotent: a healed tree re-runs to a no-op.

Usage:
    python3 scripts/heal_contagion_links_ledger.py [--root DIR] [--dry-run]

Note on --root: it locates the LEDGER files only.  The default session index
reads the configured parquet store (lib.config.data_dir()), which is the plane
the engine itself reads; tests pin fixtures by passing ``session_index_fn``.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from engine import contagion_links as cg  # noqa: E402

MARKETS = cg.MARKETS

_QUARANTINE_REASON = (
    "duplicate re-description of an already-recorded session stamped under a "
    "fresh calendar date (clock-stamped writer; forward-ledger calendar-asof "
    "audit 2026-08-05)"
)

_HEALED_BY = "scripts/heal_contagion_links_ledger.py"


class HealAbort(SystemExit):
    """Fail-closed abort: a true session could not be known from committed data.

    Raised during classification, i.e. BEFORE any file is opened for writing, so
    an abort leaves all twelve ledgers byte-identical.  Subclasses SystemExit to
    match the sibling heals (scripts/heal_us_ignition_log.py) — an uncaught abort
    still exits non-zero with its message — while the distinct name lets
    ``main()`` catch it and still emit the JSON summary.
    """


# ── data-plane session index ───────────────────────────────────────────────────

def default_session_index(mkt: str) -> set[str]:
    """ISO index dates of `mkt`'s bench close, via the engine's own loader.

    Reading through ``contagion_links._load_close`` / ``_BENCH`` is deliberate:
    the heal must resolve sessions off exactly the plane the writer stamps from,
    or the two disagree and the heal manufactures its own drift.  An unreadable
    or empty series returns the empty set, which the caller treats as fatal.
    """
    try:
        s = cg._load_close(*cg._BENCH[mkt])
    except Exception:  # noqa: BLE001 — an empty index is the fail-closed signal
        return set()
    if s is None or len(s) == 0:
        return set()
    return {str(ts.date()) for ts in pd.to_datetime(s.index)}


# ── ledger inventory ───────────────────────────────────────────────────────────

def _ledger_files(root: Path) -> list[tuple[str, Path, str | None]]:
    """(label, path, fixed_market) for every ledger this heal owns.

    fixed_market=None means the market is carried per row (history.jsonl).
    """
    data = root / "data"
    files: list[tuple[str, Path, str | None]] = [
        ("contagion_links/history.jsonl",
         data / "contagion_links" / "history.jsonl", None),
        ("risk_radar/forward_log_contagion.jsonl",
         data / "risk_radar" / "forward_log_contagion.jsonl", "us"),
    ]
    for mkt in MARKETS:
        if mkt == "us":
            continue  # us lives under risk_radar/, already listed above
        files.append((
            f"risk_radar_intl/{mkt}_forward_log_contagion.jsonl",
            data / "risk_radar_intl" / f"{mkt}_forward_log_contagion.jsonl",
            mkt,
        ))
    return files


def _quarantine_path(p: Path) -> Path:
    """Sibling quarantine file: <name>_quarantine.jsonl next to the ledger."""
    return p.with_name(f"{p.stem}_quarantine{p.suffix}")


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _dump_jsonl(rows: list[dict]) -> str:
    return "".join(
        json.dumps(r, separators=(",", ":"), default=str) + "\n" for r in rows
    )


# ── heal ───────────────────────────────────────────────────────────────────────

def heal(
    root: Path,
    dry_run: bool = False,
    session_index_fn: Callable[[str], set[str]] | None = None,
) -> dict:
    """Run the heal across all twelve ledgers.  Returns a summary dict.

    Classification for EVERY file happens first; writes happen only once every
    row in every file has a known true session (fail-closed, see HealAbort).
    Idempotent: a healed tree produces no restamps and no quarantines and the
    summary says so.
    """
    session_index_fn = session_index_fn or default_session_index
    root = Path(root)

    _index_cache: dict[str, set[str]] = {}

    def _sessions_for(mkt: str) -> set[str]:
        if mkt not in _index_cache:
            try:
                idx = set(session_index_fn(mkt) or set())
            except Exception as exc:  # any loader failure is a fail-closed abort
                raise HealAbort(
                    f"FAIL-CLOSED: session index for market {mkt!r} could not be read "
                    f"({exc}); heal aborted, nothing written."
                ) from exc
            if not idx:
                raise HealAbort(
                    f"FAIL-CLOSED: market {mkt!r} has an empty session index — its "
                    "rows' true sessions cannot be known; heal aborted, nothing written."
                )
            _index_cache[mkt] = idx
        return _index_cache[mkt]

    # --- classification pass over every file (no writes anywhere yet) ---
    plans: list[dict] = []
    # original stamp -> the markets it was wrong for.  Per-market attribution
    # matters here in a way it did not for the single-basket siblings: the 11
    # markets close on different calendars, so a date can be an honest session
    # for one market and a drifted stamp for another (2026-07-17 is a real NYSE
    # session and not a KRX one).  A bare date list would over-claim.
    original_dates: dict[str, set[str]] = {}

    for label, path, fixed_mkt in _ledger_files(root):
        if not path.exists():
            plans.append({"label": label, "path": path, "missing": True})
            continue

        rows = _read_jsonl(path)

        # Pass 1 — honest rows occupy their (market, session) slot first, so a
        # restamp can never displace a row the tape actually vouches for.
        honest = 0
        mislabeled: list[tuple[dict, str, str]] = []   # (row, market, true_session)
        occupied: set[tuple[str, str]] = set()
        for r in rows:
            mkt = str(fixed_mkt or r.get("market") or "")
            stamp = str(r.get("asof") or "")
            sessions = _sessions_for(mkt)
            if stamp in sessions:
                honest += 1
                occupied.add((mkt, stamp))
                continue
            candidates = [s for s in sessions if s <= stamp]
            if not candidates:
                raise HealAbort(
                    f"FAIL-CLOSED: {label} row market={mkt!r} asof={stamp!r} has no "
                    "bench bar at or before its stamp — its true session cannot be "
                    "known; heal aborted, nothing written."
                )
            mislabeled.append((r, mkt, max(candidates)))

        # Pass 2 — restamp or quarantine, in file order (first writer keeps the slot).
        quarantined: list[dict] = []
        restamped: list[dict] = []
        pulled_ids: set[int] = set()
        for r, mkt, true_session in mislabeled:
            original = str(r.get("asof") or "")
            original_dates.setdefault(original, set()).add(mkt)
            key = (mkt, true_session)
            if key in occupied:
                q = dict(r)
                q["quarantine_reason"] = _QUARANTINE_REASON
                q["quarantined_kept_row"] = {"market": mkt, "asof": true_session}
                q["quarantined_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                quarantined.append(q)
                pulled_ids.add(id(r))
                continue
            # Signal fields, graded and bench_path are untouched by design.
            r["asof"] = true_session
            r["data_session"] = true_session
            r["session_inferred"] = True
            r["original_asof"] = original
            r["session_source"] = "bench"
            occupied.add(key)
            restamped.append({"market": mkt, "from": original, "to": true_session})

        survivors = [r for r in rows if id(r) not in pulled_ids]

        plans.append({
            "label": label,
            "path": path,
            "missing": False,
            "rows_in": rows,
            "n_honest": honest,
            "survivors": survivors,
            "quarantined": quarantined,
            "restamped": restamped,
        })

    # --- summary (identical shape for dry-run and real run) ---
    files_summary = []
    tot_in = tot_restamp = tot_quar = tot_surv = 0
    for pl in plans:
        if pl.get("missing"):
            files_summary.append({"file": pl["label"], "missing": True})
            continue
        n_in = len(pl["rows_in"])
        n_q = len(pl["quarantined"])
        n_s = len(pl["survivors"])
        tot_in += n_in
        tot_restamp += len(pl["restamped"])
        tot_quar += n_q
        tot_surv += n_s
        files_summary.append({
            "file": pl["label"],
            "n_rows_in": n_in,
            "n_honest": pl["n_honest"],
            "n_restamped": len(pl["restamped"]),
            "n_quarantined_now": n_q,
            "n_survivors": n_s,
            "quarantined": [
                {"market": q.get("market"), "asof": q.get("asof"),
                 "true_session": q["quarantined_kept_row"]["asof"]}
                for q in pl["quarantined"]
            ],
            "restamped": pl["restamped"],
        })

    summary: dict = {
        "n_files": len(files_summary),
        "n_rows_in": tot_in,
        "n_restamped": tot_restamp,
        "n_quarantined_now": tot_quar,
        "n_survivors": tot_surv,
        "original_dates": {d: sorted(ms) for d, ms in sorted(original_dates.items())},
        "files": files_summary,
        "dry_run": dry_run,
    }

    if dry_run:
        return summary

    if tot_restamp == 0 and tot_quar == 0:
        summary["note"] = "already healed — nothing to do"
        return summary

    # --- writes: survivors in place, quarantine append-preserving, meta merge ---
    quarantine_pointers = []
    for pl in plans:
        if pl.get("missing") or (not pl["restamped"] and not pl["quarantined"]):
            continue
        path: Path = pl["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump_jsonl(pl["survivors"]), encoding="utf-8")

        if not pl["quarantined"]:
            continue
        qpath = _quarantine_path(path)
        existing_q = _read_jsonl(qpath)
        already = {(q.get("market"), q.get("asof")) for q in existing_q}
        new_q = [
            q for q in pl["quarantined"]
            if (q.get("market"), q.get("asof")) not in already
        ]
        qpath.write_text(_dump_jsonl(existing_q + new_q), encoding="utf-8")
        quarantine_pointers.append({
            "ledger": pl["label"],
            "file": str(qpath.relative_to(root)) if qpath.is_relative_to(root) else str(qpath),
            "n_rows": len(existing_q) + len(new_q),
        })

    meta_p = root / "data" / "contagion_links" / "ledger_meta.json"
    meta: dict = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt meta is rebuilt, never fatal
            meta = {}
    meta["quarantine"] = {
        "files": quarantine_pointers,
        "n_rows": sum(qp["n_rows"] for qp in quarantine_pointers),
        "reason": _QUARANTINE_REASON,
        "healed_by": _HEALED_BY,
        "last_heal": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    gap_reason = (
        "the engine stamped this calendar date from the clock, not from the tape "
        "it read; for the markets listed the date is not evidence about that "
        "session at all — their rows were restamped to their true session or "
        "quarantined as duplicates of it"
    )
    gaps = {
        str(g.get("session")): g
        for g in (meta.get("known_gaps") or [])
        if g.get("session")
    }
    for d, mkts in original_dates.items():
        gaps[d] = {"session": d, "markets": sorted(mkts), "reason": gap_reason}
    meta["known_gaps"] = [gaps[k] for k in sorted(gaps)]
    meta_p.parent.mkdir(parents=True, exist_ok=True)
    meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary["quarantine_files"] = quarantine_pointers
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (contains data/)")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)
    try:
        summary = heal(Path(args.root), dry_run=args.dry_run)
    except HealAbort as exc:
        print(json.dumps({"error": str(exc), "aborted": True}, indent=2))
        # Bare print, never a logger: this repo's logging format prefixes the
        # record and GitHub then silently drops the annotation.
        print(f"::error title=contagion-heal-aborted::{exc}", flush=True)
        return 1
    print(json.dumps(summary, indent=2))
    return 1 if summary.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
