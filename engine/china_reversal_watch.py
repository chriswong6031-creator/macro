"""Washout-reversal WATCH detection for the China Prophet board.

Program of record: charting-app ``docs/PREREG_WASHOUT_REVERSAL.md`` §5.4. This lane is a
MEASUREMENT surface, not a buy list: names the raw Prophet gate blocks solely for
trend/regime reasons, where the pre-registered washout context (W1–W3) and the
hold-confirmed reversal trigger (E-B) are true. The shelf is labeled reversal-context
with its null expectation printed, and its rows log to the track store under
``board_definition = "cn_reversal_watch_v1"`` so forward grades accrue SEPARATELY from
the Prophet featured record — the two cohorts are never pooled (the existing ledger
emitter filters on board_definition, so this lane cannot pollute the headline grade).

Detection grammar (frozen in the prereg BEFORE the panel runs; do not tune here):
  W1  bear_block on the 3D grid: monthly-bear AND below-200dma AND 2W-not-bull
      (the exact state the classic lane cannot fire in);
  W2  washout depth: close ≤ −35% vs the trailing ~252-session high, OR monthly
      StochRSI-D<20 dwell ≥ 3 closed months;
  W3  oversold visit: 3D StochRSI-D dipped <20 within the last 8 3D bars;
  E-B reversal trigger with hold: the production CB fires on the 3D grid while W1–W3
      hold, and the NEXT 3D close is above the trigger close (confirmation priced).

Panel evidence at authoring time (charting-app ``docs/WASHOUT_REVERSAL_EVIDENCE.md``):
E-B passed all six pre-registered gates on both US half-panels (pooled washout-trade
expectancy +7.7%, 2022-entered +4.2%, n=758 trades); the CN panel is confirm-only and
recorded in the same evidence doc. Detection here runs on the macro repo's own
``canon.confluence_signals`` (the golden-vector oracle); the known, intentional
close-date/anchor drift vs the Terminal engine (``golden_gate``) applies to this lane
exactly as it does to every other macro board signal.
"""
from __future__ import annotations

import pandas as pd

from engine import canon

BOARD_DEFINITION = "cn_reversal_watch_v1"

# frozen constants (prereg §2) — mirrors signal_layer/washout_lab.py
DD_LOOKBACK_3D = 84      # ≈ trailing 252 sessions on the 3D grid
DD_MIN = -0.35
MO_DWELL_MIN = 3         # months of monthly StochRSI-D<20 (prior CLOSED months)
OS_WINDOW = 8            # 3D bars
FRESH_3D_BARS = 8        # shelf freshness: confirm within the last N 3D bars (~24 sessions)

# cheap daily prefilter so the nightly only pays the full 3D computation for names that
# could possibly qualify (slightly looser than the frozen W2 so it can never exclude a
# name the real gate would admit).
_PREFILTER_DD = -0.30


def _monthly_oversold_dwell(is_os: pd.Series) -> pd.Series:
    """Consecutive-month oversold run length (terminal confluence_v2 port, verbatim)."""
    vals, count = [], 0
    for flag in is_os.fillna(False):
        count = count + 1 if flag else 0
        vals.append(count)
    return pd.Series(vals, index=is_os.index)


def detect(daily_close: pd.Series) -> dict | None:
    """Return the ACTIVE washout-reversal watch state for one name, or None.

    Active = an E-B hold-confirmed washout reversal whose confirmation bar lies within
    the last ``FRESH_3D_BARS`` 3D bars and with no CS (distribution sell) after it.
    Never raises; any data problem degrades to None."""
    try:
        c = daily_close.dropna()
        if len(c) < 300:
            return None

        # ── cheap daily prefilter ──
        dd_daily = float(c.iloc[-1] / c.rolling(252, min_periods=60).max().iloc[-1] - 1)
        mo = c.resample("ME").last().dropna()
        if len(mo) < 8:
            return None
        _mk, md = canon.stoch_rsi_kd(mo)
        dwell_mo = _monthly_oversold_dwell(md < 20)
        # prior CLOSED month (the newest monthly row may be the live partial month)
        dwell_prior = int(dwell_mo.iloc[-2]) if len(dwell_mo) >= 2 else 0
        if dd_daily > _PREFILTER_DD and dwell_prior < MO_DWELL_MIN:
            return None

        # ── full 3D-grid detection (frozen grammar) ──
        sig = canon.confluence_signals(c)
        if sig.empty:
            return None
        rows = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        if len(rows) < 20:
            return None

        bblk = (~rows["mo_bull"] & ~rows["above200"] & ~rows["w2_bull"]).to_numpy(dtype=bool)
        close3 = rows["close"].astype(float)
        dd3 = (close3 / close3.rolling(DD_LOOKBACK_3D, min_periods=20).max() - 1).to_numpy()
        w2a = dd3 <= DD_MIN
        dwell3 = (_monthly_oversold_dwell(md < 20).shift(1)
                  .reindex(rows.index, method="ffill").fillna(0).to_numpy())
        w2b = dwell3 >= MO_DWELL_MIN
        w3 = (rows["d"].rolling(OS_WINDOW, min_periods=1).min() < 20).to_numpy()

        trig = rows["CB"].to_numpy(dtype=bool) & bblk & (w2a | w2b) & w3
        cl = close3.to_numpy()
        cs = rows["CS"].to_numpy(dtype=bool)
        n = len(rows)

        # newest hold-confirmed trigger inside the freshness window, not sold since
        for i in range(n - 2, -1, -1):
            if not trig[i]:
                continue
            confirm = i + 1
            if cl[confirm] <= cl[i]:
                continue                      # failed the hold — not an E-B event
            if n - 1 - confirm > FRESH_3D_BARS:
                break                         # older events are stale for a watch shelf
            if cs[confirm + 1:].any():
                break                         # a distribution sell already ended the episode
            return {
                "trigger_date": str(rows.index[i].date()),
                "confirm_date": str(rows.index[confirm].date()),
                "trigger_px": round(float(cl[i]), 4),
                "confirm_px": round(float(cl[confirm]), 4),
                "last_px": round(float(cl[-1]), 4),
                "dd_pct": round(float(dd3[i]) * 100, 1),
                "monthly_dwell": int(dwell3[i]),
                "bars_since_confirm": int(n - 1 - confirm),
                "drivers": (["deep_drawdown"] if w2a[i] else [])
                           + (["monthly_oversold_dwell"] if w2b[i] else []),
            }
        return None
    except Exception:  # noqa: BLE001 — a watch shelf must never break the build
        return None
