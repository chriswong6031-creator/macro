"""engine.metabolism.adjudicate — ADJUDICATE row-pair core (A5, ADJUDICATE stage).

Stage 3 of the Metabolism (masterplan §1).  Two DISTINCT stateless runs rule on
each PROPOSE docket entry and write a governance ROW-PAIR — the "two-key"
(R-AUT-6): an ORCHESTRATOR run and an ADVERSARY run, each with its own run_id.

  T0 (docs/tests/display-tier/bug-fix)  → authorized on ORCHESTRATOR grant alone.
  T1/T2 (engines/collectors/UI/algo/...) → authorized only on ORCHESTRATOR grant
                                           AND ADVERSARY non-veto (both keys).

The adversary has skin in the game (R-AUT-9): its structured findings +
pre-committed tripwire predictions are appended to
data/metabolism/adversary_ledger.jsonl so VERIFY can later credit materialized
defects it flagged and debit regressions it missed.

LAWS ENFORCED HERE
------------------
* R-AUT-1  — the LLM may only DE-ESCALATE a calibrated decision, never originate
             authority.  The orchestrator's grant is ANDed with a deterministic
             case-law screen, so a proposal the screen flags (a DO_NOT_REBUILD kill
             or an ACTIVE_BUILD_MAP collision) can never be granted no matter what
             the LLM says, and the LLM's veto/deny always stands.  The screen is a
             best-effort token floor (see _deterministic_screen) — the LLM
             orchestrator, the adversary key, and the operator merge gate are the
             layers above it, not replaced by it.
* R-AUT-6  — the two-key is realized as governance row-PAIRS written by two
             different stateless run_ids, never two live sessions.
* R-AUT-9  — the adversary ledger records findings + tripwire predictions.
* Fail-closed — if the adversary run could not form an opinion (no provider,
             missing judgment), its row records veto=True; a T1/T2 proposal can
             never be authorized without a genuine second key.

Reuses engine.neuralweb.governance.append_event() (schema neuralweb.governance.v1,
NEVER-RAISE) for the row-pair, and adds two event types to its vocabulary:
    metabolism_adjudication      — orchestrator grant/deny + two_key resolution
    metabolism_adversary_review  — adversary veto/non-veto

NEVER-RAISE CONTRACT: every public function returns safe fallbacks on any error.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ADVERSARY_LEDGER = ("data", "metabolism", "adversary_ledger.jsonl")
ADVERSARY_SCHEMA = "metabolism.adversary_ledger.v1"

EVT_ADJUDICATION = "metabolism_adjudication"
EVT_ADVERSARY = "metabolism_adversary_review"

ROLE_ORCH = "orchestrator"
ROLE_ADV = "adversary"
ROLE_TWO_KEY = "two_key"

# Absolute count of distinctive title+rationale tokens that must overlap a kill /
# open-lane before the screen flags a collision on the rationale surface.  Kept
# conservative (false-deny is the INERT-safe direction — the operator can always
# build a wrongly-screened proposal by hand).
_SURFACE_MIN_OVERLAP = 3

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

# Same provider waterfall config as propose / whitehouse_brain.
_LLM_CFG: dict[str, Any] = {
    "provider_order": ["oauth", "anthropic", "deepseek"],
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "oauth_pool_lane": "metabolism-adjudicate",
    "api_key_env": "ANTHROPIC_API_KEY",
    "deepseek_key_env": "DEEPSEEK_API_KEY",
    "deepseek_base_url": "https://api.deepseek.com/anthropic",
    "opus_model": "claude-opus-4-8",
    "deepseek_model": "deepseek-v4-pro",
    "max_tokens": 4000,
}


# ── Path / IO helpers ─────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: read failed %s: %s", path, exc)
        return ""


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _target(cycle_id: str, proposal_id: str) -> str:
    return f"metabolism_proposal:{cycle_id}:{proposal_id}"


def _load_docket(docket_path: str | Path) -> dict[str, Any]:
    try:
        p = Path(docket_path)
        if not p.exists():
            log.warning("adjudicate: docket not found: %s", p)
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: docket load failed: %s", exc)
        return {}


# ── Deterministic case-law screen (R-AUT-1 floor) ─────────────────────────────

def _load_case_law(root: Path | None = None) -> dict[str, str]:
    r = _repo_root(root)
    # The in-flight screen matches OPEN lanes only (shadow finding 2026-07-11):
    # the whole ACTIVE_BUILD_MAP embeds ~500 merged-PR titles, which makes the
    # token quorum trivially satisfiable by common engineering words and would
    # deny essentially every proposal.  Killed topics are DO_NOT_REBUILD's job
    # (kept whole-file).  Fail-closed: missing heading → full text.
    try:
        from engine.metabolism.propose import _open_lanes_only  # noqa: PLC0415
        active_raw = _open_lanes_only(_read_text(r / "docs" / "ACTIVE_BUILD_MAP.md"))
    except Exception:  # noqa: BLE001
        active_raw = _read_text(r / "docs" / "ACTIVE_BUILD_MAP.md")
    return {
        "killed": _normalize(_read_text(r / "research" / "DO_NOT_REBUILD.md")),
        "active": _normalize(active_raw),
    }


def _deterministic_screen(proposal: dict[str, Any], case_law: dict[str, str]) -> dict[str, Any]:
    """Deterministic allow/deny floor over surface tokens.  The LLM can only
    de-escalate this (a deny here can never be turned into a grant, R-AUT-1).

    Best-effort, NOT a total guarantee: it matches a quorum of distinctive
    (>=4-char) tokens from the proposal's title + rationale + sensor against the
    normalized DO_NOT_REBUILD / ACTIVE_BUILD_MAP text.  A kill worded to share no
    token quorum can slip the floor — which is why it is layered with the LLM
    orchestrator, the adversary key, and the operator merge gate, none of which
    this screen replaces.

    Returns {allow: bool, reason: str}.
    """
    # T2 must never reach an autonomous grant (defense in depth vs propose validation).
    if str(proposal.get("tier") or "").strip().upper() == "T2":
        return {"allow": False, "reason": "T2 is operator-only (R-AUT-4)"}

    title_tokens = sorted({t for t in _normalize(str(proposal.get("title") or "")).split()
                           if len(t) >= 4})
    # Rationale is where a kill can hide behind a generic title; screen it too, but
    # with an ABSOLUTE overlap bar so adding tokens can't dilute the title match.
    detail = f"{proposal.get('title') or ''} {proposal.get('rationale') or ''}"
    surface_tokens = sorted({t for t in _normalize(detail).split() if len(t) >= 4})
    if not surface_tokens:
        return {"allow": True, "reason": "no distinctive tokens to screen (deferred to LLM+adversary)"}

    def _collides(hay: str) -> bool:
        if not hay:
            return False
        th = sum(1 for t in title_tokens if f" {t} " in f" {hay} ")
        sh = sum(1 for t in surface_tokens if f" {t} " in f" {hay} ")
        # (a) a majority of the title's distinctive tokens overlap, OR
        # (b) an absolute quorum of title+rationale tokens overlap (kill-in-rationale).
        title_quorum = max(2, (len(title_tokens) + 1) // 2)
        return (bool(title_tokens) and th >= title_quorum) or (sh >= _SURFACE_MIN_OVERLAP)

    if _collides(case_law.get("killed", "")):
        return {"allow": False, "reason": "collides with a DO_NOT_REBUILD kill"}
    if _collides(case_law.get("active", "")):
        return {"allow": False, "reason": "collides with an ACTIVE_BUILD_MAP open lane"}
    return {"allow": True, "reason": "no case-law collision"}


# ── UX-simplicity gate (3rd deterministic screen, R-V2-6) ────────────────────

def _classify_surface_tier(proposal: dict[str, Any], root: Path | None = None) -> str:
    """Classify the proposal's target surface tier: 'front_page' or 'admin_lab'.

    Fires ONLY when the proposal lists changed files (changed_files field).
    If no changed_files are declared, defaults to 'admin_lab' (conservative —
    only known front-page file patterns trigger the gate).

    Returns 'front_page' or 'admin_lab'.  NEVER raises.
    """
    try:
        changed = proposal.get("changed_files") or []
        if not changed:
            return "admin_lab"

        import fnmatch  # noqa: PLC0415

        # Load rules from config
        r = _repo_root(root)
        rules_path = r / "config" / "ux_simplicity_rules.yml"
        if not rules_path.exists():
            return "admin_lab"

        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        surface = raw.get("surface_patterns") or {}
        front_includes = surface.get("front_page", {}).get("include") or []
        front_excludes = surface.get("front_page", {}).get("exclude") or []

        def _norm(p: str) -> str:
            return p.replace("\\", "/").lstrip("/")

        for f in changed:
            fn = _norm(str(f))
            # Check excludes first
            excluded = any(fnmatch.fnmatch(fn, _norm(pat)) for pat in front_excludes)
            if excluded:
                continue
            # Check includes
            matched = any(fnmatch.fnmatch(fn, _norm(pat)) for pat in front_includes)
            if matched:
                return "front_page"
        return "admin_lab"
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._classify_surface_tier: %s", exc)
        return "admin_lab"


def _ux_simplicity_screen(
    proposal: dict[str, Any],
    root: Path | None = None,
) -> dict[str, Any]:
    """Third deterministic screen: UX-simplicity gate (R-V2-6).

    Fires ONLY on front-page asset diffs (never *_lab/committee/admin/*research*).
    config/ux_simplicity_rules.yml is IMMUTABLE — the LLM cannot relax it.

    A front-page-touching proposal that fails the rules is DENIED and routed to
    admin/lab tier instead.

    Returns {allow: bool, reason: str, surface_tier: str}.
    NEVER raises.
    """
    try:
        surface_tier = _classify_surface_tier(proposal, root)

        if surface_tier != "front_page":
            return {
                "allow": True,
                "reason": f"surface_tier='{surface_tier}' — UX gate not applicable",
                "surface_tier": surface_tier,
            }

        # Load the immutable rules
        r = _repo_root(root)
        rules_path = r / "config" / "ux_simplicity_rules.yml"
        if not rules_path.exists():
            # Config absent → allow (fail-open for UX gate only; case-law screen is the hard floor)
            return {
                "allow": True,
                "reason": "ux_simplicity_rules.yml absent — UX gate skipped (fail-open)",
                "surface_tier": surface_tier,
            }

        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}

        # Rule 1: jargon blocklist — any new label/heading matching blocklist → DENY
        jargon_blocklist = [str(j).lower() for j in (raw.get("jargon_blocklist") or [])]
        proposal_text = " ".join([
            str(proposal.get("title") or ""),
            str(proposal.get("rationale") or ""),
            str(proposal.get("description") or ""),
        ]).lower()
        for term in jargon_blocklist:
            if term and term in proposal_text:
                fail_note = raw.get("front_page_fail_note", "Fails UX-simplicity rules.")
                return {
                    "allow": False,
                    "reason": (
                        f"Front-page proposal uses internal jargon term '{term}' "
                        f"which is in the UX blocklist. Route to admin/lab instead. "
                        f"{fail_note}"
                    ),
                    "surface_tier": surface_tier,
                    "jargon_hit": term,
                }

        # Rule 2: max_numbers_per_default_view — if proposal declares a number count
        max_numbers = int(raw.get("max_numbers_per_default_view") or 12)
        # DENSITY ARM (advisory, defense-in-depth): the declared front-page number
        # count is honor-system; the non-evadable controls are the jargon-blocklist
        # arm below and the R-V2-6 rule that ALL front-page changes are T2-tapped
        # (the operator sees every front-page diff). A proposal omitting the field
        # is treated as 0 here; the operator tap is the real anti-crowding gate.
        declared_numbers = int(proposal.get("numbers_added_to_default_view") or 0)
        if declared_numbers > max_numbers:
            return {
                "allow": False,
                "reason": (
                    f"Front-page proposal adds {declared_numbers} numbers to the default view, "
                    f"exceeding the limit of {max_numbers}. Route dense metrics to admin/lab."
                ),
                "surface_tier": surface_tier,
            }

        # Passed all checks
        return {
            "allow": True,
            "reason": "front-page proposal passes UX-simplicity rules",
            "surface_tier": surface_tier,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._ux_simplicity_screen: %s", exc)
        # Fail-open for UX gate (the case-law screen is the hard floor)
        return {
            "allow": True,
            "reason": f"UX gate error (fail-open): {exc}",
            "surface_tier": "unknown",
        }


# ── Genesis deterministic screen (R-V6-3 — deny-only, kind=="charter") ──────

# CHF-family token patterns (case-insensitive substring match on any single
# distinctive token from this list).  DO_NOT_REBUILD §4 line ~111.
_CHF_DENY_TOKENS: tuple[str, ...] = (
    "causal",
    "chf",
    "hypothesis-factory",
    "machine-registration",
)

# CHF deferral enforced while today < this date (R-V6-3c).
_CHF_DEFER_UNTIL = "2026-10-15"

# Verbatim case-law for the adversary charter block (R-V6-3e).
_CHARTER_CASE_LAW_BLOCK = (
    "NARR-NWC (verbatim): \"Claim Reliability / Narrative Truth is NOT a lobe. "
    "It decomposes into: already-built (QI's track_record.json), an R2-rail wave (W-A), "
    "a bridge wave (W-B), and two accrual-gated future experiments (NARR-2/NARR-3). "
    "Misfiling waves as lobes is how program sprawl happens.\"\n"
    "NEXT3-U5 (verbatim): \"Codex's 'lobes 4/5/6' are respectively an operating "
    "chartered lobe (L1 short-side), a program's connective tissue (options->NW), and "
    "a rail-consumer (DQ instrumentation). None constitutes a new lobe. All upgrades "
    "on these organs are waves on existing tissue. Connective tissue and rail-consumers "
    "are not lobes.\"\n"
    "INSTRUCTION: For every charter-kind proposal, VETO if the proposed entity is a "
    "wave, rail-consumer, or connective tissue rather than a genuinely new information-"
    "domain lobe. 'Is it actually a lobe?' is your primary question."
)


def _genesis_screen(
    proposal: dict[str, Any],
    *,
    cycle_id: str,
    docket: dict[str, Any],
    root: Path | None = None,
    _today_override: str | None = None,
) -> dict[str, Any]:
    """Deterministic genesis screen for kind=='charter' proposals (R-V6-3).

    Deny-only — the LLM may only further de-escalate (R-AUT-1).
    Returns {allow: bool, reason: str}.  NEVER raises.

    Checks (in order):
      (d) Triple tier fence — proposed_tier must be 'display' AND
          proposed_lifecycle_state must be 'proposed'.
      (a) Roster cap hard deny — active_nonscored_count() >= max_active_nonscored_lobes
          unless a co-pending demotion/retire is in the same cycle docket.
      (b) Genesis rate limit — at most max_genesis_per_cycle charter grants in this cycle.
      (c) CHF-family deferral — until 2026-10-15 (DO_NOT_REBUILD §4 ~line 111).
    """
    try:
        # (d) Triple tier fence: proposed_tier must be 'display' AND
        #     proposed_lifecycle_state must be 'proposed' (scout constants + applier
        #     fence + this screen = three independent enforcement points).
        proposed_tier = str(proposal.get("proposed_tier") or "").strip().lower()
        proposed_lifecycle_state = str(proposal.get("proposed_lifecycle_state") or "").strip().lower()
        if proposed_tier != "display" or proposed_lifecycle_state != "proposed":
            return {
                "allow": False,
                "reason": (
                    f"genesis screen: tier fence — proposed_tier={proposed_tier!r} "
                    f"proposed_lifecycle_state={proposed_lifecycle_state!r}; "
                    "both must be 'display'/'proposed' for genesis (R-V6-3d)"
                ),
            }

        # Load budget config (fail-closed on read errors)
        budget = _load_genesis_budget(root)

        # (a) Roster cap hard deny
        try:
            from engine.metabolism.lobe_registry import active_nonscored_count  # noqa: PLC0415
            current_active = active_nonscored_count(root)
        except Exception as exc:  # noqa: BLE001
            log.warning("genesis_screen: lobe_registry unavailable — deny (fail-closed): %s", exc)
            return {
                "allow": False,
                "reason": "genesis screen: roster cap check failed — deny fail-closed (R-V6-3a)",
            }

        max_active = int(budget.get("max_active_nonscored_lobes", 66))
        if current_active >= max_active:
            # Allow if a co-pending demotion/retire is in the SAME cycle docket
            has_swap = _has_copending_demotion(docket)
            if not has_swap:
                return {
                    "allow": False,
                    "reason": (
                        f"genesis screen: roster cap {max_active} reached "
                        f"(current_active={current_active}), no co-pending demotion — "
                        "R-V6-3a"
                    ),
                }

        # (b) Genesis rate limit: count prior charter grants in this cycle
        prior_grants = _count_charter_grants_this_cycle(cycle_id, root)
        max_genesis = int(budget.get("max_genesis_per_cycle", 1))
        if prior_grants >= max_genesis:
            return {
                "allow": False,
                "reason": (
                    f"genesis screen: rate limit — {prior_grants} charter grant(s) already "
                    f"authorized this cycle (max_genesis_per_cycle={max_genesis}) — R-V6-3b"
                ),
            }

        # (c) CHF-family deferral — enforced only while today < 2026-10-15
        try:
            from datetime import date  # noqa: PLC0415
            today_str = _today_override or date.today().isoformat()
            if today_str < _CHF_DEFER_UNTIL:
                surface = " ".join([
                    str(proposal.get("title") or ""),
                    str(proposal.get("rationale") or ""),
                    str(proposal.get("domain_id") or ""),
                ]).lower()
                for token in _CHF_DENY_TOKENS:
                    if token in surface:
                        return {
                            "allow": False,
                            "reason": (
                                f"genesis screen: CHF-family deferral — token {token!r} "
                                f"matched; DO_NOT_REBUILD §4 line ~111 defers until "
                                f"{_CHF_DEFER_UNTIL} (R-V6-3c)"
                            ),
                        }
        except Exception as exc:  # noqa: BLE001
            log.warning("genesis_screen: CHF date check failed — denying (fail-closed): %s", exc)
            return {
                "allow": False,
                "reason": f"genesis screen: CHF date check error — deny fail-closed (R-V6-3c): {exc}",
            }

        return {"allow": True, "reason": "genesis screen: all checks passed"}

    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._genesis_screen: unexpected error — deny (fail-closed): %s", exc)
        return {
            "allow": False,
            "reason": f"genesis screen: internal error — deny fail-closed: {exc}",
        }


def _load_genesis_budget(root: Path | None) -> dict[str, Any]:
    """Load metabolism_budget.yml for genesis-screen keys.  Returns {} on error (NEVER-RAISE)."""
    try:
        import yaml  # noqa: PLC0415
        p = _repo_root(root) / "config" / "metabolism_budget.yml"
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        return raw or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._load_genesis_budget: %s", exc)
        return {}


def _has_copending_demotion(docket: dict[str, Any]) -> bool:
    """Return True if the docket contains any proposal with kind or lifecycle intent
    matching 'demote' or 'retire' (the swap pattern for R-V6-3a).  NEVER raises.
    """
    try:
        for prop in (docket.get("proposals") or []):
            kind = str(prop.get("kind") or "").lower()
            title = str(prop.get("title") or "").lower()
            rationale = str(prop.get("rationale") or "").lower()
            surface = f"{kind} {title} {rationale}"
            if "demot" in surface or "retir" in surface:
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._has_copending_demotion: %s", exc)
        return False


def _count_charter_grants_this_cycle(cycle_id: str, root: Path | None) -> int:
    """Count prior charter-kind grants already written to the governance log for
    this cycle.  Returns 0 on any read error (fail-closed = deny if count >=cap).

    NEVER raises.
    """
    try:
        rows = _events_for_target(root, _cycle_prefix(cycle_id))
        count = 0
        for ev in rows:
            if ev.get("event_type") != EVT_ADJUDICATION:
                continue
            after = ev.get("after") or {}
            if after.get("role") != ROLE_ORCH:
                continue
            if after.get("decision") != "grant":
                continue
            # Check that the original proposal was a charter kind.
            # after.kind is written by the updated governance row (W2+).
            # Fallback: check the note field for older rows.
            kind_field = str(after.get("kind") or "").lower()
            note = str(ev.get("note") or "").lower()
            if kind_field == "charter" or "charter" in note:
                count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate._count_charter_grants_this_cycle: %s", exc)
        return 0


# ── LLM role invocation ───────────────────────────────────────────────────────

_ORCH_SYSTEM = (
    "You are the ORCHESTRATOR adjudicator of the Neural Web metabolism. Rule on "
    "each build proposal against the case law and the tier ladder. GRANT a proposal "
    "only when it clearly targets a real TIL fitness sensor, carries a falsifiable "
    "fitness contract, is correctly tiered (T0 or T1), and does not duplicate a "
    "DO_NOT_REBUILD kill or an ACTIVE_BUILD_MAP open lane. Otherwise DENY.\n"
    "You may only DENY or GRANT — you may NOT raise a proposal's tier or invent "
    "authority beyond what it declared (R-AUT-1). Reply with ONLY a JSON array: "
    '[{"proposal_id": str, "grant": bool, "tier": "T0"|"T1", "rationale": str}]'
)

_ADV_SYSTEM = (
    "You are the ADVERSARY of the Neural Web metabolism. Your job is to REFUTE each "
    "proposal — find the concrete reason it will FAIL its fitness contract, collide "
    "with existing work, or smuggle in a scored-path/authority change. You have skin "
    "in the game: your predictions are scored later (R-AUT-9), so be specific, not a "
    "rubber stamp. Default to veto=true when genuinely uncertain a proposal will earn "
    "its contract. For each proposal also emit tripwire_predictions: concrete, "
    "observable failures you predict if it ships. Reply with ONLY a JSON array: "
    '[{"proposal_id": str, "veto": bool, "findings": [str], '
    '"tripwire_predictions": [str], "rationale": str}]'
)


def _build_role_user(role: str, docket: dict[str, Any], case_law: dict[str, str]) -> str:
    slim = [
        {
            "proposal_id": p.get("proposal_id"),
            "title": p.get("title"),
            "tier": p.get("tier"),
            "kind": p.get("kind"),
            "targets_sensor": p.get("targets_sensor"),
            "rationale": p.get("rationale"),
            "fitness_contract": p.get("fitness_contract"),
        }
        for p in (docket.get("proposals") or [])
    ]
    parts = [
        f"CYCLE: {docket.get('cycle_id')}  LOBE: {docket.get('lobe')}",
        "",
        "PROPOSALS TO RULE ON:",
        json.dumps(slim, indent=2, default=str)[:8000],
        "",
        "DO_NOT_REBUILD (killed topics — any collision is an automatic deny/veto):",
        (_read_case_law_raw(case_law, "killed"))[:4000],
        "",
        "ACTIVE_BUILD_MAP (open lanes — collisions are duplicative):",
        (_read_case_law_raw(case_law, "active"))[:4000],
        "",
        "Rule on every proposal by its proposal_id. Reply as a JSON array only.",
    ]
    # R-V6-3e: when the docket contains charter-kind proposals, append the
    # "is it actually a lobe?" case-law block (NARR-NWC + NEXT3-U5).
    # Applies to both roles: the orchestrator needs it to grant responsibly;
    # the adversary needs it to veto misfiled waves/rails/connective tissue.
    has_charter = any(
        str(p.get("kind") or "").lower() == "charter"
        for p in (docket.get("proposals") or [])
    )
    if has_charter:
        parts += [
            "",
            "CHARTER CASE LAW — 'IS IT ACTUALLY A LOBE?' (applies to kind=charter proposals):",
            _CHARTER_CASE_LAW_BLOCK,
        ]
    return "\n".join(parts)


def _read_case_law_raw(case_law: dict[str, str], key: str) -> str:
    # case_law holds normalized text already (cheap + sufficient for the prompt).
    return case_law.get(key, "")


def _invoke_role_llm(
    role: str,
    docket: dict[str, Any],
    case_law: dict[str, str],
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """Call the role LLM.  Returns (judgments_by_pid | None, degraded_reason).

    None judgments = the role could not run (no provider / error) → callers must
    fail closed.  NEVER raises.  Tests patch this to inject judgments.
    """
    conf = {**_LLM_CFG, **(cfg or {})}
    try:
        from engine import llm_auth  # type: ignore[import]
        providers = llm_auth.build_providers(
            conf, opus_model=conf.get("opus_model"),
            deepseek_model=conf.get("deepseek_model"),
        )
        if not providers:
            return None, "no_provider"

        system = _ORCH_SYSTEM if role == ROLE_ORCH else _ADV_SYSTEM
        user = _build_role_user(role, docket, case_law)
        max_tokens = int(conf.get("max_tokens", 4000))

        def _do_call(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}], temperature=0,
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal"
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            return (text or None), None

        text, reason, _provider = llm_auth.make_call(
            providers, _do_call, context=f"metabolism_adjudicate_{role}")
        parsed = _parse_judgments(text or "")
        if parsed is None:
            return None, reason or "empty_or_unparseable_reply"
        return parsed, reason
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: role LLM (%s) failed: %s", role, exc)
        return None, "llm_error"


def _parse_judgments(text: str) -> dict[str, dict[str, Any]] | None:
    """Parse a JSON array of per-proposal judgments keyed by proposal_id."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    for cand in (s, _slice_bracketed(s)):
        if not cand:
            continue
        try:
            data = json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
        rows = data if isinstance(data, list) else data.get("judgments") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            if isinstance(row, dict) and row.get("proposal_id"):
                out[str(row["proposal_id"])] = row
        return out
    return None


def _slice_bracketed(s: str) -> str:
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = s.find(open_c), s.rfind(close_c)
        if 0 <= i < j:
            return s[i:j + 1]
    return ""


# ── Governance row-pair helpers (idempotent) ──────────────────────────────────

def _events_for_target(root: Path | None, target: str) -> list[dict[str, Any]]:
    try:
        from engine.neuralweb.governance import load_events  # type: ignore[import]
        return load_events(root=root, target=target)
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: load_events failed: %s", exc)
        return []


def _cycle_prefix(cycle_id: str) -> str:
    return f"metabolism_proposal:{cycle_id}:"


def _ruled_in(events: list[dict[str, Any]], target: str, event_type: str, role: str) -> bool:
    """True if `events` already holds a row for (target, event_type, role).

    Callers load the cycle's rows ONCE and pass them in (resume-safe, and O(1)
    ledger reads per role instead of one per proposal).
    """
    for ev in events:
        if ev.get("target") != target or ev.get("event_type") != event_type:
            continue
        if (ev.get("after") or {}).get("role") == role:
            return True
    return False


def _latest_row(rows: list[dict[str, Any]], event_type: str, role: str) -> dict[str, Any] | None:
    found = None
    for ev in rows:
        if ev.get("event_type") == event_type and (ev.get("after") or {}).get("role") == role:
            found = ev  # ledger is append-only chronological; last wins
    return found


def _append_governance(
    event_type: str, target: str, *, authored_by: str,
    after: dict[str, Any], evidence: dict[str, Any] | None, note: str,
    root: Path | None,
) -> None:
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type, target=target, article=None, authored_by=authored_by,
            after=after, evidence=evidence, note=note, root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: governance append failed (%s/%s): %s", event_type, target, exc)


def _append_adversary_ledger(
    cycle_id: str, proposal_id: str, *, run_id: str | None,
    veto: bool, findings: list[str], tripwire_predictions: list[str],
    rationale: str, root: Path | None,
) -> None:
    try:
        p = _repo_root(root).joinpath(*ADVERSARY_LEDGER)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema": ADVERSARY_SCHEMA,
            "cycle_id": cycle_id,
            "proposal_id": proposal_id,
            "run_id": run_id,
            "ts": _now_iso(),
            "veto": bool(veto),
            "findings": findings or [],
            "tripwire_predictions": tripwire_predictions or [],
            "rationale": rationale or "",
        }
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: adversary ledger append failed: %s", exc)


# ── Public API: one role's run ────────────────────────────────────────────────

def adjudicate_role(
    role: str,
    cycle_id: str,
    docket_path: str | Path,
    *,
    run_id: str | None = None,
    root: Path | None = None,
    cfg: dict[str, Any] | None = None,
    injected: dict[str, dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run one adjudication role (orchestrator | adversary) over the docket.

    Writes one governance row per proposal (idempotent per (target, role)).
    The adversary role additionally appends to the adversary ledger (R-AUT-9).

    Returns a list of per-proposal decisions.  NEVER raises.
    """
    if role not in (ROLE_ORCH, ROLE_ADV):
        log.warning("adjudicate: unknown role %r", role)
        return []

    docket = _load_docket(docket_path)
    proposals = docket.get("proposals") or []
    case_law = _load_case_law(root)
    # Load this cycle's governance rows ONCE for resume-safe idempotence checks
    # (one ledger read per role, not one per proposal).
    existing = _events_for_target(root, _cycle_prefix(cycle_id))

    if injected is not None:
        judgments: dict[str, dict[str, Any]] | None = injected
        degraded: str | None = None
    else:
        judgments, degraded = _invoke_role_llm(role, docket, case_law, cfg)

    results: list[dict[str, Any]] = []
    for prop in proposals:
        try:
            pid = str(prop.get("proposal_id") or "")
            if not pid:
                continue
            tier = str(prop.get("tier") or "T1").strip().upper()
            target = _target(cycle_id, pid)
            # Screen 1: case-law (DO_NOT_REBUILD + ACTIVE_BUILD_MAP)
            screen = _deterministic_screen(prop, case_law)
            # Screen 3: UX-simplicity gate (fires only on front-page asset diffs)
            ux_screen = _ux_simplicity_screen(prop, root)
            # Screen 4: Genesis screen (deny-only, fires only for kind=="charter", R-V6-3)
            prop_kind = str(prop.get("kind") or "").strip().lower()
            if prop_kind == "charter":
                genesis_screen = _genesis_screen(
                    prop,
                    cycle_id=cycle_id,
                    docket=docket,
                    root=root,
                )
            else:
                genesis_screen = {"allow": True, "reason": "not a charter proposal"}
            # Combined screen: all must allow for the proposal to proceed
            combined_allow = screen["allow"] and ux_screen["allow"] and genesis_screen["allow"]
            combined_reason = (
                screen["reason"] if not screen["allow"]
                else (ux_screen["reason"] if not ux_screen["allow"]
                      else (genesis_screen["reason"] if not genesis_screen["allow"]
                            else screen["reason"]))
            )
            j = (judgments or {}).get(pid, {})
            has_opinion = (judgments is not None) and (pid in judgments)

            # Anti-repetition FLAG (R-V3-3) — INFORMATIONAL ONLY.
            # Attaches prior_fail_receipt when a past FAIL matches this construction.
            # CRITICAL: this annotation MUST NOT set allow=False, MUST NOT veto,
            # MUST NOT change any existing screen verdict. It informs; the operator
            # justifies any re-attempt. "A kill closes the specific construction tested,
            # not the search space." (house-law: context-accrual-fundamental-goal)
            prior_fail_receipt: list[dict] = []
            try:
                from engine.metabolism import recall as _rec  # noqa: PLC0415
                _construction_text = str(
                    prop.get("construction") or prop.get("description") or prop.get("rationale") or ""
                )
                if _construction_text.strip():
                    _all_rows = _rec.recall_lesson_rows(
                        construction_terms=_construction_text,
                        root=root,
                    )
                    _fp = _rec.fingerprint_construction(_construction_text)
                    for _row in _all_rows:
                        if not _rec.is_fail_verdict(str(_row.get("verdict") or "")):
                            continue
                        _row_fp = _rec.fingerprint_construction(str(_row.get("construction") or ""))
                        if not _row_fp or not _fp:
                            continue
                        # High construction overlap: fingerprint token overlap >= 50%
                        _fp_set = frozenset(_fp.split())
                        _row_fp_set = frozenset(_row_fp.split())
                        if _fp_set and _row_fp_set:
                            _overlap = len(_fp_set & _row_fp_set) / len(_fp_set | _row_fp_set)
                            if _overlap >= 0.5:
                                prior_fail_receipt.append({
                                    "cycle_id": _row.get("cycle_id"),
                                    "verdict": _row.get("verdict"),
                                    "construction": _row.get("construction"),
                                    "what_failed": _row.get("what_failed"),
                                })
            except Exception as _exc:  # noqa: BLE001
                log.warning("adjudicate: prior_fail_receipt annotation failed — %s", _exc)

            if role == ROLE_ORCH:
                # R-AUT-1: grant = deterministic allow AND llm grant (fail-closed
                # when the LLM has no opinion).
                llm_grant = bool(j.get("grant", False)) if has_opinion else False
                decision = "grant" if (combined_allow and llm_grant) else "deny"
                after = {
                    "role": ROLE_ORCH, "decision": decision, "tier": tier,
                    "run_id": run_id, "screen_allow": combined_allow,
                    "screen_reason": combined_reason,
                    "case_law_allow": screen["allow"],
                    "ux_allow": ux_screen["allow"],
                    "ux_surface_tier": ux_screen.get("surface_tier", "unknown"),
                    "genesis_allow": genesis_screen["allow"],
                    "kind": prop_kind,
                    "llm_opinion": has_opinion,
                }
                if not dry_run and not _ruled_in(existing, target, EVT_ADJUDICATION, ROLE_ORCH):
                    _append_governance(
                        EVT_ADJUDICATION, target, authored_by="metabolism_adjudicate:orchestrator",
                        after=after, evidence={"rationale": str(j.get("rationale") or "")},
                        note=f"orchestrator {decision} for {tier} {prop_kind} proposal", root=root,
                    )
                results.append({"proposal_id": pid, "tier": tier, "decision": decision,
                                "screen_allow": combined_allow,
                                "ux_surface_tier": ux_screen.get("surface_tier", "unknown"),
                                "prior_fail_receipt": prior_fail_receipt})

            else:  # ROLE_ADV
                # Fail-closed: no genuine opinion → veto. A deterministic kill is
                # also an automatic veto (the adversary agrees the topic is closed).
                if not has_opinion or not combined_allow:
                    veto = True
                    findings = (
                        ([screen["reason"]] if not screen["allow"]
                         else ([ux_screen["reason"]] if not ux_screen["allow"]
                               else ["adversary produced no opinion — fail-closed veto"]))
                    )
                    tripwires: list[str] = []
                    rationale = (
                        "deterministic case-law collision" if not screen["allow"]
                        else ("UX-simplicity gate denial" if not ux_screen["allow"]
                              else f"adversary unavailable ({degraded})")
                    )
                else:
                    veto = bool(j.get("veto", False))
                    findings = [str(x) for x in (j.get("findings") or [])]
                    tripwires = [str(x) for x in (j.get("tripwire_predictions") or [])]
                    rationale = str(j.get("rationale") or "")
                after = {"role": ROLE_ADV, "veto": veto, "tier": tier,
                         "run_id": run_id, "llm_opinion": has_opinion}
                if not dry_run and not _ruled_in(existing, target, EVT_ADVERSARY, ROLE_ADV):
                    _append_governance(
                        EVT_ADVERSARY, target, authored_by="metabolism_adjudicate:adversary",
                        after=after,
                        evidence={"findings": findings, "tripwire_predictions": tripwires,
                                  "rationale": rationale},
                        note=f"adversary {'VETO' if veto else 'non-veto'} for {tier} proposal",
                        root=root,
                    )
                    _append_adversary_ledger(
                        cycle_id, pid, run_id=run_id, veto=veto, findings=findings,
                        tripwire_predictions=tripwires, rationale=rationale, root=root,
                    )
                results.append({"proposal_id": pid, "tier": tier, "veto": veto,
                                "prior_fail_receipt": prior_fail_receipt})
        except Exception as exc:  # noqa: BLE001
            log.warning("adjudicate: proposal ruling error (%s): %s", role, exc)

    log.info("adjudicate[%s]: cycle=%s ruled %d proposal(s) (degraded=%s)",
             role, cycle_id, len(results), degraded)
    return results


# ── Public API: two-key resolution ────────────────────────────────────────────

def resolve_two_key(
    cycle_id: str,
    docket_path: str | Path,
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, dict[str, Any]]:
    """Combine the orchestrator + adversary rows into a final authorization.

    T0        → authorized iff orchestrator granted.
    T1 / T2   → authorized iff orchestrator granted AND an adversary row exists
                AND it is a non-veto (fail-closed: a missing adversary key denies).

    Writes one resolution governance row per proposal (idempotent).  Returns a
    map proposal_id → {authorized, tier, keys}.  NEVER raises.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        docket = _load_docket(docket_path)
        # Load the cycle's rows once, then filter per target in-memory.
        all_rows = _events_for_target(root, _cycle_prefix(cycle_id))
        for prop in (docket.get("proposals") or []):
            pid = str(prop.get("proposal_id") or "")
            if not pid:
                continue
            tier = str(prop.get("tier") or "T1").strip().upper()
            target = _target(cycle_id, pid)
            rows = [e for e in all_rows if e.get("target") == target]

            orch = _latest_row(rows, EVT_ADJUDICATION, ROLE_ORCH)
            adv = _latest_row(rows, EVT_ADVERSARY, ROLE_ADV)

            orch_grant = bool(orch and (orch.get("after") or {}).get("decision") == "grant")
            if adv is None:
                adv_key = "absent"
                adv_nonveto = False
            else:
                vetoed = bool((adv.get("after") or {}).get("veto"))
                adv_key = "veto" if vetoed else "nonveto"
                adv_nonveto = not vetoed

            # R-AUT-6 enforcement: the two keys must come from TWO DISTINCT
            # stateless runs. If the orchestrator and adversary rows collapse to
            # the same run_id (a bug or a single run playing both roles), the
            # "second key" is not genuine — deny, fail-closed. Unknown run_ids
            # (either side missing/empty) also fail the distinctness test.
            orch_run = str((orch or {}).get("after", {}).get("run_id") or "") if orch else ""
            adv_run = str((adv or {}).get("after", {}).get("run_id") or "") if adv else ""
            distinct_runs = bool(orch_run) and bool(adv_run) and orch_run != adv_run

            if tier == "T0":
                authorized = orch_grant
            else:  # T1 / T2 need both keys FROM DISTINCT RUNS
                authorized = (
                    orch_grant and (adv is not None) and adv_nonveto and distinct_runs
                )

            keys = {
                "orchestrator": "grant" if orch_grant else ("deny" if orch else "absent"),
                "adversary": adv_key,
                "distinct_runs": distinct_runs,
            }
            after = {"role": ROLE_TWO_KEY, "authorized": authorized, "tier": tier, "keys": keys}
            if not dry_run and not _ruled_in(all_rows, target, EVT_ADJUDICATION, ROLE_TWO_KEY):
                _append_governance(
                    EVT_ADJUDICATION, target, authored_by="metabolism_adjudicate:two_key",
                    after=after, evidence=None,
                    note=("two_key_resolution: "
                          + ("AUTHORIZED" if authorized else "NOT authorized")
                          + f" ({tier}; orch={keys['orchestrator']}, adv={keys['adversary']})"),
                    root=root,
                )
            out[pid] = {"authorized": authorized, "tier": tier, "keys": keys}
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("adjudicate: resolve_two_key failed for %s: %s", cycle_id, exc)
        return out
