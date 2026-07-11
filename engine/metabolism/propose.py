"""engine.metabolism.propose — PROPOSE lobe-brain core (A4, PROPOSE stage).

Stage 2 of the Metabolism (masterplan §1).  A stateless Opus lobe-brain reads
the TIL fitness card + masterplan + case law (ruling graph, DO_NOT_REBUILD,
ACTIVE_BUILD_MAP) and emits a structured DOCKET of build proposals, each
carrying a pre-committed FITNESS CONTRACT registered to the trial ledger.

This module is PURE LOGIC — no kill-switch, no journal, no git, no PR.  The
CLI wrapper (scripts/metabolism_propose.py) owns the kill-switch, preflight,
budget, and journal; the workflow (.github/workflows/metabolism-propose.yml)
owns the branch/commit/DRAFT-PR.  This mirrors the verify.py / metabolism_verify.py
split already shipped in the Phase A spine.

LAWS ENFORCED HERE
------------------
* R-AUT-1  — the LLM authors *proposals for code*, never a runtime signal/score.
             Everything written here is display-tier (AUTHORITY_BLOCK below).
* R-AUT-3  — stateless-cattle: the docket is the only state, written to git.
* R-AUT-8  — every proposal registers a pre-committed fitness contract in
             data/trial_ledger.jsonl (family 'metabolism_til', a distinct FDR
             family so loop volume never raises the human discovery bar) AND
             carries the contract in the docket for A6 VERIFY to grade.
* Dedup    — content-hash of each proposal is checked against DO_NOT_REBUILD
             kills, ACTIVE_BUILD_MAP open lanes, and prior dockets.  A killed
             or in-flight topic is dropped (not re-proposed).
* Budget   — the caller caps the docket at max_docket_size (config, IMMUTABLE).

NEVER-RAISE CONTRACT (mirrors governance.py / til_fitness.py):
    Every public function catches all exceptions, logs a warning, and returns a
    safe fallback.  A PROPOSE failure must never abort the stage; the worst case
    is an empty docket.

DOCKET SCHEMA (metabolism.docket.v1)
------------------------------------
  {
    "schema": "metabolism.docket.v1",
    "cycle_id": str,
    "lobe": "til",
    "as_of": ISO date,
    "run_id": str | null,
    "generated_by": "metabolism_propose",
    "provider": str | null,           # oauth | anthropic | deepseek | null
    "degraded_reason": str | null,
    "proposals": [ proposal, ... ],   # capped at max_docket_size, deduped
    "rejected": [ {title, reason}, ... ],   # honest nulls: dupes/kills dropped
    "authority": { is_context_only: true, ... },
    "notes": str,
  }

proposal:
  {
    "proposal_id": str,               # sha256[:12] of normalized(title|sensor|kind)
    "content_hash": str,              # == proposal_id
    "title": str,
    "tier": "T0" | "T1" | "T2",
    "kind": str,                      # test|doc|context_organ|engine|collector|ui
    "targets_sensor": str,
    "rationale": str,
    "fitness_contract": {             # the shape engine.metabolism.verify reads
      "proposal_id": str,
      "sensor": str,
      "expected_sign": "+" | "-",
      "band": str,
      "check_by": ISO date,
      "placebo_to_beat": str,
      "falsifier_spec": dict,         # qledger-compatible check dict (may be {})
      "asof": ISO date,
    },
  }
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.docket.v1"
LOBE = "til"
TRIAL_FAMILY = "metabolism_til"
DOCKET_SUBDIR = ("data", "metabolism", "dockets")

_VALID_TIERS = frozenset({"T0", "T1", "T2"})

# Default check_by horizon for a fitness contract when the proposer omits one.
# TIL sensors are ACCRUING until 2026-10-15 (the first real check_by in the
# pre-registered TIL trial contracts), so a proposal minted before then is given
# a floor at that date.
_FIRST_REAL_CHECK_BY = "2026-10-15"
_DEFAULT_HORIZON_DAYS = 60

# Display-tier authority — identical intent to til_fitness / verify.
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
        "mastermind_arming", "scored_path", "auto_merge",
    ],
}

# Provider waterfall config for engine.llm_auth (same as whitehouse_brain).
_LLM_CFG: dict[str, Any] = {
    "provider_order": ["oauth", "anthropic", "deepseek"],
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",
    "deepseek_key_env": "DEEPSEEK_API_KEY",
    "deepseek_base_url": "https://api.deepseek.com/anthropic",
    "opus_model": "claude-opus-4-8",
    "deepseek_model": "deepseek-v4-pro",
    "max_tokens": 4000,
}


# ── Path helpers ──────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def docket_path(cycle_id: str, root: Path | None = None) -> Path:
    base = _repo_root(root)
    return base.joinpath(*DOCKET_SUBDIR) / f"{cycle_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today(today: str | None = None) -> str:
    """Return an ISO date.  A malformed override falls back to real today so a
    bad --today can never make _mint_contract's strptime drop every proposal."""
    if today and re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        return today
    if today:
        log.warning("propose: ignoring malformed today=%r — using real date", today)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_text(path: Path, max_chars: int | None = None) -> str:
    """Tolerant text read — returns '' on any error (missing file etc.)."""
    try:
        if not path.exists():
            return ""
        txt = path.read_text(encoding="utf-8")
        if max_chars is not None and len(txt) > max_chars:
            return txt[:max_chars]
        return txt
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: could not read %s: %s", path, exc)
        return ""


