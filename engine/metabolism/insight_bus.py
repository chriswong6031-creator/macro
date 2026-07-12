"""engine.metabolism.insight_bus — Append-only stigmergy bus (V2-A §2).

STIGMERGY PRINCIPLE: lobes leave typed rows here; other lobes READ the bus.
No lobe-to-lobe calls — the bus is the only inter-lobe communication channel.

APPEND-ONLY: rows are never deleted or edited.  A 'handled' row is marked by
a later row referencing the original insight_id with handled:true (idempotent).

NEVER-RAISE CONTRACT (mirrors governance.py):
    All public functions catch ALL exceptions, log a warning, and return a safe
    fallback.  A bus failure must never abort the stage that invoked it.

ROW SCHEMA (metabolism.insight_bus.v1):
{
  "schema":       "metabolism.insight_bus.v1",
  "insight_id":   str,        # sha256[:16] of (emitter+kind+entities+ts)
  "ts":           ISO-8601,
  "cycle_id":     str | null,
  "emitter":      str,        # source module id
  "kind":         str,        # health_transition | contradiction | falsifier_tripped |
                              # freshness_sla_breach | comeback_clock_matured
  "severity":     str,        # low | medium | high | critical
  "entities":     list[str],  # lobe ids, artifact ids, etc.
  "evidence_ref": str | null, # path to artifact with more detail
  "summary":      str,        # human-readable one-line
  "handled":      bool,       # default False; set True by a handler row
  "handled_by":   str | null, # insight_id of the handler row
  "authority": { "is_context_only": true, ... }
}

DETERMINISTIC EMITTERS (no LLM):
  1. health_transition_emitter     — health status → degraded|stale|missing
  2. contradiction_emitter         — contradictions.py records (display-only)
  3. falsifier_tripped_emitter     — verify FALSIFIER_TRIPPED rows
  4. freshness_sla_emitter         — artifact past its freshness_sla_hours
  5. comeback_clock_emitter        — masterplan clock dates reached
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.insight_bus.v1"
BUS_PATH = Path("data") / "metabolism" / "insight_bus.jsonl"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
}

# Severity vocabulary
_SEVERITIES = frozenset({"low", "medium", "high", "critical"})

# Kind vocabulary
_KINDS = frozenset({
    "health_transition",
    "contradiction",
    "falsifier_tripped",
    "freshness_sla_breach",
    "comeback_clock_matured",
    # V2-C Unit 6 emitters (scout + revamp adjudicator)
    "uncovered_domain",
    "revamp_recommendation",
    # R-V5-1: permanently parked dispatch (exceeded max_build_attempts)
    "dispatched_build_parked",
    # R-V7-7: audit-reject rebuild cap exhausted — proposal parked for operator review
    "audit_rebuild_exhausted",
    # SA-W3: standout-lobe audit trigger (SA-R9 stateless-cattle)
    "audit_due",
    # R-V8-1: immune lane — unknown CI red class (no recipe match)
    "ci_red_unknown",
    # R-V8-4: lane-health sensors (dead cron, queue saturation, runner offline, key degradation)
    "lane_health_alert",
})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_insight_id(emitter: str, kind: str, entities: list[str], ts: str) -> str:
    key = f"{emitter}|{kind}|{'|'.join(sorted(entities))}|{ts}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_bus_rows(bus_path: Path) -> list[dict]:
    """Load all existing bus rows (fail-open)."""
    if not bus_path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in bus_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("insight_bus: cannot read bus file %s — %s", bus_path, exc)
    return rows


# ── Append ─────────────────────────────────────────────────────────────────────

def append_row(row: dict, root: Path | None = None) -> bool:
    """Append one row to the insight bus.  Returns True on success.

    NEVER-RAISE: any failure returns False and logs a warning.
    """
    try:
        repo = _repo_root(root)
        bus_path = repo / BUS_PATH
        bus_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with bus_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("insight_bus.append_row: failed — %s", exc)
        return False


def build_row(
    emitter: str,
    kind: str,
    severity: str,
    entities: list[str],
    summary: str,
    evidence_ref: str | None = None,
    cycle_id: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Build a bus row dict (does NOT append — call append_row separately)."""
    ts = ts or _now_utc()
    insight_id = _make_insight_id(emitter, kind, entities, ts)
    return {
        "schema": SCHEMA,
        "insight_id": insight_id,
        "ts": ts,
        "cycle_id": cycle_id,
        "emitter": emitter,
        "kind": kind,
        "severity": severity if severity in _SEVERITIES else "low",
        "entities": list(entities),
        "evidence_ref": evidence_ref,
        "summary": summary,
        "handled": False,
        "handled_by": None,
        "authority": AUTHORITY_BLOCK,
    }


