"""Heal stock-column unit artifacts in the committed EDGAR fundamentals panel.

The full fix runs inside collectors.edgar.fetch_panel on every panel rebuild
(weekly cache), where the statements.parquet cross-source lane runs alongside the
segmentation/flank lane.  This script applies the same detector/repair to the
ALREADY-COMMITTED data/edgar/fundamentals_panel.parquet so PIT factor backtests
are honest immediately, without waiting for a full frames-API refetch.

Columns repaired: assets, equity, debt_lt.
See collectors/edgar_stock_quality.py for the full detection/repair design.

Idempotent; run from any checkout that has the panel:

    python -m scripts.heal_stock_unit_artifacts [--dry-run]

Writes the healed parquet in place, a full audit to
data/edgar/_stock_quality_audit.json, and a stock_quality block into
data/edgar/_panel_meta.json (without touching the built timestamp).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from lib import config
from lib.procutil import hard_exit
from collectors.edgar_stock_quality import apply_stock_quality

log = logging.getLogger(__name__)

_STMT_COLS = ["ticker", "fy", "assets", "equity", "debt_lt"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="detect and print; write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    panel_p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not panel_p.exists():
        log.error("no %s — run collectors.edgar.fetch_panel first", panel_p)
        return 1
    panel = pd.read_parquet(panel_p)

    # Load statements (optional — proceed with None and log if absent/corrupt)
    statements: pd.DataFrame | None = None
    stmt_p = config.data_dir() / "edgar" / "statements.parquet"
    if stmt_p.exists():
        try:
            statements = pd.read_parquet(stmt_p, columns=_STMT_COLS)
            log.info("statements.parquet loaded: %d rows", len(statements))
        except Exception as exc:  # noqa: BLE001
            log.warning("statements.parquet load failed (%s) — xsrc lane skipped", exc)
    else:
        log.warning("statements.parquet not found — xsrc lane skipped")

    healed, audit = apply_stock_quality(panel, statements=statements)

    # Print summary
    print(f"flagged {audit['rows_flagged']} rows on {audit['tickers_flagged']} tickers: "
          f"{audit['by_flag']} — {audit['repaired']} repaired, "
          f"{audit['mirrors']} assets_prior mirrors")
    print()

    # Per-row flag table
    if audit["rows"]:
        print(f"{'ticker':>8}  {'fy':>4}  {'col':<14}  {'flag':<14}  "
              f"{'raw':>18}  {'repair':>18}  note")
        print("-" * 90)
        for r in audit["rows"]:
            print(f"  {r['ticker']:>6}  {r['fy']:>4}  {r['col']:<14}  "
                  f"{r['flag']:<14}  {r['raw']:>18.6g}  {r['repair']:>18.6g}  "
                  f"{r['note']}")
    else:
        print("  (no flags)")

    print()

    # xsrc_disagreements summary
    nd = len(audit["xsrc_disagreements"])
    if nd:
        print(f"xsrc_disagreements ({nd} unique ticker/fy/col pairs):")
        for d in audit["xsrc_disagreements"][:20]:
            print(f"  {d['ticker']:>6} fy{d['fy']} {d['col']:<14} "
                  f"panel={d['panel']:.6g}  statements={d['statements']:.6g}")
        if nd > 20:
            print(f"  ... and {nd - 20} more")
        print()

    # flank_suspects summary
    ns = len(audit["flank_suspects"])
    if ns:
        print(f"flank_suspects ({ns} segments; no mutation):")
        for s in audit["flank_suspects"][:20]:
            fy_range = (f"fy{s['fy_lo']}" if s["fy_lo"] == s["fy_hi"]
                        else f"fy{s['fy_lo']}-{s['fy_hi']}")
            print(f"  {s['ticker']:>6} {fy_range}  {s['col']:<14}  med={s['med']:.6g}")
        if ns > 20:
            print(f"  ... and {ns - 20} more")
        print()

    if args.dry_run:
        print("dry run — nothing written")
        return 0

    healed.to_parquet(panel_p)
    (config.data_dir() / "edgar" / "_stock_quality_audit.json").write_text(
        json.dumps(audit, indent=0))

    meta_p = config.data_dir() / "edgar" / "_panel_meta.json"
    try:
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    except Exception:  # noqa: BLE001
        meta = {}
    meta["stock_quality"] = {k: audit[k] for k in
                             ("applied", "rows_flagged", "tickers_flagged",
                              "by_flag", "repaired", "nulled", "mirrors")
                             if k in audit}
    meta_p.write_text(json.dumps(meta, indent=2))
    log.info("healed panel written to %s", panel_p)
    print(f"healed panel written to {panel_p}")
    return 0


if __name__ == "__main__":
    rc = main()
    hard_exit(rc)
