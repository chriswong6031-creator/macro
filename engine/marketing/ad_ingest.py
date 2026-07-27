"""engine.marketing.ad_ingest — first-party analytics → arena ledgers.

Ad Central Plane O (`research/AD_CENTRAL_MASTERPLAN.md` §2).  Folds
``ad_exposure`` rows out of the first-party ``analytics_events`` table into the
assignment ledger, and derives conversions from the same table.

**The division of trust.**  The browser picks the arm — on a static CDN site
nothing else can, and `templates/adtest.js` is pinned to the engine's own hash so
its pick is reproducible.  But the browser does *not* get to say who it is: the
unit key here is the server-stamped ``visitor_id`` (the httpOnly ``mm_aid``
cookie), which the page cannot read or forge.  So a tampered client can change
which ad *it* sees and can never inflate a denominator or vote twice.

Three integrity gates, all reported rather than silently applied:

* an exposure naming an arena we do not run is dropped
* an exposure naming a creative that is not an arm *of that arena* is dropped —
  the one thing a hostile client could otherwise do is invent an arm
* the first exposure per (arena, visitor) wins; later contradictions are counted

**Conversion.**  For ``signup_rate`` a visitor converts when they were anonymous
at exposure and a later event for the same ``visitor_id`` carries a ``user_id``.
A visitor who was *already* signed in when exposed is not a conversion — counting
them would credit arms for accounts that existed before the test.

Idempotent: re-running over the same window appends nothing new, because the
ledger is read first and already-assigned units are skipped.  Nightly is the sole
advancer (masterplan §0 G-I); an intraday caller may compute, never write.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from . import ad_arena
from .ledgers import read_jsonl

log = logging.getLogger(__name__)

EXPOSURE_TYPE = "ad_exposure"
SIGNUP_METRIC = "signup_rate"


# ─────────────────────────────────────────────────────────────────────────────
# Row helpers
# ─────────────────────────────────────────────────────────────────────────────

def _meta(row: dict[str, Any]) -> dict[str, Any]:
    m = row.get("meta")
    return m if isinstance(m, dict) else {}


def _at(row: dict[str, Any]) -> str:
    """Server time wins over client time — a client clock is not evidence of order."""
    return str(row.get("created_at") or row.get("client_ts") or "")


def _sort_key(row: dict[str, Any]) -> tuple:
    return (_at(row), str(row.get("id") or ""))


# ─────────────────────────────────────────────────────────────────────────────
# Exposures → assignments
# ─────────────────────────────────────────────────────────────────────────────

def fold_exposures(
    rows: Iterable[dict[str, Any]],
    arenas: list[ad_arena.Arena],
    *,
    already_assigned: set[tuple[str, str]] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Return (new assignment rows, anomaly counts).  Pure; writes nothing."""
    arms_by_arena = {a.arena_id: set(a.arm_creative_ids) | {ad_arena.HOLDOUT} for a in arenas}
    seen = set(already_assigned or ())
    anomalies: dict[str, int] = {}

    def bump(key: str) -> None:
        anomalies[key] = anomalies.get(key, 0) + 1

    out: list[dict] = []
    for row in sorted((r for r in rows if r.get("type") == EXPOSURE_TYPE), key=_sort_key):
        meta = _meta(row)
        arena_id = str(meta.get("arena") or "")
        creative = str(meta.get("creative") or "")
        visitor = str(row.get("visitor_id") or "")

        if not visitor:
            bump("exposure_without_visitor")
            continue
        if arena_id not in arms_by_arena:
            bump("exposure_for_unknown_arena")
            continue
        if creative not in arms_by_arena[arena_id]:
            # A client is free to choose among the arms; it is not free to invent one.
            bump("exposure_for_unknown_creative")
            continue

        key = (arena_id, visitor)
        if key in seen:
            bump("duplicate_exposure")
            continue
        seen.add(key)
        out.append({
            "arena_id": arena_id,
            "unit_key": visitor,
            "creative_id": creative,
            "at": _at(row),
        })
    return out, anomalies


# ─────────────────────────────────────────────────────────────────────────────
# Conversions → outcomes
# ─────────────────────────────────────────────────────────────────────────────

