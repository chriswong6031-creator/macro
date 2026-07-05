"""Neural Web operator HQ panel (W8a).

Reads COMMITTED artifacts only — the VPS-clone model. No engine imports, no
subprocess. Every section fails-open: a missing artifact returns an honest
'not yet written' placeholder rather than an exception.

Sections returned by panel():
  A. engine_health  — synapse SLA compliance, spine/kernel freshness, lagging flags
  B. reflex_log     — reflex registry summary + recent firing tails
  C. bus_graph      — confluence graph topology summary
  D. governance     — governance ledger tail + cortex memo + probation status
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ---- repo paths (mirrors admin/paths.py convention) -------------------------
_ROOT = Path(__file__).resolve().parent.parent
_DATA_NW = _ROOT / "data" / "neuralweb"
_CONFIG = _ROOT / "config"
_DATA_REFLEXES = _ROOT / "data" / "reflexes"

# individual artifact paths
_SPINE_ENVELOPE = _DATA_NW / "spine_index.parquet.envelope.json"
_SPINE_PARQUET = _DATA_NW / "spine_index.parquet"
_KERNEL_ENVELOPE = _DATA_NW / "kernel_estimates.parquet.envelope.json"
_KERNEL_FAMILIES = _DATA_NW / "kernel_families.json"
_KERNEL_DECISIONS = _DATA_NW / "kernel_decisions.json"
_LAGGING_SIGNALS = _DATA_NW / "lagging_signals.json"
_READ_GATE = _DATA_NW / "read_gate_baseline.json"
_CONFLUENCE_GRAPH = _DATA_NW / "confluence_graph.json"
_GOVERNANCE_JSONL = _DATA_NW / "governance.jsonl"
_CORTEX_MEMO = _DATA_NW / "cortex" / "memo.json"
_SYNAPSE_YML = _CONFIG / "synapse.yml"
_REFLEXES_YML = _CONFIG / "reflexes.yml"


# ---- helpers ----------------------------------------------------------------

def _read_json(p: Path):
    """Return parsed JSON or None on any error (file missing, bad JSON, etc.)."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _mtime_hours_ago(p: Path) -> float | None:
    """Return how many hours ago the file was last modified, or None."""
    try:
        mtime = p.stat().st_mtime
        now = datetime.now(timezone.utc).timestamp()
        return round((now - mtime) / 3600, 2)
    except Exception:  # noqa: BLE001
        return None


def _iso_hours_ago(ts_str: str | None) -> float | None:
    """Parse an ISO-8601 timestamp and return hours since then, or None."""
    if not ts_str:
        return None
    try:
        # handle both Z and +00:00 suffixes
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        return round((now - dt).total_seconds() / 3600, 2)
    except Exception:  # noqa: BLE001
        return None


def _parse_yaml_synapse(path: Path) -> dict | None:
    """Parse synapse.yml without importing yaml (to avoid mandatory dep).
    Returns a minimal dict: {artifacts: {name: {path, freshness_sla_hours, tier, ...}}}.
    Falls back to None if pyyaml is unavailable or parse fails."""
    try:
        import yaml  # noqa: PLC0415 — optional; present in the engine venv
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw
    except Exception:  # noqa: BLE001
        return None


def _parse_yaml_reflexes(path: Path) -> dict | None:
    """Parse reflexes.yml; returns raw dict or None."""
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _tail_jsonl(p: Path, n: int = 20) -> list[dict]:
    """Return the last n lines of a JSONL file as parsed dicts, newest-first."""
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        result = []
        for line in reversed(lines[-n * 2:]):  # over-read in case of blanks
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
            if len(result) >= n:
                break
        return result
    except Exception:  # noqa: BLE001
        return []


# ---- Section A: Engine-Health Board -----------------------------------------

