"""Long-Hold Lobe panel — operator HQ view.

Reads committed JSON artifacts only (no engine imports, no parquet, no subprocess).
Fail-open on every artifact: missing/corrupt -> the relevant sub-block carries
{"available": False, "reason": ...} but panel() always returns {"ok": True, ...}.

Primary artifact: data/research/winner_autopsy_panel.json
  (written by scripts/research/build_winner_autopsy.py — runs on Mac host backfill /
  nightly; not present in fresh CI checkouts or worktrees).

Secondary artifacts (optional supplementary data):
  data/research/thesis_funnel_states_manifest.json  — funnel population + state counts
  data/research/long_hold_labels_manifest.json      — label distribution
  data/research/falsifier_packets_manifest.json     — A1 packet build summary (LHB-W3)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .paths import DATA

# ---------------------------------------------------------------------------
# Module-level path constants — monkeypatched in tests
# ---------------------------------------------------------------------------
_WINNER_PANEL = DATA / "research" / "winner_autopsy_panel.json"
_THESIS_FUNNEL = DATA / "research" / "thesis_funnel_states_manifest.json"
_LABELS = DATA / "research" / "long_hold_labels_manifest.json"
_WATERFALL = DATA / "research" / "delivery_waterfall_panel.json"
_FALSIFIER_PACKETS_MANIFEST = DATA / "research" / "falsifier_packets_manifest.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _age_hours(stamp: str | None) -> float | None:
    """Return hours since an ISO-8601 stamp, or None on any problem."""
    if not stamp:
        return None
    try:
        # Accept both "2026-07-07T08:00:00Z" and "2026-07-07 08:00" forms
        s = str(stamp).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
    except Exception:  # noqa: BLE001
        return None


def _read_json(path) -> dict | None:
    """Read + parse JSON from path. Returns None on any error."""
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Sub-block extractors (each fail-open)
# ---------------------------------------------------------------------------

def _winner_autopsy(raw: dict) -> dict:
    """Extract the display-ready winner_autopsy sub-block from the raw panel."""
    try:
        census_raw = raw.get("census") or {}
        census: dict = {
            "available": census_raw.get("available", False),
            "n_episodes": census_raw.get("n_episodes"),
            "date_range": census_raw.get("date_range"),
            "universe_n_tickers": census_raw.get("universe_n_tickers"),
            "outcome_label_counts": census_raw.get("outcome_label_counts", {}),
            "by_era": census_raw.get("by_era", []),
            "notes": census_raw.get("notes", []),
        }

        cases_raw = raw.get("cases") or {}
        # Trim each case to the display fields; leave all other keys available too.
        items = []
        for item in (cases_raw.get("items") or []):
            if not isinstance(item, dict):
                continue
            items.append({
                "ticker":          item.get("ticker"),
                "episode_year":    item.get("episode_year"),
                "case_type":       item.get("case_type"),
                "mechanism":       item.get("mechanism"),
                "thesis_one_liner": item.get("thesis_one_liner"),
                "n_catalysts":     item.get("n_catalysts"),
                "case_t0":         item.get("case_t0"),
                "case_joined":     item.get("case_joined"),
                "reconcile":       item.get("reconcile"),
                "file":            item.get("file"),
            })
        cases = {
            "n_cases": cases_raw.get("n_cases", len(items)),
            "items": items,
        }

        watch_raw = raw.get("watch") or {}
        # Trim watch.top to display columns only (no composite score per WA-R1)
        top_raw = watch_raw.get("top") or []
        top = []
        for row in top_raw[:15]:
            if not isinstance(row, dict):
                continue
            top.append({
                "ticker":         row.get("ticker"),
                "sector":         row.get("sector"),
                "benchmark":      row.get("benchmark"),
                "state":          row.get("state"),
                "excess_21d_pp":  row.get("excess_21d_pp"),
                "new_high_63d":   row.get("new_high_63d"),
                "dollar_vol_z21": row.get("dollar_vol_z21"),
                "hazards":        row.get("hazards", []),
            })
        watch = {
            "available":    watch_raw.get("available", False),
            "as_of":        watch_raw.get("as_of"),
            "state_counts": watch_raw.get("state_counts", {}),
            "top":          top,
        }

        clocks = raw.get("clocks") or []

        return {
            "available": True,
            "display_only": raw.get("display_only", True),
            "horizon_role": raw.get("horizon_role"),
            "census": census,
            "cases": cases,
            "watch": watch,
            "clocks": clocks,
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "parse_error"}


def _thesis_funnel_block() -> dict:
    """Read thesis_funnel_states_manifest.json. Fail-open."""
    raw = _read_json(_THESIS_FUNNEL)
    if raw is None:
        return {"available": False, "reason": "thesis_funnel_states_manifest.json not found"}
    try:
        return {
            "available":    True,
            "as_of":        raw.get("as_of"),
            "population":   raw.get("n_tickers"),
            "state_counts": raw.get("state_counts", {}),
            "notes":        raw.get("notes"),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "parse_error"}


def _labels_block() -> dict:
    """Read long_hold_labels_manifest.json. Fail-open."""
    raw = _read_json(_LABELS)
    if raw is None:
        return {"available": False, "reason": "long_hold_labels_manifest.json not found"}
    try:
        return {
            "available":    True,
            "generated_at": raw.get("generated_at"),
            "distribution": raw.get("label_distribution", {}),
            "population":   raw.get("population", {}),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "parse_error"}


def _waterfall_block() -> dict:
    """Read delivery_waterfall_panel.json. Fail-open (mirrors _thesis_funnel_block pattern)."""
    raw = _read_json(_WATERFALL)
    if raw is None:
        return {"available": False, "reason": "delivery_waterfall_panel.json not found"}
    try:
        return {
            "available":      True,
            "generated_at":   raw.get("generated_at"),
            "as_of":          raw.get("as_of"),
            "counts":         raw.get("counts", {}),
            "rows":           raw.get("rows", []),
            "refused_examples": raw.get("refused_examples", []),
            "notes":          raw.get("coverage_notes"),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "parse_error"}


def _falsifier_packets_block() -> dict:
    """Read falsifier_packets_manifest.json (LHB-W3 A1 packet summary). Fail-open.

    Follows the _waterfall_block pattern exactly. Reads the manifest only —
    the full per-ticker packets JSON is too large for the panel; the manifest
    carries all summary counts and metadata needed for admin display.

    DISPLAY-ONLY. Tier-3 admin surface (LHB-R2). Raw enums legal here only.
    """
    raw = _read_json(_FALSIFIER_PACKETS_MANIFEST)
    if raw is None:
        return {
            "available": False,
            "reason": "falsifier_packets_manifest.json not found",
        }
    try:
        return {
            "available":             True,
            "generated_at":          raw.get("generated_at"),
            "n_tickers":             raw.get("n_tickers"),
            "n_with_signal":         raw.get("n_with_signal"),
            "n_summary_only":        raw.get("n_summary_only"),
            "sensor_status_counts":  raw.get("sensor_status_counts", {}),
            "a6_item_counts":        raw.get("a6_item_counts", {}),
            "elapsed_seconds":       raw.get("elapsed_seconds"),
            "ffb_r2_coverage_copy":  (
                "Advance review in 7 of 12 studied true breaks; 5 of 12 were visible only "
                "coincident with the break. A6 is a hard-stop bus, not a lead generator."
            ),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "parse_error"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def panel() -> dict:
    """Long-Hold Lobe operator panel. Never raises."""
    # Primary: winner autopsy panel
    raw = _read_json(_WINNER_PANEL)

    if raw is None:
        winner_autopsy: dict = {
            "available": False,
            "reason": (
                "winner_autopsy_panel.json not yet written "
                "(runs on Mac host backfill / nightly)"
            ),
        }
        generated_at = None
        age_hours = None
    else:
        winner_autopsy = _winner_autopsy(raw)
        generated_at = raw.get("generated_at")
        age_hours = _age_hours(generated_at)

    return {
        "ok":                True,
        "generated_at":      generated_at,
        "age_hours":         age_hours,
        "winner_autopsy":    winner_autopsy,
        "thesis_funnel":     _thesis_funnel_block(),
        "labels":            _labels_block(),
        "delivery_waterfall": _waterfall_block(),
        "falsifier_packets": _falsifier_packets_block(),
    }
