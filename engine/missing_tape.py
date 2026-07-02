"""engine/missing_tape.py — Missing-Tape v0 Orchestrator + Artifact Emitter.

Spec: research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md D8 §4 W4, Appendix P4.

Combines the three Missing-Tape legs into one display-only artifact:
    site/chinadata/missing_tape.json

and registers salience-only qledger claims (desk=missing_tape, family=missing_tape,
ladder_state=SHADOW per qual_ladder.yml) so even the risk flag accrues a forward
track record.

Artifact schema (spec D8):
    {
      "schema":        "missing_tape.v0",
      "as_of":         "YYYY-MM-DD",
      "deletion_rate": float,          # fraction of recrawled TIER1 rows that are "gone"
      "divergence_z":  float | null,   # latest onshore/offshore GDELT z (NaN → null)
      "flags": [                       # attention-collapse anomalies
        {
          "subject":    str,
          "cn_z":       float,
          "en_z":       float,
          "confidence": "HIGH" | "MED" | "LOW",   # LOW | MED | HIGH
          "today_cn":   int,
          "today_en":   int,
        },
        ...
      ],
      "risk_level":    "NONE" | "ELEVATED" | "HIGH",
      "is_context_only": true,         # NEVER a positive signal; risk flag only
    }

risk_level derivation (display only):
    HIGH      — divergence_z ≥ 2.5 OR any HIGH-confidence attention flag.
    ELEVATED  — divergence_z ≥ 1.5 OR any MED-confidence attention flag.
    NONE      — otherwise.

NO page changes in this wave (W6/W7 surfaces the artifact).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

LOG = logging.getLogger("missing_tape")

ROOT = Path(__file__).resolve().parent.parent

_ARTIFACT_REL = ("site", "chinadata", "missing_tape.json")

# Thresholds for artifact-level risk_level
_Z_HIGH: float = 2.5
_Z_ELEVATED: float = 1.5


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _site_root() -> Path:
    return ROOT


def _artifact_path(site_root: Path) -> Path:
    p = site_root.joinpath(*_ARTIFACT_REL)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _nan_to_none(v: float) -> float | None:
    """Convert float NaN to None for JSON serialization."""
    if v is None:
        return None
    try:
        return None if math.isnan(v) else round(v, 4)
    except (TypeError, ValueError):
        return None


def _risk_level(divergence_z: float | None, flags: list[dict]) -> str:
    """Derive display-level risk from the three legs."""
    confidences = {f["confidence"] for f in flags}
    dz = divergence_z or 0.0

    if dz >= _Z_HIGH or "HIGH" in confidences:
        return "HIGH"
    if dz >= _Z_ELEVATED or "MED" in confidences:
        return "ELEVATED"
    return "NONE"


# --------------------------------------------------------------------------- #
# qledger claim registration (salience-only; direction=0)
# --------------------------------------------------------------------------- #
def _register_claim(asof: str, risk_level: str, divergence_z: float | None) -> None:
    """Register one salience-only qledger claim for the missing_tape desk.

    direction=0 throughout — RISK FLAG only, never a positive signal.
    timestamp_quality=SNAPSHOT_DATE — display-only, not an entry anchor.
    """
    try:
        from engine import qledger
    except Exception as exc:
        LOG.warning("qledger import failed, claim not registered: %s", exc)
        return

    claim = qledger.make_claim(
        desk="missing_tape",
        asof=asof,
        scope_type="macro",
        scope_key="CN_CENSORSHIP_RISK",
        direction=0,          # salience-only; direction is never a positive signal
        horizon_d=21,         # accrual horizon for the forward log
        timestamp_quality="SNAPSHOT_DATE",  # display-only snapshot
        # W4 ITEM 3: bench changed from "SPY" to "510300.SS" — the machine-checkable
        # China A-share benchmark used by communique_diff desk for macro scope claims.
        # "SPY" was rejected by qledger D4 for scope=macro CN_CENSORSHIP_RISK claims.
        bench="510300.SS",
        falsifier=(
            "divergence_z consistently < 1.0 over 63d AND zero HIGH-confidence "
            "attention-collapse flags AND zero gone/edited recrawl rows"
        ),
        claim_family="missing_tape",
        extra={
            "risk_level": risk_level,
            "divergence_z": _nan_to_none(divergence_z),
            "is_context_only": True,
        },
    )

    try:
        result = qledger.register(claim)
        LOG.info("qledger claim registered: claim_id=%s status=%s",
                 result.get("claim_id", "")[:16], result.get("status"))
    except Exception as exc:
        LOG.warning("qledger.register failed: %s", exc)


# --------------------------------------------------------------------------- #
# main emitter
# --------------------------------------------------------------------------- #
def emit(
    *,
    asof: date | None = None,
    data_root: Path | None = None,
    site_root: Path | None = None,
    dry_run: bool = False,
    register_claim: bool = True,
) -> dict:
    """Run all three legs and emit the artifact.

    Returns the artifact dict (for testing / callers that need the data).
    Never raises — any leg failure is gracefully degraded.
    """
    asof = asof or date.today()
    asof_str = asof.isoformat()
    data_root = data_root or _data_root()
    site_root = site_root or _site_root()

    # ---------- Leg A: deletion_rate from recrawl_log ----------
    deletion_rate = 0.0
    try:
        from scripts.recrawl_official_tape import deletion_rate as _dr, _data_root as _dr_root
        deletion_rate = _dr(data_root=data_root)
    except Exception as exc:
        LOG.warning("recrawl deletion_rate failed: %s", exc)

    # ---------- Leg B: divergence_z from GDELT series ----------
    divergence_z: float | None = None
    try:
        from engine.missing_tape_gdelt import latest_divergence_z
        raw_z = latest_divergence_z(data_root=data_root)
        divergence_z = _nan_to_none(raw_z)
    except Exception as exc:
        LOG.warning("divergence_z failed: %s", exc)

    # ---------- Leg C: attention-collapse flags ----------
    flags: list[dict] = []
    try:
        from engine.missing_tape_attention import detect_flags
        raw_flags = detect_flags(asof=asof, data_root=data_root)
        flags = [
            {k: v for k, v in f.items() if k != "asof"}
            for f in raw_flags
        ]
    except Exception as exc:
        LOG.warning("attention_collapse detect_flags failed: %s", exc)

    risk_level = _risk_level(divergence_z, flags)

    artifact = {
        "schema": "missing_tape.v0",
        "as_of": asof_str,
        "deletion_rate": round(deletion_rate, 4),
        "divergence_z": divergence_z,
        "flags": flags,
        "risk_level": risk_level,
        "is_context_only": True,
    }

    # Write artifact
    if not dry_run:
        p = _artifact_path(site_root)
        p.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("missing_tape artifact written: %s (risk_level=%s divergence_z=%s)",
                 p, risk_level, divergence_z)

    # Register qledger claim (salience-only, SHADOW)
    if register_claim and not dry_run:
        _register_claim(asof_str, risk_level, divergence_z or float("nan"))

    return artifact


def _data_root() -> Path:
    try:
        from lib import config
        return config.data_dir()
    except Exception:
        return ROOT / "data"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-claim", action="store_true",
                   help="Skip qledger claim registration.")
    args = p.parse_args()
    try:
        result = emit(dry_run=args.dry_run, register_claim=not args.no_claim)
        LOG.info("artifact: %s", json.dumps(result, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        LOG.error("missing_tape.emit failed: %s", exc, exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
