"""Entry-Stack Expansion W2 — S-SQ Squeeze Release Phase-0 Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md §3 F3, §5, §10.
Amendment 1 ref: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md
  RUL-13: primary horizons = 21d (stop5, fwd_mdd_21 / mae21, clean8_21, days_to_10)
          mae63 REMOVED from verdict tables.
  RUL-14: co-primaries zone_held_21, stop_vol_21 (stop_vol_21 excluded from BH pool).
W0 baselines frozen: research/entry_stack/W0_BASELINES.md (RUL-9).
NC yardstick: research/entry_stack/W1_NC_REPORT.md (RUL-3).

SPECIES: S16 — Squeeze Release, horizon_class=rotational, phase0.
(S14 = Failed Breakout, S15 = Spring Reclaim are taken; S16 is the next free number.)

TRIAL FAMILY: esx_sq_phase0 (budget=12, pre-registered at W0).
  frozen state grid × 2 panels × 3 forms + 3 named sensitivities
  (pctile_thresh=20; release_window=2; vol_confirm=1.5)

ORDER OF OPERATIONS (RUL-5): registry FIRST (done via register_s16_species()),
  ledger SECOND (esx_sq_phase0 already declared in trial_ledger.jsonl at W0),
  study THIRD (this script).

Events = FIRED_UP state ONSETS from engine/vol_squeeze.assess_series:
  - Per ticker: compute assess_series(close, high, low, volume, cfg=DEFAULTS)
  - Onset = first bar where state transitions INTO FIRED_UP
    (i.e., state[t] == 'FIRED_UP' AND state[t-1] != 'FIRED_UP')
  - Dedup consecutive FIRED_UP: one event per onset (multiple consecutive FIRED_UP
    bars = one episode; only the first bar fires)
  - FIRED_DOWN events are BANNED from the long study (direction fixture in tests)
  - Defaults: pctile_thresh=25, min_duration=5, release_window=3, vol_confirm=1.3

Three forms per panel:
  (a) standalone:  raw FIRED_UP onset events
  (b) COILED intersection: events in TRUE COILED context
      = washout_ctx (individual >=15% drawdown) AND cohort_frac >= 0.40
      (reuses S-UR label_coiled_context verbatim, including weekly-D staleness doc)
  (c) gate-fire proximity: events within +/-5 bars of gate_fires_{panel}.parquet
      (gatefire intersection form = independence structurally N/A per masterplan)

SIGN CONVENTION:
  stop5 is an ADVERSE outcome. MORE POSITIVE coefficient = MORE stops (WORSE).
  Non-inferiority = CI UPPER bound < +0.01.
  stop5 superiority = CI UPPER bound < 0.0.
  Beneficial outcomes superiority: CI LOWER > 0.

OUTCOME SCOPE (RUL-13):
  Primary: stop5, fwd_mdd_21 (mae21), rotational_liftoff (clean8_21), days_to_10.
  Co-primary (RUL-14): zone_held_21 (beside stop5 in every table).
  stop_vol_21: reported as adjudication context ONLY; excluded from BH pool.
  mae63: REMOVED from verdict tables.

BH SCOPE: One BH pass pooling ALL cells x forms x outcomes of esx_sq_phase0.
  stop_vol_21 and days_to_10 excluded from BH pool.

NC-2 MARGINALITY: For the gatefire-proximity form, proximity confounding is
  tested by adding NC-2 proximity-band FE to the R1 model for stop5.
  Reuses _run_nc2_band_fe from run_w2_sur.py verbatim.

PANELS:
  - deep:    data/stocks/ (224 names, close + high/low + volume; 64y history)
  - baskets: data/baskets/ohlcv/ (2,519 names, full OHLCV 2014+)
  - delisted (close-only): DELISTED ARM: NOT APPLICABLE — needs H/L for assess_series.

DELISTED NOTE: The delisted panel (data/breadth/_closes_delisted.parquet) is close-only.
  vol_squeeze.assess_series requires H/L for the TTM-squeeze arm of the compression gate.
  Without H/L the compression threshold is looser (BBWP+HVP only, no TTM squeeze),
  which changes the fidelity-pinned event definition. Per masterplan §1 fact table
  row 3: 'Delisted-aware checks possible for close-only species; NOT for H/L-dependent
  species (S-SQ)'. The delisted panel cannot run this species. Report must contain
  an explicit DELISTED ARM: NOT APPLICABLE note with this reason.

All events use T+1 fill, graded via engine.grading forward_metrics + terminal_state.
BH q<=0.10 within esx_sq_phase0 family.

Usage:
    cd /path/to/repo
    python scripts/research/run_w2_ssq.py
    python scripts/research/run_w2_ssq.py --smoke
    python scripts/research/run_w2_ssq.py --n-bootstrap 500 --panel deep baskets
    python scripts/research/run_w2_ssq.py --out research/entry_stack/W2_SSQ_REPORT.md
"""
from __future__ import annotations

import argparse
import concurrent.futures
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Enumeration checkpoint cache
# ---------------------------------------------------------------------------
# Default location is intentionally OUTSIDE the repo tree so git never sees it.
# Override via the SSQ_EVENT_CACHE env var or the --cache-dir CLI arg.
_DEFAULT_SSQ_CACHE_DIR = Path("/private/tmp/_ssq_event_cache")


def _get_event_cache_dir(panel: str, cfg_key: str, *, override: Path | None = None) -> Path:
    """Return (and create) the cache directory for a given panel + cfg_key combo.

    Asserts the cache dir is outside the repo tree to prevent accidental git-adds.
    """
    import os
    base = Path(os.environ.get("SSQ_EVENT_CACHE", str(override or _DEFAULT_SSQ_CACHE_DIR)))
    cache_dir = base / panel / cfg_key
    # Guard: cache must not live inside the repo tree.
    try:
        cache_dir.resolve().relative_to(_REPO_ROOT.resolve())
        # If we get here, cache IS inside the repo — bail out.
        raise RuntimeError(
            f"SSQ_EVENT_CACHE resolves to a path inside the repo tree: {cache_dir}. "
            "Set SSQ_EVENT_CACHE to a directory outside the repo root."
        )
    except ValueError:
        pass  # expected: relative_to raises ValueError when path is outside
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _ticker_cache_path(cache_dir: Path, ticker: str) -> Path:
    """Return the parquet file path for a single ticker's cached events."""
    safe = ticker.replace("/", "_").replace("\\", "_")
    return cache_dir / f"{safe}.parquet"


def _load_ticker_cache(cache_dir: Path, ticker: str) -> list[dict] | None:
    """Load cached events for ticker.  Returns None on any miss or error."""
    path = _ticker_cache_path(cache_dir, ticker)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df.to_dict("records")
    except Exception:  # noqa: BLE001
        return None


def _save_ticker_cache(cache_dir: Path, ticker: str, rows: list[dict]) -> None:
    """Persist a ticker's event rows to the cache (best-effort; never raises)."""
    try:
        path = _ticker_cache_path(cache_dir, ticker)
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["ticker", "date", "panel", "fired_dir", "volume_confirmed",
                     "days_compressed", "bbwp", "hv_pctile", "coverage", "cfg_key"]
        )
        df.to_parquet(path, index=False)
    except Exception as exc:  # noqa: BLE001
        log.debug("_save_ticker_cache: failed to write cache for %s: %s", ticker, exc)

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import harness primitives from W0 PR-C (reuse — L1 law)
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
)

# Import fast R1 estimator and formatting helpers from NC runner (reuse — L1)
from scripts.research.run_w1_nc import (  # noqa: E402
    fast_r1_estimate,
    fast_effect_table,
    fast_era_table,
    bh_correction,
    _fast_make_blocks,
    _empty_r1,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
    compute_nc2_proximity_proxy,
    assign_nc2_bands,
    _eq_proximity_long,
)

