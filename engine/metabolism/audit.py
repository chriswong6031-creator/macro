"""engine.metabolism.audit — PR AUDIT stage for Metabolism V7 (R-V7-1..6).

Deterministic containment re-check + adversarial Opus code review BEFORE merge.
The merge lane's _audit_approved() gate reads the record written here.

AUTHORITY MODEL (R-V7-1, R-V7-2)
-----------------------------------
1. DETERMINISTIC pre-screen runs first; it is FAIL-CLOSED.
   (a) Foreign-file containment: every changed file must be in the proposal's
       declared target_files OR under data/metabolism/.
   (b) Immutable re-check: no IMMUTABLE_PATTERNS file touched.
   (c) Diff-budget: changed lines must not exceed audit_max_diff_lines (config).
   Any deterministic failure → reject; NO LLM call.

2. LLM ADVERSARIAL review (only if deterministic passes):
   Opus-pinned via llm_auth waterfall (oauth_pool_lane: metabolism-audit).
   System: adversarial code auditor, default-to-reject, PRODUCTION unattended.
   LLM can only REJECT or approve-within-the-envelope — never override a
   deterministic reject (it is never called then).

3. Approve ONLY iff deterministic_ok=True AND llm_verdict=="approve".
   On any error or LLM unavailability → reject (fail-closed).

OUTPUTS (R-V7-4)
-----------------
- data/metabolism/audit/<pr_number>.json  (the full record)
- governance event  metabolism_audit  in data/neuralweb/governance.jsonl

NEVER-RAISE: any exception → return a reject record.

Called by scripts/metabolism_audit.py (CLI).
Gated by scripts/metabolism_merge._audit_approved() (merge lane step 5.5).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Config constants ──────────────────────────────────────────────────────────

_DEFAULT_MAX_DIFF_LINES = 2000
_AUDIT_DIR = ("data", "metabolism", "audit")

# ── LLM provider config (mirrors adjudicate._LLM_CFG, opus-pinned) ────────────

_LLM_CFG: dict[str, Any] = {
    "provider_order": ["oauth", "anthropic"],
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "oauth_pool_lane": "metabolism-audit",
    "api_key_env": "ANTHROPIC_API_KEY",
    "opus_model": "claude-opus-4-8",
    "max_tokens": 4000,
}

# ── System prompt (adversarial code auditor) ──────────────────────────────────

_AUDIT_SYSTEM = """\
You are an adversarial code auditor for an autonomous system that is about to \
merge a pull-request to PRODUCTION without any human watching.

Your role is to PROTECT production from unsafe, scope-creeping, or incorrect code.

REJECT the pull-request if ANY of the following holds:
  - The diff does MORE than the proposal authorized (scope creep / unannounced additions).
  - The diff does LESS than the proposal required (incomplete / missing fitness contract work).
  - There is a correctness defect — logic error, off-by-one, wrong type, broken control flow.
  - There is a security or data-integrity risk — injection, credential leak, NEVER-RAISE
    violation, unhandled exception that could crash a production lane.
  - Any file is touched that the proposal did not declare.
  - The code diverges from the fitness_contract in any material respect.
  - You are not fully confident this is safe to merge UNATTENDED by a human.

DEFAULT TO REJECT under any uncertainty. The loop can always re-propose; a bad
production merge cannot be easily undone.

Reply ONLY with valid JSON (no markdown fences):
{
  "verdict": "approve" | "reject",
  "confidence": <float 0.0–1.0>,
  "findings": ["<one line per finding>"],
  "rationale": "<brief paragraph explaining your verdict>"
}
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_budget_yml(root: Path | None = None) -> dict[str, Any]:
    """Read config/metabolism_budget.yml; return {} on any error."""
    try:
        import yaml  # type: ignore[import]
        p = _repo_root(root) / "config" / "metabolism_budget.yml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: budget yml read failed: %s", exc)
    return {}


def _audit_max_diff_lines(root: Path | None = None) -> int:
    """Read audit_max_diff_lines from budget yml; default _DEFAULT_MAX_DIFF_LINES."""
    try:
        cfg = _read_budget_yml(root)
        val = cfg.get("audit_max_diff_lines")
        if val is not None:
            return int(val)
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: could not read audit_max_diff_lines: %s", exc)
    return _DEFAULT_MAX_DIFF_LINES