# ── Normalization + content hashing (dedup) ───────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, collapse to alnum tokens joined by single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def content_hash(title: str, sensor: str = "", kind: str = "") -> str:
    """Deterministic sha256[:12] of the normalized (title|sensor|kind)."""
    raw = f"{_normalize(title)}|{_normalize(sensor)}|{_normalize(kind)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ── Prompt context assembly ───────────────────────────────────────────────────

def _masterplan_phase_a(root: Path) -> str:
    """Return the Phase A section of the masterplan (bounded)."""
    txt = _read_text(root / "research" / "AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md")
    if not txt:
        return ""
    # Extract from "Phase A" heading to the next "### Phase B" heading.
    start = txt.find("### Phase A")
    if start == -1:
        return txt[:4000]
    end = txt.find("### Phase B", start)
    section = txt[start:end] if end != -1 else txt[start:start + 4000]
    return section[:4000]


def _fitness_card(root: Path) -> dict[str, Any]:
    """Read the TIL fitness card (A3 SENSE output); tolerant of absence."""
    p = root / "data" / "metabolism" / "fitness" / "til.json"
    txt = _read_text(p)
    if not txt:
        return {"_absent": True, "note": "til fitness card not yet built (SENSE must run first)"}
    try:
        return json.loads(txt)
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: fitness card parse failed: %s", exc)
        return {"_absent": True, "note": f"til fitness card unparseable: {exc}"}


def _load_lobe_from_charter(root: Path, lobe: str) -> dict[str, Any]:
    """Load the lobe charter entry for the given lobe.  Returns {} on any error."""
    try:
        import yaml  # noqa: PLC0415
        charter_path = root / "config" / "lobe_charters.yml"
        if not charter_path.exists():
            return {}
        raw = yaml.safe_load(charter_path.read_text(encoding="utf-8")) or {}
        charters = raw.get("charters") or raw.get("lobes") or {}
        return charters.get(lobe) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: charter load failed for %s: %s", lobe, exc)
        return {}


