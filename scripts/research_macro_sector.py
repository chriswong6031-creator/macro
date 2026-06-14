"""B-1 sign-check — the SHIP GATE for the macro-risk sector overlay.

The dislocation validation (research/DISLOCATION_VALIDATION.md) was run on SPY,
the index. Before we let a per-sector macro penalty go live we must confirm the
ONE thing the overlay assumes generalizes cross-sectionally:

    under HIGH macro risk (MRS), CYCLICAL sectors (XLK/XLY/XLF/XLC/XLI/XLB)
    realize DEEPER forward-63d drawdowns than DEFENSIVE sectors (XLP/XLU/XLV) —
    and the SIGN is stable across split halves.

We deliberately do NOT require a return edge (the dislocation work showed that bar
is unmet). We require only the drawdown-ordering sign. The 11 SPDRs have deep
history (XLK to 1998), so unlike the broad cross-section this IS testable.

GATE: ship macro_max>0 only if cyclical median fwd-63d drawdown is deeper than
defensive in BOTH halves. If a tier's sign flips, set its beta to 0 and re-run.

Usage:  python -m scripts.research_macro_sector
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.conditions import macro_risk_series  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from engine.regime import classify  # noqa: E402
from engine.transition import compute_flags, state_machine  # noqa: E402
from lib import config, store  # noqa: E402

CYCLICAL = ["XLK", "XLY", "XLF", "XLC", "XLI", "XLB"]
DEFENSIVE = ["XLP", "XLU", "XLV"]
FWD = 63
HIGH_MRS = 0.50          # >= => "elevated+" macro risk
WEEKLY = 5               # decluster: sample every 5th bday
SPLIT = "2016-01-01"     # split-half boundary


def _regime_with_state(f: pd.DataFrame) -> pd.DataFrame:
    """Reproduce run.py's regime frame (quad + liquidity + transition_state)."""
    regime = classify(f)
    flags = compute_flags(f, regime)
    regime = regime.join(flags)
    regime["transition_state"] = state_machine(flags, regime)
    return regime


def _fwd_drawdown(close: pd.Series, h: int = FWD) -> pd.Series:
    """For each day, the worst (min) cumulative return over the NEXT h trading
    days — the forward max adverse excursion. NaN where the window is incomplete."""
    c = close.dropna()
    arr = c.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    fut = arr[1:]
    if len(fut) >= h:
        from numpy.lib.stride_tricks import sliding_window_view
        wins = sliding_window_view(fut, h)            # (len(fut)-h+1, h)
        mins = wins.min(axis=1)
        m = len(mins)
        out[:m] = mins / arr[:m] - 1.0
    return pd.Series(out, index=c.index)


def _stats(dd: pd.Series, mask: pd.Series) -> dict:
    v = dd[mask].dropna()
    if len(v) < 30:
        return {"n": int(len(v)), "med": None, "p10": None}
    return {"n": int(len(v)),
            "med": round(100 * float(v.median()), 2),
            "p10": round(100 * float(v.quantile(0.10)), 2)}


def _tier_dd(tiers: dict[str, list[str]], closes: dict[str, pd.Series],
             mrs: pd.Series, sampler: pd.Series, hi: pd.Series,
             period_mask: pd.Series) -> dict:
    """Median + p10 forward-63d drawdown per tier, on high-MRS sampled days in the
    given period (pooled across the tier's sectors)."""
    out = {}
    for tier, names in tiers.items():
        dds, masks = [], []
        for t in names:
            c = closes.get(t)
            if c is None:
                continue
            dd = _fwd_drawdown(c)
            idx = dd.index
            m = (sampler.reindex(idx, fill_value=False)
                 & hi.reindex(idx, fill_value=False)
                 & period_mask.reindex(idx, fill_value=False))
            dds.append(dd)
            masks.append(m)
        if not dds:
            out[tier] = {"n": 0, "med": None, "p10": None}
            continue
        dd_all = pd.concat(dds)
        m_all = pd.concat(masks)
        out[tier] = _stats(dd_all, m_all)
    return out


def main() -> int:
    print("=" * 84)
    print(f"MACRO-RISK SECTOR SIGN-CHECK  (fwd-{FWD}d drawdown · high-MRS≥{HIGH_MRS} "
          f"· weekly-declustered · split @ {SPLIT})")
    print("  GATE: cyclical median drawdown DEEPER than defensive, sign-stable across halves")
    print("=" * 84)

    f = build_features()
    regime = _regime_with_state(f)
    mrs = macro_risk_series(f, regime).dropna()
    if mrs.empty:
        print("!! MRS series empty — cannot validate. Keep overlay dark (macro_max=0).")
        return 1

    closes: dict[str, pd.Series] = {}
    for t in CYCLICAL + DEFENSIVE:
        df = store.read("yahoo", t)
        if df is not None and "close" in df:
            closes[t] = df["close"].dropna()
    have = sorted(closes)
    print(f"\nMRS span: {mrs.index.min().date()}..{mrs.index.max().date()}  "
          f"(n={len(mrs)}, ≥{HIGH_MRS} on {100*(mrs>=HIGH_MRS).mean():.1f}% of days)")
    print(f"SPDRs with history: {', '.join(have)}")

    # weekly sampler + high-MRS mask on the MRS index, broadcast by reindex later
    sampler = pd.Series(False, index=mrs.index)
    sampler.iloc[::WEEKLY] = True
    hi = (mrs >= HIGH_MRS)
    full = pd.Series(True, index=mrs.index)
    first = pd.Series(mrs.index < SPLIT, index=mrs.index)
    second = pd.Series(mrs.index >= SPLIT, index=mrs.index)

    tiers = {"CYCLICAL": CYCLICAL, "DEFENSIVE": DEFENSIVE}
    verdict_halves = []
    for tag, pmask in (("FULL", full), (f"H1 (<{SPLIT})", first),
                       (f"H2 (≥{SPLIT})", second)):
        res = _tier_dd(tiers, closes, mrs, sampler, hi, pmask)
        cyc, deff = res["CYCLICAL"], res["DEFENSIVE"]
        print(f"\n[{tag}]   high-MRS days")
        for name, r in (("cyclical", cyc), ("defensive", deff)):
            print(f"  {name:<10} n={r['n']:>5}  median dd={_fmt(r['med'])}  p10 dd={_fmt(r['p10'])}")
        ok = (cyc["med"] is not None and deff["med"] is not None
              and cyc["med"] < deff["med"])
        gap = (None if cyc["med"] is None or deff["med"] is None
               else round(cyc["med"] - deff["med"], 2))
        print(f"  -> cyclical deeper than defensive? {ok}   (gap={_fmt(gap)} pp; negative = correct sign)")
        if tag.startswith(("H1", "H2")):
            verdict_halves.append(ok)

    print("\n" + "=" * 84)
    if len(verdict_halves) == 2 and all(verdict_halves):
        print("VERDICT: PASS — sign is correct AND stable across both halves.")
        print("  => ship the conservative magnitude (engine.macro_overlay.macro_max/headwind).")
        rc = 0
    else:
        print("VERDICT: FAIL / WEAK — sign not stable across halves.")
        print("  => keep the overlay DARK (set macro_max=0 & macro_headwind=0) or zero the")
        print("     offending tier's beta; do NOT ship a live magnitude on this evidence.")
        rc = 2
    print("=" * 84)
    return rc


def _fmt(v) -> str:
    return "  n/a" if v is None else f"{v:+6.2f}"


if __name__ == "__main__":
    sys.exit(main())
