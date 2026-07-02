"""C6 builder — Asia-semi aggregate read-through vs SMH, through the lead-lag kernel (W4).

The causal signal the ``scripts/intl_phase0`` harness grades for claim
``c6_asia_semi_readthrough``. ONE pre-registered equal-weight Asia-semi sensor basket
(masterplan §5 C6, ADJ-4 declared-grid discipline — no name grids): the daily
equal-weight return of the two US-listed Asia-semi ADR sensors the C6 claim declares,
**TSM + ASML** (the declared ``source_series``). ADRs, not local Samsung/SK-Hynix/
Tokyo-Electron listings, are used ON PURPOSE (§4.4): US-session timing kills the lag-1
timezone ambiguity that made the raw cross-asset lead/lag screen a transmission read.

The standing prior (ADJ-4, ``reports/cross-asset-leadlag-phase0.md``): naive lead/lag
survivors are timezone lag-1 artifacts. Here the ADRs trade in the US session
CONTEMPORANEOUSLY with SMH, and TSM/ASML are two of SMH's largest holdings, so the
expected structure is a large LAG-0 co-membership correlation (mechanical, not a lead)
and no orthogonal lag-1+ read-through. If ONLY lag-1 survives the kernel, the honest
conclusion is 'overnight transmission read' (still ledger-worthy as CONTEXT, honestly
labelled); if nothing beyond the mechanical lag-0 survives, it is CONTEXT — no lead.

EARNINGS-PRINT EXCISION (the calibrate_forex peg-excision pattern): the read-through
must not be a print-day spike miscoded as a lead (INTL-49). We excise a ±2 trading-day
window around every constituent's quarterly print from the forward target and the kernel
product series. Causal source: yfinance ``get_earnings_dates`` realized prints (2000+),
cached committed to ``data/intl_bridge/c6_earnings_dates.json``; the sparse pre-2000 tail
(ASML from 1995, TSM from 1997) is approximated at the stable Jan/Apr/Jul/Oct quarterly
cadence the realized history shows (documented in the cache + the C6 report).

Returns the harness builder contract PLUS a ``prod_by_lag`` dict {lag → z_SMH(t)·z_basket(t−k)}
so the harness runs the LEAD-LAG KERNEL (gate d — HAC-t + BH-FDR + split-half same-sign),
the gate ADJ-4 demands for any cross-market claim, alongside the standard de-risk battery
(orthogonality vs SMH's OWN momentum — the read-through must add beyond 'semis lead semis';
crisis-count; ES). Wire NOTHING regardless of verdict (W4 is context-tier); the would-be
seam if it ever clears is ``stock_score._axis_tailwind`` DOWNGRADE-only.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# The declared C6 basket constituents (engine.intl_claims c6 source_series). EW = the
# mean of the two ADRs' daily returns; BOTH must be present on a date (no single-name
# extrapolation) so the basket is a genuine two-sensor aggregate, never one name in a
# gap. ADJ-4: exactly the declared grid — no Samsung/SK-Hynix/Tokyo-Electron locals.
_CONSTITUENTS = ("TSM", "ASML")
_FOLLOWER = "SMH"                 # the declared target (semis ETF the basket reads through to)
_PRINT_EXCISE_TD = 2             # ±2 trading days around each quarterly print (INTL-49)
_LAGS = (1, 2, 3, 5)             # the standing-prior lag grid (lag-0 is the co-membership baseline)
_EARN_CACHE = ("intl_bridge", "c6_earnings_dates.json")


# --------------------------------------------------------------------------- #
# price / return helpers (causal, dedup, sorted)
# --------------------------------------------------------------------------- #
def _ret(ticker: str) -> pd.Series | None:
    df = store.read("yahoo", ticker)
    if df is None or "close" not in df.columns:
        return None
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    return s.pct_change()


def asia_semi_basket() -> pd.Series | None:
    """The ONE pre-registered EW Asia-semi basket return: mean of TSM + ASML daily
    returns, requiring BOTH present (no single-name gap-fill). Causal (returns only)."""
    parts = [_ret(t) for t in _CONSTITUENTS]
    if any(p is None for p in parts):
        return None
    panel = pd.concat(parts, axis=1, sort=True)
    # require ALL constituents present on a date → a true two-sensor aggregate
    return panel.mean(axis=1, skipna=False).dropna()


def _smh_ret() -> pd.Series | None:
    return _ret(_FOLLOWER)


# --------------------------------------------------------------------------- #
# earnings-print excision (calibrate_forex peg-excision pattern, INTL-49)
# --------------------------------------------------------------------------- #
def _print_dates() -> list[pd.Timestamp]:
    """All constituent quarterly print dates (realized yfinance + pre-2000 approx),
    read from the committed cache. No network call at grade time → reproducible."""
    p = config.data_dir().joinpath(*_EARN_CACHE)
    if not p.exists():
        return []
    try:
        blob = json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — a missing/broken cache means no excision, not a crash
        return []
    dates: set[pd.Timestamp] = set()
    for t in _CONSTITUENTS:
        rec = (blob.get("tickers") or {}).get(t) or {}
        for d in rec.get("realized_from_yfinance", []):
            dates.add(pd.Timestamp(d))
        for d in rec.get("pre2000_quarterly_approx", []):
            dates.add(pd.Timestamp(d))
    return sorted(dates)


def excise_mask(idx: pd.DatetimeIndex, span_td: int = _PRINT_EXCISE_TD) -> pd.Series:
    """True where a row MAY be used; False within ±``span_td`` TRADING days of any
    constituent print (the read-through must not be a print-day spike, INTL-49).

    Trading-day windows: each print is mapped to the nearest on-panel trading day, then
    the ±span_td index positions around it are excised — so the window is span in ACTUAL
    trading days regardless of weekends/holidays, matching the calibrate_forex intent
    (excise the managed/print zone, keep everything else)."""
    idx = pd.DatetimeIndex(idx)
    mask = pd.Series(True, index=idx)
    if len(idx) == 0:
        return mask
    prints = _print_dates()
    pos_of = {ts: i for i, ts in enumerate(idx)}
    for pd_ts in prints:
        # nearest trading day at or after the print (searchsorted); print on a weekend
        # maps to the next session — the first day the market can react to it.
        j = int(idx.searchsorted(pd_ts))
        for cand in (j, j - 1):                       # the print day itself or the prior session
            if 0 <= cand < len(idx):
                lo = max(0, cand - span_td)
                hi = min(len(idx) - 1, cand + span_td)
                mask.iloc[lo:hi + 1] = False
                break
    return mask


# --------------------------------------------------------------------------- #
# the lead-lag kernel product series (cross-asset-leadlag-phase0 convention)
# --------------------------------------------------------------------------- #
def _z(s: pd.Series) -> pd.Series:
    sd = float(s.std())
    if not sd or not np.isfinite(sd) or sd <= 0:
        return s * np.nan
    return (s - s.mean()) / sd


def prod_by_lag(basket: pd.Series, smh: pd.Series, mask: pd.Series | None = None,
                lags=_LAGS) -> dict[str, pd.Series]:
    """{lag → prod_t} where prod_t = z_SMH(t)·z_basket(t−k) — does the basket's PAST move
    predict SMH's present? (cross-asset-leadlag-phase0 kernel). Print-excised if a mask is
    given (the excised rows drop out of every lag's product, so a print-day spike cannot
    manufacture a lead). Also emits lag 0 (the mechanical co-membership baseline) under key
    'lag0' so the report can show it is contemporaneous co-membership, not a lead."""
    common = basket.dropna().index.intersection(smh.dropna().index)
    b, s = basket.reindex(common), smh.reindex(common)
    zb, zs = _z(b), _z(s)
    out: dict[str, pd.Series] = {}
    for k in (0, *lags):
        prod = (zs * zb.shift(k)).dropna()
        if mask is not None:
            prod = prod[mask.reindex(prod.index).fillna(False)]
        key = "lag0" if k == 0 else f"lag{k}"
        out[key] = prod
    return out


# --------------------------------------------------------------------------- #
# forward target + de-risk strategy (for the standard battery)
# --------------------------------------------------------------------------- #
def _smh_close() -> pd.Series | None:
    df = store.read("yahoo", _FOLLOWER)
    if df is None or "close" not in df.columns:
        return None
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def _forward_maxdd(px: pd.Series, h: int) -> pd.Series:
    vals = px.to_numpy()
    out = np.full(len(px), np.nan)
    for i in range(len(px)):
        w = vals[i:i + h + 1]
        if len(w) < 3:
            continue
        peak = np.maximum.accumulate(w)
        out[i] = float((w / peak - 1.0).min())
    return pd.Series(out, index=px.index)


def _smh_momentum_basis(idx: pd.DatetimeIndex) -> list[pd.Series]:
    """The orthogonality basis for a read-through claim is SMH's OWN momentum — the
    read-through must add something BEYOND 'semis lead semis'. Trailing 5d and 21d SMH
    returns (causal), so partialing them out isolates the basket's incremental content."""
    px = _smh_close()
    if px is None:
        return []
    out = []
    for n in (5, 21):
        out.append(px.pct_change(n).reindex(idx))
    return out


