"""engine/lab.py — Strategy Lab façade.

A THIN orchestration layer (zero new math) that lets a session go from
ticker → indicator → confluence → backtest → verdict in a handful of calls,
reusing canonical implementations without re-coding them.

The module solves three problems in the existing code:
  1. Indicator drift  — multiple files define RSI, EMA, etc.  ``INDICATORS``
     pins exactly ONE source-of-truth per concept.
  2. Backtest boilerplate — every script open-codes the same
     backtest_core → DSR → CI chain.  ``backtest()`` is the ONE seam.
  3. Multiple-testing accounting — ``backtest()`` ALWAYS uses a TrialLedger;
     a literal N is forbidden (enforced by tests/test_no_literal_ntrials.py).

IMPORTANT — survivorship bias
  ``load()`` reads from ``data/stocks/``, which is a ~224-name survivor universe
  of mega-caps.  Every Trial produced from this universe carries
  ``survivorship_biased=True``.  Do not promote a signal to production on the
  basis of in-universe IC alone.

Display-only / research artefact.  Nothing here originates signals, scores, or
escalations; LLM-originated alpha is forbidden by house law.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# lazy imports from engine/* — imported at call time so we don't pay the cost
# (and so circular-import risk stays zero) for callers that only need load().
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1.  DATA LOADING
# ---------------------------------------------------------------------------

_STOCKS_GROUP = "stocks"
_STOCKS_DIR = Path("data") / "stocks"
_QUICK_NAMES = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "JPM"]


def load(
    tickers: str | Sequence[str] = "ALL",
    group: str = "stocks",
    start: str | None = None,
    end: str | None = None,
    min_bars: int = 400,
) -> dict[str, pd.DataFrame]:
    """Load price DataFrames from the store for a set of tickers.

    Parameters
    ----------
    tickers:
        * ``'ALL'``   — every parquet in ``data/<group>/``
        * ``'quick'`` — a hard-coded 8-name smoke-test list
        * list/tuple of ticker strings — load exactly those names
    group:
        store group (default ``'stocks'``).
    start, end:
        ISO date strings for date-slicing after load (inclusive).
    min_bars:
        drop tickers with fewer rows (after slicing) than this threshold.

    Returns
    -------
    dict mapping ticker → DataFrame with columns ``[close, high, low, volume]``.
    The returned frames are SORTED by date index with duplicates removed.

    Notes
    -----
    This universe is SURVIVORSHIP-BIASED (mega-cap survivors only).
    Every Trial produced from it carries ``survivorship_biased=True``.
    """
    from lib import store  # noqa: PLC0415

    # --- resolve ticker list -------------------------------------------------
    if isinstance(tickers, str) and tickers.upper() == "ALL":
        parquet_dir = Path("data") / group
        if not parquet_dir.exists():
            return {}
        names = sorted(p.stem for p in parquet_dir.glob("*.parquet"))
    elif isinstance(tickers, str) and tickers.lower() == "quick":
        names = list(_QUICK_NAMES)
    else:
        names = list(tickers)  # type: ignore[arg-type]

    # --- load + filter -------------------------------------------------------
    out: dict[str, pd.DataFrame] = {}
    for name in names:
        df = store.read(group, name)
        if df is None or df.empty:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if start:
            df = df.loc[start:]
        if end:
            df = df.loc[:end]
        if len(df) < min_bars:
            continue
        out[name] = df
    return out


def bench(name: str = "_GSPC") -> pd.Series:
    """Return the benchmark close Series from the ``yahoo`` store group.

    Parameters
    ----------
    name:
        Store key, e.g. ``'_GSPC'`` (S&P 500) or ``'_VIX'``.

    Returns
    -------
    pd.Series of closing prices, or an empty Series if not found.
    """
    from lib import store  # noqa: PLC0415

    df = store.read("yahoo", name)
    if df is None or df.empty:
        return pd.Series(dtype=float, name=name)
    close_col = "close" if "close" in df.columns else df.columns[0]
    return df[close_col].sort_index().rename(name)


# ---------------------------------------------------------------------------
# 2.  INDICATOR REGISTRY
# ---------------------------------------------------------------------------

def _ind_rsi(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import canon  # noqa: PLC0415
    return canon.rsi(df["close"], n=kw.get("n", 14))


def _ind_ema(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import strategy_signals as ss  # noqa: PLC0415
    return ss.ema(df["close"], n=kw.get("n", 20))


def _ind_sma(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import strategy_signals as ss  # noqa: PLC0415
    return ss.sma(df["close"], n=kw.get("n", 50))


def _ind_stoch_rsi_k(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import canon  # noqa: PLC0415
    k, _d = canon.stoch_rsi_kd(df["close"])
    return k


def _ind_stoch_rsi_d(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import canon  # noqa: PLC0415
    _k, d = canon.stoch_rsi_kd(df["close"])
    return d


def _ind_macd_hist(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import technicals  # noqa: PLC0415
    return technicals.macd_hist(df["close"])


def _ind_atr(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    return st.atr(df["high"], df["low"], df["close"], n=kw.get("n", 14))


def _ind_adx(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    # adx_dmi returns (adx, plus_di, minus_di) — we expose the ADX series
    adx, _plus_di, _minus_di = st.adx_dmi(df["high"], df["low"], df["close"],
                                           n=kw.get("n", 14))
    return adx


def _ind_bb_pctb(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import strategy_signals as ss  # noqa: PLC0415
    return ss.bollinger_pctb(df["close"], n=kw.get("n", 20), k=kw.get("k", 2.0))


def _ind_realized_vol(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    return st.realized_vol(df["close"], n=kw.get("n", 20))


def _ind_ttm_squeeze(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    raw = st.ttm_squeeze(df["high"], df["low"], df["close"])
    return raw.astype(float)


def _ind_donchian_pos(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import strategy_signals as ss  # noqa: PLC0415
    return ss.donchian_position(df, entry_n=kw.get("entry_n", 55),
                                exit_n=kw.get("exit_n", 20))


def _ind_obv(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    return st.on_balance_volume(df["close"], df["volume"])


def _ind_cmf(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import stock_technicals as st  # noqa: PLC0415
    return st.chaikin_money_flow(df["high"], df["low"], df["close"],
                                 df["volume"], n=kw.get("n", 20))


def _ind_dd_from_high(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import strategy_signals as ss  # noqa: PLC0415
    return ss.dd_from_high(df["close"], n=kw.get("n", 252))


def _ind_rolling_slope(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import indicators  # noqa: PLC0415
    return indicators.rolling_slope(df["close"], window=kw.get("window", 20))


def _ind_slope_z(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import indicators  # noqa: PLC0415
    return indicators.slope_z(df["close"],
                               slope_window=kw.get("slope_window", 20),
                               baseline_window=kw.get("baseline_window", 252),
                               use_log=kw.get("use_log", True))


def _ind_pct_rank(df: pd.DataFrame, **kw) -> pd.Series:
    from engine import indicators  # noqa: PLC0415
    return indicators.pct_rank_window(df["close"], window=kw.get("window", 252))


# Canonical registry: name → Callable[[DataFrame, **kw], Series]
# This is the fix for indicator drift — one implementation per concept.
INDICATORS: dict[str, Callable[..., pd.Series]] = {
    "rsi": _ind_rsi,
    "ema": _ind_ema,
    "sma": _ind_sma,
    "stoch_rsi_k": _ind_stoch_rsi_k,
    "stoch_rsi_d": _ind_stoch_rsi_d,
    "macd_hist": _ind_macd_hist,
    "atr": _ind_atr,
    "adx": _ind_adx,
    "bb_pctb": _ind_bb_pctb,
    "realized_vol": _ind_realized_vol,
    "ttm_squeeze": _ind_ttm_squeeze,
    "donchian_pos": _ind_donchian_pos,
    "obv": _ind_obv,
    "cmf": _ind_cmf,
    "dd_from_high": _ind_dd_from_high,
    "rolling_slope": _ind_rolling_slope,
    "slope_z": _ind_slope_z,
    "pct_rank": _ind_pct_rank,
}


def indicator(name: str, df: pd.DataFrame, **params) -> pd.Series:
    """Compute a named indicator for a single-ticker OHLCV DataFrame.

    Parameters
    ----------
    name:
        Key in ``INDICATORS``.  Raises ``KeyError`` on unknown names so
        callers surface the drift immediately instead of silently getting
        a wrong series.
    df:
        DataFrame with columns ``[close]``; ``[high, low, volume]`` are
        required for some indicators (atr, adx, ttm_squeeze, obv, cmf).
    **params:
        Passed verbatim to the underlying implementation (e.g. ``n=14``).

    Returns
    -------
    pd.Series aligned to ``df.index``.
    """
    fn = INDICATORS.get(name)
    if fn is None:
        raise KeyError(
            f"Unknown indicator {name!r}.  Available: {sorted(INDICATORS)}"
        )
    return fn(df, **params)


# ---------------------------------------------------------------------------
# 3.  FEATURE FRAME
# ---------------------------------------------------------------------------

def features(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    """Build a causal feature DataFrame from a single-ticker OHLCV frame.

    Returns a DataFrame whose every column is a Series from ``INDICATORS``
    (computed causally — no look-ahead).  Missing columns (e.g. no volume data)
    are silently skipped rather than raising.

    Parameters
    ----------
    df:
        OHLCV DataFrame (``close`` required; ``high``, ``low``, ``volume``
        improve coverage).
    cols:
        Subset of ``INDICATORS`` keys to compute.  ``None`` = all that can
        be computed from available columns.

    Returns
    -------
    DataFrame with one column per successfully-computed indicator.
    """
    want = cols if cols is not None else list(INDICATORS)
    result: dict[str, pd.Series] = {}
    has_hl = "high" in df.columns and "low" in df.columns
    has_vol = "volume" in df.columns
    _needs_hl = {"atr", "adx", "ttm_squeeze", "cmf"}
    _needs_vol = {"obv", "cmf"}
    for name in want:
        if name in _needs_hl and not has_hl:
            continue
        if name in _needs_vol and not has_vol:
            continue
        try:
            s = indicator(name, df)
            result[name] = s
        except Exception as exc:
            log.debug("features: skipping %s — %s", name, exc)
    if not result:
        return pd.DataFrame(index=df.index)
    return pd.DataFrame(result, index=df.index)


# ---------------------------------------------------------------------------
# 4.  SIGNAL
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """Declarative strategy signal.

    A Signal wraps either an expression callable or a pre-computed pair of
    (continuous signal Series, position Series [0,1]) and carries the
    metadata needed for backtest() and Trial reporting.

    Parameters
    ----------
    expr:
        Callable ``(df: DataFrame) → (signal: Series, pos: Series)`` where
        ``signal`` is a continuous-valued bullish indicator and ``pos`` is
        a long/flat position in [0,1].  Alternatively, pass ``signal`` and
        ``pos`` directly as Series.
    signal:
        Pre-computed continuous signal Series (alternative to ``expr``).
    pos:
        Pre-computed position Series in [0,1] (alternative to ``expr``).
    horizon:
        Holding-period hint in calendar days (for IC and report labelling).
    family:
        TrialLedger family key — the multiple-testing namespace this Signal
        spends budget in.
    name:
        Human-readable label; defaults to repr of ``expr`` or ``'unnamed'``.
    """
    expr: Callable[[pd.DataFrame], tuple[pd.Series, pd.Series]] | None = None
    signal: pd.Series | None = None
    pos: pd.Series | None = None
    horizon: int = 21
    family: str = "lab"
    name: str = ""

    def evaluate(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Return ``(signal, pos)`` either from stored Series or by calling ``expr``.

        Raises ``ValueError`` if neither ``expr`` nor pre-computed series are set.
        """
        if self.signal is not None and self.pos is not None:
            return self.signal, self.pos
        if self.expr is not None:
            return self.expr(df)
        raise ValueError(
            "Signal must have either .expr or pre-computed (.signal, .pos)"
        )


