"""Heal share-count unit artifacts in the committed EDGAR fundamentals panel.

The full fix runs inside collectors.edgar.fetch_panel on every panel rebuild
(weekly cache), where the DEI cover-page counts are captured as a repair source.
This script applies the same detector/repair to the ALREADY-COMMITTED
data/edgar/fundamentals_panel.parquet so PIT factor backtests are honest
immediately, without waiting for (or forcing) a ~500-call frames refetch. On a
panel built before the shares_dei column existed, wrong-fact rows (ED class)
repair via prior-year carry-forward instead — still PIT-legal.

Idempotent; run from any checkout that has the panel:

    python -m scripts.heal_share_unit_artifacts [--dry-run] [--refresh-reference]

Writes the healed parquet in place, a full audit to
data/edgar/_share_quality_audit.json, and a share_quality block into
data/edgar/_panel_meta.json (without touching the built timestamp).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from lib import config
from collectors.edgar_share_quality import (
    apply_share_quality, build_reference, suspicious_tickers)

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="detect and print; write nothing")
    ap.add_argument("--refresh-reference", action="store_true",
                    help="refetch yfinance first-trade/split entries even if cached")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    panel_p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not panel_p.exists():
        log.error("no %s — run collectors.edgar.fetch_panel first", panel_p)
        return 1
    panel = pd.read_parquet(panel_p)

    ref = build_reference(suspicious_tickers(panel), refresh=args.refresh_reference)
    healed, audit = apply_share_quality(panel, ref)

    print(f"flagged {audit['rows_flagged']} rows on {audit['tickers_flagged']} tickers: "
          f"{audit['by_flag']} — {audit['repaired']} repaired, {audit['nulled']} nulled")
    for r in audit["rows"]:
        rep = "NULL" if r["repair"] is None else f"{r['repair']:.6g}"
        print(f"  {r['ticker']:>6} fy{r['fy']} {r['flag']:<16} "
              f"{r['shares_raw']:.6g} -> {rep}  ({r['note']})")

    if args.dry_run:
        print("dry run — nothing written")
        return 0

    healed.to_parquet(panel_p)
    (config.data_dir() / "edgar" / "_share_quality_audit.json").write_text(
        json.dumps(audit, indent=0))
    meta_p = config.data_dir() / "edgar" / "_panel_meta.json"
    try:
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    except Exception:  # noqa: BLE001
        meta = {}
    meta["share_quality"] = {k: audit[k] for k in
                             ("applied", "rows_flagged", "tickers_flagged",
                              "by_flag", "repaired", "nulled")}
    meta_p.write_text(json.dumps(meta, indent=2))
    print(f"healed panel written to {panel_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
