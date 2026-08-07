"""US SCAN TIER — the widened seeing set (PROPHET US roadmap §4.5).

Operator ratification 2026-08-05 ("Yes we should do the full universe then"),
after the receipts that FNV / FSM / EXK / AG / SBSW were structurally invisible:
not merely un-admitted, but absent from every frame the engine looks at.

WHAT THIS LANE DOES, IN ORDER

  1. resolve the liquidity-floored scan universe over ``data/massive_stock_day``
     (``engine/us_scan_universe.py``), MINUS the curated universe;
  2. stamp one US Context Vector row per scan name with ``tier="scan"``
     (``engine/us_context_vector.py``, the same monthly parts the curated stamp
     writes — keep-first makes the curated row win on any overlap);
  3. write the scan-tier runner-exclusion audit
     (``engine/prophet_miss_audit.build_scan_tier_audit``) to
     ``data/prophet_scan_tier/latest.json`` + append its forward-log row.

WHAT IT EXPLICITLY DOES NOT DO

  Board ADMISSION, gates, scores, ranks, sizing and plan intake are UNCHANGED.
  The curated universe remains the graded population. Nothing written here is
  read for any decision — "see everything, admit selectively."

WHY ITS OWN LANE, NOT THE ENGINE JOB
  The scan pass needs ``data/massive_stock_day`` (617 MB, ~20k parquets,
  R2-canonical). The engine job does NOT restore it — the three restores in
  daily.yml live in ``collect``, ``oracle_offrender`` and ``standout_audit_us``.
  Adding a 617 MB restore plus ~13 min of gating to a job that already runs
  135-190 min against a 200-min cap is exactly the budget-buster the charter
  warns against, so this runs post-engine in its own lane with its own timeout.

MEASURED COST (this Mac Studio, 2026-08-04, 3,980-name floored set)
  store census (all 20,476 files, close+volume only)   30 s
  close panel read (3,980 names)                      ~10 s
  signal_gate.gate per name (deep series)            ~120 ms
  context_frame per name (11 dims)                     74 ms
  => ~13 min for the full assembly. Off the render path, off the engine job.

NIGHTLY-ONLY LAW. ``--nightly`` is the sole advancer: it writes the artifact,
appends the forward-log row, and arms the context-vector stamp. A default
invocation computes and prints and writes NOTHING. ``--out-dir DIR`` runs the
full write into a scratch dir, never the real store. The forward append is
idempotent on ``price_through``, so a same-night re-run appends nothing.

Run (nightly / DAG):   python -m scripts.run_us_scan_tier --nightly
Run (safe local test): python -m scripts.run_us_scan_tier --out-dir /tmp/scan
Run (dry, no writes):  python -m scripts.run_us_scan_tier --no-stamp
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import prophet_miss_audit as PMA  # noqa: E402
from engine import us_scan_universe as USU  # noqa: E402

log = logging.getLogger("run_us_scan_tier")


def curated_universe(root: Path) -> set[str]:
    """The curated roster to EXCLUDE from the scan tier.

    Union of the stores the builder's own ``universe()`` reads, resolved without
    importing it — ``build_stock_library`` pulls a very large import graph and
    would also re-read every close series we do not need here.

    Fail-soft and DELIBERATELY over-inclusive: a name wrongly counted as curated
    is merely not scanned tonight, whereas a name wrongly counted as new gets a
    duplicate row. Keep-first in the store is the second fence behind this one.
    """
    curated: set[str] = set()
    stocks = root / "data" / "stocks"
    if stocks.is_dir():
        curated |= {p.stem for p in stocks.glob("*.parquet")}
    import pandas as pd
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
        cons = root / "data" / grp / "constituents.parquet"
        try:
            curated |= {str(t) for t in pd.read_parquet(cons).index}
        except Exception:  # noqa: BLE001 — a missing band shrinks the exclusion, never fatal
            log.info("curated_universe: %s constituents absent", grp)
    yahoo = root / "data" / "yahoo"
    if yahoo.is_dir():
        curated |= {p.stem for p in yahoo.glob("*.parquet") if not p.stem.startswith("_")}
    return curated


def stamp_context_vector(root: Path, tickers: list[str], disclosure: dict,
                         *, advance: bool, with_context_dims: bool = True,
                         liquidity: dict | None = None) -> int:
    """Stamp one ``tier="scan"`` context row per scan name. Returns rows in the part.

    Reads the whole-market store for closes AND volumes: the curated volume
    caches carry only S&P-1500 names, so passing them here would null the entire
    turnover block for every scan name and print that null as if it had been
    measured.

    Fail-soft by contract, exactly like the curated stamp — research telemetry
    must never take a lane down.
    """
    if not advance:
        log.info("context-vector stamp SKIPPED (not --nightly)")
        return 0
    import pandas as pd

    from engine import signal_gate, us_board_rank, us_context_vector as UCV

    price_through = disclosure.get("price_through")
    if not price_through or not tickers:
        return 0

    t0 = time.time()
    closes = USU.close_panel(root, tickers)
    if closes.empty:
        # Bare print at column 0: GitHub only parses a workflow command at line
        # start, and every logger here prefixes the line (repo annotation law).
        print("::warning title=us-scan-tier::scan close panel empty — nothing stamped",
              flush=True)
        return 0
    log.info("scan close panel: %s in %.1fs", closes.shape, time.time() - t0)

    # Volume panel from the same store, so turnover_pctile_20d is real for scan
    # names instead of a confident null off a cache that never held them.
    vols: dict[str, pd.Series] = {}
    for ticker in closes.columns:
        p = USU.store_dir(root) / f"{ticker}.parquet"
        try:
            series = pd.read_parquet(p, columns=["volume"])["volume"].dropna()
        except Exception:  # noqa: BLE001
            continue
        if not series.empty:
            if not isinstance(series.index, pd.DatetimeIndex):
                series.index = pd.to_datetime(series.index)
            vols[ticker] = series.sort_index()
    volumes = pd.DataFrame(vols).sort_index() if vols else None

    t1 = time.time()
    verdicts: dict[str, dict] = {}
    for ticker in closes.columns:
        series = closes[ticker].dropna()
        if series.empty:
            continue
        try:
            verdicts[ticker] = signal_gate.gate(ticker, series)
        except Exception:  # noqa: BLE001 — one bad name must not empty the tier
            continue
    log.info("scan gate pass: %d verdicts in %.1fs (%.0f ms/name)",
             len(verdicts), time.time() - t1,
             1000 * (time.time() - t1) / max(len(verdicts), 1))

    t2 = time.time()
    rows = UCV.append_candidates(
        verdicts, price_through,
        board_definition=us_board_rank.BOARD_DEFINITION,
        is_buyable=signal_gate.is_buyable,
        closes=closes,
        volumes=volumes,
        root=root,
        tier=UCV.TIER_SCAN,
        liquidity=liquidity or {},
        with_context_dims=with_context_dims,
    )
    log.info("us_context_vector (scan): part now %d rows (%.1fs)", rows, time.time() - t2)
    return rows


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="US scan tier — widened seeing set (§4.5)")
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance: write the artifact, append the forward-log row, "
                         "and stamp the context vector (the SOLE advancer)")
    ap.add_argument("--out-dir", default=None,
                    help="scratch dir for a safe local run (writes there, never the real store)")
    ap.add_argument("--no-stamp", action="store_true",
                    help="skip the context-vector stamp (audit artifact only)")
    ap.add_argument("--no-context-dims", action="store_true",
                    help="skip the 11-dimension Context Snapshot block (halves the assembly)")
    ap.add_argument("--top-n", type=int, default=PMA.SCAN_TOP_N)
    args = ap.parse_args()

    root = ROOT
    if not USU.store_available(root):
        # Line-start bare print: GitHub drops a logger-prefixed ::warning (repo law).
        print(f"::warning title=us-scan-tier::{USU.STORE_REL} is not restored in this lane — "
              "the scan tier was NOT measured tonight (a null, not an absence of runners)",
              flush=True)

    t0 = time.time()
    curated = curated_universe(root)
    # ONE store census for the whole lane: the audit and the context-vector stamp
    # need the same resolved set, and the census is a 30-second read of 20k files.
    # Resolution itself goes through us_scan_universe so this lane cannot drift
    # from the module's own definition of "floored minus curated".
    frame = USU.census(root)
    scan_tickers, floor, liquidity = USU.resolve_from_census(frame, root, curated=curated)

    doc = PMA.build_scan_tier_audit(root, top_n=args.top_n, curated=curated,
                                    tickers=scan_tickers, floor=floor)
    print_scan_summary(doc, curated_n=len(curated), elapsed=time.time() - t0)

    # Two SEPARATE gates, deliberately not one variable.
    #   write_artifact — --nightly OR --out-dir (the scratch dir is a real write,
    #                    just not to the real store).
    #   stamp_store    — --nightly ONLY. The context vector's monthly part is a
    #                    shared PIT ledger with no out-dir redirection: passing the
    #                    out-dir's advance through here would make a "safe local
    #                    test" append tier="scan" rows to the REAL store whenever
    #                    the lane env happened to be armed. Nightly is the sole
    #                    advancer, and --out-dir is not nightly.
    stamp_store = bool(args.nightly)
    if args.out_dir:
        artifact = Path(args.out_dir) / "latest.json"
        forward = Path(args.out_dir) / "forward_log.jsonl"
        write_artifact = True
    else:
        artifact = root / PMA.SCAN_ARTIFACT_REL
        forward = root / PMA.SCAN_FORWARD_LOG_REL
        write_artifact = bool(args.nightly)

    if write_artifact:
        PMA._atomic_write_json(artifact, doc)
        wrote = _append_scan_log(doc, forward)
        print(f"  writes: artifact -> {artifact}, "
              f"forward_log={'appended' if wrote else 'no append (idempotent)'}")
    else:
        print("  writes: NONE (not --nightly)")

    if not args.no_stamp and doc.get("available"):
        # The WHOLE scan tier is stamped, not just the runners: the store's value
        # is that a name which never ran is present too, with its reason — the
        # same law that makes the curated store carry ineligible names.
        if args.out_dir and not args.nightly:
            print("  context-vector stamp SKIPPED (--out-dir is a scratch run; the "
                  "store has no out-dir redirection and nightly is its sole advancer)")
        else:
            stamp_context_vector(root, scan_tickers, floor, advance=stamp_store,
                                 with_context_dims=not args.no_context_dims,
                                 liquidity=liquidity)
    return 0


def _append_scan_log(doc: dict, path: Path) -> bool:
    """Idempotent forward append on ``price_through`` (same law as the W0 log)."""
    import json
    row = {
        "price_through": doc.get("price_through"),
        "schema": doc.get("schema"),
        "available": doc.get("available"),
        "null_reason": doc.get("null_reason"),
        **{k: (doc.get("summary") or {}).get(k) for k in (
            "store_n", "floored_n", "curated_overlap_n", "scan_n", "panel_n",
            "runners_n", "runners_eligible_today_n", "runners_never_eligible_n",
            "runners_never_eligible_pct")},
        "excluder_family_hist": doc.get("excluder_family_hist") or {},
        "degraded_n": len(doc.get("degraded") or []),
    }
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    prev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prev.get("price_through") == row["price_through"]:
                    return False
        except OSError:
            pass
    PMA._append_jsonl(path, row)
    return True


def print_scan_summary(doc: dict, *, curated_n: int, elapsed: float) -> None:
    print(f"[us-scan-tier] price_through={doc.get('price_through')} "
          f"available={doc.get('available')} ({elapsed:.1f}s)")
    floor = doc.get("floor") or {}
    print(f"  floor: {floor.get('rule')}")
    if not doc.get("available"):
        print(f"  NULL — {doc.get('null_reason')}")
        return
    s = doc.get("summary") or {}
    print(f"  store {s.get('store_n')} -> floored {s.get('floored_n')} "
          f"-> minus curated ({curated_n}) overlap {s.get('curated_overlap_n')} "
          f"=> SCAN TIER {s.get('scan_n')}")
    for reason, n in (floor.get("excluded_by_reason") or {}).items():
        print(f"    excluded {reason:24s} {n}")
    print(f"  runners: {s.get('runners_n')}, eligible today "
          f"{s.get('runners_eligible_today_n')}, never eligible "
          f"{s.get('runners_never_eligible_n')}")
    for k, v in (doc.get("excluder_family_hist") or {}).items():
        print(f"    {k:36s} {v}")
    for d in doc.get("degraded") or []:
        print(f"  DEGRADED {d['input']}: {d['reason']}")


if __name__ == "__main__":
    raise SystemExit(main())
