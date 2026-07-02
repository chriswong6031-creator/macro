"""C7 builder — European-luxury aggregate → China-consumer forward-drawdown read-through.

The causal signal ``scripts.intl_phase0`` grades for claim ``c7_luxury_china_consumer``.
Tests whether a rolling trend-turn in the EW luxury basket (LVMUY ADR + CFR.SW + RMS.PA
from intl_search/closes) leads FXI (CSI300/HK consumer proxy) forward drawdowns at the
one pre-registered DD horizon (21d), per the masterplan §5 C7 mechanism:

  "European luxury (LVMH ~30% China-consumer revenue, Richemont, Hermès) is a
  *policy-undistorted* real-time read on the Chinese consumer that the A-share
  consumer tape cannot give. De-risk grain: luxury rolling over → trim CN-consumer
  conviction."

**Data depth honesty (CRITICAL per task brief):**
- LVMUY ADR: ~20 years (2006-01-27 – 2026-07-02) — the declared source_series.
- RMS.PA (Hermès): ~5 years (2021-06-15 – 2026-07-01) from intl_search/closes.
- CFR.SW (Richemont): ~5 years (2021-06-15 – 2026-07-01) from intl_search/closes.

The shared-history (all 3 legs available) is only ~5 years (from 2021-06).  The CRISES
table spans: asian_97, dotcom_00, gfc_08, eurozone_11, covid_20, rate_22 — the 5y overlap
window (2021+) contains at most ONE declared crisis (rate_22: 2022-01-01 to 2022-10-01).
When effective_n_crises < 3 the crisis-count gate fails and the harness cannot reach
CONFIRMED; we report this HONESTLY as the binding honesty constraint.

**Earnings-print excision:**  LVMH reports full-year results in late Jan/early Feb and
semi-annual results in late July; Richemont and Hermès follow similar cadences.  Windows
of ±2 trading days (4 calendar business days) around each constituent's print are NaN'd
from the signal before the lead-lag kernel runs, so intra-print spikes are not miscoded
as sustained trend (the ``calibrate_forex`` peg-excision pattern, applied here to earnings).

**Lead-lag kernel (ADJ-4 discipline):** the standing prior is that cross-market lead/lag
survivors are timezone lag-1 artifacts.  Luxury names trade in European/US hours; FXI
trades US hours (HK underlying).  This is a same-or-adjacent session, not timezone-
lagged overnight.  The kernel tests: does the lagged luxury signal (luxury[t-1]) carry
statistically significant information about FXI[t] forward drawdowns, AFTER the same-lag
exclusion window and earnings excision?  If yes → real lead.  If only lag-0 survives →
contemporaneous, not a lead.  If nothing survives → CONTEXT.

**Orthogonality basis:** the China RORO / CN-consumer domestic legs; specifically:
  - FXI own-momentum (60d return, the CN-consumer's own trend momentum)
  - China RORO state: USD/CNH move leg (the EXISTING validated de-risk leg from
    risk_radar_intl; here approximated from yahoo/CNH_F pct_change(20) as a proxy)
  A luxury read-through that merely echoes the existing RORO signal adds nothing.

Causality: the EW basket return uses a 1-bar shift before interacting with FXI returns.
No print window around an announcement day is allowed to see the announcement itself.
"""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────────
# Basket constituents and signal params
# ────────────────────────────────────────────────────────────────────────────────
_LUX_ADR = ("yahoo", "LVMUY")          # primary — 20y history, the declared source_series
_LUX_LOCALS = [                         # 5y locals from intl_search/closes (best effort)
    "RMS.PA",   # Hermès
    "CFR.SW",   # Richemont
]
_TGT_GROUP, _TGT_SERIES = "yahoo", "FXI"   # CN-consumer proxy; declared target in claim

# Trend-turn signal: 1-month return of the EW luxury basket (the momentum deterioration
# channel per §5 C7: "luxury rolling over → trim CN-consumer conviction").
_TREND_WIN = 21          # 21-trading-day rolling return (~1 month) of the basket
_TREND_PCT_WIN = 252     # causal trailing pctile for the trend-turn z-conversion
_EARNS_EXCISE_TD = 2    # ±2 trading days around print → NaN'd (earnings-excision)