def _section_engine_health() -> dict:
    """SLA compliance across all synapse-registered artifacts + spine/kernel freshness."""
    out: dict = {
        "spine": None,
        "kernel": None,
        "sla": None,
        "kernel_families": None,
        "lagging": None,
        "read_gate": None,
    }

    # Spine Index freshness
    env = _read_json(_SPINE_ENVELOPE)
    if env:
        spine_age = _iso_hours_ago(env.get("produced_at"))
        if spine_age is None:
            spine_age = _mtime_hours_ago(_SPINE_PARQUET)
        out["spine"] = {
            "produced_at": env.get("produced_at"),
            "age_hours": spine_age,
            "inputs_hash": (env.get("inputs_hash") or "")[:16] + "…",
        }
    else:
        out["spine"] = {"missing": True, "note": "data/neuralweb/spine_index.parquet.envelope.json not yet written"}

    # Kernel estimates freshness
    k_env = _read_json(_KERNEL_ENVELOPE)
    if k_env:
        k_age = _iso_hours_ago(k_env.get("produced_at"))
        out["kernel_envelope"] = {
            "produced_at": k_env.get("produced_at"),
            "age_hours": k_age,
        }
    else:
        out["kernel_envelope"] = {"missing": True, "note": "kernel_estimates.parquet.envelope.json not yet written"}

    # Kernel decisions
    kd = _read_json(_KERNEL_DECISIONS)
    if kd:
        out["kernel"] = {
            "batch_id": kd.get("batch_id"),
            "next_batch_due": kd.get("next_batch_due"),
            "n_survivors": kd.get("n_survivors", 0),
            "n_eligible": kd.get("n_eligible", 0),
            "note": kd.get("note", ""),
            "display_only": kd.get("batch_id") is None,
        }
    else:
        out["kernel"] = {"missing": True, "note": "kernel_decisions.json not yet written"}

    # Kernel families (armed status)
    kf = _read_json(_KERNEL_FAMILIES)
    if kf and isinstance(kf.get("families"), dict):
        families = kf["families"]
        armed = [k for k, v in families.items() if v.get("armed")]
        out["kernel_families"] = {
            "n_total": len(families),
            "n_armed": len(armed),
            "armed_names": armed,
            "families": [
                {
                    "name": k,
                    "armed": v.get("armed", False),
                    "staleness_days": v.get("staleness", {}).get("days_since_last_fire"),
                    "date_last": v.get("staleness", {}).get("date_last"),
                    "horizon_keys": list(v.get("horizon_curve", {}).keys())[:3],
                    "n_eff": (list(v.get("recency_trend", {}).values() or [{}])[0] or {}).get("n_eff"),
                }
                for k, v in families.items()
            ],
        }
    else:
        out["kernel_families"] = {"missing": True, "note": "kernel_families.json not yet written"}

    # Lagging signals — families with non-empty flagged[]
    lg = _read_json(_LAGGING_SIGNALS)
    if lg and isinstance(lg.get("by_family"), dict):
        by_fam = lg["by_family"]
        flagged = [k for k, v in by_fam.items() if v.get("flagged")]
        out["lagging"] = {
            "n_families": len(by_fam),
            "n_flagged": len(flagged),
            "flagged_names": flagged,
        }
    else:
        out["lagging"] = {"missing": True, "note": "lagging_signals.json not yet written"}

    # Read-gate baseline
    rg = _read_json(_READ_GATE)
    if rg:
        findings = rg.get("findings", [])
        out["read_gate"] = {
            "n_undeclared": len(findings),
            "description": rg.get("description", ""),
            "schema": rg.get("schema", ""),
        }
    else:
        out["read_gate"] = {"missing": True, "note": "read_gate_baseline.json not yet written"}

    # SLA compliance — parse synapse.yml, compare each artifact mtime vs SLA
    synapse = _parse_yaml_synapse(_SYNAPSE_YML)
    if synapse and isinstance(synapse.get("artifacts"), dict):
        artifacts = synapse["artifacts"]
        total = len(artifacts)
        breaches: list[dict] = []
        no_mtime: list[str] = []
        for art_id, art in artifacts.items():
            sla_h = art.get("freshness_sla_hours")
            art_path = art.get("path")
            if sla_h is None or not art_path:
                continue
            full_path = _ROOT / art_path
            age = _mtime_hours_ago(full_path)
            if age is None:
                no_mtime.append(art_id)
                continue
            if age > sla_h:
                breaches.append({
                    "id": art_id,
                    "tier": art.get("tier", "?"),
                    "owner": art.get("owner_program", "?"),
                    "sla_hours": sla_h,
                    "age_hours": age,
                    "overdue_hours": round(age - sla_h, 1),
                    "path": art_path,
                })
        # Sort worst-first (largest overdue_hours)
        breaches.sort(key=lambda x: x["overdue_hours"], reverse=True)
        out["sla"] = {
            "total": total,
            "n_breaches": len(breaches),
            "n_no_mtime": len(no_mtime),
            "breaches": breaches,  # full list for table
        }
    else:
        out["sla"] = {"missing": True, "note": "config/synapse.yml not parseable (pyyaml required)"}

    return out


# ---- Section B: Kernel & Decisions + Reflex Log ----------------------------

