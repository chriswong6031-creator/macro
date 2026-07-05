"""Build reflexivity overlay artifact — W4, Signal Commons.

Runs AFTER build_site.py has written site/factor_betas.json and AFTER
build_stock_board_v2.py has written site/factordata/us_standouts_v2.json.

Writes: site/factordata/reflexivity_overlay.json  (display-only, is_context_only=true)

This script is a pure read-over-artifacts step (no heavy compute; betas already
estimated), so it rides the nightly pipeline without threatening the ~67-min render budget.

PLACEMENT (R-A ruling): BOARD-level, held-agnostic overlay only.
The candidate-vs-HELD read is chartered to the Mastermind repo.
CN/HK names are out of scope in v1 (R-E ruling).
Nothing here writes to data/ (ledger law: nightly is the sole advancer).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("build_reflexivity_overlay")

ROOT = Path(__file__).resolve().parents[1]
_FACTOR_BETAS = ROOT / "site" / "factor_betas.json"
_STANDOUTS_V2 = ROOT / "site" / "factordata" / "us_standouts_v2.json"
_MEMBERSHIP   = ROOT / "data" / "baskets" / "membership.json"
_OUT          = ROOT / "site" / "factordata" / "reflexivity_overlay.json"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        log.warning("reflexivity: missing %s — degraded", path.name)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("reflexivity: cannot parse %s: %s", path.name, e)
        return None


def _candidate_tickers(standouts: dict) -> tuple[list[str], dict[str, str]]:
    """Extract unique candidate tickers + sector mapping from us_standouts_v2.

    Combines both lanes (entry_open + setting_up) — these are the names we build
    the duplicate-exposure read over.  Returns (tickers, sector_by_ticker).
    """
    seen: dict[str, str] = {}  # ticker → sector (first seen wins)
    lanes = (standouts or {}).get("lanes") or {}
    for lane_rows in lanes.values():
        if not isinstance(lane_rows, list):
            continue
        for row in lane_rows:
            t = (row.get("ticker") or "").upper()
            if not t:
                continue
            if t not in seen:
                seen[t] = row.get("sector") or ""
    tickers = list(seen.keys())
    return tickers, seen


def _as_of(standouts: dict, factor_betas: dict) -> str:
    """Best as_of from input artifacts."""
    s = (standouts or {}).get("as_of") or ""
    f = (factor_betas or {}).get("as_of") or ""
    return s or f or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def compute(site: Path | None = None) -> dict:
    """Build the reflexivity overlay artifact. Degrades gracefully on missing inputs."""
    site = site or (ROOT / "site")
    factor_betas_path = site / "factor_betas.json"
    standouts_path    = site / "factordata" / "us_standouts_v2.json"
    membership_path   = ROOT / "data" / "baskets" / "membership.json"

    factor_betas = _load_json(factor_betas_path)
    standouts    = _load_json(standouts_path)
    membership   = _load_json(membership_path)

    if not standouts:
        log.warning("reflexivity: us_standouts_v2.json absent — emitting empty overlay")
        return _empty_overlay("us_standouts_v2.json absent")

    tickers, sector_by_ticker = _candidate_tickers(standouts)

    if not tickers:
        log.warning("reflexivity: no candidates in us_standouts_v2 — emitting empty overlay")
        return _empty_overlay("no candidates in us_standouts_v2")

    betas_index: dict[str, dict] = {}
    if factor_betas and isinstance(factor_betas.get("betas"), dict):
        betas_index = factor_betas["betas"]
    else:
        log.warning("reflexivity: factor_betas.json absent or malformed — membership-only similarity")

    from engine.reflexivity import compute as _compute
    as_of = _as_of(standouts, factor_betas or {})
    artifact = _compute(
        tickers=tickers,
        sector_by_ticker=sector_by_ticker,
        betas_index=betas_index,
        membership_data=membership,
        as_of=as_of,
    )

    # Passport for source coverage
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)

    artifact["source_passport"] = {
        "factor_betas": {
            "path": _rel(factor_betas_path),
            "found": factor_betas is not None,
            "as_of": (factor_betas or {}).get("as_of"),
        },
        "us_standouts_v2": {
            "path": _rel(standouts_path),
            "found": True,
            "as_of": standouts.get("as_of"),
        },
        "membership": {
            "path": "data/baskets/membership.json",
            "found": membership is not None,
        },
    }
    return artifact


def _empty_overlay(reason: str) -> dict:
    return {
        "schema": "reflexivity_overlay.v1",
        "is_context_only": True,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": f"Empty overlay: {reason}",
        "factor_caveat": (
            "Per-name secondary betas (oil/usd/btc/gold/china) are OOS-unstable and excluded."
        ),
        "board_concentration": {"n": 0, "n_eff": 0.0, "basis": "none"},
        "by_ticker": {},
        "pair_basis": {},
        "verdicts": {},
    }


def main() -> int:
    """Entry point for nightly pipeline. Returns 0 always (non-fatal, like build_stock_board_v2)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        artifact = compute()
        out_path = _OUT
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure all values are JSON-serializable (numpy scalars → python native)
        out_text = json.dumps(artifact, indent=2, default=_json_default)
        out_path.write_text(out_text)

        n = artifact.get("board_concentration", {}).get("n", 0)
        neff = artifact.get("board_concentration", {}).get("n_eff", 0.0)
        log.info("reflexivity overlay written: %d candidates ≈ %.1f independent bets → %s",
                 n, neff, out_path)
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("reflexivity overlay failed (non-fatal): %s", e)
        return 0   # never break the render


def _json_default(obj):
    """Fallback for JSON serialization of numpy scalars."""
    import numpy as np  # noqa: PLC0415
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
