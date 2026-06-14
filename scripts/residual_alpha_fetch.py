"""One-time DEEP-history close fetch for the full S&P 1500 — the residual-alpha
Phase 0 power fix (research/RESIDUAL_ALPHA_MOMENTUM.md §4a).

The live breadth cache is only ~3 years (rolled forward nightly), which is the
binding power bottleneck on the broad IC test. This pulls yfinance 'max' closes
for every CURRENT constituent and caches one wide matrix at
data/breadth/_closes_deep.parquet, so the harness can run the broad cross-section
over decades instead of 23 months.

Survivorship caveat (loud, on purpose): these are CURRENT members back to
inception — a basket of known survivors, which biases momentum profitability
UPWARD. This fixes statistical POWER, not survivorship. Read the re-run with that
asymmetry in mind: a FAIL even here is a strong kill; a PASS must be discounted
for the bias and confirmed with point-in-time membership.

Reuses the sanctioned BreadthAdapter batched download (retry/backoff/throttle).
Run once, offline:  .venv/bin/python -m scripts.residual_alpha_fetch
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter  # noqa: E402
from lib import config  # noqa: E402


def main() -> int:
    tickers: list[str] = []
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            tickers += list(pd.read_parquet(p).index.astype(str))
    tickers = sorted(set(tickers))
    if not tickers:
        print("no constituents on disk — run breadth collectors first")
        return 1

    print(f"[fetch] {len(tickers)} tickers · yfinance 'max' (batched) — this takes a few minutes …",
          flush=True)
    closes = BreadthAdapter()._download_closes(tickers, "max")
    closes = closes.loc[:, ~closes.columns.duplicated()].dropna(axis=1, how="all").sort_index()

    out = config.data_dir() / "breadth" / "_closes_deep.parquet"
    closes.to_parquet(out)

    per_name = closes.notna().sum()
    print(f"[done] matrix {closes.shape} · {closes.index.min().date()}..{closes.index.max().date()}",
          flush=True)
    print(f"[cov]  names total {closes.shape[1]} · with >5y {int((per_name > 1260).sum())} · "
          f"with >15y {int((per_name > 3780).sum())} · median daily names "
          f"{int(closes.notna().sum(axis=1).median())}")
    print(f"[out]  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
