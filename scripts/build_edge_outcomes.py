"""scripts/build_edge_outcomes.py — Neural Web edge-outcome ledger runner (wave-2b).

CLI
---
    python -m scripts.build_edge_outcomes --retro   [--data-root PATH] [--since D] [--until D]
    python -m scripts.build_edge_outcomes --nightly [--data-root PATH]
    python -m scripts.build_edge_outcomes --retro --results-json research/edge_outcome_retro_results.json

Grades what the Neural Web's typed edges actually did: edge fired -> did the
target move, which way, with what lag.  All arithmetic lives in
``engine/neuralweb/edge_outcomes.py``; this file is I/O, lane gating, and
reporting only.

TWO LANES, TWO FILES — THEY NEVER MIX
-------------------------------------
``--retro``   replays history from the spine (and tape, if present) and writes
              ONLY ``data/neuralweb/edge_outcomes_retro.jsonl``.  Bounded and
              idempotent: re-running appends zero rows.  Safe in any lane.

``--nightly`` appends the latest session only to the prospective forward ledger
              ``data/neuralweb/edge_outcomes.jsonl``, and REFUSES unless
              ``COLLECT_LANE == "nightly"``.

The forward ledger is nightly-only from day one.  Nightly is the sole advancer
of forward ledgers (house law); intraday and ad-hoc lanes discard ``data/``
writes.  The gate mirrors ``scripts/collect.py``, which fences its own forward
graders the same way::

    # scripts/collect.py:1087
    if os.environ.get("COLLECT_LANE") == "nightly":
        ...advance the forward ledger...
    else:
        log.debug("... skipped — not the nightly lane (COLLECT_LANE=%r)", ...)

A retro replay can never contaminate the prospective record because it does not
know the prospective path: ``--retro`` resolves ``RETRO_LEDGER`` and ``--nightly``
resolves ``PROSPECTIVE_LEDGER``, and neither flag can reach the other file.

NOT WIRED — ON PURPOSE
----------------------
This PR does NOT add a ``config/dag.yml`` node, a ``.github/workflows`` step, or
a ``config/synapse.yml`` entry.  Four open lanes collide on those files; the
wiring rides a follow-up PR.  Until then this runner is invoked by hand, and
``--nightly`` is inert outside the nightly lane by design.

EXIT CODES
----------
0 = ran (including an honest zero-row run); 1 = refused or failed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.edge_outcomes import (  # noqa: E402
    FIRE_DEF_SPINE,
    FIRE_DEF_TAPE,
    MIN_N,
    VALID_FIRE_DEFS,
    aggregate,
    append_rows,
    build_rows,
    coverage_table,
    resolve_data_root,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("build_edge_outcomes")

REPO_ROOT = Path(__file__).resolve().parent.parent

PROSPECTIVE_LEDGER = "edge_outcomes.jsonl"
RETRO_LEDGER = "edge_outcomes_retro.jsonl"

NIGHTLY_LANE_ENV = "COLLECT_LANE"
NIGHTLY_LANE_VALUE = "nightly"


def nightly_lane_ok(env: dict[str, str] | None = None) -> bool:
    """True only inside the nightly lane.

    Fail-closed: an absent, empty, or differently-valued ``COLLECT_LANE``
    refuses.  Mirrors ``scripts/collect.py``'s forward-ledger gate.
    """
    environ = os.environ if env is None else env
    return environ.get(NIGHTLY_LANE_ENV) == NIGHTLY_LANE_VALUE


def _latest_session(nw_dir: Path) -> str | None:
    """The spine's newest ``as_of``.  ``--nightly`` appends only that session."""
    path = nw_dir / "spine_index.parquet"
    if not path.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(path, columns=["as_of"])
        vals = [str(v) for v in df["as_of"].dropna().unique().tolist()]
        return max(vals) if vals else None
    except Exception as exc:  # noqa: BLE001 - fail-open
        log.warning("build_edge_outcomes: latest session unreadable — %s", exc)
        return None


