"""engine.metabolism.memory — Append-only memory artifacts + anti-rot (V2-D §2).

Three append-only git artifacts:
  data/metabolism/fitness_history.jsonl   — SENSE/organism_state appends per run
  data/metabolism/lessons.jsonl           — VERIFY appends {cycle_id, verdict,
                                             what_worked, what_failed, construction}
  data/metabolism/agenda_archive/<cycle>.json — agenda archive-on-verify step

Anti-rot: when lessons.jsonl exceeds LESSONS_BYTE_CAP, a re-summarize helper
compresses old entries into a summary block; the raw tail feeds the next prompt.
The summary is display-tier only — never gate-altering.

All functions are NEVER-RAISE and return safe fallbacks on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_FITNESS_HISTORY = "metabolism.fitness_history.v1"
SCHEMA_LESSONS = "metabolism.lessons.v1"

FITNESS_HISTORY_PATH = ("data", "metabolism", "fitness_history.jsonl")
LESSONS_PATH = ("data", "metabolism", "lessons.jsonl")
AGENDA_ARCHIVE_DIR = ("data", "metabolism", "agenda_archive")

# Anti-rot byte cap: when lessons.jsonl exceeds this, trigger re-summarization
LESSONS_BYTE_CAP = 60_000
# Number of bytes to keep as the "raw tail" after compression
LESSONS_TAIL_BYTES = 8_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── fitness_history.jsonl ─────────────────────────────────────────────────────

def append_fitness_history(
    run_id: str,
    lobe: str | None,
    sensors: dict[str, Any],
    root: Path | None = None,
) -> bool:
    """Append a fitness snapshot to data/metabolism/fitness_history.jsonl.

    Called by SENSE / organism_state stage per run.
    Returns True on success, False on any error.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*FITNESS_HISTORY_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema": SCHEMA_FITNESS_HISTORY,
            "ts": _now_iso(),
            "run_id": run_id,
            "lobe": lobe,
            "sensors": sensors or {},
        }
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.append_fitness_history: %s", exc)
        return False


def load_fitness_history(
    root: Path | None = None,
    lobe: str | None = None,
    tail_n: int | None = None,
) -> list[dict[str, Any]]:
    """Load fitness_history.jsonl, optionally filtered by lobe + last N rows.

    Returns a list of rows (may be empty).  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*FITNESS_HISTORY_PATH)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if lobe is not None and r.get("lobe") != lobe:
                    continue
                rows.append(r)
            except Exception:  # noqa: BLE001
                continue
        if tail_n is not None:
            rows = rows[-tail_n:]
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.load_fitness_history: %s", exc)
        return []


# ── lessons.jsonl ─────────────────────────────────────────────────────────────

def append_lesson(
    cycle_id: str,
    verdict: str,
    what_worked: str,
    what_failed: str,
    construction: str,
    proposal_id: str | None = None,
    root: Path | None = None,
) -> bool:
    """Append a lesson to data/metabolism/lessons.jsonl.

    Called by VERIFY after each proposal outcome so PROPOSE stops repeating
    dead constructions.

    Returns True on success, False on error.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema": SCHEMA_LESSONS,
            "ts": _now_iso(),
            "cycle_id": cycle_id,
            "proposal_id": proposal_id,
            "verdict": verdict,
            "what_worked": what_worked or "",
            "what_failed": what_failed or "",
            "construction": construction or "",
        }
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
        log.info("memory.append_lesson: cycle=%s verdict=%s", cycle_id, verdict)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.append_lesson: %s", exc)
        return False


