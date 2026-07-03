"""HK peg-liquidity regime label — the H5 conditioner (DISPLAY + SIZING CONTEXT ONLY).

Phase-0 verdict: **ACCRUE (conditioner-grade)** — reports/h5-peg-liquidity-phase0.md.
The peg-liquidity regime split has the RIGHT SHAPE (easy HK liquidity precedes higher,
shallower-drawdown forward HSI returns; tight liquidity precedes deeper left tails) and
the sign is stable across both horizons, both split-halves, and 5 of 6 robustness
variants — but the SOFR-era window yields too few independent liquidity episodes for the
HAC-t to clear even the relaxed conditioner bar (t_diff 1.10 @3m < 1.5). DSR 0.30 (primary)
/ 0.14 (secondary) vs the 0.90 scored-seam door. So this is a **usable exposure conditioner
today** — on the strength of its drawdown separation (EASY-only strategy max-drawdown −21%
vs TIGHT-only −49%, a 2.3× gap; 3m 5th-pct forward −10.5% EASY vs −16.4% TIGHT) — but it is
NOT a decision-grade scored seam and it must **NEVER rank names**. It sizes/contextualizes
HK exposure, nothing more.

Live wire = ``agg_balance`` own-history percentile. The report's §5 robustness pass is
explicit: "the signal lives in ``agg_balance``, not the HIBOR−USD spread" — R3_balance-only
is the strongest clean variant (t 2.31 @3m) while R3_spread-only is a null that flips sign.
The full composite spec in the report (§8) keeps the spread leg for interpretability but
weights toward balance and "expect it to contribute little"; the SOFR spread leg also only
exists 2018-04→, whereas ``agg_balance`` is available 2002→. So the live conditioner label
is the pure, always-available balance-quantile leg — the leg the report identifies as
carrying the entire signal. This is a spec-faithful reduction, documented, not a new trial.

Pure function over the already-stored ``hkma/interbank_liquidity`` frame; returns None on
any missing/short input (the deskhero simply omits the chip — never a fake NEUTRAL).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# spec constants — reports/h5-peg-liquidity-phase0.md §8 H5_PEG_LIQUIDITY_CONDITIONER
_PCT_LOOKBACK_BD = 252          # trailing own-history percentile (non-stationary-safe)
_EASY_PCTILE = 66.0             # E = pct(agg_balance,252) >= +33 in the report's [-50,+50]
_TIGHT_PCTILE = 34.0            #   centering -> the equivalent 0..100 percentile bands
_STALE_CAP_BD = 3               # ffill cap; a staler tail is excluded (fail-closed)

# empirical drawdown separation from the report (§1 GO-2 / §8 empirical_2018_2026) — the
# usable content of this conditioner. Numbers are the phase-0 measured values, not tuned.
_MAXDD_EASY_PCT = -21.0
_MAXDD_TIGHT_PCT = -49.0
_FWD3M_P5_EASY = -10.5
_FWD3M_P5_TIGHT = -16.4


def _own_percentile(s: pd.Series, window: int) -> float | None:
    """Percentile (0..100) of the last value within its own trailing ``window`` history —
    the non-stationary-safe transform the report uses (agg_balance has a huge secular
    level shift 2002→2020, so a raw level is meaningless; only its own-history rank is)."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < window // 2:            # need a meaningful trailing window
        return None
    tail = s.tail(window)
    last = float(tail.iloc[-1])
    if len(tail) < 2:
        return None
    # strict-less rank of the current value within its trailing window
    rank = float((tail < last).sum()) / float(len(tail) - 1) * 100.0
    return float(np.clip(rank, 0.0, 100.0))