# Reuse S-UR shared machinery verbatim (L1 law: reuse, do not rewrite)
from scripts.research.run_w2_sur import (  # noqa: E402
    _load_deep_ohlcv,
    _load_baskets_ohlcv,
    label_coiled_context,
    label_gate_fire_proximity,
    run_form_analysis,
    apply_family_wide_bh,
    check_species_bar_per_form,
    _parse_nc_yardstick_from_report,
    _run_nc2_band_fe,
    compute_cofire_share_trading_bars,
    _check_era_sign_stability,
    GATE_FIRE_PROXIMITY_BARS,
    INDEPENDENCE_BARS,
    MAX_COFIRE_SHARE,
    MIN_EPISODES_PER_FORM,
    NONINFERIORITY_MARGIN,
    OUTCOME_COLS,
    OUTCOME_COLS_BH,
    ADVERSE_METRICS,
    BENEFICIAL_METRICS,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"
_DEEP_STORE    = _DATA / "stocks"
_BASKETS_OHLCV = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Species ID — S16 (next free after S14=Failed breakout, S15=Spring Reclaim)
# Verified at registration (register_s16_species()) AND at finalize.
# ---------------------------------------------------------------------------
SPECIES_ID   = "S16"
SPECIES_NAME = "Squeeze Release"
SPECIES_FAMILY = "esx_sq_phase0"

# ---------------------------------------------------------------------------
# Frozen study parameters (masterplan F3, not tunable)
# Defaults from engine/vol_squeeze.DEFAULTS:
#   pctile_thresh=25, min_duration=5, release_window=3, vol_confirm=1.3
# Named sensitivities (part of the 12-trial budget):
#   pctile_thresh=20, release_window=2, vol_confirm=1.5
# ---------------------------------------------------------------------------
DEFAULTS_CFG = {
    "pctile_thresh": 25,
    "min_duration":  5,
    "release_window": 3,
    "vol_confirm":   1.3,
}
# Named sensitivities (budget itemization, masterplan §5)
SENSITIVITY_CONFIGS = {
    "pctile20":    {"pctile_thresh": 20},   # sensitivity 1
    "relwin2":     {"release_window": 2},   # sensitivity 2
    "volconf15":   {"vol_confirm": 1.5},    # sensitivity 3
}


# ---------------------------------------------------------------------------
# Volume-carrying OHLCV loaders (LOCAL to S-SQ — volume is load-bearing)
#
# DESIGN CHOICE: S-SQ uses its own loaders rather than adding an
# include_volume parameter to the shared S-UR loaders in run_w2_sur.py.
# Rationale:
#   - S-UR does not need volume (its event is a close-vs-rolling-low reclaim,
#     not a volume-gated release). Adding a param to the shared loaders would
#     touch a verified artifact for a concern that is specific to S-SQ.
#   - Keeping the loaders local to run_w2_ssq.py is the minimal invasive
#     change: S-UR is untouched; the shared loaders continue to work as
#     shipped for S-UR and any future species that do not need volume.
#   - If a future species needs volume from the shared loaders, it can
#     add the include_volume=False parameter at that time with its own PR.
#
# Both raw stores carry volume:
#   data/stocks/      — columns [close, high, low, volume]  (verified W0 census)
#   data/baskets/ohlcv — columns [open, high, low, close, volume]  (same census)
# ---------------------------------------------------------------------------

def _load_deep_ohlcv_volume() -> dict[str, pd.DataFrame]:
    """Load deep panel with volume: close + high + low + volume (224 names).

    Volume is required for vol_squeeze.assess_series to compute volume_confirmed.
    Without volume, vol_ok=None inside assess() and every FIRED_UP event fires on
    price break ALONE — the defining volume-confirmation mechanism is disabled.
    """
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            cols = [c for c in ("close", "high", "low", "volume") if c in df.columns]
            if "close" not in cols:
                continue
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("deep: failed to load %s: %s", path.name, exc)
    n_with_vol = sum(1 for df in store.values() if "volume" in df.columns)
    log.info(
        "Loaded %d deep OHLCV+volume records (%d with volume column)",
        len(store), n_with_vol,
    )
    return store


def _load_baskets_ohlcv_volume() -> dict[str, pd.DataFrame]:
    """Load baskets panel with volume: close + high + low + volume (2,519 names).

    See _load_deep_ohlcv_volume docstring for the volume-loading rationale.
    """
    store: dict[str, pd.DataFrame] = {}
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            cols = [c for c in ("close", "high", "low", "volume") if c in df.columns]
            if "close" not in cols:
                continue
            sub = df[cols].dropna(subset=["close"]).sort_index()
            if len(sub) > 0:
                store[ticker] = sub
        except Exception as exc:  # noqa: BLE001
            log.warning("baskets: failed to load %s: %s", path.name, exc)
    n_with_vol = sum(1 for df in store.values() if "volume" in df.columns)
    log.info(
        "Loaded %d basket OHLCV+volume records (%d with volume column)",
        len(store), n_with_vol,
    )
    return store


def _spot_check_volume_loading(
    store: dict[str, pd.DataFrame],
    panel_name: str,
    sample_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Empirical spot-check: verify volume column is present and non-empty.

    Returns a dict with:
        n_total: int
        n_with_volume: int
        n_without_volume: int
        sample_results: dict[ticker -> {has_volume, n_rows, vol_nonzero}]

    Per task brief: 'verify empirically that deep AAPL and 3 sampled baskets
    frames now carry volume.'
    """
    if sample_tickers is None:
        # Default: AAPL + up to 3 alpha-sorted tickers
        candidates = sorted(store.keys())
        sample_tickers = list(dict.fromkeys(
            (["AAPL"] if "AAPL" in store else []) +
            [t for t in candidates if t != "AAPL"][:3]
        ))

    n_with_vol    = sum(1 for df in store.values() if "volume" in df.columns and df["volume"].notna().any())
    n_without_vol = len(store) - n_with_vol

    sample_results: dict[str, dict] = {}
    for t in sample_tickers:
        if t not in store:
            continue
        df = store[t]
        has_vol = "volume" in df.columns
        sample_results[t] = {
            "has_volume":   has_vol,
            "n_rows":       len(df),
            "vol_nonzero":  int(df["volume"].gt(0).sum()) if has_vol else 0,
            "vol_null":     int(df["volume"].isna().sum()) if has_vol else None,
        }
        log.info(
            "spot-check %s panel=%s: has_volume=%s n_rows=%d vol_nonzero=%d",
            t, panel_name,
            sample_results[t]["has_volume"],
            sample_results[t]["n_rows"],
            sample_results[t]["vol_nonzero"],
        )

    return {
        "n_total":          len(store),
        "n_with_volume":    n_with_vol,
        "n_without_volume": n_without_vol,
        "sample_results":   sample_results,
    }


def _build_volume_coverage_table(
    all_events_by_panel: dict[str, pd.DataFrame],
) -> dict[str, dict[str, int]]:
    """Build per-panel volume-confirmed / volume-missing event counts.

    Returns {panel: {confirmed: int, not_confirmed: int, missing: int, total: int}}

    'volume_confirmed' column:
        True  (stored as bool True or 1.0)  → engine confirmed vol >= 1.3x avg
        False (stored as bool False or 0.0) → vol present but below threshold
        NaN / missing                       → volume data absent for this ticker

    Per task brief: 'print a per-panel volume-coverage table in the report;
    if any names genuinely lack volume, exclude their events from the
    mechanism-faithful set with counts printed.'
    """
    result: dict[str, dict[str, int]] = {}
    for panel, events in all_events_by_panel.items():
        if events.empty or "volume_confirmed" not in events.columns:
            result[panel] = {"confirmed": 0, "not_confirmed": 0, "missing": len(events), "total": len(events)}
            continue

        vc = events["volume_confirmed"]
        # volume_confirmed stored as bool or float (True/1.0/0.0/NaN)
        # Normalise: True/1.0 → confirmed, False/0.0 → not_confirmed, NaN → missing
        confirmed     = int(((vc == True) | (vc == 1.0)).sum())   # noqa: E712
        not_confirmed = int(((vc == False) | (vc == 0.0)).sum())  # noqa: E712
        missing       = int(vc.isna().sum())
        total         = len(events)
        result[panel] = {
            "confirmed":     confirmed,
            "not_confirmed": not_confirmed,
            "missing":       missing,
            "total":         total,
        }
        log.info(
            "volume_coverage panel=%s: confirmed=%d not_confirmed=%d missing=%d total=%d",
            panel, confirmed, not_confirmed, missing, total,
        )
    return result


# ---------------------------------------------------------------------------
# FIRED_UP onset enumeration
# Event = first bar where state transitions INTO FIRED_UP
# (state[t] == 'FIRED_UP' AND state[t-1] != 'FIRED_UP')
# Consecutive FIRED_UP bars = one episode; only the first bar fires.
# FIRED_DOWN is BANNED from the long study.
# ---------------------------------------------------------------------------


def _assess_one_ticker(args: tuple) -> list[dict]:
    """Worker function for parallel enumeration (module-level for pickling).

    Parameters
    ----------
    args : (ticker, df_bytes, panel_name, merged_cfg, cfg_key)
        df_bytes : bytes from df.to_parquet() for pickling safety.

    Returns
    -------
    list[dict] — rows to append (may be empty list).
    """
    import io
    ticker, df_bytes, panel_name, merged_cfg, cfg_key = args
    try:
        df = pd.read_parquet(io.BytesIO(df_bytes))
    except Exception:
        return []

    if df.empty or "close" not in df.columns:
        return []

    # Lazy import per-worker — avoids cross-process module state issues
    _repo_root = Path(__file__).resolve().parents[2]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
    from engine.vol_squeeze import assess_series  # noqa: PLC0415

    close  = df["close"]
    high   = df.get("high")   if "high"   in df.columns else None
    low    = df.get("low")    if "low"    in df.columns else None
    volume = df.get("volume") if "volume" in df.columns else None

    try:
        states = assess_series(close, high=high, low=low, volume=volume, cfg=merged_cfg)
    except TypeError:
        raise
    except Exception:
        return []

    if states.empty:
        return []

    state_arr = states["state"].values
    fired_dir_arr = states["fired_dir"].values if "fired_dir" in states.columns else None
    rows: list[dict] = []
    for t in range(len(state_arr)):
        if state_arr[t] != "FIRED_UP":
            continue
        if t > 0 and state_arr[t - 1] == "FIRED_UP":
            continue
        if fired_dir_arr is not None:
            if str(fired_dir_arr[t]) == "down":
                continue
        row_data = states.iloc[t]
        # Preserve tri-state: 1.0 (confirmed), 0.0 (present-but-below threshold),
        # NaN (volume absent — has_vol gate failed). Do NOT wrap in bool() which
        # collapses NaN→False and makes _build_volume_coverage_table's missing
        # bucket permanently zero.
        vc_raw = row_data.get("volume_confirmed")
        vc = float(vc_raw) if vc_raw is not None else float("nan")
        rows.append({
            "ticker":           ticker,
            "date":             states.index[t],
            "panel":            panel_name,
            "fired_dir":        str(row_data.get("fired_dir", "")),
            "volume_confirmed": vc,
            "days_compressed":  int(row_data.get("days_compressed", 0)),
            "bbwp":             float(row_data.get("bbwp", float("nan"))),
            "hv_pctile":        float(row_data.get("hv_pctile", float("nan"))),
            "coverage":         str(row_data.get("coverage", "close")),
            "cfg_key":          cfg_key,
        })
    return rows


def enumerate_sq_events(
    ohlcv_store: dict[str, pd.DataFrame],
    panel_name: str,
    cfg: dict | None = None,
    n_workers: int = 1,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Enumerate FIRED_UP onset events across a panel.

    Uses engine/vol_squeeze.assess_series with the given cfg (merged with DEFAULTS).
    One event per FIRED_UP episode onset (dedup consecutive FIRED_UP bars).
    FIRED_DOWN onsets are not collected (long-only study).

    Parameters
    ----------
    ohlcv_store : {ticker: DataFrame with at least 'close'; optionally 'high'/'low'/'volume'}.
    panel_name : str — label stamped on every event row.
    cfg : dict override merged with DEFAULTS_CFG.
    n_workers : int — number of parallel worker processes (1 = sequential).
        Capped at 3 per task-brief L2 law. Parallelises the O(n²) assess_series
        calls across tickers using ProcessPoolExecutor.
    cache_dir : optional override for the per-ticker event cache root (default:
        _DEFAULT_SSQ_CACHE_DIR). Set to None to disable caching entirely.
        On startup, tickers with a valid cache file are loaded and skipped;
        newly-computed tickers are written immediately after computation.
        Cache location is asserted outside the repo tree (no git-add risk).

    Returns
    -------
    DataFrame with columns: ticker, date, panel, fired_dir, volume_confirmed,
        days_compressed, bbwp, hv_pctile, coverage, cfg_key.
    Empty DataFrame (same columns) if no events found.
    """
    import io

    n_workers = max(1, min(n_workers, 3))  # cap at 3 per law

    merged_cfg = {**DEFAULTS_CFG, **(cfg or {})}
    cfg_key = "_".join(f"{k}{v}" for k, v in sorted((cfg or {}).items())) or "defaults"

    # ------------------------------------------------------------------
    # Checkpoint: resolve cache dir; load any previously-computed tickers.
    # cache_dir=None disables caching (tests and direct callers that opt out).
    # ------------------------------------------------------------------
    _cache_dir: Path | None = None
    if cache_dir is not None:
        try:
            _cache_dir = _get_event_cache_dir(panel_name, cfg_key, override=cache_dir)
        except Exception as exc:  # noqa: BLE001
            log.warning("enumerate_sq_events: cache dir unavailable (%s); proceeding without cache.", exc)

    rows: list[dict] = []
    cached_tickers: set[str] = set()

    if _cache_dir is not None:
        for ticker in list(ohlcv_store.keys()):
            cached = _load_ticker_cache(_cache_dir, ticker)
            if cached is not None:
                rows.extend(cached)
                cached_tickers.add(ticker)
        if cached_tickers:
            log.info(
                "enumerate_sq_events: panel=%s cfg=%s — loaded %d tickers from cache, "
                "%d remaining to compute",
                panel_name, cfg_key, len(cached_tickers), len(ohlcv_store) - len(cached_tickers),
            )

    # Serialize DataFrames to bytes for safe multiprocessing pickling.
    # This is necessary because pandas DataFrames with numpy arrays can have
    # reference-sharing issues across fork boundaries.
    task_args: list[tuple] = []
    skipped = 0
    for ticker, df in ohlcv_store.items():
        if ticker in cached_tickers:
            continue  # already loaded from cache
        if df.empty or "close" not in df.columns:
            skipped += 1
            continue
        try:
            buf = io.BytesIO()
            df.to_parquet(buf)
            task_args.append((ticker, buf.getvalue(), panel_name, merged_cfg, cfg_key))
        except Exception as exc:  # noqa: BLE001
            log.debug("serialize failed for %s: %s", ticker, exc)
            skipped += 1

    exceptions = 0

    if n_workers > 1 and len(task_args) > 10:
        log.info(
            "enumerate_sq_events: panel=%s cfg=%s — parallel dispatch %d tickers, %d workers",
            panel_name, cfg_key, len(task_args), n_workers,
        )
        # Collect results per-ticker so we can cache immediately after each completes.
        ticker_order = [args[0] for args in task_args]
        with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as pool:
            for ticker, ticker_rows in zip(
                ticker_order, pool.map(_assess_one_ticker, task_args, chunksize=4)
            ):
                rows.extend(ticker_rows)
                if _cache_dir is not None:
                    _save_ticker_cache(_cache_dir, ticker, ticker_rows)
    else:
        # Sequential path (n_workers==1 or small panels)
        from engine.vol_squeeze import assess_series

        for ticker, df_bytes, pname, mcfg, ckey in task_args:
            ticker_rows: list[dict] = []
            try:
                df = pd.read_parquet(io.BytesIO(df_bytes))
                close  = df["close"]
                high   = df.get("high")   if "high"   in df.columns else None
                low    = df.get("low")    if "low"    in df.columns else None
                volume = df.get("volume") if "volume" in df.columns else None
                states = assess_series(close, high=high, low=low, volume=volume, cfg=mcfg)
            except TypeError:
                raise
            except Exception as exc:  # noqa: BLE001
                exceptions += 1
                log.debug("assess_series exception for %s: %s", ticker, exc)
                if _cache_dir is not None:
                    _save_ticker_cache(_cache_dir, ticker, [])  # cache empty result to skip next time
                continue

            if not states.empty:
                state_arr = states["state"].values
                fired_dir_arr = states["fired_dir"].values if "fired_dir" in states.columns else None
                for t in range(len(state_arr)):
                    if state_arr[t] != "FIRED_UP":
                        continue
                    if t > 0 and state_arr[t - 1] == "FIRED_UP":
                        continue
                    if fired_dir_arr is not None and str(fired_dir_arr[t]) == "down":
                        continue
                    row_data = states.iloc[t]
                    # Preserve tri-state float (1.0/0.0/NaN) — do NOT bool()-coerce.
                    vc_raw = row_data.get("volume_confirmed")
                    vc = float(vc_raw) if vc_raw is not None else float("nan")
                    ticker_rows.append({
                        "ticker":           ticker,
                        "date":             states.index[t],
                        "panel":            pname,
                        "fired_dir":        str(row_data.get("fired_dir", "")),
                        "volume_confirmed": vc,
                        "days_compressed":  int(row_data.get("days_compressed", 0)),
                        "bbwp":             float(row_data.get("bbwp", float("nan"))),
                        "hv_pctile":        float(row_data.get("hv_pctile", float("nan"))),
                        "coverage":         str(row_data.get("coverage", "close")),
                        "cfg_key":          ckey,
                    })

            rows.extend(ticker_rows)
            if _cache_dir is not None:
                _save_ticker_cache(_cache_dir, ticker, ticker_rows)

    log.info(
        "enumerate_sq_events: panel=%s cfg=%s → %d FIRED_UP onsets "
        "(%d from cache, %d tickers skipped, %d exceptions)",
        panel_name, cfg_key, len(rows), len(cached_tickers), skipped, exceptions,
    )

    _COLS = [
        "ticker", "date", "panel", "fired_dir", "volume_confirmed",
        "days_compressed", "bbwp", "hv_pctile", "coverage", "cfg_key",
    ]
    if not rows:
        return pd.DataFrame(columns=_COLS)

    result = pd.DataFrame(rows)
    result["date"] = pd.to_datetime(result["date"])
    return result.sort_values(["ticker", "date"]).reset_index(drop=True)


def dedup_sq_events(events: pd.DataFrame) -> pd.DataFrame:
    """Dedup FIRED_UP events: one episode per (ticker, date).

    For the squeeze, consecutive FIRED_UP bars are already eliminated by the
    onset detection above (only the first bar of each FIRED_UP run is kept).
    This function ensures no duplicate (ticker, date) pairs remain (e.g., if
    multiple cfg_keys produce the same onset date — this pass keeps the defaults
    row preferentially, then the first by cfg_key).

    Returns deduplicated DataFrame; count logged.
    """
    if events.empty:
        return events
    # Sort: defaults first (cfg_key='defaults'), then alpha
    events = events.copy()
    events["_sort_cfg"] = (events["cfg_key"] != "defaults").astype(int)
    deduped = (
        events
        .sort_values(["ticker", "date", "_sort_cfg", "cfg_key"])
        .drop_duplicates(subset=["ticker", "date"], keep="first")
        .drop(columns=["_sort_cfg"])
        .reset_index(drop=True)
    )
    removed = len(events) - len(deduped)
    if removed > 0:
        log.info("dedup_sq_events: removed %d duplicate (ticker, date) rows", removed)
    return deduped


# ---------------------------------------------------------------------------
# Grade events via the harness (T+1 fill, both horizon classes)
# Reuses grade_fires and _prepare_binary_outcomes from W0.
# ---------------------------------------------------------------------------

def grade_sq_events(
    events: pd.DataFrame,
    ohlcv_store: dict[str, pd.DataFrame],
    sector_map: dict[str, str],
    panel: str,
) -> pd.DataFrame:
    """Grade FIRED_UP events via the program harness grader.

    Constructs a fires-format DataFrame and passes it to grade_fires
    from entry_strata_phase0 (T+1 fill, both horizon classes).

    Returns graded DataFrame with all forward metrics and outcome columns.
    """
    if events.empty:
        log.warning("grade_sq_events: no events to grade for panel=%s", panel)
        return pd.DataFrame()

    fires_df = pd.DataFrame({
        "ticker":     events["ticker"].values,
        "date":       events["date"].values,
        "tier":       "SSQ",
        "sub":        events["coverage"].values,
        "ticks":      0.0,
        "not_topped": True,
        "eligible":   True,
        "panel":      panel,
    })
    fires_df["sector"] = fires_df["ticker"].map(sector_map)

    closes = {t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns}

    graded = grade_fires(fires_df, closes)
    graded = _prepare_binary_outcomes(graded)
    graded["_date_ts"] = pd.to_datetime(graded["date"]).astype(np.int64)
    graded["era"]      = graded["date"].apply(_assign_era)

    # Attach squeeze-specific context columns by aligning on ticker+date
    # (grade_fires may filter rows; alignment avoids shape mismatch)
    ctx_cols = [
        "fired_dir", "volume_confirmed", "days_compressed",
        "bbwp", "hv_pctile", "coverage", "cfg_key",
        "in_washout_ctx", "cohort_frac", "in_coiled_ctx",
        "near_gate_fire", "min_gate_fire_dist_bars",
    ]
    available_ctx = [c for c in ctx_cols if c in events.columns]
    if available_ctx:
        events_ctx = events[["ticker", "date"] + available_ctx].copy()
        events_ctx["date"] = pd.to_datetime(events_ctx["date"])
        graded = graded.merge(events_ctx, on=["ticker", "date"], how="left")

    n_gradable = int(graded["gradable"].sum())
    log.info(
        "grade_sq_events: panel=%s → %d events, %d gradable (%.1f%%)",
        panel, len(graded), n_gradable, 100 * n_gradable / max(len(graded), 1),
    )
    return graded


# ---------------------------------------------------------------------------
# Species bar check — wraps check_species_bar_per_form from run_w2_sur.
# (L1 law: reuse verbatim; this is a thin adapter that passes the correct
# parameters for S-SQ, including the is_gatefire_form flag.)
# ---------------------------------------------------------------------------

def check_sq_species_bar(
    form_label: str,
    results: dict[str, Any],
    n_events: int,
    co_fire_share: float,
    coiled_fire_recall: float | None,
    sq_recall: float,
    is_gatefire_form: bool = False,
    nc2_marginality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Thin wrapper around check_species_bar_per_form for S-SQ.

    Passes through to the shared machinery verbatim (L1 law).
    The gatefire form independence is N/A-structural (same as S-UR).
    """
    return check_species_bar_per_form(
        form_label=form_label,
        results=results,
        n_events=n_events,
        co_fire_share=co_fire_share,
        coiled_fire_recall=coiled_fire_recall,
        ur_recall=sq_recall,          # same parameter: candidate recall
        is_gatefire_form=is_gatefire_form,
        nc2_marginality=nc2_marginality,
    )


# ---------------------------------------------------------------------------
# Register S16 in species registry (idempotent; called once at script start)
# ---------------------------------------------------------------------------

def register_s16_species() -> None:
    """Register S16 Squeeze Release in data/species/registry.json (idempotent).

    Verifies S14 and S15 are taken before registering S16.
    Per RUL-5: registry before study.
    """
    from engine import species_registry as sr

    reg  = sr.load()
    taken = {e["species_id"] for e in reg.get("species", [])}

    if "S14" not in taken:
        log.warning("S14 not found in registry — expected 'Failed breakout'. Proceeding.")
    if "S15" not in taken:
        log.warning("S15 not found in registry — expected 'Spring Reclaim'. Proceeding.")

    if "S16" in taken:
        s16 = sr.get_species(reg, "S16")
        log.info(
            "S16 already registered: %s | %s",
            s16.get("name"), s16.get("validation_status"),
        )
        return  # idempotent

    s16_entry: dict[str, Any] = {
        "species_id": "S16",
        "version": "1.0",
        "name": "Squeeze Release",
        "horizon_class": "rotational",
        "validation_status": "phase0",
        "deployment_status": "unshipped",
        "mechanism": (
            "Multi-week volatility compression ends with a direction-and-volume-confirmed "
            "release bar (FIRED_UP state from engine/vol_squeeze.assess_series). "
            "The release bar — not the quiet base — is the event. "
            "Requires dual BBWP+HVP percentile gate, min_duration>=5 bars compression, "
            "directional break of the squeeze box within release_window bars, "
            "and vol_confirm=1.3x average volume confirmation. "
            "Fidelity-pinned to engine/vol_squeeze.DEFAULTS (pctile_thresh=25, "
            "min_duration=5, release_window=3, vol_confirm=1.3)."
        ),
        "adjacent_falsified": (
            "H2 aged-quiet-base/calm-VCP arming (SETUP_SPECIES section 1.6; "
            "calm-base anticipatory arming showed worst stop-outs 46-48%). "
            "Mechanical difference: S16 acts ONLY on the confirmed release bar with "
            "direction + 1.3x volume confirmation — confirmation vs anticipation. "
            "An arming variant is BANNED from this family per masterplan section 9. "
            "Context kill: trend/location guards (falsified as exposure artifacts); "
            "volume-confirmation confirmers (H4, dead)."
        ),
        "evidence_stack": {
            "phase0_study": "research/entry_stack/W2_SSQ_REPORT.md",
            "harness": "scripts/research/run_w2_ssq.py",
            "engine": "engine/vol_squeeze.assess_series (FIRED_UP state onsets)",
            "panels": (
                "deep (H/L available) + baskets (H/L available); "
                "delisted NOT APPLICABLE (needs H/L)"
            ),
            "grader": "engine/grading (RUL-9)",
            "design": (
                "R1 date-FE stratified difference; episode-block bootstrap; "
                "BH q<=0.10 family esx_sq_phase0; RUL-13 primary horizons 21d; "
                "RUL-14 co-primaries zone_held_21/stop_vol_21"
            ),
        },
        "rejection_rules": [
            "FIRED_DOWN onsets are BANNED from the long study",
            "An arming variant (entering during COILED/COMPRESSED) is BANNED from this family",
            "Event = first bar of FIRED_UP state (dedup consecutive FIRED_UP bars)",
            "Needs H/L: delisted close-only panel NOT APPLICABLE",
        ],
        "archetype_scope": {
            "primary": "US",
            "excluded": ["HK", "CA"],
            "cn_note": "CN secondary only if species pre-registers its own CN test (not in phase0)",
        },
        "regime_scope": {
            "learnable_projection": "vol_regime x horizon (engine x horizon cells)",
            "note": (
                "Squeeze release is directionally agnostic until release bar — "
                "regime provides context"
            ),
        },
        "market_scope": (
            "US primary; deep panel (224 names 64y) + baskets panel (2519 names 2014+)"
        ),
        "fixtures": (
            "tests/test_run_w2_ssq.py (event-onset dedup fixture; direction fixture: "
            "FIRED_DOWN never enters long study; injected-effect marginality test)"
        ),
        "ledger_binding": {
            "ledger": "data/trial_ledger.jsonl",
            "since": "2026-07-05",
            "flip_criteria": {
                "stop5":             "stop-out within 5 bars of T+1 fill",
                "fwd_mdd_21":        "max adverse excursion 21d (RUL-13 primary)",
                "rotational_liftoff":"clean8_21 (1.08/21d) rotational liftoff",
                "zone_held_21":      "vol-scaled zone held at 21d (RUL-14 co-primary)",
                "dead_money":        "dead-money outcome",
                "cushion_rot":       "cushion incidence rotational",
            },
        },
        "gating": {
            "come_back_on": "monthly review after phase0 report adjudication",
            "cadence": "monthly",
            "maturation": "phase0 → accruing after adjudication sign-off",
        },
        "trial_count": 12,
    }

    reg = sr.upsert_species(reg, s16_entry)
    sr.save(reg)
    log.info("S16 Squeeze Release registered in data/species/registry.json")


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    lines: list[str],
    *,
    panel_results: dict[str, Any],
    per_form_species_bars: dict[str, dict[str, Any]],
    coiled_fire_recall_note: str,
    nc2_note: str,
    delisted_status: str,
    smoke: bool = False,
    aggregate_cofire_share: float,
    primary_sa_cofire_share: float,
    primary_sa_cofire_n: int,
    primary_coiled_cofire_share: float,
    primary_gf_cofire_share: float,
    primary_gf_cofire_n: int,
    n_deep_events: int,
    n_baskets_events: int,
    volume_coverage: dict[str, dict[str, int]] | None = None,
    spot_check_results: dict[str, dict[str, Any]] | None = None,
    sensitivity_results: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Write the W2 S-SQ phase-0 report in markdown."""

    lines.append("# W2 Squeeze Release (S-SQ) Phase-0 Report — Entry-Stack Expansion")
    lines.append("")
    lines.append("**Status:** W2 study report only — no promotion decision (RUL-3).")
    lines.append("**Date:** 2026-07-05")
    lines.append(f"**Species:** {SPECIES_ID} — {SPECIES_NAME}, horizon_class=rotational, phase0.")
    lines.append(
        "**Species note:** S14=Failed breakout, S15=Spring Reclaim are taken on origin/main. "
        "Squeeze Release uses S16 (next free number, verified at registration)."
    )
    lines.append(f"**Family:** {SPECIES_FAMILY} (budget=12).")
    lines.append("")

    if smoke:
        lines.append(
            "> **WARNING: SMOKE RUN** — reduced bootstrap resamples; "
            "do NOT use for adjudication. Rerun without --smoke for production."
        )
        lines.append("")

    # Honest headline
    lines.append("## HEADLINE — Per-Form Honest Verdict")
    lines.append("")
    lines.append("**Sign convention:** stop5 is an ADVERSE outcome. MORE POSITIVE coefficient = MORE stops (WORSE).")
    lines.append("Non-inferiority = CI upper bound < +0.01. Superiority on stop5 = CI upper bound < 0.0.")
    lines.append("")
    lines.append("**Per-form primary results (deep panel, defaults cfg) — ALL NUMBERS FROM THIS RUN:**")
    lines.append("")
    lines.append(
        "| Form | stop5 coef | 95% CI_hi | Non-inferior (CI_hi<+0.01)? "
        "| Superior (CI_hi<0)? | Independence (co-fire<=60%) | zone_held_21 coef (context) |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for form_key, sb in per_form_species_bars.items():
        if not isinstance(sb, dict):
            continue
        coef = _fmt_f(sb.get("stop5_coef"), 4)
        ci_hi = sb.get("stop5_ci_hi")
        ni = (
            "NO" if sb.get("stop5_noninferiority_met") is False
            else ("YES" if sb.get("stop5_noninferiority_met") else "N/A")
        )
        if sb.get("superiority_met_nc2_nullified"):
            sup = "NO (NC-2 nullified)"
        else:
            sup = (
                "NO" if sb.get("stop5_superiority_met") is False
                else ("YES" if sb.get("stop5_superiority_met") else "N/A")
            )
        if sb.get("independence_structural_na"):
            indep = "N/A-STRUCTURAL"
        else:
            indep = (
                "FAIL" if sb.get("independence_clause_met") is False
                else ("PASS" if sb.get("independence_clause_met") else "N/A")
            )
        cofshare = f"{sb.get('co_fire_share', 0.0):.1%}"
        z_coef = _fmt_f(sb.get("zone_held_21_coef"), 4)
        lines.append(
            f"| {form_key} | {coef} | {_fmt_f(ci_hi, 4)} | {ni} | {sup} "
            f"| {indep} ({cofshare}) | {z_coef} |"
        )
    lines.append("")
    lines.append(
        "**Adjacency (R2 per RUL-2):** H2 aged-quiet-base arming is the nearest falsified relative. "
        "S16 acts ONLY on the confirmed FIRED_UP release bar (direction + vol confirmed) — "
        "confirmation vs anticipation. An arming variant is BANNED from this family. "
        "This distinction must hold empirically or the species fails."
    )
    lines.append("")
    lines.append("**HONEST FINDING (AS MEASURED IN THIS RUN):** See per-form species bar summary below.")
    lines.append("Nulls and kills printed with equal care as wins.")
    lines.append("**Adjudication belongs to the orchestrator, not this study.**")
    lines.append("")

    # NC yardstick (RUL-3 mandatory preamble) — parsed at runtime
    lines.append("## NC Yardstick (RUL-3 mandatory preamble)")
    lines.append("")
    lines.append("**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).")
    lines.append("Numbers below are parsed from that file at runtime — NOT hardcoded.")
    lines.append("Per masterplan §10 RUL-3: null-competitors appear as the first table.")
    lines.append("Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.")
    lines.append(
        "The S-SQ candidate 'beats NC-2' only if its stop5 coefficient retains CI-excluding-0 "
        "AFTER entry_quality-band fixed effects (tested for gatefire form; see NC-2 Marginality below)."
    )
    lines.append("")
    yardstick_rows = _parse_nc_yardstick_from_report()
    if yardstick_rows:
        lines.append("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |")
        lines.append("|---|---|---|---|---|---|")
        for row in yardstick_rows:
            lines.append(
                f"| {row['panel']} | {row['nc']} | {row['coef']} "
                f"| {row['ci']} | {row['excl0']} | {row['recall']} |"
            )
    else:
        lines.append(
            "> **W1_NC_REPORT.md NOT FOUND** — NC yardstick unavailable. "
            "Run `python scripts/research/run_w1_nc.py` first."
        )
    lines.append("")
    lines.append(f"NC-2 proximity note: {nc2_note}")
    lines.append("")

    # COILED-FIRE recall note
    lines.append("## COILED-FIRE Recall Clause Note")
    lines.append("")
    lines.append(coiled_fire_recall_note)
    lines.append("")

    # Independence clause per form
    lines.append("## Independence Clause (Per-Form Co-Fire Shares)")
    lines.append("")
    lines.append("Per-form co-fire shares at +/-3 TRUE TRADING BARS (deep panel, defaults cfg):")
    lines.append("Co-fire computed on each form's OWN event subset (L1 law: same as S-UR).")
    lines.append("")
    lines.append("| Form | Co-fire share | n near | Independence clause (<=60%) |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| standalone | {primary_sa_cofire_share:.1%} | {primary_sa_cofire_n} "
        f"| {'PASS' if primary_sa_cofire_share <= MAX_COFIRE_SHARE else 'FAIL'} |"
    )
    lines.append(
        f"| COILED-intersection | {primary_coiled_cofire_share:.1%} | — "
        f"| {'PASS' if primary_coiled_cofire_share <= MAX_COFIRE_SHARE else 'FAIL'} |"
    )
    lines.append(
        f"| gatefire-proximity | {primary_gf_cofire_share:.1%} | {primary_gf_cofire_n} "
        f"| N/A-STRUCTURAL |"
    )
    lines.append("")
    lines.append(
        "**DESIGN NOTE — GATEFIRE FORM INDEPENDENCE IS N/A-STRUCTURAL:** "
        "The gatefire form selects S-SQ events WITHIN ±5 BARS of gate fires (form definition). "
        "It is structurally gate-dependent. The ±3-bar co-fire check uses a tighter radius. "
        "Verdict: N/A-STRUCTURAL (same reasoning as S-UR gatefire form)."
    )
    lines.append("")
    lines.append(f"Aggregate co-fire share (standalone forms): {aggregate_cofire_share:.1%}")
    lines.append(f"Independence clause threshold: <= {MAX_COFIRE_SHARE:.0%}")
    lines.append("")

    # DELISTED ARM: NOT APPLICABLE
    lines.append("## Delisted Panel Status")
    lines.append("")
    lines.append(delisted_status)
    lines.append("")

    # Volume coverage table (BLOCKER FIX: per task brief)
    lines.append("## Volume Coverage Table (Mechanism-Faithful Events)")
    lines.append("")
    lines.append(
        "**BLOCKER FIX:** The prior loaders dropped `volume`, leaving "
        "`vol_ok=None` in `assess()` so every FIRED_UP fired on price break ALONE. "
        "This table verifies the fix: volume must be present and `volume_confirmed` "
        "must be True/False (never NaN) on all OHLCV names."
    )
    lines.append("")
    lines.append(
        "**Mechanism-faithful set** = events with `volume_confirmed == True`. "
        "Events with `volume_confirmed == False` are volume-ABSENT or below threshold. "
        "Events with `volume_confirmed` missing (NaN) indicate tickers without volume "
        "in the raw store — these are excluded from the mechanism-faithful count. "
        "Per task brief: 'if any names genuinely lack volume, exclude their events "
        "from the mechanism-faithful set with counts printed.'"
    )
    lines.append("")
    if spot_check_results:
        lines.append("### Spot-Check: Volume Loading Verification (AAPL + 3 sampled names)")
        lines.append("")
        lines.append("| Panel | Ticker | has_volume | n_rows | vol_nonzero | vol_null |")
        lines.append("|---|---|---|---|---|---|")
        for panel_sc, sc_data in spot_check_results.items():
            for ticker, info in sc_data.get("sample_results", {}).items():
                vol_null_str = str(info.get("vol_null", "—"))
                lines.append(
                    f"| {panel_sc} | {ticker} | {info['has_volume']} "
                    f"| {info['n_rows']} | {info['vol_nonzero']} | {vol_null_str} |"
                )
        lines.append("")
    if volume_coverage:
        lines.append("### Per-Panel Volume-Confirmed Summary (defaults cfg events)")
        lines.append("")
        lines.append(
            "| Panel | Total events | volume_confirmed=True | "
            "volume_confirmed=False | volume_confirmed=NaN (missing) | "
            "% mechanism-faithful |"
        )
        lines.append("|---|---|---|---|---|---|")
        for panel_vc, vc in volume_coverage.items():
            total         = vc.get("total", 0)
            confirmed     = vc.get("confirmed", 0)
            not_confirmed = vc.get("not_confirmed", 0)
            missing       = vc.get("missing", 0)
            pct_faithful  = f"{confirmed / max(total, 1):.1%}"
            lines.append(
                f"| {panel_vc} | {total} | {confirmed} "
                f"| {not_confirmed} | {missing} | {pct_faithful} |"
            )
        lines.append("")
        lines.append(
            "> **volume_confirmed=True** = direction break AND vol >= 1.3x 20d avg "
            "(the S16 mechanism definition). "
            "**volume_confirmed=False** = price broke the squeeze box but volume was "
            "below the 1.3x threshold — price-break-only, not mechanism-faithful. "
            "The species bar uses ALL FIRED_UP events (the registered event set); "
            "the mechanism-faithful fraction is a diagnostic."
        )
    else:
        lines.append("> *Volume coverage data not available (run with volume-carrying loaders).*")
    lines.append("")

    # BH correction scope
    lines.append("## BH Correction Scope")
    lines.append("")
    lines.append(f"Family-wide BH: one BH pass pooling ALL cells x forms x outcomes of {SPECIES_FAMILY}.")
    lines.append(
        "Pool includes defaults + all 3 named sensitivities (pctile20, relwin2, volconf15) "
        "× all forms × all panels. "
        "Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and days_to_10 (collider)."
    )
    lines.append(f"BH q <= {BH_Q_THRESHOLD} threshold applied to all pooled cells.")
    lines.append("")

    # Event counts
    lines.append("## Event Counts")
    lines.append("")
    lines.append(f"- Deep panel FIRED_UP onsets (defaults cfg): {n_deep_events}")
    lines.append(f"- Baskets panel FIRED_UP onsets (defaults cfg): {n_baskets_events}")
    lines.append("")

    # Sensitivity results summary
    if sensitivity_results:
        lines.append("## Sensitivity Analysis (Registered 12-Trial Budget)")
        lines.append("")
        lines.append(
            "Per masterplan §5 trial-ledger: `esx_sq_phase0` budget=12 covers "
            "'frozen state grid × 2 panels × 3 forms + 3 named sensitivities "
            "(pctile_thresh=20; release_window=2; vol_confirm=1.5)'. "
            "Each sensitivity is enumerated, graded, and analyzed independently. "
            "volconf15 is now meaningful with volume flowing (BLOCKER FIX applied)."
        )
        lines.append("")
        lines.append("| Sensitivity | Panel | n_events | stop5 coef (standalone) | 95% CI_hi | BH rej? |")
        lines.append("|---|---|---|---|---|---|")
        for sens_key, sens_data in sensitivity_results.items():
            for panel_s in ["deep", "baskets"]:
                pd_sens = sens_data.get(panel_s, {})
                n_ev    = pd_sens.get("n_events", "—")
                sa_eff  = pd_sens.get("standalone_effects", [])
                s5_eff  = next((e for e in sa_eff if e.get("outcome") == "stop5"), None)
                if s5_eff:
                    coef_s   = _fmt_f(s5_eff.get("coef"), 4)
                    ci_hi_s  = _fmt_f(s5_eff.get("ci_hi"), 4)
                    bh_rej_s = "YES" if s5_eff.get("bh_rejected_family") else "no"
                else:
                    coef_s  = "—"
                    ci_hi_s = "—"
                    bh_rej_s = "—"
                lines.append(
                    f"| {sens_key} | {panel_s} | {n_ev} | {coef_s} | {ci_hi_s} | {bh_rej_s} |"
                )
        lines.append("")
        for sens_key, sens_data in sensitivity_results.items():
            lines.append(f"### Sensitivity: {sens_key}")
            lines.append("")
            cfg_override = SENSITIVITY_CONFIGS.get(sens_key, {})
            merged = {**DEFAULTS_CFG, **cfg_override}
            lines.append(f"Config override vs defaults: `{cfg_override}`")
            lines.append(f"Merged cfg: pctile_thresh={merged['pctile_thresh']}, "
                         f"min_duration={merged['min_duration']}, "
                         f"release_window={merged['release_window']}, "
                         f"vol_confirm={merged['vol_confirm']}")
            lines.append("")
            for panel_s in ["deep", "baskets"]:
                pd_sens = sens_data.get(panel_s, {})
                if not pd_sens:
                    lines.append(f"**Panel {panel_s}:** not run.")
                    continue
                lines.append(f"**Panel {panel_s}:**")
                lines.append(f"- FIRED_UP onsets: {pd_sens.get('n_events', 0)}")
                sa_eff = pd_sens.get("standalone_effects", [])
                if sa_eff:
                    lines.append("  Effect table (standalone form, R1 FE):")
                    lines.append("")
                    lines.append(
                        "  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |"
                    )
                    lines.append("  |---|---|---|---|---|---|")
                    for e in sa_eff:
                        outcome_s = e.get("outcome", "—")
                        coef_s    = _fmt_f(e.get("coef"), 4)
                        ci_s      = _ci_str(e)
                        pv_s      = _fmt_f(e.get("p_value"), 4)
                        bh_q_s    = _fmt_f(e.get("bh_q_family"), 4)
                        rej_s     = "YES" if e.get("bh_rejected_family") else "no"
                        lines.append(
                            f"  | {outcome_s} | {coef_s} | {ci_s} | {pv_s} | {bh_q_s} | {rej_s} |"
                        )
                    lines.append("")
                else:
                    lines.append("  *No gradable events for this sensitivity/panel.*")
                    lines.append("")
            lines.append("")
    else:
        lines.append("## Sensitivity Analysis")
        lines.append("")
        lines.append("> *Sensitivity results not available.*")
        lines.append("")

    # Per-form species bar summary
    lines.append("## Per-Form Species Bar Summary (no cross-form cherry-picking)")
    lines.append("")
    lines.append("Per masterplan §5: each form evaluated independently.")
    lines.append("NO promotion decision made in this report (RUL-3).")
    lines.append("")
    for form_key, sb in per_form_species_bars.items():
        if not isinstance(sb, dict):
            continue
        lines.append(f"### Species Bar: {form_key}")
        lines.append("")
        lines.append("| Clause | Value | Met? |")
        lines.append("|---|---|---|")

        def _yn(v: bool | None) -> str:
            if v is True:  return "YES"
            if v is False: return "NO"
            return "DEFERRED"

        lines.append(f"| n_events >= 150 | {sb.get('n_events', 0)} | {_yn(sb.get('n_met'))} |")
        ci_hi_str = f"{sb.get('stop5_ci_hi'):.4f}" if sb.get("stop5_ci_hi") is not None else "—"
        coef_str  = f"{sb.get('stop5_coef'):.4f}" if sb.get("stop5_coef") is not None else "—"
        lines.append(
            f"| Stop5 non-inferiority (CI_hi < +0.01) | coef={coef_str} CI_hi={ci_hi_str} "
            f"| {_yn(sb.get('stop5_noninferiority_met'))} |"
        )
        sup5_verdict = _yn(sb.get("stop5_superiority_met"))
        if sb.get("superiority_met_nc2_nullified"):
            sup5_verdict = "NO (NC-2 nullified: CI includes 0 after proximity band FE)"
        lines.append(f"| Stop5 superiority (CI_hi < 0) | CI_hi={ci_hi_str} | {sup5_verdict} |")
        sup_axes = sb.get("superiority_axes", [])
        sup_overall_verdict = _yn(sb.get("superiority_met"))
        if sb.get("superiority_met_nc2_nullified"):
            sup_overall_verdict = "NO (NC-2 nullified: gatefire stop5 CI includes 0 after proximity de-confounding)"
        lines.append(
            f"| Superiority CI-excl-0 on >=1 constitution axis | "
            f"{sup_axes if sup_axes else 'none'} | {sup_overall_verdict} |"
        )
        era_stable = sb.get("era_sign_stable")
        era_str = (
            "YES (>=3/4 eras)" if era_stable is True
            else ("NO (<3/4 eras)" if era_stable is False else "INSUFFICIENT DATA")
        )
        lines.append(
            f"| Era sign-stability (>=3/4 eras) | {era_str} | {_yn(sb.get('era_sign_stable_met'))} |"
        )
        sq_recall_str = f"{sb.get('recall_ur', 0):.1%}"
        recall_thresh = sb.get("recall_clause_threshold")
        recall_thresh_str = f"{recall_thresh:.1%}" if recall_thresh is not None else "DEFERRED"
        lines.append(
            f"| Recall clause (>= half COILED-FIRE recall) | S-SQ proxy (treatment-share-of-pool)={sq_recall_str} threshold={recall_thresh_str} "
            f"| {_yn(sb.get('recall_clause_met'))} |"
        )
        cofire_str = f"{sb.get('co_fire_share', 1.0):.1%}"
        if sb.get("independence_structural_na"):
            indep_verdict = "N/A (structurally gate-dependent: form defined by gate-fire proximity)"
        else:
            indep_verdict = _yn(sb.get("independence_clause_met"))
        lines.append(
            f"| Independence clause (co-fire <= 60% at ±3 bars) | {cofire_str} | {indep_verdict} |"
        )
        z_coef = sb.get("zone_held_21_coef")
        z_lo   = sb.get("zone_held_21_ci_lo")
        z_hi   = sb.get("zone_held_21_ci_hi")
        if z_coef is not None:
            lines.append(
                f"| zone_held_21 (ADJUDICATION CONTEXT, no clause) | "
                f"coef={z_coef:.4f} CI=[{z_lo:.4f},{z_hi:.4f}] | — |"
            )
        lines.append("")
        if sb.get("recall_clause_note"):
            lines.append(f"> **RECALL CLAUSE NOTE:** {sb['recall_clause_note']}")
            lines.append("")
        lines.append(
            "> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program "
            "constitution; feeds no clause in this study; informs whether fixed −5% stop "
            "mismeasures high-vol washout entries."
        )
        lines.append("")

    # Per-panel per-form results
    for panel_label, panel_data in panel_results.items():
        lines.append(f"## Panel: {panel_label}")
        lines.append("")
        survivor_msg = panel_data.get("survivor_stamp", "")
        if survivor_msg:
            lines.append(f"**SURVIVOR BIAS STAMP:** {survivor_msg}")
            lines.append("")

        for form_label, form_data in panel_data.get("forms", {}).items():
            lines.append(f"### Form: {form_label}")
            lines.append("")

            n_events  = form_data.get("n_events_total", 0)
            n_deduped = form_data.get("n_events_deduped", 0)
            n_gradable = form_data.get("n_gradable", 0)
            n_treat   = form_data.get("n_treatment", 0)
            n_ctrl    = form_data.get("n_control", 0)

            lines.append(f"- Total FIRED_UP onsets: {n_events}")
            lines.append(f"- Deduped episodes: {n_deduped}")
            lines.append(f"- Gradable: {n_gradable}")
            lines.append(f"- N treatment: {n_treat} | N control: {n_ctrl}")
            if n_treat > 0 and (n_treat + n_ctrl) > 0:
                recall = n_treat / (n_treat + n_ctrl)
                lines.append(f"- Recall (treatment / all): {recall:.1%}")

            if form_data.get("skipped"):
                lines.append(f"- **SKIPPED:** {form_data.get('skip_reason', '')}")
                lines.append("")
                continue

            effects = form_data.get("effects", [])
            if effects:
                lines.append("")
                lines.append("#### Effect Table (R1 FE, fast block bootstrap)")
                lines.append("")
                lines.append(
                    "**zone_held_21:** vol-scaled band held over fill+1..+21. "
                    "ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop "
                    "mismeasures high-vol washout entries (RUL-14 rationale)."
                )
                lines.append("")
                lines.append(
                    "| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |"
                )
                lines.append("|---|---|---|---|---|---|---|---|")
                for e in effects:
                    outcome    = e.get("outcome", "—")
                    coef       = _fmt_f(e.get("coef"), 4)
                    ci         = _ci_str(e)
                    naive      = _fmt_f(e.get("naive_diff"), 4)
                    pv         = _fmt_f(e.get("p_value"), 4)
                    bh_q       = _fmt_f(e.get("bh_q_family"), 4)
                    rej        = "YES" if e.get("bh_rejected_family") else "no"
                    excl       = " *" if _excl_zero(e) == "YES *" else ""
                    recall_str = _fmt_f(e.get("recall"), 3)
                    lines.append(
                        f"| {outcome} | {coef} | {ci}{excl} | {naive} | {pv} "
                        f"| {bh_q} | {rej} | {recall_str} |"
                    )
            else:
                lines.append("")
                lines.append("*No gradable events for this form.*")

            # Era table
            era_tbl = form_data.get("era_table")
            era_stable = form_data.get("era_sign_stable")
            if era_tbl is not None and not era_tbl.empty:
                lines.append("")
                lines.append("#### Era table (stop5 rate by stratum, program eras)")
                era_stable_str = (
                    "**YES (>=3/4 eras sign-stable)**" if era_stable is True
                    else ("**NO (<3/4 eras)**" if era_stable is False else "**INSUFFICIENT DATA**")
                )
                lines.append(f"Era sign-stability clause: {era_stable_str}")
                lines.append("")
                era_cols = ["era"] + [c for c in era_tbl.columns if c != "era"]
                lines.append("| " + " | ".join(era_cols) + " |")
                lines.append("|" + "|".join(["---"] * len(era_cols)) + "|")
                for _, erow in era_tbl.iterrows():
                    row_vals = []
                    for c in era_cols:
                        v = erow[c]
                        if c.endswith("_rate"):
                            row_vals.append(f"{float(v):.1%}" if pd.notna(v) else "—")
                        elif c.endswith("_mean"):
                            row_vals.append(f"{float(v):.4f}" if pd.notna(v) else "—")
                        elif c == "n_fires":
                            row_vals.append(str(int(v)) if pd.notna(v) else "—")
                        elif isinstance(v, float):
                            row_vals.append(f"{v:.1f}" if pd.notna(v) else "—")
                        else:
                            row_vals.append(str(v))
                    lines.append("| " + " | ".join(row_vals) + " |")

            # NC-2 marginality (gatefire form)
            nc2 = form_data.get("nc2_marginality")
            if nc2 is not None and nc2.get("band_computed"):
                lines.append("")
                lines.append("#### NC-2 Marginality (gatefire-proximity form only)")
                lines.append("")
                lines.append(
                    "Proximity confounding test: NC-2 proximity-band FE added to stop5 R1 model."
                )
                coef = _fmt_f(nc2.get("coef"), 4)
                ci_lo = _fmt_f(nc2.get("ci_lo"), 4)
                ci_hi_nc2 = _fmt_f(nc2.get("ci_hi"), 4)
                excl = "YES *" if nc2.get("ci_excl_zero") else "no"
                lines.append(f"- stop5 coef with NC-2 band FE: {coef} CI=[{ci_lo}, {ci_hi_nc2}] CI-excl-0: {excl}")
                lines.append(f"- N treatment with computable proximity: {nc2.get('n_treatment_nc2', '—')}")
                lines.append(f"- Note: {nc2.get('note', '—')}")
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by `scripts/research/run_w2_ssq.py`*")
    lines.append(f"*Species: {SPECIES_ID} — {SPECIES_NAME}*")
    lines.append(f"*Grader: engine/grading.py (program barriers, RUL-9).*")
    lines.append("*'validated' word deliberately absent (CI-enforced).*")
    lines.append("*No promotion language. Studies only.*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main study driver
# ---------------------------------------------------------------------------

def run_study(
    panels: list[str],
    n_bootstrap: int = N_BOOTSTRAP,
    smoke: bool = False,
    out_path: Path | None = None,
    n_workers: int = 1,
    cache_dir: Path | None = None,
) -> None:
    """Run the full S-SQ phase-0 study.

    ORDER (RUL-5):
      1. Register S16 species (idempotent)
      2. Verify family ledger (esx_sq_phase0 already declared at W0)
      3. Enumerate FIRED_UP onsets, grade, analyze, write report

    Parameters
    ----------
    panels : list of panel names to include {'deep', 'baskets'}
    n_bootstrap : bootstrap resamples (>=1000 for production per masterplan L2)
    smoke : if True, use reduced data (for fast CI checks, NOT for adjudication)
    out_path : output path for the report (defaults to research/entry_stack/W2_SSQ_REPORT.md)
    n_workers : parallel workers for enumerate_sq_events (capped at 3 per L2 law)
    cache_dir : optional root dir for per-ticker event cache (default: _DEFAULT_SSQ_CACHE_DIR).
        Passed through to enumerate_sq_events. Must be outside the repo tree.
    """
    if smoke:
        log.warning("SMOKE MODE: reduced dataset. NOT suitable for adjudication (L2 law).")
        n_bootstrap = max(n_bootstrap, 50)

    # Resolve cache dir: None means "use production default".
    # enumerate_sq_events treats None as "no caching"; run_study always enables the cache.
    _effective_cache_dir: Path = cache_dir if cache_dir is not None else _DEFAULT_SSQ_CACHE_DIR
    log.info("Enumeration cache dir: %s", _effective_cache_dir)

    # Step 1: Registry (RUL-5)
    register_s16_species()

    # Step 2: Verify ledger — esx_sq_phase0 should already be declared (pre-registered at W0).
    # Per task brief (L4): only our family rows in ledger; do NOT call _register_all_families
    # (that would add foreign families). Just verify esx_sq_phase0 is present.
    import json
    ledger_found = False
    if _LEDGER_PATH.exists():
        with open(_LEDGER_PATH) as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("family") == SPECIES_FAMILY:
                        ledger_found = True
                        break
                except json.JSONDecodeError:
                    pass
    if ledger_found:
        log.info("Trial ledger: %s already declared (budget=12 from W0).", SPECIES_FAMILY)
    else:
        log.warning(
            "Trial ledger: %s NOT FOUND. Expected pre-declaration at W0. "
            "Run entry_strata_phase0._register_all_families() first.",
            SPECIES_FAMILY,
        )

    # Step 3: Load NC yardstick early (RUL-3 — parsed at runtime, never hardcoded)
    nc_yardstick_rows = _parse_nc_yardstick_from_report()
    if not nc_yardstick_rows:
        log.warning("W1_NC_REPORT.md not found — NC yardstick will be blank in report.")

    # Step 4: Build sector map
    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    # Step 5: Load panels — USE VOLUME-CARRYING LOADERS (BLOCKER FIX)
    # S-SQ uses its own volume-aware loaders (not the shared S-UR loaders which
    # drop volume). See _load_deep_ohlcv_volume/_load_baskets_ohlcv_volume docstrings
    # for the design-choice rationale.
    panel_data_stores: dict[str, dict[str, pd.DataFrame]] = {}
    gate_fires_stores: dict[str, pd.DataFrame | None] = {}
    spot_check_results: dict[str, dict[str, Any]] = {}

    if "deep" in panels:
        log.info("Loading deep OHLCV+volume panel (BLOCKER FIX: volume-carrying loader)...")
        deep_store = _load_deep_ohlcv_volume()
        panel_data_stores["deep"] = deep_store
        spot_check_results["deep"] = _spot_check_volume_loading(deep_store, "deep")
        log.info(
            "Deep volume spot-check: %d/%d tickers have volume",
            spot_check_results["deep"]["n_with_volume"],
            spot_check_results["deep"]["n_total"],
        )
        if _FIRES_DEEP.exists():
            gate_fires_stores["deep"] = pd.read_parquet(_FIRES_DEEP)
            log.info("Loaded gate_fires_deep.parquet: %d rows", len(gate_fires_stores["deep"]))
        else:
            gate_fires_stores["deep"] = None
            log.warning("gate_fires_deep.parquet not found — gatefire form will be skipped for deep")

    if "baskets" in panels:
        log.info("Loading baskets OHLCV+volume panel (BLOCKER FIX: volume-carrying loader)...")
        baskets_store = _load_baskets_ohlcv_volume()
        panel_data_stores["baskets"] = baskets_store
        spot_check_results["baskets"] = _spot_check_volume_loading(baskets_store, "baskets")
        log.info(
            "Baskets volume spot-check: %d/%d tickers have volume",
            spot_check_results["baskets"]["n_with_volume"],
            spot_check_results["baskets"]["n_total"],
        )
        if _FIRES_BASKETS.exists():
            gate_fires_stores["baskets"] = pd.read_parquet(_FIRES_BASKETS)
            log.info("Loaded gate_fires_baskets.parquet: %d rows", len(gate_fires_stores["baskets"]))
        else:
            gate_fires_stores["baskets"] = None
            log.warning("gate_fires_baskets.parquet not found — gatefire form will be skipped for baskets")

    # Step 6: Load the full gate fires (for ALL panels combined) as the R1 control set
    gate_fires_control: pd.DataFrame | None = None
    for pname in ["deep", "baskets"]:
        if pname in panels and gate_fires_stores.get(pname) is not None:
            gf = gate_fires_stores[pname]
            if gate_fires_control is None:
                gate_fires_control = gf.copy()
            else:
                gate_fires_control = pd.concat([gate_fires_control, gf], ignore_index=True)

    # Step 7: Enumerate FIRED_UP onsets per panel (defaults cfg) and per sensitivity.
    # BLOCKER FIX: volume now flows — assess_series receives volume= series, so
    # vol_ok is computed and volume_confirmed is True/False (never NaN) for OHLCV names.
    deep_events_default: pd.DataFrame = pd.DataFrame()
    baskets_events_default: pd.DataFrame = pd.DataFrame()

    # Sensitivity events: {sens_key: {panel: DataFrame}}
    sensitivity_events: dict[str, dict[str, pd.DataFrame]] = {
        k: {} for k in SENSITIVITY_CONFIGS
    }

    if "deep" in panels:
        log.info("Enumerating FIRED_UP onsets for deep panel (defaults cfg)...")
        deep_events_default = enumerate_sq_events(
            panel_data_stores["deep"], panel_name="deep", cfg=None, n_workers=n_workers,
            cache_dir=_effective_cache_dir,
        )
        log.info("Deep FIRED_UP onsets (defaults): %d", len(deep_events_default))

        for sens_key, cfg_override in SENSITIVITY_CONFIGS.items():
            log.info("Enumerating deep panel sensitivity=%s cfg=%s...", sens_key, cfg_override)
            sens_ev = enumerate_sq_events(
                panel_data_stores["deep"], panel_name="deep", cfg=cfg_override, n_workers=n_workers,
                cache_dir=_effective_cache_dir,
            )
            log.info("Deep FIRED_UP onsets (sensitivity=%s): %d", sens_key, len(sens_ev))
            sensitivity_events[sens_key]["deep"] = sens_ev

    if "baskets" in panels:
        log.info("Enumerating FIRED_UP onsets for baskets panel (defaults cfg)...")
        baskets_events_default = enumerate_sq_events(
            panel_data_stores["baskets"], panel_name="baskets", cfg=None, n_workers=n_workers,
            cache_dir=_effective_cache_dir,
        )
        log.info("Baskets FIRED_UP onsets (defaults): %d", len(baskets_events_default))

        for sens_key, cfg_override in SENSITIVITY_CONFIGS.items():
            log.info("Enumerating baskets panel sensitivity=%s cfg=%s...", sens_key, cfg_override)
            sens_ev = enumerate_sq_events(
                panel_data_stores["baskets"], panel_name="baskets", cfg=cfg_override, n_workers=n_workers,
                cache_dir=_effective_cache_dir,
            )
            log.info("Baskets FIRED_UP onsets (sensitivity=%s): %d", sens_key, len(sens_ev))
            sensitivity_events[sens_key]["baskets"] = sens_ev

    # Build volume coverage table BEFORE dedup (counts all enumerated events)
    volume_coverage_by_panel: dict[str, pd.DataFrame] = {}
    if not deep_events_default.empty:
        volume_coverage_by_panel["deep"] = deep_events_default
    if not baskets_events_default.empty:
        volume_coverage_by_panel["baskets"] = baskets_events_default
    volume_coverage = _build_volume_coverage_table(volume_coverage_by_panel)

    n_deep_events = len(deep_events_default)
    n_baskets_events = len(baskets_events_default)

    # Step 7b: dedup_sq_events — BLOCKER FIX
    # With sensitivities wired, multiple cfg keys can produce the same (ticker, date) onset.
    # Skipping dedup here would multiply rows. We dedup the defaults events (one event per
    # (ticker, date)), keeping the defaults row preferentially.
    # The sensitivity events are separately enumerated and do NOT feed the main form analysis;
    # they are graded independently (below). Each sensitivity's own events are also deduped.
    if not deep_events_default.empty:
        before_dedup = len(deep_events_default)
        deep_events_default = dedup_sq_events(deep_events_default)
        log.info(
            "dedup_sq_events deep (defaults): %d → %d events (%d removed)",
            before_dedup, len(deep_events_default), before_dedup - len(deep_events_default),
        )
    if not baskets_events_default.empty:
        before_dedup = len(baskets_events_default)
        baskets_events_default = dedup_sq_events(baskets_events_default)
        log.info(
            "dedup_sq_events baskets (defaults): %d → %d events (%d removed)",
            before_dedup, len(baskets_events_default), before_dedup - len(baskets_events_default),
        )
    for sens_key in list(sensitivity_events.keys()):
        for pname in list(sensitivity_events[sens_key].keys()):
            ev = sensitivity_events[sens_key][pname]
            if not ev.empty:
                sensitivity_events[sens_key][pname] = dedup_sq_events(ev)

    # Step 8: Label COILED context (reuse label_coiled_context verbatim — L1)
    for panel_name, events_df in [("deep", deep_events_default), ("baskets", baskets_events_default)]:
        if events_df.empty or panel_name not in panel_data_stores:
            continue
        log.info("Labeling COILED context for %s panel...", panel_name)
        labeled = label_coiled_context(
            events_df, panel_data_stores[panel_name], sector_map=sector_map,
        )
        if panel_name == "deep":
            deep_events_default = labeled
        else:
            baskets_events_default = labeled

    # Step 9: Label gate-fire proximity (reuse label_gate_fire_proximity verbatim — L1)
    for panel_name, events_df in [("deep", deep_events_default), ("baskets", baskets_events_default)]:
        if events_df.empty or panel_name not in panel_data_stores:
            continue
        gf = gate_fires_stores.get(panel_name)
        if gf is not None and not gf.empty:
            log.info("Labeling gate-fire proximity for %s panel...", panel_name)
            labeled = label_gate_fire_proximity(events_df, gf, proximity_bars=GATE_FIRE_PROXIMITY_BARS)
            if panel_name == "deep":
                deep_events_default = labeled
            else:
                baskets_events_default = labeled

    # Step 10: Grade defaults events
    graded_by_panel: dict[str, pd.DataFrame] = {}

    for panel_name, events_df in [("deep", deep_events_default), ("baskets", baskets_events_default)]:
        if events_df.empty or panel_name not in panel_data_stores:
            continue
        log.info("Grading FIRED_UP events for %s panel (defaults)...", panel_name)
        graded = grade_sq_events(
            events_df, panel_data_stores[panel_name], sector_map, panel_name
        )
        graded_by_panel[panel_name] = graded

    # Step 11: Build per-panel form results and accumulate all effects for family-wide BH
    all_effects_for_bh: list[dict[str, Any]] = []
    panel_results: dict[str, Any] = {}

    # For the primary summary (deep panel, defaults)
    per_form_species_bars: dict[str, dict[str, Any]] = {}
    primary_sa_cofire_share  = 0.0
    primary_sa_cofire_n      = 0
    primary_coiled_cofire_share = 0.0
    primary_gf_cofire_share  = 0.0
    primary_gf_cofire_n      = 0
    aggregate_cofire_parts: list[float] = []

    for panel_name, graded in graded_by_panel.items():
        ohlcv_store = panel_data_stores[panel_name]
        gf = gate_fires_stores.get(panel_name)
        closes_for_nc2 = {t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns}
        events_for_panel = (
            deep_events_default if panel_name == "deep" else baskets_events_default
        )

        survivor_stamp = (
            f"SURVIVOR BIAS STAMP: absolute rates on surviving {panel_name}-panel names only. "
            "Comparisons within-era are directionally valid."
        )

        forms_results: dict[str, Any] = {}

        # Grade gate fires once for this panel (reused across all three forms)
        gf_graded: pd.DataFrame = pd.DataFrame()
        if gf is not None and not gf.empty:
            gf_graded = grade_fires(gf.copy(), closes_for_nc2)
            gf_graded = _prepare_binary_outcomes(gf_graded)
            gf_graded["_date_ts"] = pd.to_datetime(gf_graded["date"]).astype(np.int64)
            gf_graded["era"] = gf_graded["date"].apply(_assign_era)
            gf_graded["sector"] = gf_graded["ticker"].map(sector_map)
            gf_graded["_is_ssq"] = 0
            log.info("Graded gate fires for %s panel: %d rows", panel_name, len(gf_graded))

        # Form (a): standalone — all FIRED_UP onset events vs gate fires
        if not graded.empty:
            # standalone = all FIRED_UP onset events
            graded_sa = graded.copy()
            graded_sa["_is_ssq"] = 1  # all events are the "treatment"

            # Build control: all gate fires (for R1 contrast)
            # R1 contrast: treatment = S-SQ events, control = gate fires
            # Combine treatment (S-SQ events) with control (gate fires, pre-graded once)
            if not gf_graded.empty:
                combined_sa = pd.concat(
                    [graded_sa, gf_graded.copy()],
                    ignore_index=True, sort=False,
                )
                combined_sa["_date_ts"] = pd.to_datetime(combined_sa["date"]).astype(np.int64)
            else:
                # No gate fires — standalone analysis only (no R1 contrast possible)
                combined_sa = graded_sa.copy()

            n_sa = len(graded_sa[graded_sa["gradable"] == True]) if "gradable" in graded_sa.columns else len(graded_sa)  # noqa: E712

            sa_results = run_form_analysis(
                combined_sa, "_is_ssq", panel=panel_name,
                n_bootstrap=n_bootstrap, rng_seed=RNG_SEED,
            )

            # Co-fire share (standalone form, per-form)
            sa_cofire, sa_cofire_n = compute_cofire_share_trading_bars(
                events_for_panel, ohlcv_store,
                gf if gf is not None else pd.DataFrame(),
                INDEPENDENCE_BARS,
            )
            aggregate_cofire_parts.append(sa_cofire)

            for e in sa_results.get("effects", []):
                e["form_key"] = f"{panel_name}_standalone"
            all_effects_for_bh.extend(sa_results.get("effects", []))

            forms_results["standalone"] = {
                "n_events_total": len(events_for_panel),
                "n_events_deduped": len(events_for_panel),
                "n_gradable": sa_results.get("n_treatment", 0),
                "n_treatment": sa_results.get("n_treatment", 0),
                "n_control": sa_results.get("n_control", 0),
                "effects": sa_results.get("effects", []),
                "era_table": sa_results.get("era_table"),
                "era_sign_stable": sa_results.get("era_sign_stable"),
                "nc2_marginality": None,
            }

            # Per-form species bar (primary panel = deep, primary form = standalone)
            if panel_name == "deep":
                primary_sa_cofire_share = sa_cofire
                primary_sa_cofire_n = sa_cofire_n
                per_form_species_bars["standalone (deep, defaults)"] = check_sq_species_bar(
                    "standalone (deep, defaults)",
                    sa_results,
                    n_events=n_sa,
                    co_fire_share=sa_cofire,
                    coiled_fire_recall=None,  # DEFERRED (same as S-UR)
                    sq_recall=sa_results.get("n_treatment", 0) / max(
                        sa_results.get("n_treatment", 0) + sa_results.get("n_control", 1), 1
                    ),
                    is_gatefire_form=False,
                )

        # Form (b): COILED intersection
        if "in_coiled_ctx" in graded.columns and not gf_graded.empty:
            coiled_mask = graded["in_coiled_ctx"] == True  # noqa: E712

            graded_coiled = graded[coiled_mask].copy()
            graded_coiled["_is_ssq"] = 1

            if not graded_coiled.empty:
                combined_coiled = pd.concat(
                    [graded_coiled, gf_graded.copy()],
                    ignore_index=True, sort=False,
                )
                combined_coiled["_date_ts"] = pd.to_datetime(combined_coiled["date"]).astype(np.int64)
                n_coiled = len(graded_coiled[graded_coiled["gradable"] == True]) if "gradable" in graded_coiled.columns else len(graded_coiled)  # noqa: E712

                coiled_results = run_form_analysis(
                    combined_coiled, "_is_ssq", panel=panel_name,
                    n_bootstrap=n_bootstrap, rng_seed=RNG_SEED,
                )

                # Co-fire for COILED form
                if "in_coiled_ctx" in events_for_panel.columns:
                    coiled_ev_for_cofire = events_for_panel[
                        events_for_panel["in_coiled_ctx"] == True  # noqa: E712
                    ]
                else:
                    coiled_ev_for_cofire = pd.DataFrame()
                if not coiled_ev_for_cofire.empty:
                    coiled_cofire, _ = compute_cofire_share_trading_bars(
                        coiled_ev_for_cofire, ohlcv_store, gf, INDEPENDENCE_BARS,
                    )
                else:
                    coiled_cofire = 0.0

                for e in coiled_results.get("effects", []):
                    e["form_key"] = f"{panel_name}_coiled"
                all_effects_for_bh.extend(coiled_results.get("effects", []))

                forms_results["coiled"] = {
                    "n_events_total": int(coiled_mask.sum()),
                    "n_events_deduped": int(coiled_mask.sum()),
                    "n_gradable": coiled_results.get("n_treatment", 0),
                    "n_treatment": coiled_results.get("n_treatment", 0),
                    "n_control": coiled_results.get("n_control", 0),
                    "effects": coiled_results.get("effects", []),
                    "era_table": coiled_results.get("era_table"),
                    "era_sign_stable": coiled_results.get("era_sign_stable"),
                    "nc2_marginality": None,
                }

                if panel_name == "deep":
                    primary_coiled_cofire_share = coiled_cofire
                    per_form_species_bars["COILED-intersection (deep, defaults)"] = check_sq_species_bar(
                        "COILED-intersection (deep, defaults)",
                        coiled_results,
                        n_events=n_coiled,
                        co_fire_share=coiled_cofire,
                        coiled_fire_recall=None,
                        sq_recall=coiled_results.get("n_treatment", 0) / max(
                            coiled_results.get("n_treatment", 0) + coiled_results.get("n_control", 1), 1
                        ),
                        is_gatefire_form=False,
                    )

        # Form (c): gate-fire proximity
        if "near_gate_fire" in graded.columns and not gf_graded.empty:
            gf_mask = graded["near_gate_fire"] == True  # noqa: E712
            graded_gf = graded[gf_mask].copy()
            graded_gf["_is_ssq"] = 1

            if not graded_gf.empty:
                combined_gf = pd.concat(
                    [graded_gf, gf_graded.copy()],
                    ignore_index=True, sort=False,
                )
                combined_gf["_date_ts"] = pd.to_datetime(combined_gf["date"]).astype(np.int64)
                n_gf = len(graded_gf[graded_gf["gradable"] == True]) if "gradable" in graded_gf.columns else len(graded_gf)  # noqa: E712

                gf_results = run_form_analysis(
                    combined_gf, "_is_ssq", panel=panel_name,
                    n_bootstrap=n_bootstrap, rng_seed=RNG_SEED,
                    closes_for_nc2=closes_for_nc2,
                    compute_nc2_fe=True,
                )

                # Co-fire for gatefire form (N/A-structural but compute for reporting)
                if "near_gate_fire" in events_for_panel.columns:
                    gf_events_sub = events_for_panel[
                        events_for_panel["near_gate_fire"] == True  # noqa: E712
                    ]
                else:
                    gf_events_sub = pd.DataFrame()

                if not gf_events_sub.empty:
                    gf_cofire, gf_cofire_n_val = compute_cofire_share_trading_bars(
                        gf_events_sub, ohlcv_store, gf, INDEPENDENCE_BARS,
                    )
                else:
                    gf_cofire, gf_cofire_n_val = 0.0, 0

                for e in gf_results.get("effects", []):
                    e["form_key"] = f"{panel_name}_gatefire"
                all_effects_for_bh.extend(gf_results.get("effects", []))

                forms_results["gatefire"] = {
                    "n_events_total": int(gf_mask.sum()),
                    "n_events_deduped": int(gf_mask.sum()),
                    "n_gradable": gf_results.get("n_treatment", 0),
                    "n_treatment": gf_results.get("n_treatment", 0),
                    "n_control": gf_results.get("n_control", 0),
                    "effects": gf_results.get("effects", []),
                    "era_table": gf_results.get("era_table"),
                    "era_sign_stable": gf_results.get("era_sign_stable"),
                    "nc2_marginality": gf_results.get("nc2_marginality"),
                }

                if panel_name == "deep":
                    primary_gf_cofire_share = gf_cofire
                    primary_gf_cofire_n = gf_cofire_n_val
                    per_form_species_bars["gatefire-proximity (deep, defaults)"] = check_sq_species_bar(
                        "gatefire-proximity (deep, defaults)",
                        gf_results,
                        n_events=n_gf,
                        co_fire_share=gf_cofire,
                        coiled_fire_recall=None,
                        sq_recall=gf_results.get("n_treatment", 0) / max(
                            gf_results.get("n_treatment", 0) + gf_results.get("n_control", 1), 1
                        ),
                        is_gatefire_form=True,
                        nc2_marginality=gf_results.get("nc2_marginality"),
                    )

        panel_results[panel_name] = {
            "survivor_stamp": survivor_stamp,
            "forms": forms_results,
        }

    # Step 11b: Grade and analyze sensitivity configs (BLOCKER FIX: wired into run_study)
    # Each sensitivity is enumerated/graded/analyzed independently and its effects
    # are included in the family-wide BH pool (part of the registered 12-trial budget).
    # volconf15 sensitivity is now meaningful with volume flowing.
    # Only standalone form for sensitivities (reduces wall-clock; 3 sens × 2 panels = 6 cells).
    sensitivity_results: dict[str, dict[str, Any]] = {}
    for sens_key, cfg_override in SENSITIVITY_CONFIGS.items():
        log.info("Running sensitivity analysis: %s (cfg=%s)", sens_key, cfg_override)
        sensitivity_results[sens_key] = {}
        for panel_name in panels:
            ohlcv_store = panel_data_stores.get(panel_name, {})
            gf = gate_fires_stores.get(panel_name)
            if not ohlcv_store:
                continue
            sens_ev = sensitivity_events.get(sens_key, {}).get(panel_name, pd.DataFrame())
            if sens_ev.empty:
                sensitivity_results[sens_key][panel_name] = {"n_events": 0, "standalone_effects": []}
                continue

            # Grade sensitivity events
            graded_sens = grade_sq_events(sens_ev, ohlcv_store, sector_map, panel_name)
            if graded_sens.empty:
                sensitivity_results[sens_key][panel_name] = {"n_events": len(sens_ev), "standalone_effects": []}
                continue

            # Build gate-fire control set for this panel
            closes_s = {t: df["close"] for t, df in ohlcv_store.items() if "close" in df.columns}
            gf_graded_s: pd.DataFrame = pd.DataFrame()
            if gf is not None and not gf.empty:
                gf_graded_s = grade_fires(gf.copy(), closes_s)
                gf_graded_s = _prepare_binary_outcomes(gf_graded_s)
                gf_graded_s["_date_ts"] = pd.to_datetime(gf_graded_s["date"]).astype(np.int64)
                gf_graded_s["era"]      = gf_graded_s["date"].apply(_assign_era)
                gf_graded_s["sector"]   = gf_graded_s["ticker"].map(sector_map)
                gf_graded_s["_is_ssq"]  = 0

            # Standalone form only
            graded_sens_sa = graded_sens.copy()
            graded_sens_sa["_is_ssq"] = 1
            if not gf_graded_s.empty:
                combined_s = pd.concat([graded_sens_sa, gf_graded_s], ignore_index=True, sort=False)
                combined_s["_date_ts"] = pd.to_datetime(combined_s["date"]).astype(np.int64)
            else:
                combined_s = graded_sens_sa.copy()

            sens_sa_results = run_form_analysis(
                combined_s, "_is_ssq", panel=panel_name,
                n_bootstrap=n_bootstrap, rng_seed=RNG_SEED,
            )
            for e in sens_sa_results.get("effects", []):
                e["form_key"] = f"{panel_name}_{sens_key}_standalone"
            all_effects_for_bh.extend(sens_sa_results.get("effects", []))

            sensitivity_results[sens_key][panel_name] = {
                "n_events":          len(sens_ev),
                "standalone_effects": sens_sa_results.get("effects", []),
            }
            log.info(
                "Sensitivity %s panel=%s: %d events, %d standalone effects",
                sens_key, panel_name, len(sens_ev),
                len(sens_sa_results.get("effects", [])),
            )

    # Step 12: Family-wide BH correction (now includes defaults + sensitivity effects)
    if all_effects_for_bh:
        all_effects_for_bh = apply_family_wide_bh(all_effects_for_bh)
        log.info(
            "Applied family-wide BH correction over %d effects "
            "(defaults all-forms + sensitivities standalone)",
            len(all_effects_for_bh),
        )
        # Propagate updated BH q/rejected back to sensitivity_results
        bh_by_formkey: dict[str, dict[str, Any]] = {}
        for e in all_effects_for_bh:
            fk = e.get("form_key", "")
            if fk not in bh_by_formkey:
                bh_by_formkey[fk] = {}
            bh_by_formkey[fk][e.get("outcome", "")] = e
        for sens_key in sensitivity_results:
            for panel_name in sensitivity_results[sens_key]:
                fk = f"{panel_name}_{sens_key}_standalone"
                if fk in bh_by_formkey:
                    updated = [
                        bh_by_formkey[fk].get(e["outcome"], e)
                        for e in sensitivity_results[sens_key][panel_name].get("standalone_effects", [])
                    ]
                    sensitivity_results[sens_key][panel_name]["standalone_effects"] = updated

    # Step 13: Build report
    aggregate_cofire_share = (
        float(np.mean(aggregate_cofire_parts)) if aggregate_cofire_parts else 0.0
    )

    coiled_fire_recall_note = (
        "COILED-FIRE recall is DEFERRED (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). "
        "The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated "
        "until the full cycles.py pipeline is run per-fire over all gate dates. "
        "S-SQ proxy reported as TREATMENT-SHARE-OF-POOL (n_treatment / (n_treatment + n_control)): "
        "this is NOT the +/-5-bar gate-fire recall (n_near / total_gf) as used in S-UR; "
        "the recall clause is DEFERRED so this proxy feeds no verdict, it is cosmetic only."
    )

    nc2_note = (
        "NC-2 PARTIAL: proximity component only (EQ_W_PROX=0.52 of total). "
        "PROXY-INPUT LIMITATION: the 63-bar close-min pivot is a PROXY for the true "
        "cand_price/dcl_price pivot (cycles.py:1705-1706). "
        "NC-2 marginality test for gatefire form only (proximity confounding is the primary "
        "alternative explanation for any stop5 improvement in that form). "
        "NC-2 is DESCRIPTIVE-ONLY for standalone and COILED forms."
    )

    delisted_status = (
        "DELISTED ARM: NOT APPLICABLE — the delisted panel (data/breadth/_closes_delisted.parquet) "
        "is close-only and does not contain H/L columns. "
        "engine/vol_squeeze.assess_series requires H/L for the TTM-squeeze arm of the compression "
        "detection gate. Without H/L the compression threshold is looser (BBWP+HVP only, no TTM), "
        "changing the fidelity-pinned event definition. "
        "Per masterplan §1 fact table row 3: 'NOT for H/L-dependent species (S-SQ)'. "
        "This panel cannot run this species. Results are based on deep and baskets panels only."
    )

    lines: list[str] = []
    report_text = write_report(
        lines,
        panel_results=panel_results,
        per_form_species_bars=per_form_species_bars,
        coiled_fire_recall_note=coiled_fire_recall_note,
        nc2_note=nc2_note,
        delisted_status=delisted_status,
        smoke=smoke,
        aggregate_cofire_share=aggregate_cofire_share,
        primary_sa_cofire_share=primary_sa_cofire_share,
        primary_sa_cofire_n=primary_sa_cofire_n,
        primary_coiled_cofire_share=primary_coiled_cofire_share,
        primary_gf_cofire_share=primary_gf_cofire_share,
        primary_gf_cofire_n=primary_gf_cofire_n,
        n_deep_events=n_deep_events,
        n_baskets_events=n_baskets_events,
        volume_coverage=volume_coverage,
        spot_check_results=spot_check_results,
        sensitivity_results=sensitivity_results,
    )

    # Step 14: Write report
    out = out_path or (_RESEARCH_DIR / "W2_SSQ_REPORT.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_text, encoding="utf-8")
    log.info("Report written to %s", out)
    print(f"\nReport written to: {out}")

    # Final verification: re-check S16 is in registry, not S14/S15
    from engine import species_registry as sr
    final_reg = sr.load()
    final_taken = {e["species_id"] for e in final_reg.get("species", [])}
    assert "S16" in final_taken, f"S16 not found in registry at finalize! Taken: {final_taken}"
    assert "S14" in final_taken, "S14 (Failed breakout) missing from registry — unexpected"
    assert "S15" in final_taken, "S15 (Spring Reclaim) missing from registry — unexpected"
    log.info("Final registry check passed: S14+S15 taken, S16 registered.")

    print("\n=== SUMMARY ===")
    print(f"Species: {SPECIES_ID} — {SPECIES_NAME}")
    print(f"Family: {SPECIES_FAMILY}")
    print(f"Deep FIRED_UP onsets: {n_deep_events}")
    print(f"Baskets FIRED_UP onsets: {n_baskets_events}")
    print(f"Forms analyzed: {list(per_form_species_bars.keys())}")
    for fk, sb in per_form_species_bars.items():
        ni = "YES" if sb.get("stop5_noninferiority_met") else "NO"
        sup = "YES" if sb.get("superiority_met") else ("NO(nc2)" if sb.get("superiority_met_nc2_nullified") else "NO")
        print(
            f"  {fk}: n={sb.get('n_events', 0)}, stop5_coef={sb.get('stop5_coef', float('nan')):.4f}, "
            f"non-inferior={ni}, superior={sup}"
        )
    print(f"Report: {out}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="W2 S-SQ Squeeze Release phase-0 study."
    )
    p.add_argument(
        "--smoke",
        action="store_true",
        help="Smoke run (reduced data; NOT for adjudication per L2 law).",
    )
    p.add_argument(
        "--n-bootstrap",
        type=int,
        default=N_BOOTSTRAP,
        help=f"Bootstrap resamples (default: {N_BOOTSTRAP}; >=1000 for production per L2).",
    )
    p.add_argument(
        "--panel",
        nargs="+",
        choices=["deep", "baskets"],
        default=["deep", "baskets"],
        help="Panels to include (default: deep baskets).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path for the report markdown.",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Parallel worker processes for enumerate_sq_events (default: 1 = sequential). "
            "Capped at 3 per task-brief L2 law. Parallelises the O(n²) assess_series "
            "calls across tickers using ProcessPoolExecutor."
        ),
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=(
            "Root directory for per-ticker enumeration cache "
            f"(default: {_DEFAULT_SSQ_CACHE_DIR}). "
            "Must be outside the repo tree. Cache files are NOT git-added. "
            "Cached tickers are skipped on re-run (checkpoint/resume). "
            "Set to empty string to disable caching."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    warnings.filterwarnings("ignore", category=FutureWarning)
    args = _parse_args()
    run_study(
        panels=args.panel,
        n_bootstrap=args.n_bootstrap,
        smoke=args.smoke,
        out_path=args.out,
        n_workers=args.workers,
        cache_dir=args.cache_dir,
    )
