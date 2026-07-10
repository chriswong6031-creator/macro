"""engine.metabolism.agenda — Agenda-setter core (V2-A §4).

Stateless Opus reasoner.  Reads organism_state + open insight_bus rows +
ruling_graph slice + ACTIVE_BUILD_MAP → emits a ranked agenda artifact.

INERTNESS GUARANTEE:
    This module ONLY writes data/metabolism/agenda/<cycle_id>.json.
    It dispatches NOTHING, grants NOTHING, opens NO PR, touches NO lobe roster.

DETERMINISTIC SEVERITY FLOOR (enforced after every LLM call):
    Every open insight_bus row with severity >= 'high' MUST appear as an
    URGENT_FIX item in the agenda.  The LLM may reorder within a bucket;
    it may never DROP a high-severity finding.  This floor is enforced in
    code — the LLM output is post-processed before writing.

DEDUP:
    A content_hash (sha256[:12] of normalized title) is checked against
    DO_NOT_REBUILD.md and ACTIVE_BUILD_MAP.  Killed or in-flight topics
    are dropped from the agenda.

BUDGET-SPLIT GUIDANCE (not enforced here — informational for the LLM):
    max_docket_size from metabolism_budget.yml guides the total item count.
    Suggested split: 40% URGENT_FIX, 40% NOVEL_BUILD, 20% DEEP_RESEARCH.

SCHEMA (metabolism.agenda.v1):
{
  "schema":    "metabolism.agenda.v1",
  "cycle_id":  str,
  "as_of":     ISO date,
  "generated_by": "metabolism_agenda",
  "provider":  str | null,
  "degraded_reason": str | null,
  "items": [
    {
      "title":       str,
      "bucket":      "URGENT_FIX" | "NOVEL_BUILD" | "DEEP_RESEARCH",
      "severity":    str,          # low|medium|high|critical
      "target_lobe": str | null,
      "rationale":   str,
      "dedup_hash":  str,          # sha256[:12] of normalized(title)
      "forced_floor": bool,        # True if this item was inserted by the severity floor
    },
    ...
  ],
  "rejected":  [{title, reason}, ...],
  "authority": { is_context_only: true, ... },
}

NEVER-RAISE CONTRACT: every function catches all exceptions, logs, returns safe fallback.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.metabolism.orchestrator_brain import _build_orchestrator_system  # noqa: PLC2403
from engine.metabolism.insight_bus import get_open_rows  # noqa: F401
from engine.metabolism.organism_state import build_organism_state  # noqa: F401

log = logging.getLogger(__name__)

SCHEMA = "metabolism.agenda.v1"
AGENDA_DIR = Path("data") / "metabolism" / "agenda"

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
        "dispatch", "grant", "pr_open", "lobe_roster_change",
    ],
}

_BUCKETS = frozenset({"URGENT_FIX", "NOVEL_BUILD", "DEEP_RESEARCH"})
_SEVERITIES = ("low", "medium", "high", "critical")
_HIGH_SEVERITIES = frozenset({"high", "critical"})


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ── Content-hash dedup ─────────────────────────────────────────────────────────

def _dedup_hash(title: str) -> str:
    """sha256[:12] of normalized title."""
    normalized = re.sub(r"[^a-z0-9]+", "_", title.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def _load_killed_topics(root: Path) -> set[str]:
    """Load topic titles from research/DO_NOT_REBUILD.md (rough keyword set)."""
    p = root / "research" / "DO_NOT_REBUILD.md"
    if not p.exists():
        return set()
    try:
        text = p.read_text(encoding="utf-8")
        # Extract lines that look like topic headings / table rows
        words: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#") or line.startswith("|"):
                # Extract alphanumeric tokens of length >= 4
                for token in re.findall(r"[a-z0-9_]{4,}", line.lower()):
                    words.add(token)
        return words
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda: cannot load DO_NOT_REBUILD — %s", exc)
        return set()


def _is_killed(title: str, killed_words: set[str]) -> bool:
    """Heuristic: title is killed if it shares 2+ content words with the kill registry."""
    if not killed_words:
        return False
    title_words = set(re.findall(r"[a-z0-9_]{4,}", title.lower()))
    overlap = title_words & killed_words
    return len(overlap) >= 2


def _load_active_build_hashes(root: Path) -> set[str]:
    """Load dedup hashes from ACTIVE_BUILD_MAP.md (titles mentioned in open PRs)."""
    p = root / "docs" / "ACTIVE_BUILD_MAP.md"
    if not p.exists():
        return set()
    try:
        text = p.read_text(encoding="utf-8")
        hashes: set[str] = set()
        # Every line may contain a title-like phrase
        for line in text.splitlines():
            line = line.strip()
            if len(line) > 10:
                hashes.add(_dedup_hash(line))
        return hashes
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda: cannot load ACTIVE_BUILD_MAP — %s", exc)
        return set()


# ── Agenda item validator / normalizer ────────────────────────────────────────

def _normalize_item(item: Any) -> dict | None:
    """Validate and normalize one agenda item from LLM output."""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    bucket = str(item.get("bucket") or "NOVEL_BUILD").upper()
    if bucket not in _BUCKETS:
        bucket = "NOVEL_BUILD"
    severity = str(item.get("severity") or "low").lower()
    if severity not in _SEVERITIES:
        severity = "low"
    return {
        "title": title,
        "bucket": bucket,
        "severity": severity,
        "target_lobe": item.get("target_lobe") or None,
        "rationale": str(item.get("rationale") or "")[:500],
        "dedup_hash": _dedup_hash(title),
        "forced_floor": bool(item.get("forced_floor", False)),
    }


# ── Severity floor enforcer ────────────────────────────────────────────────────

def _enforce_severity_floor(
    items: list[dict],
    high_insight_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Ensure every high-severity insight row appears as URGENT_FIX.

    Returns (items_with_floor, newly_forced_items).
    The LLM may NOT drop a high-severity bus row.
    """
    existing_hashes = {item["dedup_hash"] for item in items}
    forced: list[dict] = []

    for row in high_insight_rows:
        # Build a title from the insight row
        title = f"[AUTO] {row.get('kind', 'anomaly').upper()}: {row.get('summary', '')[:80]}"
        dh = _dedup_hash(title)
        if dh in existing_hashes:
            continue  # Already present
        forced_item: dict[str, Any] = {
            "title": title,
            "bucket": "URGENT_FIX",
            "severity": row.get("severity") or "high",
            "target_lobe": (row.get("entities") or [None])[0],
            "rationale": (
                f"Forced floor: high-severity insight {row.get('insight_id', '?')} "
                f"from emitter {row.get('emitter', '?')}. "
                f"Evidence: {row.get('evidence_ref', 'none')}"
            ),
            "dedup_hash": dh,
            "forced_floor": True,
        }
        items.append(forced_item)
        existing_hashes.add(dh)
        forced.append(forced_item)

    return items, forced


