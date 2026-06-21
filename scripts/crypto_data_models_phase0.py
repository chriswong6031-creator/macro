"""Phase-0 validation for the three new crypto data-models (Coinbase Premium,
options/futures VRP + carry, spot-ETF USD flows). House rule: a signal only earns a
SCORED axis if it shows a same-sign forward-return edge in BOTH market halves; else it
ships as display/context. Prints rank-IC (Spearman) vs forward returns, full + split.

Run: python -m scripts.crypto_data_models_phase0
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import btc_signals


def _ic(x: pd.Series, fwd: pd.Series) -> float:
    d = pd.concat([x, fwd], axis=1).dropna()
    if len(d) < 60:
        return float("nan")
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank()))


def _row(sig, name, col, fwd, split):
    s = sig[col] if col in sig.columns else None
    if s is None:
        return f"{name:24s} <missing>"
    full = _ic(s, fwd)
    pre = _ic(s[sig.index < split], fwd[sig.index < split])
    post = _ic(s[sig.index >= split], fwd[sig.index >= split])
    same = (np.sign(pre) == np.sign(post)) and abs(pre) > 0.03 and abs(post) > 0.03
    verdict = "GO (both halves)" if same else "context (no robust 2-half edge)"
    return f"{name:24s} IC full={full:+.3f}  pre={pre:+.3f}  post={post:+.3f}  n={s.notna().sum():5d}  -> {verdict}"


def main() -> int:
    sig = btc_signals.compute_all()
    close = sig["close"]
    split = pd.Timestamp("2021-01-01")
    for h in (7, 30, 90):
        fwd = close.shift(-h) / close - 1.0
        print(f"\n================ forward {h}d return ================")
        print(_row(sig, "coinbase_premium_ema", "coinbase_premium_ema", fwd, split))
        print(_row(sig, "coinbase_premium_z", "coinbase_premium_z", fwd, split))
        print(_row(sig, "vrp_z", "vrp_z", fwd, split))
        print(_row(sig, "futures_carry_z", "futures_carry_z", fwd, split))
        print(_row(sig, "etf_usd_z", "etf_usd_z", fwd, split))
        print(_row(sig, "etf_concentration", "etf_concentration", fwd, split))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
