"""Thesis monitor — deterministic kill-criteria watcher (W4b, P2-B).

TWO THESIS PRODUCERS
====================
1. **Deterministic auto-theses** (NEW — this file, no credential needed):
   Every PRECIPICE / BROADENING (including text-grade variants) flag in
   data/foresight/log.jsonl auto-instantiates a thesis with machine-checkable
   kill-criteria derived from the flag's own components.  Persisted to
   data/foresight/deterministic_theses.jsonl (append-only).

2. **LLM analyst theses** (optional — engine/foresight_analyst when a credential
   is present): still consumed and monitored when present, now as an enrichment
   layer on top of deterministic coverage.

KILL-CRITERIA TEMPLATES
=======================
Derived from the flag's components at instantiation:

For text-stage flags (PRECIPICE (text) / BROADENING (text)):
  - {kind: "text_accel_negative", detail: "language accel < 0 for 2 consecutive builds"}
  - {kind: "stage_regressed_to_watch", detail: "cascade stage no longer thesis-stage"}

For numeric-physical flags (PRECIPICE / BROADENING — TIGHT/SOLD_OUT band):
  - {kind: "band_loosens", detail: "bottleneck_band is LOOSE or AWAITING_DATA for 2 builds"}
  - {kind: "breadth_rolls_negative", detail: "revision_breadth < 0 for 2 consecutive builds"}
  - {kind: "stage_regressed_to_watch", detail: "cascade stage no longer thesis-stage"}

MONITORING STATUS
=================
Each thesis is re-evaluated each build:
  INTACT     — no criterion met or partially met
  WEAKENING  — any one criterion partially met (e.g. 1 of 2 consecutive builds)
  BROKEN     — a criterion fully met (2 consecutive builds, or stage has regressed)
  UNVERIFIABLE — a criterion references data that is not in the current payload
                 (never silently INTACT per §5 of the upgrade doc)

CONSECUTIVE-BUILD STATE
=======================
Tracked honestly: each thesis record has an "updates" array (append-only event rows).
The counter is derived by reading the last N events — no field is ever mutated.

OUTPUT SHAPE (backward-compatible with foresight_health.py)
===========================================================
  n_open          int — total active theses (LLM + deterministic)
  monitored       list[dict] — per-thesis status records
  n_broken        int
  n_weakening     int
  n_deterministic int — NEW: count from deterministic producer
  n_llm           int — NEW: count from LLM producer

DISPLAY-ONLY; degrade to None when no theses exist at all (both producers empty).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from lib import config

log = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────
BROKEN_DROP = 0.25         # absolute heat fall from open => BROKEN (LLM theses)
WEAKEN_DROP = 0.12         # absolute heat fall from open => WEAKENING (LLM theses)
MIN_SURFACES = 2           # convergence below this quorum => BROKEN
CONSECUTIVE_NEEDED = 2     # builds in a row before a criterion fires BROKEN

THESIS_STAGES = {"PRECIPICE", "BROADENING", "PRECIPICE (text)", "BROADENING (text)"}
TEXT_STAGES = {"PRECIPICE (text)", "BROADENING (text)"}
NUMERIC_STAGES = {"PRECIPICE", "BROADENING"}

# ── file paths ───────────────────────────────────────────────────────────────

def _foresight_dir() -> Path:
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _llm_ledger_path() -> Path:
    return _foresight_dir() / "analyst_theses.jsonl"


def _det_ledger_path() -> Path:
    return _foresight_dir() / "deterministic_theses.jsonl"


def _log_path() -> Path:
    return _foresight_dir() / "log.jsonl"


# ── LLM thesis reader (unchanged contract) ───────────────────────────────────

def _open_theses() -> dict[str, dict]:
    """Latest open LLM thesis per theme from the analyst ledger."""
    p = _llm_ledger_path()
    if not p.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t = e.get("theme")
        if not t:
            continue
        if t not in latest or str(e.get("asof")) > str(latest[t].get("asof")):
            latest[t] = e
    return latest


# ── deterministic kill-criteria templates ───────────────────────────────────

def _make_kill_criteria(stage: str) -> list[dict]:
    """Return machine-checkable kill-criteria for a given thesis stage."""
    universal = {"kind": "stage_regressed_to_watch",
                 "detail": "cascade stage no longer in PRECIPICE/BROADENING family"}
    if stage in TEXT_STAGES:
        return [
            {"kind": "text_accel_negative",
             "detail": "language accel < 0 for 2 consecutive builds"},
            universal,
        ]
    # numeric physical stage
    return [
        {"kind": "band_loosens",
         "detail": "bottleneck_band is LOOSE or AWAITING_DATA for 2 consecutive builds"},
        {"kind": "breadth_rolls_negative",
         "detail": "revision_breadth < 0 for 2 consecutive builds"},
        universal,
    ]


# ── cascade ledger scanner ───────────────────────────────────────────────────

def _latest_thesis_stage_per_theme() -> dict[str, dict]:
    """Scan log.jsonl and return the MOST RECENT thesis-stage row per theme.

    A thesis-stage row is one whose `stage` field is in THESIS_STAGES.
    Returns {theme: row_dict}.
    """
    p = _log_path()
    if not p.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in p.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        stage = row.get("stage") or ""
        if stage not in THESIS_STAGES:
            continue
        theme = row.get("theme")
        asof = row.get("asof") or ""
        if not theme or not asof:
            continue
        if theme not in latest or asof > latest[theme].get("asof", ""):
            latest[theme] = row
    return latest


# ── deterministic thesis ledger (append-only) ───────────────────────────────

def _read_det_ledger() -> dict[str, dict]:
    """Read deterministic_theses.jsonl.  Returns {theme: latest_record}.
    Each record may have an 'updates' list of event rows (append-only)."""
    p = _det_ledger_path()
    if not p.exists():
        return {}
    records: dict[str, list[dict]] = {}
    for line in p.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        theme = row.get("theme")
        if not theme:
            continue
        records.setdefault(theme, []).append(row)
    # Fold: for each theme, the HEADER row is the one with source="deterministic" (not an update),
    # and update rows have kind="update".  Return the header merged with its update list.
    result: dict[str, dict] = {}
    for theme, rows in records.items():
        header = next((r for r in rows if r.get("kind") != "update"), None)
        updates = [r for r in rows if r.get("kind") == "update"]
        if header is None:
            continue
        merged = {**header, "updates": updates}
        result[theme] = merged
    return result


def _append_det_record(record: dict) -> None:
    """Append a single JSON record to deterministic_theses.jsonl."""
    p = _det_ledger_path()
    with p.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


def _ensure_deterministic_theses(cascade_rows: dict[str, dict]) -> dict[str, dict]:
    """For every active thesis-stage flag in the cascade ledger, ensure a deterministic
    thesis record exists in deterministic_theses.jsonl.  Opens new ones; does NOT close
    (closing happens via update events when criteria are met).

    Returns the (now-up-to-date) ledger: {theme: merged_record}.
    """
    existing = _read_det_ledger()
    ts = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    for theme, row in cascade_rows.items():
        if theme in existing:
            continue  # already has a record; skip
        stage = row.get("stage", "")
        record = {
            "theme": theme,
            "opened": today,
            "ts": ts,
            "source": "deterministic",
            "stage_at_open": stage,
            "kill_criteria": _make_kill_criteria(stage),
            # capture the ledger snapshot fields at open time
            "bottleneck_band_at_open": row.get("bottleneck_band"),
            "revision_breadth_at_open": row.get("revision_breadth"),
        }
        try:
            _append_det_record(record)
        except Exception as e:  # noqa: BLE001
            log.warning("thesis_monitor: failed to write deterministic thesis for %s: %s", theme, e)

    # Re-read so caller gets the just-written records too
    return _read_det_ledger()


# ── criterion evaluation against current cascade row ─────────────────────────

def _current_cascade_map() -> dict[str, dict]:
    """Build a {theme: most_recent_log_row} from log.jsonl for ALL stages
    (not just thesis stages) — used to check stage regression."""
    p = _log_path()
    if not p.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in p.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        theme = row.get("theme")
        asof = row.get("asof") or ""
        if not theme:
            continue
        if theme not in latest or asof > latest[theme].get("asof", ""):
            latest[theme] = row
    return latest


def _get_updates_for(det_record: dict) -> list[dict]:
    """Return the update events from the det_record (already merged from ledger)."""
    return det_record.get("updates") or []


def _evaluate_criterion(
    criterion: dict,
    current_row: dict | None,
    convergence_item: dict | None,
    updates: list[dict],
) -> str:
    """Evaluate one kill-criterion against the current state.

    Returns "BROKEN", "WEAKENING", "INTACT", or "UNVERIFIABLE".

    consecutive-build counting:
      We count the last N "criterion_check" update events for this kind where
      condition_met=True.  If current build also meets it, we count that too.
    """
    kind = criterion.get("kind")

    # ── stage_regressed_to_watch ─────────────────────────────────────────
    if kind == "stage_regressed_to_watch":
        stage_now = (current_row or {}).get("stage") or ""
        if current_row is None:
            return "UNVERIFIABLE"
        if stage_now not in THESIS_STAGES:
            return "BROKEN"
        return "INTACT"

    # ── text_accel_negative ──────────────────────────────────────────────
    if kind == "text_accel_negative":
        # We check language_accel from the convergence item or cascade row.
        # If not present → UNVERIFIABLE (never silently INTACT).
        lang_accel: Any = None
        if convergence_item:
            lang_accel = convergence_item.get("language_accel")
        if lang_accel is None and current_row:
            lang_accel = current_row.get("language_accel")
        if lang_accel is None:
            return "UNVERIFIABLE"
        current_neg = float(lang_accel) < 0
        # update events use criterion_kind (not kind, which is always "update")
        prev_count = sum(
            1 for u in updates[-CONSECUTIVE_NEEDED:]
            if u.get("criterion_kind") == kind and u.get("condition_met")
        )
        if current_neg:
            if prev_count >= (CONSECUTIVE_NEEDED - 1):
                return "BROKEN"
            return "WEAKENING"
        return "INTACT"

    # ── band_loosens ─────────────────────────────────────────────────────
    if kind == "band_loosens":
        bb = (current_row or {}).get("bottleneck_band")
        if bb is None:
            return "UNVERIFIABLE"
        loosening = bb in ("LOOSE", "AWAITING_DATA", None) or bb not in (
            "TIGHT", "SOLD_OUT", "TIGHTENING", "TIGHT (text)", "TIGHTENING (text)"
        )
        prev_count = sum(
            1 for u in updates[-CONSECUTIVE_NEEDED:]
            if u.get("criterion_kind") == kind and u.get("condition_met")
        )
        if loosening:
            if prev_count >= (CONSECUTIVE_NEEDED - 1):
                return "BROKEN"
            return "WEAKENING"
        return "INTACT"

    # ── breadth_rolls_negative ───────────────────────────────────────────
    if kind == "breadth_rolls_negative":
        rb = (current_row or {}).get("revision_breadth")
        if rb is None:
            return "UNVERIFIABLE"
        current_neg = float(rb) < 0
        prev_count = sum(
            1 for u in updates[-CONSECUTIVE_NEEDED:]
            if u.get("criterion_kind") == kind and u.get("condition_met")
        )
        if current_neg:
            if prev_count >= (CONSECUTIVE_NEEDED - 1):
                return "BROKEN"
            return "WEAKENING"
        return "INTACT"

    # unknown criterion kind
    return "UNVERIFIABLE"


def _aggregate_criteria_status(criterion_statuses: list[str]) -> str:
    """Aggregate multiple criterion statuses into a single thesis status.

    Per §5 of the upgrade doc: UNVERIFIABLE criteria must never yield silently INTACT.
    If ANY criterion is UNVERIFIABLE and none is BROKEN or WEAKENING, the thesis is
    UNVERIFIABLE — the monitor admits it cannot verify rather than claiming integrity.
    """
    if not criterion_statuses:
        return "INTACT"
    if "BROKEN" in criterion_statuses:
        return "BROKEN"
    if "WEAKENING" in criterion_statuses:
        return "WEAKENING"
    # Any UNVERIFIABLE criterion (when none are worse) → UNVERIFIABLE
    if "UNVERIFIABLE" in criterion_statuses:
        return "UNVERIFIABLE"
    return "INTACT"


def _append_update_event(
    theme: str,
    criterion_kind: str,
    condition_met: bool,
    status: str,
) -> None:
    """Append a criterion-check update event (consecutive-build tracking)."""
    try:
        event = {
            "kind": "update",
            "theme": theme,
            "criterion_kind": criterion_kind,
            "condition_met": condition_met,
            "status": status,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _append_det_record(event)
    except Exception as e:  # noqa: BLE001
        log.warning("thesis_monitor: update event write failed for %s/%s: %s",
                    theme, criterion_kind, e)


# ── LLM thesis evaluation (original heat-decay logic) ───────────────────────

def _status_llm(opened: dict, heat_now: float, phys_now: bool, n_now: int) -> str:
    """Original heat-decay logic for LLM theses."""
    h0 = opened.get("heat_at_open") or 0.0
    drop = h0 - (heat_now or 0.0)
    if (opened.get("physical_at_open") and not phys_now) or n_now < MIN_SURFACES or drop >= BROKEN_DROP:
        return "BROKEN"
    n0 = opened.get("n_surfaces_at_open") or 0
    if drop >= WEAKEN_DROP or (n0 - n_now) >= 1:
        return "WEAKENING"
    return "INTACT"


# ── main entry point ─────────────────────────────────────────────────────────

def compute_thesis_monitor(convergence: dict | None, write_state: bool = True) -> dict | None:
    """Re-evaluate all open theses (deterministic + LLM) against the CURRENT convergence.

    Now works with ZERO LLM involvement — the deterministic producer auto-instantiates
    theses from thesis-stage flags in the cascade ledger (log.jsonl).

    Returns None only when BOTH producers have zero theses to monitor.
    DISPLAY-ONLY.
    """
    # ── Step 1: collect current cascade state ────────────────────────────
    current_cascade = _current_cascade_map()           # {theme: most_recent_log_row}
    cascade_thesis_rows = _latest_thesis_stage_per_theme()  # {theme: most_recent_thesis_row}
    conv_current: dict[str, dict] = {}
    if convergence and convergence.get("ranked"):
        conv_current = {it.get("theme"): it for it in convergence.get("ranked") or []}

    # ── Step 2: ensure deterministic theses exist for all active thesis-stage flags ──
    try:
        det_ledger = _ensure_deterministic_theses(cascade_thesis_rows)
    except Exception as e:  # noqa: BLE001
        log.warning("thesis_monitor: deterministic thesis init failed: %s", e)
        det_ledger = {}

    # ── Step 3: collect LLM theses ───────────────────────────────────────
    llm_opened = _open_theses()  # {theme: record}

    # ── Step 4: exit early if both producers empty ───────────────────────
    if not det_ledger and not llm_opened:
        return None

    monitored = []
    today_asof = (convergence or {}).get("asof") or date.today().isoformat()

    # ── Step 5: evaluate deterministic theses ────────────────────────────
    for theme, det_rec in det_ledger.items():
        current_row = current_cascade.get(theme)
        conv_item = conv_current.get(theme)
        updates = _get_updates_for(det_rec)
        criteria = det_rec.get("kill_criteria") or []

        criterion_statuses: list[str] = []
        for crit in criteria:
            cstatus = _evaluate_criterion(crit, current_row, conv_item, updates)
            criterion_statuses.append(cstatus)
            # Append update event for consecutive-build tracking (only for trackable criteria)
            if crit.get("kind") in ("text_accel_negative", "band_loosens", "breadth_rolls_negative"):
                condition_met = cstatus in ("BROKEN", "WEAKENING")
                if write_state:
                    _append_update_event(theme, crit["kind"], condition_met, cstatus)

        thesis_status = _aggregate_criteria_status(criterion_statuses)

        monitored.append({
            "theme": theme,
            "source": "deterministic",
            "status": thesis_status,
            "stage_at_open": det_rec.get("stage_at_open"),
            "opened": det_rec.get("opened"),
            "kill_criteria": criteria,
            "criterion_statuses": criterion_statuses,
            "n_criteria": len(criteria),
        })

    # ── Step 6: evaluate LLM theses ─────────────────────────────────────
    for theme, o in llm_opened.items():
        now = conv_current.get(theme) or {}
        heat_now = now.get("heat") or 0.0
        phys_now = bool(now.get("physical_confirmed"))
        n_now = now.get("n_signals") or 0
        status = _status_llm(o, heat_now, phys_now, n_now)
        monitored.append({
            "theme": theme,
            "source": "llm",
            "status": status,
            "heat_at_open": o.get("heat_at_open"),
            "heat_now": round(heat_now, 3),
            "n_surfaces_now": n_now,
            "physical_now": phys_now,
            "opened_asof": o.get("asof"),
            "kill_criteria": o.get("kill_criteria"),
        })

    if not monitored:
        return None

    # ── Step 7: sort by severity ─────────────────────────────────────────
    order = {"BROKEN": 0, "UNVERIFIABLE": 1, "WEAKENING": 2, "INTACT": 3}
    monitored.sort(key=lambda m: order.get(m["status"], 4))

    n_det = sum(1 for m in monitored if m["source"] == "deterministic")
    n_llm = sum(1 for m in monitored if m["source"] == "llm")

    out: dict = {
        "asof": today_asof,
        "n_open": len(monitored),
        "n_broken": sum(1 for m in monitored if m["status"] == "BROKEN"),
        "n_weakening": sum(1 for m in monitored if m["status"] == "WEAKENING"),
        "n_deterministic": n_det,
        "n_llm": n_llm,
        "monitored": monitored,
        "note": (
            "deterministic+LLM dual-producer: deterministic theses auto-instantiate from "
            "PRECIPICE/BROADENING cascade flags and evaluate machine-checkable kill-criteria "
            "(consecutive-build tracking); LLM theses use heat-decay logic when a credential "
            "is present. THESIS-BROKEN fires with zero LLM involvement."
        ),
    }

    if write_state:
        try:
            d = _foresight_dir()
            (d / "thesis_monitor.json").write_text(
                json.dumps(out, separators=(",", ":"), default=str)
            )
        except Exception as e:  # noqa: BLE001
            log.warning("thesis_monitor state write failed: %s", e)

    return out
