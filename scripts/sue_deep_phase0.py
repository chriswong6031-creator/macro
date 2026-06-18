"""Deep-history SUE re-validation — backfills the prices the shallow cache blocks.

`reports/sue-deep-history-phase0.md` showed SUE is validated only on the ~3y broad-universe
price cache (`engine.equity_factors._closes()`), while the EPS panel is deep (2008+, 1317
names) and PIT membership exists. This script backfills max-history adjusted closes for the
EPS universe (yfinance, batched, cached to `data/edgar/sue_deep_closes.parquet`) and re-runs
the SUE rank-IC / IC-IR / HAC-t / quintile-L/S over 2011→2026.

SURVIVORSHIP CAVEAT (load-bearing): yahoo serves only currently-listed tickers, so delisted
S&P members are absent — this deep read is survivorship-BIASED (an optimistic bound), the
SAME caveat the existing factor zoo carries (DATA_SIGNAL_EXPANSION #5). A truly clean deep
test needs delisting-recovered prices (harder / paid). The backfill is a large network pull
→ meant for CI / a one-off; the cache makes re-runs instant.

Run: .venv/bin/python -m scripts.sue_deep_phase0 [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.sue import load_panel, sue_cross_section  # noqa: E402
from engine.validation import ic_summary, rank_ic  # noqa: E402
from lib import config  # noqa: E402

CACHE = config.data_dir() / "edgar" / "sue_deep_closes.parquet"
OUT = config.data_dir() / "edgar" / "sue_deep_phase0.json"
H = 63
START_YEAR = 2011
BATCH = 80


def backfill(tickers: list[str], refresh: bool) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        df = pd.read_parquet(CACHE)
        df.index = pd.to_datetime(df.index)
        return df
    import yfinance as yf
    frames: dict[str, pd.Series] = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        try:
            d = yf.download(batch, period="max", auto_adjust=True, progress=False, threads=True)
            cl = d["Close"] if ("Close" in getattr(d.columns, "get_level_values", lambda _: [])(0)) else d
            if isinstance(cl, pd.Series):
                cl = cl.to_frame(batch[0])
            for c in cl.columns:
                s = cl[c].dropna()
                if len(s) > 252:
                    frames[str(c)] = s
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i // BATCH} failed: {type(e).__name__}", file=sys.stderr)
        print(f"  backfilled {len(frames)} ok / {min(i + BATCH, len(tickers))} attempted", file=sys.stderr)
    df = pd.DataFrame(frames).sort_index()
    df.index = pd.to_datetime(df.index)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE)
    return df


def quarter_ends(idx: pd.DatetimeIndex, start_year: int) -> list:
    out = []
    for d in pd.date_range(f"{start_year}-01-01", idx.max(), freq="QE"):
        prior = idx[idx <= d]
        if len(prior):
            out.append(prior[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    panel = load_panel()
    if panel is None:
        print("no eps panel — run collectors.edgar_eps"); return 1
    universe = sorted({t.replace(".", "-") for t in panel["ticker"].unique()})
    print(f"EPS universe {len(universe)} tickers; backfilling deep closes (survivorship-biased)…",
          file=sys.stderr)
    closes = backfill(universe, args.refresh)
    deep10 = int((closes.notna().sum() > 2520).sum())
    print(f"deep closes: {closes.shape}  span {str(closes.index.min())[:10]}..{str(closes.index.max())[:10]}  "
          f"{deep10} names with >10y")

    fwd = closes.pct_change(H, fill_method=None).shift(-H)
    grid = [d for d in quarter_ends(closes.index, START_YEAR) if d in fwd.index]
    ics, ls, n_names = [], [], []
    for d in grid:
        fr = fwd.loc[d].dropna()
        sue = sue_cross_section(panel, d)
        sue.index = [str(t).replace(".", "-") for t in sue.index]
        common = sue.index.intersection(fr.index)
        if len(common) >= 30:
            n_names.append(len(common))
            ics.append(rank_ic(sue.reindex(common), fr.reindex(common)))
            j = pd.concat([sue.reindex(common).rename("s"), fr.reindex(common).rename("f")], axis=1).dropna()
            if len(j) >= 40:
                q = pd.qcut(j["s"].rank(method="first"), 5, labels=False)
                ls.append(float(j["f"][q == 4].mean() - j["f"][q == 0].mean()))

    s = ic_summary(pd.Series(ics).dropna(), periods_per_year=4)
    lss = pd.Series(ls).dropna()
    ls_sharpe = float(lss.mean() / lss.std() * np.sqrt(4)) if len(lss) > 5 and lss.std() else None
    med_names = int(np.median(n_names)) if n_names else 0
    span = f"{grid[0].date()}..{grid[-1].date()}" if grid else "n/a"

    report = {"span": span, "quarters": len(grid), "median_names": med_names,
              "deep_names_gt10y": deep10, "mean_ic": s.get("mean_ic"), "ic_ir_ann": s.get("ic_ir_ann"),
              "t_hac": s.get("t_hac"), "hit": s.get("hit"), "n": s.get("n"),
              "ls_quintile_sharpe_ann": None if ls_sharpe is None else round(ls_sharpe, 3),
              "caveat": "survivorship-biased (delisted names absent) — optimistic bound; "
                        "clean deep test needs delisting-recovered prices."}
    OUT.write_text(json.dumps(report, indent=2, default=str))

    print("\n=== DEEP SUE (survivorship-biased) ===")
    print(f"span {span}, {len(grid)} quarters, ~{med_names} names/quarter")
    print(f"mean IC {s.get('mean_ic')}  IC-IR(ann) {s.get('ic_ir_ann')}  HAC t {s.get('t_hac')}  "
          f"hit {s.get('hit')}  n {s.get('n')}")
    print(f"quintile L/S Sharpe (ann): {report['ls_quintile_sharpe_ann']}")
    print(f"vs the shallow 2023-2025 read: IC 0.038, IC-IR 1.24, L/S Sharpe 1.45")
    print("CAVEAT:", report["caveat"])
    print(f"[wrote {OUT}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
