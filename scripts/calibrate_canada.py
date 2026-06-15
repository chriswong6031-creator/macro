"""Canada regime calibration — DIAGNOSTIC ONLY (v1).

Measures whether the Canada quad / overlay actually differentiate S&P/TSX Composite
forward returns, split-half for robustness, and writes reports/canada-calibration.md.
Unlike calibrate_china/hk this does NOT auto-rewrite the config priors — the Canada
engine ships with HK-mirrored priors and this report is the evidence base for a
later, deliberate re-weight (see the Canada plan's follow-ups). Returns 0 always.

Usage: python -m scripts.calibrate_canada
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("calibrate_canada")


def _fwd_returns(px: pd.Series, horizon: int) -> pd.Series:
    return px.shift(-horizon) / px - 1.0


def _by_quad(hist: pd.DataFrame, fwd: pd.Series) -> pd.DataFrame:
    df = hist[["quad", "quad_name"]].join(fwd.rename("fwd")).dropna(subset=["quad", "fwd"])
    g = df.groupby("quad_name")["fwd"]
    out = pd.DataFrame({"n": g.count(), "mean_%": (g.mean() * 100).round(2),
                        "hit_%": (g.apply(lambda s: (s > 0).mean()) * 100).round(1)})
    return out.sort_values("mean_%", ascending=False)


def main() -> int:
    try:
        cfg = config.load()["canada"]["engine"]["calibration"]
        hist = store.read("canada_regime", "regime_history")
        mi = config.load()["canada"]["yahoo"]["market_index"]
        mdf = store.read("canada", mi)
        if hist is None or mdf is None:
            log.warning("canada calibration: missing regime history or prices; skipping")
            return 0
        px = mdf["close"].reindex(hist.index).ffill()
        split = pd.Timestamp(cfg["split_date"])
        lines = ["# Canada / S&P/TSX regime calibration (diagnostic)\n",
                 f"_Generated from {hist.index.min().date()} → {hist.index.max().date()}; "
                 f"split at {split.date()}. Priors are HK-mirrored and NOT auto-applied — "
                 "this is the evidence base for a later deliberate re-weight._\n"]
        for h in cfg["forward_days"]:
            fwd = _fwd_returns(px, h)
            lines.append(f"\n## Forward {h}d returns by quad\n")
            lines.append("**Full sample**\n\n" + _by_quad(hist, fwd).to_markdown())
            lo, hi = hist[hist.index < split], hist[hist.index >= split]
            if len(lo) > 60:
                lines.append("\n\n**Pre-split**\n\n" + _by_quad(lo, fwd.reindex(lo.index)).to_markdown())
            if len(hi) > 60:
                lines.append("\n\n**Post-split**\n\n" + _by_quad(hi, fwd.reindex(hi.index)).to_markdown())
            lines.append("\n")
        out = config.ROOT / "reports" / "canada-calibration.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(str(x) for x in lines))
        log.info("wrote %s", out)
    except Exception as e:  # noqa: BLE001 — diagnostic, never fatal
        log.error("canada calibration failed (%s); skipping", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