def load_recent_lessons(
    root: Path | None = None,
    byte_cap: int = LESSONS_TAIL_BYTES,
) -> str:
    """Return the tail of lessons.jsonl as a text string, byte-capped.

    Returns '(lessons.jsonl not yet present — accruing)' if absent.
    NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        if not p.exists():
            return "(lessons.jsonl not yet present — accruing)"
        text = p.read_text(encoding="utf-8")
        encoded = text.encode()
        if len(encoded) <= byte_cap:
            return text
        tail = encoded[-byte_cap:].decode(errors="replace")
        return "(tail)\n" + tail
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.load_recent_lessons: %s", exc)
        return "(lessons unavailable)"


def _needs_resummary(root: Path | None = None) -> bool:
    """Return True if lessons.jsonl exceeds the anti-rot byte cap."""
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        if not p.exists():
            return False
        size = p.stat().st_size
        return size > LESSONS_BYTE_CAP
    except Exception:  # noqa: BLE001
        return False


def resummary_lessons(
    summary_text: str,
    root: Path | None = None,
) -> bool:
    """Anti-rot: compress old lessons.

    The caller (weekly dream cycle) provides summary_text (LLM-generated,
    display-tier only — never gate-altering).  This function:
    1. Reads lessons.jsonl.
    2. Takes the raw tail (last LESSONS_TAIL_BYTES).
    3. Writes: [summary block as a single JSON row] + [raw tail rows].
    4. Replaces lessons.jsonl atomically.

    The summary row is marked is_summary=True so callers can distinguish it.
    Returns True on success.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*LESSONS_PATH)
        if not p.exists():
            return False

        text = p.read_text(encoding="utf-8")
        encoded = text.encode()
        # Keep only the raw tail
        if len(encoded) > LESSONS_TAIL_BYTES:
            tail_text = encoded[-LESSONS_TAIL_BYTES:].decode(errors="replace")
            # Drop the leading partial line — a raw byte slice can chop mid-JSON,
            # leaving an unparseable first row. Cut to the first complete line.
            nl = tail_text.find("\n")
            tail_text = tail_text[nl + 1:] if nl != -1 else ""
        else:
            tail_text = text

        # Build the summary row
        summary_row = {
            "schema": SCHEMA_LESSONS,
            "ts": _now_iso(),
            "is_summary": True,
            "summary": summary_text,
            "note": (
                "Anti-rot compression: this row summarizes lessons prior to the tail. "
                "Display-only — never gate-altering. The raw tail follows."
            ),
        }

        # Reconstruct: summary_row + newline + tail_text (strip leading partial line if any)
        new_content = (
            json.dumps(summary_row, separators=(",", ":"), default=str)
            + "\n"
            + tail_text.lstrip()
        )

        tmp = p.with_suffix(".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(p)
        log.info("memory.resummary_lessons: compressed to %d bytes", len(new_content.encode()))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.resummary_lessons: %s", exc)
        return False


# ── agenda_archive/ ───────────────────────────────────────────────────────────

def archive_agenda(
    cycle_id: str,
    agenda_data: dict[str, Any],
    verify_outcome: dict[str, Any] | None = None,
    root: Path | None = None,
) -> bool:
    """Archive a completed agenda + graded outcome to data/metabolism/agenda_archive/.

    Called by the VERIFY stage after grading.  The archived file carries both
    the original agenda and the realized outcome so the dream cycle can compare
    what was proposed vs what materialized.

    Returns True on success.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        archive_dir = repo.joinpath(*AGENDA_ARCHIVE_DIR)
        archive_dir.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "schema": "metabolism.agenda_archive.v1",
            "cycle_id": cycle_id,
            "archived_at": _now_iso(),
            "agenda": agenda_data,
            "verify_outcome": verify_outcome or {},
        }

        out_path = archive_dir / f"{cycle_id}.json"
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(out_path)
        log.info("memory.archive_agenda: wrote %s", out_path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.archive_agenda: %s", exc)
        return False


def load_agenda_archive(
    root: Path | None = None,
    tail_n: int = 20,
) -> list[dict[str, Any]]:
    """Load the most recent agenda_archive entries (up to tail_n).

    Returns a list sorted oldest-first.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        archive_dir = repo.joinpath(*AGENDA_ARCHIVE_DIR)
        if not archive_dir.exists():
            return []
        files = sorted(archive_dir.glob("*.json"))
        if tail_n:
            files = files[-tail_n:]
        results: list[dict[str, Any]] = []
        for f in files:
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("memory.load_agenda_archive: %s", exc)
        return []
