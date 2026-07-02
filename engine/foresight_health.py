"""Foresight Desk data-health surface — P0-D of the upgrade programme.

`compute_foresight_health` derives per-leg status from the already-computed payloads
(pure function — does NOT re-run any engine).  The result is emitted into the cascade
JSON and rendered as a compact status strip on foresight.html so users can tell a live
machine from a dead one.

Status enum per leg:
  LIVE    — the leg has genuine, non-degenerate data today
  PARTIAL — the leg has partial data (n/m counts surfaced in the `detail` key)
  DARK    — the leg is absent / all-AWAITING / all-None — no real read

Top-level:
  n_leading_live  — count of LEADING legs (t1_fred, t1_text, t2_demand, t3_guidance,
                    power) with status LIVE or PARTIAL
  mode            — "FULL" if any of t1_fred / t1_text is LIVE or PARTIAL;
                    "CONFIRMER-ONLY" otherwise

Append-only log: one JSON line per build to data/foresight/health_log.jsonl (deduped
by date; created if absent).

Degrade gracefully — any missing / None input → that leg DARK, never raises.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_AWAITING = {"AWAITING_DATA", "INSUFFICIENT_HISTORY"}
_TIGHT_BANDS = {"TIGHT", "SOLD_OUT", "TIGHTENING"}
_GLUT_BANDS = {"GLUT_FORMING", "GLUT", "TIGHTENING", "LOOSE", "BALANCED",
               "GLUT_FORMING (text)", "EARLY_GLUT", "STABLE"}
_REAL_DEMAND = {"ACCELERATING", "STEADY", "COOLING", "CONTRACTING"}
_REAL_GUIDANCE = {"RAISING", "BROAD-RAISE", "CUTTING", "NEUTRAL"}
_REAL_BB = {"TIGHT", "SOLD_OUT", "TIGHTENING", "LOOSE", "BALANCED"}


def _leg(status: str, detail: str | None, why: str) -> dict:
    return {"status": status, "detail": detail, "why": why}


def _assess_t1_fred(themes: list[dict]) -> dict:
    """T1 FRED bottleneck bands: count themes with a real (non-AWAITING/None) band."""
    if not themes:
        return _leg("DARK", None,
                    "no themes — cascade returned nothing")
    real = [t for t in themes
            if t.get("bottleneck_band") not in (None, *_AWAITING)]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a physical band — FRED capacity/PPI series "
                    "not yet collected (see config.yml bottleneck+power groups)")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}",
                    f"{n}/{m} themes have a physical band; {m - n} still AWAITING_DATA")
    return _leg("LIVE", f"{n}/{m}",
                f"all {n} themes have a physical bottleneck band")


def _assess_t1_text(themes: list[dict]) -> dict:
    """T1 text leg: EDGAR language accel (sold-out / on-allocation), leg6_language.

    W1a wired: bottleneck.py now includes leg6_language in legs/WEIGHTS (0.25, PROVISIONAL).
    Assessment:
      LIVE    — ≥1 theme has a non-null language read (bottleneck_band not None/AWAITING_DATA,
                OR bottleneck_text_only is True) indicating the parquet has data and is wired
      PARTIAL — parquet exists and the collector has run but <18 themes have a language read
      DARK    — data/edgar/bottleneck_hits.parquet absent or stale / no affirmative hits

    We detect LIVE from the cascade themes: any theme with bottleneck_text_only=True or
    any non-None bottleneck_band that is a text-only band implies the language leg fired.
    Fallback: check parquet existence directly.
    """
    # Count themes with any evidence of the language leg being active
    text_bands = {"TIGHT (text)", "TIGHTENING (text)"}
    n_text = sum(1 for t in themes
                 if t.get("bottleneck_text_only") or t.get("bottleneck_band") in text_bands)

    if themes:
        # Cascade was computed: use the theme fields as ground truth (they reflect the
        # engine's actual output; parquet checks would double-count or diverge).
        n, m = n_text, len(themes)
        detail = f"{n}/{m}"
        if n_text > 0:
            if n_text < m:
                return _leg("PARTIAL", detail,
                            f"{n}/{m} themes have an active text-only band (TIGHT (text) / "
                            "TIGHTENING (text)) — leg6_language wired, parquet live, "
                            "weight 0.25 PROVISIONAL (shadow-calibration pending)")
            return _leg("LIVE", detail,
                        f"all {n} themes have a language read — leg6_language wired at 0.25 "
                        "(PROVISIONAL); polarity=null (fallback b — no snippet from EDGAR FTS)")
        # No text bands in the cascade — parquet may exist but threshold not cleared
        return _leg("DARK", f"0/{m}",
                    f"leg6_language wired but 0/{m} themes have a text-only band — "
                    "parquet may be absent, empty, or no theme cleared the ≥2-distinct-filer "
                    "threshold in the current window")

    # No themes passed (cascade=None or empty) — no cascade means we cannot assess the
    # language leg's contribution. Return DARK; a running cascade is required.
    return _leg("DARK", None,
                "cascade not provided — cannot assess t1_text without cascade theme data")


def _assess_t2_demand(themes: list[dict]) -> dict:
    """T2 demand: demand_band present on any theme."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes if t.get("demand_band") in _REAL_DEMAND]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a demand_band — hyperscaler capex pool absent")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}",
                    f"{n}/{m} themes have a demand read; {m - n} not capex-linked")
    return _leg("LIVE", f"{n}/{m}", f"all {n} themes have a demand read")


