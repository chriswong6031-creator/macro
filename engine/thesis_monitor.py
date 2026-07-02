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
    """Read deterministic_theses.jsonl.  Returns {theme: latest_OPEN_record}.

    B2b FIX: A thesis can be closed (kind="close") and then re-opened.  We scan
    ALL rows in append order and track, per theme:
      - The MOST RECENT header (source="deterministic", kind not "update"/"close") for the
        CURRENT open epoch (i.e., after the last close event, if any).
      - Update events belonging to the current open epoch (after last close).
      - A close event (kind="close") marks the end of an epoch.

    Closed theses (whose most recent non-update row is kind="close") are NOT returned
    in the result — they are excluded from n_open/monitored.  A re-flag opens a
    FRESH header via _ensure_deterministic_theses.
    """
    p = _det_ledger_path()
    if not p.exists():
        return {}

    # Collect all rows per theme in append order
    all_rows: dict[str, list[dict]] = {}
    for line in p.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        theme = row.get("theme")
        if not theme:
            continue
        all_rows.setdefault(theme, []).append(row)

    result: dict[str, dict] = {}
    for theme, rows in all_rows.items():
        # Walk rows in order to find the most recent open epoch
        # An "epoch" starts at a header (kind != "update" and kind != "close")
        # and ends at a close (kind == "close").
        current_header: dict | None = None
        current_updates: list[dict] = []
        is_closed = False

        for row in rows:
            kind = row.get("kind")
            if kind == "update":
                current_updates.append(row)
            elif kind == "close":
                # Mark end of this epoch; reset for potential next epoch
                is_closed = True
                # Keep header/updates for potential display of closed state,
                # but mark so we don't include in result.
            else:
                # New header — starts a fresh epoch (re-flag after close)
                current_header = row
                current_updates = []
                is_closed = False

        if current_header is None or is_closed:
            continue  # no open thesis for this theme

        result[theme] = {**current_header, "updates": current_updates}
    return result


def _append_det_record(record: dict) -> None:
    """Append a single JSON record to deterministic_theses.jsonl."""
    p = _det_ledger_path()
    with p.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