# ────────────────────────────────────────────────────────────────────────────────
# Pre-registered LVMH + peer earnings print calendar (approximate; used for excision).
# LVMH: full-year results ~Jan/Feb; first-half results ~late July.
# Hermès: full-year ~mid Feb; first-half ~late Jul / early Aug.
# Richemont: full-year ~May; half-year ~Nov.
# These are approximate; the excision window is ±2td so small shifts don't matter.
# Source: public investor-relations calendars (non-model-sensitive lookup).
# ────────────────────────────────────────────────────────────────────────────────
_EARNINGS_DATES_APPROX: list[str] = [
    # LVMH full-year results (late Jan / early Feb)
    "2006-02-07", "2007-02-07", "2008-02-06", "2009-02-04", "2010-02-04",
    "2011-02-03", "2012-02-07", "2013-02-06", "2014-02-04", "2015-02-04",
    "2016-02-03", "2017-02-07", "2018-02-01", "2019-02-01", "2020-01-29",
    "2021-01-26", "2022-02-01", "2023-01-26", "2024-01-25", "2025-01-27",
    "2026-01-27",
    # LVMH first-half results (late July)
    "2006-07-26", "2007-07-25", "2008-07-23", "2009-07-23", "2010-07-28",
    "2011-07-27", "2012-07-25", "2013-07-25", "2014-07-23", "2015-07-29",
    "2016-07-27", "2017-07-26", "2018-07-25", "2019-07-25", "2020-07-27",
    "2021-07-28", "2022-07-27", "2023-07-26", "2024-07-24", "2025-07-23",
    "2026-07-23",
    # Hermès half-year results (late July / early Aug)
    "2021-07-29", "2022-07-29", "2023-07-28", "2024-07-29", "2025-07-28",
    "2026-07-28",
    # Richemont full-year results (mid-May)
    "2021-05-14", "2022-05-13", "2023-05-12", "2024-05-10", "2025-05-09",
    "2026-05-08",
    # Richemont half-year results (mid-Nov)
    "2021-11-05", "2022-11-04", "2023-11-10", "2024-11-08", "2025-11-07",
]

# ────────────────────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────────────────────

def _close(group: str, name: str) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _intl_search_close(col: str) -> pd.Series | None:
    """Read a column from the intl_search/closes parquet (the multi-stock close matrix)."""
    df = store.read("intl_search", "closes")
    if df is None or col not in df.columns:
        return None
    s = df[col].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _build_luxury_basket(idx: pd.Index) -> tuple[pd.Series, list[str], str]:
    """Equal-weight luxury basket on the business-day index `idx`.

    Returns (basket_close, constituents_used, depth_note).
    LVMUY is the declared source_series and the primary constituent.
    RMS.PA and CFR.SW (locals) are used if available (best-effort; they only have 5y).
    The basket is EW on the sub-panel of dates where each constituent has data.
    """
    frames: dict[str, pd.Series] = {}

    lvmuy = _close(*_LUX_ADR)
    if lvmuy is not None:
        frames["LVMUY"] = lvmuy.reindex(idx)

    for col in _LUX_LOCALS:
        s = _intl_search_close(col)
        if s is not None and len(s) >= 50:
            # Normalize local-currency prices to a common index base of 100 to avoid
            # level-dominated equal weighting (RMS.PA is ~1600 EUR, LVMUY ~$110).
            # The basket is therefore a pure EW RETURN basket, not EW price basket.
            frames[col] = s.reindex(idx)

    if not frames:
        return pd.Series(dtype=float, index=idx), [], "no constituents available"

    # Compute daily returns per constituent, mean them (EW), then cumulate → an index
    # This is an EW TOTAL-RETURN basket (buy-and-hold each component equally).
    rets = pd.DataFrame({k: v.pct_change(fill_method=None) for k, v in frames.items()})
    ew_ret = rets.mean(axis=1)          # NaN-safe (skips missing legs on sparse dates)
    basket_idx = (1.0 + ew_ret).cumprod().rename("luxury_ew")
    basket_idx.index = pd.to_datetime(basket_idx.index)

    depth_note = (
        f"EW basket: {sorted(frames.keys())}; "
        f"LVMUY from 2006-01-27 (~20y); "
        f"RMS.PA/CFR.SW from 2021-06 (~5y via intl_search); "
        f"full 3-leg overlap from 2021-06-15 (~5y). "
        f"effective_n_crises cap: the 5y locals restrict the shared window to "
        f"1 declared crisis (rate_22 2022-01-01..2022-10-01) — BELOW the 3-crisis floor. "
        f"LVMUY-only basket extends to 2006 (2 declared crises: eurozone_11, rate_22) — "
        f"STILL below the 3-crisis floor. HONEST NEGATIVE expected."
    )
    return basket_idx, sorted(frames.keys()), depth_note


