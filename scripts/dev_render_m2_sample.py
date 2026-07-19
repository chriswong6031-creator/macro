"""scripts/dev_render_m2_sample.py — Dev-only M2 overlay sample renderer.

Usage:
    python scripts/dev_render_m2_sample.py --tickers AAPL,NVDA,JPM --out-dir /tmp/m2_charts

For each ticker: loads OHLCV (last 120 bars), builds M2 overlays (AVWAP +
POC), renders a v2 candlestick chart, and writes <out-dir>/<TICKER>_m2.svg.

Never writes outside --out-dir. Not wired into any pipeline.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render M2-overlay sample charts for given tickers."
    )
    parser.add_argument(
        "--tickers",
        default="AAPL,NVDA,JPM",
        help="Comma-separated ticker list (default: AAPL,NVDA,JPM)",
    )
    parser.add_argument(
        "--out-dir",
        default="/tmp/m2_charts",
        help="Output directory for SVG files (default: /tmp/m2_charts)",
    )
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Repo root: two levels up from this script
    repo_root = Path(__file__).resolve().parent.parent

    # Ensure engine package is importable
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from engine.marketing.chart_render import (
        load_ohlcv,
        build_m2_overlays,
        render_chart_v2,
    )

    written: list[str] = []

    for ticker in tickers:
        ohlcv = load_ohlcv(ticker, repo_root, n=120)
        if ohlcv is None:
            print(f"[SKIP] {ticker}: no OHLCV data at {repo_root / 'data' / 'stocks' / f'{ticker}.parquet'}")
            continue

        dates, o, h, l, c, v = ohlcv

        overlays = build_m2_overlays(ticker, dates, o, h, l, c, v, repo_root)

        svg = render_chart_v2(
            ticker=ticker,
            dates=dates,
            o=o,
            h=h,
            l=l,
            c=c,
            volume=v,
            indicators=("volume", "macd"),
            avwap_overlay=overlays.get("avwap_overlay"),
            poc_overlay=overlays.get("poc_overlay"),
        )

        out_path = out_dir / f"{ticker}_m2.svg"
        out_path.write_text(svg, encoding="utf-8")
        written.append(str(out_path))
        print(f"[OK] {ticker}: wrote {out_path}")

    if not written:
        print("No charts written.")
        sys.exit(1)

    print(f"\nWrote {len(written)} chart(s):")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
