#!/usr/bin/env python3
"""Static guard: us_standouts.json and signal_gate.json must be ONE pair, not two runs.

Both artifacts are written by a single process — scripts/build_stock_library.py, the gate
at its `if sig_verdict:` block and the board ~1,600 lines later — and they carry two copies
of the same reading: the board's rows embed a `signal` blob whose keys are a strict
superset (28) of a gate verdict entry's keys (11). The two writes are NOT equally
protected: the gate is guarded by `if sig_verdict:` plus a try/except that logs and
continues, while the board write is unconditional. So a run can advance the board and skip
the gate, and nothing on either file says so — both stamp the same `as_of`, which is the
DATA date, not the write time.

That is exactly what happened on 2026-08-12: an engine-render `scope=all` run re-emitted
the board with fresh blobs while the gate write did not happen, leaving 8 of 69 buy rows
with `signal.ticks` disagreeing with the gate verdict's ticks (CRCL, GPCR, GRAB, LNG,
NTES, RBRK, SGML, TEM — NTES blob ticks 0 against gate ticks 3). Every reader that treats
the gate as PRIMARY — scripts/build_discovery._signal_verdicts, the discovery "Buy zone"
strip's source of truth, and scripts/run_watchlist_sentinel._load_per_ticker_states — was
handed a stale gate wearing a current-looking date. engine/us_board_rank.verdict_for
documents the in-process resolution for the same reason.

THE INVARIANT: for every board row carrying a non-empty `signal` blob, that blob equals the
gate's verdict for the ticker on EVERY key the gate entry carries. This is exact equality,
not a tolerance: measured on a coherent main, 144/144 rows across buy/watch/leaders/laggards
match their gate entry on all 11 gate keys, so there is no benign drift to allow for. Keys
the blob carries and the gate does not are ignored — the gate entry's own key set is the
contract, and widening the blob must not red this guard.

`emit` is the lineage stamp both writes now carry (build_stock_library._PAIR_EMIT_STAMP):
one uuid per writer PROCESS. Differing pair_ids name WHICH side is stale (older `at_utc`),
but differing pair_ids with identical content are a benign re-emit and are not a violation
on their own — only content disagreement is.

Absent artifacts are not a violation (sparse agent checkouts and fresh clones carry no
site/ tree; the CLI prints n/a and exits 0). A present-but-unparseable artifact IS.

Exit 0 on clean. Exit 1 with the offending tickers on violation.

Usage:
    python3 scripts/check_signal_gate_coherence.py [STANDOUTS] [GATE]
    # defaults: site/factordata/us_standouts.json  site/factordata/signal_gate.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]

STANDOUTS_PATH = "site/factordata/us_standouts.json"
GATE_PATH = "site/factordata/signal_gate.json"

# Every bucket whose rows embed a `signal` blob. All four are graded: a stale gate skews
# whichever names it happens to reach, and `leaders`/`laggards` feed the same surfaces.
BUCKETS = ("buy", "watch", "leaders", "laggards")

# The marker used in place of a key list when the gate has no entry for a board ticker.
ABSENT = "absent_from_gate"

# How many mismatched keys get their values printed before the rest are named only.
_VALUES_SHOWN = 3


def incoherent_tickers(standouts: Mapping, gate: Mapping) -> dict[str, list[str]]:
    """{ticker: [mismatched gate key, ...]} for every board row that disagrees with the gate.

    The ONE shared predicate: the CLI, build_stock_library's render-lane self-check,
    build_discovery and run_watchlist_sentinel all flag the same names from this function,
    so a reader's demotion can never cover a different set than the guard reports.

    A ticker the gate does not carry is flagged ``[ABSENT]``. Rows with an empty or absent
    `signal` blob are SKIPPED — they carry no second copy to disagree with. An empty result
    means the pair is coherent.
    """
    verdicts = (gate or {}).get("verdicts") or {}
    if not isinstance(verdicts, Mapping):
        verdicts = {}

    out: dict[str, list[str]] = {}
    for bucket in BUCKETS:
        for row in (standouts or {}).get(bucket) or []:
            if not isinstance(row, Mapping):
                continue
            ticker = row.get("ticker")
            blob = row.get("signal")
            if not ticker or not blob or not isinstance(blob, Mapping):
                continue
            entry = verdicts.get(ticker)
            if entry is None:
                out[ticker] = [ABSENT]
                continue
            if not isinstance(entry, Mapping):
                out[ticker] = [ABSENT]
                continue
            keys = [k for k in entry if blob.get(k) != entry[k]]
            if keys:
                # A ticker can sit in two buckets; union so the second copy cannot mask
                # the first one's disagreement.
                out[ticker] = sorted(set(out.get(ticker) or []) | set(keys))
    return out


def _emit(payload: Mapping) -> dict:
    """The `emit` lineage stamp of one artifact, or {} when it carries none (pre-stamp file)."""
    e = (payload or {}).get("emit")
    return dict(e) if isinstance(e, Mapping) else {}


def stale_side(standouts: Mapping, gate: Mapping) -> str | None:
    """``"gate"`` / ``"board"`` — whichever emit stamp is OLDER, or None when unknowable.

    None is the honest answer whenever the stamps cannot decide: an artifact written before
    `emit` existed, one pair_id shared by both files (one run wrote the pair, so neither
    side lags), or identical timestamps. Readers say nothing about direction on None rather
    than guessing.
    """
    e_s, e_g = _emit(standouts), _emit(gate)
    pid_s, pid_g = e_s.get("pair_id"), e_g.get("pair_id")
    if not pid_s or not pid_g or pid_s == pid_g:
        return None
    at_s, at_g = e_s.get("at_utc"), e_g.get("at_utc")
    if not at_s or not at_g or at_s == at_g:
        return None
    # ISO-8601 UTC seconds sort lexically; the older side is the one left behind.
    return "gate" if at_g < at_s else "board"


def _lineage_line(standouts: Mapping, gate: Mapping,
                  standouts_name: str, gate_name: str) -> str | None:
    """The differing-pair_id line for the violation report, or None when the stamps agree."""
    e_s, e_g = _emit(standouts), _emit(gate)
    pid_s, pid_g = e_s.get("pair_id"), e_g.get("pair_id")
    if not pid_s or not pid_g or pid_s == pid_g:
        return None
    side = stale_side(standouts, gate)
    direction = ""
    if side:
        stale, fresh = (gate_name, standouts_name) if side == "gate" else (standouts_name, gate_name)
        direction = f" — {stale} is the STALE side (its write ran before {fresh}'s)"
    return (
        f"lineage: the two artifacts were written by DIFFERENT runs "
        f"({standouts_name} emit.pair_id={pid_s} at_utc={e_s.get('at_utc')}; "
        f"{gate_name} emit.pair_id={pid_g} at_utc={e_g.get('at_utc')}){direction}"
    )


def _load(path: str) -> tuple[Path, dict | None, str | None]:
    """(resolved path, parsed payload or None, parse-error violation or None)."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return p, None, None
    try:
        return p, json.loads(p.read_text()), None
    except Exception as e:  # noqa: BLE001 — a present-but-unreadable artifact IS a violation
        return p, None, f"JSON parse error in {path}: {e}"


