"""Shared helpers for Amendment-3 runners (run_a3_htf.py, run_a3_struct.py).

These utilities are duplicated in neither runner; both import from here.

Exported helpers
----------------
bear_ctx_series(idx_close)          -> pd.Series[bool/NaN], daily-indexed
compute_rv63_at_fires(fires, closes) -> pd.Series[float], fire-indexed
assign_rv63_tercile(rv63_fire)       -> pd.Series[float 0/1/2/NaN], fire-indexed
materialize_at_fires(fires, daily_series_map) -> pd.DataFrame, fire-indexed
era_sign_stability(graded_ok, stratum_col, outcome) -> dict
ticker_half_sign_agreement(graded_ok, stratum_col, outcome) -> dict
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ── Bear-context constants — wave6.py F8 frozen definition verbatim ──────────
_F8_BEAR_WIN  = 126
_F8_BEAR_FRAC = 0.70

# ── RV63 tercile trailing window (trailing-year cross-section at each fire) ───
_RV63_TRAILING_BARS = 252


def bear_ctx_series(idx_close: pd.Series) -> pd.Series:
    """Index-level bear-context flag — wave6.py F8 frozen definition.

    F8: index close below its 200MA on >=70% of trailing 126 index days,
    as-of each bar (leak-free).  Math replicates wave6.py lines 919-921 verbatim
    for the go/no-go branch.

    NOTE on missing-data branch: wave6.py sets f8_bear_ctx=False when the index
    series is absent or short; this implementation returns NaN instead, which is
    a deliberate, more-honest policy consistent with RUL-31's no-fillna(False)
    mandate.  The divergence is intentional — NaN excludes the fire from
    bear_ctx-stratified reads rather than mislabelling it as 'not bear'.

    Returns
    -------
    pd.Series[float] 0.0/1.0/NaN on idx_close.index.
    NaN until 200 MA has converged (first 200 bars).
    """
    if len(idx_close) < 201:
        return pd.Series(np.nan, index=idx_close.index, dtype=float)

    im = idx_close.rolling(200).mean()
    below = (idx_close < im)
    bearfrac = below.rolling(_F8_BEAR_WIN, min_periods=int(_F8_BEAR_WIN * 0.6)).mean()
    bctx = bearfrac >= _F8_BEAR_FRAC
    return pd.Series(
        np.where(bearfrac.isna(), np.nan, bctx.astype(float)),
        index=idx_close.index,
        dtype=float,
    )


def load_spy_close(repo_root: Any) -> pd.Series | None:
    """Load the deep-panel SPY close (or nearest proxy) for bear_ctx computation.

    Tries data/stocks/SPY.parquet, then data/stocks/QQQ.parquet, then the
    first file in data/stocks/ with >=1000 bars as a last resort.
    Returns None if no suitable series is found.
    """
    from pathlib import Path

    stocks = Path(repo_root) / "data" / "stocks"
    for ticker in ("SPY", "QQQ", "IVV", "VTI"):
        p = stocks / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if "close" in df.columns:
                    s = df["close"].dropna().sort_index()
                    if len(s) >= 600:
                        return s
            except Exception:
                continue
    # fallback: first ticker with >=1000 bars
    for p in sorted(stocks.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
            if "close" in df.columns:
                s = df["close"].dropna().sort_index()
                if len(s) >= 1000:
                    return s
        except Exception:
            continue
    return None


def compute_rv63_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    trailing_bars: int = _RV63_TRAILING_BARS,
) -> pd.Series:
    """Realized volatility (63-bar) at each fire date, trailing cross-sectional.

    Per-ticker: compute the full realized_vol(close, 63) series once, then
    searchsorted to the fire date.  Uses trailing_bars to determine the
    lookback window for the cross-sectional tercile assignment (done in
    assign_rv63_tercile, not here).

    Returns fire-indexed pd.Series[float|NaN].
    """
    from engine.stock_technicals import realized_vol

    rv_cache: dict[str, pd.Series] = {}
    for ticker, close in closes.items():
        if len(close) < 65:
            continue
        try:
            rv_cache[ticker] = realized_vol(close, 63)
        except Exception:
            pass

    vals: list[float] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        rv = rv_cache.get(ticker)
        if rv is None:
            vals.append(float("nan"))
            continue
        loc = rv.index.searchsorted(sig_date, side="right") - 1
        if loc < 0:
            vals.append(float("nan"))
            continue
        v = float(rv.iloc[loc])
        vals.append(v if pd.notna(v) else float("nan"))

    return pd.Series(vals, index=fires.index, name="rv63_at_fire", dtype=float)


def assign_rv63_tercile(
    rv63_fire: pd.Series,
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    trailing_bars: int = _RV63_TRAILING_BARS,
) -> pd.Series:
    """Trailing-year cross-sectional tercile of rv63 at each fire date.

    For each fire date d: take all rv63_at_fire values where the fire date is
    within the trailing trailing_bars window (i.e. fire_date in [d-trailing_bars, d]).
    Compute 33rd and 67th percentiles of those values, assign band 0/1/2.

    This matches the SLQ mechanics (trailing-year cross-section at each fire).
    NaN if <30 observations in the trailing window.

    Returns fire-indexed pd.Series[float 0/1/2/NaN].
    """
    fire_dates = pd.to_datetime(fires["date"]).values
    rv_vals = rv63_fire.values
    terciles = np.full(len(fires), np.nan)

    for i, (fire_date_ts, rv_val) in enumerate(zip(fire_dates, rv_vals)):
        if np.isnan(rv_val):
            continue
        fire_date = pd.Timestamp(fire_date_ts)
        # trailing window: all fires up to and including this fire date
        # using a calendar approximation: fire_date - trailing_bars trading days
        cutoff = fire_date - pd.Timedelta(days=int(trailing_bars * 1.5))
        mask = (fire_dates >= cutoff) & (fire_dates <= fire_date)
        window_vals = rv_vals[mask]
        window_vals = window_vals[~np.isnan(window_vals)]
        if len(window_vals) < 30:
            continue
        q33 = float(np.percentile(window_vals, 33.33))
        q67 = float(np.percentile(window_vals, 66.67))
        if rv_val <= q33:
            terciles[i] = 0.0
        elif rv_val <= q67:
            terciles[i] = 1.0
        else:
            terciles[i] = 2.0

    return pd.Series(terciles, index=fires.index, name="rv63_tercile", dtype=float)


def assign_age63_tercile(
    age63_fire: pd.Series,
    fires: pd.DataFrame,
    *,
    trailing_bars: int = _RV63_TRAILING_BARS,
) -> pd.Series:
    """Trailing-year cross-sectional tercile of age63 (bars since 63d close-min).

    Same mechanics as assign_rv63_tercile but for the pure-age covariate.
    Returns fire-indexed pd.Series[float 0/1/2/NaN].
    """
    fire_dates = pd.to_datetime(fires["date"]).values
    age_vals = age63_fire.values
    terciles = np.full(len(fires), np.nan)

    for i, (fire_date_ts, age_val) in enumerate(zip(fire_dates, age_vals)):
        if np.isnan(age_val):
            continue
        fire_date = pd.Timestamp(fire_date_ts)
        cutoff = fire_date - pd.Timedelta(days=int(trailing_bars * 1.5))
        mask = (fire_dates >= cutoff) & (fire_dates <= fire_date)
        window_vals = age_vals[mask]
        window_vals = window_vals[~np.isnan(window_vals)]
        if len(window_vals) < 30:
            continue
        q33 = float(np.percentile(window_vals, 33.33))
        q67 = float(np.percentile(window_vals, 66.67))
        if age_val <= q33:
            terciles[i] = 0.0
        elif age_val <= q67:
            terciles[i] = 1.0
        else:
            terciles[i] = 2.0

    return pd.Series(terciles, index=fires.index, name="age63_tercile", dtype=float)


def compute_age63_at_fires(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
) -> pd.Series:
    """Bars since the trailing 63-bar close minimum at each fire date.

    Pure-age covariate for family F (RUL-30): proves F is not H2 re-derived.
    At each fire: how many bars since close hit its 63-day low?

    Returns fire-indexed pd.Series[float|NaN].
    """
    vals: list[float] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        close = closes.get(ticker)
        if close is None or close.empty:
            vals.append(float("nan"))
            continue
        c = close.dropna().sort_index()
        loc = c.index.searchsorted(sig_date, side="right") - 1
        if loc < 63:
            vals.append(float("nan"))
            continue
        window = c.iloc[max(0, loc - 62): loc + 1]
        if len(window) < 20:
            vals.append(float("nan"))
            continue
        argmin = int(np.argmin(window.values))
        bars_since = len(window) - 1 - argmin
        vals.append(float(bars_since))

    return pd.Series(vals, index=fires.index, name="age63_at_fire", dtype=float)


def materialize_series_at_fires(
    fires: pd.DataFrame,
    ticker_series_map: dict[str, pd.Series],
    col_name: str,
) -> pd.Series:
    """Materialize a per-ticker daily Series at fire dates (asof lookup).

    For each fire row: searchsorted to find the last bar on or before the
    fire date in the ticker's series.  Returns a fire-indexed pd.Series.

    Parameters
    ----------
    fires:
        Fire DataFrame with 'ticker' and 'date' columns.
    ticker_series_map:
        {ticker: pd.Series} pre-computed daily series (any numeric type).
    col_name:
        Name for the returned Series.
    """
    vals: list[float] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        s = ticker_series_map.get(ticker)
        if s is None or s.empty:
            vals.append(float("nan"))
            continue
        loc = s.index.searchsorted(sig_date, side="right") - 1
        if loc < 0:
            vals.append(float("nan"))
            continue
        v = float(s.iloc[loc])
        vals.append(v if pd.notna(v) else float("nan"))

    return pd.Series(vals, index=fires.index, name=col_name, dtype=float)


def materialize_df_col_at_fires(
    fires: pd.DataFrame,
    ticker_df_map: dict[str, pd.DataFrame],
    col_name: str,
) -> pd.Series:
    """Materialize one column of a per-ticker daily DataFrame at fire dates."""
    series_map = {
        ticker: df[col_name]
        for ticker, df in ticker_df_map.items()
        if col_name in df.columns
    }
    return materialize_series_at_fires(fires, series_map, col_name)


def assign_trailing_tercile(
    fire_vals: pd.Series,
    fires: pd.DataFrame,
    col_name: str,
    *,
    trailing_bars: int = _RV63_TRAILING_BARS,
) -> pd.Series:
    """Generic trailing-year cross-sectional tercile assignment at fires.

    Same mechanics as assign_rv63_tercile; used for any numeric fire-level series.
    Returns fire-indexed pd.Series[float 0/1/2/NaN].
    """
    fire_dates = pd.to_datetime(fires["date"]).values
    raw_vals = fire_vals.values.astype(float)
    terciles = np.full(len(fires), np.nan)

    for i, (fire_date_ts, val) in enumerate(zip(fire_dates, raw_vals)):
        if np.isnan(val):
            continue
        fire_date = pd.Timestamp(fire_date_ts)
        cutoff = fire_date - pd.Timedelta(days=int(trailing_bars * 1.5))
        mask = (fire_dates >= cutoff) & (fire_dates <= fire_date)
        window_vals = raw_vals[mask]
        window_vals = window_vals[~np.isnan(window_vals)]
        if len(window_vals) < 30:
            continue
        q33 = float(np.percentile(window_vals, 33.33))
        q67 = float(np.percentile(window_vals, 66.67))
        if val <= q33:
            terciles[i] = 0.0
        elif val <= q67:
            terciles[i] = 1.0
        else:
            terciles[i] = 2.0

    return pd.Series(terciles, index=fires.index, name=col_name + "_tercile", dtype=float)


# ---------------------------------------------------------------------------
# RUL-28 mandatory verdict clauses
# ---------------------------------------------------------------------------

def era_sign_stability(
    graded_ok: pd.DataFrame,
    stratum_col: str,
    outcome: str,
    *,
    n_bootstrap: int,
    computable_mask: "pd.Series | None" = None,
    extra_fe_cols: "list[str] | None" = None,
) -> dict:
    """Era-stratified r1_estimate — sign stability check for RUL-28.

    Runs r1_estimate on each PROGRAM_ERA subset and returns:
        era_rows: list of {era, n_treatment, coef, sign} per estimable era
        n_eras_estimable: count of eras with a non-None coef
        n_sign_agree: count of eras whose coef sign matches pooled_sign
        pooled_sign: sign of the pooled coef (passed via caller)
        sign_stable_3of4: bool — True iff n_sign_agree >= 3

    Thin-era threshold: skip eras with < 30 rows after computable_mask applied.
    Returns empty/defaults if stratum_col or outcome absent.
    """
    from scripts.research.entry_strata_phase0 import (
        _assign_era,
        PROGRAM_ERAS,
        r1_estimate,
    )

    if stratum_col not in graded_ok.columns or outcome not in graded_ok.columns:
        return {
            "era_rows": [],
            "n_eras_estimable": 0,
            "n_sign_agree": 0,
            "pooled_sign": None,
            "sign_stable_3of4": False,
            "note": "stratum or outcome column absent",
        }

    df = graded_ok.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["_era"] = df["date"].apply(_assign_era)

    # Apply computable_mask to establish the analysable pool
    if computable_mask is not None:
        aligned = computable_mask.reindex(df.index).fillna(False)
        df = df[aligned].copy()

    # Pooled direction from all estimable eras combined
    pooled_ok = df[df[stratum_col].notna() & df[outcome].notna()]
    if len(pooled_ok) < 10:
        return {
            "era_rows": [],
            "n_eras_estimable": 0,
            "n_sign_agree": 0,
            "pooled_sign": None,
            "sign_stable_3of4": False,
            "note": "insufficient pooled rows",
        }
    pooled_coef: float | None = None
    try:
        pr = r1_estimate(
            pooled_ok, outcome, stratum_col,
            fe_granularity="date",
            sector_col="sector" if "sector" in pooled_ok.columns else None,
            n_bootstrap=min(n_bootstrap, 200),
            extra_fe_cols=extra_fe_cols,
        )
        pooled_coef = pr.get("coef")
    except Exception:
        pass

    pooled_sign = None if (pooled_coef is None or pooled_coef == 0.0) else (1 if pooled_coef > 0 else -1)

    era_rows: list[dict] = []
    for era in PROGRAM_ERAS:
        sub = df[df["_era"] == era].copy()
        sub_ok = sub[sub[stratum_col].notna() & sub[outcome].notna()]
        n_treat = int((sub_ok[stratum_col] == 1.0).sum())
        if len(sub_ok) < 30 or sub_ok[stratum_col].nunique() < 2:
            era_rows.append({
                "era": era,
                "n_total": len(sub_ok),
                "n_treatment": n_treat,
                "coef": None,
                "sign": None,
                "note": "thin or no-variation",
            })
            continue
        try:
            res = r1_estimate(
                sub_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in sub_ok.columns else None,
                n_bootstrap=min(n_bootstrap, 200),
                extra_fe_cols=extra_fe_cols,
            )
            coef = res.get("coef")
            sign = None if (coef is None or coef == 0.0) else (1 if coef > 0 else -1)
            era_rows.append({
                "era": era,
                "n_total": len(sub_ok),
                "n_treatment": n_treat,
                "coef": coef,
                "sign": sign,
            })
        except Exception as exc:
            era_rows.append({
                "era": era,
                "n_total": len(sub_ok),
                "n_treatment": n_treat,
                "coef": None,
                "sign": None,
                "note": str(exc),
            })

    n_estimable = sum(1 for r in era_rows if r.get("coef") is not None)
    n_agree = (
        sum(1 for r in era_rows
            if r.get("sign") is not None and pooled_sign is not None
            and r["sign"] == pooled_sign)
        if pooled_sign is not None else 0
    )
    sign_stable = n_agree >= 3

    return {
        "era_rows":          era_rows,
        "n_eras_estimable":  n_estimable,
        "n_sign_agree":      n_agree,
        "pooled_sign":       pooled_sign,
        "sign_stable_3of4":  sign_stable,
    }


def ticker_half_sign_agreement(
    graded_ok: pd.DataFrame,
    stratum_col: str,
    outcome: str,
    *,
    n_bootstrap: int,
    computable_mask: "pd.Series | None" = None,
    extra_fe_cols: "list[str] | None" = None,
) -> dict:
    """Ticker-half sign agreement — mandatory on baskets panel (RUL-28).

    Splits tickers alphabetically into two halves; runs r1_estimate on each.
    Returns:
        half_rows: [{half: 'A'|'B', tickers_n, n_total, coef, sign}]
        sign_agree: bool — both halves have non-None coef and same sign
        note: populated if non-estimable

    Thin threshold: skip halves with < 20 rows.
    """
    from scripts.research.entry_strata_phase0 import r1_estimate

    if "ticker" not in graded_ok.columns or stratum_col not in graded_ok.columns:
        return {
            "half_rows": [],
            "sign_agree": False,
            "note": "ticker or stratum column absent",
        }

    df = graded_ok.copy()
    if computable_mask is not None:
        aligned = computable_mask.reindex(df.index).fillna(False)
        df = df[aligned].copy()

    all_tickers = sorted(df["ticker"].astype(str).unique())
    mid = len(all_tickers) // 2
    halves = [("A", set(all_tickers[:mid])), ("B", set(all_tickers[mid:]))]

    half_rows: list[dict] = []
    for label, tset in halves:
        sub = df[df["ticker"].astype(str).isin(tset)].copy()
        sub_ok = sub[sub[stratum_col].notna() & sub[outcome].notna()]
        if len(sub_ok) < 20 or sub_ok[stratum_col].nunique() < 2:
            half_rows.append({
                "half": label,
                "tickers_n": len(tset),
                "n_total": len(sub_ok),
                "coef": None,
                "sign": None,
                "note": "thin or no-variation",
            })
            continue
        try:
            res = r1_estimate(
                sub_ok, outcome, stratum_col,
                fe_granularity="date",
                sector_col="sector" if "sector" in sub_ok.columns else None,
                n_bootstrap=min(n_bootstrap, 200),
                extra_fe_cols=extra_fe_cols,
            )
            coef = res.get("coef")
            sign = None if (coef is None or coef == 0.0) else (1 if coef > 0 else -1)
            half_rows.append({
                "half": label,
                "tickers_n": len(tset),
                "n_total": len(sub_ok),
                "coef": coef,
                "sign": sign,
            })
        except Exception as exc:
            half_rows.append({
                "half": label,
                "tickers_n": len(tset),
                "n_total": len(sub_ok),
                "coef": None,
                "sign": None,
                "note": str(exc),
            })

    signs = [r["sign"] for r in half_rows if r.get("sign") is not None]
    sign_agree = len(signs) == 2 and signs[0] == signs[1]

    return {
        "half_rows":  half_rows,
        "sign_agree": sign_agree,
    }
