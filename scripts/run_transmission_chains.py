"""Runner for the Transmission Chains episode tracker (TXI W1).

Thin wrapper over engine.transmission_chains.run(): loads the chain library in
knowledge/transmission/, advances each chain's episode state from the forward ledger +
the current artifacts (data/transmission|forex|regime/latest.json + the parquet store),
and writes data/transmission/chain_state.json + appends chain_episodes.jsonl.

Runs in the nightly AFTER build_transmission (which writes data/transmission/latest.json)
inside the cl_markets cluster. Completes in seconds — it reads a handful of JSONs + a few
series. NO-OP GRACEFULLY: absent upstream artifacts leave chains unresolvable (dormant),
and the runner still exits 0 (additive, never fatal). Nightly is the SOLE advancer of the
forward ledger (ledger law) — this runner is only invoked by the nightly workflow.

Usage:
    python -m scripts.run_transmission_chains                # write artifacts
    python -m scripts.run_transmission_chains --dry-run      # print the state + blast table, no write
    python -m scripts.run_transmission_chains --root /path   # override the repo root
    python -m scripts.run_transmission_chains --substrate DIR --dry-run   # override the per-ticker dir
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import transmission_chains as tc  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("run_transmission_chains")


def _print_table(state: dict) -> None:
    """Print a compact per-chain state table (used by --dry-run)."""
    print(f"\ntransmission chains — asof {state.get('asof')} "
          f"({len(state.get('chains', []))} chains)\n")
    hdr = f"{'chain':<34} {'tier':<11} {'state':<12} {'hop':<7} {'armable':<8}"
    print(hdr)
    print("-" * len(hdr))
    for c in state.get("chains", []):
        hop = f"{c['hop']}/{c['n_hops']}"
        print(f"{c['chain']:<34} {c['tier']:<11} {c['state']:<12} {hop:<7} {str(c['armable']):<8}")
        for n in c.get("nodes", []):
            if not n["resolved"]:
                mark = "??"
            elif n["confirmed"]:
                mark = "OK"
            else:
                mark = ".."
            rc = n.get("receipts") or [{}]
            val = rc[0].get("value")
            reason = f"  [{n.get('unresolved_reason')}]" if not n["resolved"] else ""
            print(f"    {mark} {n['id']:<26} value={val}{reason}")
        if c.get("falsifier_fired"):
            print(f"    !! falsifier fired: {c['falsifier_fired'].get('note')}")
        _print_blast(c)
    sub = state.get("substrate")
    if sub:
        print(f"substrate: {sub.get('universe')} names, asof "
              f"{sub.get('substrate_asof', {}).get('min')}..{sub.get('substrate_asof', {}).get('max')}")
    print()


def _label_en(obj) -> str:
    """The English label of a {en, zh} dict, else str(obj)."""
    if isinstance(obj, dict):
        return obj.get("en", "")
    return str(obj) if obj is not None else ""


def _print_blast(c: dict) -> None:
    """Per-armed-chain blast table: one row per channel with its member count, unevaluable
    bucket, printed percentile cuts, and 5 example tickers (masterplan §scoping.5 — proves the
    sweep on real data). Dormant chains (blast=={} or []) print nothing."""
    blast = c.get("blast")
    if not blast or not isinstance(blast, dict):
        return
    print(f"    blast radius ({c['state']}):")
    for flag, b in blast.items():
        if not b.get("resolved", False):
            note = _label_en(b.get("note"))
            tag = "dropped/proxy" if note.lower().startswith(("dropped", "proxy")) else "unresolved"
            print(f"      - {flag:26s} [{tag}] {note[:72]}")
            continue
        cuts = b.get("cuts") or {}
        cutstr = "  ".join(f"{k.split('.')[-1]}≥cut={v}" for k, v in cuts.items())
        examples = ", ".join(b.get("names", [])[:5])
        print(f"      - {flag:26s} n={b.get('n', 0):<4d} uneval={b.get('unevaluable', 0):<4d} "
              f"{cutstr}")
        if examples:
            print(f"          eg: {examples}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="repo root override (default: two levels above this script)")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and print the state + blast table; do NOT write artifacts")
    ap.add_argument("--substrate", type=Path, default=None,
                    help="per-ticker substrate dir override (default: <root>/site/stockdata)")
    ap.add_argument("--no-blast", action="store_true",
                    help="skip the W2 blast-radius sweep (state machine only)")
    args = ap.parse_args()

    t0 = time.perf_counter()
    try:
        state = tc.run(root=args.root, write=not args.dry_run,
                       substrate_dir=args.substrate,
                       resolve_blast_radius=not args.no_blast)
    except tc.ChainSchemaError as e:
        # a malformed / schema-violating chain file is a HARD fail (reds CI / the build
        # summary) — never silently skip a bad edit.
        log.error("chain library schema error: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001 — additive; a runtime failure must not break the nightly
        log.error("transmission_chains runner failed (non-fatal): %s", e)
        return 0
    wall = time.perf_counter() - t0

    if args.dry_run:
        _print_table(state)
        sub = state.get("substrate") or {}
        print(f"[wall] full run (load + state + blast sweep over {sub.get('universe', 0)} "
              f"names): {wall:.2f}s")
    else:
        log.info("wrote chain_state.json (%d chains, asof=%s) in %.2fs",
                 len(state.get("chains", [])), state.get("asof"), wall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
