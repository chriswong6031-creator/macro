"""engine.neuralweb.daily_brief — deterministic Neural Web daily brief (PR-D).

Produces a machine-readable "what did Neural Web do today?" surface.

Design
------
- Fail-open: every input is optional; missing input degrades gracefully to an
  explicit gap note. Never raises; always returns a dict.
- Deterministic: no LLM, no randomness, no NLP. All text is template-filled
  from structured artifact values.
- Display-only: no signals, no trade recommendations, no buy/sell language.
  Caveat strings are hard-coded and included in every output.
- Two-phase: engine job writes phase='engine'; cortex job finalizes
  phase='final' and upserts a compact history row.
- Delta method: compact snapshot compared against the last history row;
  changes reported as what_changed / what_is_stale / what_contradicted.
- qi domain in world_state is NEVER read (pending border ruling); any qi
  key present in world_state is silently ignored.

Schema: 'neuralweb.daily_brief.v1'
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_NW = _ROOT / "data" / "neuralweb"

SCHEMA = "neuralweb.daily_brief.v1"

# Domains forbidden from reading (pending border ruling)
_FORBIDDEN_DOMAINS = frozenset({"qi"})

# Trading verbs that must never appear in any output string
TRADING_VERBS = frozenset({"buy", "sell", "hold", "add", "trim", "long", "short",
                           "overweight", "underweight"})

# Fixed caveat strings
_CAVEATS = [
    "deterministic: all text is template-filled from structured artifact values; no LLM or NLP",
    "display-only: no signals or scoring authority; context only",
    "no trading authority: this brief contains no buy/sell/hold recommendations",
    "contradiction records are display-only annotations per hard law (engine/neuralweb/contradictions.py)",
]

# Freshness SLA used for staleness assessment (hours)
_DEFAULT_FRESHNESS_SLA_H = 30.0


# ---- helpers -----------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _iso_hours_ago(ts_str: str | None) -> float | None:
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        return round((now - dt).total_seconds() / 3600, 2)
    except Exception:  # noqa: BLE001
        return None


def _safe_str(x: Any) -> str:
    """Return a clean string representation, never raising."""
    if x is None:
        return ""
    return str(x)


def _scrub_trading_verbs(text: str) -> str:
    """Redact trading verbs from dynamically-sourced text.

    Replaces each word-boundary match of a TRADING_VERBS token with '[redacted]'
    and logs a warning.  Never raises so the brief always ships.
    Called on every externally-sourced produced string before it enters the
    artifact (contradiction summaries, P3 lobe-gap labels).
    """
    import re
    result = text
    for verb in TRADING_VERBS:
        pattern = re.compile(r'(?<!\w)' + re.escape(verb) + r'(?!\w)', re.IGNORECASE)
        if pattern.search(result):
            log.warning("daily_brief: scrubbed trading verb '%s' from upstream string: %s",
                        verb, text[:120])
            result = pattern.sub("[redacted]", result)
    return result


# ---- input readers -----------------------------------------------------------

def _load_health(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "health.json"
    d = _read_json(p)
    if d and d.get("schema") == "neuralweb.health.v1":
        return d
    return None


def _load_world_state(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "world_state.json"
    return _read_json(p)


def _load_mastermind_context(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "mastermind_context.json"
    return _read_json(p)


def _load_confluence_graph(root: Path) -> dict | None:
    p = root / "site" / "neuralwebdata" / "confluence_graph.json"
    return _read_json(p)


def _load_cortex_memo(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "cortex" / "memo.json"
    return _read_json(p)


def _load_history(root: Path) -> list[dict]:
    p = root / "data" / "neuralweb" / "daily_brief_history.jsonl"
    if not p.exists():
        return []
    try:
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        return rows
    except Exception:  # noqa: BLE001
        return []


def _load_prior_brief(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "daily_brief.json"
    d = _read_json(p)
    if d and d.get("schema") == SCHEMA:
        return d
    return None


# ---- did-the-brain-run section -----------------------------------------------

def _build_brain_run(health: dict | None, memo: dict | None) -> dict:
    """Extract cortex run summary from health artifact."""
    out: dict[str, Any] = {
        "cortex_status": "unknown",
        "tool_call_batches": None,
        "individual_tool_calls": None,
        "context_stale": None,
        "summary": None,
    }

    if health is None:
        out["cortex_status"] = "unknown"
        out["summary"] = "health.json not available — cortex status unknown"
        return out

    cortex = health.get("cortex") or {}
    out["cortex_status"] = cortex.get("status", "unknown")

    run_status = cortex.get("run_status") or {}
    out["tool_call_batches"] = run_status.get("tool_call_batches")
    out["individual_tool_calls"] = run_status.get("individual_tool_calls")
    out["context_stale"] = run_status.get("context_stale", False)

    # Narrative summary line
    cs = out["cortex_status"]
    memo_as_of = cortex.get("memo_as_of") or ""
    if cs == "fresh":
        tc = out["individual_tool_calls"]
        tc_str = f" ({tc} tool calls)" if tc is not None else ""
        out["summary"] = f"cortex ran{tc_str}; memo as_of {memo_as_of}"
    elif cs == "degraded":
        reason = run_status.get("degradation_reason") or "unknown reason"
        out["summary"] = f"cortex degraded — {reason}"
    elif cs == "missing":
        out["summary"] = "cortex memo missing — no cortex run recorded"
    else:
        out["summary"] = f"cortex status: {cs}"

    return out


# ---- compact snapshot for delta -----------------------------------------------

def _build_snapshot(health: dict | None, contradictions: list[dict]) -> dict:
    """Build compact snapshot for history delta comparison."""
    snap: dict[str, Any] = {
        "as_of": None,
        "lobe_status": {},
        "contradiction_count": len(contradictions),
        "contradiction_ids": sorted(c.get("id", "") for c in contradictions),
        "cortex_status": "unknown",
    }

    if health:
        snap["as_of"] = health.get("as_of")
        snap["cortex_status"] = (health.get("cortex") or {}).get("status", "unknown")
        for lobe in health.get("lobes", []):
            lid = lobe.get("id")
            if lid:
                snap["lobe_status"][lid] = {
                    "as_of": lobe.get("as_of"),
                    "status": lobe.get("status"),
                    "row_count": lobe.get("row_count"),
                }

    return snap


# ---- delta detection ---------------------------------------------------------

def _detect_changes(current_snap: dict, prior_snap: dict | None) -> list[dict]:
    """Detect meaningful changes between current and prior snapshot."""
    if prior_snap is None:
        return [{
            "kind": "first_run",
            "id": "system",
            "summary": "no prior brief found — this is the first run",
            "severity": "info",
            "evidence_path": "data/neuralweb/daily_brief_history.jsonl",
        }]

    changes: list[dict] = []

    # as_of advanced
    cur_as_of = current_snap.get("as_of")
    prev_as_of = prior_snap.get("as_of")
    if cur_as_of and prev_as_of and cur_as_of > prev_as_of:
        changes.append({
            "kind": "as_of_advanced",
            "id": "system",
            "summary": f"as_of advanced from {prev_as_of} to {cur_as_of}",
            "severity": "info",
            "evidence_path": "data/neuralweb/health.json",
        })

    # cortex status changed
    cur_cs = current_snap.get("cortex_status", "unknown")
    prev_cs = prior_snap.get("cortex_status", "unknown")
    if cur_cs != prev_cs:
        sev = "warn" if cur_cs in ("degraded", "missing") else "info"
        changes.append({
            "kind": "cortex_status_changed",
            "id": "cortex",
            "summary": f"cortex status changed: {prev_cs} → {cur_cs}",
            "severity": sev,
            "evidence_path": "data/neuralweb/health.json",
        })

    # lobe status or row_count changed
    cur_lobes = current_snap.get("lobe_status", {})
    prev_lobes = prior_snap.get("lobe_status", {})
    for lid, cur in cur_lobes.items():
        prev = prev_lobes.get(lid)
        if prev is None:
            changes.append({
                "kind": "lobe_new",
                "id": lid,
                "summary": f"lobe {lid} appeared in scope",
                "severity": "info",
                "evidence_path": "data/neuralweb/health.json",
            })
            continue
        if cur.get("status") != prev.get("status"):
            sev = "warn" if cur.get("status") in ("stale", "missing", "degraded") else "info"
            changes.append({
                "kind": "lobe_status_changed",
                "id": lid,
                "summary": f"lobe {lid} status: {prev.get('status')} → {cur.get('status')}",
                "severity": sev,
                "evidence_path": "data/neuralweb/health.json",
            })
        # row_count changed >1% or >10 rows
        cur_rc = cur.get("row_count")
        prev_rc = prev.get("row_count")
        if cur_rc is not None and prev_rc is not None and cur_rc != prev_rc:
            delta = abs(cur_rc - prev_rc)
            pct = delta / max(prev_rc, 1) * 100
            if delta > 10 or pct > 1:
                # as_of advanced for this lobe
                if cur.get("as_of") and prev.get("as_of") and cur["as_of"] > prev["as_of"]:
                    changes.append({
                        "kind": "lobe_refresh",
                        "id": lid,
                        "summary": f"lobe {lid} refreshed: as_of {prev['as_of']} → {cur['as_of']}, rows {prev_rc} → {cur_rc}",
                        "severity": "info",
                        "evidence_path": "data/neuralweb/health.json",
                    })
                else:
                    changes.append({
                        "kind": "lobe_row_count_changed",
                        "id": lid,
                        "summary": f"lobe {lid} row count changed: {prev_rc} → {cur_rc} ({pct:.0f}%)",
                        "severity": "info",
                        "evidence_path": "data/neuralweb/health.json",
                    })

    # lobes that disappeared
    for lid in prev_lobes:
        if lid not in cur_lobes:
            changes.append({
                "kind": "lobe_removed",
                "id": lid,
                "summary": f"lobe {lid} no longer in scope",
                "severity": "watch",
                "evidence_path": "data/neuralweb/health.json",
            })

    return changes


# ---- contradiction delta ------------------------------------------------------

def _load_contradictions(graph: dict | None, mc: dict | None) -> list[dict]:
    """Load contradiction records from available artifacts. Display-only."""
    records: list[dict] = []

    # Try confluence_graph first (most complete)
    if graph and isinstance(graph.get("contradiction_records"), list):
        records = list(graph["contradiction_records"])
    elif graph and isinstance((graph.get("contradiction_summary") or {}).get("records"), list):
        records = list(graph["contradiction_summary"]["records"])

    # Fall back to mastermind_context lobes.contradictions.records
    if not records and mc:
        lobes_mc = mc.get("lobes") or {}
        if isinstance(lobes_mc, dict):
            contr = lobes_mc.get("contradictions") or {}
            if isinstance(contr.get("records"), list):
                records = list(contr["records"])

    return records


def _contradiction_delta(current_records: list[dict], prior_snap: dict | None) -> list[dict]:
    """Compare contradiction ids vs prior snapshot."""
    prior_ids = set((prior_snap or {}).get("contradiction_ids", []))
    cur_ids = set(r.get("id", "") for r in current_records)

    items: list[dict] = []
    for r in current_records:
        rid = r.get("id", "")
        delta_vs_prior = "new" if rid not in prior_ids else "persisting"
        sev = r.get("severity", "note")
        ui_sev = "watch" if sev == "tension" else "info"
        raw_summary = r.get("description") or r.get("summary") or f"contradiction {rid}"
        items.append({
            "id": rid,
            "summary": _scrub_trading_verbs(raw_summary),
            "severity": ui_sev,
            "delta_vs_prior": delta_vs_prior,
            "evidence_path": "site/neuralwebdata/confluence_graph.json",
        })

    # Ids that were in prior but not current → no_longer_present (NEVER 'resolved')
    for rid in prior_ids:
        if rid and rid not in cur_ids:
            items.append({
                "id": rid,
                "summary": f"contradiction {rid} no longer present in current graph",
                "severity": "info",
                "delta_vs_prior": "no_longer_present",
                "evidence_path": "site/neuralwebdata/confluence_graph.json",
            })

    return items


# ---- staleness section --------------------------------------------------------

def _build_stale(health: dict | None) -> list[dict]:
    """Collect stale lobes from health artifact."""
    if health is None:
        return [{
            "id": "system",
            "as_of": None,
            "age_hours": None,
            "freshness_sla_hours": _DEFAULT_FRESHNESS_SLA_H,
            "severity": "warn",
        }]

    stale_items: list[dict] = []
    for lobe in health.get("lobes", []):
        if lobe.get("status") in ("stale", "missing", "degraded"):
            sla_h = lobe.get("freshness_sla_hours", _DEFAULT_FRESHNESS_SLA_H)
            age_h = lobe.get("age_hours")
            sev = "warn" if lobe.get("status") == "stale" else "watch"
            stale_items.append({
                "id": lobe.get("id", "unknown"),
                "as_of": lobe.get("as_of"),
                "age_hours": age_h,
                "freshness_sla_hours": sla_h,
                "severity": sev,
            })

    return stale_items


# ---- operator attention -------------------------------------------------------

def _build_operator_attention(
    health: dict | None,
    ws_missing: bool,
    mc_missing: bool,
    brain_run: dict,
    contradiction_delta: list[dict],
    prior_snap: dict | None,
    stale_lobes: list[dict],
    conformance_misses: list[dict],
) -> list[dict]:
    """Deterministic operator attention items."""
    items: list[dict] = []

    # P1: cortex degraded
    cs = brain_run.get("cortex_status", "unknown")
    if cs in ("degraded", "missing"):
        items.append({
            "priority": 1,
            "area": "cortex",
            "summary": f"cortex {cs} — inspect data/neuralweb/cortex/memo.json and run_status",
            "action_type": "ops_fix",
        })

    # P1: world_state missing
    if ws_missing:
        items.append({
            "priority": 1,
            "area": "world_state",
            "summary": "world_state.json missing — engine may not have completed",
            "action_type": "ops_fix",
        })

    # P1: mastermind_context missing
    if mc_missing:
        items.append({
            "priority": 1,
            "area": "mastermind_context",
            "summary": "mastermind_context.json missing — NW→Mastermind bridge may not have run",
            "action_type": "ops_fix",
        })

    # P1: context stale
    if brain_run.get("context_stale"):
        items.append({
            "priority": 1,
            "area": "cortex",
            "summary": "cortex context was stale at run time — check world_state freshness",
            "action_type": "inspect",
        })

    # P2: registered daily-engine lobe stale
    for s in stale_lobes:
        if s.get("severity") in ("warn", "watch"):
            items.append({
                "priority": 2,
                "area": s.get("id", "unknown"),
                "summary": f"lobe {s.get('id')} is {s.get('severity', 'stale')} — age {s.get('age_hours')}h vs SLA {s.get('freshness_sla_hours')}h",
                "action_type": "inspect",
            })

    # P2: workflow conformance miss
    if conformance_misses:
        for miss in conformance_misses:
            if isinstance(miss, dict) and miss.get("producer"):
                items.append({
                    "priority": 2,
                    "area": "dag_conformance",
                    "summary": f"producer {miss.get('producer')} not declared in daily.yml — update config/dag.yml",
                    "action_type": "ops_fix",
                })

    # P2: contradiction count increased
    prior_n = len((prior_snap or {}).get("contradiction_ids", []))
    cur_new = sum(1 for c in contradiction_delta if c.get("delta_vs_prior") == "new")
    if cur_new > 0:
        items.append({
            "priority": 2,
            "area": "contradictions",
            "summary": f"{cur_new} new contradiction(s) detected — inspect confluence_graph.json",
            "action_type": "follow_up",
        })

    # P3: fresh_partial gaps
    if health:
        for lobe in health.get("lobes", []):
            if lobe.get("status") == "fresh_partial" and lobe.get("gaps"):
                raw_gap_summary = f"lobe {lobe.get('id')} has gaps: {', '.join(str(g) for g in (lobe.get('gaps') or [])[:3])}"
                items.append({
                    "priority": 3,
                    "area": lobe.get("id", "unknown"),
                    "summary": _scrub_trading_verbs(raw_gap_summary),
                    "action_type": "follow_up",
                })

    # Sort by priority
    items.sort(key=lambda x: x["priority"])
    return items


# ---- candidate_watch ----------------------------------------------------------

def _build_candidate_watch(health: dict | None) -> dict:
    """Display-only counts from bottom_sensors lobe summary. No ticker-level details."""
    if health is None:
        return {"note": "health.json not available"}

    for lobe in health.get("lobes", []):
        if "bottom_sensors" in lobe.get("id", ""):
            return {
                "lobe_id": lobe.get("id"),
                "status": lobe.get("status"),
                "row_count": lobe.get("row_count"),
                "as_of": lobe.get("as_of"),
                "note": "display-only lobe summary; no ticker-level detail or buy language",
            }

    return {"note": "bottom_sensors lobe not found in health record"}


# ---- overall status ----------------------------------------------------------

def _brief_status(health: dict | None, brain_run: dict) -> str:
    """Derive brief status from health overall_status + cortex."""
    if health is None:
        return "degraded"
    overall = health.get("overall_status", "unknown")
    cs = brain_run.get("cortex_status", "unknown")
    if cs in ("degraded", "missing") or overall == "degraded":
        return "degraded"
    if overall == "warn":
        return "warn"
    return "ok"


# ---- evidence clock section --------------------------------------------------

def _build_evidence_clock(root: Path) -> dict:
    """Read data/neuralweb/evidence_clock.json and return a counts-only block.

    Public/site-safe: returns counts and morning_line only.  No blocking_reason
    prose, no readiness detail, no internal row text.

    Returns
    -------
    dict with key 'available' (bool) and, when available:
        as_of, counts (by_state + n_acknowledged), top_due, morning_line
    """
    p = root / "data" / "neuralweb" / "evidence_clock.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"available": False}

    if not isinstance(raw, dict):
        return {"available": False}
    if raw.get("schema") != "neuralweb.evidence_clock.v1":
        return {"available": False}

    # Type-guard summary: artifact may deliver a list or other non-dict (fix R2a)
    summary_raw = raw.get("summary")
    summary: dict = summary_raw if isinstance(summary_raw, dict) else {}

    # Type-guard by_state: must be a dict keyed by state strings (fix R2b)
    by_state_raw = summary.get("by_state")
    by_state: dict = by_state_raw if isinstance(by_state_raw, dict) else {}

    # Coerce every count value to int to guard against string artifacts (fix R2c)
    _STATE_KEYS = (
        "overdue", "due", "human_review", "missing", "stale",
        "blocked", "not_ready", "promotion_eligible", "accruing",
    )
    counts: dict = {}
    for _k in _STATE_KEYS:
        _v = by_state.get(_k, 0)
        counts[_k] = _v if isinstance(_v, int) else 0

    n_ack_raw = summary.get("n_acknowledged")
    n_ack: int = n_ack_raw if isinstance(n_ack_raw, int) else 0
    counts["n_acknowledged"] = n_ack

    # top_due: safe only when clock_id is a short public string (already in experiments.json)
    top_due_raw = summary.get("top_due")
    top_due = None
    if isinstance(top_due_raw, dict):
        _cid = top_due_raw.get("clock_id")
        if isinstance(_cid, str) and 0 < len(_cid) <= 120:
            top_due = {
                "clock_id": _cid,
                "due_at": top_due_raw.get("due_at"),
            }

    # Reconstruct morning_line locally — never pass artifact prose through to the
    # public site surface (fix R2, public-leak guard).
    _parts = []
    for _s in ("overdue", "due", "human_review", "missing", "stale", "blocked",
               "not_ready", "promotion_eligible", "accruing"):
        _n = counts.get(_s, 0)
        if _n > 0:
            _parts.append(f"{_n} {_s.replace('_', ' ')}")
    morning_line = (", ".join(_parts) + "." if _parts else "0 items.") + (
        f" Top due: {top_due['clock_id']}." if top_due else ""
    )

    return {
        "available": True,
        "as_of": raw.get("as_of"),
        "counts": counts,
        "top_due": top_due,
        "morning_line": morning_line,
    }


# ---- main build function ------------------------------------------------------

def build(root: Path | None = None, phase: str = "engine") -> dict:
    """
    Build the NW daily brief artifact.

    Parameters
    ----------
    root  : repo root (auto-detected if None)
    phase : 'engine' or 'final'

    Returns
    -------
    dict matching schema neuralweb.daily_brief.v1
    """
    if root is None:
        root = _ROOT

    now = _now_utc()

    # ---- load all inputs (all optional; fail-open) ----
    gaps_noted: list[str] = []

    health = _load_health(root)
    if health is None:
        gaps_noted.append("health.json missing or schema mismatch — lobe status unavailable")

    ws = _load_world_state(root)
    ws_missing = ws is None
    if ws_missing:
        gaps_noted.append("world_state.json missing")

    mc = _load_mastermind_context(root)
    mc_missing = mc is None
    if mc_missing:
        gaps_noted.append("mastermind_context.json missing")

    graph = _load_confluence_graph(root)
    if graph is None:
        gaps_noted.append("site/neuralwebdata/confluence_graph.json missing")

    evidence_clock = _build_evidence_clock(root)
    if not evidence_clock.get("available"):
        gaps_noted.append(
            "evidence_clock.json not present (PR1 not yet merged or build failed)"
        )

    memo = _load_cortex_memo(root)
    if memo is None:
        gaps_noted.append("data/neuralweb/cortex/memo.json missing")

    # history for delta
    history = _load_history(root)
    prior_snap = history[-1].get("snapshot") if history else None

    # ---- derive live_overlay staleness from world_state ----
    live_overlay_stale = False
    if ws and isinstance(ws.get("live_overlay"), dict):
        live_overlay_stale = bool(ws["live_overlay"].get("stale"))

    # ---- contradiction records ----
    contradiction_records = _load_contradictions(graph, mc)

    # ---- build sections ----
    brain_run = _build_brain_run(health, memo)

    current_snap = _build_snapshot(health, contradiction_records)
    as_of = current_snap.get("as_of") or now

    what_changed = _detect_changes(current_snap, prior_snap)
    what_contradicted = _contradiction_delta(contradiction_records, prior_snap)

    stale_lobes = _build_stale(health)
    conformance_misses = (health or {}).get("workflow_conformance_misses", [])

    operator_attention = _build_operator_attention(
        health=health,
        ws_missing=ws_missing,
        mc_missing=mc_missing,
        brain_run=brain_run,
        contradiction_delta=what_contradicted,
        prior_snap=prior_snap,
        stale_lobes=stale_lobes,
        conformance_misses=conformance_misses,
    )

    # P3: evidence-clock overdue items
    if evidence_clock.get("available"):
        n_overdue = (evidence_clock.get("counts") or {}).get("overdue", 0) or 0
        if n_overdue > 0:
            operator_attention.append({
                "priority": 3,
                "area": "evidence_clock",
                "summary": (
                    f"{n_overdue} evidence-clock item{'s' if n_overdue != 1 else ''} overdue"
                    " — see admin Observatory"
                ),
                "action_type": "follow_up",
            })
            operator_attention.sort(key=lambda x: x["priority"])

    candidate_watch = _build_candidate_watch(health)

    brief_status = _brief_status(health, brain_run)

    # ---- check live_overlay staleness → P1 ----
    if live_overlay_stale:
        operator_attention.insert(0, {
            "priority": 1,
            "area": "world_state",
            "summary": "live_overlay is stale in world_state.json — regime read may lag",
            "action_type": "inspect",
        })
        operator_attention.sort(key=lambda x: x["priority"])
        if brief_status == "ok":
            brief_status = "warn"

    return {
        "schema": SCHEMA,
        "produced_at": now,
        "as_of": as_of,
        "status": brief_status,
        "phase": phase,
        "did_the_brain_run": brain_run,
        "what_changed": what_changed,
        "what_contradicted": what_contradicted,
        "what_is_stale": stale_lobes,
        "operator_attention": operator_attention,
        "candidate_watch": candidate_watch,
        "evidence_clock": evidence_clock,
        "caveats": _CAVEATS,
        "_gaps": gaps_noted,
    }


def write(payload: dict, root: Path | None = None) -> None:
    """Write daily_brief.json to both data/ and site/ locations."""
    if root is None:
        root = _ROOT

    data_path = root / "data" / "neuralweb" / "daily_brief.json"
    site_path = root / "site" / "neuralwebdata" / "daily_brief.json"

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    for dest in (data_path, site_path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        log.info("daily_brief: wrote %s", dest)


def _build_compact_row(payload: dict, snapshot: dict) -> dict:
    """Build compact history row for upsert."""
    return {
        "as_of": payload.get("as_of"),
        "produced_at": payload.get("produced_at"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "snapshot": snapshot,
    }


def upsert_history(payload: dict, root: Path | None = None) -> None:
    """Upsert one compact history row keyed by as_of.

    Same as_of → replace row; file stays chronologically sorted; append otherwise.
    """
    if root is None:
        root = _ROOT

    history_path = root / "data" / "neuralweb" / "daily_brief_history.jsonl"

    # Load existing
    rows = []
    if history_path.exists():
        try:
            for line in history_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    # Extract current as_of from the payload (needed for health snapshot lookup)
    health = _load_health(root)
    contradiction_records = []
    if health:
        graph = _load_confluence_graph(root)
        mc = _load_mastermind_context(root)
        contradiction_records = _load_contradictions(graph, mc)

    snapshot = _build_snapshot(health, contradiction_records)
    new_row = _build_compact_row(payload, snapshot)
    new_as_of = new_row.get("as_of")

    # Replace existing row with same as_of, or append
    replaced = False
    if new_as_of:
        for i, row in enumerate(rows):
            if row.get("as_of") == new_as_of:
                rows[i] = new_row
                replaced = True
                break

    if not replaced:
        rows.append(new_row)

    # Sort chronologically
    rows.sort(key=lambda r: r.get("as_of") or "")

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    log.info("daily_brief: upserted history row as_of=%s (replaced=%s)", new_as_of, replaced)
