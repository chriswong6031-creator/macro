"""engine/neuralweb/evidence_clock.py — Global Evidence Clock core logic.

Read-only aggregator.  Consumes every review-clock source in the repo and
produces ONE display-only artifact answering "what is due / stale /
underpowered / blocked today".

Rules (EC-R1..R8, ratified 2026-07-06 by ADJUDICATION_BY_FABLE.md):
  EC-R1  sources listed here; per-claim rows forbidden (rollups only).
  EC-R2  9-state vocabulary, deterministic assignment.
  EC-R3  precedence demotion order: governance > RF > qledger > trial >
         freshness > experiments > display clocks.
  EC-R4  one output artifact; packet stubs inline on due/overdue rows (cap 10).
  EC-R5  no site/ copy; authed admin + daily brief counts only.
  EC-R6  floor demotion: due but evidence_refs missing → not_ready.
  EC-R7  stale = first-class warning; regenerate_cmd from synapse producer.
  EC-R8  ack reads evidence_clock_reviews.jsonl; never writes it.

Hard constraints:
  - stdlib + yaml + json only (no pandas, no alert/scoring imports)
  - never import from money-path modules
  - always returns a valid packet; never raises (callers catch internally)
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml  # PyYAML — available in the engine environment

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.evidence_clock.v1"
AUTHORITY = "display_only"

VALID_STATES = frozenset({
    "accruing", "due", "overdue", "stale", "missing",
    "blocked", "promotion_eligible", "human_review", "not_ready",
})

# Sort order for states (lower = higher priority in output)
STATE_ORDER = {
    "overdue": 0, "due": 1, "human_review": 2, "missing": 3,
    "stale": 4, "blocked": 5, "not_ready": 6, "promotion_eligible": 7,
    "accruing": 8,
}

FORBIDDEN_KEYS = {"score", "rank", "weight", "size", "allocation"}

FIXED_CAVEATS = [
    "display_only: routes attention; cannot promote, retire, or mutate any source system",
    "deterministic: no LLM in the loop; all text template-filled from source ledgers",
    "date-due is not decision-ready: rows demote to not_ready/blocked when evidence floors are unmet",
]

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(root: Path) -> dict:
    """Load config/evidence_clock.yml."""
    cfg_path = root / "config" / "evidence_clock.yml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_synapse_registry(root: Path) -> dict:
    """Load config/synapse.yml for producer lookups (fail-soft → {})."""
    try:
        with open(root / "config" / "synapse.yml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("could not load synapse.yml: %s", exc)
        return {}


def _synapse_producer(synapse_reg: dict, artifact_path: str) -> str | None:
    """Resolve producer command from synapse registry by artifact path."""
    artifacts = synapse_reg.get("artifacts") or {}
    for _key, entry in artifacts.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("path") == artifact_path:
            prod = entry.get("producer")
            if prod:
                prod_mod = prod[:-3] if prod.endswith(".py") else prod
                return f"python -m {prod_mod.replace('/', '.')}" if "/" in prod_mod else prod_mod
    return None


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        # Handle ISO datetime strings too
        if "T" in val or " " in val:
            val = val.split("T")[0].split(" ")[0]
        return date.fromisoformat(val[:10])
    except (ValueError, TypeError):
        return None


def _date_state(due_at: date | None, grace_days: int, today: date) -> str:
    """Compute the raw date-based state (pre-demotion)."""
    if due_at is None:
        return "accruing"
    if due_at > today:
        return "accruing"
    if today <= due_at + timedelta(days=grace_days):
        return "due"
    return "overdue"


# ---------------------------------------------------------------------------
# Row construction helpers
# ---------------------------------------------------------------------------

def _base_row(
    *,
    clock_id: str,
    source_system: str,
    subject_id: str,
    subject_type: str,
    owner_program: str | None,
    clock_type: str,
    due_at: date | None,
    as_of: str | None,
    state: str,
    date_state: str,
    readiness: dict | None = None,
    evidence_refs: list[str] | None = None,
    regenerate_cmd: str | None = None,
    blocking_reason: str | None = None,
) -> dict:
    """Build a canonical row dict."""
    r: dict[str, Any] = {
        "clock_id": clock_id,
        "source_system": source_system,
        "subject_id": subject_id,
        "subject_type": subject_type,
        "owner_program": owner_program,
        "clock_type": clock_type,
        "due_at": due_at.isoformat() if due_at else None,
        "as_of": as_of,
        "state": state,
        "date_state": date_state,
        "readiness": readiness or {},
        "allowed_actions": ["inspect", "print_gap"],
        "forbidden_actions": ["promote", "mutate_source_state", "score"],
        "evidence_refs": evidence_refs or [],
        "regenerate_cmd": regenerate_cmd,
        "acknowledged": False,
        "review": None,
        "packet": None,
    }
    if blocking_reason:
        r["readiness"]["blocking_reason"] = blocking_reason
    return r


def _sort_key(row: dict) -> tuple:
    state = row.get("state", "accruing")
    order = STATE_ORDER.get(state, 99)
    due_str = row.get("due_at") or "9999-99-99"
    clock_id = row.get("clock_id", "")
    return (order, due_str, clock_id)


# ---------------------------------------------------------------------------
# Adapter 1: experiments
# ---------------------------------------------------------------------------

def _adapt_experiments(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from data/experiments/registry_seed.json."""
    path = root / "data" / "experiments" / "registry_seed.json"
    gaps: list[str] = []
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        gaps.append(f"experiments: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    grace = cfg.get("grace_days", 7)
    exps = data.get("experiments") or []
    missing_cb: list[str] = []

    for entry in exps:
        eid = entry.get("id", "unknown")
        cb_str = entry.get("come_back_on")
        if not cb_str:
            missing_cb.append(eid)
            continue

        cb_date = _parse_date(cb_str)
        ds = _date_state(cb_date, grace, today)
        track_json = entry.get("track_json")
        evidence_refs = [track_json] if track_json else []

        row = _base_row(
            clock_id=f"experiments:{eid}",
            source_system="experiments",
            subject_id=eid,
            subject_type=entry.get("kind", "experiment"),
            owner_program=_guess_program(entry),
            clock_type="come_back_on",
            due_at=cb_date,
            as_of=entry.get("started"),
            state=ds,
            date_state=ds,
            readiness={
                "maturation": entry.get("maturation"),
                "cadence": entry.get("cadence"),
                "status": entry.get("status"),
            },
            evidence_refs=evidence_refs,
        )
        rows.append(row)

    # Rollup for entries missing come_back_on (RF-9 nonconformance)
    if missing_cb:
        rollup = _base_row(
            clock_id="experiments:missing-come-back",
            source_system="experiments",
            subject_id="missing_come_back_on",
            subject_type="experiment",
            owner_program=None,
            clock_type="come_back_on",
            due_at=None,
            as_of=None,
            state="blocked",
            date_state="accruing",
            readiness={"n_missing": len(missing_cb), "ids": missing_cb[:20]},
            blocking_reason=f"{len(missing_cb)} entries lack come_back_on (RF-9)",
        )
        rows.append(rollup)

    return rows, gaps


def _guess_program(entry: dict) -> str | None:
    """Try to derive owner_program from experiment entry fields."""
    src = entry.get("source") or ""
    phase = entry.get("phase_hint") or ""
    # Common patterns
    if "oracle" in src or "oracle" in phase:
        return "oracle-rotation"
    if "neural" in src or "nw" in phase:
        return "neural-web"
    if "research_factory" in src:
        return "research-factory"
    if "cycle" in src:
        return "cycle-intelligence"
    return None


# ---------------------------------------------------------------------------
# Adapter 2: research_factory
# ---------------------------------------------------------------------------

def _adapt_research_factory(root: Path, cfg: dict, today: date, exp_ids: set[str]) -> tuple[list[dict], list[str]]:
    """Rows from data/research_factory/review/queue.json + candidates.jsonl."""
    gaps: list[str] = []
    rows: list[dict] = []

    # Queue check
    queue_path = root / "data" / "research_factory" / "review" / "queue.json"
    try:
        with open(queue_path, encoding="utf-8") as f:
            queue = json.load(f)
        n_candidates = queue.get("n_candidates", 0)
        if n_candidates > 0:
            row = _base_row(
                clock_id="research_factory:review-queue",
                source_system="research_factory",
                subject_id="review_queue",
                subject_type="candidate",
                owner_program="research-factory",
                clock_type="human_review_due",
                due_at=today,  # present = overdue if n>0
                as_of=queue.get("generated_at", "")[:10] or None,
                state="human_review",
                date_state="due",
                readiness={"n_candidates": n_candidates},
                evidence_refs=[str(queue_path.relative_to(root))],
            )
            rows.append(row)
    except FileNotFoundError:
        gaps.append(f"research_factory: queue.json not found at {queue_path.relative_to(root)}")
    except Exception as exc:
        gaps.append(f"research_factory: could not load queue.json: {exc}")

    # Candidates without experiments-seed entry
    cands_path = root / "data" / "research_factory" / "candidates.jsonl"
    try:
        with open(cands_path, encoding="utf-8") as f:
            candidates = [json.loads(l) for l in f if l.strip()]
        blocking_states = {"paper", "deferred", "awaiting_data"}
        for cand in candidates:
            cid = cand.get("id", "unknown")
            status = cand.get("status", "")
            if status not in blocking_states:
                continue
            # Check if any experiments seed entry references this candidate (exact match only)
            if cid in exp_ids:
                continue
            row = _base_row(
                clock_id=f"research_factory:{cid}",
                source_system="research_factory",
                subject_id=cid,
                subject_type="candidate",
                owner_program="research-factory",
                clock_type="awaiting_execution",
                due_at=None,
                as_of=cand.get("created_at", "")[:10] or None,
                state="blocked",
                date_state="accruing",
                readiness={"status": status, "horizon_d": cand.get("evaluation_plan", {}).get("horizon_d")},
                evidence_refs=[str(cands_path.relative_to(root))],
                blocking_reason="RF-9: missing experiments-seed entry",
            )
            rows.append(row)
    except FileNotFoundError:
        gaps.append(f"research_factory: candidates.jsonl not found at {cands_path.relative_to(root)}")
    except Exception as exc:
        gaps.append(f"research_factory: could not load candidates.jsonl: {exc}")

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 3: qledger
# ---------------------------------------------------------------------------

def _adapt_qledger(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rollup rows from data/qledger/claims.jsonl."""
    path = root / "data" / "qledger" / "claims.jsonl"
    gaps: list[str] = []
    rows: list[dict] = []

    try:
        with open(path, encoding="utf-8") as f:
            claims = [json.loads(l) for l in f if l.strip()]
    except Exception as exc:
        gaps.append(f"qledger: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    # Per-desk rollup (open claims only)
    desk_stats: dict[str, dict] = defaultdict(
        lambda: {"n_open": 0, "n_past_check_by": 0, "oldest_past_cb": None}
    )
    n_total = len(claims)
    n_with_falsifier = sum(1 for c in claims if c.get("falsifier"))

    for c in claims:
        if c.get("status") != "open":
            continue
        desk = c.get("desk") or "unknown"
        desk_stats[desk]["n_open"] += 1
        cb = _parse_date(c.get("check_by"))
        if cb and cb < today:
            desk_stats[desk]["n_past_check_by"] += 1
            old = desk_stats[desk]["oldest_past_cb"]
            if old is None or cb < old:
                desk_stats[desk]["oldest_past_cb"] = cb

    for desk, stats in sorted(desk_stats.items()):
        n_open = stats["n_open"]
        n_past = stats["n_past_check_by"]
        if n_open == 0:
            continue
        # Use oldest past-check_by as due_at so _date_state can yield overdue
        due_at = stats["oldest_past_cb"] if n_past > 0 else None
        ds = _date_state(due_at, 0, today)  # grace=0 for check_by
        state = ds if n_past > 0 else "accruing"
        row = _base_row(
            clock_id=f"qledger:{desk}",
            source_system="qledger",
            subject_id=desk,
            subject_type="claim_family",
            owner_program=None,
            clock_type="check_by",
            due_at=due_at,
            as_of=None,
            state=state,
            date_state=ds,
            readiness={"n_open": n_open, "n_past_check_by": n_past},
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    # Global falsifier-floor blocked row
    fc = n_with_falsifier / n_total if n_total else 0.0
    fc_pct = f"{fc*100:.1f}%"
    floor_row = _base_row(
        clock_id="qledger:falsifier_coverage",
        source_system="qledger",
        subject_id="falsifier_coverage",
        subject_type="claim_family",
        owner_program=None,
        clock_type="evidence_floor",
        due_at=None,
        as_of=None,
        state="blocked",
        date_state="accruing",
        readiness={
            "n_claims": n_total,
            "n_with_falsifier": n_with_falsifier,
            "falsifier_coverage": fc_pct,
        },
        evidence_refs=[str(path.relative_to(root))],
        blocking_reason=f"falsifier coverage {fc_pct}; not a promotion-grade substrate",
    )
    rows.append(floor_row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 4: trial_ledger
# ---------------------------------------------------------------------------

def _adapt_trial_ledger(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Family rollup rows from data/trial_ledger.jsonl."""
    path = root / "data" / "trial_ledger.jsonl"
    gaps: list[str] = []
    rows: list[dict] = []

    try:
        with open(path, encoding="utf-8") as f:
            trials = [json.loads(l) for l in f if l.strip()]
    except Exception as exc:
        gaps.append(f"trial_ledger: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    family_cap = cfg.get("sources", {}).get("trial_ledger", {}).get("family_cap", 15)

    # Count per family, find last ts
    family_data: dict[str, dict] = defaultdict(lambda: {"n": 0, "last_ts": None})
    for t in trials:
        fam = t.get("family", "unknown")
        family_data[fam]["n"] += 1
        ts = t.get("ts")
        if ts:
            last = family_data[fam]["last_ts"]
            if last is None or ts > last:
                family_data[fam]["last_ts"] = ts

    sorted_families = sorted(family_data.items(), key=lambda x: -x[1]["n"])
    top = sorted_families[:family_cap]
    rest = sorted_families[family_cap:]

    for fam, stats in top:
        row = _base_row(
            clock_id=f"trial_ledger:{fam}",
            source_system="trial_ledger",
            subject_id=fam,
            subject_type="family",
            owner_program=None,
            clock_type="fdr_batch_due",
            due_at=None,  # batch date from declared_clocks if applicable
            as_of=stats["last_ts"][:10] if stats["last_ts"] else None,
            state="accruing",
            date_state="accruing",
            readiness={"n_trials": stats["n"], "last_ts": stats["last_ts"]},
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    if rest:
        n_rest = sum(s["n"] for _, s in rest)
        last_ts = max((s["last_ts"] for _, s in rest if s["last_ts"]), default=None)
        row = _base_row(
            clock_id="trial_ledger:other",
            source_system="trial_ledger",
            subject_id=f"other_{len(rest)}_families",
            subject_type="family",
            owner_program=None,
            clock_type="fdr_batch_due",
            due_at=None,
            as_of=last_ts[:10] if last_ts else None,
            state="accruing",
            date_state="accruing",
            readiness={"n_trials": n_rest, "n_families": len(rest)},
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 5: freshness
# ---------------------------------------------------------------------------

def _adapt_freshness(root: Path, cfg: dict, today: date, synapse_reg: dict) -> tuple[list[dict], list[str]]:
    """Rows from health.json lobe staleness + mastermind_context.json."""
    gaps: list[str] = []
    rows: list[dict] = []

    # health.json
    health_path = root / "data" / "neuralweb" / "health.json"
    if health_path.exists():
        try:
            with open(health_path, encoding="utf-8") as f:
                health = json.load(f)
            # Find stale/missing/degraded lobes
            lobes = health.get("lobes") or health.get("lobe_health") or {}
            if isinstance(lobes, dict):
                for lobe_id, lobe_data in lobes.items():
                    if not isinstance(lobe_data, dict):
                        continue
                    status = lobe_data.get("status") or lobe_data.get("state", "")
                    if status in ("stale", "missing", "degraded"):
                        # Try to resolve regenerate_cmd
                        lobe_path = lobe_data.get("path")
                        regen = None
                        if lobe_path:
                            regen = _synapse_producer(synapse_reg, lobe_path)
                        row = _base_row(
                            clock_id=f"freshness:{lobe_id}",
                            source_system="freshness",
                            subject_id=lobe_id,
                            subject_type="artifact",
                            owner_program=None,
                            clock_type="freshness_sla",
                            due_at=None,
                            as_of=lobe_data.get("last_updated") or lobe_data.get("as_of"),
                            state="stale" if status != "missing" else "missing",
                            date_state="stale" if status != "missing" else "missing",
                            readiness={"status": status, "lobe_id": lobe_id},
                            evidence_refs=[str(health_path.relative_to(root))],
                            regenerate_cmd=regen,
                        )
                        rows.append(row)
        except Exception as exc:
            gaps.append(f"freshness: could not process health.json: {exc}")
    else:
        gaps.append("freshness: data/neuralweb/health.json not present (first nightly will create it)")

    # mastermind_context.json
    mc_path = root / "data" / "neuralweb" / "mastermind_context.json"
    if mc_path.exists():
        try:
            with open(mc_path, encoding="utf-8") as f:
                mc = json.load(f)
            mc_asof = _parse_date(str(mc.get("as_of", "")))
            mc_stale = False
            stale_chips = []
            if mc_asof:
                # Business-day approximation: >2 calendar days is conservative but safe
                if (today - mc_asof).days > 2:
                    mc_stale = True

            freshness = mc.get("freshness") or {}
            for chip_name, chip_data in freshness.items():
                if isinstance(chip_data, dict) and chip_data.get("stale"):
                    stale_chips.append(chip_name)
                    mc_stale = True

            if mc_stale:
                regen = _synapse_producer(synapse_reg, str(mc_path.relative_to(root)))
                row = _base_row(
                    clock_id="freshness:mastermind_context",
                    source_system="freshness",
                    subject_id="mastermind_context",
                    subject_type="artifact",
                    owner_program="nw-mastermind-bridge",
                    clock_type="freshness_sla",
                    due_at=None,
                    as_of=mc_asof.isoformat() if mc_asof else None,
                    state="stale",
                    date_state="stale",
                    readiness={
                        "as_of": mc.get("as_of"),
                        "stale_chips": stale_chips,
                    },
                    evidence_refs=[str(mc_path.relative_to(root))],
                    regenerate_cmd=regen,
                )
                rows.append(row)
        except Exception as exc:
            gaps.append(f"freshness: could not process mastermind_context.json: {exc}")

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 6: governance
# ---------------------------------------------------------------------------

def _adapt_governance(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from governance.jsonl + probation files — only when lapses_at non-null."""
    gaps: list[str] = []
    rows: list[dict] = []
    grace = cfg.get("grace_days", 7)

    # governance.jsonl
    gov_path = root / "data" / "neuralweb" / "governance.jsonl"
    try:
        with open(gov_path, encoding="utf-8") as f:
            gov_rows = [json.loads(l) for l in f if l.strip()]
        for g in gov_rows:
            lapses_at = _parse_date(g.get("evidence", {}).get("lapses_at"))
            if lapses_at is None:
                continue
            ds = _date_state(lapses_at, grace, today)
            row = _base_row(
                clock_id=f"governance:{g.get('event_id', 'unknown')}",
                source_system="governance",
                subject_id=g.get("target", "unknown"),
                subject_type="authority",
                owner_program=None,
                clock_type="lapse_at",
                due_at=lapses_at,
                as_of=g.get("ts", "")[:10] or None,
                state=ds,
                date_state=ds,
                readiness={"event_type": g.get("event_type"), "article": g.get("article")},
                evidence_refs=[str(gov_path.relative_to(root))],
            )
            rows.append(row)
    except Exception as exc:
        gaps.append(f"governance: could not load {gov_path.relative_to(root)}: {exc}")

    # Probation files
    probation_paths = [
        root / "data" / "neuralweb" / "cortex" / "probation.json",
        root / "data" / "reflexes" / "factor_attention" / "probation.json",
    ]
    for prob_path in probation_paths:
        if not prob_path.exists():
            continue
        try:
            with open(prob_path, encoding="utf-8") as f:
                prob = json.load(f)
            lapses_at = _parse_date(prob.get("lapses_at"))
            if lapses_at is None:
                continue
            slug = prob_path.parts[-2]  # e.g. "cortex" or "factor_attention"
            ds = _date_state(lapses_at, grace, today)
            row = _base_row(
                clock_id=f"governance:probation:{slug}",
                source_system="governance",
                subject_id=slug,
                subject_type="authority",
                owner_program=None,
                clock_type="lapse_at",
                due_at=lapses_at,
                as_of=prob.get("as_of"),
                state=ds,
                date_state=ds,
                readiness={"granted": prob.get("granted"), "tier": prob.get("tier")},
                evidence_refs=[str(prob_path.relative_to(root))],
            )
            rows.append(row)
        except Exception as exc:
            gaps.append(f"governance: could not process {prob_path.relative_to(root)}: {exc}")

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 7: cortex
# ---------------------------------------------------------------------------

def _adapt_cortex(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from data/neuralweb/machine_registry.jsonl."""
    path = root / "data" / "neuralweb" / "machine_registry.jsonl"
    gaps: list[str] = []
    rows: list[dict] = []
    grace = cfg.get("grace_days", 7)

    if not path.exists():
        gaps.append("cortex: data/neuralweb/machine_registry.jsonl not present (empty by design)")
        return rows, gaps

    try:
        with open(path, encoding="utf-8") as f:
            entries = [json.loads(l) for l in f if l.strip()]
    except Exception as exc:
        gaps.append(f"cortex: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    for entry in entries:
        if entry.get("status") != "registered":
            continue
        cb = _parse_date(entry.get("come_back"))
        ds = _date_state(cb, grace, today)
        row = _base_row(
            clock_id=f"cortex:{entry.get('id', 'unknown')}",
            source_system="cortex",
            subject_id=entry.get("id", "unknown"),
            subject_type="hypothesis",
            owner_program="neural-web",
            clock_type="come_back_on",
            due_at=cb,
            as_of=entry.get("registered_at", "")[:10] or None,
            state=ds,
            date_state=ds,
            readiness={"horizon_d": entry.get("horizon_d"), "status": entry.get("status")},
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 8: rule_experiments
# ---------------------------------------------------------------------------

def _adapt_rule_experiments(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from data/rule_experiments/registry.jsonl — per exp_id latest status=registered."""
    path = root / "data" / "rule_experiments" / "registry.jsonl"
    gaps: list[str] = []
    rows: list[dict] = []

    try:
        with open(path, encoding="utf-8") as f:
            all_recs = [json.loads(l) for l in f if l.strip()]
    except Exception as exc:
        gaps.append(f"rule_experiments: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    # Group by exp_id, find latest status
    by_id: dict[str, list[dict]] = defaultdict(list)
    for rec in all_recs:
        by_id[rec.get("exp_id", "unknown")].append(rec)

    for exp_id, recs in by_id.items():
        # Sort by registered_at descending
        recs_sorted = sorted(recs, key=lambda r: r.get("registered_at", ""), reverse=True)
        latest = recs_sorted[0]
        if latest.get("status") != "registered":
            continue
        row = _base_row(
            clock_id=f"rule_experiments:{exp_id}",
            source_system="rule_experiments",
            subject_id=exp_id,
            subject_type="experiment",
            owner_program=None,
            clock_type="awaiting_execution",
            due_at=today,  # registered = due now
            as_of=latest.get("registered_at", "")[:10] or None,
            state="due",
            date_state="due",
            readiness={
                "n_floor": latest.get("n_floor"),
                "declared_budget": latest.get("declared_budget"),
            },
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 9: cycle_pattern
# ---------------------------------------------------------------------------

def _adapt_cycle_pattern(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from data/cycle_pattern/truths.jsonl."""
    path = root / "data" / "cycle_pattern" / "truths.jsonl"
    gaps: list[str] = []
    rows: list[dict] = []
    grace = cfg.get("grace_days", 7)

    # Retirement statuses — rows with these are skipped (they are finished / invalidated)
    RETIRED_STATUSES = {"retired", "promoted_null"}

    try:
        with open(path, encoding="utf-8") as f:
            truths_raw = [json.loads(l) for l in f if l.strip()]
    except Exception as exc:
        gaps.append(f"cycle_pattern: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    # Dedup by truth_id keeping LAST occurrence in file order (latest edit wins)
    deduped: dict[str, dict] = {}
    for truth in truths_raw:
        tid = truth.get("truth_id", "unknown")
        deduped[tid] = truth  # later entry overwrites earlier

    for truth_id, truth in deduped.items():
        # Skip retired / finalized-null rows
        if truth.get("status") in RETIRED_STATUSES:
            continue
        nrd = _parse_date(truth.get("next_review_due"))
        if nrd is None:
            continue
        ds = _date_state(nrd, grace, today)
        row = _base_row(
            clock_id=f"cycle_pattern:{truth_id}",
            source_system="cycle_pattern",
            subject_id=truth_id,
            subject_type="truth",
            owner_program=truth.get("owner_program"),
            clock_type="next_review_due",
            due_at=nrd,
            as_of=truth.get("last_reviewed"),
            state=ds,
            date_state=ds,
            readiness={
                "status": truth.get("status"),
                "cadence": truth.get("monitoring", {}).get("cadence"),
                "effect_class": truth.get("effect_class"),
            },
            evidence_refs=[str(path.relative_to(root))]
            + (truth.get("evidence_refs") or [])[:3],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 10: species
# ---------------------------------------------------------------------------

def _adapt_species(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from data/species/registry.json — only when gating.come_back_on non-null."""
    path = root / "data" / "species" / "registry.json"
    gaps: list[str] = []
    rows: list[dict] = []
    grace = cfg.get("grace_days", 7)

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        gaps.append(f"species: could not load {path.relative_to(root)}: {exc}")
        return rows, gaps

    species_list = data.get("species") or []
    for sp in species_list:
        gating = sp.get("gating") or {}
        cb = _parse_date(gating.get("come_back_on"))
        if cb is None:
            continue
        ds = _date_state(cb, grace, today)
        row = _base_row(
            clock_id=f"species:{sp.get('species_id', 'unknown')}",
            source_system="species",
            subject_id=sp.get("species_id", "unknown"),
            subject_type="hypothesis",
            owner_program=None,
            clock_type="come_back_on",
            due_at=cb,
            as_of=data.get("authored"),
            state=ds,
            date_state=ds,
            readiness={
                "validation_status": sp.get("validation_status"),
                "deployment_status": sp.get("deployment_status"),
                "cadence": gating.get("cadence"),
            },
            evidence_refs=[str(path.relative_to(root))],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 11: declared clocks
# ---------------------------------------------------------------------------

def _adapt_declared(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows from config/evidence_clock.yml declared_clocks."""
    gaps: list[str] = []
    rows: list[dict] = []
    grace = cfg.get("grace_days", 7)

    for decl in cfg.get("declared_clocks") or []:
        cb = _parse_date(decl.get("due_at"))
        ds = _date_state(cb, grace, today)
        row = _base_row(
            clock_id=decl.get("clock_id", "declared:unknown"),
            source_system="declared",
            subject_id=decl.get("subject_id", "unknown"),
            subject_type=decl.get("subject_type", "hypothesis"),
            owner_program=decl.get("owner_program"),
            clock_type=decl.get("clock_type", "come_back_on"),
            due_at=cb,
            as_of=None,
            state=ds,
            date_state=ds,
            readiness={"note": decl.get("note")},
            evidence_refs=["config/evidence_clock.yml"],
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Adapter 12: expected artifacts
# ---------------------------------------------------------------------------

def _adapt_expected_artifacts(root: Path, cfg: dict, today: date) -> tuple[list[dict], list[str]]:
    """Rows for expected artifacts that are missing on disk."""
    gaps: list[str] = []
    rows: list[dict] = []

    for ea in cfg.get("expected_artifacts") or []:
        path_str = ea.get("path", "")
        full_path = root / path_str
        if full_path.exists():
            continue  # Present — no row needed
        row = _base_row(
            clock_id=f"expected_artifact:{path_str}",
            source_system="declared",
            subject_id=path_str,
            subject_type="artifact",
            owner_program=None,
            clock_type="expected_artifact",
            due_at=None,
            as_of=None,
            state="missing",
            date_state="missing",
            readiness={"note": ea.get("note")},
            evidence_refs=[path_str],
            regenerate_cmd=ea.get("producer"),
            blocking_reason=f"artifact missing on disk; run: {ea.get('producer')}",
        )
        rows.append(row)

    return rows, gaps


# ---------------------------------------------------------------------------
# Precedence demotion (EC-R3)
# ---------------------------------------------------------------------------

def _apply_precedence(rows: list[dict], root: Path, today: date) -> None:
    """
    Apply EC-R3 precedence demotions in-place.

    (a) experiments row whose subject_id matches an RF candidate in
        awaiting_data/blocked → demote to blocked.
    (b) Rows whose evidence_refs artifact is stale per health.json →
        add stale_input note to readiness (do NOT change state).
    """
    # Build RF blocking set from candidates.jsonl directly (EC-R3 precedence)
    rf_blocked_subjects: set[str] = set()
    cands_path = root / "data" / "research_factory" / "candidates.jsonl"
    if cands_path.exists():
        try:
            with open(cands_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = json.loads(line)
                    if c.get("status") in ("awaiting_data", "blocked"):
                        cid = c.get("id")
                        if cid:
                            rf_blocked_subjects.add(cid)
        except Exception:
            pass
    # Also capture from already-produced RF rows (RF-9 nonconformance rows)
    for row in rows:
        if row["source_system"] == "research_factory":
            br = row.get("readiness", {}).get("blocking_reason", "")
            status = row.get("readiness", {}).get("status", "")
            if "awaiting_data" in status or "blocked" in status or "RF-9" in br:
                rf_blocked_subjects.add(row["subject_id"])

    # Build stale artifact set from health.json
    stale_artifacts: set[str] = set()
    health_path = root / "data" / "neuralweb" / "health.json"
    if health_path.exists():
        try:
            with open(health_path, encoding="utf-8") as f:
                health = json.load(f)
            lobes = health.get("lobes") or health.get("lobe_health") or {}
            for lobe_id, lobe_data in (lobes.items() if isinstance(lobes, dict) else []):
                if isinstance(lobe_data, dict):
                    if lobe_data.get("status") in ("stale", "missing"):
                        lp = lobe_data.get("path")
                        if lp:
                            stale_artifacts.add(lp)
        except Exception:
            pass

    for row in rows:
        # (a) EC-R3: experiments demoted by RF state
        if row["source_system"] == "experiments" and row["subject_id"] in rf_blocked_subjects:
            if row["state"] in ("due", "overdue"):
                row["state"] = "blocked"
                row["readiness"]["blocking_reason"] = (
                    row["readiness"].get("blocking_reason", "")
                    or "RF candidate in awaiting_data/blocked for this subject"
                )

        # (b) Stale input note (no state change)
        for ref in row.get("evidence_refs") or []:
            if ref in stale_artifacts:
                row["readiness"]["stale_input"] = ref


# ---------------------------------------------------------------------------
# Floor demotion (EC-R6)
# ---------------------------------------------------------------------------

def _apply_floor_demotion(rows: list[dict], root: Path) -> None:
    """EC-R6: due/overdue but evidence_refs missing on disk → not_ready."""
    for row in rows:
        if row["state"] not in ("due", "overdue"):
            continue
        refs = row.get("evidence_refs") or []
        if not refs:
            # No declared refs — unknown floor, stay due
            row["readiness"]["floor"] = "undeclared"
            continue
        missing_refs = [r for r in refs if not (root / r).exists()]
        if missing_refs:
            row["state"] = "not_ready"
            row["readiness"]["blocking_reason"] = (
                f"evidence_refs missing on disk: {missing_refs[:3]}"
            )
            row["readiness"]["missing_refs"] = missing_refs


# ---------------------------------------------------------------------------
# Review ack (EC-R8)
# ---------------------------------------------------------------------------

def _apply_acks(rows: list[dict], root: Path, snooze_days: int, today: date) -> None:
    """EC-R8: read evidence_clock_reviews.jsonl; set acknowledged=True within snooze window."""
    reviews_path = root / "data" / "neuralweb" / "evidence_clock_reviews.jsonl"
    if not reviews_path.exists():
        return

    try:
        with open(reviews_path, encoding="utf-8") as f:
            reviews = [json.loads(l) for l in f if l.strip()]
    except Exception:
        return

    # Latest review per clock_id
    latest_review: dict[str, dict] = {}
    for rev in reviews:
        cid = rev.get("clock_id")
        if not cid:
            continue
        prev = latest_review.get(cid)
        if prev is None or rev.get("reviewed_on", "") > prev.get("reviewed_on", ""):
            latest_review[cid] = rev

    for row in rows:
        cid = row["clock_id"]
        rev = latest_review.get(cid)
        if not rev:
            continue
        reviewed_on = _parse_date(rev.get("reviewed_on"))
        if reviewed_on and (today - reviewed_on).days <= snooze_days:
            row["acknowledged"] = True
            row["review"] = {
                "reviewed_on": rev.get("reviewed_on"),
                "note": rev.get("note"),
                "outcome": rev.get("outcome"),
            }


# ---------------------------------------------------------------------------
# Packet stubs (EC-R4)
# ---------------------------------------------------------------------------

def _attach_packet_stubs(rows: list[dict], cap: int, root: Path) -> None:
    """Add inline packet stubs to the top `cap` due/overdue rows."""
    due_rows = [r for r in rows if r["state"] in ("due", "overdue")]
    for row in due_rows[:cap]:
        missing = [r for r in (row.get("evidence_refs") or []) if not (root / r).exists()]
        row["packet"] = {
            "reason_due": (
                f"{row['clock_type']} reached {row.get('due_at') or 'now'}"
            ),
            "source_evidence": row.get("evidence_refs") or [],
            "missing_evidence": missing,
            "allowed_decisions": ["inspect", "defer", "reject", "paper"],
            "blocked_decisions": ["promote", "authority_change"],
        }


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(rows: list[dict], today: date) -> dict:
    """Build the summary block including morning_line."""
    by_state: dict[str, int] = {s: 0 for s in STATE_ORDER}
    n_acknowledged = 0

    for row in rows:
        state = row.get("state", "accruing")
        by_state[state] = by_state.get(state, 0) + 1
        if row.get("acknowledged"):
            n_acknowledged += 1

    # top_due: first due/overdue row NOT acknowledged
    top_due_info: dict | None = None
    for row in rows:
        if row.get("state") in ("due", "overdue") and not row.get("acknowledged"):
            top_due_info = {
                "clock_id": row["clock_id"],
                "due_at": row.get("due_at"),
                "owner_program": row.get("owner_program"),
            }
            break

    # morning_line: only subtract acks on due/overdue rows (not stale/blocked acks)
    n_ack_due = sum(
        1 for r in rows
        if r.get("acknowledged") and r.get("state") in ("due", "overdue")
    )
    n_due = by_state.get("due", 0) + by_state.get("overdue", 0) - n_ack_due
    n_due = max(0, n_due)
    n_accruing = by_state.get("accruing", 0)
    n_stale = by_state.get("stale", 0)
    n_blocked = by_state.get("blocked", 0)
    n_missing = by_state.get("missing", 0)
    n_human = by_state.get("human_review", 0)

    parts = []
    if n_due:
        parts.append(f"{n_due} due/overdue")
    if n_human:
        parts.append(f"{n_human} human_review")
    if n_missing:
        parts.append(f"{n_missing} missing")
    if n_accruing:
        parts.append(f"{n_accruing} accruing")
    if n_stale:
        parts.append(f"{n_stale} stale")
    if n_blocked:
        parts.append(f"{n_blocked} blocked")

    summary_str = ", ".join(parts) if parts else "0 items"
    if top_due_info:
        summary_str += f". Top due: {top_due_info['clock_id']}."
    else:
        summary_str += "."

    return {
        "n_rows": len(rows),
        "by_state": by_state,
        "n_acknowledged": n_acknowledged,
        "top_due": top_due_info,
        "morning_line": summary_str,
    }


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build(root: Path, today: date | None = None) -> dict:
    """
    Build the evidence clock artifact.

    Returns the full packet dict.  Never raises — all errors captured in `gaps`.
    """
    if today is None:
        today = _today()

    cfg = load_config(root)
    synapse_reg = load_synapse_registry(root)
    grace_days = cfg.get("grace_days", 7)
    snooze_days = cfg.get("snooze_days", 7)
    packet_cap = cfg.get("packet_stub_cap", 10)

    all_rows: list[dict] = []
    all_gaps: list[str] = []

    sources_cfg = cfg.get("sources") or {}

    def _run(name: str, fn, *args):
        """Run an adapter, catching all exceptions into gaps."""
        if not sources_cfg.get(name, {}).get("enabled", True):
            return
        try:
            rows, gaps = fn(*args)
            all_rows.extend(rows)
            all_gaps.extend(gaps)
        except Exception as exc:
            all_gaps.append(f"{name}: unhandled adapter error: {exc}")

    # Collect exp_ids for RF cross-check
    exp_ids: set[str] = set()
    try:
        with open(root / "data" / "experiments" / "registry_seed.json", encoding="utf-8") as f:
            ed = json.load(f)
        exp_ids = {e.get("id", "") for e in (ed.get("experiments") or [])}
    except Exception:
        pass

    _run("experiments", _adapt_experiments, root, cfg, today)
    _run("research_factory", _adapt_research_factory, root, cfg, today, exp_ids)
    _run("qledger", _adapt_qledger, root, cfg, today)
    _run("trial_ledger", _adapt_trial_ledger, root, cfg, today)
    _run("freshness", _adapt_freshness, root, cfg, today, synapse_reg)
    _run("governance", _adapt_governance, root, cfg, today)
    _run("cortex", _adapt_cortex, root, cfg, today)
    _run("rule_experiments", _adapt_rule_experiments, root, cfg, today)
    _run("cycle_pattern", _adapt_cycle_pattern, root, cfg, today)
    _run("species", _adapt_species, root, cfg, today)

    # Declared & expected artifacts always run
    try:
        decl_rows, decl_gaps = _adapt_declared(root, cfg, today)
        all_rows.extend(decl_rows)
        all_gaps.extend(decl_gaps)
    except Exception as exc:
        all_gaps.append(f"declared: {exc}")

    try:
        ea_rows, ea_gaps = _adapt_expected_artifacts(root, cfg, today)
        all_rows.extend(ea_rows)
        all_gaps.extend(ea_gaps)
    except Exception as exc:
        all_gaps.append(f"expected_artifacts: {exc}")

    # Apply precedence, floor demotion, acks
    try:
        _apply_precedence(all_rows, root, today)
    except Exception as exc:
        all_gaps.append(f"precedence: {exc}")

    try:
        _apply_floor_demotion(all_rows, root)
    except Exception as exc:
        all_gaps.append(f"floor_demotion: {exc}")

    try:
        _apply_acks(all_rows, root, snooze_days, today)
    except Exception as exc:
        all_gaps.append(f"acks: {exc}")

    # Sort rows
    all_rows.sort(key=_sort_key)

    # Packet stubs
    try:
        _attach_packet_stubs(all_rows, packet_cap, root)
    except Exception as exc:
        all_gaps.append(f"packet_stubs: {exc}")

    summary = _build_summary(all_rows, today)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "schema": SCHEMA,
        "as_of": today.isoformat(),
        "generated_utc": now_utc,
        "authority": AUTHORITY,
        "summary": summary,
        "rows": all_rows,
        "gaps": all_gaps,
        "caveats": FIXED_CAVEATS,
    }
