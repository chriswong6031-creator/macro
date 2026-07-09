#!/usr/bin/env python3
"""Export per-ticker Insider Power artifacts for the Mastermind Terminal.

Reads the point-in-time Form-4 panel (data/sec_insider/insider_panel.parquet),
runs engine.insider_power.compute (the ONE source of truth for the scoring), and
writes one `<TICKER>.insider.json` per name into an output directory. The
Terminal fetches these from `/data/<SYM>.insider.json` (served by Caddy), the
same convention as `<SYM>.fund.json` / `<SYM>.opts.json`.

Usage:
    # every ticker with recent open-market activity → site/data/
    python scripts/export_insider_power.py --out site/data

    # just a few (e.g. to refresh the Terminal's local-dev fixtures)
    python scripts/export_insider_power.py --out /path/to/terminal/public/data \
        --tickers AAPL NVDA TSLA XOM

    # pin the as-of date (defaults to the panel's latest filing date)
    python scripts/export_insider_power.py --out site/data --asof 2026-03-31

Nightly pipeline: run with --out pointing at the site data store, then rsync to
the VPS `/data` mount (same path other per-ticker artifacts already ride).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import insider_power  # noqa: E402

PANEL = Path("data/sec_insider/insider_panel.parquet")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output directory for <SYM>.insider.json files")
    ap.add_argument("--panel", default=str(PANEL), help="path to insider_panel.parquet")
    ap.add_argument("--tickers", nargs="*", help="restrict to these tickers (default: all with activity)")
    ap.add_argument("--asof", default=None, help="as-of date YYYY-MM-DD (default: panel max filing_date)")
    args = ap.parse_args()

    panel_path = Path(args.panel)
    if not panel_path.exists():
        print(f"panel not found: {panel_path}", file=sys.stderr)
        return 2
    panel = pd.read_parquet(panel_path)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    payloads = insider_power.compute(panel, asof=args.asof, tickers=args.tickers)
    asof = payloads[next(iter(payloads))]["asof"] if payloads else args.asof
    n = 0
    for ticker, payload in payloads.items():
        # Ticker symbols may contain '/' (rare share-class notation) — sanitize.
        safe = ticker.replace("/", "-")
        (out_dir / f"{safe}.insider.json").write_text(
            json.dumps(payload, separators=(",", ":")))
        n += 1

    print(f"wrote {n} insider-power artifacts to {out_dir} (asof {asof})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