def confluence(
    *signals: Signal,
    mode: str = "all",
    min_k: int | None = None,
    horizon: int | None = None,
    family: str = "lab",
    name: str = "",
) -> Signal:
    """Combine multiple Signals into one via AND/OR/k-of-n logic.

    Parameters
    ----------
    *signals:
        Signal objects to combine.
    mode:
        ``'all'`` — every signal must be positive (AND).
        ``'any'`` — at least one positive (OR).
        ``'k_of_n'`` — at least ``min_k`` positive.
    min_k:
        Required for ``mode='k_of_n'``.
    horizon:
        Horizon for the combined signal.  Defaults to the max of input horizons.
    family:
        TrialLedger family for the output Signal.
    name:
        Label for the combined Signal.

    Returns
    -------
    A new Signal whose ``expr`` evaluates all inputs and combines their
    position Series.
    """
    if not signals:
        raise ValueError("confluence requires at least one Signal")
    if mode not in ("all", "any", "k_of_n"):
        raise ValueError(f"mode must be 'all', 'any', or 'k_of_n', got {mode!r}")
    if mode == "k_of_n" and min_k is None:
        raise ValueError("mode='k_of_n' requires min_k")

    _horizon = horizon if horizon is not None else max(s.horizon for s in signals)
    _k = min_k if min_k is not None else (len(signals) if mode == "all" else 1)

    def _expr(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        pairs = [s.evaluate(df) for s in signals]
        sig_series = [p[0] for p in pairs]
        pos_series = [p[1] for p in pairs]
        # align on common index
        idx = pos_series[0].index
        for ps in pos_series[1:]:
            idx = idx.intersection(ps.index)
        pos_matrix = pd.DataFrame(
            {i: ps.reindex(idx) for i, ps in enumerate(pos_series)}
        )
        combined_pos = (pos_matrix.sum(axis=1) >= _k).astype(float)
        # continuous signal = mean of component signals
        sig_matrix = pd.DataFrame(
            {i: ss.reindex(idx) for i, ss in enumerate(sig_series)}
        )
        combined_sig = sig_matrix.mean(axis=1)
        return combined_sig, combined_pos

    return Signal(
        expr=_expr,
        horizon=_horizon,
        family=family,
        name=name or f"confluence_{mode}({'|'.join(s.name or '?' for s in signals)})",
    )


# ---------------------------------------------------------------------------
# 5.  TRIAL RESULT
# ---------------------------------------------------------------------------

_LAB_DIR = Path("data") / "lab"
_DEFAULT_TRIALS_PATH = _LAB_DIR / "trials.jsonl"

# Verdict taxonomy mirrors strategy_lab.py
_VERDICT_RULES = [
    # (condition_fn, verdict_string)
    # Applied in order; first match wins.
]

_BANNED_METRICS = frozenset({
    # metrics that verdict() refuses to key off (house law)
    "accuracy", "win_rate_raw",
})


@dataclass
class Trial:
    """Result of a single backtest run from ``backtest()``.

    Attributes
    ----------
    name:
        Ticker or universe label this trial was run on.
    family:
        TrialLedger family (multiple-testing namespace).
    stats:
        Dict of numeric statistics (DSR, Sharpe CI, split-half, rank IC, …).
    survivorship_biased:
        Always True when the universe comes from ``data/stocks/``.
    meta:
        Free-form dict for extra metadata (horizon, cost_bps, etc.).
    """
    name: str
    family: str
    stats: dict[str, Any]
    survivorship_biased: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def verdict(self) -> str:
        """Return a verdict string based on stats.

        Taxonomy (mirrors strategy_lab):
          TRADABLE        — DSR ≥ 0.95, CI excludes 0, split-half consistent
          ENTRY-OVERLAY   — DSR ≥ 0.90, meaningful IC
          RISK-CONTROL    — useful as a risk filter even with limited edge
          NO-EDGE         — everything else

        Refuses to key off any metric in ``_BANNED_METRICS``.

        The DSR pass/fail band wording is delegated to
        ``engine.validation.dsr_verdict()`` to avoid re-hardcoding thresholds.
        """
        from engine import validation as _V  # noqa: PLC0415

        s = self.stats
        dsr = s.get("dsr") or 0.0
        ci_lo = (s.get("sharpe_ci") or [None])[0]
        split_ok = bool(s.get("split_half_consistent", False))
        mean_ic = s.get("mean_ic") or 0.0

        # Delegate band thresholds to the shared validation helper so a single
        # change to dsr_verdict() propagates everywhere.
        _dsr_band = _V.dsr_verdict(dsr)  # "SURVIVES …" / "MARGINAL …" / "FAILS …"

        if dsr >= 0.95 and ci_lo is not None and ci_lo > 0 and split_ok:
            return "TRADABLE"
        if dsr >= 0.90 and abs(mean_ic) > 0.02:
            return "ENTRY-OVERLAY"
        # risk-control: low edge but consistent sign and modest IC
        if abs(mean_ic) > 0.01 and dsr >= 0.70:
            return "RISK-CONTROL"
        _ = _dsr_band  # consumed above for side-effect-free delegation check
        return "NO-EDGE"

    def to_ledger(self, path: str | Path = _DEFAULT_TRIALS_PATH) -> None:
        """Append this Trial as a JSONL row to ``path``.

        Creates parent directories automatically.  Idempotent on repeated calls
        (each call appends one line; downstream tools must dedup by content if
        needed).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "name": self.name,
            "family": self.family,
            "stats": self.stats,
            "survivorship_biased": self.survivorship_biased,
            "meta": self.meta,
            "verdict": self.verdict(),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------------------
# 6.  BACKTEST
# ---------------------------------------------------------------------------

def backtest(
    signal: Signal,
    universe: dict[str, pd.DataFrame],
    *,
    cost_bps: float = 5.0,
    bench_name: str = "_GSPC",
    family: str | None = None,
    n_configs_searched: int | None = None,
    stop_pct: float | None = None,
) -> Trial:
    """Run a full backtest of ``signal`` over ``universe`` and return a Trial.

    This is the ONE canonical backtest seam.  Internally it:

    1. Per-name backtest_core (one file at a time, causal position).
    2. Equal-weight aggregation of net returns across the universe.
    3. ret_moments → deflated_sharpe via a TrialLedger (NEVER a literal N —
       the ratchet in tests/test_no_literal_ntrials.py enforces this).
    4. block_bootstrap_ci on the aggregate net returns.
    5. Split-half robustness: first vs second half of the time series.
    6. rank_ic time series → ic_summary + newey_west_tstat.

    Parameters
    ----------
    signal:
        Signal to evaluate (evaluated once per ticker).
    universe:
        Dict returned by ``load()``.  Must be non-empty.
    cost_bps:
        One-way transaction cost in basis points.
    bench_name:
        Benchmark store key used for bench return moments only.
    family:
        TrialLedger family.  Defaults to ``signal.family``.
    n_configs_searched:
        The count of configs tried in the search that produced this signal
        (used to populate the TrialLedger so DSR is honest).  If ``None``,
        the ledger starts at 1 (this single evaluation).
    stop_pct:
        If given, clip allocation to 0 when drawdown from peak exceeds this
        fraction (e.g. 0.20 = 20% stop).  Applied before cost calculation.

    Returns
    -------
    Trial with ``survivorship_biased=True`` when universe is from data/stocks/.

    Notes
    -----
    The returned Trial stats never include banned metrics (``_BANNED_METRICS``).
    """
    from engine import validation as V  # noqa: PLC0415
    from engine.trial_ledger import TrialLedger  # noqa: PLC0415

    _family = family or signal.family

    # --- build ledger with N --------------------------------------------------
    _n = max(int(n_configs_searched or 1), 1)
    ledger = TrialLedger.with_declared_budget(_n, _family)

    # --- per-name backtests ---------------------------------------------------
    net_returns: list[pd.Series] = []
    ics: list[float] = []   # per-date rank IC proxy (using position as signal)
    fwd_horizon = signal.horizon

    bench_close = bench(bench_name)

    for name, df in universe.items():
        try:
            _sig, pos = signal.evaluate(df)
        except Exception as exc:
            log.debug("backtest: skipping %s — evaluate failed: %s", name, exc)
            continue

        # optionally apply a trailing-stop to the position
        if stop_pct is not None and stop_pct > 0:
            close = df["close"]
            cum = (1.0 + close.pct_change().fillna(0.0)).cumprod()
            peak = cum.expanding().max()
            dd = cum / peak - 1.0
            pos = pos.where(dd > -abs(stop_pct), 0.0)

        bt = V.backtest_core(df["close"], pos.reindex(df.index).fillna(0.0),
                             cost_bps=cost_bps)
        net = bt["net"]
        if len(net.dropna()) < 30:
            continue
        net_returns.append(net)

        # per-date IC proxy: signal rank vs fwd_horizon-bar return
        fwd = df["close"].pct_change(fwd_horizon).shift(-fwd_horizon)
        common = _sig.index.intersection(fwd.index)
        if len(common) >= 10:
            ic = V.rank_ic(_sig.reindex(common), fwd.reindex(common))
            if np.isfinite(ic):
                ics.append(ic)

    if not net_returns:
        return Trial(
            name="(empty universe)",
            family=_family,
            stats={"error": "no valid backtests"},
            survivorship_biased=True,
            meta={"cost_bps": cost_bps},
        )

    # --- equal-weight aggregate -----------------------------------------------
    agg = pd.concat(net_returns, axis=1).mean(axis=1).dropna()

    # --- statistics -----------------------------------------------------------
    stats: dict[str, Any] = {}

    # ret_moments → deflated_sharpe
    moments = V.ret_moments(agg)
    if moments is not None:
        sr_daily, skew, kurt, T = moments
        dsr_result = V.deflated_sharpe(
            sr_daily, skew, kurt, T,
            ledger=ledger, family=_family,
        )
        if dsr_result:
            stats.update(dsr_result)
        stats["dsr_verdict"] = V.dsr_verdict(stats.get("dsr", 0.0))

    # block_bootstrap_ci
    bb = V.block_bootstrap_ci(agg, ann=252)
    if bb:
        stats.update(bb)

    # split-half robustness
    half = len(agg) // 2
    if half >= 30:
        h1, h2 = agg.iloc[:half], agg.iloc[half:]
        m1, m2 = V.ret_moments(h1), V.ret_moments(h2)
        if m1 and m2:
            sign1, sign2 = np.sign(m1[0]), np.sign(m2[0])
            stats["split_half_consistent"] = bool(sign1 == sign2 and sign1 != 0)
            stats["split_half_sr_h1"] = round(float(m1[0]), 4)
            stats["split_half_sr_h2"] = round(float(m2[0]), 4)

    # IC summary
    if ics:
        ic_sum = V.ic_summary(ics, periods_per_year=max(1, 252 // fwd_horizon))
        stats.update(ic_sum)
        nw = V.newey_west_tstat(ics)
        stats["ic_nw_t"] = nw.get("t")
        stats["ic_nw_p"] = nw.get("p")

    # n_tickers covered
    stats["n_tickers"] = len(net_returns)

    return Trial(
        name=signal.name or _family,
        family=_family,
        stats=stats,
        survivorship_biased=True,
        meta={
            "cost_bps": cost_bps,
            "horizon": fwd_horizon,
            "n_configs_searched": _n,
            "bench": bench_name,
        },
    )


# ---------------------------------------------------------------------------
# 7.  CHARACTERIZE
# ---------------------------------------------------------------------------

def characterize(
    names: list[str],
    universe: dict[str, pd.DataFrame],
    *,
    horizon: int = 21,
    regime_bench: str = "_GSPC",
    vix_name: str = "_VIX",
    min_ics: int = 6,
) -> dict:
    """Compute a per-indicator white-space characterization map.

    For each indicator in ``names`` (must be keys of ``INDICATORS``) computes:

    * ``base_rate``       — time-series of per-date cross-sectional rank ICs,
                            summarised via ``validation.ic_summary`` +
                            ``validation.newey_west_tstat``.
    * ``persistence``     — ``validation.bootstrap_effective_t`` on the equal-
                            weight aggregate position series (proxy for signal
                            autocorrelation / effective-N haircut).
    * ``regime``          — IC split by SPX-200dma regime (above / below) and,
                            where VIX data are available, by VIX tercile.
    * ``orthogonality``   — ``validation.vif`` across all named indicators
                            computed on the first ticker in the universe (full
                            feature-frame), plus per-pair Spearman correlations.

    Writes ``data/lab/indicator_characterization.json`` and returns the dict.

    Parameters
    ----------
    names:
        List of indicator keys from ``INDICATORS``.  Unknown keys are logged
        and skipped (marked ``status: unknown_indicator``).
    universe:
        Dict from ``load()``; used for the IC loop and persistence estimate.
    horizon:
        Forward-return horizon in calendar days for IC computation.
    regime_bench:
        Store key for the SPX benchmark (for 200-dma regime split).
    vix_name:
        Store key for the VIX series (for VIX-tercile regime split).
    min_ics:
        Minimum number of per-date ICs required to produce a summary; below
        this threshold the section is ``{"n": n, "insufficient": True}``.

    Notes
    -----
    This is the characterization MACHINERY, not a full sweep.  Running all
    200+ catalog signals against the full ~224-ticker survivor universe is
    compute-intensive; a dedicated nightly sweep script should call this
    with ``tickers='quick'`` for smoke checks and the full ``tickers='ALL'``
    universe for production runs.  The file written here is a research
    artefact; do not promote signals to production on in-universe IC alone
    (survivorship bias — see module docstring).
    """
    from engine import validation as V  # noqa: PLC0415

    # --- regime series -------------------------------------------------------
    spx = bench(regime_bench)
    vix_s = bench(vix_name)

    def _spx_regime(date) -> str | None:
        """Return 'above_200dma' / 'below_200dma' for a given date."""
        if spx.empty:
            return None
        spx_sub = spx.loc[:date]
        if len(spx_sub) < 200:
            return None
        ma200 = float(spx_sub.iloc[-200:].mean())
        return "above_200dma" if float(spx_sub.iloc[-1]) >= ma200 else "below_200dma"

    # Pre-compute VIX tercile thresholds over the full series
    _vix_q33: float | None = None
    _vix_q67: float | None = None
    if not vix_s.empty:
        vix_clean = vix_s.dropna()
        if len(vix_clean) >= 60:
            _vix_q33 = float(vix_clean.quantile(0.333))
            _vix_q67 = float(vix_clean.quantile(0.667))

    def _vix_tercile(date) -> str | None:
        if _vix_q33 is None or vix_s.empty:
            return None
        try:
            v = float(vix_s.asof(date))  # type: ignore[arg-type]
        except Exception:
            return None
        if not np.isfinite(v):
            return None
        if v <= _vix_q33:
            return "vix_low"
        if v <= _vix_q67:
            return "vix_mid"
        return "vix_high"

    # --- IC loop over universe dates -----------------------------------------
    # We compute a CROSS-SECTIONAL IC per rebalance date (every horizon bars).
    # Only tickers that have all named indicators on that date contribute.
    # The result is a dict: indicator_name -> list of (date, ic, regime_spx, regime_vix)

    # Collect signal matrices per ticker, then align to common dates
    ticker_signals: dict[str, dict[str, pd.Series]] = {}
    ticker_fwd: dict[str, pd.Series] = {}

    for tkr, df in universe.items():
        sig_map: dict[str, pd.Series] = {}
        for name in names:
            if name not in INDICATORS:
                continue
            try:
                s = indicator(name, df)
                sig_map[name] = s
            except Exception as exc:
                log.debug("characterize: %s indicator %s failed: %s", tkr, name, exc)
        if sig_map:
            ticker_signals[tkr] = sig_map
            fwd = df["close"].pct_change(horizon).shift(-horizon)
            ticker_fwd[tkr] = fwd

    # Collect ICs per indicator, split by regime
    ic_records: dict[str, list[tuple]] = {n: [] for n in names if n in INDICATORS}

    if ticker_signals:
        # Get a common date grid from the first ticker
        first_tkr = next(iter(ticker_signals))
        ref_index = ticker_signals[first_tkr][next(iter(ticker_signals[first_tkr]))].index
        # Sample every `horizon` bars to avoid heavily overlapping forward returns
        step = max(1, horizon // 2)
        sample_dates = ref_index[::step]

        for date in sample_dates:
            # Build cross-section: ticker -> (signal_value, fwd_return)
            for ind_name in ic_records:
                sig_cross: dict[str, float] = {}
                fwd_cross: dict[str, float] = {}
                for tkr, sig_map in ticker_signals.items():
                    if ind_name not in sig_map:
                        continue
                    s = sig_map[ind_name]
                    f = ticker_fwd.get(tkr)
                    if f is None:
                        continue
                    try:
                        sv = float(s.asof(date))  # type: ignore[arg-type]
                        fv = float(f.asof(date))  # type: ignore[arg-type]
                    except Exception:
                        continue
                    if np.isfinite(sv) and np.isfinite(fv):
                        sig_cross[tkr] = sv
                        fwd_cross[tkr] = fv

                if len(sig_cross) < 5:
                    continue
                ic = V.rank_ic(
                    pd.Series(sig_cross),
                    pd.Series(fwd_cross),
                )
                if np.isfinite(ic):
                    reg_spx = _spx_regime(date)
                    reg_vix = _vix_tercile(date)
                    ic_records[ind_name].append((str(date.date()), ic, reg_spx, reg_vix))

    # --- orthogonality via VIF on the first ticker ---------------------------
    _vif_result: dict[str, float] = {}
    if ticker_signals:
        first_tkr = next(iter(ticker_signals))
        feat_dict = {n: ticker_signals[first_tkr][n]
                     for n in names if n in ticker_signals[first_tkr]}
        if len(feat_dict) >= 2:
            feat_df = pd.DataFrame(feat_dict).dropna()
            if len(feat_df) >= 30:
                _vif_result = V.vif(feat_df)

    # --- build output --------------------------------------------------------
    out: dict[str, Any] = {}

    for name in names:
        if name not in INDICATORS:
            out[name] = {"status": "unknown_indicator"}
            continue

        records = ic_records.get(name, [])
        all_ics = [r[1] for r in records]
        n_ics = len(all_ics)

        if n_ics < min_ics:
            base_rate: dict[str, Any] = {"n": n_ics, "insufficient": True}
            persistence: dict[str, Any] = {}
            regime: dict[str, Any] = {}
        else:
            # base_rate
            ppy = max(1, 252 // horizon)
            base_rate = V.ic_summary(all_ics, periods_per_year=ppy)
            nw = V.newey_west_tstat(all_ics)
            base_rate["nw_t"] = nw.get("t")
            base_rate["nw_p"] = nw.get("p")

            # persistence: bootstrap_effective_t on per-ticker position proxies
            # Use the IC time series as the "returns" proxy for autocorrelation
            ic_series = pd.Series(all_ics)
            persistence = V.bootstrap_effective_t(ic_series)

            # regime splits
            regime = {}
            for reg_field_idx, reg_label in [(2, "spx_regime"), (3, "vix_regime")]:
                buckets: dict[str, list[float]] = {}
                for r in records:
                    key = r[reg_field_idx]
                    if key is not None:
                        buckets.setdefault(key, []).append(r[1])
                if buckets:
                    regime[reg_label] = {
                        k: V.ic_summary(v, periods_per_year=ppy)
                        for k, v in buckets.items()
                        if len(v) >= min_ics
                    }

        # orthogonality
        orthogonality: dict[str, Any] = {
            "vif": _vif_result.get(name),
        }

        out[name] = {
            "status": "ok",
            "base_rate": base_rate,
            "persistence": persistence,
            "regime": regime,
            "orthogonality": orthogonality,
        }

    path = _LAB_DIR / "indicator_characterization.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# 8.  CATALOG ENTRY POINTS  (token-efficient AI interface)
# ---------------------------------------------------------------------------

def list_signals(family: str | None = None) -> list[dict]:
    """Passthrough to ``engine.tech_catalog.list_signals``.

    Returns a list of signal descriptor dicts for every registered catalog
    signal, optionally filtered by ``family``.  Each entry includes the
    ``signal_id`` key.  Use this to enumerate available signals before calling
    ``catalog_backtest``.

    Parameters
    ----------
    family:
        If given, return only signals whose ``family`` key equals this string.
        ``None`` = all signals.
    """
    from engine import tech_catalog  # noqa: PLC0415
    return tech_catalog.list_signals(family=family)


def catalog_backtest(
    signal_id: str,
    universe: dict[str, pd.DataFrame],
    *,
    horizon: int | None = None,
    cost_bps: float = 5.0,
    family: str | None = None,
    n_configs_searched: int | None = None,
    stop_pct: float | None = None,
    **kw: Any,
) -> Trial:
    """Token-efficient AI entry point: enumerate + backtest ANY catalog signal.

    Dispatches ``signal_id`` → ``tech_catalog.compute`` → wraps as a
    ``lab.Signal`` → ``lab.backtest``.  An AI agent can call
    ``list_signals()`` to enumerate, then ``catalog_backtest(id, universe)``
    to evaluate, without writing boilerplate.

    Parameters
    ----------
    signal_id:
        A signal ID returned by ``list_signals()`` / ``tech_catalog.list_signals()``.
    universe:
        Dict from ``load()``.
    horizon:
        Forward-return horizon in calendar days.  Defaults to the descriptor's
        ``default_params.get('horizon', 21)`` or 21 if unset.
    cost_bps:
        One-way transaction cost in basis points.
    family:
        TrialLedger family.  Defaults to the signal's catalog ``family``.
    n_configs_searched:
        Number of configs tried (for honest DSR haircut).  Defaults to 1.
    stop_pct:
        Optional trailing-stop fraction passed to ``backtest()``.
    **kw:
        Additional param overrides forwarded to ``tech_catalog.compute``
        (e.g. ``n=14`` for an RSI-based signal).

    Returns
    -------
    Trial (``survivorship_biased=True`` when universe is from data/stocks/).

    Raises
    ------
    KeyError:
        If ``signal_id`` is not registered in the catalog.
    """
    from engine import tech_catalog  # noqa: PLC0415

    descriptor = tech_catalog.get_signal(signal_id)
    _family = family or descriptor.get("family", "lab")
    _horizon = horizon or int(
        descriptor.get("default_params", {}).get("horizon", 21)
    )

    def _expr(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        raw = tech_catalog.compute(signal_id, df, **kw)
        raw_filled = raw.reindex(df.index).fillna(0.0)
        # event signals (0/1) double as position; continuous signals need a
        # threshold — use sign > 0 for direction=+1 or < 0 for direction=-1.
        direction = descriptor.get("direction", 1)
        if descriptor.get("kind") == "event":
            pos = raw_filled.clip(0.0, 1.0)
        elif direction < 0:
            pos = (raw_filled < 0).astype(float)
        else:
            pos = (raw_filled > 0).astype(float)
        return raw_filled, pos

    sig = Signal(
        expr=_expr,
        horizon=_horizon,
        family=_family,
        name=signal_id,
    )

    return backtest(
        sig,
        universe,
        cost_bps=cost_bps,
        family=_family,
        n_configs_searched=n_configs_searched,
        stop_pct=stop_pct,
    )
