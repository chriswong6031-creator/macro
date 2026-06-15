"""Phase-0 (RESEARCH-ONLY) for the OKX retail positioning chips (P1a).

Honest prior = DISPLAY. Two reasons: (a) rubik retail/taker history is shallow
(~180d), so the sample is tiny and any split-half is impossible; (b) the same
single-asset-timing trap that flipped the carry signal and the CME basis applies
— crowding is a fragility/context read, not a directional edge.

This is a SINGLE-ASSET TIME-SERIES test (one BTC series), so it uses a rolling
Spearman IC, not the panel rank-IC stack. It imports btc_inputs / btc_signals /
validation, prints a verdict, and WIRES NOTHING. See OKX_RETAIL_CHIPS_SPEC.md §5.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_inputs, btc_signals  # noqa: E402
from engine import validation as V  # noqa: E402

HORIZONS = [21, 63]
MIN_POWER_OBS = 250          # below this the read is underpowered -> DISPLAY


def _fwd(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def _rolling_ic(sig: pd.Series, fwd: pd.Series, win: int = 63, step: int = 5) -> list:
    """Single-asset rolling-window Spearman IC: signal_t vs forward-return_t over
    each ~quarter window (>=10 joint obs per window via validation.rank_ic)."""
    idx = sig.dropna().index.intersection(fwd.dropna().index)
    s, f = sig.reindex(idx), fwd.reindex(idx)
    ics = []
    for i in range(win, len(idx) + 1, step):
        ic = V.rank_ic(s.iloc[i - win:i].values, f.iloc[i - win:i].values)
        if np.isfinite(ic):
            ics.append(ic)
    return ics


def main() -> None:
    inp = btc_inputs.load_all()
    sig = btc_signals.compute_all(inp)
    close = inp["price"]["close"]
    if "okx_ls_ratio_z" not in sig.columns:
        print("okx columns absent (collector not run yet) -> DISPLAY")
        return

    n_obs = int(sig["okx_ls_ratio_z"].dropna().shape[0])
    print(f"OKX rubik usable obs: {n_obs} (power floor {MIN_POWER_OBS})")

    cands = {"ls_z": sig.get("okx_ls_ratio_z"), "taker": sig.get("okx_taker_buy")}
    rows, pvals = [], {}
    for name, s in cands.items():
        if s is None:
            continue
        for h in HORIZONS:
            summ = V.ic_summary(_rolling_ic(s, _fwd(close, h)), periods_per_year=max(1, 252 // h))
            pvals[f"{name}@{h}"] = summ.get("p_hac")
            rows.append((f"{name}@{h}", summ.get("mean_ic"), summ.get("t_hac"),
                         summ.get("p_hac"), summ.get("n")))

    # incremental over the named incumbents (funding_z CONFIRMED + oi_mcap_pctile)
    base = [sig[c] for c in ("funding_z", "oi_mcap_pctile") if c in sig.columns]
    if base and cands["ls_z"] is not None:
        resid = V.resid_z(cands["ls_z"], basis=base, win=120, min_p=60)
        for h in HORIZONS:
            summ = V.ic_summary(_rolling_ic(resid, _fwd(close, h)), periods_per_year=max(1, 252 // h))
            pvals[f"resid_ls@{h}"] = summ.get("p_hac")
            rows.append((f"resid_ls@{h}", summ.get("mean_ic"), summ.get("t_hac"),
                         summ.get("p_hac"), summ.get("n")))

    bh = V.benjamini_hochberg({k: v for k, v in pvals.items() if v is not None}, alpha=0.10)
    print("\n  trial            mean_ic    t_hac      p      n")
    for nm, ic, t, p, n in rows:
        print(f"  {nm:14s} {str(ic):>8} {str(t):>8} {str(p):>7} {str(n):>5}")
    survivors = [k for k, v in bh.items() if v["reject"]]
    print("\n  BH-FDR rejects:", survivors or "none")

    if n_obs < MIN_POWER_OBS:
        verdict = "DISPLAY (underpowered — rubik history too shallow for a stable estimate)"
    elif survivors:
        verdict = "PROMOTE-CANDIDATE (separate follow-up, never auto-wire): " + ", ".join(survivors)
    else:
        verdict = "DISPLAY (no incremental edge survives BH-FDR over funding+OI)"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
