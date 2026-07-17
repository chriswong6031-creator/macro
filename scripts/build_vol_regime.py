"""scripts/build_vol_regime.py — publish the validated index vol-regime.

Reads the long vol series we already hold (VIX 1990+, VIX3M, VIX9D, MOVE, CBOE SKEW,
SPY), builds engine/vol_regime, and writes:

  • site/vol/regime.json      — the snapshot + the plain-English game plan (drives the
                                Options Desk "market weather" hero and the macro pages).
  • site/vol/mastermind.json  — a compact options/vol CONTEXT block for the Mastermind
                                bot's lens layer (vol_regime.context.v1): the gated
                                risk-on/off score + the kill-switch regime + sizing
                                scalar, carrying the honesty frame in the payload.

The regime legs are SCORED only where data/vol_regime/gate.json (written by
scripts/validate_vol_regime.py) marks them earned; otherwise everything is display/context.
Additive + graceful: any missing series degrades a leg, never raises into the build.

RIC W3 addition: regime.json gains an 'opex_risk' block — the OPEX window risk read
from engine/opex_risk.py (n_hot/n_applicable, level, glance copy, state stack).
Display-only context; never read by compute(). Partial/absent surface data → nulls,
never a build failure.

Run: .venv/bin/python -m scripts.build_vol_regime
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from engine import opex, opex_risk, options_desk, vol_regime
from lib import config, store

log = logging.getLogger(__name__)


def _series(group: str, name: str, col: str = "close"):
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    s = df[col] if col in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index().astype(float)


def build() -> dict | None:
    """Build the regime payload (snapshot + game plan). Returns the dict, or None if the
    core VIX series is unavailable. Importable so build_gex_board reuses it without
    re-reading the store."""
    cfg = (config.load().get("engine", {}) or {}).get("vol_regime") or {}
    vix = _series("yahoo", "_VIX")
    if vix is None:
        log.warning("vol_regime: no VIX series — skipping")
        return None
    # VVIX: prefer the long CBOE history (collectors/cboe_indices.CboeVvixAdapter, 2006+);
    # fall back to the short yahoo _VVIX so the leg still appears until the CBOE series accrues.
    vvix = _series("cboe", "vvix", col="vvix")
    if vvix is None:
        vvix = _series("yahoo", "_VVIX")
    frame = vol_regime.build_frame(
        vix, _series("yahoo", "_VIX3M"), _series("yahoo", "_VIX9D"),
        _series("yahoo", "_MOVE"), _series("cboe", "skew", col="skew"),
        _series("yahoo", "SPY"), cfg, vvix=vvix)
    if frame.empty:
        return None
    snap = vol_regime.snapshot(frame, cfg)
    plan = options_desk.regime_game_plan(snap)
    spy = _series("yahoo", "SPY")
    opex_snap = None
    try:
        opex_snap = opex.snapshot(spy) if spy is not None else None
    except Exception as e:  # noqa: BLE001 — additive context, never fatal
        log.warning("vol_regime: opex snapshot failed: %s", e)
    # RIC W3: OPEX window risk read (display-only; null-safe; never fatal)
    opex_risk_snap = None
    try:
        opex_risk_snap = opex_risk.snapshot(spy_close=spy)
    except Exception as e:  # noqa: BLE001
        log.warning("vol_regime: opex_risk snapshot failed: %s", e)
    return {"schema": "vol_regime.v1", "asof": snap.get("asof"),
            "snapshot": snap, "game_plan": plan, "opex": opex_snap,
            "opex_risk": opex_risk_snap,
            "built": str(date.today())}


def mastermind_block(payload: dict) -> dict:
    """Compact options/vol CONTEXT block for the Mastermind lens layer. Index-level
    (robust); single-name gamma stays out. Carries the doctrine so the bot can't mistake
    a display read for a validated one."""
    snap = (payload or {}).get("snapshot") or {}
    return {
        "schema": "vol_regime.context.v1",
        "asof": snap.get("asof"),
        "regime": snap.get("regime"),
        "risk_score": snap.get("risk_score"),       # display composite
        "scored_score": snap.get("scored_score"),   # gated — None until earned
        "scored_active": snap.get("scored_active"),
        "ts_slope": snap.get("ts_slope"),
        "ts_slope_state": snap.get("ts_slope_state"),
        "move_pctile": snap.get("move_pctile"),
        "vrp_pctile": snap.get("vrp_pctile"),
        "vrp_state": snap.get("vrp_state"),
        "insurance_cost": snap.get("insurance_cost"),
        "vol_target_scalar": snap.get("vol_target_scalar"),
        "fragility_confluence": snap.get("fragility_confluence"),
        "kill_switch": snap.get("regime") == "backwardation-stress",
        "doctrine": snap.get("doctrine"),
        "use": ("CONTEXT lens only — a validated index vol-regime drives a subtract-only "
                "risk/sizing nudge (never sizes alone). Single-name dealer-gamma is display-only."),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    payload = build()
    if payload is None:
        log.error("vol_regime: nothing to write")
        return 0
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out = site / "vol"
    out.mkdir(parents=True, exist_ok=True)
    (out / "regime.json").write_text(json.dumps(payload, separators=(",", ":"), default=float))
    (out / "mastermind.json").write_text(
        json.dumps(mastermind_block(payload), separators=(",", ":"), default=float))
    snap = payload["snapshot"]
    log.info("vol_regime: %s regime=%s risk=%s scored=%s vt=%s",
             snap.get("asof"), snap.get("regime"), snap.get("risk_score"),
             snap.get("scored_score"), snap.get("vol_target_scalar"))
    # RIC W3: log the OPEX window entry to the forward ledger (nightly lane only;
    # lane gate is enforced inside log_window — off-lane = silent no-op).
    or_snap = payload.get("opex_risk")
    if or_snap:
        try:
            opex_risk.log_window(or_snap)
        except Exception as e:  # noqa: BLE001
            log.warning("vol_regime: opex_risk.log_window failed: %s", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
