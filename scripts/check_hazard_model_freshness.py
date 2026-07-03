"""W4.2 ops guard — hazard model freshness / epoch-integrity check (cheap, no refit).

Wired into cycle-calibration.yml as a LOG-AND-SKIP step (fail-open: a stale model degrades
to the KM prior downstream and writes a warning; it never blocks the calibration lane).
This is the diff-and-alert half of the W4.2 ops contract — the heavy monthly refit
(scripts/fit_cycle_hazard) is a separate, deliberately-manual/scheduled step.

Checks (all warn-only unless --strict):
  1. A price-basis panel + a matching model_<epoch>.json exist and the epochs agree.
  2. The panel is a PRICE epoch (price_*), never a stale TR epoch (substrate contract).
  3. The model is not more than --max-stale-days old (default 100) vs the panel mtime.
  4. The model ledger is well-formed (6 cells, each with a verdict).

Exit code is 0 in warn mode (fail-open) even on findings; --strict makes findings exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).parent.parent.resolve()


def _emit(level: str, msg: str) -> None:
    # GitHub-Actions annotation when in CI; plain print otherwise.
    prefix = {"error": "::error::", "warning": "::warning::"}.get(level, "")
    print(f"{prefix}{msg}")


def check(hazard_dir: Path, max_stale_days: int) -> list[str]:
    findings: list[str] = []

    panels = sorted(hazard_dir.glob("panel_price_*.parquet"))
    tr_panels = sorted(hazard_dir.glob("panel_tr_*.parquet"))
    if tr_panels:
        findings.append(
            f"STALE TR-epoch panel(s) present (substrate-contract violation): "
            f"{[p.name for p in tr_panels]} — turns on total-return closes; rebuild on price basis."
        )
    if not panels:
        findings.append("no price-basis panel (panel_price_*.parquet) found — epoch not corrected.")
        return findings

    panel = panels[-1]
    epoch = panel.stem.replace("panel_", "")
    model = hazard_dir / f"model_{epoch}.json"
    if not model.exists():
        findings.append(f"no model for current epoch {epoch}: expected {model.name}.")
        return findings

    # Staleness: model mtime vs now
    age_days = (datetime.now(timezone.utc)
                - datetime.fromtimestamp(model.stat().st_mtime, tz=timezone.utc)).days
    if age_days > max_stale_days:
        findings.append(
            f"hazard model {model.name} is {age_days}d old (> {max_stale_days}d) — "
            f"downstream should degrade to the KM prior; schedule a refit."
        )

    # Ledger well-formedness
    try:
        m = json.loads(model.read_text())
    except Exception as e:  # noqa: BLE001
        findings.append(f"model {model.name} is not valid JSON: {e}")
        return findings

    if not str(m.get("turn_def_version", "")).startswith("price_"):
        findings.append(
            f"model epoch {m.get('turn_def_version')!r} is not price-basis — "
            f"structure-math substrate contract violated."
        )
    led = m.get("ledger", {})
    n_cells = sum(1 for d in ("up", "down") for h in ("1m", "3m", "6m")
                  if isinstance(led.get(d, {}).get(h), dict) and "verdict" in led[d][h])
    if n_cells != 6:
        findings.append(f"model ledger has {n_cells}/6 well-formed cells.")
    else:
        n_pass = sum(1 for d in ("up", "down") for h in ("1m", "3m", "6m")
                     if led[d][h].get("verdict") == "PASS")
        print(f"hazard model OK: epoch {epoch}, {age_days}d old, {n_pass}/6 cells PASS.")

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="W4.2 hazard model freshness/integrity check")
    ap.add_argument("--hazard-dir", default=str(_REPO / "data/hazard"))
    ap.add_argument("--max-stale-days", type=int, default=100)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on findings (default: warn-only, fail-open)")
    args = ap.parse_args()

    hazard_dir = Path(args.hazard_dir)
    if not hazard_dir.exists():
        _emit("warning", f"hazard dir {hazard_dir} absent — skipping (pre-W4.1).")
        return 0

    findings = check(hazard_dir, args.max_stale_days)
    for f in findings:
        _emit("warning", f"hazard-freshness: {f}")
    if findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