def build(claim: dict) -> dict:
    """Harness builder contract for c6_asia_semi_readthrough at the ONE declared horizon.

    Signal graded for orthogonality: the basket's trailing return z (its de-risk tell),
    vs SMH forward drawdown, partialed against SMH's OWN momentum. Strategy: SMH long/flat,
    flat while the basket is rolling over (a de-risk read-through), causal next-bar,
    print-excised. Plus ``prod_by_lag`` for the lead-lag kernel (gate d). Everything causal;
    print windows excised (INTL-49)."""
    basket = asia_semi_basket()
    smh_r = _smh_ret()
    px = _smh_close()
    if basket is None or smh_r is None or px is None:
        return {"error": "C6 sensor data unavailable (need yahoo/TSM, yahoo/ASML, yahoo/SMH)"}

    common = basket.dropna().index.intersection(smh_r.dropna().index)
    if len(common) < 400:
        return {"error": f"C6 basket∩SMH only {len(common)} rows"}
    mask = excise_mask(common)

    # the lead-lag kernel products (excised), incl. the lag-0 co-membership baseline
    prods = prod_by_lag(basket.reindex(common), smh_r.reindex(common), mask=mask)

    # --- the de-risk strategy leg for the standard battery ------------------
    # basket "rolling over" = its trailing 21d return in the bottom causal tercile → the
    # read-through de-risk tell. Long SMH otherwise; flat next-bar while rolling over.
    from engine.validation import backtest_core, _sharpe
    basket_lvl = (1.0 + basket.reindex(common).fillna(0)).cumprod()
    mom21 = basket_lvl.pct_change(21)
    roll_pctile = mom21.rolling(504, min_periods=252).apply(
        lambda w: float((w[-1] > w[:-1]).mean()) if len(w) > 1 else np.nan, raw=True)
    de_risk = (roll_pctile < 0.30)                          # bottom-30% momentum = de-risk
    # print-excise the POSITION signal too: no acting on a print-window row
    de_risk = de_risk & mask.reindex(de_risk.index).fillna(True)
    alloc = (1.0 - de_risk.astype(float)).shift(1).fillna(1.0).reindex(common).fillna(1.0)
    pxc = px.reindex(common).dropna()
    alloc = alloc.reindex(pxc.index).fillna(1.0)
    strat = backtest_core(pxc, alloc, cost_bps=3.0, cash_yield=None)["net"].reindex(pxc.index)
    bench = pxc.pct_change().reindex(pxc.index)

    h = int(claim.get("horizons", (5,))[0])
    target_dd = _forward_maxdd(pxc, h).reindex(pxc.index)
    # excise print windows from the forward target so a print-day spike is not scored
    target_dd = target_dd.where(mask.reindex(target_dd.index).fillna(True))

    # orthogonality signal: the basket's trailing 21d return (its de-risk tell), and the
    # basis is SMH's OWN 5d/21d momentum (semis-lead-semis) — the read-through must survive.
    sig = mom21.reindex(common)
    basis = _smh_momentum_basis(common)

    r = strat.dropna()
    n = len(r)
    s1 = _sharpe(r.iloc[:n // 2].to_numpy(), 252) if n >= 240 else float("nan")
    s2 = _sharpe(r.iloc[n // 2:].to_numpy(), 252) if n >= 240 else float("nan")
    split_same = bool(np.isfinite(s1) and np.isfinite(s2) and np.sign(s1) == np.sign(s2))

    def _sp(a, b):
        j = pd.concat([pd.Series(a).rename("a"), pd.Series(b).rename("b")], axis=1).dropna()
        return float(j["a"].rank().corr(j["b"].rank())) if len(j) >= 30 else None

    split_date = str(common[len(common) // 2].date())
    return {
        "signal": sig, "strat_ret": strat, "bench_ret": bench, "target_dd": target_dd,
        "basis": basis, "split_half_same_sign": split_same, "ic": _sp(sig, target_dd),
        "prod_by_lag": prods, "leadlag_split": split_date,
        "_n_common": int(len(common)), "_n_excised": int((~mask).sum()),
        "_lag_corrs": {k: (round(float(v.mean()), 4) if len(v) else None)
                       for k, v in prods.items()},
    }


def builder(claim: dict) -> dict:
    """Harness entry point for c6_asia_semi_readthrough (the declared 5d horizon)."""
    return build(claim)
