"""engine.signal_foundry.harness — frozen battery for the Signal Foundry.

BATTERY_VERSION = "sf-battery-1"

This file is FROZEN (SF-R2): changes to the battery require a human-authored PR.
The LLM emits declarative specs; it never modifies this ruler.

Battery stages:
  (a) Registration: trial_ledger.log_trial BEFORE computing (SF-R4).
  (b) Data loading + feature construction via apply_pipeline.
  (c) Statistics: Spearman IC, Newey-West HAC t, circular block bootstrap CI,
      time-shift placebo, negative-lag placebo, era split (2010-01-01), DSR.
      For excess_return / absolute_return + single_series: cost-aware backtest
      vs declared baseline (8 bps).
  (d) Verdict (SF-R9 closed grammar).
  (e) Write data/signal_foundry/results/<id>.json.

Thresholds (each marked with their causal_scout.py analogue):
  MIN_EFFECTIVE_MONTHS = 60  # 5 years in calendar months (history gate)
  MIN_N = 25                 # house power floor (mirrors causal_scout MIN_N)
  HAC_LAGS_DEFAULT = None    # computed as max(4, horizon_d) per series
  ERA_BREAK = 2010-01-01     # DT-R16 mandatory (mirrors causal_scout ERA_BREAK)
  N_BOOTSTRAP = 200          # DT-R14 (mirrors causal_scout N_BOOTSTRAP)
  N_SHIFT = 200              # DT-R14 time-shift placebo (mirrors causal_scout N_SHIFT)
  SHIFT_PCTILE_FLOOR = 0.90  # time-shift must be in top 10% of nulls (mirrors causal_scout)
  BOOT_CI_STRADDLES_THRESHOLD — unstable if both placebo legs are bad AND CI straddles 0
  DSR_FLOOR = 0.90           # pre-registered gate (default in config; overridden by spec)
  T_HAC_FLOOR = 2.0          # pre-registered gate (default; overridden by spec)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr  # type: ignore[import]

from engine.trial_ledger import TrialLedger
from engine.validation import (
    backtest_core,
    deflated_sharpe,
    newey_west_tstat,
    ret_moments,
)
from engine.signal_foundry.spec import construction_hash
from engine.signal_foundry.transforms import apply_pipeline

BATTERY_VERSION = "sf-battery-1"

# ---------------------------------------------------------------------------
# Constants (each with a comment mapping to causal_scout where applicable)
# ---------------------------------------------------------------------------
ERA_BREAK = pd.Timestamp("2010-01-01")   # DT-R16; mirrors causal_scout ERA_BREAK
MIN_EFFECTIVE_MONTHS = 60                # 5 calendar years — history gate
MIN_N = 25                               # house power floor; mirrors causal_scout MIN_N
N_BOOTSTRAP = 200                        # mirrors causal_scout N_BOOTSTRAP
N_SHIFT = 200                            # mirrors causal_scout N_SHIFT
SHIFT_PCTILE_FLOOR = 0.90               # time-shift top-10% threshold (causal_scout)
COST_BPS = 8.0                           # one-way cost for long/flat backtest

_ALLOWED_VERDICTS = {
    "data_missing", "insufficient_history", "insufficient_power",
    "era_specific", "unstable", "null", "pass_candidate",
    "forbidden", "error",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_series(entry: dict, repo_root: Path) -> pd.Series:
    """Load a single data entry from parquet or CSV.

    entry: {path, column, ...}  (from spec.data[])
    Raises FileNotFoundError / KeyError / ValueError on bad input.
    """
    path = Path(entry["path"])
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    col = entry.get("column")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, index_col=0, parse_dates=True, sep=sep)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    # Ensure index is DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    # Dedup index (keep last)
    df = df[~df.index.duplicated(keep="last")]

    if col not in df.columns:
        raise KeyError(f"Column '{col}' not found in {path}. Available: {list(df.columns)}")
    s = df[col].dropna()
    s.name = str(path.stem)
    return s


def _build_feature(spec: dict, repo_root: Path) -> pd.Series:
    """Load data entries and apply the spec's feature pipeline.

    For binary transforms (ratio, spread, rolling_corr), data must have
    exactly 2 entries; the pipeline receives a 2-tuple.
    """
    data_entries = spec["data"]
    if len(data_entries) == 1:
        raw = _load_series(data_entries[0], repo_root)
        inputs: Any = raw
    elif len(data_entries) == 2:
        s1 = _load_series(data_entries[0], repo_root)
        s2 = _load_series(data_entries[1], repo_root)
        # Align on common dates
        aligned = pd.concat([s1, s2], axis=1).dropna()
        inputs = (aligned.iloc[:, 0], aligned.iloc[:, 1])
    else:
        raise ValueError(
            f"spec.data has {len(data_entries)} entries; 1 or 2 supported"
        )

    pipeline = spec["feature"]["pipeline"]
    feature = apply_pipeline(inputs, pipeline)
    feature = feature.sort_index()
    return feature


def _build_target(spec: dict, repo_root: Path, feature_index: pd.DatetimeIndex) -> pd.Series:
    """Build the forward-return target from spec.target with STRICT next-bar discipline.

    Signal known at close t → exposure/outcome measured from t+1 (shift(1) on feature).
    That is implemented in the alignment step of run_spec, not here.

    Here we compute the raw forward metric over horizon_d calendar days:
      excess_return  = fwd horizon return of target.path MINUS baseline fwd return
      absolute_return = fwd horizon return (log or simple)
      drawdown_onset  = indicator: did price fall >=5% within horizon_d days?
      forward_vol     = realized vol over next horizon_d days
    """
    target_spec = spec["target"]
    kind = target_spec["kind"]
    horizon_d = int(target_spec["horizon_d"])
    tgt_path = target_spec["path"]

    tgt_entry = {"path": tgt_path, "column": target_spec.get("column", "Close")}
    # Many target files store 'Close' or 'Adj Close' or similar
    tgt_series = _load_raw_price(tgt_entry, repo_root)

    if kind == "absolute_return":
        fwd = tgt_series.pct_change(horizon_d).shift(-horizon_d)
        target = fwd.dropna()

    elif kind == "excess_return":
        baseline_name = spec.get("baseline", "buy_and_hold")
        fwd_asset = tgt_series.pct_change(horizon_d).shift(-horizon_d)
        baseline_fwd = _compute_baseline_fwd(tgt_series, baseline_name, horizon_d)
        target = (fwd_asset - baseline_fwd).dropna()

    elif kind == "drawdown_onset":
        # indicator: max drawdown within next horizon_d bars >= 5%
        def _drawdown_indicator(prices: pd.Series, h: int) -> pd.Series:
            n = len(prices)
            idx = prices.index
            out = pd.Series(np.nan, index=idx)
            arr = prices.to_numpy(float)
            for i in range(n - h):
                window = arr[i + 1: i + h + 1]
                if len(window) == 0:
                    continue
                peak = arr[i]
                if peak <= 0:
                    continue
                dd = (window - peak) / peak
                out.iloc[i] = float(np.min(dd) <= -0.05)
            return out
        target = _drawdown_indicator(tgt_series, horizon_d).dropna()

    elif kind == "forward_vol":
        # Realized vol over next horizon_d bars
        ret = tgt_series.pct_change()

        def _fwd_vol(s: pd.Series, h: int) -> pd.Series:
            n = len(s)
            out = pd.Series(np.nan, index=s.index)
            arr = s.to_numpy(float)
            for i in range(n - h):
                window = arr[i + 1: i + h + 1]
                if len(window) >= 2:
                    out.iloc[i] = float(np.std(window, ddof=1))
            return out
        target = _fwd_vol(ret, horizon_d).dropna()
    else:
        raise ValueError(f"Unknown target.kind: {kind}")

    target.name = f"target_{kind}_{horizon_d}d"
    return target


def _load_raw_price(entry: dict, repo_root: Path) -> pd.Series:
    """Load raw price series, trying common column names."""
    path = Path(entry["path"])
    if not path.is_absolute():
        path = repo_root / path
    if not path.exists():
        raise FileNotFoundError(f"Target file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, index_col=0, parse_dates=True, sep=sep)
    else:
        raise ValueError(f"Unsupported target file format: {path.suffix}")

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Try common column names
    col = entry.get("column")
    for candidate in ([col] if col else []) + ["Adj Close", "adj_close", "Close", "close", "price", "value"]:
        if candidate and candidate in df.columns:
            s = df[candidate].dropna()
            s.name = str(path.stem)
            return s
    raise KeyError(
        f"Could not find price column in {path}. "
        f"Tried: {[col, 'Adj Close', 'Close', 'price', 'value']}. "
        f"Available: {list(df.columns)}"
    )


def _compute_baseline_fwd(prices: pd.Series, baseline_name: str, horizon_d: int) -> pd.Series:
    """Compute baseline forward returns for the excess_return target kind."""
    if baseline_name == "buy_and_hold":
        return prices.pct_change(horizon_d).shift(-horizon_d)
    elif baseline_name == "sma_200":
        sma = prices.rolling(200, min_periods=100).mean()
        alloc = (prices > sma).astype(float)
        bt = backtest_core(prices, alloc, cost_bps=0.0)
        # Rolling horizon return of the bt strategy net
        fwd = bt["net"].rolling(horizon_d).sum().shift(-horizon_d)
        return fwd
    elif baseline_name == "flat":
        # Flat = 0% return everywhere
        return pd.Series(0.0, index=prices.index)
    else:
        raise ValueError(f"Unknown baseline: {baseline_name!r}. Allowed: buy_and_hold, sma_200, flat")


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _calendar_months(index: pd.DatetimeIndex) -> int:
    """Count distinct year-months in index (SF-R11, DT-R14)."""
    if len(index) == 0:
        return 0
    return int(len(index.to_period("M").unique()))


def _spearman_ic(feature: pd.Series, target: pd.Series) -> float:
    """Spearman rank IC between feature and target."""
    aligned = pd.concat([feature, target], axis=1).dropna()
    if len(aligned) < MIN_N:
        return float("nan")
    ic, _ = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return float(ic)


def _hac_lags_for_horizon(horizon_d: int) -> int:
    """HAC lag count appropriate for horizon (mirrors causal_scout hac_lags logic)."""
    return max(4, horizon_d)


def _circular_block_bootstrap_ic(
    feature: np.ndarray,
    target: np.ndarray,
    n_draws: int = N_BOOTSTRAP,
    block_size: int | None = None,
    seed: int = 42,
) -> dict:
    """Circular block bootstrap CI on the Spearman IC.

    Block size defaults to sqrt(n) (mirrors causal_scout MIN_BLOCK logic).
    Returns {ci_2p5, ci_97p5, boot_mean, n_draws, block_size, ci_straddles_0}.
    """
    n = len(feature)
    if n < max(15, (block_size or 21) * 3):
        return {}
    if block_size is None:
        block_size = max(5, int(np.sqrt(n)))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_size))
    grid = np.arange(block_size)
    stats = np.empty(n_draws)
    from scipy.stats import spearmanr as _sr
    for k in range(n_draws):
        starts = rng.integers(0, n, n_blocks)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        ic, _ = _sr(feature[idx], target[idx])
        stats[k] = float(ic)
    lo, hi = float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))
    return {
        "ci_2p5": round(lo, 4),
        "ci_97p5": round(hi, 4),
        "boot_mean": round(float(np.mean(stats)), 4),
        "n_draws": n_draws,
        "block_size": block_size,
        "ci_straddles_0": bool(lo <= 0.0 <= hi),
    }


def _time_shift_placebo_ic(
    feature: np.ndarray,
    target: np.ndarray,
    n_draws: int = N_SHIFT,
    min_shift: int | None = None,
    seed: int = 99,
) -> dict:
    """Circular time-shift placebo (DT-R14): rotate FEATURE series by random
    amounts >= min_shift (defaults to 1/4 of length), compute Spearman IC.

    Returns {shift_pctile, obs_ic, placebo_pct_ge_abs_obs, n_draws}.
    shift_pctile = fraction of placebo |IC| < |obs_IC|.
    A high pctile (>= 0.90) means observed IC is in the top 10% of nulls.
    """
    from scipy.stats import spearmanr as _sr
    n = len(feature)
    if n < 20:
        return {}
    if min_shift is None:
        min_shift = max(1, n // 4)
    obs_ic, _ = _sr(feature, target)
    rng = np.random.default_rng(seed)
    shifts = rng.integers(min_shift, n, n_draws)
    null_ics = np.empty(n_draws)
    for k, s in enumerate(shifts):
        f_shifted = np.roll(feature, int(s))
        ic, _ = _sr(f_shifted, target)
        null_ics[k] = float(ic)
    # Fraction of placebo |IC| that is LESS than |obs_IC| → pctile of obs
    shift_pctile = float(np.mean(np.abs(null_ics) < abs(obs_ic)))
    placebo_pct_ge = float(np.mean(np.abs(null_ics) >= abs(obs_ic)))
    return {
        "shift_pctile": round(shift_pctile, 4),
        "obs_ic": round(float(obs_ic), 4),
        "placebo_pct_ge_abs_obs": round(placebo_pct_ge, 4),
        "n_draws": n_draws,
    }


def _negative_lag_placebo_ic(
    feature: np.ndarray,
    target: np.ndarray,
    horizon_d: int,
) -> dict:
    """Negative-lag placebo: shift feature by -horizon_d (into the future).

    The feature must NOT predict better when shifted into the future than at lag 0.
    If the negative-lag IC is >= the observed IC in absolute terms, this is a
    concern (mirrors causal_scout negative-lag placebo logic).

    Returns {neg_lag_ic, obs_ic, neg_dominates}.
    """
    from scipy.stats import spearmanr as _sr
    n = len(feature)
    h = int(horizon_d)
    if h <= 0 or h >= n:
        return {}
    # Shift feature forward by horizon (looks into the future)
    f_neg = feature[h:]    # feature at t+h
    t_aligned = target[:n - h]  # target at t
    if len(f_neg) < MIN_N:
        return {}
    neg_ic, _ = _sr(f_neg, t_aligned)
    obs_ic, _ = _sr(feature[:n - h], t_aligned)
    neg_dominates = bool(abs(neg_ic) >= abs(obs_ic))
    return {
        "neg_lag_ic": round(float(neg_ic), 4),
        "obs_ic_same_window": round(float(obs_ic), 4),
        "neg_dominates": neg_dominates,
    }


def _era_split_ics(
    feature: pd.Series,
    target: pd.Series,
) -> dict:
    """Compute Spearman IC in pre/post-2010 eras (DT-R16).

    Returns {pre_ic, post_ic, sign_flip, era_n_pre, era_n_post}.
    sign_flip = True if pre and post ICs have opposite signs.
    """
    aligned = pd.concat([feature, target], axis=1).dropna()
    pre = aligned[aligned.index < ERA_BREAK]
    post = aligned[aligned.index >= ERA_BREAK]

    def _ic(df: pd.DataFrame) -> float | None:
        if len(df) < MIN_N:
            return None
        ic, _ = spearmanr(df.iloc[:, 0], df.iloc[:, 1])
        return float(ic)

    pre_ic = _ic(pre)
    post_ic = _ic(post)
    sign_flip = (
        pre_ic is not None
        and post_ic is not None
        and (pre_ic > 0) != (post_ic > 0)
    )
    return {
        "pre_ic": round(pre_ic, 4) if pre_ic is not None else None,
        "post_ic": round(post_ic, 4) if post_ic is not None else None,
        "era_n_pre": int(len(pre)),
        "era_n_post": int(len(post)),
        "sign_flip": sign_flip,
    }


def _split_half_ic(
    feature: pd.Series,
    target: pd.Series,
) -> dict:
    """Split-half IC: compare first half vs second half.

    Returns {h1_ic, h2_ic, sign_flip}.
    sign_flip = True if the two halves disagree in sign.
    """
    aligned = pd.concat([feature, target], axis=1).dropna()
    n = len(aligned)
    mid = n // 2
    h1 = aligned.iloc[:mid]
    h2 = aligned.iloc[mid:]

    def _ic(df: pd.DataFrame) -> float | None:
        if len(df) < MIN_N:
            return None
        ic, _ = spearmanr(df.iloc[:, 0], df.iloc[:, 1])
        return float(ic)

    h1_ic = _ic(h1)
    h2_ic = _ic(h2)
    sign_flip = (
        h1_ic is not None
        and h2_ic is not None
        and (h1_ic > 0) != (h2_ic > 0)
    )
    return {
        "h1_ic": round(h1_ic, 4) if h1_ic is not None else None,
        "h2_ic": round(h2_ic, 4) if h2_ic is not None else None,
        "split_half_sign_flip": sign_flip,
    }


# ---------------------------------------------------------------------------
# Backtest for single_series excess/absolute return specs
# ---------------------------------------------------------------------------

def _run_backtest(
    spec: dict,
    feature: pd.Series,
    repo_root: Path,
) -> dict:
    """Long/flat backtest for single_series excess_return / absolute_return specs.

    Implements strict next-bar discipline: alloc at t = sign(feature at t),
    exposure begins t+1 via backtest_core's shift(1).

    Returns a dict with {net_sharpe, gross_sharpe, cagr_net, cagr_gross,
    holdout_sharpe, max_dd, cost_bps, baseline_name, years}.
    Returns {} on failure.
    """
    try:
        kind = spec["target"]["kind"]
        if kind not in {"excess_return", "absolute_return"}:
            return {}
        if spec.get("universe", "single_series") != "single_series":
            return {}

        baseline_name = spec.get("baseline", "buy_and_hold")
        tgt_entry = {
            "path": spec["target"]["path"],
            "column": spec["target"].get("column", "Close"),
        }
        prices = _load_raw_price(tgt_entry, repo_root)

        # Align feature and prices
        aligned = pd.concat([feature.rename("f"), prices.rename("p")], axis=1).dropna()
        if len(aligned) < 60:
            return {}
        f = aligned["f"]
        p = aligned["p"]

        # Long/flat allocation: +1 if feature > 0, else 0 (no shorting)
        alloc = (f > 0).astype(float)

        bt = backtest_core(p, alloc, cost_bps=COST_BPS)
        net = bt["net"].dropna()
        gross = bt["gross"].dropna()
        hold = bt["hold"].dropna()

        ppy = 252
        def _ann_sharpe(r: pd.Series) -> float:
            r = r.dropna()
            sd = float(r.std(ddof=1))
            return float(r.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan")

        def _cagr(r: pd.Series) -> float:
            r = r.dropna()
            if len(r) < 2:
                return float("nan")
            return float(np.prod(1 + r) ** (ppy / len(r)) - 1)

        def _maxdd(r: pd.Series) -> float:
            eq = np.cumprod(1 + r.fillna(0).to_numpy(float))
            peak = np.maximum.accumulate(eq)
            return float(np.min(eq / peak - 1.0))

        return {
            "net_sharpe": round(_ann_sharpe(net), 3),
            "gross_sharpe": round(_ann_sharpe(gross), 3),
            "hold_sharpe": round(_ann_sharpe(hold), 3),
            "cagr_net": round(_cagr(net), 4),
            "cagr_gross": round(_cagr(gross), 4),
            "max_dd": round(_maxdd(net), 4),
            "cost_bps": COST_BPS,
            "baseline": baseline_name,
            "years": round(float(bt["years"]), 2),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _run_backtest_raw(
    spec: dict,
    feature: pd.Series,
    repo_root: Path,
) -> dict | None:
    """Return the raw backtest dict from backtest_core for DSR computation.

    Unlike _run_backtest (which returns only summary statistics), this returns
    the full backtest_core dict including the per-bar 'net' return Series.
    Used by run_spec to obtain an actual strategy-return stream for DSR.
    Returns None on any failure.
    """
    try:
        kind = spec["target"]["kind"]
        if kind not in {"excess_return", "absolute_return"}:
            return None
        if spec.get("universe", "single_series") != "single_series":
            return None

        tgt_entry = {
            "path": spec["target"]["path"],
            "column": spec["target"].get("column", "Close"),
        }
        prices = _load_raw_price(tgt_entry, repo_root)
        aligned = pd.concat([feature.rename("f"), prices.rename("p")], axis=1).dropna()
        if len(aligned) < 60:
            return None
        f = aligned["f"]
        p = aligned["p"]
        alloc = (f > 0).astype(float)
        return backtest_core(p, alloc, cost_bps=COST_BPS)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_spec(
    spec: dict,
    repo_root: str | Path = ".",
    ledger_path: str | Path | None = None,
    asof: str | None = None,
) -> dict:
    """Run the frozen battery on a declarative spec.

    Parameters
    ----------
    spec : dict
        Validated, registered spec (must have id, data, feature.pipeline, target, gates).
    repo_root : Path
        Root of the repository (for git-tracked path resolution).
    ledger_path : Path or None
        Path to the TrialLedger JSONL.  Defaults to engine.trial_ledger.DEFAULT_PATH.
    asof : str or None
        Override for the ran_at timestamp (ISO date string).  Default = date.today().

    Returns
    -------
    dict  — the full result record; also written to data/signal_foundry/results/<id>.json.

    Note on SF-R7 enforcement: schema validation (validate_spec) and the git-tracked
    path gate are enforced by the screen (engine.signal_foundry.screen.screen_candidate)
    BEFORE a spec is filed.  run_spec does NOT re-call validate_spec at run time —
    it relies on _build_feature raising FileNotFoundError/KeyError on absent or
    untracked paths, producing a 'data_missing' verdict.  A hand-built spec that
    bypasses the screen and references a gitignored-but-present runner-local store
    will not be blocked here; it will run and produce a result that carries no
    git-tracking guarantee.  Callers that bypass the screen must validate manually.
    """
    from engine.trial_ledger import DEFAULT_PATH as _DEFAULT_LEDGER

    repo_root = Path(repo_root)
    ran_at = asof or date.today().isoformat()
    spec_id = spec.get("id", "UNKNOWN")

    # ------------------------------------------------------------------
    # (a) Registration — log BEFORE computing (SF-R4)
    # ------------------------------------------------------------------
    led_path = Path(ledger_path) if ledger_path is not None else _DEFAULT_LEDGER
    ledger = TrialLedger(path=led_path, family="signal_foundry")

    # Canonical config for ledger dedup (construction + gates)
    _ledger_config = {
        "id": spec_id,
        "construction_hash": construction_hash(spec),
        "gates": spec.get("gates", {}),
        "registered_at": spec.get("registered_at"),
    }
    ledger.log_trial(
        config=_ledger_config,
        family="signal_foundry",
        source=spec_id,
    )
    ledger_n = ledger.effective_n("signal_foundry")

    # ------------------------------------------------------------------
    # Gate-freeze check: refuse if gates changed post-registration
    # ------------------------------------------------------------------
    stored_hash = spec.get("gates_hash")
    if stored_hash is not None:
        import hashlib as _hl
        import json as _js
        computed_hash = _hl.sha1(
            _js.dumps(spec.get("gates", {}), sort_keys=True, default=str,
                      separators=(",", ":")).encode()
        ).hexdigest()[:16]
        if computed_hash != stored_hash:
            return _write_result(repo_root, spec, {}, {}, {}, "error",
                                 [f"gates changed after registration (SF-R4): "
                                  f"stored={stored_hash!r} computed={computed_hash!r}"],
                                 ran_at, ledger_n)

    # ------------------------------------------------------------------
    # (b) Load data + build feature
    # ------------------------------------------------------------------
    try:
        feature = _build_feature(spec, repo_root)
    except Exception as exc:
        return _write_result(
            repo_root, spec, {}, {}, {}, "data_missing",
            [f"feature load/build failed: {exc}"],
            ran_at, ledger_n,
        )

    try:
        target = _build_target(spec, repo_root, feature.index)
    except Exception as exc:
        return _write_result(
            repo_root, spec, {}, {}, {}, "data_missing",
            [f"target load/build failed: {exc}"],
            ran_at, ledger_n,
        )

    # Align feature and target with STRICT next-bar discipline:
    # feature at t predicts target from t+1 onward.
    # Implement by shifting feature forward by 1 (i.e., the feature value
    # at t-1 aligns with the target outcome measured starting at t).
    feature_lagged = feature.shift(1)  # feature known at t → target starts at t+1
    aligned = pd.concat(
        [feature_lagged.rename("feature"), target.rename("target")],
        axis=1,
    ).dropna()

    if len(aligned) == 0:
        return _write_result(
            repo_root, spec, {}, {}, {}, "data_missing",
            ["no aligned (feature, target) pairs after shift(1)"],
            ran_at, ledger_n,
        )

    # ------------------------------------------------------------------
    # History gate: require >= 5 years = 60 effective calendar months
    # ------------------------------------------------------------------
    eff_months = _calendar_months(pd.DatetimeIndex(aligned.index))
    if eff_months < MIN_EFFECTIVE_MONTHS:
        return _write_result(
            repo_root, spec, {"effective_months": eff_months}, {}, {},
            "insufficient_history",
            [f"only {eff_months} effective months (need >= {MIN_EFFECTIVE_MONTHS})"],
            ran_at, ledger_n,
        )

    # Power gate
    n_obs = len(aligned)
    if n_obs < MIN_N:
        return _write_result(
            repo_root, spec, {"n_obs": n_obs, "effective_months": eff_months},
            {}, {}, "insufficient_power",
            [f"only {n_obs} aligned observations (need >= {MIN_N})"],
            ran_at, ledger_n,
        )

    feat_arr = aligned["feature"].to_numpy(float)
    tgt_arr = aligned["target"].to_numpy(float)
    feat_series = aligned["feature"]
    tgt_series = aligned["target"]

    # ------------------------------------------------------------------
    # (c) Statistics
    # ------------------------------------------------------------------
    horizon_d = int(spec["target"]["horizon_d"])
    hac_lags = _hac_lags_for_horizon(horizon_d)

    # Full-sample Spearman IC
    full_ic = _spearman_ic(feat_series, tgt_series)

    # HAC t-stat on IC series (non-overlapping subsampling)
    # Use non-overlapping subsamples to correct for horizon overlap
    sub_step = max(1, horizon_d)
    feat_sub = feat_arr[::sub_step]
    tgt_sub = tgt_arr[::sub_step]
    # Build IC series day-by-day (rolling window of min_periods=21 for HAC input)
    # For HAC: compute cross-product z-score effect series, then NW on mean
    from engine.validation import newey_west_tstat as _nw
    # Effect series: zscore-product (mirrors causal_scout z-product)
    def _zscore_arr(a: np.ndarray) -> np.ndarray:
        s = float(np.std(a))
        if s < 1e-12:
            return np.zeros_like(a)
        return (a - float(np.mean(a))) / s
    effect = _zscore_arr(feat_arr) * _zscore_arr(tgt_arr)
    effect_sub = effect[::sub_step]
    hac_stat = _nw(effect_sub, lags=max(1, min(hac_lags, len(effect_sub) - 1)))

    # Split-half IC
    split_half = _split_half_ic(feat_series, tgt_series)

    # Era split IC (DT-R16)
    era = _era_split_ics(feat_series, tgt_series)

    # Circular block bootstrap CI on IC
    block_ci = _circular_block_bootstrap_ic(
        feat_arr, tgt_arr, n_draws=N_BOOTSTRAP,
        block_size=max(5, min(horizon_d, int(np.sqrt(n_obs)))),
        seed=42,
    )

    # Time-shift placebo (DT-R14, mirrors causal_scout SHIFT_PCTILE_FLOOR=0.90)
    shift_plac = _time_shift_placebo_ic(
        feat_arr, tgt_arr, n_draws=N_SHIFT,
        min_shift=max(1, horizon_d),  # shifts must be >= horizon to avoid contamination
        seed=99,
    )

    # Negative-lag placebo (mirrors causal_scout negative-lag logic)
    neg_plac = _negative_lag_placebo_ic(feat_arr, tgt_arr, horizon_d)

    # ------------------------------------------------------------------
    # Backtest (for excess_return / absolute_return + single_series)
    # Run BEFORE DSR so the actual net-return series can feed the gate.
    # ------------------------------------------------------------------
    try:
        backtest_result = _run_backtest(spec, feat_series, repo_root)
    except Exception as exc:
        backtest_result = {"error": str(exc)}

    # ------------------------------------------------------------------
    # DSR gate (SF-R3): use honest multiple-testing N from ledger.
    #
    # Input series selection:
    #   * For excess_return / absolute_return single_series specs a real
    #     long/flat strategy return series is available from _run_backtest.
    #     We prefer it because deflated_sharpe() was designed for a strategy
    #     return stream (var_scaler = 1 - skew*SR + (kurt-1)/4*SR^2 assumes
    #     return-series moments, not z-product moments).  The z-product of two
    #     standardized normal series is structurally leptokurtic (~kurtosis 6.75
    #     vs 3 for normal), which would distort the deflation correction.
    #   * For all other spec kinds (panel, drawdown_onset, forward_vol) no
    #     cost-aware return series is computed, so we fall back to the z-product
    #     effect_sub as a proxy.  This is an acknowledged limitation (PR-E
    #     deferral: a proper IC-significance DSR for panel specs is TODO).
    # ------------------------------------------------------------------
    _target_kind = spec.get("target", {}).get("kind", "")
    _universe = spec.get("universe", "single_series")
    _use_backtest_for_dsr = (
        _target_kind in {"excess_return", "absolute_return"}
        and _universe == "single_series"
        and isinstance(backtest_result, dict)
        and "error" not in backtest_result
    )

    dsr_result: dict | None = None
    _dsr_series_label: str = ""
    if _use_backtest_for_dsr:
        # Obtain the actual net-return series from a fresh backtest call
        # (backtest_result only stores summary stats, not the per-bar returns).
        try:
            _bt_raw = _run_backtest_raw(spec, feat_series, repo_root)
            _net_rets = _bt_raw.get("net") if _bt_raw else None
            if _net_rets is not None and len(_net_rets.dropna()) >= 10:
                moments = ret_moments(_net_rets)
                _dsr_series_label = "strategy_net_return"
            else:
                moments = ret_moments(pd.Series(effect_sub))
                _dsr_series_label = "z_product_fallback"
        except Exception:
            moments = ret_moments(pd.Series(effect_sub))
            _dsr_series_label = "z_product_fallback"
    else:
        # Non-return spec or panel: z-product proxy (acknowledged PR-E deferral).
        moments = ret_moments(pd.Series(effect_sub))
        _dsr_series_label = "z_product_ic_proxy"

    if moments is not None:
        sr_daily, skew, kurt, t = moments
        dsr_result = deflated_sharpe(
            sr_daily, skew, kurt, t,
            ledger=ledger,
            family="signal_foundry",
        )
        if dsr_result is not None:
            dsr_result = dict(dsr_result, dsr_series=_dsr_series_label)

    stats = {
        "n_obs": n_obs,
        "effective_months": eff_months,
        "full_ic": round(full_ic, 4) if full_ic == full_ic else None,
        "hac": hac_stat,
        "split_half": split_half,
        "era_split": era,
        "block_bootstrap_ci": block_ci,
        "dsr": dsr_result,
    }

    placebos = {
        "time_shift": shift_plac,
        "negative_lag": neg_plac,
    }

    # ------------------------------------------------------------------
    # (d) Verdict (SF-R9 closed grammar)
    # ------------------------------------------------------------------
    gates = spec.get("gates", {})
    t_hac_gate = float(gates.get("min_t_hac", 2.0))
    dsr_gate = float(gates.get("dsr", 0.90))
    # NOTE: fdr_q (SF-R3 BH-FDR) is a REQUIRED gate key in spec.py and is
    # recorded in each spec's gates dict, but per-spec BH-FDR is inherently
    # cohort-level (requires a set of p-values across the family, not just the
    # current single spec).  Application is deferred to the PR-E cohort review
    # stage, where all specs in a family are evaluated together.  The gate value
    # stored here is the pre-registered threshold that the PR-E stage will apply.
    # TODO (PR-E): apply Benjamini-Hochberg across the family's p-values at
    #              promotion time using each spec's fdr_q threshold.

    verdict, reasons = _compute_verdict(
        spec_id, full_ic, hac_stat, block_ci, shift_plac, neg_plac,
        era, split_half, dsr_result, t_hac_gate, dsr_gate, n_obs,
    )

    return _write_result(
        repo_root, spec, stats, placebos, backtest_result,
        verdict, reasons, ran_at, ledger_n,
    )


def _compute_verdict(
    spec_id: str,
    full_ic: float,
    hac_stat: dict,
    block_ci: dict,
    shift_plac: dict,
    neg_plac: dict,
    era: dict,
    split_half: dict,
    dsr_result: dict | None,
    t_hac_gate: float,
    dsr_gate: float,
    n_obs: int,
) -> tuple[str, list[str]]:
    """Determine verdict from stats.  SF-R9 closed grammar."""
    reasons: list[str] = []

    t_hac = hac_stat.get("t") if hac_stat else None

    # --- insufficient_power ---
    if n_obs < MIN_N or t_hac is None:
        return "insufficient_power", [f"n_obs={n_obs} < {MIN_N} or HAC t unavailable"]

    # --- era_specific (sign flip across era break) ---
    if era.get("sign_flip"):
        pre_ic = era.get("pre_ic")
        post_ic = era.get("post_ic")
        reasons.append(
            f"era split sign flip: pre_2010 IC={pre_ic}, post_2010 IC={post_ic} (DT-R16)"
        )
        return "era_specific", reasons

    # --- unstable (split-half sign flip OR bootstrap CI straddles 0 with bad placebos) ---
    unstable_flags: list[str] = []
    if split_half.get("split_half_sign_flip"):
        unstable_flags.append(
            f"split-half sign flip: H1 IC={split_half.get('h1_ic')}, H2 IC={split_half.get('h2_ic')}"
        )
    if block_ci.get("ci_straddles_0"):
        unstable_flags.append(
            f"bootstrap CI [{block_ci.get('ci_2p5')}, {block_ci.get('ci_97p5')}] straddles 0"
        )
    if len(unstable_flags) >= 2:
        # Both split-half flip AND CI straddles 0 → unstable
        return "unstable", unstable_flags

    # --- time-shift placebo failure ---
    # mirrors causal_scout: if shift_pctile < 0.90, IC is indistinguishable from lagged echo
    shift_pctile = shift_plac.get("shift_pctile")
    if shift_pctile is not None and shift_pctile < SHIFT_PCTILE_FLOOR:
        reasons.append(
            f"time-shift placebo: IC at {shift_pctile:.0%} of null distribution "
            f"(floor={SHIFT_PCTILE_FLOOR:.0%}) — indistinguishable from lagged echo (DT-R14)"
        )
        return "null", reasons

    # --- negative-lag placebo failure ---
    # mirrors causal_scout: reverse causation concern
    if neg_plac.get("neg_dominates"):
        reasons.append(
            f"negative-lag placebo fires: future-shifted IC {neg_plac.get('neg_lag_ic')} "
            f">= observed IC {neg_plac.get('obs_ic_same_window')} — reverse-causation concern"
        )
        return "null", reasons

    # --- HAC t gate ---
    t_abs = abs(float(t_hac)) if t_hac is not None else 0.0
    if t_abs < t_hac_gate:
        reasons.append(
            f"|t_HAC|={t_abs:.2f} < gate {t_hac_gate} (pre-registered)"
        )
        return "null", reasons

    # --- DSR gate ---
    dsr_val = (dsr_result or {}).get("dsr")
    if dsr_val is None:
        reasons.append("DSR could not be computed (insufficient moments)")
        return "null", reasons
    if float(dsr_val) < dsr_gate:
        reasons.append(
            f"DSR={dsr_val:.4f} < gate {dsr_gate} (pre-registered)"
        )
        return "null", reasons

    # --- pass_candidate ---
    reasons.append(
        f"meets pre-registered gates: |t_HAC|={t_abs:.2f} >= {t_hac_gate}, "
        f"DSR={dsr_val:.4f} >= {dsr_gate}; placebos clean"
    )
    return "pass_candidate", reasons


def _write_result(
    repo_root: Path,
    spec: dict,
    stats: dict,
    placebos: dict,
    backtest: dict,
    verdict: str,
    reasons: list[str],
    ran_at: str,
    ledger_n: int,
) -> dict:
    """Assemble result dict and write to data/signal_foundry/results/<id>.json."""
    assert verdict in _ALLOWED_VERDICTS, f"verdict '{verdict}' not in SF-R9 grammar"
    spec_id = spec.get("id", "UNKNOWN")
    result = {
        "spec": spec,
        "stats": stats,
        "placebos": placebos,
        "backtest": backtest,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "battery_version": BATTERY_VERSION,
        "ran_at": ran_at,
        "ledger_n_at_run": ledger_n,
    }

    # Write to data/signal_foundry/results/<id>.json (SF-R10)
    try:
        out_dir = repo_root / "data" / "signal_foundry" / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{spec_id}.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
    except Exception as exc:
        result["write_error"] = str(exc)

    return result
