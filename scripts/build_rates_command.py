"""Build the Forward Path board artifact -> data/rates_command/latest.json.

Mirror of scripts/build_transmission.py idioms exactly.

Reads all inputs from data/ (bond_health, transmission, zq_path, release_forecast,
market_state, commodity, policy/intel, site/policy_lever) via
engine.rates_inflation_command.build_board(), writes atomically to
data/rates_command/latest.json, and appends a stamp to
data/rates_command/forward_log.jsonl ONLY under the nightly lane gate.

Ledger law: keep-FIRST per asof_night (skip if a row with same asof_night exists).

Usage: python -m scripts.build_rates_command
Returns 0 always (fail-open so the pipeline continues on engine errors).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_rates_command")

_LANE_GATE: str = "nightly"


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _append_forward_log(outdir: Path, artifact: dict) -> None:
    """Append divergence-flag stamp to forward_log.jsonl under nightly lane gate.

    keep-FIRST per asof_night: skip if a row with the same asof_night already exists.
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    if lane != _LANE_GATE:
        log.info("forward_log: lane='%s' != '%s' — skipping append", lane, _LANE_GATE)
        return

    asof_night = artifact.get("asof", "")
    if not asof_night:
        log.warning("forward_log: asof missing — skipping append")
        return

    log_path = outdir / "forward_log.jsonl"

    # keep-FIRST: check if a row with this asof_night already exists
    if log_path.exists():
        try:
            existing = log_path.read_text(encoding="utf-8").splitlines()
            for line in existing:
                try:
                    row = json.loads(line)
                    if row.get("asof_night") == asof_night:
                        log.info("forward_log: keep-FIRST — %s already logged, skipping", asof_night)
                        return
                except Exception:
                    continue
        except Exception as exc:
            log.warning("forward_log: could not read existing log: %s", exc)

    # Build stamp
    ep = artifact.get("expectations_pressure") or {}
    divergence = artifact.get("divergence") or []

    def _d_active(key: str) -> bool | None:
        for d in divergence:
            if d.get("key") == key:
                return d.get("active")
        return None

    stamp = {
        "schema": "rates_command_flag.v1",
        "asof_night": asof_night,
        "net_state": ep.get("net_state"),
        "hawk_score": ep.get("hawk_score"),
        "ease_score": ep.get("ease_score"),
        "flags": {
            "d1": _d_active("D1_dots_vs_market"),
            "d2": _d_active("D2_projection_vs_breakeven"),
            "d3": _d_active("D3_pressure_vs_market"),
        },
        "implied_bp_12m": (artifact.get("board") or {}).get("rate_path_row", {}).get("implied_bp_12m"),
        "gap_bp": (artifact.get("board") or {}).get("rate_path_row", {}).get("gap", {}).get("gap_bp"),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(stamp, ensure_ascii=False) + "\n")
        log.info("forward_log: appended stamp for asof_night=%s", asof_night)
    except Exception as exc:
        log.warning("forward_log: append failed: %s", exc)


def main() -> int:
    try:
        from lib import config
        data_dir = config.data_dir()
    except Exception:
        data_dir = Path(__file__).resolve().parent.parent / "data"

    outdir = data_dir / "rates_command"

    # Build the board artifact
    try:
        from engine.rates_inflation_command import build_board, build_changes
        artifact = build_board()
    except Exception as exc:
        log.error("rates_inflation_command.build_board failed: %s", exc)
        return 0

    if not artifact:
        log.warning("build_board returned empty — skipping write")
        return 0

    new_asof = artifact.get("asof", "")

    # Load prior artifact for build_changes
    latest_path = outdir / "latest.json"
    old_artifact: dict | None = None
    if latest_path.exists():
        try:
            old_artifact = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not read prior artifact: %s", exc)

    # Attach changes + prev_state
    try:
        changes, prev_state = build_changes(old_artifact, artifact, new_asof)
        artifact["changes"] = changes
        artifact["prev_state"] = prev_state
    except Exception as exc:
        log.warning("build_changes failed: %s", exc)

    # Mark build timestamp
    artifact["built"] = datetime.now(timezone.utc).isoformat()

    # Write atomically
    content = json.dumps(artifact, indent=2, default=str, ensure_ascii=False)
    try:
        _atomic_write(latest_path, content)
        log.info("wrote %s (%d KB)", latest_path, len(content) // 1024)
    except Exception as exc:
        log.error("atomic write failed: %s", exc)
        return 0

    # Forward log (nightly-gated)
    _append_forward_log(outdir, artifact)

    log.info(
        "rates_command done: asof=%s net_state=%s hawk=%.0f ease=%.0f stance_en=%s",
        new_asof,
        (artifact.get("expectations_pressure") or {}).get("net_state", "?"),
        (artifact.get("expectations_pressure") or {}).get("hawk_score", 0),
        (artifact.get("expectations_pressure") or {}).get("ease_score", 0),
        (artifact.get("stance") or {}).get("en", "?")[:80],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
