"""Phase-4 GEX validation gate: does the gamma regime track FORWARD realized vol?

The ONE falsifiable claim of the dealer-gamma layer (a VOL-REGIME effect, NOT
direction): short-gamma days (net GEX < 0 / spot below the zero-gamma flip) should
precede HIGHER forward realized vol than long-gamma days. Runs on the daily
per-symbol GEX summaries the collector accumulates (data/cboe/gex*.parquet).

There is NO free options history, so this FORWARD-ACCUMULATES: it honestly reports
"building history" until n per bucket clears MIN_PER_BUCKET, and its verdict GATES
whether GEX may ever touch the per-stock ladder SCORE (engine/cycles.py). If it never
beats a null, GEX stays display-only (the gex.html board + a context panel) and never
enters the scoring path — the same validate-before-weight rule the liquidity modifier
earned. Writes reports/gex-validation.md.

Run: .venv/bin/python -m scripts.validate_gex
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

MIN_PER_BUCKET = 30        # honest power floor before any verdict
HORIZONS = (5, 10)
N_BOOT = 2000


def _fwd_rv(spot: pd.Series, h: int) -> pd.Series:
    """Forward h-day realized vol (annualized), aligned to day t (uses t+1..t+h)."""
    r = np.log(pd.to_numeric(spot, errors="coerce")).diff()
    return r.rolling(h).std().shift(-h) * np.sqrt(252)


def _regime(d: pd.DataFrame):
    if "gamma_regime" in d and d["gamma_regime"].notna().any():
        return d["gamma_regime"].map({"long": 1.0, "short": -1.0})
    if "net_gex_bn" in d:
        return np.sign(pd.to_numeric(d["net_gex_bn"], errors="coerce"))
    if "spot_vs_flip_pct" in d:      # legacy SPX frame
        return np.sign(pd.to_numeric(d["spot_vs_flip_pct"], errors="coerce"))
    return None


def _boot(longg: np.ndarray, shortg: np.ndarray):
    """Bootstrap CI of (short-gamma mean RV - long-gamma mean RV). Positive = claim holds."""
    diffs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        diffs[i] = (np.random.choice(shortg, len(shortg)).mean()
                    - np.random.choice(longg, len(longg)).mean())
    return float(shortg.mean() - longg.mean()), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def evaluate(name: str, d: pd.DataFrame) -> list[str]:
    if "spot" not in d.columns or len(d) < 5:
        return [f"{name}: n={len(d)} — building history"]
    reg = _regime(d)
    if reg is None:
        return [f"{name}: no regime column"]
    d = d.copy()
    d["reg"] = np.asarray(reg, dtype=float)
    out = []
    for h in HORIZONS:
        df = pd.DataFrame({"reg": d["reg"].values, "rv": _fwd_rv(d["spot"], h).values}).dropna()
        longg = df[df["reg"] > 0]["rv"].to_numpy()
        shortg = df[df["reg"] < 0]["rv"].to_numpy()
        if len(longg) < MIN_PER_BUCKET or len(shortg) < MIN_PER_BUCKET:
            out.append(f"{name} h={h}d: building history (long n={len(longg)}, short n={len(shortg)}; "
                       f"need {MIN_PER_BUCKET}/bucket)")
            continue
        diff, lo, hi = _boot(longg, shortg)
        verdict = "PASS — short>long, CI excludes 0" if lo > 0 else "NO EDGE — CI includes 0 → display-only"
        out.append(f"{name} h={h}d: short_RV−long_RV={diff:+.3f} [{lo:+.3f}, {hi:+.3f}] "
                   f"(long n={len(longg)}, short n={len(shortg)}) → {verdict}")
    return out


def main() -> int:
    files = sorted(glob.glob(str(config.data_dir() / "cboe" / "gex*.parquet")))
    lines = ["# GEX validation — gamma regime vs forward realized vol", "",
             "Falsifiable claim: short-gamma days precede HIGHER forward realized vol than long-gamma days.",
             "Forward-accumulating (no free options history). This verdict GATES any ladder weight; "
             "until it PASSES, GEX is display-only and never touches the score.", ""]
    if not files:
        lines.append("- no GEX history yet (collector has not run)")
    for f in files:
        try:
            lines += ["- " + ln for ln in evaluate(Path(f).stem, pd.read_parquet(f))]
        except Exception as e:  # noqa: BLE001
            lines.append(f"- {Path(f).stem}: read error ({e})")
    report = "\n".join(lines)
    print(report)
    out = config.ROOT / "reports" / "gex-validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