def _assess_t3_guidance(themes: list[dict]) -> dict:
    """T3 guidance: guidance_band present on any theme."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes if t.get("guidance_band") in _REAL_GUIDANCE]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a guidance_band — 8-K guidance sweep absent or no tilts")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}",
                    f"{n}/{m} themes have a guidance read")
    return _leg("LIVE", f"{n}/{m}", f"all {n} themes have a guidance read")


def _assess_t4_level(themes: list[dict]) -> dict:
    """T4 revision-breadth level: revision_breadth present."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes if t.get("revision_breadth") is not None]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}", f"0/{m} themes have revision_breadth")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}", f"{n}/{m} themes have revision_breadth")
    return _leg("LIVE", f"{n}/{m}", f"all {n} themes have revision_breadth (level)")


def _assess_t4_accel(themes: list[dict]) -> dict:
    """T4 broadening_state: at least one theme NOT in _AWAITING states."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes
            if t.get("broadening_state") not in (None, *_AWAITING)]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a broadening_state — revision history < 21 days "
                    "(ACCEL_LOOKBACK_DAYS=21; revisions archive too young)")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}",
                    f"{n}/{m} themes have a broadening direction read")
    return _leg("LIVE", f"{n}/{m}", f"all {n} themes have a broadening direction read")


def _assess_glut(themes: list[dict]) -> dict:
    """Glut bands: at least one non-AWAITING/None glut_band."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes
            if t.get("glut_band") not in (None, *_AWAITING)]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a glut_band — glut engine needs the same "
                    "FRED series as T1 (dark for the same reason)")
    if n < m:
        return _leg("PARTIAL", f"{n}/{m}", f"{n}/{m} themes have a glut read")
    return _leg("LIVE", f"{n}/{m}", f"all {n} themes have a glut read")


def _assess_power(power: object) -> dict:
    """Power scarcity: payload not None and band not AWAITING."""
    if power is None:
        return _leg("DARK", None,
                    "power_scarcity returned None — FRED electricity/utility series "
                    "absent (IPG2211S, CAPUTLG2211S, WPU0543 not collected)")
    band = (power if isinstance(power, dict) else {}).get("band")
    if not band or band in _AWAITING:
        return _leg("DARK", None,
                    f"power payload present but band={band!r} — "
                    "still AWAITING FRED power-group collection")
    return _leg("LIVE", band,
                f"power scarcity live: band={band}")