# ── LLM agenda call ───────────────────────────────────────────────────────────

_AGENDA_PROMPT_TEMPLATE = """\
You are the Metabolism Orchestrator.  Your task: produce a ranked agenda of work items.

INPUT DATA is in the system prompt above (organism_state, open insight bus rows, standing laws, active build map).

OUTPUT FORMAT — respond with ONLY valid JSON (no markdown, no preamble):
{{
  "items": [
    {{
      "title": "short imperative phrase",
      "bucket": "URGENT_FIX" | "NOVEL_BUILD" | "DEEP_RESEARCH",
      "severity": "low" | "medium" | "high" | "critical",
      "target_lobe": "lobe_id or null",
      "rationale": "1-2 sentences citing evidence from the input data"
    }}
  ]
}}

RULES:
- Maximum {max_docket_size} items total.
- Rank URGENT_FIX first, then NOVEL_BUILD, then DEEP_RESEARCH.
- Every item must cite specific evidence from the organism_state or insight bus rows.
- Do NOT propose anything touching scored-path surfaces, authority levels, or PR merges.
- Do NOT propose anything in DO_NOT_REBUILD or already in the ACTIVE_BUILD_MAP.
- Every 'title' must be unique and <=80 characters.
- Respond with ONLY the JSON object — no surrounding text.
"""


