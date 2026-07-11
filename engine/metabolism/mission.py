"""engine.metabolism.mission — Mission self-model loader + strategic memory.

Public surfaces (all NEVER-RAISE, display-tier / is_context_only=True):

  load_mission(root)
      Load config/nw_mission.yml → dict; safe fallback on any error.

  build_mission_block(*, root, byte_cap)
      Freshness-stamped prompt block (endgame/mission + posture/pillars +
      standing laws + forward clocks), byte-budgeted.

  append_strategic_memory(row, *, root)
      Append to data/metabolism/strategic_memory.jsonl.

  load_strategic_memory(top_k, root)
      Most-recent-first rows from that ledger → list[dict].

  build_strategic_memory_block(lobe, *, n_tail, byte_cap, root)
      Same ledger as a formatted string slice, filtered by lobe → str.
      Used by PROPOSE context builder and orchestrator_brain.

No LLM calls, no network, deterministic.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.metabolism.provenance import stamp_context

log = logging.getLogger(__name__)

SCHEMA_STRATEGIC_MEMORY = "metabolism.strategic_memory.v1"

MISSION_PATH = ("config", "nw_mission.yml")
STRATEGIC_MEMORY_PATH = ("data", "metabolism", "strategic_memory.jsonl")

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}

# Hard-coded mission fallback when config/nw_mission.yml is absent or unparseable.
# Used both as a standalone string (W5 style) and embedded in the fallback dict (W3 style).
_MISSION_FALLBACK_TEXT = (
    "Neural Web mission: amass trader context — surface the information that helps "
    "a conviction-based trader improve entry quality, avoid momentum-chasing, and "
    "build asymmetric positions.  Every lobe is context-accrual infrastructure; "
    "the gauntlet is a promotion gate, not a build gate."
)

# W3-style fallback dict (preserves load_mission() contract for W3 tests)
_FALLBACK_MISSION: dict[str, Any] = {
    "schema": "nw_mission.v1",
    "version": 0,
    "as_of": "unknown",
    "endgame": "(mission file absent — accruing)",
    "mission_pillars": [],
    "standing_laws": [],
    "strategic_posture": [],
    "forward_clocks": [],
    "_fallback": True,
}


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wrap(text: str, indent: str = "") -> str:
    """Collapse runs of whitespace/newlines to single spaces for prompt compactness."""
    return re.sub(r"\s+", " ", text).strip()


# ── Mission loader ────────────────────────────────────────────────────────────

def load_mission(root: Path | None = None) -> dict[str, Any]:
    """Load config/nw_mission.yml.

    Returns a safe fallback dict on any error (including missing file,
    corrupt YAML, wrong schema).  NEVER raises.
    """
    try:
        import yaml  # noqa: PLC0415

        repo = _repo_root(root)
        p = repo.joinpath(*MISSION_PATH)
        if not p.exists():
            log.warning("mission.load_mission: %s not found — using fallback", p)
            return dict(_FALLBACK_MISSION)

        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            log.warning("mission.load_mission: YAML root is not a dict — using fallback")
            return dict(_FALLBACK_MISSION)

        # Accept any schema prefix starting with nw_mission
        schema = str(raw.get("schema", ""))
        if not schema.startswith("nw_mission"):
            log.warning(
                "mission.load_mission: unexpected schema %r — using fallback", schema
            )
            return dict(_FALLBACK_MISSION)

        return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("mission.load_mission: %s — using fallback", exc)
        return dict(_FALLBACK_MISSION)


# ── Prompt block builder ──────────────────────────────────────────────────────

def build_mission_block(
    byte_cap: int = 4_000,
    *,
    root: Path | None = None,
) -> str:
    """Build a freshness-stamped prompt block for the mission + posture + clocks.

    Handles both W3-style YAML (endgame/mission_pillars/standing_laws) and
    W5-style YAML (mission/iteration_focus/constraints/guiding_principles).
    Falls back to the hard-coded mission statement when the file is absent.

    Returns a plain-text block.  NEVER raises.
    """
    try:
        mission = load_mission(root)
        repo = _repo_root(root)
        mission_path = repo.joinpath(*MISSION_PATH)

        # Stamp the mission file for freshness
        blocks = stamp_context(
            [{"name": "mission", "source": str(mission_path.relative_to(repo)), "text": ""}],
            root=root,
        )
        stamped = blocks[0] if blocks else {}
        age_days = stamped.get("age_days")
        is_stale = stamped.get("is_stale", False)
        freshness_note = (
            f"[STALE {age_days:.0f}d old]" if (is_stale and age_days is not None)
            else f"[as_of {mission.get('as_of', 'unknown')}]"
        )

        lines: list[str] = [
            f"=== NW MISSION SELF-MODEL {freshness_note} ===",
            "",
        ]

        # Support both W3-style YAML (endgame key) and W5-style YAML (mission key)
        endgame = str(mission.get("endgame") or mission.get("mission") or "").strip()
        if endgame and not endgame.startswith("("):
            lines += ["ENDGAME:", _wrap(endgame, indent="  "), ""]
        elif mission.get("_fallback"):
            lines += ["ENDGAME:", _wrap(_MISSION_FALLBACK_TEXT, indent="  "), ""]

        # W3-style fields
        pillars = mission.get("mission_pillars") or []
        if pillars:
            lines.append("MISSION PILLARS:")
            for i, pillar in enumerate(pillars, start=1):
                lines.append(f"  {i}. {_wrap(str(pillar).strip(), indent='     ')}")
            lines.append("")

        standing_laws = mission.get("standing_laws") or []
        if standing_laws:
            lines.append("STANDING LAWS:")
            for law_entry in standing_laws:
                law_id = law_entry.get("id", "?")
                law_text = str(law_entry.get("law", "")).strip()
                lines.append(f"  [{law_id}] {_wrap(law_text, indent='    ')}")
            lines.append("")

        header = "\n".join(lines)

        # W3-style posture / clocks
        posture_lines: list[str] = []
        posture = mission.get("strategic_posture") or []
        if posture:
            posture_lines = ["STRATEGIC POSTURE:"]
            for item in posture:
                posture_lines.append(f"  - {str(item).strip()}")

        clock_lines: list[str] = []
        clocks = mission.get("forward_clocks") or []
        if clocks:
            clock_lines = ["", "FORWARD CLOCKS:"]
            for clock in clocks:
                date = clock.get("date", "?")
                what = str(clock.get("what", "")).strip()
                clock_lines.append(f"  {date}: {what}")

        # W5-style fields (iteration_focus / constraints / guiding_principles)
        extra_lines: list[str] = []
        iteration_focus = str(mission.get("iteration_focus") or "").strip()
        if iteration_focus:
            extra_lines += ["", f"ITERATION FOCUS: {iteration_focus}"]

        constraints = mission.get("constraints") or []
        if isinstance(constraints, list) and constraints:
            extra_lines.append("")
            extra_lines.append("CONSTRAINTS:")
            for c in constraints[:10]:
                extra_lines.append(f"  - {c}")

        guiding = mission.get("guiding_principles") or []
        if isinstance(guiding, list) and guiding:
            extra_lines.append("")
            extra_lines.append("GUIDING PRINCIPLES:")
            for p in guiding[:8]:
                extra_lines.append(f"  - {p}")

        footer = "\n".join(posture_lines + clock_lines + extra_lines)
        full = header + ("\n" + footer if footer.strip() else "")

        encoded = full.encode("utf-8")
        if len(encoded) <= byte_cap:
            return full

        # Truncate: keep header, trim the rest
        budget_left = byte_cap - len(header.encode("utf-8")) - 100
        if budget_left > 0:
            tail = footer.encode("utf-8")[:budget_left].decode("utf-8", errors="replace")
            return header + "\n" + tail + "\n...(truncated)"
        return header + "\n...(posture/clocks truncated — byte_cap exceeded)"

    except Exception as exc:  # noqa: BLE001
        log.warning("mission.build_mission_block: %s", exc)
        return f"## Mission\n\n{_MISSION_FALLBACK_TEXT}"


# ── Strategic memory ledger ───────────────────────────────────────────────────

def append_strategic_memory(
    row: dict[str, Any],
    root: Path | None = None,
) -> bool:
    """Append one strategic-memory row to data/metabolism/strategic_memory.jsonl.

    Expected row schema:
        {ts, cycle_id, lobe, verdict, measurement_lens_class, sensor}

    Extra keys are passed through as-is.
    The function stamps 'ts' to now if absent, adds schema key.
    Returns True on success, False on any error.  NEVER raises.
    """
    try:
        if not isinstance(row, dict):
            log.warning("mission.append_strategic_memory: row is not a dict")
            return False

        repo = _repo_root(root)
        p = repo.joinpath(*STRATEGIC_MEMORY_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)

        stamped: dict[str, Any] = {
            "schema": SCHEMA_STRATEGIC_MEMORY,
            "ts": row.get("ts") or _now_iso(),
            "lobe": str(row.get("lobe_id") or row.get("lobe") or ""),
            "cycle_id": row.get("cycle_id"),
            "sensor": str(row.get("sensor") or ""),
            "verdict": str(row.get("verdict") or ""),
            "measurement_lens_class": str(row.get("measurement_lens_class") or ""),
            "check_by": row.get("check_by"),
        }
        # Pass through extra keys (e.g. construction from W3 callers)
        for k, v in row.items():
            if k not in stamped:
                stamped[k] = v

        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stamped, separators=(",", ":"), default=str) + "\n")
        log.info(
            "mission.append_strategic_memory: cycle=%s lobe=%s verdict=%s",
            stamped.get("cycle_id"),
            stamped.get("lobe"),
            stamped.get("verdict"),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("mission.append_strategic_memory: %s", exc)
        return False


def load_strategic_memory(
    top_k: int = 50,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load the most recent rows from data/metabolism/strategic_memory.jsonl.

    Returns rows sorted most-recent-first (by 'ts' field, falling back to
    file order).  Returns [] if file absent or on any error.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*STRATEGIC_MEMORY_PATH)
        if not p.exists():
            return []

        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue

        def _ts_key(r: dict) -> str:
            return str(r.get("ts") or "")

        rows.sort(key=_ts_key, reverse=True)
        return rows[:top_k] if top_k else rows

    except Exception as exc:  # noqa: BLE001
        log.warning("mission.load_strategic_memory: %s", exc)
        return []


def build_strategic_memory_block(
    lobe: str | None = None,
    *,
    n_tail: int = 20,
    byte_cap: int = 2000,
    root: Path | None = None,
) -> str:
    """Return the tail of strategic_memory.jsonl as formatted text for prompt injection.

    Parameters
    ----------
    lobe : str | None
        If provided, filter rows to this lobe only.
    n_tail : int
        Maximum number of rows to return (tail of the file).
    byte_cap : int
        Hard cap on returned string length.

    Returns
    -------
    str — compact JSON lines, one per row.  Returns absence message when file
    is missing.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*STRATEGIC_MEMORY_PATH)
        if not p.exists():
            return "(strategic_memory.jsonl not yet present — accruing as VERIFY runs)"

        rows: list[dict] = []
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    if not isinstance(r, dict):
                        continue
                    if lobe is not None and r.get("lobe") != lobe:
                        continue
                    rows.append(r)
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            log.warning("mission.build_strategic_memory_block: read error — %s", exc)
            return "(strategic memory unavailable)"

        if not rows:
            return "(strategic_memory.jsonl present but no matching rows — accruing)"

        # Take the tail
        tail_rows = rows[-n_tail:]

        lines_out: list[str] = []
        used_bytes = 0
        for row in tail_rows:
            # Drop authority block for prompt compactness
            compact = {k: v for k, v in row.items() if k not in ("authority",)}
            line = json.dumps(compact, separators=(",", ":"), default=str)
            line_bytes = len(line.encode())
            if used_bytes + line_bytes + 1 > byte_cap and lines_out:
                break
            lines_out.append(line)
            used_bytes += line_bytes + 1

        return "\n".join(lines_out)

    except Exception as exc:  # noqa: BLE001
        log.warning("mission.build_strategic_memory_block: %s", exc)
        return "(strategic memory unavailable)"
