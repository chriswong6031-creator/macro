"""Runner for the Transmission CALIBRATION historical episode miner (TXI W3).

Thin wrapper over engine.transmission_calibration.run(): loads the chain library in
knowledge/transmission/, scans the FULL history of each hop's collected source series
(REUSING the node-evaluation grammar from engine.transmission_chains — no duplicated
threshold parser), measures each hop's conditional forward confirmation rate P(hop confirms
| upstream fired) with n, splits it by the regime cell it occurred in (TXI-R6, from
data/regime/regime_history.parquet), runs a descriptive cohort event-study, and writes
data/transmission/chain_calibration.json (transmission_calibration.v1).

CADENCE — WEEKLY, not nightly (masterplan §W3: heavy history scan runs OFF the render path).
Wired in weekly.yml AFTER build_transmission (Saturday deep-dive lane), declared in
config/dag.yml (the #3295 undeclared-step trap). The nightly transmission_chains read then
picks up chain_calibration.json to fill each hop's base_rates + promote the display tier.

NO-OP GRACEFULLY: absent series/regime history leave hops "untested" and the runner still
exits 0 (additive, never fatal). A malformed/schema-violating chain file is a HARD fail
(reds the build summary) — never silently skipped.

LEDGER LAW: chain_calibration.json is a weekly-advanced forward ARTIFACT. A worktree run
must `git restore data/` before commit — the weekly workflow is the sole scheduled writer.

Usage:
    python -m scripts.run_transmission_calibration                # write the artifact
    python -m scripts.run_transmission_calibration --dry-run      # print the calibration table, no write
    python -m scripts.run_transmission_calibration --root /path   # override the repo root
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import transmission_calibration as cal  # noqa: E402
from engine import transmission_chains as tc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("run_transmission_calibration")


def _fmt_p(p) -> str:
    return f"{p:.3f}" if isinstance(p, float) else str(p)


def _print_table(state: dict) -> None:
    """Compact per-chain / per-hop calibration table (used by --dry-run). Prints, per hop:
    pooled p_confirm + n, how many regime cells got REAL rates vs untested, and the method
    (series vs proxy vs untested). Honest by design — thin/untested hops print as such."""
    print(f"\ntransmission calibration — asof {state.get('asof')} "
          f"(floor n>={state.get('n_floor')}; regime_history={'yes' if state.get('regime_history_available') else 'NO'})\n")
    total_hops = 0
    total_cal = 0
    for c in state.get("chains", []):
        total_hops += c.get("n_hops", 0)
        total_cal += c.get("calibrated_hops", 0)
        print(f"=== {c['chain']}  (rev {c.get('rev')}) — {c.get('calibrated_hops')}/{c.get('n_hops')} hops calibrated ===")
        for h in c.get("hops", []):
            per_regime = h.get("per_regime", {}) or {}
            cells_real = sum(1 for v in per_regime.values() if isinstance(v.get("p"), float))
            cells_untested = sum(1 for v in per_regime.values() if v.get("p") == "untested")
            regime_bit = (f"{cells_real} regime cells measured, {cells_untested} untested"
                          if h.get("regime_split") == "available"
                          else f"pooled only [{h.get('regime_split')}]")
            print(f"  {h['from']:22s} -> {h['to']:22s}  lag{h['lag_d']}")
            print(f"      p_confirm={_fmt_p(h.get('p_confirm')):10s} n={h.get('n'):<6d} {regime_bit}")
            for cell, cv in per_regime.items():
                print(f"        [{cell:34s}] p={_fmt_p(cv.get('p')):10s} n={cv.get('n')}")
            meth = h.get("method") or {}
            if isinstance(meth, dict):
                print(f"        method: from={meth.get('from')}")
                print(f"                to  ={meth.get('to')}")
            if h.get("untested_reason"):
                print(f"        untested: {h['untested_reason']}")
            if h.get("regime_split_reason"):
                print(f"        split: {h['regime_split_reason']}")
        es = c.get("cohort_event_study", {})
        if es.get("available"):
            hz = "  ".join(f"{k}:mean_excess={v.get('mean_excess_pct')}(n={v.get('n')})"
                           for k, v in es.get("horizons", {}).items())
            print(f"  cohort event-study ({es.get('cohort')} vs SPY): {hz}")
        else:
            print(f"  cohort event-study: unavailable ({es.get('reason')})")
        print()
    print(f"TOTAL: {total_cal}/{total_hops} hops calibrated across {len(state.get('chains', []))} chains "
          f"(the rest untested — honest coverage on ~15y usable history).\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="repo root override (default: two levels above this script)")
    ap.add_argument("--dry-run", action="store_true",
                    help="mine and print the calibration table; do NOT write the artifact")
    args = ap.parse_args()

    t0 = time.perf_counter()
    try:
        state = cal.run(root=args.root, write=not args.dry_run)
    except tc.ChainSchemaError as e:
        # a malformed / schema-violating chain file is a HARD fail — never silently skip a bad edit.
        log.error("chain library schema error: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001 — additive; a runtime failure must not break the weekly
        log.error("transmission_calibration runner failed (non-fatal): %s", e)
        return 0
    wall = time.perf_counter() - t0

    if args.dry_run:
        _print_table(state)
        print(f"[wall] full history scan of {len(state.get('chains', []))} chains: {wall:.2f}s")
    else:
        log.info("wrote chain_calibration.json (%d chains, asof=%s) in %.2fs",
                 len(state.get("chains", [])), state.get("asof"), wall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