# ── Deterministic pre-screen helpers ──────────────────────────────────────────

def _parse_changed_files_from_diff(diff_text: str) -> list[str]:
    """Extract changed file paths from a unified diff.

    Handles two forms:
      - '+++ b/<path>'   (unified diff header, most common)
      - 'diff --git a/<p> b/<p>'  (git diff header, a fallback)

    Returns deduplicated list; paths are relative (no leading '/').
    NEVER raises.
    """
    try:
        paths: set[str] = set()
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                p = line[6:].strip()
                if p and p != "/dev/null":
                    paths.add(p)
            elif line.startswith("diff --git "):
                # 'diff --git a/<p> b/<p>' — take the b/ side
                parts = line.split(" b/", 1)
                if len(parts) == 2:
                    p = parts[1].strip()
                    if p:
                        paths.add(p)
        return sorted(paths)
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: _parse_changed_files_from_diff failed: %s", exc)
        return []


def _count_diff_lines(diff_text: str) -> int:
    """Count added + removed lines in a unified diff (lines starting +/- excluding headers)."""
    try:
        count = 0
        for line in diff_text.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: _count_diff_lines failed: %s", exc)
        return 0


def _is_allowed_path(path: str, allowed: list[str]) -> bool:
    """Return True if path is in allowed OR under data/metabolism/."""
    norm = path.replace("\\", "/").lstrip("/")
    if norm.startswith("data/metabolism/"):
        return True
    # Normalise allowed paths the same way
    for a in allowed:
        na = (a or "").replace("\\", "/").lstrip("/")
        if norm == na:
            return True
    return False


# ── LLM call helpers ──────────────────────────────────────────────────────────

_DIFF_CHAR_BUDGET = 30_000  # chars sent to the LLM; rest noted as truncated


def _build_user_prompt(
    proposal: dict[str, Any],
    diff_text: str,
    immutable_paths: list[str],
) -> str:
    """Build the user-side prompt for the auditor."""
    # Truncate diff if too large
    truncated = False
    if len(diff_text) > _DIFF_CHAR_BUDGET:
        diff_text = diff_text[:_DIFF_CHAR_BUDGET]
        truncated = True

    title = proposal.get("title") or "(untitled)"
    rationale = proposal.get("rationale") or ""
    target_files = proposal.get("target_files") or []
    fitness_contract = proposal.get("fitness_contract") or {}

    tf_str = "\n".join(f"  - {f}" for f in target_files) or "  (none declared)"
    fc_str = json.dumps(fitness_contract, indent=2) if fitness_contract else "(none)"
    trunc_note = (
        f"\n[NOTE: diff was truncated to {_DIFF_CHAR_BUDGET} chars; full diff larger]"
        if truncated else ""
    )
    immutable_str = "\n".join(f"  - {p}" for p in immutable_paths) or "  (see check_self_mod_fence.IMMUTABLE_PATTERNS)"

    return (
        f"=== PROPOSAL ===\n"
        f"Title: {title}\n"
        f"Rationale: {rationale}\n\n"
        f"Declared target_files:\n{tf_str}\n\n"
        f"Fitness contract:\n{fc_str}\n\n"
        f"=== IMMUTABLE paths (must NEVER be touched by the loop) ===\n"
        f"{immutable_str}\n\n"
        f"=== DIFF ==={trunc_note}\n"
        f"{diff_text}\n"
    )


def _parse_llm_reply(text: str) -> dict[str, Any] | None:
    """Parse auditor JSON reply robustly (mirrors adjudicate._parse_judgments style)."""
    if not text:
        return None
    s = text.strip()
    # Strip markdown fences
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    # Try raw then bracketed
    for cand in (s, _slice_braced(s)):
        if not cand:
            continue
        try:
            data = json.loads(cand)
            if isinstance(data, dict) and "verdict" in data:
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def _slice_braced(s: str) -> str:
    i, j = s.find("{"), s.rfind("}")
    if 0 <= i < j:
        return s[i:j + 1]
    return ""


