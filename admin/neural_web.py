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
        "short_desc": _short_desc(art.get("notes")),
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

    def _is_lobe(k: str, v: dict) -> bool:
        if v.get("owner_program") == "neural-web":
            return True
        p = v.get("path", "")
        if p.startswith("data/neuralweb/") or p.startswith("site/neuralwebdata/"):
            return True
        if "mastermind:context" in (v.get("external_consumers") or []):
            return True
        return False

    lobe_arts = {k: v for k, v in all_arts.items() if _is_lobe(k, v)}

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

    return {
        "ok": True,
        "source": source,
        "as_of": as_of,
        "overall_status": overall_status,
        "summary_counts": status_counts,
        "graph": graph_info,
        "groups": groups,
        "lobes": lobes_flat,
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

    def _is_lobe(k: str, v: dict) -> bool:
        if v.get("owner_program") == "neural-web":
            return True
        p = v.get("path", "")
        if p.startswith("data/neuralweb/") or p.startswith("site/neuralwebdata/"):
            return True
        if "mastermind:context" in (v.get("external_consumers") or []):
            return True
        return False

    lobe_arts = {k: v for k, v in all_arts.items() if _is_lobe(k, v)}

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

    # --- Description (full notes, whitespace-collapsed) ---
    raw_notes = art.get("notes") or ""
    description = " ".join(raw_notes.split())

    return {
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
        "purpose_source": "config/synapse.yml",
        "metrics": metrics,
        "transmission": transmission,
        "recent_actions": recent_actions,
        "health_detail": health_lobe,
        "missing": not exists_locally,
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
    """
    return {
        "ok": True,
        "engine_health": _section_engine_health(),
        "reflex_log": _section_reflex_log(),
        "bus_graph": _section_bus_graph(),
        "governance": _section_governance(),
        "factor_intelligence": _section_factor_intelligence(),
        "daily_brief": _section_daily_brief(),
    }