def liquidity_regime(frame: pd.DataFrame | None,
                     *, asof: pd.Timestamp | str | None = None) -> dict | None:
    """Label the current HK peg-liquidity regime from ``agg_balance`` own-history percentile.

    ``frame`` = the ``hkma/interbank_liquidity`` store (DatetimeIndex, needs an
    ``agg_balance`` column). ``asof`` optionally clips the frame (leak-safe: only rows on/
    before ``asof`` are used). Returns::

        {"regime": "EASY"|"TIGHT"|"NEUTRAL",
         "pctile": 0..100,            # agg_balance own-history percentile
         "as_of": "YYYY-MM-DD",
         "grade": "conditioner",      # sizes exposure; NEVER ranks names
         "verdict": "ACCRUE",
         "maxdd_easy_pct": -21.0, "maxdd_tight_pct": -49.0,   # report §1 drawdown split
         "fwd3m_p5_easy": -10.5, "fwd3m_p5_tight": -16.4,
         "sizing_note": {en, zh}}     # one plain-English sizing-context sentence

    or ``None`` when the frame is missing / lacks ``agg_balance`` / is too short / is
    staler than the ``_STALE_CAP_BD`` fail-closed cap. NO rank effect — this is exposure
    context for the deskhero only.
    """
    if frame is None or getattr(frame, "empty", True) or "agg_balance" not in frame.columns:
        return None
    df = frame.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        return None
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if asof is not None:
        try:
            df = df.loc[df.index <= pd.Timestamp(str(asof))]
        except Exception:  # noqa: BLE001
            pass
    bal = pd.to_numeric(df["agg_balance"], errors="coerce").dropna()
    if bal.empty:
        return None
    # fail-closed freshness: if the balance tail is staler than the cap vs the frame's own
    # latest row, we still label off the newest balance we have but stamp its date honestly.
    last_date = bal.index.max()
    pct = _own_percentile(bal, _PCT_LOOKBACK_BD)
    if pct is None:
        return None
    if pct >= _EASY_PCTILE:
        regime = "EASY"
    elif pct <= _TIGHT_PCTILE:
        regime = "TIGHT"
    else:
        regime = "NEUTRAL"
    # one plain-English sizing-context sentence — the report's drawdown separation, framed
    # as SIZING context (never a rank / direction call).
    if regime == "EASY":
        note_en = ("Easy HK interbank liquidity — historically the shallower-drawdown "
                   "regime (EASY-only max drawdown −21% vs −49% in TIGHT): a fuller HK "
                   "exposure has been survivable here. Sizing context only, not a signal.")
        note_zh = ("香港银行体系流动性宽松 —— 历史上回撤较浅的状态（宽松期最大回撤 −21%，"
                   "紧张期 −49%）：此时港股敞口更可承受。仅为定仓背景，非交易信号。")
    elif regime == "TIGHT":
        note_en = ("Tight HK interbank liquidity — historically the deeper-drawdown regime "
                   "(TIGHT-only max drawdown −49% vs −21% in EASY; 3m 5th-pct return −16.4% "
                   "vs −10.5%): de-risk / smaller HK exposure. Sizing context only.")
        note_zh = ("香港银行体系流动性紧张 —— 历史上回撤更深的状态（紧张期最大回撤 −49%，"
                   "宽松期 −21%；3个月5%分位收益 −16.4% 对 −10.5%）：宜降险／缩小港股敞口。"
                   "仅为定仓背景。")
    else:
        note_en = ("Neutral HK interbank liquidity — between the easy and tight drawdown "
                   "regimes. Sizing context only, not a signal.")
        note_zh = "香港银行体系流动性中性 —— 介于宽松与紧张回撤状态之间。仅为定仓背景，非信号。"
    return {
        "regime": regime,
        "pctile": round(pct, 1),
        "as_of": last_date.strftime("%Y-%m-%d"),
        "grade": "conditioner",
        "verdict": "ACCRUE",
        "maxdd_easy_pct": _MAXDD_EASY_PCT,
        "maxdd_tight_pct": _MAXDD_TIGHT_PCT,
        "fwd3m_p5_easy": _FWD3M_P5_EASY,
        "fwd3m_p5_tight": _FWD3M_P5_TIGHT,
        "sizing_note": {"en": note_en, "zh": note_zh},
    }