def build_prompt_context(root: Path | None = None, lobe: str = LOBE) -> dict[str, Any]:
    """Assemble the read-only context the proposer prompt is grounded in.

    Includes five W5 steering-memory blocks (R-V4-3):
      (a) relevance-ranked recall via recall.recall_lessons (lobe-scoped, FAIL-floor)
      (b) preference_prior via dream.load_preference_prior() — advisory calibration
      (c) open insight-bus rows via insight_bus.get_open_rows() (byte-capped, severity-ordered)
      (d) lobe trajectory + strategic gap via strategic.build_trajectory_block/gap
      (e) mission block via mission.build_mission_block() + strategic memory tail

    Never raises; missing artifacts become honest 'absent' notes.
    """
    r = _repo_root(root)
    ctx: dict[str, Any] = {
        "fitness_card": _fitness_card(r),
        "masterplan_phase_a": _masterplan_phase_a(r),
        # Case law — the curated 11KB kill registry ships whole; the 58KB build
        # map and the 800KB ruling graph are bounded to keep the prompt cheap.
        "do_not_rebuild": _read_text(r / "research" / "DO_NOT_REBUILD.md", max_chars=12000),
        "active_build_map": _read_text(r / "docs" / "ACTIVE_BUILD_MAP.md", max_chars=12000),
        "ruling_graph_note": (
            "config/ruling_graph.yml is the 500-ruling case-law registry (query it "
            "before proposing; do NOT re-propose a killed or in-flight topic)."
        ),
    }

    # (a) Relevance-ranked recall (R-V4-3a) — lobe-scoped, FAIL-floor preserved
    try:
        from engine.metabolism import recall as _recall  # noqa: PLC0415
        charter = _load_lobe_from_charter(r, lobe)
        sensors = charter.get("fitness_sensors") or []
        recall_text = _recall.recall_lessons(
            lobe=lobe,
            sensors=sensors if isinstance(sensors, list) else [],
            byte_budget=2000,
            root=r,
        )
        ctx["recall_lessons"] = recall_text
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: recall_lessons failed: %s", exc)
        ctx["recall_lessons"] = "(recall unavailable)"

    # (b) Preference prior (R-V4-3b) — advisory calibration from dream cycle
    try:
        from engine.metabolism import dream as _dream  # noqa: PLC0415
        prior = _dream.load_preference_prior(root=r)
        if prior:
            prior_text = json.dumps(prior, indent=2, default=str)[:2000]
        else:
            prior_text = "(preference_prior absent — accruing until first dream cycle closes)"
        ctx["preference_prior"] = prior_text
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: preference_prior load failed: %s", exc)
        ctx["preference_prior"] = "(preference prior unavailable)"

    # (c) Open insight-bus rows (R-V4-3c) — severity-ordered, byte-capped
    try:
        from engine.metabolism import insight_bus as _ibus  # noqa: PLC0415
        open_rows = _ibus.get_open_rows(root=r)
        _SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        open_rows_sorted = sorted(
            open_rows,
            key=lambda row: (_SEV_ORDER.get(row.get("severity", "low"), 3),),
        )
        # Byte-cap: keep top rows within 2000 bytes
        ibus_lines: list[str] = []
        used = 0
        for row in open_rows_sorted[:20]:
            compact = {k: v for k, v in row.items() if k not in ("authority",)}
            line = json.dumps(compact, separators=(",", ":"), default=str)
            lb = len(line.encode())
            if used + lb + 1 > 2000 and ibus_lines:
                break
            ibus_lines.append(line)
            used += lb + 1
        ctx["insight_bus_open"] = "\n".join(ibus_lines) if ibus_lines else "(no open insight-bus rows)"
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: insight_bus.get_open_rows failed: %s", exc)
        ctx["insight_bus_open"] = "(insight bus unavailable)"

    # (d) Trajectory + strategic gap (R-V4-3d)
    try:
        from engine.metabolism import strategic as _strategic  # noqa: PLC0415
        traj_text = _strategic.build_trajectory_block(lobe, root=r, byte_cap=1200)
        gap_text = _strategic.build_strategic_gap(root=r, byte_cap=1200)
        ctx["trajectory_block"] = traj_text
        ctx["strategic_gap"] = gap_text
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: trajectory/strategic-gap failed: %s", exc)
        ctx["trajectory_block"] = "(trajectory unavailable)"
        ctx["strategic_gap"] = "(strategic gap unavailable)"

    # (e) Mission block + strategic memory tail (R-V4-3e)
    try:
        from engine.metabolism import mission as _mission  # noqa: PLC0415
        mission_text = _mission.build_mission_block(root=r, byte_cap=1000)
        strategic_mem = _mission.build_strategic_memory_block(lobe, byte_cap=1500, root=r)
        ctx["mission_block"] = mission_text
        ctx["strategic_memory"] = strategic_mem
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: mission/strategic-memory failed: %s", exc)
        ctx["mission_block"] = "(mission block unavailable)"
        ctx["strategic_memory"] = "(strategic memory unavailable)"

    return ctx


# ── Dedup corpus ──────────────────────────────────────────────────────────────

def _open_lanes_only(abm_text: str) -> str:
    """Extract the '## Open PRs' section (+ file collisions) from ACTIVE_BUILD_MAP.

    The in-flight collision screen must match OPEN lanes only.  Matching the
    whole file — which embeds the last 14 days of merged-PR titles (~500) —
    makes a majority-token quorum trivially satisfiable by common engineering
    words, rejecting essentially every proposal (observed on the first shadow
    cycles, 2026-07-11).  Merged work is not an in-flight collision; killed
    topics are DO_NOT_REBUILD's job.

    Fail-CLOSED: if the expected heading is absent, return the full text
    (over-rejection is the safe direction for a fence).
    """
    if not abm_text:
        return abm_text
    start = abm_text.find("## Open PRs")
    if start < 0:
        return abm_text
    stop = abm_text.find("## Recently Merged", start)
    return abm_text[start:stop] if stop > start else abm_text[start:]