def _assess_confirmers(themes: list[dict]) -> dict:
    """Alt-data confirmers: any altdata_summary present."""
    if not themes:
        return _leg("DARK", None, "no themes")
    real = [t for t in themes if t.get("altdata_summary")]
    n, m = len(real), len(themes)
    if n == 0:
        return _leg("DARK", f"0/{m}", f"0/{m} themes have an alt-data confirmer summary")
    return _leg("PARTIAL" if n < m else "LIVE", f"{n}/{m}",
                f"{n}/{m} themes have an alt-data confirmer read")


def _assess_analyst(analyst: object) -> dict:
    """LLM analyst: payload not None."""
    if analyst is None:
        return _leg("DARK", None,
                    "analyst payload absent — no Anthropic credential (graceful no-op; "
                    "desk functions without LLM)")
    if not (analyst if isinstance(analyst, dict) else {}).get("regime_read"):
        return _leg("PARTIAL", None, "analyst payload present but regime_read absent")
    return _leg("LIVE", None, "LLM analyst read present")


def _assess_t1_fingerprint(themes: list[dict]) -> dict:
    """T1 XBRL fingerprint (W5a): per-theme member-level inventory-days + RPO legs.

    Status:
      LIVE    — ≥1 theme has fingerprint n_legs_live ≥ 2 (both legs from its own members)
      PARTIAL — ≥1 theme has fingerprint n_legs_live == 1 (only one leg active)
      DARK    — no theme has any fingerprint data (statements.parquet absent or
                no theme reaches the MIN_MEMBERS=3 gate for any leg)

    The detail string surfaces n_themes_live/n_total (themes with ≥1 fingerprint leg).
    Annual-cadence honesty: fingerprint is labeled "annual" in the payload.
    """
    if not themes:
        return _leg("DARK", None, "no themes")

    full_live = [t for t in themes
                 if (t.get("fingerprint") or {}).get("n_legs_live", 0) >= 2]
    partial_live = [t for t in themes
                    if (t.get("fingerprint") or {}).get("n_legs_live", 0) == 1]
    total_with_fp = len(full_live) + len(partial_live)
    m = len(themes)

    if total_with_fp == 0:
        return _leg("DARK", f"0/{m}",
                    f"0/{m} themes have a fingerprint leg — statements.parquet coverage "
                    "may be thin or MIN_MEMBERS=3 gate not met for any theme; "
                    "RPO coverage thin (software/agents baskets only)")
    if full_live:
        detail = f"{total_with_fp}/{m} ({len(full_live)} both legs)"
        status = "LIVE" if total_with_fp == m else "PARTIAL"
        return _leg(status, detail,
                    f"{len(full_live)}/{m} themes have both fingerprint legs (inv-days + RPO); "
                    f"{len(partial_live)} have 1 leg; basis=annual; weights PROVISIONAL")
    # Only partial-live themes (1 leg each)
    return _leg("PARTIAL", f"{total_with_fp}/{m}",
                f"{total_with_fp}/{m} themes have 1 fingerprint leg (inventory-days only — "
                "RPO coverage thin for non-software themes); basis=annual; weights PROVISIONAL")


def _assess_monitor(monitor: object) -> dict:
    """Thesis monitor: payload not None."""
    if monitor is None:
        return _leg("DARK", None,
                    "thesis monitor absent — no theses to monitor yet "
                    "(monitor is only meaningful once PRECIPICE/BROADENING flags exist)")
    # real thesis_monitor payload keys: "n_open" (count) + "monitored" (list) — NOT "theses"
    md = monitor if isinstance(monitor, dict) else {}
    n_th = md.get("n_open") or len(md.get("monitored") or [])
    if n_th == 0:
        return _leg("PARTIAL", "0 theses",
                    "monitor present but 0 active theses — fires once a thesis stage is logged")
    return _leg("LIVE", f"{n_th} theses", f"monitor watching {n_th} active thesis/theses")


