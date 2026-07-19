"""admin/marketing.py — Marketing NW lobe admin page.

Panel payloads for GET /api/marketing/{overview,departments,channels,campaigns,
experiments,lobes}.  All sources are fail-soft (try/except → None/[]).  Panels
read only committed artifacts; they never write.

The single source of truth is data/neuralweb/marketing_state.json (marketing.state/v1).
config/marketing.yml is read for the settings echo.

All public functions return {"ok": True, ...} or {"ok": False, "error": ...}.
If the state file is absent they return ok:True with empty/null sections and
an honest accruing note — so the page renders gracefully on day 0.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_STATE_REL   = Path("data/neuralweb/marketing_state.json")
_CONTENT_REL = Path("data/marketing/content_plan.json")
_LAB_REL     = Path("data/marketing/lab_rollup.json")
_CONFIG_REL  = Path("config/marketing.yml")

# N-floor (docket D03 §Traps + small-N humility): a reach cell backed by fewer
# than this many posts is display-only — never allowed to crown a winner.
_LAB_N_FLOOR = 20

_ACCRUING_NOTE = (
    "marketing_state.json not yet written — "
    "accruing after first nightly governor run."
)
_CONTENT_ACCRUING_NOTE = (
    "content_plan.json not yet written — "
    "accruing after first nightly governor run."
)
_LAB_WAITING_NOTE = (
    "No live posts yet — the Lab starts measuring once Broadcast goes live (W1). "
    "The hypotheses below are seeded and waiting for evidence."
)


# ---------------------------------------------------------------------------
# IO helpers (all fail-soft)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _state(root: Path) -> dict | None:
    return _read_json(root / _STATE_REL)


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def overview(root=None) -> dict:
    """CMO office view: lobe lifecycle, mandate, north-star, CMO portfolio,
    opportunity queue depth, self-improvement loop, guardrail checklist."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "lobe": None,
                "north_star": None,
                "cmo": None,
                "authority_level": None,
                "mandate": None,
            }
        return {
            "ok": True,
            "lobe": s.get("lobe"),
            "north_star": s.get("north_star"),
            "cmo": s.get("cmo"),
            "authority_level": (s.get("lobe") or {}).get("authority_level"),
            "mandate": (s.get("lobe") or {}).get("mandate"),
            "as_of": s.get("as_of"),
            "waves": s.get("waves"),
            "notes": s.get("notes"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.overview failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def departments(root=None) -> dict:
    """Department portfolio: one record per department + authority ladder."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "departments": [],
                "authority_ladder": [],
            }
        return {
            "ok": True,
            "departments": s.get("departments") or [],
            "authority_ladder": s.get("authority_ladder") or [],
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.departments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def channels(root=None) -> dict:
    """Desk network: accounts, distinctness, actuation path; publication ledger;
    corrections count."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "desk_network": None,
                "publications": None,
                "corrections": None,
            }
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "desk_network": s.get("desk_network"),
            "publications": pipeline.get("publications"),
            "corrections": (pipeline.get("publications") or {}).get("corrections"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.channels failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def campaigns(root=None) -> dict:
    """Opportunity bus + campaigns table + pipeline summary."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "opportunities": None,
                "campaigns": None,
                "pipeline": None,
            }
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "opportunities": pipeline.get("opportunities"),
            "campaigns": pipeline.get("campaigns"),
            "pipeline": pipeline,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.campaigns failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def experiments(root=None) -> dict:
    """Experiment registry + trial-variant selector + north-star window."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "experiments": None,
                "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
                "north_star": None,
            }
        pipeline = s.get("pipeline") or {}
        cfg = _read_yaml(repo / _CONFIG_REL)
        active_variant = (cfg.get("settings") or {}).get("trial_variant", "7_trading_days")
        return {
            "ok": True,
            "experiments": pipeline.get("experiments"),
            "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
            "active_trial_variant": active_variant,
            "north_star": s.get("north_star"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.experiments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def lobes(root=None) -> dict:
    """Engines-by-department; provenance modes + claims summary; growth-event spine."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "engines_by_department": [],
                "provenance": None,
                "growth_events": None,
            }
        # Build engines-by-department index from department records
        depts = s.get("departments") or []
        engines_by_dept = [
            {
                "department_id":   d.get("id"),
                "department_name": d.get("name"),
                "engines":         d.get("engines") or [],
                "lifecycle_state": d.get("lifecycle_state"),
                "authority_level": d.get("authority_level"),
            }
            for d in depts
        ]
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "engines_by_department": engines_by_dept,
            "provenance": s.get("provenance"),
            "growth_events": pipeline.get("growth_events"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.lobes failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def content(root=None) -> dict:
    """Content Studio panel: reads data/marketing/content_plan.json.

    Returns {ok, content_types, accounts, featured_charts, distinctness, summary}.
    Fail-soft with honest note when the file is absent (accruing state).
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        cp = _read_json(repo / _CONTENT_REL)
        if cp is None:
            return {
                "ok": True,
                "note": _CONTENT_ACCRUING_NOTE,
                "content_types": [],
                "accounts": [],
                "featured_charts": [],
                "distinctness": None,
                "summary": None,
            }
        return {
            "ok": True,
            "content_types": cp.get("content_types") or [],
            "accounts": cp.get("accounts") or [],
            "featured_charts": cp.get("featured_charts") or [],
            "distinctness": cp.get("distinctness"),
            "summary": cp.get("summary"),
            "as_of": cp.get("as_of"),
            "source": cp.get("source"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.content failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def lab(root=None) -> dict:
    """Growth Science Lab panel: reads data/marketing/lab_rollup.json.

    The Lab grades the zero-follower playbook hypotheses against real reach
    data.  Until Broadcast (W1) posts live, the file is absent or n_posts=0 —
    that is a first-class *waiting* state, not an error: we still surface the
    seeded hypotheses so the operator sees what will be measured.

    Returns {ok, waiting, note, as_of, n_posts, n_rows, n_orphans,
             hypotheses, cells, top_posts, n_floor}.

    N-floor enforcement (docket §Traps): every reach cell is tagged
    ``below_floor`` when its post count is under _LAB_N_FLOOR, so the page can
    never visually crown a winner under the floor.  We tag rather than drop —
    small-sample cells stay visible, greyed and labelled.
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        rollup = _read_json(repo / _LAB_REL)

        # Absent file OR zero posts → honest waiting state.  Seeded hypotheses
        # are read from the rollup when present so the operator sees the bench.
        if rollup is None or int(rollup.get("n_posts") or 0) <= 0:
            hyps = _lab_hypotheses((rollup or {}).get("hypotheses") or [])
            return {
                "ok": True,
                "waiting": True,
                "note": _LAB_WAITING_NOTE,
                "as_of": (rollup or {}).get("as_of"),
                "n_posts": int((rollup or {}).get("n_posts") or 0),
                "n_rows": int((rollup or {}).get("n_rows") or 0),
                "n_orphans": int((rollup or {}).get("n_orphans") or 0),
                "hypotheses": hyps,
                "cells": [],
                "top_posts": [],
                "n_floor": _LAB_N_FLOOR,
            }

        cells = _lab_cells(rollup.get("cells") or [])
        return {
            "ok": True,
            "waiting": False,
            "as_of": rollup.get("as_of"),
            "n_posts": int(rollup.get("n_posts") or 0),
            "n_rows": int(rollup.get("n_rows") or 0),
            "n_orphans": int(rollup.get("n_orphans") or 0),
            "hypotheses": _lab_hypotheses(rollup.get("hypotheses") or []),
            "cells": cells,
            "top_posts": rollup.get("top_posts") or [],
            "n_floor": _LAB_N_FLOOR,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.lab failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _lab_hypotheses(raw: list) -> list:
    """Normalise hypothesis records, defaulting an unknown state to the cautious
    ``seeding`` bucket (never a fake ``confirmed``)."""
    out = []
    for hyp_item in raw or []:
        state = (hyp_item.get("state") or "seeding").lower()
        if state not in ("seeding", "confirmed", "refuted"):
            state = "seeding"
        out.append({
            "id": hyp_item.get("id"),
            "title": hyp_item.get("title") or hyp_item.get("id") or "Hypothesis",
            "state": state,
            "n_evidence": int(hyp_item.get("n_evidence") or 0),
            "note": hyp_item.get("note") or "",
        })
    return out


def _lab_cells(raw: list) -> list:
    """Tag each reach cell with ``below_floor`` (n < _LAB_N_FLOOR).  Cells stay
    in the list either way — the floor suppresses the *verdict*, not the row."""
    out = []
    for cell in raw or []:
        n = int(cell.get("n") or 0)
        dims = cell.get("dims") or {}
        out.append({
            "dims": dims,
            "n": n,
            "below_floor": n < _LAB_N_FLOOR,
            "med_impressions": cell.get("med_impressions"),
            "med_likes": cell.get("med_likes"),
            "med_replies": cell.get("med_replies"),
            "med_reposts": cell.get("med_reposts"),
        })
    return out


def department(root=None, dept_id=None) -> dict:
    """Single-department detail payload.

    Returns mission/tagline/formal_name, engines [{id,name,does}], scorecard,
    authority, model mix, wave, retirement test.
    Fail-soft: returns ok:True with note if state absent or dept not found.
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "department": None,
            }
        depts = s.get("departments") or []
        if dept_id is None:
            return {
                "ok": True,
                "note": "dept_id required",
                "department": None,
            }
        dept = next((d for d in depts if d.get("id") == dept_id), None)
        if dept is None:
            return {
                "ok": True,
                "note": f"Department '{dept_id}' not found (accruing or unknown id).",
                "department": None,
            }
        return {
            "ok": True,
            "department": dept,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.department failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def settings(root=None) -> dict:
    """Echo of config/marketing.yml top-level knobs. Read-only."""
    repo = Path(root) if root is not None else _ROOT
    try:
        cfg = _read_yaml(repo / _CONFIG_REL)
        s_block = cfg.get("settings") or {}
        return {
            "ok": True,
            "settings": {
                "trial_variant":      s_block.get("trial_variant", "7_trading_days"),
                "desk_network_stage": s_block.get("desk_network_stage", "A"),
                "paid_enabled":       bool(s_block.get("paid_enabled", False)),
                "auditor_strict":     bool(s_block.get("auditor_strict", True)),
                "north_star_window_days": int(s_block.get("north_star_window_days", 90)),
            },
            "positioning": cfg.get("positioning") or {},
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.settings failed: %s", exc)
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Outbox panel (D02 W0, Lane B)
# ---------------------------------------------------------------------------

_OUTBOX_EMPTY_NOTE = (
    "outbox empty — items accrue when the nightly governor runs "
    "with MARKETING_OUTBOX_ENABLED=1."
)

_TERMINAL_STATUSES = frozenset({"posted", "failed", "quarantined"})
_STATUS_KEYS = ("queued", "approved", "held", "posted", "failed", "quarantined")


def _zero_counts() -> dict:
    return {k: 0 for k in _STATUS_KEYS}


def outbox(root=None) -> dict:
    """Posting-queue panel.

    Reads data/marketing/outbox/{items.jsonl,status_ledger.jsonl,decisions.jsonl}
    via engine.marketing.outbox public API.  Fail-soft: ok:True on absent files,
    ok:False only on unexpected exceptions.

    Frozen payload contract: see D02 W0 Lane B spec.
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        # Config for effective_cap
        cfg = _read_yaml(repo / _CONFIG_REL)
        cap = _ob.effective_cap(cfg)

        # Read raw data (all fail-soft → [] on absence)
        ob_root = repo  # outbox_dir resolves against repo root
        items = _ob.read_items(ob_root)
        statuses = _ob.current_statuses(ob_root)
        decisions = _ob.latest_decisions(ob_root)
        ledger = _ob.read_ledger(ob_root)

        # Empty state
        if not items:
            return {
                "ok": True,
                "note": _OUTBOX_EMPTY_NOTE,
                "as_of": None,
                "cap": cap,
                "summary": _zero_counts() | {"total": 0},
                "accounts": [],
                "history": [],
            }

        # Build last-ledger-row per item_id for last_transition_at and receipt
        _last_ledger: dict[str, dict] = {}
        for row in ledger:
            item_id = row.get("id")
            if item_id:
                _last_ledger[item_id] = row

        # Compute effective status per item (folded status + held overlay)
        def _effective_status(item_id: str, folded: str, decision: str | None) -> str:
            """Held = queued status AND latest decision is 'hold'."""
            if folded == "queued" and decision == "hold":
                return "held"
            return folded

        # Build item enriched dicts
        enriched: list[dict] = []
        for item in items:
            item_id = item.get("id", "")
            folded = statuses.get(item_id, item.get("status", "queued"))
            dec_row = decisions.get(item_id)
            dec_val = dec_row.get("decision") if dec_row else None
            decided_at = dec_row.get("at") if dec_row else None
            eff = _effective_status(item_id, folded, dec_val)
            last_row = _last_ledger.get(item_id)
            last_transition_at = last_row.get("at") if last_row else None
            receipt = last_row.get("receipt") if last_row else None
            enriched.append({
                "id": item_id,
                "as_of": item.get("as_of"),
                "kind": item.get("kind"),
                "text": item.get("text"),
                "media": item.get("media") or [],
                "scheduled_at": item.get("scheduled_at"),
                "slot": item.get("slot"),
                "priority": item.get("priority"),
                "provenance": item.get("provenance"),
                "status": folded,               # ledger-folded status (not held overlay)
                "decision": dec_val,
                "decided_at": decided_at,
                "created_at": item.get("created_at"),
                "last_transition_at": last_transition_at,
                "receipt": receipt,
                "_effective": eff,
                "_account": item.get("account", ""),
            })

        # Max as_of across items
        as_of_vals = [e["as_of"] for e in enriched if e.get("as_of")]
        max_as_of = max(as_of_vals) if as_of_vals else None

        # Summary counts
        summary_counts = _zero_counts()
        for e in enriched:
            eff = e["_effective"]
            if eff in summary_counts:
                summary_counts[eff] += 1
        summary = {"total": len(enriched)} | summary_counts

        # Group by account, ordered by account id
        acct_map: dict[str, list] = {}
        for e in enriched:
            acct = e["_account"]
            acct_map.setdefault(acct, []).append(e)

        accounts_out: list[dict] = []
        for acct_id in sorted(acct_map.keys()):
            acct_items = acct_map[acct_id]
            # Sort by scheduled_at then id
            acct_items.sort(key=lambda x: (x.get("scheduled_at") or "", x.get("id") or ""))
            acct_counts = _zero_counts()
            for e in acct_items:
                eff = e["_effective"]
                if eff in acct_counts:
                    acct_counts[eff] += 1
            # Build item dicts (drop internal keys)
            items_out = [
                {k: v for k, v in e.items() if not k.startswith("_")}
                for e in acct_items
            ]
            accounts_out.append({
                "id": acct_id,
                "counts": acct_counts,
                "items": items_out,
            })

        # History: terminal items, newest first by last_transition_at
        terminal = [
            e for e in enriched
            if e["status"] in _TERMINAL_STATUSES
        ]
        terminal.sort(
            key=lambda x: (x.get("last_transition_at") or ""),
            reverse=True,
        )
        history_out = [
            {
                "id": e["id"],
                "account": e["_account"],
                "kind": e["kind"],
                "text": e["text"],
                "status": e["status"],
                "at": e["last_transition_at"],
                "receipt": e["receipt"],
            }
            for e in terminal[:50]
        ]

        return {
            "ok": True,
            "as_of": max_as_of,
            "cap": cap,
            "summary": summary,
            "accounts": accounts_out,
            "history": history_out,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.outbox failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def decide_outbox(item_id: str, decision: str, note: str | None = None, root=None) -> bool:
    """Thin wrapper: record an operator approve/hold decision via engine outbox API.

    Returns True on success, False on unknown id or invalid decision.
    Never raises.
    """
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        repo = Path(root) if root is not None else _ROOT
        return _ob.record_decision(item_id, decision, actor="admin", root=repo, note=note)
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.decide_outbox failed: %s", exc)
        return False