def fold_signups(
    rows: Iterable[dict[str, Any]],
    assignments: list[dict[str, Any]],
    *,
    already_converted: set[tuple[str, str]] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Derive `signup_rate` outcomes from the same event stream.

    A visitor converts when they hold no ``user_id`` at exposure and a later
    event for the same ``visitor_id`` carries one.  Already-signed-in visitors
    are excluded and counted — crediting them would hand arms the accounts that
    existed before the test started.
    """
    all_rows = sorted(rows, key=_sort_key)
    assigned_at: dict[str, str] = {}
    arenas_for: dict[str, set[str]] = {}
    for a in assignments:
        unit = str(a.get("unit_key") or "")
        if not unit:
            continue
        at = str(a.get("at") or "")
        if unit not in assigned_at or at < assigned_at[unit]:
            assigned_at[unit] = at
        arenas_for.setdefault(unit, set()).add(str(a.get("arena_id") or ""))

    anomalies: dict[str, int] = {}

    def bump(key: str) -> None:
        anomalies[key] = anomalies.get(key, 0) + 1

    # Anyone already identified at or before their exposure is not a new account.
    pre_existing: set[str] = set()
    for row in all_rows:
        visitor = str(row.get("visitor_id") or "")
        if not visitor or visitor not in assigned_at:
            continue
        if row.get("user_id") and _at(row) <= assigned_at[visitor]:
            pre_existing.add(visitor)

    seen = set(already_converted or ())
    out: list[dict] = []
    for row in all_rows:
        visitor = str(row.get("visitor_id") or "")
        if not visitor or visitor not in assigned_at or not row.get("user_id"):
            continue
        if _at(row) <= assigned_at[visitor]:
            continue
        if visitor in pre_existing:
            bump("already_signed_in_at_exposure")
            continue
        for arena_id in sorted(arenas_for.get(visitor, ())):
            key = (arena_id, visitor)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "arena_id": arena_id,
                "unit_key": visitor,
                "metric": SIGNUP_METRIC,
                "value": 1.0,
                "at": _at(row),
            })
    return out, anomalies


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator — the nightly's entry point
# ─────────────────────────────────────────────────────────────────────────────

def ingest(
    rows: Iterable[dict[str, Any]],
    *,
    root: Path | str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fold *rows* into the arena ledgers.  Never raises.

    `dry_run=True` computes everything and writes nothing — the shape an intraday
    lane must use, since only the nightly advances a forward ledger.
    """
    try:
        r = Path(root) if root is not None else Path(".")
        arenas = ad_arena.load_arenas(root=r)
        if not arenas:
            return {"ok": True, "arenas": 0, "assignments": 0, "outcomes": 0,
                    "note": "no arenas to ingest for", "dry_run": dry_run}

        rows = list(rows)
        d = r / ad_arena.DEFAULT_LEDGER_DIR
        existing_assign = read_jsonl(d / ad_arena.ASSIGNMENTS_FILE)
        existing_out = read_jsonl(d / ad_arena.OUTCOMES_FILE)
        seen_assign = {
            (str(x.get("arena_id")), str(x.get("unit_key"))) for x in existing_assign
        }
        seen_out = {
            (str(x.get("arena_id")), str(x.get("unit_key")))
            for x in existing_out if str(x.get("metric")) == SIGNUP_METRIC
        }

        new_assign, a_anom = fold_exposures(rows, arenas, already_assigned=seen_assign)
        # Conversions are joined against the FULL assignment history, not just
        # tonight's — a visitor exposed last week can convert today.
        all_assign = existing_assign + new_assign
        new_out, o_anom = fold_signups(rows, all_assign, already_converted=seen_out)

        written_a = written_o = 0
        if not dry_run:
            for row in new_assign:
                if ad_arena.record_assignment(
                    row["arena_id"], row["unit_key"], row["creative_id"],
                    root=r, at=row["at"],
                ):
                    written_a += 1
            for row in new_out:
                if ad_arena.record_outcome(
                    row["arena_id"], row["unit_key"], row["metric"],
                    value=row["value"], root=r, at=row["at"],
                ):
                    written_o += 1

        anomalies = {**a_anom, **o_anom}
        return {
            "ok": True,
            "arenas": len(arenas),
            "rows_seen": len(rows),
            "assignments": len(new_assign),
            "outcomes": len(new_out),
            "written_assignments": written_a,
            "written_outcomes": written_o,
            "anomalies": anomalies,
            "dry_run": dry_run,
            "plain": _plain(len(new_assign), len(new_out), anomalies, dry_run),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("ad_ingest.ingest failed: %s", exc)
        return {"ok": False, "error": str(exc), "dry_run": dry_run}


def _plain(assignments: int, outcomes: int, anomalies: dict[str, int], dry_run: bool) -> str:
    if not assignments and not outcomes:
        return "No new split-test activity tonight."
    lead = "Would record" if dry_run else "Recorded"
    parts = [f"{lead} {assignments} new visitor{'s' if assignments != 1 else ''}"]
    if outcomes:
        parts.append(f"{outcomes} sign-up{'s' if outcomes != 1 else ''}")
    tail = ", ".join(parts) + "."
    if anomalies:
        tail += " Dropped: " + ", ".join(
            f"{k.replace('_', ' ')} ×{v}" for k, v in sorted(anomalies.items())
        ) + "."
    return tail