def _check(standouts_path: str = STANDOUTS_PATH,
           gate_path: str = GATE_PATH) -> list[str]:
    """Return a list of violation strings. Empty list = coherent (or artifact absent)."""
    p_s, d_s, err_s = _load(standouts_path)
    p_g, d_g, err_g = _load(gate_path)
    if err_s or err_g:
        return [e for e in (err_s, err_g) if e]
    if d_s is None or d_g is None:
        # Absent artifact is not a violation (fresh clone, sparse agent checkout, or a
        # first run that has not emitted the pair yet).
        return []

    flagged = incoherent_tickers(d_s, d_g)
    if not flagged:
        return []

    violations: list[str] = []
    verdicts = (d_g or {}).get("verdicts") or {}
    blobs = {}
    for bucket in BUCKETS:
        for row in (d_s or {}).get(bucket) or []:
            if isinstance(row, Mapping) and row.get("ticker") and row.get("signal"):
                blobs.setdefault(row["ticker"], row["signal"])

    for ticker in sorted(flagged):
        keys = flagged[ticker]
        if keys == [ABSENT]:
            violations.append(
                f"{ticker}: on the board but ABSENT from the gate's verdicts — the gate "
                f"never saw this name"
            )
            continue
        blob = blobs.get(ticker) or {}
        entry = verdicts.get(ticker) or {}
        shown = ", ".join(
            f"{k}: board={blob.get(k)!r} gate={entry.get(k)!r}" for k in keys[:_VALUES_SHOWN]
        )
        rest = f" (+{len(keys) - _VALUES_SHOWN} more: {', '.join(keys[_VALUES_SHOWN:])})" \
            if len(keys) > _VALUES_SHOWN else ""
        violations.append(f"{ticker}: {len(keys)} gate key(s) disagree — {shown}{rest}")

    line = _lineage_line(d_s, d_g, p_s.name, p_g.name)
    if line:
        violations.append(line)
    return violations


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    standouts = argv[0] if argv else STANDOUTS_PATH
    gate = argv[1] if len(argv) > 1 else GATE_PATH

    missing = [
        a for a in (standouts, gate)
        if not (Path(a) if Path(a).is_absolute() else ROOT / a).exists()
    ]
    if missing:
        print(f"signal-gate coherence: n/a ({', '.join(missing)} absent)")
        return 0

    violations = _check(standouts, gate)
    if violations:
        print(
            f"check_signal_gate_coherence: FAIL — {len(violations)} coherence violation(s) "
            f"between {standouts} and {gate}:\n",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nThe board and the gate are written by ONE build_stock_library run, so a "
            "disagreement means one side was advanced without the other (the gate write is "
            "guarded by `if sig_verdict:` and can be skipped while the board write is not). "
            "Re-run the build so both artifacts are re-emitted together; readers that treat "
            "the gate as primary demote it for the listed tickers in the meantime.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_signal_gate_coherence: OK — {standouts} and {gate} are one coherent pair "
        f"(every {'/'.join(BUCKETS)} row with a signal blob equals its gate verdict on "
        f"every gate key)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
