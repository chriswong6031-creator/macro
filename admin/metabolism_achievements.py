"""admin/metabolism_achievements.py — Per-cycle achievements rollup for the Metabolism loop.

Composes a structured per-cycle achievements view from:
  - data/metabolism/journal/cycle-*.json  (incl. new achievements key when present)
  - data/metabolism/verify/*.json
  - data/metabolism/audit/*.json
  - GitHub PR list (metabolism/ head_refs)

PUBLIC API
----------
achievements(limit_cycles=20, root=None) -> dict

  Returns:
    {
      "cycles": [
        {
          "cycle_id": str,
          "started_at": str | None,
          "headline_plain": str,
          "blocker_plain": str | None,
          "lobes": {lobe: {proposed: n, authorized: n, denied: n, never_ruled: n, prs: [...]}},
          "proposals": [...],   # merged view: proposals + verdicts + builds
          "stages": {
            "agenda":     {status, note_plain},
            "propose":    {status, note_plain},
            "adjudicate": {status, note_plain},
            "build":      {status, note_plain},
          },
        },
        ...
      ],
      "generated_at": str,
    }

FAIL-SOFT CONTRACT
------------------
Every source reader is wrapped in try/except. A missing directory, corrupt
file, or unreadable record is silently skipped — never fatal. achievements()
never raises. A missing root returns an empty cycles list.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import github_api
from .paths import ROOT

log = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Timestamp helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(ts_str: Any) -> datetime:
    """Parse ISO-8601 timestamp, always returning an aware datetime.

    Returns _EPOCH on any parse failure — never raises.
    """
    try:
        s = str(ts_str or "").strip()
        if not s:
            return _EPOCH
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return _EPOCH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Stage note helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stage_summary(stages: dict, stage_name: str) -> dict[str, str | None]:
    """Extract {status, note_plain} for a named stage from the journal stages dict.

    Looks for any key matching stage_name as prefix (e.g. "adjudicate" matches
    "adjudicate_orchestrator", "adjudicate_adversary", "adjudicate_resolve").
    Returns the latest-finished stage record.  Never raises.
    """
    try:
        best: dict[str, Any] = {}
        best_ts = _EPOCH
        for key, rec in (stages or {}).items():
            if not key.startswith(stage_name):
                continue
            rec_ts = _parse_ts(rec.get("finished_at") or rec.get("started_at") or "")
            if rec_ts >= best_ts:
                best_ts = rec_ts
                best = rec
        status = best.get("status") or "pending"
        raw_note = best.get("note") or ""
        note_plain = _plain_note(raw_note)
        return {"status": status, "note_plain": note_plain}
    except Exception:  # noqa: BLE001
        return {"status": "unknown", "note_plain": None}


def _plain_note(raw_note: str) -> str | None:
    """Return a plain-word note from a journal stage note.

    Stage notes may be raw strings like "docket 2 proposal(s); lobe=til; provider=anthropic"
    or JSON blobs (dispatch records).  We extract a human-readable summary.
    Never raises.
    """
    try:
        s = str(raw_note or "").strip()
        if not s:
            return None
        if s.startswith("{"):
            try:
                d = json.loads(s)
                # dispatch record: extract status + proposal_id
                st = str(d.get("status") or "")
                pid = str(d.get("proposal_id") or "")
                if st and pid:
                    return f"{st}: {pid}"[:160]
                if st:
                    return st[:160]
            except Exception:  # noqa: BLE001
                pass
        return s[:160]
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Blocker / headline derivation
# ─────────────────────────────────────────────────────────────────────────────

_RATE_LIMITED_TOKENS = (
    "rate_limited_all", "rate_limited", "429", "529", "usage_limit",
    "quota", "all_keys_cooling", "no_enabled_keys", "key_budget",
    "rate limit", "overloaded",
)

_AUTH_FAIL_TOKENS = (
    "preflight auth failed", "auth_ok=False", "cli_missing",
    "401", "403", "authentication_error", "oauth",
)


def _derive_blocker(journal: dict) -> str | None:
    """Derive a plain-word blocker description from journal stage notes.

    Returns None when no notable blocker is detected.  Never raises.
    """
    try:
        stages = journal.get("stages") or {}
        # Scan all stage notes for degraded/blocker patterns
        for key, rec in stages.items():
            note = str(rec.get("note") or "").lower()
            status = str(rec.get("status") or "").lower()
            if status in ("noop_paused", "failed"):
                for tok in _RATE_LIMITED_TOKENS:
                    if tok in note:
                        return "all AI keys were rate-limited or cooling"
                for tok in _AUTH_FAIL_TOKENS:
                    if tok in note:
                        return "AI key auth failed"
                if "paused" in note or "kill switch" in note or "autonomy" in note:
                    return "loop paused by operator (AUTONOMY_PAUSED)"
        return None
    except Exception:  # noqa: BLE001
        return None


def _derive_headline(journal: dict, proposals: list[dict], verdicts: list[dict],
                     builds: list[dict]) -> str:
    """Derive a plain-word headline for the cycle.

    Examples:
      "1 proposal drafted, denied by the safety screen"
      "5 proposals drafted — never adjudicated"
      "Nothing this cycle — all AI keys were rate-limited"
      "2 proposals authorized, 1 PR opened"

    Never raises.
    """
    try:
        n_proposals = len(proposals)
        n_authorized = sum(1 for v in verdicts if v.get("decision") == "authorized")
        n_denied = sum(1 for v in verdicts if v.get("decision") == "denied")
        n_never_ruled = sum(1 for v in verdicts if v.get("decision") == "never_ruled")
        n_builds = sum(1 for b in builds if b.get("status") == "pr_opened")

        if n_proposals == 0:
            # No proposals — try to explain why
            blocker = _derive_blocker(journal)
            if blocker:
                return f"Nothing this cycle — {blocker}"
            status = journal.get("status") or "unknown"
            stage = journal.get("stage") or ""
            if status in ("noop_paused",):
                return "Nothing this cycle — loop paused"
            if "agenda" in stage:
                return "Nothing this cycle — agenda stage had no output"
            return "Nothing this cycle"

        prop_word = "proposal" if n_proposals == 1 else "proposals"

        if n_authorized > 0 and n_builds > 0:
            pr_word = "PR" if n_builds == 1 else "PRs"
            return f"{n_authorized} {prop_word} authorized, {n_builds} {pr_word} opened"

        if n_authorized > 0:
            return f"{n_authorized} {prop_word} authorized, awaiting build"

        if n_never_ruled > 0 and n_denied == 0:
            return f"{n_proposals} {prop_word} drafted — never adjudicated"

        if n_denied > 0:
            # Find the most common denial reason
            reasons = [v.get("reason_plain") or "" for v in verdicts if v.get("decision") == "denied"]
            if reasons:
                # Collapse to the most common reason
                reason_counts: dict[str, int] = {}
                for r in reasons:
                    reason_counts[r] = reason_counts.get(r, 0) + 1
                top_reason = max(reason_counts, key=lambda k: reason_counts[k])
                if n_proposals == 1:
                    return f"1 proposal drafted, denied — {top_reason}"
                return f"{n_proposals} {prop_word} drafted, denied — {top_reason}"

        blocker = _derive_blocker(journal)
        if blocker:
            return f"{n_proposals} {prop_word} drafted; stalled — {blocker}"

        return f"{n_proposals} {prop_word} drafted"
    except Exception:  # noqa: BLE001
        return "cycle summary unavailable"


# ─────────────────────────────────────────────────────────────────────────────
# Lobe rollup
# ─────────────────────────────────────────────────────────────────────────────

def _build_lobe_rollup(
    proposals: list[dict],
    verdicts: list[dict],
    builds: list[dict],
) -> dict[str, dict]:
    """Build per-lobe {proposed, authorized, denied, never_ruled, prs} rollup.

    Never raises.
    """
    try:
        verdict_by_id: dict[str, dict] = {v.get("id"): v for v in verdicts if v.get("id")}
        build_by_id: dict[str, list] = {}
        for b in builds:
            bid = b.get("id") or ""
            build_by_id.setdefault(bid, []).append(b)

        lobe_map: dict[str, dict] = {}
        for prop in proposals:
            lobe = str(prop.get("lobe") or "unknown")
            pid = str(prop.get("id") or "")
            if lobe not in lobe_map:
                lobe_map[lobe] = {"proposed": 0, "authorized": 0, "denied": 0,
                                  "never_ruled": 0, "prs": []}
            lobe_map[lobe]["proposed"] += 1
            verdict = verdict_by_id.get(pid, {})
            decision = str(verdict.get("decision") or "never_ruled")
            if decision == "authorized":
                lobe_map[lobe]["authorized"] += 1
            elif decision == "denied":
                lobe_map[lobe]["denied"] += 1
            else:
                lobe_map[lobe]["never_ruled"] += 1
            for b in build_by_id.get(pid, []):
                pr_url = b.get("pr_url")
                if pr_url and pr_url not in lobe_map[lobe]["prs"]:
                    lobe_map[lobe]["prs"].append(pr_url)
        return lobe_map
    except Exception:  # noqa: BLE001
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Merged proposal view
# ─────────────────────────────────────────────────────────────────────────────

def _merge_proposals_view(
    proposals: list[dict],
    verdicts: list[dict],
    builds: list[dict],
) -> list[dict]:
    """Merge proposals + verdicts + builds into one per-proposal record.

    Never raises.
    """
    try:
        verdict_by_id: dict[str, dict] = {v.get("id"): v for v in verdicts if v.get("id")}
        builds_by_id: dict[str, list] = {}
        for b in builds:
            bid = b.get("id") or ""
            builds_by_id.setdefault(bid, []).append(b)

        merged: list[dict] = []
        for prop in proposals:
            pid = str(prop.get("id") or "")
            v = verdict_by_id.get(pid, {})
            b_list = builds_by_id.get(pid, [])
            merged.append({
                "id": pid,
                "lobe": prop.get("lobe"),
                "kind": prop.get("kind"),
                "tier": prop.get("tier"),
                "title": prop.get("title"),
                "proposed_at": prop.get("proposed_at"),
                "decision": v.get("decision"),
                "reason_plain": v.get("reason_plain"),
                "adjudicated_at": v.get("adjudicated_at"),
                "builds": b_list,
            })
        return merged
    except Exception:  # noqa: BLE001
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PR source (fail-soft)
# ─────────────────────────────────────────────────────────────────────────────

def _load_prs_by_cycle() -> dict[str, list[dict]]:
    """Load GitHub PRs grouped by cycle_id extracted from head_ref.

    head_ref pattern: metabolism/build-<lobe>-<cycle_id>-<pid>
    Returns {} on any error.  Never raises.
    """
    try:
        if not github_api.token():
            return {}
        result = github_api.list_prs(per_page=100)
        if not result.get("ok"):
            return {}
        out: dict[str, list[dict]] = {}
        for p in result.get("prs") or []:
            head_ref = str(p.get("head_ref") or "")
            if not head_ref.startswith("metabolism/build-"):
                continue
            # Extract cycle_id: metabolism/build-<lobe>-<cycle_id...>
            # cycle_id format: cycle-YYYY-MM-DD-<hash>
            import re  # noqa: PLC0415
            m = re.search(r"(cycle-\d{4}-\d{2}-\d{2}-[0-9a-f]+)", head_ref)
            if m:
                cid = m.group(1)
                out.setdefault(cid, []).append({
                    "number": p.get("number"),
                    "url": p.get("html_url"),
                    "state": p.get("state"),
                    "draft": p.get("draft"),
                    "head_ref": head_ref,
                    "created_at": p.get("created_at"),
                })
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_achievements._load_prs_by_cycle: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Verify + Audit sources
# ─────────────────────────────────────────────────────────────────────────────

def _load_verify_by_cycle(base: Path) -> dict[str, list[dict]]:
    """Load verify records grouped by cycle_id.  Never raises."""
    out: dict[str, list[dict]] = {}
    try:
        vdir = base / "data" / "metabolism" / "verify"
        if not vdir.exists():
            return out
        for f in vdir.glob("*.json"):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
                cid = str(rec.get("cycle_id") or "")
                if cid:
                    out.setdefault(cid, []).append(rec)
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_achievements._load_verify_by_cycle: %s", exc)
    return out


def _load_audit_by_proposal(base: Path) -> dict[str, dict]:
    """Load audit records keyed by proposal_id.  Never raises."""
    out: dict[str, dict] = {}
    try:
        adir = base / "data" / "metabolism" / "audit"
        if not adir.exists():
            return out
        for f in adir.glob("*.json"):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
                pid = str(rec.get("proposal_id") or "")
                if pid:
                    # Keep most-recent by ts
                    existing = out.get(pid)
                    if existing is None or rec.get("ts", "") >= existing.get("ts", ""):
                        out[pid] = rec
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_achievements._load_audit_by_proposal: %s", exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Core journal reader
# ─────────────────────────────────────────────────────────────────────────────

def _read_cycle_journals(base: Path, limit_cycles: int) -> list[dict]:
    """Read the most recent cycle journals, sorted newest-first.

    Returns a list of raw journal dicts.  Never raises.
    """
    try:
        jdir = base / "data" / "metabolism" / "journal"
        if not jdir.exists():
            return []
        files = sorted(jdir.glob("cycle-*.json"), reverse=True)
        journals = []
        for f in files[:limit_cycles]:
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                journals.append(j)
            except Exception:  # noqa: BLE001
                continue
        return journals
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_achievements._read_cycle_journals: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def achievements(limit_cycles: int = 20, root: Path | None = None) -> dict:
    """Return the metabolism per-cycle achievements rollup.

    Parameters
    ----------
    limit_cycles : int
        Maximum cycles to return.  Clamped to [1, 100].
    root : Path | None
        Repo root.  Uses ROOT from .paths when None.

    Returns
    -------
    dict with keys: cycles, generated_at.  Never raises.
    """
    try:
        limit_cycles = max(1, min(100, int(limit_cycles)))
        base: Path = Path(root) if root is not None else ROOT

        journals = _read_cycle_journals(base, limit_cycles)
        prs_by_cycle = _load_prs_by_cycle()
        verify_by_cycle = _load_verify_by_cycle(base)
        audit_by_proposal = _load_audit_by_proposal(base)

        cycles: list[dict] = []
        for journal in journals:
            try:
                cycle_id = str(journal.get("cycle_id") or "")
                if not cycle_id:
                    continue

                # ── Extract achievements key (FROZEN CONTRACT) ──────────────
                ach = journal.get("achievements") or {}
                proposals: list[dict] = ach.get("proposals") or []
                verdicts: list[dict] = ach.get("verdicts") or []
                builds: list[dict] = ach.get("builds") or []

                # ── Stage summaries ─────────────────────────────────────────
                stages_raw = journal.get("stages") or {}
                stage_summaries: dict[str, dict] = {
                    "agenda":     _stage_summary(stages_raw, "agenda"),
                    "propose":    _stage_summary(stages_raw, "propose"),
                    "adjudicate": _stage_summary(stages_raw, "adjudicate"),
                    "build":      _stage_summary(stages_raw, "build"),
                }

                # ── started_at: first stage started_at ─────────────────────
                started_at: str | None = None
                for rec in stages_raw.values():
                    sa = rec.get("started_at") or ""
                    if sa and (started_at is None or sa < started_at):
                        started_at = sa

                # ── Headline + blocker ──────────────────────────────────────
                blocker_plain = _derive_blocker(journal)
                headline_plain = _derive_headline(journal, proposals, verdicts, builds)

                # ── Lobe rollup ─────────────────────────────────────────────
                lobe_rollup = _build_lobe_rollup(proposals, verdicts, builds)

                # ── Merged proposals view ───────────────────────────────────
                merged_proposals = _merge_proposals_view(proposals, verdicts, builds)

                cycles.append({
                    "cycle_id": cycle_id,
                    "started_at": started_at,
                    "headline_plain": headline_plain,
                    "blocker_plain": blocker_plain,
                    "lobes": lobe_rollup,
                    "proposals": merged_proposals,
                    "stages": stage_summaries,
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("metabolism_achievements: cycle %s failed: %s",
                            journal.get("cycle_id", "?"), exc)
                continue

        return {
            "cycles": cycles,
            "generated_at": _now_iso(),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_achievements.achievements: top-level error: %s", exc)
        return {
            "cycles": [],
            "generated_at": _now_iso(),
        }
