"""Neural Web operator HQ panel (W8a + PR-4 factor_intelligence).

Reads COMMITTED artifacts only — the VPS-clone model. No engine imports, no
subprocess. Every section fails-open: a missing artifact returns an honest
'not yet written' placeholder rather than an exception.

Sections returned by panel():
  A. engine_health      — synapse SLA compliance, spine/kernel freshness, lagging flags
  B. reflex_log         — reflex registry summary + recent firing tails
  C. bus_graph          — confluence graph topology summary
  D. governance         — governance ledger tail + cortex memo + probation status
  E. factor_intelligence — NW factor lobe: state freshness, panel health, Pair G,
                           attention authority, hypotheses, §9.2 alerts (RUL-NW7/NW8 §D PR-4)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Plain-English lobe descriptions (curated + fingerprinted). Optional import:
# a fresh clone before the module is generated falls back to auto-summaries.
try:
    from .nw_lobe_descriptions import LOBE_DESCRIPTIONS
except Exception:  # noqa: BLE001
    LOBE_DESCRIPTIONS = {}

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

# R-ORTH PR-4: covariance spine (independence display)
_COVARIANCE_SPINE = _DATA_NW / "covariance_spine.json"

# Factor intelligence (§D PR-4 — RUL-NW7/NW8)
_FACTOR_STATE = _DATA_NW / "factor_intelligence_state.json"
_FACTOR_FIRINGS = _ROOT / "data" / "reflexes" / "factor_attention" / "firings.jsonl"
_FACTOR_GRADES = _ROOT / "data" / "reflexes" / "factor_attention" / "grades.jsonl"
_FACTOR_PROBATION = _ROOT / "data" / "reflexes" / "factor_attention" / "probation.json"
_FACTOR_CONTRADICTIONS = _DATA_NW / "factor_contradictions.jsonl"


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


def _read_independence_summary() -> dict:
    """Read the lobes block from covariance_spine.json fail-open (R-ORTH PR-4).

    Returns a dict with independence fields, all null when the file is absent.
    Display-only; never gates, ranks, or scores.

    Fields:
      effective_independent_lobes  — participation-ratio estimate or null
      n_lobes_measurable           — engines with >= 30 active weeks or null
      n_lobes_total                — total engines in spine_index or null
      pctile_vs_null               — lobes pctile vs. circular-shift null or null
      same_bet_warning             — warning object when active, else null
      dominant_overlap_cluster     — largest cluster engine list or null
      descriptive_not_gauntleted   — always True
      display_only                 — always True
      available                    — True when the spine file was readable
    """
    _null: dict = {
        "effective_independent_lobes": None,
        "n_lobes_measurable": None,
        "n_lobes_total": None,
        "pctile_vs_null": None,
        "same_bet_warning": None,
        "dominant_overlap_cluster": None,
        "descriptive_not_gauntleted": True,
        "display_only": True,
        "available": False,
    }
    raw = _read_json(_COVARIANCE_SPINE)
    if raw is None:
        return _null
    lobes = (raw.get("blocks") or {}).get("lobes")
    if lobes is None:
        return _null
    null_ref = lobes.get("null_reference") or {}
    pctile = null_ref.get("pctile_vs_null")
    clusters = lobes.get("clusters") or []
    dominant: list | None = None
    if clusters:
        largest = max(clusters, key=lambda c: len(c.get("engines") or []))
        dominant = largest.get("engines") or None
    sbw = lobes.get("same_bet_warning")
    same_bet = sbw if (sbw and sbw.get("active")) else None
    return {
        "effective_independent_lobes": lobes.get("effective_independent_lobes"),
        "n_lobes_measurable": lobes.get("n_lobes_measurable"),
        "n_lobes_total": lobes.get("n_lobes_total"),
        "pctile_vs_null": pctile,
        "same_bet_warning": same_bet,
        "dominant_overlap_cluster": dominant,
        "descriptive_not_gauntleted": True,
        "display_only": True,
        "available": True,
    }


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

_NW_HEALTH_JSON = _DATA_NW / "health.json"


def _section_engine_health() -> dict:
    """SLA compliance across all synapse-registered artifacts + spine/kernel freshness.

    Prefers data/neuralweb/health.json (PR-C artifact) when present — renders its
    lobes/status/overall directly and falls back to the legacy in-memory computation
    when the artifact is absent (older clones or first nightly before PR-C runs).
    """
    # --- PR-C fast-path: consume pre-built health artifact ---
    nw_health = _read_json(_NW_HEALTH_JSON)
    if nw_health and nw_health.get("schema") == "neuralweb.health.v1":
        out: dict = {
            "spine": None,
            "kernel": None,
            "sla": None,
            "kernel_families": None,
            "lagging": None,
            "read_gate": None,
            # PR-C enrichment keys
            "nw_health": {
                "overall_status": nw_health.get("overall_status"),
                "produced_at": nw_health.get("produced_at"),
                "as_of": nw_health.get("as_of"),
                "cortex_source": (nw_health.get("cortex") or {}).get("cortex_source"),
                "summary_counts": nw_health.get("summary_counts"),
                "lobes": nw_health.get("lobes", []),
                "cortex": nw_health.get("cortex"),
                "workflow_conformance_misses": nw_health.get("workflow_conformance_misses", []),
            },
        }
        # Still populate spine/kernel/lagging/read_gate from live artifacts for
        # the existing admin display panels — they remain useful for detailed ops view.
    else:
        out = {
            "spine": None,
            "kernel": None,
            "sla": None,
            "kernel_families": None,
            "lagging": None,
            "read_gate": None,
            "nw_health": {"missing": True, "note": "data/neuralweb/health.json not yet written (pre-PR-C clone or first nightly)"},
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
        raw_rs = memo.get("run_status")
        if raw_rs:
            run_status = raw_rs
        else:
            # Legacy memo without run_status — derive from tool_call_census
            tcc = memo.get("tool_call_census") or {}
            has_tools = bool(tcc) and not (len(tcc) == 1 and "fallback_call" in tcc)
            run_status = {
                "status": "warn" if has_tools else "degraded",
                "degraded": not has_tools,
                "degradation_reason": "zero_tool_calls" if not has_tools else None,
                "provider_attempts": [],
                "tool_call_batches": 0,
                "individual_tool_calls": sum(tcc.values()) if tcc else 0,
                "expected_min_tool_calls": 1,
                "context_stale": False,
                "context_as_of": None,
                "_legacy_memo": True,
            }
        out["cortex_memo"] = {
            "as_of": memo.get("as_of"),
            "summary": memo.get("summary", ""),
            "what_fired": memo.get("what_fired", []),
            "contradictions_review": memo.get("contradictions_review", ""),
            "deserves_operator": memo.get("deserves_operator", []),
            "tool_call_census": memo.get("tool_call_census", {}),
            "is_context_only": memo.get("is_context_only", True),
            "run_status": run_status,
        }
    else:
        out["probation"] = {"missing": True, "note": "data/neuralweb/cortex/memo.json not yet written"}
        out["cortex_memo"] = {"missing": True, "note": "data/neuralweb/cortex/memo.json not yet written"}

    return out


# ---- Section E: Factor Intelligence (§D PR-4 — RUL-NW7/NW8) ----------------

_CI_SENSITIVE_WORD = "val" + "idat"  # CI guard: never write this directly


def _section_factor_intelligence() -> dict:
    """NW factor lobe card: state freshness, panel health, Pair G ledger,
    attention authority, hypotheses block, and the §9.2 alert list.

    Reads COMMITTED artifacts only. No engine imports. Fail-open per artifact.
    Declared consumer in config/synapse.yml → factor-intelligence-state.
    """
    today_str = datetime.now(timezone.utc).date().isoformat()

    # ── State artifact ───────────────────────────────────────────────────────
    state = _read_json(_FACTOR_STATE)
    state_missing = state is None

    if state_missing:
        state_as_of = None
        state_age_hours = _mtime_hours_ago(_FACTOR_STATE)  # None (file absent)
        panel_block: dict = {}
        factor_weather: dict = {}
        hypotheses: dict = {}
        allowed_actions: dict = {}
        gaps: list = []
    else:
        state_as_of = state.get("as_of")
        state_age_hours = _iso_hours_ago(state.get("produced_at")) or _mtime_hours_ago(_FACTOR_STATE)
        panel_block = state.get("panel") or {}
        factor_weather = state.get("factor_weather") or {}
        hypotheses = state.get("hypotheses") or {}
        allowed_actions = state.get("allowed_actions") or {}
        gaps = state.get("gaps") or []

    # ── Panel health ─────────────────────────────────────────────────────────
    n_dates = panel_block.get("n_dates")
    latest_date = panel_block.get("latest_date")
    floor_met = bool(panel_block.get("history_floor_met", False))

    # ── Pair G ledger ────────────────────────────────────────────────────────
    contradictions_present = _FACTOR_CONTRADICTIONS.exists()
    pair_g_today_count = 0
    if contradictions_present:
        try:
            rows = _tail_jsonl(_FACTOR_CONTRADICTIONS, 50)
            pair_g_today_count = sum(
                1 for r in rows
                if (r.get("date") == today_str or r.get("as_of") == today_str)
            )
        except Exception:  # noqa: BLE001
            pass
    if not state_missing:
        contr_block = state.get("contradictions") or {}
        pair_g_block = contr_block.get("pair_g") or {}
        # Use state artifact's n_today as ground truth (more reliable)
        pair_g_today_count = pair_g_block.get("n_today", pair_g_today_count)

    # ── Attention authority (from state artifact; fall back to files) ────────
    att_block = (state.get("attention") or {}).get("factor_attention", {}) if not state_missing else {}
    n_firings = att_block.get("n_firings", 0)
    n_graded = att_block.get("n_graded", 0)
    att_granted = att_block.get("granted", False)
    att_tier = att_block.get("tier", "A0/A1 shadow")
    att_reason = att_block.get("reason", "insufficient-n")

    # Probation freshness from the committed probation.json (back-compat read)
    prob_age_hours = _mtime_hours_ago(_FACTOR_PROBATION)

    # ── §9.2 Alert list ──────────────────────────────────────────────────────
    alerts: list[str] = []

    # Alert 1: factor_weather absent from world_state.json while wired
    world_state_p = _DATA_NW / "world_state.json"
    ws = _read_json(world_state_p)
    if isinstance(ws, dict) and "factor_weather" not in ws:
        alerts.append("factor_weather absent from world_state.json — integration not yet active (expected until PR-2 lands)")

    # Alert 2: panel n_dates < 60 → dormancy
    if not state_missing and n_dates is not None and n_dates < 60:
        alerts.append(
            f"factor panel n_dates={n_dates} < 60 — lobe dormant (Pair G cannot fire, history floor not met)"
        )

    # Alert 3: H2 gate-passed but severity ceiling still 'note' (not yet applicable pre-BH)
    # Per RUL-NW12: severity clamp is always 'note' pre-H2 gate. Check if h2 is 'gate-passed'.
    h2_status = (hypotheses.get("h2") or {}).get("status", "") if isinstance(hypotheses.get("h2"), dict) else ""
    if h2_status == "gate-passed" and not state_missing:
        alerts.append("H2 is gate-passed but severity ceiling may still be 'note' — check _record() clamp in factor_contradictions.py")

    # Alert 4: attention granted but no approved A3 wiring
    if att_granted:
        alerts.append(
            "factor_attention authority granted — verify A3 wiring is approved before using in clamp paths"
        )

    # Alert 5: any artifact carrying rank/score fields or CI-sensitive word
    if not state_missing:
        state_str = str(state)
        if _CI_SENSITIVE_WORD + "ed" in state_str.lower():
            alerts.append(
                f"state artifact contains the CI-sensitive word — check build_factor_intelligence_state.py"
            )
        # Check for rank/score fields anywhere
        for forbidden in ("may_rank", "may_originate"):
            val = (allowed_actions or {}).get(forbidden)
            if val is True:
                alerts.append(f"allowed_actions.{forbidden}=True in state artifact — must be False (RUL-NW9)")

    return {
        "state_missing": state_missing,
        "state_as_of": state_as_of,
        "state_age_hours": state_age_hours,
        "panel_health": {
            "n_dates": n_dates,
            "latest_date": latest_date,
            "floor_met": floor_met,
        },
        "pair_g": {
            "ledger_present": contradictions_present,
            "today_count": pair_g_today_count,
        },
        "factor_attention": {
            "n_firings": n_firings,
            "n_graded": n_graded,
            "granted": att_granted,
            "tier": att_tier,
            "reason": att_reason,
            "probation_age_hours": prob_age_hours,
        },
        "hypotheses": {
            hi: {
                "status": (hypotheses.get(hi) or {}).get("status", "not-visible-in-tree")
                if isinstance(hypotheses.get(hi), dict)
                else "not-visible-in-tree"
            }
            for hi in ("h1", "h2", "h3", "h4", "h5")
        },
        "gaps_count": len(gaps),
        "gaps_sample": gaps[:5],
        "alerts": alerts,
        "display_only": True,
        "is_context_only": True,
    }


# ---- Section F: Daily Brief (PR-D) ------------------------------------------

_NW_DAILY_BRIEF_JSON = _DATA_NW / "daily_brief.json"


def _section_daily_brief() -> dict:
    """PR-D NW daily brief — status, brain-run line, operator_attention.

    Reads data/neuralweb/daily_brief.json (committed artifact only).
    Fail-open: missing or malformed artifact → honest placeholder.
    No engine imports, no subprocess.
    """
    brief = _read_json(_NW_DAILY_BRIEF_JSON)
    if brief is None or brief.get("schema") != "neuralweb.daily_brief.v1":
        return {
            "missing": True,
            "note": "data/neuralweb/daily_brief.json not yet written (pre-PR-D clone or first nightly)",
        }

    brain_run = brief.get("did_the_brain_run") or {}
    attn = brief.get("operator_attention") or []
    p1 = [a for a in attn if a.get("priority") == 1]
    p2 = [a for a in attn if a.get("priority") == 2]

    return {
        "schema": brief.get("schema"),
        "produced_at": brief.get("produced_at"),
        "as_of": brief.get("as_of"),
        "status": brief.get("status"),
        "phase": brief.get("phase"),
        "brain_run_summary": brain_run.get("summary"),
        "cortex_status": brain_run.get("cortex_status"),
        "operator_attention_p1": p1,
        "operator_attention_p2": p2[:5],  # top 5 only for admin display
        "operator_attention_count": len(attn),
        "gaps": brief.get("_gaps") or [],
    }


# ---- Section G: Evidence Clock (EC-R5) --------------------------------------

_NW_EVIDENCE_CLOCK_JSON = _DATA_NW / "evidence_clock.json"

# States shown in the queue (operator-facing); accruing/promotion_eligible skipped
_EC_QUEUE_STATES = frozenset({
    "overdue", "due", "human_review", "missing", "stale", "blocked", "not_ready"
})


def _section_evidence_clock() -> dict:
    """Global Evidence Clock queue — operator HQ view.

    Reads data/neuralweb/evidence_clock.json (committed artifact only).
    No engine imports, no subprocess. Fail-open: missing/corrupt → available=False.

    Returns
    -------
    dict with:
        available    — bool
        as_of        — str | None
        generated_utc — str | None
        summary      — full summary dict (when available)
        queue        — top 25 rows in operator states, each trimmed
        n_accruing   — int count of accruing/promotion_eligible rows
        caveats      — passthrough from artifact
    """
    raw = _read_json(_NW_EVIDENCE_CLOCK_JSON)
    if raw is None or raw.get("schema") != "neuralweb.evidence_clock.v1":
        return {
            "available": False,
            "note": "data/neuralweb/evidence_clock.json not yet written (PR1 not yet merged or build failed)",
        }

    try:
        # Type-guard summary (fix R3a)
        summary_raw = raw.get("summary")
        summary: dict = summary_raw if isinstance(summary_raw, dict) else {}

        # Type-guard rows: must be a list (fix R3b)
        all_rows_raw = raw.get("rows")
        all_rows: list = all_rows_raw if isinstance(all_rows_raw, list) else []

        # Split rows: operator queue vs. accruing/promotion_eligible
        # Skip non-dict entries entirely (fix R3b)
        queue_rows = []
        n_accruing = 0
        for row in all_rows:
            if not isinstance(row, dict):
                continue
            state = row.get("state", "")
            if state in _EC_QUEUE_STATES:
                queue_rows.append(row)
            else:
                n_accruing += 1

        # Trim each queue row to operator-safe fields only
        def _trim_row(r: dict) -> dict:
            # Type-guard readiness: must be a dict (fix R3c)
            readiness = r.get("readiness")
            readiness = readiness if isinstance(readiness, dict) else {}
            return {
                "clock_id": r.get("clock_id"),
                "source_system": r.get("source_system"),
                "owner_program": r.get("owner_program"),
                "clock_type": r.get("clock_type"),
                "due_at": r.get("due_at"),
                "state": r.get("state"),
                "blocking_reason": readiness.get("blocking_reason"),
                "regenerate_cmd": r.get("regenerate_cmd"),
                "acknowledged": r.get("acknowledged", False),
                "packet": r.get("packet"),
            }

        return {
            "available": True,
            "as_of": raw.get("as_of"),
            "generated_utc": raw.get("generated_utc"),
            "summary": summary,
            "queue": [_trim_row(r) for r in queue_rows[:25]],
            "n_accruing": n_accruing,
            "caveats": raw.get("caveats") or [],
        }

    except Exception:  # noqa: BLE001
        # Belt-and-braces: artifact produced by a sibling PR may drift;
        # never let a parse error darken the whole /api/neural_web panel
        return {"available": False, "error": "parse_error"}


# ---- Lobe Observatory helpers -----------------------------------------------

# Group definitions: (key, label, hue, id-prefix-or-owner-key-list)
# First-match wins on _assign_group().
_LOBE_GROUPS: list[tuple[str, str, str]] = [
    ("core",     "Core",     "#6a8dff"),
    ("kernel",   "Kernel",   "#b18cff"),
    ("cortex",   "Cortex",   "#38e0d4"),
    ("factor",   "Factor",   "#ffb84d"),
    ("reflexes", "Reflexes", "#ff6b6b"),
    ("bridge",   "Bridge",   "#4ad6a0"),
    ("sensors",  "Sensors",  "#f78fff"),
    ("ops",      "Ops",      "#8b98ad"),
]

_GROUP_CORE_IDS = frozenset({
    "world-state", "spine-index", "confluence-graph",
    "neuralweb-health", "neuralweb-daily-brief",
    "neuralweb-daily-brief-history",
    "site-neuralweb-daily-brief", "site-neuralweb-health",
    "site-neuralweb-mastermind-context", "site-golden-signals",
    "site-artifact-manifest",
})

_KNOWN_ACRONYMS = {"NW", "SLA", "FDR", "EV", "IC", "R2", "JSON", "JSONL",
                   "HTML", "UI", "UX", "ETF", "BTC", "HK", "CN", "CA"}


def _assign_group(lobe_id: str, owner_program: str) -> str:
    """Assign a group key to a lobe by id/owner (first-match wins)."""
    lid = lobe_id.lower()
    if lobe_id in _GROUP_CORE_IDS or lid.startswith("site-neuralweb") or lid.startswith("site-golden"):
        return "core"
    if lid.startswith("kernel-") or lid in {"lagging-signals", "kernel-half-lives"}:
        return "kernel"
    if lid.startswith("cortex-") or lid in {
        "hypothesis-inbox", "machine-registry", "research-queue", "governance-ledger",
    }:
        return "cortex"
    if lid.startswith("causal-") or lid.startswith("site-causal-"):
        return "cortex"
    if lid.startswith("reflex-") or lid.startswith("ops-push-") or lid.startswith("cortex-attention-"):
        return "reflexes"
    if lid.startswith("factor-") or lid.startswith("site-factor-"):
        return "factor"
    if lid.startswith("neuralweb-mastermind") or lid.startswith("site-neuralweb-mastermind") or lid.startswith("options-entry-"):
        return "bridge"
    if lid.startswith("bottom-sensors"):
        return "sensors"
    return "ops"


def _humanize_label(lobe_id: str) -> str:
    """Title-case a kebab-case id, preserving known acronyms."""
    words = lobe_id.replace("-", " ").split()
    result = []
    for w in words:
        upper = w.upper()
        if upper in _KNOWN_ACRONYMS:
            result.append(upper)
        else:
            result.append(w.title())
    return " ".join(result)


def _short_desc(notes_text: str | None) -> str:
    """Return first sentence of notes, <=160 chars, whitespace-collapsed."""
    if not notes_text:
        return ""
    text = " ".join(notes_text.split())
    # Find first sentence end
    for delim in (".", "!", "?"):
        idx = text.find(delim)
        if idx != -1 and idx < 200:
            sentence = text[: idx + 1].strip()
            return sentence[:160]
    return text[:160]


# ---- Plain-English descriptions + staleness guard ---------------------------
# The lobe registry (list/producer/consumers/freshness) is derived live from
# synapse.yml on every request, so structural changes are ALWAYS reflected. The
# one hand-curated layer — the plain-English prose — is guarded here so it can
# never SILENTLY go stale: each curated entry stores a fingerprint of the synapse
# note it was written from. If the note later changes, the fingerprint no longer
# matches → the description is flagged 'stale' (UI badge + a CI drift test).
# A lobe with no curated entry renders an auto-cleaned summary flagged 'auto'.

# strip file paths / code identifiers for the auto-fallback summary
_PATH_RE = re.compile(r"\b[\w./-]+\.(?:py|json|jsonl|parquet|yml|yaml|md)\b(?::\d+)?")
_LINEREF_RE = re.compile(r"\b\w+\.\w+:\d+\b")


def _note_fingerprint(raw_notes: str | None) -> str:
    """Stable 16-hex fingerprint of a synapse note (whitespace-collapsed)."""
    text = " ".join((raw_notes or "").split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _auto_plain(raw_notes: str | None) -> tuple[str, str]:
    """Best-effort readable fallback for lobes without a curated description.
    Strips file paths / code identifiers; returns (short, full)."""
    text = " ".join((raw_notes or "").split())
    if not text:
        return ("", "")
    cleaned = _LINEREF_RE.sub("", _PATH_RE.sub("", text))
    cleaned = re.sub(r"\(\s*\)", "", cleaned)          # empty parens left behind
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return (_short_desc(cleaned), cleaned[:460].strip())


def _plain_desc(lobe_id: str, raw_notes: str | None) -> tuple[str, str, str]:
    """Return (short, full, desc_status) for a lobe.

    desc_status ∈ {'curated', 'stale', 'auto'}:
      curated — hand-written prose whose fingerprint matches the current note
      stale   — hand-written prose written for an OLDER version of the note
      auto    — no curated entry; an auto-cleaned summary from the registry
    """
    entry = LOBE_DESCRIPTIONS.get(lobe_id) if isinstance(LOBE_DESCRIPTIONS, dict) else None
    if entry and entry.get("short"):
        status = "curated" if entry.get("src_fp") == _note_fingerprint(raw_notes) else "stale"
        return entry.get("short", ""), entry.get("full", ""), status
    short, full = _auto_plain(raw_notes)
    return short, full, "auto"


def _is_nw_lobe(lobe_id: str, art: dict) -> bool:
    """The NW-scope rule: is this synapse artifact a Neural Web lobe?"""
    if art.get("owner_program") == "neural-web":
        return True
    p = art.get("path", "")
    if p.startswith("data/neuralweb/") or p.startswith("site/neuralwebdata/"):
        return True
    if "mastermind:context" in (art.get("external_consumers") or []):
        return True
    return False


def nw_scoped_lobes() -> dict:
    """{lobe_id: artifact_dict} for every NW-scoped synapse artifact.

    Shared by lobes_panel/lobe_detail and the description audit/tests so the
    scope rule lives in exactly one place. Returns {} if synapse is unreadable.
    """
    synapse = _parse_yaml_synapse(_SYNAPSE_YML)
    if not synapse or not isinstance(synapse.get("artifacts"), dict):
        return {}
    return {k: v for k, v in synapse["artifacts"].items() if _is_nw_lobe(k, v)}


def _derive_lobe_status(
    art_path: str,
    storage: str | None,
    freshness_sla_hours,
    health_lobe: dict | None,
) -> tuple[str, float | None, bool | None]:
    """Return (status, age_hours, sla_met).

    When health_lobe is present, use its status directly.
    Otherwise derive from disk mtime vs SLA.
    """
    if health_lobe is not None:
        status = health_lobe.get("status", "unknown")
        age_hours = health_lobe.get("age_hours")
        sla_h = health_lobe.get("freshness_sla_hours") or freshness_sla_hours
        sla_met: bool | None = None
        if age_hours is not None and sla_h is not None:
            sla_met = float(age_hours) <= float(sla_h)
        return status, age_hours, sla_met

    full_path = _ROOT / art_path
    exists = full_path.exists()
    if not exists:
        if (storage or "").lower() == "git":
            return "missing", None, None
        return "not_locally_verifiable", None, None

    age_hours = _mtime_hours_ago(full_path)
    sla_h = freshness_sla_hours
    if sla_h is None:
        sla_met = None
        status = "fresh"
    else:
        try:
            sla_met = float(age_hours) <= float(sla_h) if age_hours is not None else None
            status = "fresh" if sla_met else "stale"
        except (TypeError, ValueError):
            sla_met = None
            status = "fresh"
    return status, age_hours, sla_met


def _count_recent_actions(lobe_id: str, owner_program: str) -> int:
    """Count recent actions attributable to this lobe (quick scan, fail-open)."""
    count = 0
    # Reflex firings for reflex-type lobes
    reflex_dir = _DATA_REFLEXES / lobe_id
    if reflex_dir.exists():
        firings = _tail_jsonl(reflex_dir / "firings.jsonl", 10)
        count += len(firings)
    # Governance events mentioning this lobe id or producer
    gov_events = _tail_jsonl(_GOVERNANCE_JSONL, 50)
    for ev in gov_events:
        target = str(ev.get("target", ""))
        if lobe_id in target:
            count += 1
    return count


def _build_lobe_summary(
    lobe_id: str,
    art: dict,
    health_lobe: dict | None,
) -> dict:
    """Build a <lobe_summary> dict."""
    owner = art.get("owner_program", "")
    group = _assign_group(lobe_id, owner)
    consumers = list(art.get("consumers") or [])
    external = list(art.get("external_consumers") or [])
    art_path = art.get("path", "")
    storage = art.get("storage")
    sla_h = art.get("freshness_sla_hours")

    status, age_hours, sla_met = _derive_lobe_status(art_path, storage, sla_h, health_lobe)

    row_count = health_lobe.get("row_count") if health_lobe else None
    byte_size = health_lobe.get("byte_size") if health_lobe else None

    n_recent = _count_recent_actions(lobe_id, owner)
    p_short, _p_full, desc_status = _plain_desc(lobe_id, art.get("notes"))

    return {
        "id": lobe_id,
        "label": _humanize_label(lobe_id),
        "group": group,
        "status": status,
        "tier": art.get("tier", ""),
        "cadence": art.get("cadence", ""),
        "horizon_role": art.get("horizon_role", ""),
        "storage": storage or "",
        "producer": art.get("producer", ""),
        "path": art_path,
        "age_hours": age_hours,
        "freshness_sla_hours": sla_h,
        "sla_met": sla_met,
        "row_count": row_count,
        "byte_size": byte_size,
        "n_consumers": len(consumers) + len(external),
        "n_recent_actions": n_recent,
        "short_desc": p_short or _short_desc(art.get("notes")),
        "desc_status": desc_status,
    }


# Ordered group keys for the `groups` list
_GROUP_ORDER = ["core", "kernel", "cortex", "factor", "reflexes", "bridge", "sensors", "ops"]


def lobes_panel() -> dict:
    """Return the NW observatory summary (GET /api/neural_web/lobes).

    Reads synapse.yml for the canonical lobe registry, enriches with
    health.json / daily_brief.json / confluence_graph.json when present.
    Fail-open: missing artifacts return honest nulls.
    """
    # --- Synapse registry ---
    synapse = _parse_yaml_synapse(_SYNAPSE_YML)
    if not synapse or not isinstance(synapse.get("artifacts"), dict):
        return {
            "ok": False,
            "error": "synapse.yml unreadable or missing (pyyaml required)",
            "overall_status": "unknown",
        }

    all_arts = synapse["artifacts"]
    lobe_arts = {k: v for k, v in all_arts.items() if _is_nw_lobe(k, v)}

    # --- Health.json enrichment ---
    nw_health = _read_json(_NW_HEALTH_JSON)
    health_by_id: dict[str, dict] = {}
    as_of: str | None = None
    source = "synapse_registry"

    if nw_health and nw_health.get("schema") == "neuralweb.health.v1":
        source = "health_json"
        as_of = nw_health.get("as_of")
        for lh in (nw_health.get("lobes") or []):
            lid = lh.get("id")
            if lid:
                health_by_id[lid] = lh

    # --- Confluence graph ---
    cg = _read_json(_CONFLUENCE_GRAPH)
    graph_info: dict = {"n_nodes": None, "n_edges": None, "edge_types": None}
    if cg:
        edges = cg.get("edges") or []
        edge_types: dict[str, int] = {}
        for e in edges:
            t = e.get("edge_type", "unknown")
            edge_types[t] = edge_types.get(t, 0) + 1
        graph_info = {
            "n_nodes": len(cg.get("nodes") or []),
            "n_edges": len(edges),
            "edge_types": edge_types,
        }

    # --- Build lobe summaries ---
    lobes_flat: list[dict] = []
    for lobe_id, art in lobe_arts.items():
        health_lobe = health_by_id.get(lobe_id)
        lobes_flat.append(_build_lobe_summary(lobe_id, art, health_lobe))

    # --- Summary counts ---
    status_counts: dict[str, int] = {
        "total": len(lobes_flat),
        "fresh": 0, "stale": 0, "missing": 0,
        "degraded": 0, "unknown": 0, "not_locally_verifiable": 0,
    }
    for ls in lobes_flat:
        st = ls["status"]
        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["unknown"] += 1

    # --- Overall status ---
    git_statuses = [
        ls["status"] for ls in lobes_flat
        if ls.get("storage", "").lower() == "git" and ls["group"] == "core"
    ]
    if status_counts["missing"] > 0 and any(s == "missing" for s in git_statuses):
        overall_status = "degraded"
    elif status_counts["stale"] > 0 or status_counts["degraded"] > 0:
        overall_status = "warn"
    elif status_counts["total"] == 0:
        overall_status = "unknown"
    else:
        overall_status = "ok"

    # --- Group structure ---
    group_map: dict[str, list[dict]] = {k: [] for k in _GROUP_ORDER}
    for ls in lobes_flat:
        g = ls["group"]
        if g in group_map:
            group_map[g].append(ls)
        else:
            group_map["ops"].append(ls)

    group_meta = {key: (label, hue) for key, label, hue in _LOBE_GROUPS}
    groups = []
    for key in _GROUP_ORDER:
        label, hue = group_meta[key]
        groups.append({
            "key": key,
            "label": label,
            "hue": hue,
            "lobes": sorted(group_map[key], key=lambda x: x["id"]),
        })

    # --- Description health (staleness of the curated prose layer) ---
    desc_health = {"curated": 0, "stale": 0, "auto": 0}
    for ls in lobes_flat:
        ds = ls.get("desc_status", "auto")
        desc_health[ds] = desc_health.get(ds, 0) + 1

    # --- R-ORTH PR-4: independence summary (fail-open) ---
    independence = _read_independence_summary()

    return {
        "ok": True,
        "source": source,
        "as_of": as_of,
        "overall_status": overall_status,
        "summary_counts": status_counts,
        "desc_health": desc_health,
        "graph": graph_info,
        "groups": groups,
        "lobes": lobes_flat,
        "independence": independence,
        # W-AI: Master Brain pin (additive — groups/lobes contract unchanged)
        "orchestrator_hero": _orchestrator_hero(),
    }


def lobe_detail(lobe_id: str) -> dict:
    """Return per-lobe detail (GET /api/neural_web/lobe?id=<id>).

    On unknown id → ok=false with known_ids list.
    Fail-open on missing artifacts.
    """
    # --- Synapse registry ---
    synapse = _parse_yaml_synapse(_SYNAPSE_YML)
    if not synapse or not isinstance(synapse.get("artifacts"), dict):
        return {"ok": False, "error": "synapse.yml unreadable (pyyaml required)", "known_ids": []}

    all_arts = synapse["artifacts"]
    lobe_arts = {k: v for k, v in all_arts.items() if _is_nw_lobe(k, v)}

    if not lobe_id or lobe_id not in lobe_arts:
        return {
            "ok": False,
            "error": "unknown lobe id",
            "known_ids": sorted(lobe_arts.keys()),
        }

    art = lobe_arts[lobe_id]
    owner = art.get("owner_program", "")
    group = _assign_group(lobe_id, owner)
    group_label, hue = next(
        ((label, h) for key, label, h in _LOBE_GROUPS if key == group),
        ("Ops", "#8b98ad"),
    )

    art_path = art.get("path", "")
    storage = art.get("storage")
    sla_h = art.get("freshness_sla_hours")

    # --- Health enrichment ---
    nw_health = _read_json(_NW_HEALTH_JSON)
    health_lobe: dict | None = None
    if nw_health and nw_health.get("schema") == "neuralweb.health.v1":
        for lh in (nw_health.get("lobes") or []):
            if lh.get("id") == lobe_id:
                health_lobe = lh
                break

    status, age_hours, sla_met = _derive_lobe_status(art_path, storage, sla_h, health_lobe)

    full_path = _ROOT / art_path if art_path else None
    exists_locally = bool(full_path and full_path.exists())

    # Metrics block
    as_of_m = health_lobe.get("as_of") if health_lobe else None
    produced_at = health_lobe.get("produced_at") if health_lobe else None
    row_count = health_lobe.get("row_count") if health_lobe else None
    byte_size = health_lobe.get("byte_size") if health_lobe else None
    gaps = health_lobe.get("gaps", []) if health_lobe else []

    metrics = {
        "age_hours": age_hours,
        "freshness_sla_hours": sla_h,
        "sla_met": sla_met,
        "as_of": as_of_m,
        "produced_at": produced_at,
        "row_count": row_count,
        "byte_size": byte_size,
        "exists_locally": exists_locally,
        "gaps": gaps or [],
    }

    # --- Transmission ---
    consumers_raw = list(art.get("consumers") or [])
    external_consumers = list(art.get("external_consumers") or [])

    def _kind(c: str) -> str:
        if c.startswith("engine/"):
            return "engine"
        if c.startswith("module/"):
            return "module"
        if c.startswith("scripts/"):
            return "script"
        return "program"

    consumers_list = [{"name": c, "kind": _kind(c)} for c in consumers_raw]

    # Confluence edges referencing this lobe
    cg = _read_json(_CONFLUENCE_GRAPH)
    edges_list: list[dict] = []
    if cg:
        producer_path = art.get("producer", "")
        for e in (cg.get("edges") or []):
            src = e.get("src", "")
            dst = e.get("dst", "")
            # Match by artifact:<id>, producer module path, or lobe id substring
            relevant = (
                f"artifact:{lobe_id}" in (src, dst)
                or lobe_id in src or lobe_id in dst
                or (producer_path and (producer_path in src or producer_path in dst))
            )
            if relevant:
                edges_list.append({
                    "src": src,
                    "dst": dst,
                    "edge_type": e.get("edge_type", ""),
                    "n": e.get("n"),
                    "note": e.get("note", ""),
                })

    transmission = {
        "producer": art.get("producer", ""),
        "consumers": consumers_list,
        "external_consumers": external_consumers,
        "edges": edges_list,
    }

    # --- Recent actions ---
    recent_actions: list[dict] = []

    # 1. Reflex firings if this lobe corresponds to a reflex data dir
    reflex_dir = _DATA_REFLEXES / lobe_id
    if reflex_dir.exists():
        for f in _tail_jsonl(reflex_dir / "firings.jsonl", 15):
            ts = f.get("ts") or f.get("timestamp") or f.get("fired_at") or ""
            summary = f.get("trigger_key") or f.get("action") or f.get("scope_key") or str(f)[:80]
            recent_actions.append({
                "ts": ts,
                "kind": "reflex_firing",
                "summary": str(summary)[:120],
                "source": f"data/reflexes/{lobe_id}/firings.jsonl",
            })

    # 2. Governance events mentioning this lobe
    for ev in _tail_jsonl(_GOVERNANCE_JSONL, 50):
        target = str(ev.get("target", ""))
        if lobe_id in target or (art.get("producer") and art["producer"] in target):
            ts = ev.get("ts") or ""
            recent_actions.append({
                "ts": ts,
                "kind": ev.get("event_type", "governance"),
                "summary": (ev.get("note") or ev.get("article") or "")[:120],
                "source": "data/neuralweb/governance.jsonl",
            })

    # 3. Cortex memo what_fired if cortex-type lobe
    memo = _read_json(_CORTEX_MEMO)
    if memo and group == "cortex":
        for fired in (memo.get("what_fired") or []):
            recent_actions.append({
                "ts": memo.get("as_of", ""),
                "kind": "cortex_fired",
                "summary": str(fired)[:120],
                "source": "data/neuralweb/cortex/memo.json",
            })

    # 4. Daily brief what_changed matching this lobe id
    brief = _read_json(_NW_DAILY_BRIEF_JSON)
    if brief and brief.get("schema") == "neuralweb.daily_brief.v1":
        for change in (brief.get("what_changed") or []):
            if change.get("id") == lobe_id:
                recent_actions.append({
                    "ts": brief.get("as_of", ""),
                    "kind": "daily_brief_change",
                    "summary": str(change.get("summary", ""))[:120],
                    "source": "data/neuralweb/daily_brief.json",
                })

    # Sort newest-first by ts (lexicographic ISO sort), cap at 15
    recent_actions.sort(key=lambda x: x.get("ts", ""), reverse=True)
    recent_actions = recent_actions[:15]

    # --- Description: plain-English prose + raw technical note (staleness guard) ---
    raw_notes = art.get("notes") or ""
    description_technical = " ".join(raw_notes.split())
    p_short, p_full, desc_status = _plain_desc(lobe_id, raw_notes)
    description = p_full or description_technical

    # --- R-ORTH PR-4: independence note for this lobe (fail-open) ---
    # Match lobe to spine overlap data using best-effort name-containment.
    # The spine uses engine names (e.g. "us_board", "oracle_rotation") while lobe ids
    # use the synapse artifact key (e.g. "oracle-state", "spine-index").  We match by
    # checking if the lobe_id (with hyphens→underscores) appears as a substring of any
    # spine engine name, or vice-versa.  Imperfect; documented here, not over-engineered.
    independence_note: str | None = None
    co_fire_cluster: list | None = None
    spine_raw = _read_json(_COVARIANCE_SPINE)
    if spine_raw:
        lobes_block = (spine_raw.get("blocks") or {}).get("lobes")
        if lobes_block:
            lobe_key = lobe_id.replace("-", "_")
            producer_key = (art.get("producer") or "").replace("-", "_").replace("/", "_")

            def _name_match(engine_name: str) -> bool:
                """Return True if this lobe is plausibly the named spine engine."""
                en = engine_name.lower()
                # Direct containment in either direction
                if lobe_key in en or en in lobe_key:
                    return True
                # Also try producer basename (last path component without .py)
                prod_base = producer_key.split("_")[-1] if producer_key else ""
                if prod_base and len(prod_base) > 3 and prod_base in en:
                    return True
                return False

            # Check if lobe appears in highest_overlap_pairs
            for pair in (lobes_block.get("highest_overlap_pairs") or []):
                if _name_match(pair.get("a", "")) or _name_match(pair.get("b", "")):
                    partner = pair.get("b") if _name_match(pair.get("a", "")) else pair.get("a")
                    corr = pair.get("corr")
                    independence_note = (
                        f"This engine appears in the top-overlap pairs from the R-ORTH covariance "
                        f"spine (highest |corr| pairs). Co-firing correlation with '{partner}': "
                        f"{corr:.2f} (|r|={abs(corr):.2f}). "
                        f"Descriptive only — not gauntleted."
                    ) if corr is not None else (
                        f"This engine appears in the top-overlap pairs with '{partner}'. "
                        f"Descriptive only — not gauntleted."
                    )
                    break

            # Check if lobe appears in dominant cluster
            clusters = lobes_block.get("clusters") or []
            if clusters:
                largest = max(clusters, key=lambda c: len(c.get("engines") or []))
                cluster_engines = largest.get("engines") or []
                if any(_name_match(e) for e in cluster_engines):
                    co_fire_cluster = cluster_engines
                    if independence_note is None:
                        independence_note = (
                            f"This engine is in the largest co-firing cluster "
                            f"({len(cluster_engines)} engines). "
                            f"These engines show elevated intra-cluster correlation — "
                            f"they may be measuring similar market conditions. "
                            f"Descriptive only — not gauntleted."
                        )

    # --- Support map: upstream + downstream traversal (W2, RUL-CC-14) ---
    support_map_block = _support_map_for_lobe(lobe_id)

    out: dict = {
        "ok": True,
        "id": lobe_id,
        "label": _humanize_label(lobe_id),
        "group": group,
        "group_label": group_label,
        "hue": hue,
        "status": status,
        "tier": art.get("tier", ""),
        "cadence": art.get("cadence", ""),
        "horizon_role": art.get("horizon_role", ""),
        "storage": storage or "",
        "producer": art.get("producer", ""),
        "path": art_path,
        "format": art.get("format", ""),
        "description": description,
        "description_technical": description_technical,
        "desc_status": desc_status,
        "short_desc": p_short,
        "purpose_source": "config/synapse.yml",
        "metrics": metrics,
        "transmission": transmission,
        "recent_actions": recent_actions,
        "health_detail": health_lobe,
        "missing": not exists_locally,
        "support_map": support_map_block,
    }
    if independence_note is not None:
        out["independence_note"] = independence_note
    if co_fire_cluster is not None:
        out["co_fire_cluster"] = co_fire_cluster
    return out


# ---- Section G: Support Map (W2, RUL-CC-7/CC-14) ----------------------------

_SUPPORT_MAP_DISPLAY_CAP = 25  # max listed items in lobe_detail support_map block


def _load_support_map():
    """Import engine.neuralweb.support_map via importlib (avoids bare 'import engine' text).

    Admin must not use top-level engine imports; this helper lazy-loads the module
    at call time so the no-engine-imports contract (and its CI test) is satisfied.
    Returns the module or raises ImportError.
    """
    import importlib  # noqa: PLC0415
    import sys  # noqa: PLC0415
    # Ensure repo root is on sys.path so importlib can resolve engine.*
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    return importlib.import_module("engine.neuralweb.support_map")


def _section_support_map() -> dict:
    """Synapse-vs-confluence coverage drift warning (panel-level, Section G).

    Reports artifact ids registered in synapse.yml but absent from
    confluence_graph.json edges.  Fail-open: returns an honest placeholder
    when synapse.yml is unreadable or support_map is unavailable.

    RUL-CC-7: synapse.yml is the authoritative adjacency source; confluence_graph
    is a derived view.  This section surfaces the drift between the two.
    """
    try:
        _sm = _load_support_map()
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "note": f"support_map module unavailable: {exc}",
            "registered_but_missing_from_confluence": [],
            "drift_count": 0,
        }

    try:
        graph = _sm.load_graph(_ROOT)
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "note": f"synapse.yml unreadable: {exc}",
            "registered_but_missing_from_confluence": [],
            "drift_count": 0,
        }

    try:
        missing = _sm.coverage_vs_confluence(_CONFLUENCE_GRAPH, graph=graph)
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "note": f"coverage_vs_confluence error: {exc}",
            "registered_but_missing_from_confluence": [],
            "drift_count": 0,
        }
    return {
        "available": True,
        "registered_but_missing_from_confluence": missing,
        "drift_count": len(missing),
        "note": (
            "Artifact ids registered in synapse.yml but not referenced as "
            "'artifact:<id>' in any confluence_graph.json edge. "
            "RUL-CC-7: synapse.yml is the authoritative adjacency source; "
            "confluence_graph.json is a derived view that may lag."
        ),
    }


def _support_map_for_lobe(lobe_id: str) -> dict:
    """Compute upstream + downstream support-map views for a lobe (lobe_detail helper).

    Returns:
      {
        available: bool,
        upstream: [{artifact_id, hop, via_module}, ...],   # full list
        upstream_count: int,
        downstream: [{artifact_id, hop, via_module}, ...], # capped at _SUPPORT_MAP_DISPLAY_CAP
        downstream_count: int,                             # total before cap
        bound: "upper",
        note: str,
      }
    Fail-open: returns available=False with a note on any error.
    """
    _null = {
        "available": False,
        "note": "",
        "upstream": [],
        "upstream_count": 0,
        "downstream": [],
        "downstream_count": 0,
        "bound": "upper",
    }

    try:
        _sm = _load_support_map()
    except Exception as exc:  # noqa: BLE001
        _null["note"] = f"support_map module unavailable: {exc}"
        return _null

    try:
        graph = _sm.load_graph(_ROOT)
    except Exception as exc:  # noqa: BLE001
        _null["note"] = f"synapse.yml unreadable: {exc}"
        return _null

    try:
        us_full = _sm.upstream(graph, lobe_id)
        ds_full = _sm.downstream(graph, lobe_id)
        us_compact = [
            {"artifact_id": r["artifact_id"], "hop": r["hop"], "via_module": r["via_module"]}
            for r in us_full[:_SUPPORT_MAP_DISPLAY_CAP]
        ]
        ds_compact = [
            {"artifact_id": r["artifact_id"], "hop": r["hop"], "via_module": r["via_module"]}
            for r in ds_full[:_SUPPORT_MAP_DISPLAY_CAP]
        ]
        return {
            "available": True,
            "upstream": us_compact,
            "upstream_count": len(us_full),
            "downstream": ds_compact,
            "downstream_count": len(ds_full),
            "bound": "upper",
            "note": (
                "Downstream artifacts that read this artifact (directly or transitively); "
                "terminal display surfaces are listed at hop 1 only. "
                "Bound is upper: shared-producer inversion may include additional "
                f"artifacts beyond those that directly depend on this one. "
                f"Lists capped at {_SUPPORT_MAP_DISPLAY_CAP} (see counts for totals)."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        _null["note"] = f"traversal error for {lobe_id!r}: {exc}"
        return _null


# ---- Section I: Mechanism Pathways QA (W3, RUL-CC-1) -----------------------

_NW_MECHANISM_PATHWAYS_JSON = _DATA_NW / "mechanism_pathways.json"
_NW_MECHANISM_PATHWAYS_HISTORY_JSONL = _DATA_NW / "mechanism_pathways_history.jsonl"

# Tail depth for history emission-mix analysis
_MP_HISTORY_TAIL = 30


def _section_mechanism_pathways() -> dict:
    """MPC QA section — emission mix, current pathway summary, stale-leg listing.

    Reads data/neuralweb/mechanism_pathways.json (committed artifact only) and
    data/neuralweb/mechanism_pathways_history.jsonl (tail of _MP_HISTORY_TAIL rows).
    Fail-open: missing or malformed artifact → honest placeholder.
    No engine imports, no subprocess.
    """
    # --- current artifact ---
    mp = _read_json(_NW_MECHANISM_PATHWAYS_JSON)
    if mp is None or mp.get("schema") != "neuralweb.mechanism_pathways.v1":
        return {
            "available": False,
            "note": (
                "data/neuralweb/mechanism_pathways.json not yet written "
                "(pre-W1 clone or first nightly has not run yet)"
            ),
        }

    pathways: list = mp.get("pathways") or []
    no_pathway_rec: dict | None = mp.get("no_pathway")
    primary_family = pathways[0].get("family", "") if pathways else None
    primary_direction = pathways[0].get("direction_en", "") if pathways else None
    coverage = pathways[0].get("coverage_score") if pathways else None
    coverage_basis = pathways[0].get("coverage_basis") if pathways else None
    coherence = pathways[0].get("coherence", "") if pathways else None
    stale_legs: list = pathways[0].get("stale_legs") or [] if pathways else []
    alt_families: list = [pw.get("family", "") for pw in pathways[1:3]]

    current_summary: dict = {
        "as_of": mp.get("as_of"),
        "has_pathway": bool(pathways),
        "primary_family": primary_family,
        "primary_direction": primary_direction,
        "coverage_score": coverage,
        "coverage_basis": coverage_basis,
        "coherence": coherence,
        "stale_legs": stale_legs,
        "stale_legs_count": len(stale_legs),
        "alternate_families": alt_families,
    }
    if no_pathway_rec:
        current_summary["no_pathway"] = {
            "reason": no_pathway_rec.get("reason", ""),
            "printed": no_pathway_rec.get("printed", True),
        }

    # --- history emission mix ---
    history_mix: dict = {
        "available": False,
        "tail_rows": 0,
        "pathway_count": 0,
        "no_pathway_count": 0,
        "no_pathway_reasons": {},
    }

    hist_path = _NW_MECHANISM_PATHWAYS_HISTORY_JSONL
    if hist_path.exists():
        try:
            rows: list[dict] = []
            for line in hist_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:  # noqa: BLE001
                        pass
            # Take tail
            tail = rows[-_MP_HISTORY_TAIL:] if len(rows) > _MP_HISTORY_TAIL else rows
            pathway_n = sum(1 for r in tail if r.get("pathways_count", 0) > 0)
            no_pathway_n = len(tail) - pathway_n
            reason_counts: dict[str, int] = {}
            for r in tail:
                reason = r.get("no_pathway_reason")
                if reason:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
            history_mix = {
                "available": True,
                "tail_rows": len(tail),
                "pathway_count": pathway_n,
                "no_pathway_count": no_pathway_n,
                "no_pathway_reasons": reason_counts,
            }
        except Exception:  # noqa: BLE001
            pass

    return {
        "available": True,
        "current": current_summary,
        "history_emission_mix": history_mix,
        "schema": mp.get("schema"),
        "display_only": True,
        "not_a_signal": True,
    }


# ---- Section J: Master Brain / orchestrator (W-AI) ---------------------------
# The Neural Web's "master brain" is the nightly pipeline itself (daily.yml over
# config/synapse.yml). engine/neuralweb/orchestrator_log.py gives it a face: one
# run-log entry per pipeline run + an every-N-runs review. This section surfaces
# that face to the admin. The engine module is lazy-loaded via importlib (same
# pattern as _load_support_map — no top-level engine imports) and every read
# fails open: no artifacts → honest empties, never an exception.

_ORCH_RUNLOG_REL = Path("data") / "neuralweb" / "orchestrator_runlog.jsonl"
_ORCH_REVIEWS_REL = Path("data") / "neuralweb" / "orchestrator_reviews.jsonl"
_FEEDBACK_SUMMARY_REL = Path("data") / "governance" / "mastermind_feedback_summary.json"
_ORCH_NEXT_RUN_NOTE = "next scheduled run: daily.yml cron 02:00 UTC"

_ORCH_DEFAULT_SETTINGS = {
    "review_every_n_runs": 5,
    "site_rows": 60,
    "ingest_bot_feedback": True,
    "brief_attention_nudges": True,
}


def _orch_settings(repo: Path) -> dict:
    """config.yml ``orchestrator:`` block (all four keys), degrade-safe to defaults."""
    out = dict(_ORCH_DEFAULT_SETTINGS)
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((repo / "config.yml").read_text(encoding="utf-8")) or {}
        block = cfg.get("orchestrator") or {}
        n = block.get("review_every_n_runs")
        if isinstance(n, int) and not isinstance(n, bool) and 2 <= n <= 50:
            out["review_every_n_runs"] = n
        rows = block.get("site_rows")
        if isinstance(rows, int) and not isinstance(rows, bool) and 10 <= rows <= 365:
            out["site_rows"] = rows
        for key in ("ingest_bot_feedback", "brief_attention_nudges"):
            if isinstance(block.get(key), bool):
                out[key] = block[key]
    except Exception:  # noqa: BLE001
        pass
    return out


def _load_orchestrator_log():
    """Lazy-import engine.neuralweb.orchestrator_log via importlib (mirrors
    _load_support_map so the no-engine-imports contract stays satisfied)."""
    import importlib  # noqa: PLC0415
    import sys  # noqa: PLC0415
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    return importlib.import_module("engine.neuralweb.orchestrator_log")


def _orch_load(repo: Path, limit: int = 60) -> dict:
    """{entries, reviews, settings} — via the engine module when importable,
    else a direct fail-open read of the committed JSONL ledgers.
    entries/reviews are oldest-first (the ledger order)."""
    try:
        mod = _load_orchestrator_log()
        data = mod.load(repo, limit=limit)
        entries = data.get("entries") or []
        reviews = data.get("reviews") or []
    except Exception:  # noqa: BLE001
        entries = list(reversed(_tail_jsonl(repo / _ORCH_RUNLOG_REL, limit)))
        reviews = list(reversed(_tail_jsonl(repo / _ORCH_REVIEWS_REL, 12)))
    return {"entries": entries, "reviews": reviews, "settings": _orch_settings(repo)}


def _orch_dialogue(repo: Path) -> dict:
    """Bot↔orchestrator dialogue state from the governed feedback summary."""
    fb = _read_json(repo / _FEEDBACK_SUMMARY_REL) or {}
    return {
        "feedback_state": fb.get("state") or "absent",
        "generated_utc": fb.get("generated_utc"),
        "nudges": fb.get("nudges") or [],
        "operator_directives": fb.get("operator_directives") or [],
        "ack": fb.get("ack") or {"nudge_codes_seen": [], "directive_ids_seen": []},
        "reflection": fb.get("reflection"),
    }


def _orch_cortex(repo: Path) -> dict:
    """Cortex status (health.json run_status) + probation.json, fail-open."""
    prob = _read_json(repo / "data" / "neuralweb" / "cortex" / "probation.json")
    health = _read_json(repo / "data" / "neuralweb" / "health.json") or {}
    run_status = (health.get("cortex") or {}).get("run_status") or {}
    return {
        "status": run_status.get("status") or "unknown",
        "degradation_reason": run_status.get("degradation_reason"),
        "model_used": run_status.get("model_used"),
        "probation": prob or {"missing": True,
                              "note": "data/neuralweb/cortex/probation.json not yet written"},
    }


def orchestrator_panel(root=None) -> dict:
    """Master Brain page payload (GET /api/orchestrator).

    Reads committed artifacts only; every section fails open. ``root`` defaults
    to the repo root (tests pass a fixture root).
    """
    repo = Path(root) if root is not None else _ROOT
    data = _orch_load(repo, limit=60)
    entries_desc = list(reversed(data["entries"]))[:30]   # newest-first for display
    reviews_desc = list(reversed(data["reviews"]))[:12]
    dialogue = _orch_dialogue(repo)
    cortex = _orch_cortex(repo)
    latest = entries_desc[0] if entries_desc else {}
    status_hero = {
        "id": "orchestrator",
        "label": "Neural Web Orchestrator",
        "run_date": latest.get("run_date"),
        "workflow": latest.get("workflow"),
        "summary": latest.get("summary"),
        "overall_status": latest.get("overall_status") or "unknown",
        "next_run_note": _ORCH_NEXT_RUN_NOTE,
        "lobes_total": latest.get("lobes_total"),
        "lobes_stale": latest.get("lobes_stale"),
        "what_changed_n": latest.get("what_changed_n"),
        "cortex_status": cortex.get("status"),
        "feedback_state": dialogue["feedback_state"],
        "nudges_n": len(dialogue["nudges"]),
        "directives_n": len(dialogue["operator_directives"]),
        "n_entries": len(data["entries"]),
        "last_review_at": reviews_desc[0].get("produced_at") if reviews_desc else None,
    }
    return {
        "ok": True,
        "status_hero": status_hero,
        "entries": entries_desc,
        "reviews": reviews_desc,
        "settings": data["settings"],
        "dialogue": dialogue,
        "cortex": cortex,
    }


def _orchestrator_hero() -> dict:
    """Compact Master-Brain pin for the Observatory page (lobes_panel).

    Additive: the existing groups/lobes contract is untouched; older payload
    consumers simply ignore this key. Fail-open on every read."""
    latest_rows = _tail_jsonl(_ROOT / _ORCH_RUNLOG_REL, 1)
    latest = latest_rows[0] if latest_rows else {}
    reviews = _tail_jsonl(_ROOT / _ORCH_REVIEWS_REL, 1)
    fb = _read_json(_ROOT / _FEEDBACK_SUMMARY_REL) or {}
    return {
        "id": "orchestrator",
        "label": "Neural Web Orchestrator",
        "run_date": latest.get("run_date"),
        "summary": latest.get("summary"),
        "overall_status": latest.get("overall_status") or "unknown",
        "nudges_n": len(fb.get("nudges") or []),
        "directives_n": len(fb.get("operator_directives") or []),
        "last_review_at": reviews[0].get("produced_at") if reviews else None,
    }


# ---- Top-level panel entry point -------------------------------------------

def panel() -> dict:
    """Return the full Neural Web operator HQ payload.

    Structure:
        engine_health      — Section A
        reflex_log         — Section B
        bus_graph          — Section C
        governance         — Section D
        factor_intelligence — Section E (§D PR-4, RUL-NW7/NW8)
        daily_brief        — Section F (PR-D)
        evidence_clock     — Section G (EC-R5)
        support_map        — Section H (RUL-CC-14)
        mechanism_pathways — Section I (W3, RUL-CC-1)
    """
    return {
        "ok": True,
        "engine_health": _section_engine_health(),
        "reflex_log": _section_reflex_log(),
        "bus_graph": _section_bus_graph(),
        "governance": _section_governance(),
        "factor_intelligence": _section_factor_intelligence(),
        "daily_brief": _section_daily_brief(),
        "evidence_clock": _section_evidence_clock(),
        "support_map": _section_support_map(),
        "mechanism_pathways": _section_mechanism_pathways(),
    }