def _load_dedup_corpus(root: Path) -> dict[str, Any]:
    """Collect normalized terms/hashes to dedup proposals against.

    Returns
    -------
    dict with keys:
        killed_text  (str)         — normalized DO_NOT_REBUILD text
        active_text  (str)         — normalized ACTIVE_BUILD_MAP text
        prior_hashes (set[str])    — content hashes from prior dockets
    """
    r = _repo_root(root)
    killed = _normalize(_read_text(r / "research" / "DO_NOT_REBUILD.md"))
    active = _normalize(_open_lanes_only(_read_text(r / "docs" / "ACTIVE_BUILD_MAP.md")))

    prior_hashes: set[str] = set()
    try:
        ddir = r.joinpath(*DOCKET_SUBDIR)
        if ddir.exists():
            for p in ddir.glob("*.json"):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                for prop in (d.get("proposals") or []):
                    h = prop.get("content_hash") or prop.get("proposal_id")
                    if h:
                        prior_hashes.add(str(h))
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: prior-docket scan failed: %s", exc)

    return {"killed_text": killed, "active_text": active, "prior_hashes": prior_hashes}


def _dedup_reason(title: str, sensor: str, kind: str, corpus: dict[str, Any]) -> str | None:
    """Return a rejection reason if this proposal is a dup/kill, else None.

    A title's distinctive tokens (len >= 4) must overlap the case-law text by a
    quorum to count as a match — a single common word is not a collision.
    """
    h = content_hash(title, sensor, kind)
    if h in corpus.get("prior_hashes", set()):
        return "duplicate of a prior docket proposal (content-hash match)"

    tokens = [t for t in _normalize(title).split() if len(t) >= 4]
    if not tokens:
        return None

    def _hits(hay: str) -> int:
        if not hay:
            return 0
        return sum(1 for t in tokens if f" {t} " in f" {hay} ")

    quorum = max(2, (len(tokens) + 1) // 2)  # majority of distinctive tokens
    if _hits(corpus.get("killed_text", "")) >= quorum:
        return "matches a DO_NOT_REBUILD kill (topic already closed)"
    if _hits(corpus.get("active_text", "")) >= quorum:
        return "matches an ACTIVE_BUILD_MAP open lane (in-flight — avoid collision)"
    return None


# ── LLM invocation ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = (
    "You are the {lobe_label} lobe-brain of the Neural Web's autonomic metabolism. "
    "Your job is to PROPOSE small, high-leverage engineering changes that would improve "
    "the {lobe_label} fitness sensors — {sensor_list}.\n\n"
    "HARD LAWS (violating any = the proposal is discarded):\n"
    "1. You author PROPOSALS FOR CODE, never a runtime trading signal, score, or "
    "escalation. Nothing you emit ranks, sizes, gates, or escalates anything.\n"
    "2. Never re-propose a topic listed in DO_NOT_REBUILD or already in flight in "
    "ACTIVE_BUILD_MAP.\n"
    "3. Every proposal MUST carry a falsifiable fitness_contract: which sensor it "
    "improves, the expected sign, a magnitude band, a check_by date, and the "
    "placebo/holdout it must beat. A proposal with no measurable contract is invalid.\n"
    "4. ACCRUAL HONESTY: if a sensor is still accruing (maturity_date in the future), "
    "any proposal targeting it MUST carry check_by >= that maturity_date. A proposal "
    "with an earlier check_by on an accruing sensor is structurally invalid and will "
    "be rejected.\n"
    "5. Prefer T0 (docs/tests/display-tier context organs/bug-fixes/coverage) work. "
    "T1 (new engines/collectors/UI/algorithm changes) is allowed but must be small "
    "and testable. Never propose T2 (scored-path promotion, guard/CI/secret/spend "
    "changes) — those are operator-only.\n\n"
    "Reply with ONLY a JSON array (no prose, no code fence) of at most {{max_n}} "
    "proposals. Each element:\n"
    '{{"title": str, "tier": "T0"|"T1", "kind": "test"|"doc"|"context_organ"|'
    '"engine"|"collector"|"ui", "targets_sensor": str, "rationale": str, '
    '"fitness_contract": {{"sensor": str, "expected_sign": "+"|"-", "band": str, '
    '"check_by": "YYYY-MM-DD", "placebo_to_beat": str}}}}'
)

