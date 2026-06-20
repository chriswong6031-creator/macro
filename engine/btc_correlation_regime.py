"""Bitcoin Vector — correlation-mode detector (DISPLAY chip, NON-NUMERIC).

The paper's Override #3 wants a macro-driven vs flow-driven mode read. The design
review DROPPED the dynamic re-weighter (a firewall leak + overfit backdoor on
~5 cycles) and kept ONLY a non-numeric lean chip: "+flow" / "+macro" / "mixed".
It re-weights nothing, gates nothing, and cannot move the composite index a point.

Data discipline (review fix): net-liquidity's DAILY diff is zero on ~80% of days
(WALCL is weekly, forward-filled), so its daily correlation measures the release
calendar, not a regime — it is EXCLUDED here. Net-liquidity stays a level/slope
SCORE input only (engine/btc_regime). The flow leg reads SECOND-MOMENT
(correlation) quantities, structurally separate from the first-moment etf_flow_z
that scores T5 — so ETF flows are never double-counted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CORR_WINDOW = 90
HYST = 0.10        # |flow − macro| must exceed this to leave "mixed" (kills boundary whipsaw)


def _roll_abs_corr(a: pd.Series, b: pd.Series, n: int = CORR_WINDOW) -> pd.Series:
    return a.rolling(n, min_periods=max(30, n // 2)).corr(b).abs()


def lean(df: pd.DataFrame) -> dict:
    """Return the non-numeric mode lean. The numbers are debug only; the UI shows
    the WORD. Pre-ETF (no flow data) → macro by construction."""
    try:
        if "close" not in df:
            return {"ok": False}
        ret = df["close"].pct_change()
        macro_parts = []
        if "real_yield" in df and not df["real_yield"].dropna().empty:
            macro_parts.append(_roll_abs_corr(ret, df["real_yield"].diff()))
        if "dxy" in df and not df["dxy"].dropna().empty:
            macro_parts.append(_roll_abs_corr(ret, df["dxy"].diff()))
        macro = (pd.concat(macro_parts, axis=1).mean(axis=1)
                 if macro_parts else pd.Series(np.nan, index=df.index))

        flow = pd.Series(np.nan, index=df.index)
        flow_src = next((c for c in ("etf_flow_sum", "etf_flow_z", "etf_flow_usd_mn")
                         if c in df.columns and not df[c].dropna().empty), None)
        if flow_src:
            flow = _roll_abs_corr(ret, df[flow_src].diff() if flow_src == "etf_flow_sum"
                                  else df[flow_src])

        m = float(macro.dropna().iloc[-1]) if macro.dropna().size else None
        f = float(flow.dropna().iloc[-1]) if flow.dropna().size else None

        if f is None and m is None:
            return {"ok": False}
        if f is None:                       # pre-ETF era
            mode, word, zh = "macro", "+macro", "宏观主导"
        else:
            mm = m or 0.0
            if f - mm > HYST:
                mode, word, zh = "flow", "+flow", "资金流主导"
            elif mm - f > HYST:
                mode, word, zh = "macro", "+macro", "宏观主导"
            else:
                mode, word, zh = "mixed", "mixed", "混合"
        return {
            "ok": True, "display_only": True, "non_numeric": True,
            "lean": mode, "chip": word, "chip_zh": zh,
            "_macro_strength": round(m, 3) if m is not None else None,   # debug only
            "_flow_strength": round(f, 3) if f is not None else None,    # debug only
            "note": ("Macro-driven vs flow-driven lean. Display chip only — it re-weights "
                     "nothing (the dynamic re-weighter was dropped as an overfit backdoor)."),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