def _assess_grading(track: object) -> dict:
    """Track record: any rows logged in data/foresight/log.jsonl."""
    if track is None:
        return _leg("DARK", None, "no track-record data passed")
    n = (track if isinstance(track, dict) else {}).get("foresight", 0)
    if n == 0:
        return _leg("DARK", "0 rows",
                    "0 cascade flags logged — PRECIPICE/BROADENING have never fired; "
                    "ledger accrues once a thesis stage is reachable")
    return _leg("LIVE", f"{n} rows", f"{n} cascade flag rows logged (forward-grading accruing)")


def compute_foresight_health(
    cascade: dict | None = None,
    emergence: object = None,
    subsectors: object = None,
    convergence: object = None,
    power: object = None,
    analyst: object = None,
    monitor: object = None,
    track: object = None,
) -> dict:
    """Derive per-leg operational status from already-computed payloads.

    Parameters mirror the build_foresight.py call-site variables.  All are optional;
    any None input yields DARK for that leg — never raises.

    Returns a dict suitable for JSON serialisation and Jinja2 template consumption.
    """
    try:
        themes: list[dict] = (cascade or {}).get("themes") or []
    except Exception:  # noqa: BLE001
        themes = []

    try:
        legs = {
            "t1_fred":         _assess_t1_fred(themes),
            "t1_text":         _assess_t1_text(themes),
            "t1_fingerprint":  _assess_t1_fingerprint(themes),   # W5a XBRL member fingerprints
            "t2_demand":       _assess_t2_demand(themes),
            "t3_guidance":     _assess_t3_guidance(themes),
            "t4_level":        _assess_t4_level(themes),
            "t4_accel":        _assess_t4_accel(themes),
            "glut":            _assess_glut(themes),
            "power":           _assess_power(power),
            "confirmers":      _assess_confirmers(themes),
            "analyst":         _assess_analyst(analyst),
            "monitor":         _assess_monitor(monitor),
            "grading":         _assess_grading(track),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("foresight_health: leg assessment failed: %s", exc)
        legs = {}

    LEADING_LEGS = ("t1_fred", "t1_text", "t1_fingerprint", "t2_demand", "t3_guidance", "power")
    try:
        n_leading_live = sum(
            1 for k in LEADING_LEGS
            if legs.get(k, {}).get("status") in ("LIVE", "PARTIAL")
        )
        # FULL if either of the two primary physical leads has any life
        t1_alive = any(
            legs.get(k, {}).get("status") in ("LIVE", "PARTIAL")
            for k in ("t1_fred", "t1_text")
        )
        mode = "FULL" if t1_alive else "CONFIRMER-ONLY"
    except Exception:  # noqa: BLE001
        n_leading_live = 0
        mode = "CONFIRMER-ONLY"

    result = {
        "legs": legs,
        "n_leading_live": n_leading_live,
        "mode": mode,
        "n_themes": len(themes),
    }

    # Append-only daily log — dedup by date
    try:
        _append_health_log(result)
    except Exception as exc:  # noqa: BLE001
        log.warning("foresight_health: log append failed (non-fatal): %s", exc)

    return result


# ---------------------------------------------------------------------------
# Append-only health log
# ---------------------------------------------------------------------------

def _health_log_path() -> Path:
    try:
        from lib import config  # noqa: PLC0415
        return config.data_dir() / "foresight" / "health_log.jsonl"
    except Exception:  # noqa: BLE001
        return Path("data") / "foresight" / "health_log.jsonl"


def _append_health_log(health: dict) -> None:
    """Append one line per calendar day (dedup by date)."""
    p = _health_log_path()
    today = date.today().isoformat()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Check for existing entry today
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                if json.loads(line).get("date") == today:
                    return  # already logged today
            except Exception:  # noqa: BLE001
                continue
    record = {
        "date": today,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": health.get("mode"),
        "n_leading_live": health.get("n_leading_live"),
        "n_themes": health.get("n_themes"),
        "legs": {k: v.get("status") for k, v in (health.get("legs") or {}).items()},
    }
    with p.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
