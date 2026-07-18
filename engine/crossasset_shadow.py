"""Cross-Asset Shadow Escalator — CA-W3-B (2026-07-18).

Shadow lane for the US market mirroring CGL-R4 escalation mechanics exactly.

Public API: run(root=None) -> dict | None

Spec: research/NW_CROSSASSET_DEPTH_MASTERPLAN.md §7.3, rulings CA-W3-R1/R2.

Construction:
  - pressure  = absorption_pctile_5y from data/regime/latest.json["cross_asset"]
                (Kritzman-Page one-bet fragility; continuous gauge, NOT K-of-N — CA-W3-R2)
  - incumbent = US risk-radar state from data/risk_radar/forward_log.jsonl (last row)
                (same source contagion_links uses for the US incumbent — _incumbent_state("us"))
  - shadow    = incumbent + 1 band iff pressure >= 0.90 AND incumbent >= "watch",
                capped at "risk-off"; never a new origin scare; below-watch NEVER escalates
  - escalated = shadow_state != incumbent_state

Artifacts:
  - data/crossasset_shadow/latest.json (always written on armed lane when inputs present)
  - data/risk_radar/forward_log_crossasset.jsonl (forward log, armed-lane-only, dedup on asof)

Fail-open: any missing input → log.warning + return None. Never raises into the build.

Display-only: display_only=True in latest.json. Promotion to authority requires
>=30 graded shadow rows + do-no-harm vs incumbent (earliest review 2026-10-17, CA-W3-R1).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

# Band ladder — identical to contagion_links._STATE_ORDER (CGL-R4 frozen construction)
_STATE_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]

_FORWARD_LOG_NAME = "forward_log_crossasset.jsonl"
_LATEST_NAME = "latest.json"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _data_base(root=None) -> Path:
    return config.data_dir() if root is None else (Path(root) / "data")


def _regime_path(root=None) -> Path:
    return _data_base(root) / "regime" / "latest.json"


def _fwd_log_path(root=None) -> Path:
    p = _data_base(root) / "risk_radar" / _FORWARD_LOG_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _latest_path(root=None) -> Path:
    p = _data_base(root) / "crossasset_shadow" / _LATEST_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Lane-arming check — identical gate as engine/risk_radar_audit.ledger_lane_armed
# ---------------------------------------------------------------------------

def _lane_armed() -> bool:
    """True only on COLLECT_LANE=nightly (or legacy US_LANE=nightly).

    Mirrors engine.risk_radar_audit.ledger_lane_armed exactly — nightly is the
    sole advancer of data/ forward ledgers (house law).
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return rows


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _read_pressure(root=None) -> float | None:
    """Read absorption_pctile_5y from data/regime/latest.json["cross_asset"].

    Returns None on any read/key error (fail-open).
    """
    try:
        payload = json.loads(_regime_path(root).read_text(encoding="utf-8"))
        ca = payload.get("cross_asset") or {}
        val = ca.get("absorption_pctile_5y")
        if val is None:
            log.warning("crossasset_shadow: absorption_pctile_5y missing from regime/latest.json cross_asset block")
            return None
        return float(val)
    except Exception as exc:  # noqa: BLE001
        log.warning("crossasset_shadow: could not read pressure from regime/latest.json: %s", exc)
        return None


def _read_incumbent(root=None) -> tuple[str | None, str | None]:
    """Read US incumbent state from data/risk_radar/forward_log.jsonl (last row).

    Returns (state, asof) or (None, None) on missing/empty (fail-open).
    Mirrors contagion_links._incumbent_state("us") exactly.
    """
    try:
        fwd_log = _data_base(root) / "risk_radar" / "forward_log.jsonl"
        rows = _read_jsonl(fwd_log)
        if not rows:
            log.warning("crossasset_shadow: forward_log.jsonl empty or missing — incumbent unavailable")
            return None, None
        last = rows[-1]
        state = last.get("state")
        asof = last.get("asof")
        return state, asof
    except Exception as exc:  # noqa: BLE001
        log.warning("crossasset_shadow: could not read incumbent from forward_log.jsonl: %s", exc)
        return None, None


