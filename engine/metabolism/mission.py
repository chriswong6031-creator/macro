"""engine.metabolism.mission — Mission self-model loader + strategic memory (R-V4-4).

Three public surfaces:
  load_mission(root)             — load config/nw_mission.yml; safe fallback dict.
  build_mission_block(byte_cap)  — freshness-stamped prompt block (mission + posture
                                   + forward clocks), byte-budgeted.
  append_strategic_memory(row)   — append to data/metabolism/strategic_memory.jsonl.
  load_strategic_memory(top_k)   — most-recent-first rows from that ledger.

All functions are NEVER-RAISE and return safe fallbacks on any error.
No LLM calls, no network, deterministic.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.metabolism.provenance import stamp_context

log = logging.getLogger(__name__)

SCHEMA_STRATEGIC_MEMORY = "metabolism.strategic_memory.v1"

MISSION_PATH = ("config", "nw_mission.yml")
STRATEGIC_MEMORY_PATH = ("data", "metabolism", "strategic_memory.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── Mission loader ────────────────────────────────────────────────────────────

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
    root: Path | None = None,
) -> str:
    """Build a freshness-stamped prompt block for the mission + posture + clocks.

    The block is injected into every orchestrator-tier PROPOSE prompt as the
    first context block so the loop always knows its endgame, laws, and current
    strategic posture.

    Respects byte_cap: if the rendered text exceeds the cap, the posture and
    clocks sections are truncated (the endgame + pillars are preserved whole).

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
            "ENDGAME:",
            _wrap(str(mission.get("endgame", "(absent)")), indent="  "),
            "",
            "MISSION PILLARS:",
        ]
        for i, pillar in enumerate(mission.get("mission_pillars") or [], start=1):
            lines.append(f"  {i}. {_wrap(str(pillar).strip(), indent='     ')}")
        lines.append("")
        lines.append("STANDING LAWS:")
        for law_entry in mission.get("standing_laws") or []:
            law_id = law_entry.get("id", "?")
            law_text = str(law_entry.get("law", "")).strip()
            lines.append(f"  [{law_id}] {_wrap(law_text, indent='    ')}")
        lines.append("")
        header = "\n".join(lines)

        posture_lines: list[str] = ["STRATEGIC POSTURE:"]
        for item in mission.get("strategic_posture") or []:
            posture_lines.append(f"  - {str(item).strip()}")

        clock_lines: list[str] = ["", "FORWARD CLOCKS:"]
        for clock in mission.get("forward_clocks") or []:
            date = clock.get("date", "?")
            what = str(clock.get("what", "")).strip()
            clock_lines.append(f"  {date}: {what}")

        footer = "\n".join(posture_lines + clock_lines)

        full = header + "\n" + footer
        encoded = full.encode("utf-8")
        if len(encoded) <= byte_cap:
            return full

        # Truncate: keep header, trim posture/clocks
        budget_left = byte_cap - len(header.encode("utf-8")) - 100
        if budget_left > 0:
            tail = footer.encode("utf-8")[:budget_left].decode("utf-8", errors="replace")
            return header + "\n" + tail + "\n...(truncated)"
        return header + "\n...(posture/clocks truncated — byte_cap exceeded)"

    except Exception as exc:  # noqa: BLE001
        log.warning("mission.build_mission_block: %s", exc)
        return "(mission block unavailable)"


def _wrap(text: str, indent: str = "") -> str:
    """Collapse runs of whitespace/newlines to single spaces for prompt compactness."""
    import re  # noqa: PLC0415
    return re.sub(r"\s+", " ", text).strip()


# ── Strategic memory ledger ───────────────────────────────────────────────────

def append_strategic_memory(
    row: dict[str, Any],
    root: Path | None = None,
) -> bool:
    """Append one strategic-memory row to data/metabolism/strategic_memory.jsonl.

    Expected row schema:
        {ts, cycle_id, lobe, construction, verdict, measurement_lens_class}

    Extra keys are passed through as-is.
    The function stamps 'ts' to now if absent, adds schema key.
    Returns True on success, False on any error.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*STRATEGIC_MEMORY_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)

        out: dict[str, Any] = {
            "schema": SCHEMA_STRATEGIC_MEMORY,
            "ts": row.get("ts") or _now_iso(),
        }
        out.update({k: v for k, v in row.items() if k not in ("schema", "ts")})

        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, separators=(",", ":"), default=str) + "\n")
        log.info(
            "mission.append_strategic_memory: cycle=%s lobe=%s verdict=%s",
            out.get("cycle_id"),
            out.get("lobe"),
            out.get("verdict"),
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

        # Sort most-recent-first by 'ts'
        def _ts_key(r: dict) -> str:
            return str(r.get("ts") or "")

        rows.sort(key=_ts_key, reverse=True)
        return rows[:top_k] if top_k else rows

    except Exception as exc:  # noqa: BLE001
        log.warning("mission.load_strategic_memory: %s", exc)
        return []