def _call_llm(
    providers: list[dict],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
) -> tuple[str | None, str | None, str | None]:
    """Call the LLM via llm_auth.make_call.

    Returns (text, degraded_reason, provider_used).
    NEVER-RAISE.
    """
    try:
        from engine.llm_auth import make_call  # noqa: PLC0415

        def _call_fn(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.content[0].text if resp.content else None
            return text, None

        return make_call(providers, _call_fn, context="metabolism_agenda")
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda._call_llm: failed — %s", exc)
        return None, f"llm_error: {exc}", None


def _parse_llm_items(text: str | None) -> list[dict]:
    """Parse LLM output JSON into agenda items.  Returns [] on any failure."""
    if not text:
        return []
    try:
        # Strip markdown fences
        stripped = re.sub(r"```[a-z]*\n?", "", text).strip()
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data.get("items") or []
        if isinstance(data, list):
            return data
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda._parse_llm_items: JSON parse failed — %s", exc)
        return []


# ── Main builder ──────────────────────────────────────────────────────────────

def build_agenda(
    cycle_id: str,
    root: Path | None = None,
    providers: list[dict] | None = None,
    model: str | None = None,
    max_docket_size: int | None = None,
) -> dict[str, Any]:
    """Build the agenda artifact for a given cycle.

    Parameters
    ----------
    cycle_id : str
        Current cycle identifier.
    root : Path | None
        Repo root override for testing.
    providers : list[dict] | None
        LLM provider list (from llm_auth.build_providers).
        If None, a no-provider empty agenda is returned.
    model : str | None
        Model ID (used to decide fable_mode_core injection).
    max_docket_size : int | None
        Cap on total items; loaded from metabolism_budget.yml if not provided.

    Returns
    -------
    dict — agenda artifact (schema metabolism.agenda.v1). NEVER raises.
    """
    try:
        return _build_agenda_inner(
            cycle_id=cycle_id,
            root=root,
            providers=providers,
            model=model,
            max_docket_size=max_docket_size,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda.build_agenda: fatal — %s", exc)
        return {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "as_of": _now_date(),
            "generated_by": "metabolism_agenda",
            "provider": None,
            "degraded_reason": f"fatal error: {exc}",
            "items": [],
            "rejected": [],
            "authority": AUTHORITY_BLOCK,
            "grounding": {"unverified": True},
        }


def _build_agenda_inner(
    cycle_id: str,
    root: Path | None,
    providers: list[dict] | None,
    model: str | None,
    max_docket_size: int | None,
) -> dict[str, Any]:
    """Inner builder — allowed to raise; wrapped by build_agenda."""
    repo = _repo_root(root)

    # 1. Load budget config for max_docket_size
    if max_docket_size is None:
        try:
            import yaml  # noqa: PLC0415
            budget_path = repo / "config" / "metabolism_budget.yml"
            if budget_path.exists():
                budget_cfg = yaml.safe_load(budget_path.read_text(encoding="utf-8")) or {}
                max_docket_size = budget_cfg.get("max_docket_size") or 5
        except Exception as exc:  # noqa: BLE001
            log.warning("agenda: cannot load budget config — %s", exc)
        max_docket_size = max_docket_size or 5

    # 2. Load organism state
    try:
        os_path = repo / "data" / "metabolism" / "organism_state.json"
        organism_state = _read_json(os_path)
        if organism_state is None:
            log.info("agenda: organism_state.json absent — building on the fly")
            organism_state = build_organism_state(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda: cannot load organism_state — %s", exc)
        organism_state = {}

    # 3. Load open insight bus rows
    try:
        open_rows = get_open_rows(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("agenda: cannot get open insight rows — %s", exc)
        open_rows = []

    high_rows = [r for r in open_rows if r.get("severity") in _HIGH_SEVERITIES]

    # 4. Load dedup context
    killed_words = _load_killed_topics(repo)
    active_hashes = _load_active_build_hashes(repo)

    # 5. Build system prompt
    system_prompt = _build_orchestrator_system(
        model=model,
        role="orchestrator",
        lobe=None,
        root=repo,
        organism_state=organism_state,
    )

    # 6. Build user prompt (include open rows)
    open_rows_text = json.dumps(open_rows[:20], ensure_ascii=False)  # Cap at 20
    user_prompt = _AGENDA_PROMPT_TEMPLATE.format(max_docket_size=max_docket_size)
    user_prompt += (
        f"\n\n## Open Insight Bus Rows (high-severity MUST appear in URGENT_FIX)\n"
        f"```json\n{open_rows_text}\n```"
    )

    # 7. LLM call
    provider_used: str | None = None
    degraded_reason: str | None = None
    raw_items: list[dict] = []

    if providers:
        text, degraded_reason, provider_used = _call_llm(
            providers=providers,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2000,
        )
        raw_items = _parse_llm_items(text)
    else:
        degraded_reason = "no_provider"
        log.info("agenda: no providers configured — returning floor-only agenda")

    # 8. Normalize and dedup
    items: list[dict] = []
    rejected: list[dict] = []
    seen_hashes: set[str] = set()

    for raw in raw_items:
        item = _normalize_item(raw)
        if item is None:
            rejected.append({"title": str(raw), "reason": "normalization_failed"})
            continue
        dh = item["dedup_hash"]
        if dh in seen_hashes:
            rejected.append({"title": item["title"], "reason": "duplicate"})
            continue
        if _is_killed(item["title"], killed_words):
            rejected.append({"title": item["title"], "reason": "killed_topic"})
            continue
        if dh in active_hashes:
            rejected.append({"title": item["title"], "reason": "already_in_flight"})
            continue
        items.append(item)
        seen_hashes.add(dh)

    # 9. DETERMINISTIC SEVERITY FLOOR — enforce AFTER LLM processing
    items, forced = _enforce_severity_floor(items, high_rows)

    # 10. Cap at max_docket_size (floor items count first)
    if len(items) > max_docket_size:
        # Preserve forced-floor items; trim from the end
        forced_items = [i for i in items if i.get("forced_floor")]
        regular_items = [i for i in items if not i.get("forced_floor")]
        n_regular = max(0, max_docket_size - len(forced_items))
        items = forced_items + regular_items[:n_regular]

    # 11. Grounding check (R-V3-5b) — informational annotation; NEVER blocks items
    grounding: dict[str, Any] = {"unverified": True}
    try:
        from engine.metabolism import grounding as _grounding  # noqa: PLC0415
        _payload = {"items": items, "rejected": rejected}
        grounding = _grounding.validate_grounding(_payload, root=repo)
    except Exception as _exc:  # noqa: BLE001
        log.warning("agenda: grounding check failed (display-tier, non-fatal) — %s", _exc)

    return {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "as_of": _now_date(),
        "generated_by": "metabolism_agenda",
        "provider": provider_used,
        "degraded_reason": degraded_reason,
        "items": items,
        "rejected": rejected,
        "authority": AUTHORITY_BLOCK,
        "grounding": grounding,
    }