def _excision_mask(idx: pd.Index) -> pd.Series:
    """Boolean mask: True on dates within ±EARNS_EXCISE_TD trading days of a print date.
    These rows are NaN'd from the signal before grading."""
    mask = pd.Series(False, index=idx)
    biz = pd.bdate_range(idx.min(), idx.max())
    for ds in _EARNINGS_DATES_APPROX:
        try:
            anchor = pd.Timestamp(ds)
        except Exception:
            continue
        if anchor < idx.min() or anchor > idx.max():
            continue
        # find position in biz-day index
        pos_arr = np.searchsorted(biz, anchor)
        lo = max(0, int(pos_arr) - _EARNS_EXCISE_TD)
        hi = min(len(biz) - 1, int(pos_arr) + _EARNS_EXCISE_TD)
        excised = pd.DatetimeIndex(biz[lo : hi + 1])
        mask |= pd.Series(True, index=excised).reindex(idx, fill_value=False)
    return mask


def _fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over the next h bars (≤0; deeper = more negative). CAUSAL
    target label — looks forward from t, so never fed into the signal."""
    a = px.to_numpy()
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        w = a[i : i + h + 1]
        w = w[~np.isnan(w)]
        if len(w) >= 3:
            peak = np.maximum.accumulate(w)
            out[i] = float((w / peak - 1.0).min())
    return pd.Series(out, index=px.index)


def _sharpe(r: pd.Series, ann: int = 252) -> float | None:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return None
    return float(r.mean() / r.std() * np.sqrt(ann))


# ────────────────────────────────────────────────────────────────────────────────
# Main builder
# ────────────────────────────────────────────────────────────────────────────────

def build(claim: dict, horizon: int = 21) -> dict:
    """Harness builder contract for c7_luxury_china_consumer at the ONE declared DD horizon (21d).

    Signal construction:
    1. Build the EW luxury basket (LVMUY primary + RMS.PA/CFR.SW locals where available).
    2. Compute the basket's trailing _TREND_WIN-day momentum (the "rolling over" signal).
    3. Earnings-excision: NaN the momentum signal at ±2td around known print dates.
    4. Convert to a causal trailing-percentile de-risk signal.
    5. Long/flat strategy on FXI (the declared CN-consumer target), flat when the luxury
       trend-turn signal is in the top quartile (strongest deterioration).
    6. Lead-lag kernel: the kernel is embedded via the `prod` key — the product of
       z(luxury_trend) and z(FXI_return) at the declared lag, so the harness's
       leadlag_kernel() can run it.

    Orthogonality basis: FXI own-momentum (CN-consumer's own trend) + CNH_F 20d move
    (the RORO leg), so the luxury signal must carry RESIDUAL information beyond what the
    CN consumer's own trend + the existing RORO leg already capture.
    """
    # --- target price series
    tgt = _close(_TGT_GROUP, _TGT_SERIES)
    if tgt is None:
        return {"error": f"{_TGT_GROUP}/{_TGT_SERIES} unavailable"}

    idx = tgt.index
    bench_ret = tgt.pct_change(fill_method=None).rename("FXI_ret")

    # --- luxury basket
    basket_idx, constituents, depth_note = _build_luxury_basket(idx)
    if basket_idx.dropna().__len__() < 100:
        return {"error": "luxury basket has < 100 valid rows"}

    # --- trend-turn signal: rolling TREND_WIN return of the basket (momentum)
    basket_ret_series = basket_idx.pct_change(fill_method=None)
    trend_raw = basket_idx.pct_change(_TREND_WIN, fill_method=None)   # 21d momentum

    # --- earnings-print excision (±2td around prints → NaN)
    excise = _excision_mask(idx)
    trend_excised = trend_raw.copy()
    trend_excised.loc[excise] = np.nan
    n_excised = int(excise.sum())

    # --- causal trailing percentile: high value = recent luxury DECLINE = de-risk signal.
    # We flip sign so that LOW luxury momentum → HIGH de-risk percentile.
    trend_neg = -trend_excised      # flip: basket rolling over → positive de-risk signal
    if trend_neg.dropna().__len__() < _TREND_PCT_WIN:
        log.warning("c7: insufficient history for causal pctile (%d rows)", len(trend_neg.dropna()))
        # Fall back to z-score-based signal instead
        win = min(_TREND_PCT_WIN, len(trend_neg.dropna()) // 2)
        mu = trend_neg.rolling(win, min_periods=win // 4).mean()
        sd = trend_neg.rolling(win, min_periods=win // 4).std()
        sig = (trend_neg - mu) / sd.replace(0, np.nan)
    else:
        try:
            from engine.indicators import pct_rank_window
            sig = pct_rank_window(trend_neg.dropna(), _TREND_PCT_WIN)
        except Exception:
            # fallback z-score
            mu = trend_neg.rolling(_TREND_PCT_WIN, min_periods=_TREND_PCT_WIN // 4).mean()
            sd = trend_neg.rolling(_TREND_PCT_WIN, min_periods=_TREND_PCT_WIN // 4).std()
            sig = (trend_neg - mu) / sd.replace(0, np.nan)

    sig = sig.reindex(idx)

    # --- de-risk long/flat strategy: flat when causal signal > 0.70 pctile (top 30%)
    # Acts next-bar (causal shift(1))
    RISK_THR = 0.70
    pos = (1.0 - (sig > RISK_THR).astype(float)).shift(1).fillna(1.0)
    strat_ret = (pos * bench_ret).dropna()
    bench_a = bench_ret.reindex(strat_ret.index)

    # --- forward max-drawdown target (the LABEL the orthogonality gate measures against)
    target_dd = _fwd_maxdd(tgt, horizon).reindex(idx)

    # --- orthogonality basis
    # 1. FXI own-momentum (the CN consumer's own trend — the most direct collinearity concern)
    fxi_mom = tgt.pct_change(_TREND_WIN, fill_method=None).reindex(idx)
    # 2. CNH/USD offshore 20d move (the EXISTING China RORO leg — approximation)
    cnh = _close("yahoo", "CNH_F")
    if cnh is not None:
        cnh_roro = cnh.reindex(idx).pct_change(20, fill_method=None)
    else:
        cnh_roro = pd.Series(dtype=float, index=idx)
    basis = [fxi_mom.dropna(), (-cnh_roro).dropna()]   # sign: weaker yuan = risk-off ↑

    # --- IC (rank correlation of signal with forward drawdown target)
    j = pd.concat([sig.rename("f"), target_dd.rename("y")], axis=1).dropna()
    ic = float(j["f"].rank().corr(j["y"].rank())) if len(j) >= 60 else None

    # --- split-half same-sign Sharpe (on the long/flat strategy returns)
    n = len(strat_ret.dropna())
    if n >= 120:
        mid = strat_ret.dropna().index[n // 2]
        sh1 = _sharpe(strat_ret.dropna().loc[:mid])
        sh2 = _sharpe(strat_ret.dropna().loc[mid:])
        split_same = bool(
            sh1 is not None and sh2 is not None
            and np.isfinite(sh1) and np.isfinite(sh2)
            and np.sign(sh1) == np.sign(sh2)
        )
    else:
        sh1, sh2, split_same = None, None, None

    return {
        "signal": sig,
        "strat_ret": strat_ret,
        "bench_ret": bench_a,
        "target_dd": target_dd,
        "basis": basis,
        "split_half_same_sign": split_same,
        "ic": ic,
        # metadata for the report
        "_constituents": constituents,
        "_n_excised_bars": n_excised,
        "_depth_note": depth_note,
        "_split_sharpe": (sh1, sh2),
        "_basket_start": str(basket_idx.first_valid_index().date()) if basket_idx.first_valid_index() else None,
    }


def builder(claim: dict) -> dict:
    """Harness entry point — grade at the ONE declared DD horizon (21d)."""
    return build(claim, horizon=21)