def mark_handled(insight_id: str, handler_id: str, root: Path | None = None) -> bool:
    """Append a handler row that marks an insight as handled (idempotent).

    The handler row itself carries handled=True and references the original.
    Re-appending for the same insight_id is idempotent (the bus is append-only;
    later readers see the most-recent handled=True and treat it as resolved).
    """
    try:
        repo = _repo_root(root)
        ts = _now_utc()
        handler_row = {
            "schema": SCHEMA,
            "insight_id": handler_id,
            "ts": ts,
            "cycle_id": None,
            "emitter": "insight_bus.mark_handled",
            "kind": "handled",
            "severity": "low",
            "entities": [insight_id],
            "evidence_ref": None,
            "summary": f"handled: insight {insight_id}",
            "handled": True,
            "handled_by": handler_id,
            "authority": AUTHORITY_BLOCK,
        }
        return append_row(handler_row, root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("insight_bus.mark_handled: failed — %s", exc)
        return False


def get_open_rows(root: Path | None = None) -> list[dict]:
    """Return all rows where handled=False (or no handler row exists).

    A row is 'open' when no later row in the bus references it with handled=True.
    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        bus_path = repo / BUS_PATH
        rows = _load_bus_rows(bus_path)
        # Build set of handled insight_ids
        handled_ids: set[str] = set()
        for r in rows:
            if r.get("handled") and r.get("entities"):
                for eid in r["entities"]:
                    handled_ids.add(eid)
        open_rows = [
            r for r in rows
            if not r.get("handled", False) and r.get("insight_id") not in handled_ids
        ]
        return open_rows
    except Exception as exc:  # noqa: BLE001
        log.warning("insight_bus.get_open_rows: failed — %s", exc)
        return []


# ── Deterministic emitters ─────────────────────────────────────────────────────

def health_transition_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight rows for lobes with degraded|stale|missing health status.

    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        p = repo / "data" / "neuralweb" / "health.json"
        raw = _read_json(p)
        if not isinstance(raw, dict):
            return []

        lobes_raw = raw.get("lobes") or {}
        if isinstance(lobes_raw, list):
            lobes = {r.get("id", f"lobe_{i}"): r for i, r in enumerate(lobes_raw)}
        else:
            lobes = lobes_raw

        rows: list[dict] = []
        bad_statuses = {"degraded", "stale", "missing"}
        for lobe_id, rec in lobes.items():
            if not isinstance(rec, dict):
                continue
            status = rec.get("status", "")
            if status in bad_statuses:
                severity = "high" if status == "degraded" else "medium"
                row = build_row(
                    emitter="health_transition_emitter",
                    kind="health_transition",
                    severity=severity,
                    entities=[lobe_id],
                    summary=f"Lobe {lobe_id} health={status}",
                    evidence_ref="data/neuralweb/health.json",
                    cycle_id=cycle_id,
                )
                rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("health_transition_emitter: failed — %s", exc)
        return []


def contradiction_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight rows for contradiction records from contradictions.py output.

    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        # Try to import and run contradictions; fall back to reading a cached artifact
        try:
            from engine.neuralweb.contradictions import detect_contradictions  # noqa: PLC0415
            records = detect_contradictions(root=repo)
        except Exception as exc:  # noqa: BLE001
            log.warning("contradiction_emitter: cannot run detect_contradictions — %s", exc)
            # Fall back to reading cached artifact if present
            cached = repo / "data" / "neuralweb" / "contradictions.json"
            if cached.exists():
                raw = _read_json(cached)
                records = (raw.get("records") or []) if isinstance(raw, dict) else []
            else:
                return []

        rows: list[dict] = []
        for rec in (records or []):
            if not isinstance(rec, dict):
                continue
            # Only emit 'tension' severity (not 'note' — too noisy)
            if rec.get("severity") != "tension":
                continue
            entities = []
            if rec.get("pair"):
                entities.append(str(rec["pair"]))
            row = build_row(
                emitter="contradiction_emitter",
                kind="contradiction",
                severity="medium",
                entities=entities or ["contradictions"],
                summary=f"Contradiction tension: {rec.get('pair', '?')} — {rec.get('reading', '')[:80]}",
                evidence_ref="data/neuralweb/contradictions.json",
                cycle_id=cycle_id,
            )
            rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("contradiction_emitter: failed — %s", exc)
        return []


def falsifier_tripped_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight rows for FALSIFIER_TRIPPED outcomes in verify records.

    Scans data/metabolism/verify/*.json for recent FALSIFIER_TRIPPED outcomes.
    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        verify_dir = repo / "data" / "metabolism" / "verify"
        if not verify_dir.exists():
            return []

        rows: list[dict] = []
        for vf in sorted(verify_dir.glob("*.json"))[-20:]:  # last 20 files
            try:
                data = json.loads(vf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            outcome = data.get("outcome") or (data.get("triage") or {}).get("classification") or ""
            if outcome not in ("FALSIFIER_TRIPPED", "falsifier_tripped"):
                continue
            lobe_id = data.get("lobe") or data.get("lobe_id") or vf.stem
            row = build_row(
                emitter="falsifier_tripped_emitter",
                kind="falsifier_tripped",
                severity="high",
                entities=[lobe_id],
                summary=f"FALSIFIER_TRIPPED for lobe {lobe_id} in {vf.name}",
                evidence_ref=str(vf.relative_to(repo)),
                cycle_id=cycle_id,
            )
            rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("falsifier_tripped_emitter: failed — %s", exc)
        return []


def freshness_sla_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight rows for artifacts past their freshness_sla_hours.

    Reads config/synapse.yml and checks age vs SLA for metabolism-owned artifacts.
    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        synapse_path = repo / "config" / "synapse.yml"
        if not synapse_path.exists():
            return []

        try:
            import yaml  # noqa: PLC0415
            raw = yaml.safe_load(synapse_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("freshness_sla_emitter: cannot read synapse.yml — %s", exc)
            return []

        artifacts = raw.get("artifacts") or {}
        now = datetime.now(timezone.utc).timestamp()
        rows: list[dict] = []

        for art_id, art in artifacts.items():
            if not isinstance(art, dict):
                continue
            # Only metabolism-owned or metabolism-phase artifacts
            op = art.get("owner_program", "")
            if "metabolism" not in op:
                continue
            sla_h = art.get("freshness_sla_hours")
            if not sla_h:
                continue
            path_rel = art.get("path", "")
            if not path_rel:
                continue
            p = repo / path_rel
            if not p.exists():
                continue
            try:
                mtime = p.stat().st_mtime
                age_h = (now - mtime) / 3600.0
                if age_h > float(sla_h):
                    row = build_row(
                        emitter="freshness_sla_emitter",
                        kind="freshness_sla_breach",
                        severity="medium",
                        entities=[art_id],
                        summary=(
                            f"Artifact {art_id} is {age_h:.1f}h old "
                            f"(SLA {sla_h}h)"
                        ),
                        evidence_ref=path_rel,
                        cycle_id=cycle_id,
                    )
                    rows.append(row)
            except Exception as exc:  # noqa: BLE001
                log.warning("freshness_sla_emitter: stat failed for %s — %s", p, exc)
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("freshness_sla_emitter: failed — %s", exc)
        return []


# Masterplan clock registry: a simple list of (lobe, date_str, description)
# In a future V2-D build this would be parsed from a config/masterplan_clocks.yml.
# For now: a minimal hard-coded set of known clock dates from the programs.
_COMEBACK_CLOCKS: list[dict] = [
    {
        "lobe": "til",
        "date": "2026-10-15",
        "description": "First TIL check_by dates fire — sensors mature from accruing",
    },
    {
        "lobe": "neural_web",
        "date": "2026-10-06",
        "description": "Orthogonality rail R-ORTH come-back clock",
    },
]


def comeback_clock_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight rows when a registered masterplan come-back clock date is reached.

    Parses config/masterplan_clocks.yml if present; else uses the built-in fallback list.
    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Try loading from config file
        clocks_path = repo / "config" / "masterplan_clocks.yml"
        clocks: list[dict] = []
        if clocks_path.exists():
            try:
                import yaml  # noqa: PLC0415
                raw = yaml.safe_load(clocks_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    clocks = raw.get("clocks") or []
                elif isinstance(raw, list):
                    clocks = raw
            except Exception as exc:  # noqa: BLE001
                log.warning("comeback_clock_emitter: cannot read clocks config — %s", exc)
        if not clocks:
            clocks = _COMEBACK_CLOCKS

        rows: list[dict] = []
        for clock in clocks:
            if not isinstance(clock, dict):
                continue
            clock_date = str(clock.get("date") or "")
            if not clock_date:
                continue
            if today_str >= clock_date:
                lobe = str(clock.get("lobe") or "unknown")
                row = build_row(
                    emitter="comeback_clock_emitter",
                    kind="comeback_clock_matured",
                    severity="medium",
                    entities=[lobe],
                    summary=(
                        f"Come-back clock matured for {lobe} (date={clock_date}): "
                        f"{clock.get('description', '')}"
                    ),
                    evidence_ref=None,
                    cycle_id=cycle_id,
                )
                rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("comeback_clock_emitter: failed — %s", exc)
        return []


# ── Main runner ────────────────────────────────────────────────────────────────

def run_all_emitters(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Run all deterministic emitters and append new rows to the bus.

    Returns the list of newly appended rows.
    NEVER-RAISE: returns [] on any error.
    """
    try:
        repo = _repo_root(root)
        new_rows: list[dict] = []

        # SA-W3: import audit_due_emitter here to avoid circular import at module level
        try:
            from engine.metabolism.standout_auditor import audit_due_emitter  # type: ignore[import]
        except Exception as _import_exc:  # noqa: BLE001
            audit_due_emitter = None  # type: ignore[assignment]
            log.warning("insight_bus: standout_auditor import failed — audit_due_emitter skipped: %s", _import_exc)

        emitters = [
            health_transition_emitter,
            contradiction_emitter,
            falsifier_tripped_emitter,
            freshness_sla_emitter,
            comeback_clock_emitter,
        ]
        if audit_due_emitter is not None:
            emitters.append(audit_due_emitter)

        # Load existing insight ids to avoid duplicates within the same cycle
        existing = get_open_rows(root=repo)
        existing_ids: set[str] = {r.get("insight_id", "") for r in existing}

        for emitter_fn in emitters:
            try:
                emitted = emitter_fn(root=repo, cycle_id=cycle_id)
                for row in emitted:
                    if not isinstance(row, dict):
                        continue
                    iid = row.get("insight_id", "")
                    if iid in existing_ids:
                        continue  # Skip exact duplicate
                    if append_row(row, root=repo):
                        new_rows.append(row)
                        existing_ids.add(iid)
            except Exception as exc:  # noqa: BLE001
                log.warning("run_all_emitters: emitter %s failed — %s", emitter_fn.__name__, exc)
                continue

        return new_rows
    except Exception as exc:  # noqa: BLE001
        log.warning("run_all_emitters: failed — %s", exc)
        return []