def _call_llm_auditor(
    proposal: dict[str, Any],
    diff_text: str,
    immutable_paths: list[str],
) -> tuple[str | None, float | None, list[str], str, str | None]:
    """Call the opus auditor.

    Returns (llm_verdict, confidence, findings, rationale, error_reason).
    On any failure → verdict None, error_reason set.
    NEVER raises.
    """
    try:
        from engine import llm_auth  # type: ignore[import]

        providers = llm_auth.build_providers(
            _LLM_CFG,
            opus_model=_LLM_CFG.get("opus_model"),
        )
        if not providers:
            return None, None, [], "", "no_provider"

        user_content = _build_user_prompt(proposal, diff_text, immutable_paths)
        max_tokens = int(_LLM_CFG.get("max_tokens", 4000))

        def _do_call(client: Any, model: str) -> tuple[str | None, str | None]:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_AUDIT_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
                temperature=0,
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal"
            text_out = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return (text_out or None), None

        text, reason, _provider = llm_auth.make_call(
            providers, _do_call, context="metabolism_audit"
        )
        if not text:
            return None, None, [], "", reason or "empty_reply"

        parsed = _parse_llm_reply(text)
        if parsed is None:
            return None, None, [], "", "llm_error"

        verdict = str(parsed.get("verdict") or "reject").lower()
        if verdict not in ("approve", "reject"):
            verdict = "reject"
        confidence = float(parsed.get("confidence") or 0.0)
        findings = [str(f) for f in (parsed.get("findings") or [])]
        rationale = str(parsed.get("rationale") or "")
        return verdict, confidence, findings, rationale, None

    except Exception as exc:  # noqa: BLE001
        log.warning("audit: LLM auditor call failed: %s", exc)
        return None, None, [], "", "llm_error"


# ── Persistence helpers ────────────────────────────────────────────────────────

def _write_audit_record(record: dict[str, Any], root: Path | None = None) -> None:
    """Write data/metabolism/audit/<pr_number>.json. NEVER raises."""
    try:
        pr_number = record.get("pr_number")
        r = _repo_root(root)
        audit_dir = r.joinpath(*_AUDIT_DIR)
        audit_dir.mkdir(parents=True, exist_ok=True)
        path = audit_dir / f"{pr_number}.json"
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: write_audit_record failed for PR %s: %s",
                    record.get("pr_number"), exc)