def _section_reflex_log() -> dict:
    """Reflex registry summary + recent firings per registered reflex."""
    reflexes_raw = _parse_yaml_reflexes(_REFLEXES_YML)
    if not reflexes_raw or not isinstance(reflexes_raw.get("reflexes"), dict):
        return {
            "missing": True,
            "note": "config/reflexes.yml not parseable (pyyaml required)",
            "n_registered": 0,
            "n_mirroring": 0,
            "per_reflex": [],
        }

    reflex_defs = reflexes_raw["reflexes"]
    n_registered = len(reflex_defs)
    per_reflex = []

    for name, defn in reflex_defs.items():
        firings_path_str = defn.get("firings_jsonl")
        if firings_path_str:
            firings_path = _ROOT / firings_path_str
        else:
            firings_path = _DATA_REFLEXES / name / "firings.jsonl"

        # Determine migration status
        is_mirroring = firings_path.exists()

        # Read recent firings
        recent = _tail_jsonl(firings_path, 20) if is_mirroring else []

        # Count firings in last 7 days
        now_ts = datetime.now(timezone.utc).timestamp()
        n_7d = 0
        for f in recent:
            ts_str = f.get("ts") or f.get("timestamp") or f.get("fired_at")
            if ts_str:
                age_h = _iso_hours_ago(ts_str)
                if age_h is not None and age_h <= 168:  # 7*24
                    n_7d += 1

        # Last fired
        last_fired = None
        last_fired_age = None
        if recent:
            first = recent[0]
            last_fired = first.get("ts") or first.get("timestamp") or first.get("fired_at")
            last_fired_age = _iso_hours_ago(last_fired)

        per_reflex.append({
            "name": name,
            "mirroring": is_mirroring,
            "description": (defn.get("description") or "").strip()[:120],
            "push_tier_candidate": bool(defn.get("push_tier")),
            "n_firings_7d": n_7d,
            "last_fired": last_fired,
            "last_fired_age_hours": last_fired_age,
            "claim_family": defn.get("claim_family"),
            "tier": defn.get("tier"),
            "recent_firings": recent[:3],  # last 3 for display
        })

    n_mirroring = sum(1 for r in per_reflex if r["mirroring"])

    return {
        "n_registered": n_registered,
        "n_mirroring": n_mirroring,
        "per_reflex": per_reflex,
    }


# ---- Section C: Bus Graph (Confluence) --------------------------------------

def _section_bus_graph() -> dict:
    """Confluence graph topology summary."""
    cg = _read_json(_CONFLUENCE_GRAPH)
    if not cg:
        return {"missing": True, "note": "data/neuralweb/confluence_graph.json not yet written"}

    edges = cg.get("edges", [])
    edge_types: dict[str, int] = {}
    for e in edges:
        t = e.get("edge_type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    cs = cg.get("contradiction_summary", {})
    contradiction_records = cg.get("contradiction_records", [])
    top_pairs = cs.get("top_pair_ids", [])
    top_contradictions = [
        r for r in contradiction_records
        if r.get("pair_id") in top_pairs
    ]

    return {
        "n_nodes": len(cg.get("nodes", [])),
        "n_edges": len(edges),
        "n_contradictions": cs.get("n", 0),
        "by_severity": cs.get("by_severity", {}),
        "edge_types": edge_types,
        "top_pair_ids": top_pairs,
        "top_contradictions": top_contradictions[:5],
        "display_only": bool(cg.get("display_only", True)),
        "hard_law": cg.get("hard_law", ""),
        "asof": cg.get("asof") or cg.get("produced_at"),
        "is_context_only": bool(cg.get("is_context_only", True)),
    }


# ---- Section D: Governance --------------------------------------------------

def _section_governance() -> dict:
    """Governance ledger tail + cortex memo + probation status."""
    out: dict = {
        "recent_events": [],
        "probation": None,
        "cortex_memo": None,
    }

    # Governance ledger — last 30 events, newest-first
    events = _tail_jsonl(_GOVERNANCE_JSONL, 30)
    out["recent_events"] = events

    # Cortex memo (includes probation block)
    memo = _read_json(_CORTEX_MEMO)
    if memo:
        prob = memo.get("probation", {})
        out["probation"] = {
            "tier": prob.get("tier"),
            "granted": prob.get("granted", False),
            "reason": prob.get("reason"),
            "n_graded": (prob.get("attention_track_record") or {}).get("n"),
            "hits": (prob.get("attention_track_record") or {}).get("hits"),
            "min_n": 30,
            "min_events": 8,
            "lapses_at": prob.get("lapses_at"),
        }
        out["cortex_memo"] = {
            "as_of": memo.get("as_of"),
            "summary": memo.get("summary", ""),
            "what_fired": memo.get("what_fired", []),
            "contradictions_review": memo.get("contradictions_review", ""),
            "deserves_operator": memo.get("deserves_operator", []),
            "tool_call_census": memo.get("tool_call_census", {}),
            "is_context_only": memo.get("is_context_only", True),
        }
    else:
        out["probation"] = {"missing": True, "note": "data/neuralweb/cortex/memo.json not yet written"}
        out["cortex_memo"] = {"missing": True, "note": "data/neuralweb/cortex/memo.json not yet written"}

    return out


# ---- Top-level panel entry point -------------------------------------------

def panel() -> dict:
    """Return the full Neural Web operator HQ payload.

    Structure:
        engine_health  — Section A
        reflex_log     — Section B
        bus_graph      — Section C
        governance     — Section D
    """
    return {
        "ok": True,
        "engine_health": _section_engine_health(),
        "reflex_log": _section_reflex_log(),
        "bus_graph": _section_bus_graph(),
        "governance": _section_governance(),
    }
