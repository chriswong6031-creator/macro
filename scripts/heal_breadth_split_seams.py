"""One-shot healer for split seams in runner-local breadth close caches.

The nightly collector now self-heals these seams (BreadthAdapter._merge_refreshed),
but only where it runs. This script repairs OTHER checkouts' gitignored caches in
place — e.g. the main checkout's data/breadth/_closes_cache.parquet, which scripts
(build_impulse, calibrate_bottom_radar, ad-hoc studies) read directly between
collector runs. 2026-07-10 incident: KLAC $1,842.80 -> $180.90 across 2026-05-11/12
(10:1 split back-adjusted only inside the refresh window), plus CRWD 4:1 and a DD
re-basing in the same cache.

For every ticker flagged by the same seam scan the collector uses, the full cache
window is re-downloaded (auto-adjusted, hence a coherent basis) and the column
replaced wholesale in the closes cache AND the _high/_low/_volume extras caches.
Flagged tickers whose re-pull matches the cache (genuine ±40% news days: CNC,
SATS, FISV...) are reported as "real move" and rewritten unchanged.

For the breadth universes this touches ONLY the gitignored cache parquets — never
committed series (breadth.parquet recomputes from the healed cache on the next
collector run). The --closes-files targets (search-universe closes.parquet, hk_search
closes_deep.parquet — 2026-07-10 follow-up audit) are COMMITTED wide matrices with the
same vulnerability: heal those inside a PR worktree so the fix ships through review
(the fixed collectors self-heal any seam that forms after that, but their nightly scan
is windowed to ~18 months — this script is the full-history legacy sweep).

Usage:
  python scripts/heal_breadth_split_seams.py --data-dir /path/to/data \
      [--universes breadth smallcap_breadth midcap_breadth] \
      [--closes-files intl_search/closes.parquet ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import seam_suspects  # noqa: E402

EXTRAS = {"_high_cache": "High", "_low_cache": "Low", "_volume_cache": "Volume"}


def _download(tickers: list[str], period: str) -> pd.DataFrame:
    raw = yf.download(tickers, period=period, auto_adjust=True,
                      progress=False, group_by="column", threads=True)
    if not isinstance(raw.columns, pd.MultiIndex):
        # single-ticker frame: plain Field columns -> (Field, ticker)
        raw.columns = pd.MultiIndex.from_product([raw.columns, tickers[:1]])
    return raw


def heal(udir: Path, dry: bool) -> None:
    cpath = udir / "_closes_cache.parquet"
    if not cpath.exists():
        print(f"{udir.name}: no closes cache — skipped")
        return
    closes = pd.read_parquet(cpath)
    bad = seam_suspects(None, None, closes)
    if not bad:
        print(f"{udir.name}: clean ({closes.shape[1]} tickers) — nothing to do")
        return
    span_years = max(1, (closes.index.max() - closes.index.min()).days // 365 + 1)
    print(f"{udir.name}: {len(bad)} flagged ticker(s): {bad}")
    if dry:
        return
    raw = _download(bad, f"{span_years}y")
    fresh_closes = raw["Close"]
    healed, real_moves, missed = [], [], []
    for t in bad:
        if t not in fresh_closes.columns or not fresh_closes[t].notna().any():
            missed.append(t)
            continue
        new = fresh_closes[t].reindex(closes.index)
        diff = (new / closes[t] - 1).abs().max()
        (real_moves if pd.notna(diff) and diff < 0.005 else healed).append(t)
        closes[t] = new
    closes.to_parquet(cpath)
    for cache_name, field in EXTRAS.items():
        epath = udir / f"{cache_name}.parquet"
        if not epath.exists() or field not in raw.columns.get_level_values(0):
            continue
        ex = pd.read_parquet(epath)
        for t in healed + real_moves:
            if t in ex.columns and t in raw[field].columns:
                ex[t] = raw[field][t].reindex(ex.index)
        ex.to_parquet(epath)
    print(f"{udir.name}: healed seams {healed}; real moves rewritten unchanged "
          f"{real_moves}; no data (left as-is) {missed}")


def heal_file(path: Path, dry: bool) -> None:
    """Heal one standalone wide-closes parquet (no OHLCV extras siblings).

    Same scan + wholesale column replacement as heal(), but the re-pull window
    is derived from the FILE's own span ("max" beyond 10y — hk closes_deep goes
    back to 1986) so the reindex never truncates deep history the file carries."""
    if not path.exists():
        print(f"{path}: missing — skipped")
        return
    closes = pd.read_parquet(path)
    label = f"{path.parent.name}/{path.name}"
    bad = seam_suspects(None, None, closes)
    if not bad:
        print(f"{label}: clean ({closes.shape[1]} tickers) — nothing to do")
        return
    span_years = max(1, (closes.index.max() - closes.index.min()).days // 365 + 1)
    period = "max" if span_years > 10 else f"{span_years}y"
    print(f"{label}: {len(bad)} flagged ticker(s): {bad}")
    if dry:
        return
    raw = _download(bad, period)
    fresh_closes = raw["Close"]
    healed, real_moves, missed = [], [], []
    for t in bad:
        if t not in fresh_closes.columns or not fresh_closes[t].notna().any():
            missed.append(t)
            continue
        new = fresh_closes[t].reindex(closes.index)
        diff = (new / closes[t] - 1).abs().max()
        (real_moves if pd.notna(diff) and diff < 0.005 else healed).append(t)
        closes[t] = new
    closes.to_parquet(path)
    print(f"{label}: healed seams {healed}; real moves rewritten unchanged "
          f"{real_moves}; no data (left as-is) {missed}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", required=True, type=Path,
                    help="the data/ directory whose caches to heal")
    ap.add_argument("--universes", nargs="+",
                    default=["breadth", "smallcap_breadth", "midcap_breadth",
                             "china_breadth", "hk_breadth", "canada_breadth"])
    ap.add_argument("--closes-files", nargs="*",
                    default=["intl_search/closes.parquet", "china_search/closes.parquet",
                             "canada_search/closes.parquet", "hk_search/closes_deep.parquet"],
                    help="standalone wide-closes parquets (relative to --data-dir); "
                         "pass an empty list to skip")
    ap.add_argument("--dry-run", action="store_true",
                    help="report flagged tickers without downloading or writing")
    args = ap.parse_args()
    for uni in args.universes:
        heal(args.data_dir / uni, args.dry_run)
    for rel in args.closes_files:
        heal_file(args.data_dir / rel, args.dry_run)


if __name__ == "__main__":
    main()