def _shadow_state(pressure_pct: float, incumbent: str | None) -> str | None:
    """Apply CGL-R4 escalation rule verbatim (CA-W3-R2).

    escalate iff pressure_pct >= 0.90 AND incumbent >= "watch"
    escalation = incumbent + 1 band, capped at "risk-off".
    Below-watch incumbents NEVER escalate.
    """
    if incumbent is None:
        return None
    if incumbent not in _STATE_ORDER:
        return incumbent  # unknown state — pass through, fail-open
    if pressure_pct >= 0.90:
        idx = _STATE_ORDER.index(incumbent)
        if idx >= _STATE_ORDER.index("watch"):  # >= watch → escalate
            return _STATE_ORDER[min(idx + 1, len(_STATE_ORDER) - 1)]
    return incumbent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(root=None) -> dict | None:
    """Compute the cross-asset shadow state for the US market.

    Reads:
      - data/regime/latest.json["cross_asset"]["absorption_pctile_5y"]
      - data/risk_radar/forward_log.jsonl (last row, US incumbent state)

    Writes (when lane is armed — COLLECT_LANE=nightly):
      - data/crossasset_shadow/latest.json
      - data/risk_radar/forward_log_crossasset.jsonl (dedup on asof)

    Returns:
      {pressure_pctile, incumbent_state, shadow_state, escalated}
      or None if any required input is missing.
    """
    # --- Read inputs (both fail-open → None on error) ---
    pressure = _read_pressure(root)
    if pressure is None:
        return None

    incumbent, incumbent_asof = _read_incumbent(root)
    if incumbent is None:
        return None

    # --- Compute shadow state (CGL-R4 mirror) ---
    shadow = _shadow_state(pressure, incumbent)
    escalated = bool(shadow != incumbent)

    asof_str = (
        incumbent_asof
        if incumbent_asof
        else datetime.now(timezone.utc).date().isoformat()
    )
    built_at = datetime.now(timezone.utc).isoformat()

    # --- Compact return dict ---
    result = {
        "pressure_pctile":  pressure,
        "incumbent_state":  incumbent,
        "shadow_state":     shadow,
        "escalated":        escalated,
    }

    # --- Persistence: only when lane is armed ---
    if not _lane_armed():
        log.debug(
            "crossasset_shadow: lane not armed; returning in-memory only "
            "(pressure=%.3f incumbent=%s shadow=%s)",
            pressure, incumbent, shadow,
        )
        return result

    # --- Write latest.json ---
    try:
        latest = {
            "asof":             asof_str,
            "market":           "us",
            "pressure_pctile":  pressure,
            "incumbent_state":  incumbent,
            "shadow_state":     shadow,
            "escalated":        escalated,
            "display_only":     True,
            "note": (
                "Shadow test lane only — not a live radar authority. "
                "Promotion gated on >=30 graded shadow rows + do-no-harm vs incumbent "
                "(earliest review 2026-10-17, CA-W3-R1)."
            ),
            "built_at":         built_at,
        }
        lp = _latest_path(root)
        lp.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
        log.debug("crossasset_shadow: wrote latest.json (shadow=%s escalated=%s)", shadow, escalated)
    except Exception as exc:  # noqa: BLE001
        log.warning("crossasset_shadow: failed to write latest.json: %s", exc)

    # --- Forward log append (dedup on asof) ---
    try:
        fwd_path = _fwd_log_path(root)
        existing_asofs = {r.get("asof") for r in _read_jsonl(fwd_path)}
        if asof_str not in existing_asofs:
            dom_scare = "cross_asset_escalation" if escalated else f"incumbent:{incumbent}"
            row = {
                "asof":             asof_str,
                "market":           "us",
                "state":            shadow,
                "incumbent_state":  incumbent,
                "pressure_pct":     pressure,
                "escalated":        escalated,
                "top_score":        None,
                "dominant_scare":   dom_scare,
                "graded":           None,
                "bench_path":       None,
            }
            with fwd_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            log.debug("crossasset_shadow: appended forward_log row asof=%s", asof_str)
        else:
            log.debug("crossasset_shadow: forward_log already has asof=%s — skipping (dedup)", asof_str)
    except Exception as exc:  # noqa: BLE001
        log.warning("crossasset_shadow: failed to append forward log: %s", exc)

    return result