def _print_report(mode: str, meta: dict, cov: dict, board: dict, write: dict, gaps: list[str]) -> None:
    print("")
    print(f"edge-outcomes [{mode}]")
    print(f"  edges inventoried : {meta.get('n_edges_inventoried')}")
    print(f"  rows built        : {meta.get('n_rows')}  (graded {meta.get('n_graded_rows')})")
    print(f"  appended          : {write.get('n_appended')}  "
          f"(skipped: {write.get('n_skipped_content_hash')} by content-hash, "
          f"{write.get('n_skipped_key')} by key; {write.get('n_existing')} already on file)")
    frac = cov.get("gradeable_fraction")
    frac_s = "n/a" if frac is None else f"{frac:.1%}"
    print(f"  gradeable edges   : {cov.get('n_edges_gradeable')}/{cov.get('n_edges')} ({frac_s})")
    if cov.get("ungradeable_by_reason"):
        print("  ungradeable by reason:")
        for code, n in cov["ungradeable_by_reason"].items():
            print(f"    {n:>4}  {code}")
    print(f"  scoreboard        : {board.get('n_edges_measured')} measured "
          f"(n_graded >= {board.get('min_n')}), {board.get('n_edges_accruing')} accruing")
    for e in board.get("edges", [])[:10]:
        if e["state"] == "measured":
            ci = e.get("agreement_ci95") or [float("nan"), float("nan")]
            warn = "  [OVERLAP: nominal CI]" if e.get("overlap_warning") else ""
            base = e.get("dst_base_rate_matched")
            lift = e.get("agreement_lift_vs_base")
            base_s = "n/a" if base is None else f"{base:.3f}"
            lift_s = "n/a" if lift is None else f"{lift:+.3f}"
            print(f"    {e['edge_type']:<12} {e['src']} -> {e['dst']}  "
                  f"n={e['n_graded']} (indep blocks={e.get('n_independent_blocks')}) "
                  f"agree={e['agreement_rate']:.3f} vs base={base_s} (lift {lift_s}) "
                  f"CI95=[{ci[0]:.3f},{ci[1]:.3f}] lag={e.get('median_lag_sessions')}{warn}")
        else:
            print(f"    {e['edge_type']:<12} {e['src']} -> {e['dst']}  "
                  f"n_fires={e['n_fires']} n_graded={e['n_graded']} "
                  f"ACCRUING (rate suppressed: {e['rate_suppressed_reason']})")
    if gaps:
        print("  gaps:")
        for g in gaps:
            print(f"    - {g}")
    print("")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the Neural Web edge-outcome ledger (display-tier, deterministic).",
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--retro", action="store_true",
                      help="Replay history into the RETRO ledger (never the prospective one).")
    mode.add_argument("--nightly", action="store_true",
                      help="Append the latest session to the PROSPECTIVE ledger. "
                           "Refuses unless COLLECT_LANE=nightly.")
    ap.add_argument("--data-root", default=None,
                    help="Path to a data/neuralweb directory (top of the resolution ladder).")
    ap.add_argument("--fire-def", default=FIRE_DEF_SPINE, choices=sorted(VALID_FIRE_DEFS),
                    help=f"Fire definition (default {FIRE_DEF_SPINE}; "
                         f"{FIRE_DEF_TAPE} is the disclosed variant).")
    ap.add_argument("--since", default=None, help="Earliest fire date (ISO), retro only.")
    ap.add_argument("--until", default=None, help="Latest fire date (ISO), retro only.")
    ap.add_argument("--results-json", default=None,
                    help="Write the coverage + scoreboard payload to this JSON path.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report, but write no ledger rows.")
    args = ap.parse_args(argv)

    # --- lane gate, before anything touches the forward ledger -------------
    if args.nightly and not nightly_lane_ok():
        log.error(
            "build_edge_outcomes: REFUSING --nightly — %s=%r, expected %r. "
            "The prospective forward ledger is nightly-only; nightly is the sole "
            "advancer of forward ledgers. Use --retro for an ad-hoc replay.",
            NIGHTLY_LANE_ENV, os.environ.get(NIGHTLY_LANE_ENV), NIGHTLY_LANE_VALUE,
        )
        return 1

    nw_dir, provenance = resolve_data_root(args.data_root, repo_root=REPO_ROOT)
    if nw_dir is None:
        log.error("build_edge_outcomes: no data/neuralweb directory found on the ladder "
                  "(--data-root -> $MACRO_PRIMARY_DATA_NW -> <repo>/data/neuralweb -> primary checkout)")
        return 1
    log.info("build_edge_outcomes: data root %s (via %s)", nw_dir, provenance)

    since, until = args.since, args.until
    if args.nightly:
        latest = _latest_session(nw_dir)
        if latest is None:
            log.error("build_edge_outcomes: --nightly needs a readable spine; none found")
            return 1
        since = until = latest
        log.info("build_edge_outcomes: nightly session %s", latest)

    gaps: list[str] = []
    try:
        rows, gaps, meta = build_rows(
            nw_dir, fire_def=args.fire_def, since=since, until=until, gaps=gaps,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("build_edge_outcomes: build_rows failed: %s", exc)
        return 1

    ledger_name = RETRO_LEDGER if args.retro else PROSPECTIVE_LEDGER
    ledger_path = nw_dir / ledger_name

    if args.dry_run:
        write = {"n_appended": 0, "n_skipped_content_hash": 0,
                 "n_skipped_key": 0, "n_existing": 0}
        log.info("build_edge_outcomes: --dry-run — no rows written to %s", ledger_path)
    else:
        write = append_rows(ledger_path, rows)
        log.info("build_edge_outcomes: %s +%d rows", ledger_path, write["n_appended"])

    # Score the FULL ledger on disk (or this run's rows under --dry-run), so the
    # scoreboard reflects everything accrued, not just tonight's slice.
    from engine.neuralweb.edge_outcomes import read_ledger
    scored = rows if args.dry_run else (read_ledger(ledger_path) or rows)
    board = aggregate(scored, min_n=MIN_N)
    cov = coverage_table(scored)

    _print_report("retro" if args.retro else "nightly", meta, cov, board, write, gaps)

    if args.results_json:
        payload = {
            "mode": "retro" if args.retro else "nightly",
            "fire_def": args.fire_def,
            "data_root_provenance": provenance,
            "since": since,
            "until": until,
            "meta": meta,
            "coverage": cov,
            "scoreboard": board,
            "gaps": gaps,
            "ledger": str(ledger_path.name),
        }
        out = Path(args.results_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                       encoding="utf-8")
        log.info("build_edge_outcomes: results -> %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
