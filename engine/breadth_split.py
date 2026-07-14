"""AI-vs-non-AI breadth decomposition (DISPLAY-ONLY, never scored).

Decomposes the S&P-oid close cache into AI-adjacent vs non-AI cohorts and
reports per-cohort breadth metrics (pct above 50/200dma, advance share) plus
the AI-minus-non-AI spread. Answers: "is the tape's health real, or is it
composition-driven by AI names?"

THIS IS NOT a McClellan-thrust signal (that construction is killed, RRX-R4/R10).
It feeds no score, no gate, no regime signal.

Style anchor: engine/vol_sentiment.py — degrade-never-raise, absent-safe reads,
display-only discipline.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Band constants (module-level dict for calibration overlay).
# All thresholds are RELATIVE / descriptive spread bands, not absolute VIX-like
# anchors — doctrine compliance (RRX-R10).
# ---------------------------------------------------------------------------

# spread = ai_pct - nonai_pct (percentage points of pct_above_50dma)
_BANDS: dict[str, dict] = {
    "ai_leading": {
        "min_spread": 15.0,
        "stance_en": "strength concentrated in AI-linked names, the rest is not confirming",
        "stance_zh": "涨势集中于 AI 相关个股，非 AI 板块未能跟进",
    },
    "ai_lagging": {
        "max_spread": -15.0,
        "stance_en": "AI-linked names lagging while the rest holds up",
        "stance_zh": "AI 相关个股落后，非 AI 板块相对支撑",
    },
    "broad": {
        "stance_en": "participation broad, not just the AI complex — watch for rotation",
        "stance_zh": "普涨格局，非局限于 AI 板块 — 留意轮动信号",
    },
}

# Cache is young until it has >= 252 rows of price history
_YOUNG_THRESHOLD = 252


def _r(x, n: int = 1):
    """Round to n decimal places; return None for NaN/inf/None."""
    if x is None:
        return None
    try:
        f = float(x)
        return round(f, n) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _stance(spread_50: float | None) -> tuple[str, str]:
    """Derive stance copy from the spread_50 value."""
    if spread_50 is None:
        return "—", "—"
    if spread_50 >= _BANDS["ai_leading"]["min_spread"]:
        return _BANDS["ai_leading"]["stance_en"], _BANDS["ai_leading"]["stance_zh"]
    if spread_50 <= _BANDS["ai_lagging"]["max_spread"]:
        return _BANDS["ai_lagging"]["stance_en"], _BANDS["ai_lagging"]["stance_zh"]
    return _BANDS["broad"]["stance_en"], _BANDS["broad"]["stance_zh"]


def _pct_above_dma(closes: pd.DataFrame, window: int) -> pd.Series:
    """Per-day fraction of tickers above their <window>-day moving average.

    Honest denominators: a ticker counts only when it has >= window prior
    observations on that day. Denominator can vary day to day.

    Returns a Series indexed by date.
    """
    min_periods = window  # a ticker needs exactly <window> prior obs
    # rolling mean for each ticker; NaN if fewer than window obs available
    ma = closes.rolling(window, min_periods=min_periods).mean()
    above = (closes > ma).astype(float)
    # where MA is NaN (insufficient history), above is NaN — we must exclude those
    above[ma.isna()] = np.nan
    # denominator = count of qualifying tickers each day
    qualifying_count = (~ma.isna()).sum(axis=1)
    # sum of above-MA flags per day
    above_sum = above.sum(axis=1, min_count=1)
    pct = (above_sum / qualifying_count.replace(0, np.nan)) * 100.0
    return pct.where(qualifying_count > 0)


def _adv_share(closes: pd.DataFrame) -> pd.Series:
    """Per-day fraction of tickers with close > previous close (both present)."""
    daily_chg = closes.diff()  # NaN on first row and where either day is missing
    advancing = (daily_chg > 0).astype(float)
    advancing[daily_chg.isna()] = np.nan
    qualifying = (~daily_chg.isna()).sum(axis=1)
    adv_sum = advancing.sum(axis=1, min_count=1)
    share = (adv_sum / qualifying.replace(0, np.nan)) * 100.0
    return share.where(qualifying > 0)


def compute_breadth_split() -> dict | None:
    """Compute the AI vs non-AI breadth decomposition.

    Returns the JSON payload dict or None on total shortfall.
    Never raises.
    """
    try:
        return _compute()
    except Exception as e:  # noqa: BLE001
        log.error("compute_breadth_split: unexpected error: %s", e)
        return None


def _compute() -> dict | None:
    # --- Load closes cache ---
    closes_path = config.data_dir() / "breadth" / "_closes_cache.parquet"
    if not closes_path.exists():
        log.warning("breadth_split: _closes_cache.parquet not found")
        return None
    try:
        closes = pd.read_parquet(closes_path)
        closes.index = pd.to_datetime(closes.index)
        closes = closes.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("breadth_split: failed to read closes cache: %s", e)
        return None

    if closes.empty or closes.shape[0] < 5:
        log.warning("breadth_split: closes cache too small (%d rows)", closes.shape[0])
        return None

    as_of = closes.index.max().strftime("%Y-%m-%d")
    n_rows = closes.shape[0]
    cache_cols = set(closes.columns)

    # --- Load AI tags ---
    # Import here to avoid circular dependency and keep imports lazy
    from scripts.build_ai_adjacency_tag import ensure_ai_tags

    tag_df = ensure_ai_tags()
    if tag_df is None:
        log.warning("breadth_split: AI tag unavailable — returning None")
        return None

    # Intersect with cache columns
    ai_tickers = set(tag_df["ticker"]) & cache_cols
    non_ai_tickers = cache_cols - set(tag_df["ticker"])

    # Sub-cohort sizes — cache-intersected so that ai_core + ai_infra_power == ai_total.
    # Full tagged population (pre-intersection) exposed under *_tagged keys for Tier-2 receipts.
    ai_core_tickers_tagged = set(tag_df.loc[tag_df["tag"] == "ai_core", "ticker"])
    ai_infra_power_tickers_tagged = set(tag_df.loc[tag_df["tag"] == "ai_infra_power", "ticker"])
    ai_core_count = int(len(ai_core_tickers_tagged & cache_cols))
    ai_infra_power_count = int(len(ai_infra_power_tickers_tagged & cache_cols))
    ai_core_tagged_count = int(len(ai_core_tickers_tagged))
    ai_infra_power_tagged_count = int(len(ai_infra_power_tickers_tagged))

    # Cohort sizes in cache (what we actually compute on)
    ai_in_cache = int(len(ai_tickers))
    nonai_in_cache = int(len(non_ai_tickers))

    if ai_in_cache == 0 or nonai_in_cache == 0:
        log.warning(
            "breadth_split: degenerate cohorts ai=%d nonai=%d", ai_in_cache, nonai_in_cache
        )
        return None

    ai_closes = closes[sorted(ai_tickers)]
    nonai_closes = closes[sorted(non_ai_tickers)]

    # --- Per-cohort breadth metrics ---
    ai_pct50 = _pct_above_dma(ai_closes, 50)
    nonai_pct50 = _pct_above_dma(nonai_closes, 50)
    ai_pct200 = _pct_above_dma(ai_closes, 200)
    nonai_pct200 = _pct_above_dma(nonai_closes, 200)
    ai_adv = _adv_share(ai_closes)
    nonai_adv = _adv_share(nonai_closes)

    spread_50 = ai_pct50 - nonai_pct50
    spread_200 = ai_pct200 - nonai_pct200
    spread_adv = ai_adv - nonai_adv

    # Latest values
    def _last(s: pd.Series) -> float | None:
        s = s.dropna()
        if s.empty:
            return None
        v = float(s.iloc[-1])
        return v if np.isfinite(v) else None

    lat_ai_pct50 = _last(ai_pct50)
    lat_nonai_pct50 = _last(nonai_pct50)
    lat_ai_pct200 = _last(ai_pct200)
    lat_nonai_pct200 = _last(nonai_pct200)
    lat_ai_adv = _last(ai_adv)
    lat_nonai_adv = _last(nonai_adv)
    lat_spread_50 = _last(spread_50)
    lat_spread_200 = _last(spread_200)
    lat_spread_adv = _last(spread_adv)

    # Spark: last 120 values of spread_50
    spark_vals = spread_50.dropna().tail(120)
    spark_list = [_r(v, 1) for v in spark_vals.values]

    # Tag version
    tag_version = ""
    try:
        sentinel = config.data_dir() / "breadth" / "ticker_ai_tag.version"
        if sentinel.exists():
            tag_version = sentinel.read_text().strip()
    except Exception:  # noqa: BLE001
        pass

    # Stance
    stance_en, stance_zh = _stance(lat_spread_50)

    # Young flag: while cache history < 252 rows, trend context is still accruing
    young = bool(n_rows < _YOUNG_THRESHOLD)
    young_note = (
        "Trend context is still accruing — fewer than 252 trading days in the cache."
        if young else None
    )

    payload = {
        "as_of": as_of,
        "cohort_sizes": {
            # Cache-intersected counts: ai_core + ai_infra_power == ai_total (reconcilable).
            "ai_core": ai_core_count,
            "ai_infra_power": ai_infra_power_count,
            "ai_total": ai_in_cache,
            "non_ai": nonai_in_cache,
            "universe": ai_in_cache + nonai_in_cache,
            # Full tagged population (before cache intersection) — for Tier-2 audit receipts only.
            "ai_core_tagged": ai_core_tagged_count,
            "ai_infra_power_tagged": ai_infra_power_tagged_count,
        },
        "latest": {
            "ai_pct50": _r(lat_ai_pct50),
            "nonai_pct50": _r(lat_nonai_pct50),
            "spread_50": _r(lat_spread_50),
            "ai_pct200": _r(lat_ai_pct200),
            "nonai_pct200": _r(lat_nonai_pct200),
            "spread_200": _r(lat_spread_200),
            "ai_adv_share": _r(lat_ai_adv),
            "nonai_adv_share": _r(lat_nonai_adv),
            "spread_adv": _r(lat_spread_adv),
        },
        "spark": {
            "spread_50": spark_list,
        },
        "young": young,
        "young_note": young_note,
        "tag_version": tag_version,
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "disclaimer_en": (
            "Display-only composition decomposition — shows whether tape health "
            "is broad or concentrated in AI-adjacent names. Never scored, never "
            "feeds any gate or regime engine, no forward claim."
        ),
        "disclaimer_zh": (
            "仅供展示的成分分解 — 显示市场健康度是否集中于 AI 相关个股。"
            "不计分，不进入任何闸门或周期引擎，无前瞻性判断。"
        ),
    }

    # --- Also persist the full daily series (deterministic derived artifact, NOT a ledger) ---
    # This is regenerated from source on each run; it is not append-only.
    _persist_series(ai_pct50, nonai_pct50, ai_pct200, nonai_pct200, ai_adv, nonai_adv,
                    spread_50, spread_200, spread_adv)

    log.info(
        "breadth_split: as_of=%s ai=%d nonai=%d spread_50=%.1f%% young=%s",
        as_of, ai_in_cache, nonai_in_cache,
        lat_spread_50 if lat_spread_50 is not None else float("nan"),
        young,
    )
    return payload


def _persist_series(
    ai_pct50: pd.Series,
    nonai_pct50: pd.Series,
    ai_pct200: pd.Series,
    nonai_pct200: pd.Series,
    ai_adv: pd.Series,
    nonai_adv: pd.Series,
    spread_50: pd.Series,
    spread_200: pd.Series,
    spread_adv: pd.Series,
) -> None:
    """Persist the full daily series to data/breadth/breadth_split.parquet.

    This is a DETERMINISTIC DERIVED ARTIFACT (overwritten each run, not a ledger).
    It can be regenerated from _closes_cache.parquet + ticker_ai_tag.parquet at any time.
    """
    try:
        idx = ai_pct50.index.union(nonai_pct50.index)
        df = pd.DataFrame(
            {
                "ai_pct50": ai_pct50.reindex(idx),
                "nonai_pct50": nonai_pct50.reindex(idx),
                "ai_pct200": ai_pct200.reindex(idx),
                "nonai_pct200": nonai_pct200.reindex(idx),
                "ai_adv_share": ai_adv.reindex(idx),
                "nonai_adv_share": nonai_adv.reindex(idx),
                "spread_50": spread_50.reindex(idx),
                "spread_200": spread_200.reindex(idx),
                "spread_adv": spread_adv.reindex(idx),
            },
            index=idx,
        ).sort_index()

        out_path = config.data_dir() / "breadth" / "breadth_split.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("breadth_split: could not persist series: %s", e)
