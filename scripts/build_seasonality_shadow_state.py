#!/usr/bin/env python3
"""Lane 6 — emit the biopharma seasonality shadow lobe + advance its forward ledger.

Reads the committed calendar-clock artifacts (``site/seasonalitydata/``), builds
one compact, expiring, context-only Neural Web state per covered biopharma
symbol via the fail-closed contract, and writes:

* ``data/neuralweb/biopharma_seasonality_state.json`` — the envelope-stamped
  state map plus the structured gaps for everything it could not build;
* ``data/seasonality/nw_forward_ledger.jsonl`` — APPEND-ONLY forward outcomes,
  one register row per (symbol, window occurrence) for every forecast the map
  shows, graded at horizon from the adjusted-close store.

Four things worth knowing before editing this file:

* **Nothing here can act.**  Every state carries the birth authority ceiling
  (all-false) from ``engine.seasonality.contracts``; the consumer attaches the
  block only to names an existing candidate universe already admitted.  There
  is no rank, gate, size, or origination path in or out of this artifact.
* **This script is the ledger's SOLE advancer.**  House law: the nightly
  advances forward ledgers and intraday lanes discard ``data/`` writes.  The
  ledger is opened in append mode and existing lines are never rewritten,
  reordered, or re-dated — a re-run appends nothing it has already recorded.
* **Fail-open, always.**  A missing index, a missing entity artifact, an absent
  price store: each becomes a structured gap or an annotation, never an
  exception.  ``main`` returns 0 unconditionally — a shadow lobe must not take
  the nightly down.
* **It must run AFTER build_stock_seasonality.**  The entity tree it reads is
  gitignored except the default symbol, so off the runner it is only populated
  by that builder earlier in the same sequential cluster.

Roughly a second of work: ~28 symbols, one 305-start baseline sweep each.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.envelope import stamp  # noqa: E402
from engine.seasonality import panel as season_panel  # noqa: E402
from engine.seasonality import state as season_state  # noqa: E402

log = logging.getLogger("build_seasonality_shadow_state")

INDEX_PATH = "site/seasonalitydata/index.json"
ENTITIES_DIR = "site/seasonalitydata/entities/"
STATE_PATH = "data/neuralweb/biopharma_seasonality_state.json"
LEDGER_PATH = "data/seasonality/nw_forward_ledger.jsonl"
UNIVERSE_SOURCE = INDEX_PATH


def _annotate(title: str, message: str) -> None:
    """Emit a GitHub Actions annotation.

    A bare ``print`` on purpose: every logger in this repo prefixes its records,
    and GitHub silently drops an annotation that does not START the line.
    ``flush`` is load-bearing because stdout is block-buffered when piped in
    Actions.
    """
    print(f"::warning title={title}::{message}", flush=True)


def _file_gap(reason_code: str, detail: str) -> dict[str, Any]:
    """A gap about the RUN rather than about one symbol (``symbol`` is null)."""
    return {"symbol": None, "reason_code": reason_code, "detail": detail}


# --- ledger I/O (this module is the only writer) ----------------------------


def load_ledger(root: Path) -> tuple[list[dict], int]:
    """Read every ledger row. Returns ``(rows, n_unparseable)``; never raises.

    An unparseable line is COUNTED and left exactly where it is. Repairing it
    would mean rewriting the file, and an append-only ledger that rewrites
    itself is not append-only.
    """
    path = root / LEDGER_PATH
    if not path.exists():
        return [], 0
    rows: list[dict] = []
    bad = 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _annotate("seasonality_shadow", f"forward ledger unreadable ({exc}) — grading skipped")
        return [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def append_ledger(root: Path, rows: list[dict]) -> None:
    """Append rows and nothing else — existing bytes are never touched."""
    if not rows:
        return
    path = root / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def load_closes(
    root: Path, symbols: list[str], gaps: list[dict]
) -> dict[str, list[tuple[date, float]]] | None:
    """Load ascending ``(session_date, adjusted_close)`` pairs for ``symbols``.

    Uses the panel's own loader, so the grading leg reads the SAME adjusted
    ``close`` column the year panel was folded from — a grade computed off the
    raw ``close_price`` series would put every split into the realized return.

    ``None`` (the store itself is absent) and ``{}`` (the store is there and no
    requested symbol loaded from it) are DIFFERENT answers and are returned as
    different values.  Collapsing them is what made the 30-day
    ``ungradable_missing_prices`` close-out unreachable in the one case it was
    written for: a symbol that left the store cannot be closed out if "no frames
    loaded" is read as "there is no price store", and the row then sits PENDING
    forever, inflating the pending count and never entering ``live_n``.
    """
    store = root / "data" / "yahoo"
    if not store.is_dir():
        gaps.append(
            _file_gap(
                "price_store_absent",
                f"{store} absent — matured registrations left PENDING, nothing graded",
            )
        )
        return None
    frames: dict[str, list[tuple[date, float]]] = {}
    for symbol in symbols:
        try:
            closes = season_panel.load_adjusted_closes(root, symbol)
        except Exception as exc:  # noqa: BLE001 — a bad parquet is one ungraded symbol
            log.warning("shadow-state price load skipped %s: %s", symbol, exc)
            continue
        frames[symbol] = [
            (stamp_.date(), float(value)) for stamp_, value in closes.items()
        ]
    return frames


# --- build ------------------------------------------------------------------


def build(*, root: Path, now: datetime | None = None) -> dict:
    """Run the whole lobe. Never raises for one bad symbol; returns a summary."""
    root = Path(root)
    started = time.time()
    now = now or datetime.now(timezone.utc)
    gaps: list[dict] = []

    index_path = root / INDEX_PATH
    index: dict[str, Any] = {}
    if not index_path.exists():
        _annotate(
            "seasonality_shadow",
            f"{INDEX_PATH} absent — no covered universe, empty state map written",
        )
        gaps.append(_file_gap("index_absent", f"{INDEX_PATH} not in the tree"))
    else:
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index = loaded
            else:
                gaps.append(_file_gap("index_unreadable", "index.json is not an object"))
        except (OSError, ValueError) as exc:
            _annotate("seasonality_shadow", f"{INDEX_PATH} unreadable ({exc}) — empty state map written")
            gaps.append(_file_gap("index_unreadable", f"{type(exc).__name__}: {exc}"))

    # --- ledger: grade what has matured, THEN count the forward sample ---
    ledger_rows, n_unparseable = load_ledger(root)
    if n_unparseable:
        _annotate(
            "seasonality_shadow",
            f"{n_unparseable} unparseable line(s) in {LEDGER_PATH} — left in place, not counted",
        )
        gaps.append(_file_gap("ledger_lines_unparseable", f"{n_unparseable} line(s) skipped"))

    graded_keys = {
        str(row.get("key")) for row in ledger_rows if row.get("row_type") == "grade"
    }
    register_keys = {
        str(row.get("key")) for row in ledger_rows if row.get("row_type") == "register"
    }
    asof_date = _index_as_of(index, now)
    pending = [
        row
        for row in ledger_rows
        if row.get("row_type") == "register" and str(row.get("key")) not in graded_keys
    ]
    matured = sorted(
        {
            str(row.get("symbol") or "")
            for row in pending
            if _matured(row, asof_date)
        }
        - {""}
    )
    new_grades: list[dict] = []
    if matured:
        frames = load_closes(root, matured, gaps)
        # `frames is None` means the price store itself is absent — an infra
        # outage, under which nothing is gradable and nothing may be closed out.
        # An EMPTY dict is the opposite: the store is there and these symbols
        # are not in it, which is exactly the case `grade_rows` closes out as
        # `ungradable_missing_prices` after 30 days. So the empty dict is passed
        # through rather than treated as an outage.
        if frames is not None:
            new_grades = season_state.grade_rows(pending, frames, asof_date)
            # Idempotence: a key already graded on a prior night is never re-graded.
            new_grades = [
                row for row in new_grades if str(row.get("key")) not in graded_keys
            ]

    live_n = season_state.live_n_by_symbol(ledger_rows + new_grades)

    # --- states ---
    # ``root`` is what lets the lobe read the covariance spine for its overlap
    # measurement. Without it the overlap slot still emits — as its explicit
    # ``spine_artifact_unavailable`` form — so a checkout with no spine produces
    # a visibly unmeasured overlap rather than a silent one.
    states, symbol_gaps = season_state.build_states(
        index, root / ENTITIES_DIR, live_n, now, root=root
    )
    gaps.extend(symbol_gaps)

    # --- register every forecast this map SHOWS ---
    new_registers = season_state.register_rows(states, register_keys, asof_date)
    append_ledger(root, new_grades + new_registers)

    n_covered = len(season_state.covered_symbols(index))
    payload: dict[str, Any] = {
        "schema": season_state.STATE_FILE_SCHEMA,
        # The ENVELOPE schema above and the PER-STATE schema here are two
        # different versions and always were: the file's shape (universe block,
        # states map, gaps list) is unchanged, while the states inside moved
        # v1 -> v2. Declaring the inner schema at the top level means a consumer
        # can dispatch without opening a state, and means the day they diverge
        # again nobody has to infer it from a sample.
        "state_schema": season_state.EMITTED_STATE_SCHEMA,
        "as_of": index.get("as_of"),
        "generated_at": season_state.utc_iso(now),
        "universe": {
            "source": UNIVERSE_SOURCE,
            "sector_filter": season_state.BIOPHARMA_SECTOR,
            "n_covered": n_covered,
            "n_emitted": len(states),
            "n_gaps": len(gaps),
        },
        "states": states,
        "gaps": gaps,
    }
    payload = stamp(payload, artifact_id=season_state.STATE_ARTIFACT_ID)

    out = root / STATE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if n_covered and not states:
        _annotate(
            "seasonality_shadow",
            f"0 of {n_covered} covered biopharma symbols produced a state "
            f"({len(gaps)} structured gap(s)) — the entity tree is R2-published and "
            "may not be synced in this checkout",
        )

    summary = {
        "n_covered": n_covered,
        "n_emitted": len(states),
        "n_gaps": len(gaps),
        "n_registered": len(new_registers),
        "n_graded": len(new_grades),
        "ledger_rows": len(ledger_rows) + len(new_grades) + len(new_registers),
        "state_bytes": out.stat().st_size,
        "elapsed_s": round(time.time() - started, 2),
    }
    log.info("seasonality shadow state: %s", json.dumps(summary))
    return summary


def _index_as_of(index: dict, now: datetime) -> date:
    """The covered set's own as-of, falling back to the wall clock."""
    raw = index.get("as_of")
    if isinstance(raw, str) and raw:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    return now.astimezone(timezone.utc).date()


def _matured(register: dict, asof: date) -> bool:
    try:
        return date.fromisoformat(str(register["occurrence_end_date"])) < asof
    except (KeyError, TypeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the biopharma seasonality Neural Web shadow state."
    )
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        summary = build(root=args.root)
        print(json.dumps(summary), flush=True)
    except Exception as exc:  # noqa: BLE001 — fail-open: a shadow lobe never blocks the nightly
        log.warning("seasonality shadow state build failed: %s", exc)
        _annotate("seasonality_shadow", f"build failed ({exc}) — previous state retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
