"""Oracle Research Factory — Promotion Scan (W-B1 nightly step).

Flags screened/accruing compounds meeting the economic promotion floor into
data/oracle/promotion_queue.json for Fable adjudication.

NEVER auto-promotes.  This script only writes the queue; a human (Fable)
makes the final promotion call.

Promotion floor (from ORACLE_COMPOUND_LIBRARY.md §Tier-2):
  |effect_63d| >= 0.01  OR  hit_63d >= 0.55
  AND n >= 100
  AND >= 3/4 eras direction-consistent

Search width is computed as the TOTAL count of trial_ledger rows (both
historical screening + live_ledger rows), providing the FDR denominator
for the Harvey-Liu-Zhu factor-zoo accounting at the promotion stage.

Usage
-----
  python scripts/oracle_promotion_scan.py [--data-dir PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_promotion_scan")

# Promotion floor constants
_MIN_N = 100
_MIN_ABS_EFFECT_63D = 0.01      # |effect_63d| >= 1%
_MIN_HIT_63D = 0.55             # hit_63d >= 55%
_MIN_ERA_CONSISTENT = 3         # of 4 eras direction-consistent


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _meets_promotion_floor(ledger_row: dict) -> bool:
    """Return True if the ledger row passes the promotion floor."""
    n = ledger_row.get("n", 0) or 0
    if n < _MIN_N:
        return False

    effect = ledger_row.get("effect_63d")
    hit = ledger_row.get("hit_63d")
    era_consistent = ledger_row.get("era_consistent_63d", 0) or 0

    if era_consistent < _MIN_ERA_CONSISTENT:
        return False

    # Must pass EITHER effect OR hit threshold
    effect_ok = (effect is not None and abs(effect) >= _MIN_ABS_EFFECT_63D)
    hit_ok = (hit is not None and hit >= _MIN_HIT_63D)

    return effect_ok or hit_ok


def _get_best_ledger_row(
    compound_id: str,
    trial_rows: list[dict],
    live_rows: list[dict],
) -> dict | None:
    """Get the best (most recent) combined ledger row for a compound.

    Combines historical trial_ledger rows with live_ledger summary stats.
    Returns None if no usable row exists.
    """
    # Prefer live data if n is sufficient (live has uncontaminated forward return)
    # Otherwise use historical screen
    combined_rows = [r for r in trial_rows if r.get("compound_id") == compound_id]
    live_compound_rows = [r for r in live_rows if r.get("compound_id") == compound_id]

    if not combined_rows and not live_compound_rows:
        return None

    # If we have live rows with outcomes, build a combined n from both
    if live_compound_rows:
        # Latest historical row + augmented n from live
        latest_hist = combined_rows[-1] if combined_rows else {}
        live_mature = [r for r in live_compound_rows
                       if r.get("outcome_mature") is True]
        live_n = len(live_mature)
        hist_n = latest_hist.get("n", 0) or 0

        # Compute live effect if enough mature rows
        if live_mature:
            import numpy as np
            live_excesses = [r.get("excess_63d") for r in live_mature
                             if r.get("excess_63d") is not None]
            if live_excesses:
                live_effect = float(np.mean(live_excesses))
                live_hit = float(sum(1 for x in live_excesses if x > 0) / len(live_excesses))
                # Use latest_hist as base and override with augmented stats
                best = dict(latest_hist)
                best["n"] = hist_n + live_n
                # Weighted average effect (hist vs live)
                if hist_n > 0 and latest_hist.get("effect_63d") is not None:
                    hist_eff = latest_hist["effect_63d"]
                    total_n = hist_n + live_n
                    best["effect_63d"] = (hist_eff * hist_n + live_effect * live_n) / total_n
                else:
                    best["effect_63d"] = live_effect
                best["hit_63d"] = live_hit if live_n > hist_n else latest_hist.get("hit_63d", live_hit)
                best["live_n"] = live_n
                return best

    return combined_rows[-1] if combined_rows else None


def run_promotion_scan(
    data_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Run the promotion scan.  Returns the written queue dict."""
    from engine.oracle.compounds import load_registry

    compounds_dir = data_dir / "oracle" / "compounds"
    registry = load_registry(compounds_dir)

    trial_rows = _load_jsonl(compounds_dir / "trial_ledger.jsonl")
    live_rows = _load_jsonl(compounds_dir / "live_ledger.jsonl")

    # Search width = total trial count (all compounds, all screens)
    search_width = len(trial_rows) + len([r for r in live_rows
                                          if r.get("outcome_mature") is True])
    log.info("Promotion scan: %d registry compounds, %d trial rows, %d live rows, search_width=%d",
             len(registry), len(trial_rows), len(live_rows), search_width)

    candidates = []
    for compound in registry:
        status = compound.get("status", "exploratory")
        if status not in ("screened", "accruing"):
            continue

        cid = compound["id"]
        best = _get_best_ledger_row(cid, trial_rows, live_rows)
        if best is None:
            log.debug("Compound %s: no ledger row found, skipping", cid)
            continue

        if _meets_promotion_floor(best):
            candidates.append({
                "compound_id": cid,
                "compound_name": compound.get("name"),
                "family": compound.get("family"),
                "current_status": status,
                "n": best.get("n"),
                "effect_63d": best.get("effect_63d"),
                "hit_63d": best.get("hit_63d"),
                "era_consistent_63d": best.get("era_consistent_63d"),
                "era_dominant_direction_63d": best.get("era_dominant_direction_63d"),
                "live_n": best.get("live_n", 0),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "search_width_at_scan": search_width,
                "floor_passed": {
                    "n_ge_100": (best.get("n") or 0) >= _MIN_N,
                    "abs_effect63_ge_1pct": abs(best.get("effect_63d") or 0) >= _MIN_ABS_EFFECT_63D,
                    "hit63_ge_55pct": (best.get("hit_63d") or 0) >= _MIN_HIT_63D,
                    "era_consistent_ge_3": (best.get("era_consistent_63d") or 0) >= _MIN_ERA_CONSISTENT,
                },
                "note": (
                    "QUEUE ONLY — not promoted. Fable adjudication required. "
                    f"Search width at scan: {search_width}."
                ),
            })

    queue = {
        "schema": "oracle_promotion_queue.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "search_width": search_width,
        "n_candidates": len(candidates),
        "candidates": candidates,
        "note": (
            "This queue flags compounds meeting the economic floor for Fable adjudication. "
            "NO auto-promotion. search_width is the Harvey-Liu-Zhu FDR denominator. "
            "Promotion requires a registered gauntlet shot (oracle_gauntlet_p3.py)."
        ),
    }

    if candidates:
        log.info("Promotion scan: %d candidate(s) flagged:", len(candidates))
        for c in candidates:
            log.info("  [%s] %s — n=%s effect63d=%s hit63d=%s era_consistent=%s",
                     c["compound_id"], c["compound_name"],
                     c["n"], c["effect_63d"], c["hit_63d"], c["era_consistent_63d"])
    else:
        log.info("Promotion scan: no compounds meet the floor (n=%d total searched)", search_width)

    if not dry_run:
        queue_path = data_dir / "oracle" / "promotion_queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(queue, separators=(",", ":"), default=str))
        log.info("promotion_queue.json written: %d candidates", len(candidates))

    return queue


def main() -> int:
    p = argparse.ArgumentParser(description="Oracle Promotion Scan")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()

    try:
        queue = run_promotion_scan(data_dir, dry_run=args.dry_run)
        print(f"\n=== oracle_promotion_scan ===")
        print(f"  search_width:  {queue['search_width']}")
        print(f"  candidates:    {queue['n_candidates']}")
        for c in queue.get("candidates", []):
            print(f"  [{c['compound_id']}] n={c['n']} effect63d={c.get('effect_63d')} hit63d={c.get('hit_63d')}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"::error::oracle_promotion_scan FAILED: {e}", flush=True)
        log.exception("oracle_promotion_scan FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