def _append_close_event(theme: str, reason: str = "BROKEN") -> None:
    """Append a terminal kind='close' event when a thesis is BROKEN.

    B2b FIX: closed theses are excluded from n_open/monitored.  A subsequent
    re-flag opens a FRESH header (the close marks the end of the old epoch).
    """
    try:
        _append_det_record({
            "kind": "close",
            "theme": theme,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:  # noqa: BLE001
        log.warning("thesis_monitor: close event write failed for %s: %s", theme, e)


def _ensure_deterministic_theses(cascade_rows: dict[str, dict]) -> dict[str, dict]:
    """For every active thesis-stage flag in the cascade ledger, ensure a deterministic
    thesis record exists in deterministic_theses.jsonl.  Opens new ones; does NOT close
    (closing happens via _append_close_event when a criterion fires BROKEN).

    B2b FIX: `opened` is set to the flag row's `asof`, not date.today().  This ensures
    the thesis header records WHEN the cascade actually flagged it, not when the monitor ran.

    N2 FIX: `late_line_basis` is stored at open time for future breadth-basis auditing.

    Returns the (now-up-to-date) ledger: {theme: merged_record}.
    """
    existing = _read_det_ledger()
    ts = datetime.now(timezone.utc).isoformat()

    for theme, row in cascade_rows.items():
        if theme in existing:
            continue  # already has a record; skip
        stage = row.get("stage", "")
        # B2b FIX: opened = flag row's asof, not today
        opened = row.get("asof") or date.today().isoformat()
        kc = _make_kill_criteria(stage)
        # N2 FIX: store breadth basis at open time
        if stage not in TEXT_STAGES:
            for c in kc:
                if c.get("kind") == "breadth_rolls_negative":
                    c["detail"] = (
                        "sign test on legacy breadth (revision_breadth); "
                        "stage may have been decided on breadth_cov — see late_line_basis"
                    )
        record = {
            "theme": theme,
            "opened": opened,
            "ts": ts,
            "source": "deterministic",
            "stage_at_open": stage,
            "kill_criteria": kc,
            # capture the ledger snapshot fields at open time
            "bottleneck_band_at_open": row.get("bottleneck_band"),
            "revision_breadth_at_open": row.get("revision_breadth"),
            # N2: breadth basis for future auditing
            "late_line_basis": row.get("late_line_basis"),
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


def _dedup_update_key(u: dict) -> tuple:
    """Return the dedup key for an update event row: (criterion_kind, asof).

    B2 FIX: new rows carry an explicit `asof`; old rows without it fall back to
    date(ts) so legacy data is tolerated without silently double-counting.
    """
    kind = u.get("criterion_kind")
    asof = u.get("asof")
    if asof is None:
        # Legacy row: derive from ts
        ts = u.get("ts") or ""
        try:
            asof = datetime.fromisoformat(ts).date().isoformat()
        except Exception:  # noqa: BLE001
            asof = ts[:10] if len(ts) >= 10 else ts
    return (kind, asof)


def _deduplicated_updates(updates: list[dict]) -> list[dict]:
    """Return updates deduped to one event per (criterion_kind, asof).

    B2 FIX: same-day re-runs with identical cascade state produce only one event
    per criterion per asof date, so consecutive-build counters are not inflated.
    """
    seen: set[tuple] = set()
    result: list[dict] = []
    for u in updates:
        key = _dedup_update_key(u)
        if key not in seen:
            seen.add(key)
            result.append(u)
    return result


def _prior_updates(updates: list[dict], current_asof: str | None) -> list[dict]:
    """Return PRIOR-build updates only — excluding any event with the same asof as the
    current build.

    B2 FIX: the consecutive-build counter must count events from PRIOR asof dates only.
    When prev_count (prior events) + 1 (current build) >= CONSECUTIVE_NEEDED, we fire.
    This way, two re-runs of the same asof cannot inflate the counter: both runs see
    the same prior_updates (no event with current_asof in them on run 1; the event
    written by run 1 is excluded from run 2's prior_updates because it has the same asof).
    """
    deduped = _deduplicated_updates(updates)
    if not current_asof:
        return deduped
    return [u for u in deduped if u.get("asof") != current_asof]


# N3 fix: explicit loosening allowlist — unknown/new band strings → UNVERIFIABLE, never BROKEN.
# TIGHTENING counts as still-supportive (not loosening).
_LOOSENING_BANDS = {"LOOSE", "NEUTRAL", "AWAITING_DATA"}
_SUPPORTIVE_BANDS = {"TIGHT", "SOLD_OUT", "TIGHTENING", "TIGHT (text)", "TIGHTENING (text)"}


def _evaluate_criterion(
    criterion: dict,
    current_row: dict | None,
    convergence_item: dict | None,
    updates: list[dict],
    current_asof: str | None = None,
) -> str:
    """Evaluate one kill-criterion against the current state.

    Returns "BROKEN", "WEAKENING", "INTACT", or "UNVERIFIABLE".

    B2 FIX — consecutive-build counting:
      Updates are deduped to one event per (criterion_kind, asof) before counting.
      This means two same-day re-runs with identical cascade state cannot
      double-increment the counter.
    """
    kind = criterion.get("kind")

    # ── stage_regressed_to_watch ─────────────────────────────────────────
    if kind == "stage_regressed_to_watch":
        if current_row is None:
            return "UNVERIFIABLE"
        stage_now = (current_row or {}).get("stage") or ""
        if stage_now not in THESIS_STAGES:
            return "BROKEN"
        return "INTACT"

    # B2 FIX: use prior-build updates only (excludes current asof to prevent double-counting).
    # prev_count = how many PRIOR builds (distinct asof dates) already met this criterion.
    # Current build contributes +1 if it meets the criterion too.
    prior = _prior_updates(updates, current_asof)

    # ── text_accel_negative ──────────────────────────────────────────────
    if kind == "text_accel_negative":
        # N1 FIX: language_accel is read from: convergence item → current cascade row
        # (the cascade _append_ledger now logs it — see foresight_cascade.py).
        # If not present in EITHER source → UNVERIFIABLE (never silently INTACT).
        lang_accel: Any = None
        if convergence_item:
            lang_accel = convergence_item.get("language_accel")
        if lang_accel is None and current_row:
            lang_accel = current_row.get("language_accel")
        if lang_accel is None:
            return "UNVERIFIABLE"
        current_neg = float(lang_accel) < 0
        prev_count = sum(
            1 for u in prior[-CONSECUTIVE_NEEDED:]
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
        # N3 FIX: use an explicit loosening allowlist.
        # Unknown/new band strings → UNVERIFIABLE, never BROKEN.
        # TIGHTENING counts as still-supportive (thesis intact).
        if bb in _LOOSENING_BANDS:
            loosening = True
        elif bb in _SUPPORTIVE_BANDS:
            loosening = False
        else:
            # Unknown band string — cannot determine if loosening
            return "UNVERIFIABLE"
        prev_count = sum(
            1 for u in prior[-CONSECUTIVE_NEEDED:]
            if u.get("criterion_kind") == kind and u.get("condition_met")
        )
        if loosening:
            if prev_count >= (CONSECUTIVE_NEEDED - 1):
                return "BROKEN"
            return "WEAKENING"
        return "INTACT"

    # ── breadth_rolls_negative ───────────────────────────────────────────
    if kind == "breadth_rolls_negative":
        # N2 NOTE: reads legacy `revision_breadth`; the stage may have been decided on
        # breadth_cov. Since it is a sign test the practical risk is low — see
        # `late_line_basis` at open time in the thesis header for future use.
        rb = (current_row or {}).get("revision_breadth")
        if rb is None:
            return "UNVERIFIABLE"
        current_neg = float(rb) < 0
        prev_count = sum(
            1 for u in prior[-CONSECUTIVE_NEEDED:]
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
    asof: str | None = None,
) -> None:
    """Append a criterion-check update event (consecutive-build tracking).

    B2 FIX: each event row is stamped with the cascade `asof` it evaluated.
    The evaluator skips appending when (theme, criterion_kind, asof) already exists,
    so two same-day re-runs with identical cascade state produce only ONE event row.
    Old rows without `asof` are tolerated (treated as date(ts) for legacy compatibility).
    """
    try:
        event = {
            "kind": "update",
            "theme": theme,
            "criterion_kind": criterion_kind,
            "condition_met": condition_met,
            "status": status,
            "asof": asof,
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
    # B2b: track themes that go BROKEN this build so we can append close events
    newly_broken: list[str] = []

    for theme, det_rec in det_ledger.items():
        current_row = current_cascade.get(theme)
        conv_item = conv_current.get(theme)
        updates = _get_updates_for(det_rec)
        criteria = det_rec.get("kill_criteria") or []

        criterion_statuses: list[str] = []
        for crit in criteria:
            cstatus = _evaluate_criterion(
                crit, current_row, conv_item, updates, current_asof=today_asof
            )
            criterion_statuses.append(cstatus)
            # Append update event for consecutive-build tracking (only for trackable criteria)
            # B2 FIX: pass today_asof so the event row carries the cascade asof it evaluated;
            # the evaluator deduplicates by (criterion_kind, asof) to prevent double-counting.
            if crit.get("kind") in ("text_accel_negative", "band_loosens", "breadth_rolls_negative"):
                condition_met = cstatus in ("BROKEN", "WEAKENING")
                if write_state:
                    # B2 FIX: check if this (theme, criterion_kind, asof) already appended
                    already_logged = any(
                        u.get("criterion_kind") == crit["kind"] and u.get("asof") == today_asof
                        for u in updates
                    )
                    if not already_logged:
                        _append_update_event(
                            theme, crit["kind"], condition_met, cstatus, asof=today_asof
                        )

        thesis_status = _aggregate_criteria_status(criterion_statuses)

        if thesis_status == "BROKEN":
            newly_broken.append(theme)

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

    # B2b: append terminal close events for newly-BROKEN theses
    if write_state:
        for theme in newly_broken:
            _append_close_event(theme, reason="BROKEN")

    # ── Step 6: evaluate LLM theses (B3 FIX: fold onto deterministic row, not separate row) ──
    # B3: one monitored row per THEME — deterministic is canonical; LLM is enrichment.
    # Build a fast lookup of deterministic rows by theme.
    det_by_theme = {m["theme"]: m for m in monitored}

    n_llm_enriched = 0
    for theme, o in llm_opened.items():
        now = conv_current.get(theme) or {}
        heat_now = now.get("heat") or 0.0
        phys_now = bool(now.get("physical_confirmed"))
        n_now = now.get("n_signals") or 0
        llm_status = _status_llm(o, heat_now, phys_now, n_now)

        if theme in det_by_theme:
            # B3: fold LLM data as enrichment onto the existing deterministic row
            det_by_theme[theme].update({
                "llm_mechanism": o.get("mechanism"),
                "llm_status": llm_status,
                "llm_heat_at_open": o.get("heat_at_open"),
                "llm_heat_now": round(heat_now, 3),
                "llm_opened_asof": o.get("asof"),
                "llm_kill_criteria": o.get("kill_criteria"),
            })
            n_llm_enriched += 1
        else:
            # LLM-only thesis (no matching deterministic row) — add as standalone
            monitored.append({
                "theme": theme,
                "source": "llm",
                "status": llm_status,
                "heat_at_open": o.get("heat_at_open"),
                "heat_now": round(heat_now, 3),
                "n_surfaces_now": n_now,
                "physical_now": phys_now,
                "opened_asof": o.get("asof"),
                "kill_criteria": o.get("kill_criteria"),
            })
            n_llm_enriched += 1

    if not monitored:
        return None

    # ── Step 7: sort by severity ─────────────────────────────────────────
    order = {"BROKEN": 0, "UNVERIFIABLE": 1, "WEAKENING": 2, "INTACT": 3}
    monitored.sort(key=lambda m: order.get(m["status"], 4))

    # B3: counts are per-THEME (monitored rows are already deduped to one per theme)
    n_det = sum(1 for m in monitored if m["source"] == "deterministic")
    # n_llm = themes that have LLM enrichment (either standalone or folded onto deterministic)
    n_llm = n_llm_enriched

    # B2b: n_open counts OPEN theses only (closed theses were excluded from det_ledger)
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
            "(consecutive-build tracking, asof-deduped); LLM theses fold onto deterministic "
            "rows as enrichment when the theme overlaps. THESIS-BROKEN fires with zero LLM "
            "involvement; close event appended on BROKEN, closed theses excluded from n_open."
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