# Fallback for lobes without charter sensors (kept for import compat)
_SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.format(
    lobe_label="TIL (Thematic Intelligence Lobe)",
    sensor_list="front_run_lead, placebo_hit_rate, falsifier_honesty, live_leg_quality",
)


def _build_system_prompt(lobe: str, root: Path | None = None) -> str:
    """Build the PROPOSE system prompt from the charter (R-V4-10).

    A lobe is loop-manageable when its lobe_charters.yml entry declares
    fitness_sensors.  The system prompt is assembled from those sensors.

    Returns a formatted system prompt string.  NEVER raises.
    """
    try:
        charter = _load_lobe_from_charter(_repo_root(root), lobe)
        sensors_raw = charter.get("fitness_sensors") or []

        if not sensors_raw:
            # SENSE-only lobe: no declared sensors → PROPOSE must not fabricate fitness.
            # Return a minimal inert prompt that blocks proposals.
            return (
                f"You are the {lobe} lobe-brain. This lobe has no declared fitness_sensors "
                f"in lobe_charters.yml and is SENSE-only. You must NOT propose anything — "
                f"emit an empty JSON array: []. NEVER fabricate fitness sensors."
            )

        # Build sensor list string for the prompt
        sensor_ids: list[str] = []
        for s in sensors_raw:
            if isinstance(s, dict):
                sid = str(s.get("id") or "").strip()
            else:
                sid = str(s).strip()
            if sid:
                sensor_ids.append(sid)

        sensor_list = ", ".join(sensor_ids) if sensor_ids else lobe
        lobe_label = f"{lobe.upper()} ({charter.get('information_domain', lobe)})"

        return _SYSTEM_PROMPT_TEMPLATE.format(
            lobe_label=lobe_label,
            sensor_list=sensor_list,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("propose._build_system_prompt: %s", exc)
        # Fall back to the hardcoded TIL prompt so a charter error never silences proposals
        return _SYSTEM_PROMPT


def _load_accruing_sensor_maturity(root: Path, lobe: str) -> dict[str, str]:
    """Return {sensor_id: maturity_date} for sensors with accruing=true in the charter.

    Used by the accrual-honesty check_by validation gate.
    Returns {} on any error.  NEVER raises.
    """
    try:
        charter = _load_lobe_from_charter(root, lobe)
        sensors_raw = charter.get("fitness_sensors") or []
        result: dict[str, str] = {}
        for s in sensors_raw:
            if not isinstance(s, dict):
                continue
            if s.get("accruing"):
                sid = str(s.get("id") or "").strip()
                mat_date = str(s.get("maturity_date") or "").strip()
                if sid and mat_date and re.match(r"^\d{4}-\d{2}-\d{2}$", mat_date):
                    result[sid] = mat_date
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("propose._load_accruing_sensor_maturity: %s", exc)
        return {}


def _build_user_prompt(context: dict[str, Any], max_n: int) -> str:
    card = json.dumps(context.get("fitness_card", {}), indent=2, default=str)[:3000]
    parts = [
        "TIL FITNESS CARD (the sensors you must improve):",
        card,
        "",
        "MASTERPLAN — PHASE A (your remit and the tier ladder):",
        context.get("masterplan_phase_a", "")[:3500],
        "",
        "DO_NOT_REBUILD — killed / forbidden topics (never re-propose these):",
        context.get("do_not_rebuild", "")[:6000],
        "",
        "ACTIVE_BUILD_MAP — open PR lanes (avoid colliding with these):",
        context.get("active_build_map", "")[:6000],
        "",
        context.get("ruling_graph_note", ""),
        "",
        # ── W5 steering-memory blocks (R-V4-3) ─────────────────────────────
        "RECENT LESSONS (relevance-ranked, FAIL-floor preserved — stop repeating dead constructions):",
        context.get("recall_lessons", "(absent)"),
        "",
        "PREFERENCE PRIOR (advisory calibration from closed contracts — never gate-altering):",
        context.get("preference_prior", "(absent)"),
        "",
        "INSIGHT BUS (open rows, severity-ordered — informational only):",
        context.get("insight_bus_open", "(absent)"),
        "",
        "TRAJECTORY (lobe fitness slope):",
        context.get("trajectory_block", "(absent)"),
        "",
        "STRATEGIC GAP (cross-lobe biggest gap):",
        context.get("strategic_gap", "(absent)"),
        "",
        "MISSION:",
        context.get("mission_block", "(absent)"),
        "",
        "STRATEGIC MEMORY (past verify outcomes for this lobe):",
        context.get("strategic_memory", "(absent)"),
        "",
        f"Propose at most {max_n} changes now, as a JSON array only.",
    ]
    return "\n".join(parts)


def _invoke_llm(
    context: dict[str, Any],
    max_n: int,
    cfg: dict[str, Any] | None = None,
    lobe: str = LOBE,
    root: Path | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Call the Opus proposer via the shared llm_auth waterfall.

    Returns (reply_text, provider_used, degraded_reason).  NEVER raises.
    Tests patch this function to inject a canned reply without any network.
    """
    conf = {**_LLM_CFG, **(cfg or {})}
    try:
        from engine import llm_auth  # type: ignore[import]
        providers = llm_auth.build_providers(
            conf, opus_model=conf.get("opus_model"),
            deepseek_model=conf.get("deepseek_model"),
        )
        if not providers:
            return None, None, "no_provider"

        system = _build_system_prompt(lobe, root).replace("{max_n}", str(max_n))
        user = _build_user_prompt(context, max_n)
        max_tokens = int(conf.get("max_tokens", 4000))

        def _do_call(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0,
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal"
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return (text or None), None

        text, reason, provider = llm_auth.make_call(
            providers, _do_call, context="metabolism_propose")
        return text, provider, reason
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: LLM invocation failed: %s", exc)
        return None, None, "llm_error"


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Parse a JSON array of proposals out of a model reply.  Returns [] on failure.

    Tolerant of ```json fences and of a leading/trailing prose wrapper.
    """
    if not text:
        return []
    s = text.strip()
    # Strip code fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    # Try whole-string parse first.
    for candidate in (s, _slice_bracketed(s)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            # A single object, or {"proposals": [...]}
            inner = data.get("proposals")
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
            return [data]
    return []


def _slice_bracketed(s: str) -> str:
    """Return the substring from the first '[' to the last ']' (or braces)."""
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = s.find(open_c), s.rfind(close_c)
        if 0 <= i < j:
            return s[i:j + 1]
    return ""


# ── Proposal validation + contract minting ────────────────────────────────────

def _mint_contract(prop: dict[str, Any], proposal_id: str, today: str) -> dict[str, Any]:
    """Build the fitness contract in the exact shape engine.metabolism.verify reads."""
    raw = prop.get("fitness_contract") or {}
    sensor = str(raw.get("sensor") or prop.get("targets_sensor") or "").strip()
    sign = str(raw.get("expected_sign") or "+").strip()
    if sign not in ("+", "-"):
        sign = "+"
    check_by = str(raw.get("check_by") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", check_by):
        # default: max(today + horizon, first-real-check-by)
        horizon = (datetime.strptime(today, "%Y-%m-%d")
                   + timedelta(days=_DEFAULT_HORIZON_DAYS)).strftime("%Y-%m-%d")
        check_by = max(horizon, _FIRST_REAL_CHECK_BY)
    else:
        check_by = max(check_by, _FIRST_REAL_CHECK_BY)
    return {
        "proposal_id": proposal_id,
        "sensor": sensor,
        "expected_sign": sign,
        "band": str(raw.get("band") or "unspecified").strip(),
        "check_by": check_by,
        "placebo_to_beat": str(raw.get("placebo_to_beat") or "shadow placebo tape").strip(),
        # falsifier_spec is a qledger-compatible check dict; the proposer rarely
        # supplies a wired one, so default to {} — verify() reads it defensively
        # and returns UNVERIFIABLE (→ operator_tap) rather than a false kill.
        "falsifier_spec": raw.get("falsifier_spec") if isinstance(raw.get("falsifier_spec"), dict) else {},
        "asof": today,
    }


def _validate_proposal(
    prop: dict[str, Any],
    accruing_maturity: dict[str, str] | None = None,
) -> str | None:
    """Return an error string if the proposal is structurally invalid, else None.

    Parameters
    ----------
    accruing_maturity : dict[str, str] | None
        Optional map of {sensor_id: maturity_date} for sensors still accruing.
        When provided, the accrual-honesty gate rejects proposals whose check_by
        is earlier than the sensor's maturity_date (R-V4-10).
    """
    if not isinstance(prop, dict):
        return "not an object"
    if not str(prop.get("title") or "").strip():
        return "missing title"
    tier = str(prop.get("tier") or "").strip().upper()
    if tier not in _VALID_TIERS:
        return f"invalid tier {prop.get('tier')!r}"
    # T2 proposals are operator-only — the loop may never propose them (R-AUT-4).
    if tier == "T2":
        return "T2 proposals are operator-only and forbidden to the loop"
    fc = prop.get("fitness_contract")
    if not isinstance(fc, dict):
        return "missing fitness_contract"
    sensor = str(fc.get("sensor") or prop.get("targets_sensor") or "").strip()
    if not sensor:
        return "fitness_contract has no sensor"

    # Accrual-honesty gate (R-V4-10): check_by must be >= maturity_date for accruing sensors
    if accruing_maturity:
        mat_date = accruing_maturity.get(sensor)
        if mat_date:
            check_by = str(fc.get("check_by") or "").strip()
            if check_by and re.match(r"^\d{4}-\d{2}-\d{2}$", check_by):
                if check_by < mat_date:
                    return (
                        f"accrual-honesty violation: sensor '{sensor}' matures {mat_date} "
                        f"but check_by={check_by!r} is earlier; set check_by >= {mat_date}"
                    )

    return None


# ── Docket assembly ───────────────────────────────────────────────────────────

def build_docket(
    cycle_id: str,
    raw_proposals: list[dict[str, Any]],
    *,
    root: Path | None = None,
    max_docket_size: int = 5,
    today: str | None = None,
    run_id: str | None = None,
    provider: str | None = None,
    degraded_reason: str | None = None,
    lobe: str = LOBE,
) -> dict[str, Any]:
    """Validate, dedup, cap, and contract-stamp raw proposals into a docket dict.

    NEVER raises.  Invalid/dup/killed proposals are dropped into `rejected`
    (honest nulls), never silently vanished.

    Accrual-honesty validation (R-V4-10): loads accruing sensor maturity dates
    from the lobe charter and rejects proposals with check_by earlier than the
    sensor's maturity_date.
    """
    r = _repo_root(root)
    day = _today(today)
    corpus = _load_dedup_corpus(r)
    seen_this_cycle: set[str] = set()

    # Load accruing sensor maturity dates for this lobe (fail-open: {} = no gate)
    accruing_maturity = _load_accruing_sensor_maturity(r, lobe)

    proposals: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for prop in (raw_proposals or []):
        try:
            title = str((prop or {}).get("title") or "").strip()
            err = _validate_proposal(prop, accruing_maturity=accruing_maturity)
            if err:
                rejected.append({"title": title or "(untitled)", "reason": err})
                continue

            tier = str(prop["tier"]).strip().upper()
            kind = str(prop.get("kind") or "").strip()
            sensor = str((prop.get("fitness_contract") or {}).get("sensor")
                         or prop.get("targets_sensor") or "").strip()

            pid = content_hash(title, sensor, kind)
            if pid in seen_this_cycle:
                rejected.append({"title": title, "reason": "duplicate within this cycle"})
                continue

            dreason = _dedup_reason(title, sensor, kind, corpus)
            if dreason:
                rejected.append({"title": title, "reason": dreason})
                continue

            if len(proposals) >= int(max_docket_size):
                rejected.append({"title": title, "reason": f"over max_docket_size={max_docket_size}"})
                continue

            seen_this_cycle.add(pid)
            proposals.append({
                "proposal_id": pid,
                "content_hash": pid,
                "title": title,
                "tier": tier,
                "kind": kind,
                "targets_sensor": sensor,
                "rationale": str(prop.get("rationale") or "").strip(),
                "fitness_contract": _mint_contract(prop, pid, day),
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("propose: proposal skipped (%s)", exc)
            rejected.append({"title": "(error)", "reason": f"exception: {exc}"})

    return {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "lobe": lobe,
        "as_of": day,
        "run_id": run_id,
        "generated_by": "metabolism_propose",
        "provider": provider,
        "degraded_reason": degraded_reason,
        "proposals": proposals,
        "rejected": rejected,
        "authority": AUTHORITY_BLOCK,
        "notes": (
            f"{len(proposals)} proposal(s) after dedup/cap; {len(rejected)} rejected. "
            "TIL fitness accrues until 2026-10-15 — contracts minted now are shadow/display-tier "
            "and grade only after their check_by. Nothing here is a runtime signal (R-AUT-1)."
        ),
    }


def register_contracts(docket: dict[str, Any], root: Path | None = None) -> int:
    """Register each proposal's fitness contract as one declared trial (R-AUT-8).

    Uses the 'metabolism_til' FDR family so loop volume never raises the human
    programs' discovery bar.  Returns the count registered.  NEVER raises.
    """
    proposals = docket.get("proposals") or []
    if not proposals:
        return 0
    try:
        from engine.trial_ledger import TrialLedger  # type: ignore[import]
        path = (_repo_root(root) / "data" / "trial_ledger.jsonl") if root is not None else None
        led = TrialLedger(path=path, family=TRIAL_FAMILY)
        n = 0
        for prop in proposals:
            try:
                led.log_declared_budget(
                    1, family=TRIAL_FAMILY,
                    reason=f"metabolism proposal {prop.get('proposal_id')}: {prop.get('title', '')[:100]}",
                )
                n += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("propose: contract registration failed for %s (%s)",
                            prop.get("proposal_id"), exc)
        return n
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: trial ledger unavailable: %s", exc)
        return 0


def write_docket(docket: dict[str, Any], root: Path | None = None) -> Path | None:
    """Atomically write the docket to data/metabolism/dockets/<cycle_id>.json."""
    try:
        p = docket_path(docket["cycle_id"], root)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(docket, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)
        return p
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: docket write failed: %s", exc)
        return None


# ── Orchestration (pure — no kill-switch/journal; the CLI owns those) ─────────

def propose(
    cycle_id: str,
    *,
    lobe: str = LOBE,
    root: Path | None = None,
    max_docket_size: int = 5,
    today: str | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
    injected_proposals: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the PROPOSE core: context → LLM → docket → contracts → write.

    Parameters
    ----------
    lobe : str
        Which lobe's charter to drive the prompt. Defaults to 'til' (the only
        actively loop-managed lobe today).  Pass a different lobe id to route
        the charter-driven system prompt, accrual-honesty gate, and trajectory
        annotation to a different lobe.
    injected_proposals : list | None
        If provided, the LLM call is skipped and these raw proposals are used
        directly (hermetic-test seam).

    Returns
    -------
    dict {docket, meta} where meta carries provider/degraded_reason/registered/
    n_proposals/n_rejected/artifact.  NEVER raises.
    """
    try:
        provider: str | None = None
        degraded: str | None = None

        if injected_proposals is not None:
            raw = injected_proposals
        else:
            context = build_prompt_context(root, lobe=lobe)
            text, provider, degraded = _invoke_llm(
                context, int(max_docket_size), cfg, lobe=lobe, root=root,
            )
            raw = _extract_json_array(text or "")
            if not raw and not degraded:
                degraded = "empty_or_unparseable_reply"

        docket = build_docket(
            cycle_id, raw, root=root, max_docket_size=int(max_docket_size),
            today=today, run_id=run_id, provider=provider, degraded_reason=degraded,
            lobe=lobe,
        )

        registered = 0
        artifact: str | None = None
        if not dry_run:
            registered = register_contracts(docket, root)
            p = write_docket(docket, root)
            artifact = str(p) if p else None

            # Stamp a lobe-annotated trajectory row so strategic.build_trajectory_block
            # can filter rows by lobe_id (Finding #2: run_trajectory was defined but
            # never called from the propose path).
            try:
                from engine.metabolism.trajectory import run_trajectory  # noqa: PLC0415
                run_trajectory(cycle_id=cycle_id, root=root, lobe_id=lobe)
            except Exception as _te:  # noqa: BLE001
                log.warning("propose: trajectory stamp failed — %s", _te)

        return {
            "docket": docket,
            "meta": {
                "provider": provider,
                "degraded_reason": degraded,
                "registered": registered,
                "n_proposals": len(docket.get("proposals") or []),
                "n_rejected": len(docket.get("rejected") or []),
                "artifact": artifact,
            },
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("propose: unexpected error for %s: %s", cycle_id, exc)
        empty = build_docket(cycle_id, [], root=root, max_docket_size=int(max_docket_size),
                             today=today, run_id=run_id, degraded_reason=f"exception:{exc}")
        return {"docket": empty, "meta": {"provider": None, "degraded_reason": f"exception:{exc}",
                                          "registered": 0, "n_proposals": 0,
                                          "n_rejected": 0, "artifact": None}}