def _append_governance_event(record: dict[str, Any], root: Path | None = None) -> None:
    """Append governance metabolism_audit event. NEVER raises."""
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        pr_number = record.get("pr_number")
        rationale = str(record.get("rationale") or "")[:200]
        evidence: dict[str, Any] = {
            "head_sha": record.get("head_sha"),
            "verdict": record.get("verdict"),
            "deterministic_ok": record.get("deterministic_ok"),
            "llm_verdict": record.get("llm_verdict"),
            "confidence": record.get("confidence"),
        }
        append_event(
            "metabolism_audit",
            target=f"metabolism_pr:{pr_number}",
            article=None,
            authored_by="metabolism_audit",
            evidence=evidence,
            note=rationale,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("audit: governance append failed for PR %s: %s",
                    record.get("pr_number"), exc)


# ── Public API ─────────────────────────────────────────────────────────────────

def audit_pr(
    pr_number: int,
    proposal: dict[str, Any],
    diff_text: str,
    head_sha: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Audit a build-lane PR.

    Parameters
    ----------
    pr_number : int
        The GitHub PR number.
    proposal : dict
        The proposal dict from the cycle docket (must contain target_files,
        fitness_contract, title, rationale).
    diff_text : str
        The full unified diff of the PR (from `gh pr diff <n> --patch`).
    head_sha : str
        The current HEAD SHA of the PR branch (stamped into the record so the
        merge lane can detect post-audit pushes).
    root : Path | None
        Repo root for file I/O (None = auto-detect).

    Returns
    -------
    dict with keys:
        pr_number, head_sha, verdict ("approve"|"reject"),
        deterministic_ok (bool), llm_verdict (str|None),
        confidence (float|None), findings (list[str]),
        rationale (str), ts (ISO string).

    NEVER raises — any exception → reject record.
    """
    record: dict[str, Any] = {
        "schema": "metabolism.audit.v1",
        "pr_number": pr_number,
        "head_sha": head_sha,
        "verdict": "reject",
        "deterministic_ok": False,
        "llm_verdict": None,
        "confidence": None,
        "findings": [],
        "rationale": "audit not completed (exception or unknown error)",
        "ts": _now_iso(),
    }

    try:
        target_files: list[str] = [
            str(f) for f in (proposal.get("target_files") or []) if f is not None
        ]
        findings: list[str] = []

        # ── DETERMINISTIC PRE-SCREEN ──────────────────────────────────────────

        changed_files = _parse_changed_files_from_diff(diff_text)

        # (a) Foreign-file containment
        foreign: list[str] = [
            f for f in changed_files if not _is_allowed_path(f, target_files)
        ]
        for f in foreign:
            findings.append(f"foreign_file:{f}")

        # (b) Immutable re-check (reuse check_self_mod_fence._matches_immutable)
        try:
            from scripts.check_self_mod_fence import (  # type: ignore[import]
                IMMUTABLE_PATTERNS, _matches_immutable,
            )
            immutable_hits = [f for f in changed_files if _matches_immutable(f)]
            for f in immutable_hits:
                findings.append(f"immutable_touch:{f}")
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: immutable check import failed: %s", exc)
            # Fail-closed: treat as a reject finding
            findings.append("immutable_check_error:import_failed")
            IMMUTABLE_PATTERNS = []

        # (c) Diff-budget
        diff_line_count = _count_diff_lines(diff_text)
        max_lines = _audit_max_diff_lines(root)
        if diff_line_count > max_lines:
            findings.append(f"diff_too_large:{diff_line_count}")

        deterministic_ok = len(findings) == 0
        record["deterministic_ok"] = deterministic_ok
        record["findings"] = list(findings)

        if not deterministic_ok:
            record["verdict"] = "reject"
            record["rationale"] = (
                f"Deterministic pre-screen FAILED ({len(findings)} finding(s)): "
                + "; ".join(findings[:5])
            )
            _write_audit_record(record, root)
            _append_governance_event(record, root)
            return record

        # ── LLM ADVERSARIAL REVIEW ────────────────────────────────────────────

        immutable_list = list(IMMUTABLE_PATTERNS) if IMMUTABLE_PATTERNS else []

        llm_verdict, confidence, llm_findings, llm_rationale, error_reason = (
            _call_llm_auditor(proposal, diff_text, immutable_list)
        )

        # Fail-closed: if LLM failed, treat as reject
        if llm_verdict is None or error_reason:
            record["verdict"] = "reject"
            record["llm_verdict"] = error_reason or "no_provider"
            record["confidence"] = None
            record["findings"] = list(findings) + llm_findings
            record["rationale"] = (
                f"LLM auditor unavailable or failed ({error_reason!r}) — "
                "fail-closed: REJECT"
            )
            _write_audit_record(record, root)
            _append_governance_event(record, root)
            return record

        record["llm_verdict"] = llm_verdict
        record["confidence"] = confidence
        record["findings"] = list(findings) + llm_findings
        record["rationale"] = llm_rationale

        # Approve only iff deterministic passed AND LLM approved
        if deterministic_ok and llm_verdict == "approve":
            record["verdict"] = "approve"
        else:
            record["verdict"] = "reject"
            if not record["rationale"]:
                record["rationale"] = "LLM auditor rejected (see findings)"

        _write_audit_record(record, root)
        _append_governance_event(record, root)
        return record

    except Exception as exc:  # noqa: BLE001
        log.warning("audit.audit_pr: unexpected exception for PR %s: %s", pr_number, exc)
        record["verdict"] = "reject"
        record["rationale"] = f"audit_pr exception (fail-closed): {exc}"
        record["ts"] = _now_iso()
        try:
            _write_audit_record(record, root)
            _append_governance_event(record, root)
        except Exception:  # noqa: BLE001
            pass
        return record
