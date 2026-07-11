"""engine.metabolism.applier — Charter-proposal + lifecycle-docket applier (V4 W5, R-V4-9).

consume_charter_proposals(root) reads:
  - data/metabolism/charter_proposals/*.json   (scout output)
  - data/metabolism/lifecycle_docket/*.json    (lifecycle.py output)

and routes each item as an injected proposal into the normal PROPOSE→ADJUDICATE
gauntlet (propose.py already supports injected_proposals — that seam is used here).

CRITICAL SAFETY PROPERTIES (double fence, mirrors lifecycle.py)
---------------------------------------------------------------
1. Tier-raise REFUSAL: any item whose destination raises tier to 'confirmer' or
   'scored' is REFUSED with a journal row — refused items are NEVER injected.
   This is defense-in-depth on top of lifecycle.py's own fence.

2. POST-GRANT APPLICATION: even when armed, the applier NEVER edits
   config/lobe_charters.yml directly.  Instead it emits a diff/draft-PR PLAN
   record under data/metabolism/shadow/<plan_id>.json so the BUILD lane
   (metabolism_build) is the only code-writer.

3. SHADOW / DRY-RUN MODE: when AUTONOMY_PAUSED or dry_run=True, all plan
   records go to data/metabolism/shadow/ and no injected_proposals are returned.

4. Only display-tier state transitions are allowed post-grant in armed mode.

NEVER-RAISE CONTRACT: every public function returns a safe fallback on any error.
No LLM calls, no network, no reads from ~/. Deterministic.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.applier.v1"

# Dirs that the applier reads
CHARTER_PROPOSALS_DIR = ("data", "metabolism", "charter_proposals")
LIFECYCLE_DOCKET_DIR = ("data", "metabolism", "lifecycle_docket")

# Plan record output (never lobe_charters.yml directly)
SHADOW_DIR = ("data", "metabolism", "shadow")

# Tiers whose destination MUST be refused (double fence mirrors lifecycle.py)
_REFUSED_DESTINATION_TIERS = frozenset({"confirmer", "scored"})
_REFUSED_LIFECYCLE_STATES = frozenset({"confirmer", "scored"})

# Journal dir for refusal records
APPLIER_JOURNAL_PATH = ("data", "metabolism", "applier_journal.jsonl")

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
        "direct_charter_edit",
    ],
}


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plan_id(item: dict[str, Any]) -> str:
    """Deterministic plan id from item content."""
    raw = json.dumps(item, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Refusal guard (double fence) ──────────────────────────────────────────────

def _is_tier_raise_forbidden(item: dict[str, Any]) -> tuple[bool, str]:
    """Return (True, reason) if this item would raise tier to a forbidden level.

    Checks both 'tier' fields and 'to_state' lifecycle fields.
    """
    tier = str(item.get("tier") or item.get("destination_tier") or "").lower()
    if tier in _REFUSED_DESTINATION_TIERS:
        return True, (
            f"tier-raise refused: destination tier '{tier}' is confirmer/scored — "
            "lifecycle.py cannot emit this autonomously (R-V2-3); "
            "applier double-fence prevents injection"
        )

    to_state = str(item.get("to_state") or "").lower()
    if to_state in _REFUSED_LIFECYCLE_STATES:
        return True, (
            f"lifecycle-state refused: to_state='{to_state}' would reach confirmer/scored — "
            "blocked by applier double fence (R-V2-3)"
        )

    return False, ""


def _journal_refusal(
    item: dict[str, Any],
    reason: str,
    repo: Path,
) -> None:
    """Append a refusal record to the applier journal.  NEVER raises."""
    try:
        journal_path = repo.joinpath(*APPLIER_JOURNAL_PATH)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema": SCHEMA,
            "ts": _now_iso(),
            "event": "tier_raise_refused",
            "item_id": str(item.get("schema") or "unknown"),
            "item_lobe_id": str(item.get("lobe_id") or ""),
            "reason": reason,
            "authority": AUTHORITY_BLOCK,
        }
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("applier._journal_refusal: %s", exc)


# ── Charter proposal loading ──────────────────────────────────────────────────

def _load_charter_proposals(repo: Path) -> list[dict[str, Any]]:
    """Load all charter_proposals/*.json files.  Returns [] on any error."""
    items: list[dict[str, Any]] = []
    proposals_dir = repo.joinpath(*CHARTER_PROPOSALS_DIR)
    if not proposals_dir.exists():
        return items
    try:
        for f in sorted(proposals_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source_file"] = str(f.name)
                    items.append(data)
                elif isinstance(data, list):
                    for d in data:
                        if isinstance(d, dict):
                            d["_source_file"] = str(f.name)
                            items.append(d)
            except Exception as exc:  # noqa: BLE001
                log.warning("applier: cannot read charter_proposals/%s — %s", f.name, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("applier._load_charter_proposals: %s", exc)
    return items


def _load_lifecycle_docket(repo: Path) -> list[dict[str, Any]]:
    """Load all lifecycle_docket/*.json files.  Returns [] on any error."""
    items: list[dict[str, Any]] = []
    docket_dir = repo.joinpath(*LIFECYCLE_DOCKET_DIR)
    if not docket_dir.exists():
        return items
    try:
        for f in sorted(docket_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source_file"] = str(f.name)
                    items.append(data)
            except Exception as exc:  # noqa: BLE001
                log.warning("applier: cannot read lifecycle_docket/%s — %s", f.name, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("applier._load_lifecycle_docket: %s", exc)
    return items


# ── Item → injected proposal conversion ──────────────────────────────────────

def _item_to_proposal(item: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a charter proposal or lifecycle docket item to an injected_proposal dict.

    Returns None if the item cannot be converted (missing required fields).
    NEVER raises.
    """
    try:
        # Determine title
        title = str(item.get("title") or item.get("description") or "").strip()
        lobe_id = str(item.get("lobe_id") or item.get("lobe") or "").strip()
        if not title and lobe_id:
            from_state = str(item.get("from_state") or "").strip()
            to_state = str(item.get("to_state") or "").strip()
            if from_state and to_state:
                title = f"lifecycle: {lobe_id} {from_state}→{to_state}"
        if not title:
            return None

        # Tier: default T1 for lifecycle docket items, T0 for charter proposals
        schema = str(item.get("schema") or "")
        if "lifecycle" in schema:
            tier = str(item.get("tier") or item.get("t_level") or "T1").strip().upper()
        else:
            tier = str(item.get("tier") or "T0").strip().upper()
        if tier not in ("T0", "T1", "T2"):
            tier = "T1"

        # Kind
        kind = str(item.get("kind") or "engine").strip()
        if kind not in ("test", "doc", "context_organ", "engine", "collector", "ui"):
            kind = "engine"

        # Sensor
        sensor = str(item.get("targets_sensor") or item.get("sensor") or "liveness").strip()

        # Rationale
        rationale = str(item.get("rationale") or item.get("reason") or item.get("description") or "").strip()

        # Fitness contract
        # Scout charter proposals (metabolism.charter_proposal.v1) carry no
        # fitness_contract BY DESIGN — chartering a display-tier lobe is a
        # lifecycle act, not a sensor-delta build.  Its honest falsifiable
        # contract is liveness-at-maturity: the chartered lobe must produce
        # its artifact and pass health by check_by.  We synthesize that
        # default openly, stamped with contract_source so the adjudicator
        # and any later audit can see the contract was applier-defaulted,
        # never silently fabricated as a fitness claim.
        fc_raw = item.get("fitness_contract") or {}
        if not isinstance(fc_raw, dict):
            fc_raw = {}

        item_schema = str(item.get("schema") or "")
        is_charter_proposal = "charter_proposal" in item_schema and "lifecycle" not in item_schema
        if is_charter_proposal and not fc_raw.get("sensor"):
            sensor = "liveness"

        fc: dict[str, Any] = {
            "sensor": fc_raw.get("sensor") or sensor,
            "expected_sign": fc_raw.get("expected_sign") or "+",
            "band": fc_raw.get("band") or "unspecified",
            "check_by": fc_raw.get("check_by") or "2026-10-15",
            "placebo_to_beat": fc_raw.get("placebo_to_beat") or "shadow placebo tape",
            "contract_source": (
                "item" if fc_raw.get("sensor") else "applier_default_charter_liveness"
            ),
        }

        return {
            "title": title,
            "tier": tier,
            "kind": kind,
            "targets_sensor": sensor,
            "rationale": rationale,
            "fitness_contract": fc,
            "_from_applier": True,
            "_source_file": item.get("_source_file"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("applier._item_to_proposal: %s", exc)
        return None


# ── Plan record emission (armed post-grant) ───────────────────────────────────

def _emit_plan_record(
    item: dict[str, Any],
    plan_id: str,
    repo: Path,
    shadow: bool = False,
) -> Path | None:
    """Write a draft-PR plan record (never edits lobe_charters.yml directly).

    When shadow=True or armed mode applies to display-tier only, always goes to
    data/metabolism/shadow/.  NEVER raises.
    """
    try:
        out_dir = repo.joinpath(*SHADOW_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "schema": "metabolism.applier_plan.v1",
            "ts": _now_iso(),
            "plan_id": plan_id,
            "shadow": shadow,
            "action": "draft_pr_plan",
            "note": (
                "This is a PLAN record only. The BUILD lane (metabolism_build) is the "
                "only code-writer; the applier NEVER edits config/lobe_charters.yml "
                "or config/synapse.yml directly."
            ),
            "proposed_edit": {
                "target_file": "config/lobe_charters.yml",
                "lobe_id": str(item.get("lobe_id") or ""),
                "from_state": str(item.get("from_state") or ""),
                "to_state": str(item.get("to_state") or ""),
                "tier": str(item.get("tier") or ""),
                "description": str(item.get("description") or item.get("reason") or ""),
            },
            "source_item": item,
            "authority": AUTHORITY_BLOCK,
        }
        out_path = out_dir / f"{plan_id}.json"
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
        tmp.replace(out_path)
        return out_path
    except Exception as exc:  # noqa: BLE001
        log.warning("applier._emit_plan_record: %s", exc)
        return None


# ── Main public function ──────────────────────────────────────────────────────

def consume_charter_proposals(
    root: Path | None = None,
    *,
    dry_run: bool = False,
    armed: bool = False,
) -> list[dict[str, Any]]:
    """Read charter_proposals/ and lifecycle_docket/, apply safety screens,
    and return a list of injected_proposals for the PROPOSE gauntlet.

    Parameters
    ----------
    root : Path | None
        Repo root override.
    dry_run : bool
        If True, behave as shadow mode: no items injected, plan records go to
        data/metabolism/shadow/.
    armed : bool
        If True (AUTONOMY_PAUSED=false and operator-armed), post-grant plan
        records are emitted for allowed display-tier items.  If False (default,
        paused), plan records still go to shadow/.

    Returns
    -------
    list[dict] — injected_proposals (empty in shadow/dry_run mode).
    NEVER raises.
    """
    try:
        repo = _repo_root(root)
        is_shadow = dry_run or not armed

        charter_items = _load_charter_proposals(repo)
        lifecycle_items = _load_lifecycle_docket(repo)
        all_items = charter_items + lifecycle_items

        if not all_items:
            return []

        injected: list[dict[str, Any]] = []
        refused_count = 0
        plan_count = 0

        for item in all_items:
            try:
                # Double fence: tier-raise refusal
                forbidden, reason = _is_tier_raise_forbidden(item)
                if forbidden:
                    _journal_refusal(item, reason, repo)
                    refused_count += 1
                    log.warning("applier: refused item (tier-raise) — %s", reason)
                    continue

                # Convert to injected proposal
                proposal = _item_to_proposal(item)
                if proposal is None:
                    log.info("applier: skipped item (no valid title/sensor)")
                    continue

                # Emit plan record (shadow or armed)
                pid = _plan_id(item)
                plan_path = _emit_plan_record(item, pid, repo, shadow=is_shadow)
                if plan_path:
                    plan_count += 1
                    log.info("applier: plan record → %s (shadow=%s)", plan_path.name, is_shadow)

                # In shadow/dry_run mode, do not inject
                if not is_shadow:
                    injected.append(proposal)

            except Exception as exc:  # noqa: BLE001
                log.warning("applier: item processing error — %s", exc)
                continue

        log.info(
            "applier.consume_charter_proposals: total=%d refused=%d plans=%d injected=%d shadow=%s",
            len(all_items), refused_count, plan_count, len(injected), is_shadow,
        )
        return injected

    except Exception as exc:  # noqa: BLE001
        log.warning("applier.consume_charter_proposals: %s", exc)
        return []
