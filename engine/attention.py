"""Abnormal-attention z from Wikimedia pageviews (DISPLAY-ONLY).

Single source of truth for the z definition used by BOTH the build-time chip
(scripts/build_site.build_attention_data -> site/factordata/attention.json) and the
Phase-0 backtest (scripts/wiki_attention_phase0.py). NOT wired into any scoring path
(engine/axes, top_picks, setups, equity_factors) — it is a neutral over-extension /
fade-risk caution, never directional. See research/WIKI_ATTENTION_CHIP_SPEC.md.

z definition (per ticker): a recent (trailing `recent_days`) mean of log1p(views) versus
a CAUSAL baseline over the prior `z_window` days, standardized with a robust median/MAD
(pageview counts are heavily right-skewed, so MAD beats std). The baseline window is
shifted back by `recent_days` so a spike never inflates its own baseline. Clipped for
display. The same construction, evaluated at every date, is the panel the Phase-0 ranks.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_MAD_SCALE = 1.4826   # MAD -> std-equivalent for a normal


def _cfg() -> dict:
    try:
        return config.load().get("wiki_pageviews", {}) or {}
    except Exception:  # noqa: BLE001 — usable defaults below
        return {}


def causal_z_series(views, *, z_window: int = 90, recent_days: int = 5,
                    clip: tuple[float, float] | None = None) -> pd.Series:
    """Per-date robust abnormal-attention z, CAUSAL (uses only views up to each date).

    recent_t = mean log-views over (t-recent_days, t];  baseline = the prior z_window of
    log-views, shifted back by recent_days so the recent window is excluded; z = (recent -
    median)/(1.4826*MAD). NaN until the baseline is estimable. This is the time series the
    Phase-0 panel ranks; the chip uses its last value."""
    v = pd.Series(views).astype(float).sort_index()
    v = v[~v.index.duplicated(keep="last")]
    lv = np.log1p(v.clip(lower=0))
    minp = max(20, z_window // 2)
    recent = lv.rolling(recent_days, min_periods=max(1, recent_days // 2)).mean()
    base = lv.shift(recent_days)                              # exclude the recent window
    med = base.rolling(z_window, min_periods=minp).median()
    mad = (base - med).abs().rolling(z_window, min_periods=minp).median()
    sd = (_MAD_SCALE * mad).replace(0, np.nan)
    z = (recent - med) / sd
    if clip is not None:
        z = z.clip(clip[0], clip[1])
    return z


def attention_z(views, cfg: dict | None = None) -> float | None:
    """The latest causal robust z for one ticker's daily views, clipped — or None."""
    cfg = cfg if cfg is not None else _cfg()
    z = causal_z_series(
        views,
        z_window=int(cfg.get("z_window", 90)),
        recent_days=int(cfg.get("recent_days", 5)),
        clip=(float(cfg.get("clip_lo", -3.0)), float(cfg.get("clip_hi", 6.0))),
    ).dropna()
    if not len(z):
        return None
    val = float(z.iloc[-1])
    return round(val, 2) if np.isfinite(val) else None


def attention_signals(panel: dict[str, pd.DataFrame], cfg: dict | None = None) -> dict:
    """{ticker: {z, views, asof}} for every ticker whose views yield a finite latest z.

    Includes sub-threshold (quiet) names too — the render gate (`chip_threshold`) decides
    what becomes a chip — so attention.json carries the full cross-section the Phase-0 and
    any future promotion would need. Additive/graceful: a bad frame is skipped."""
    cfg = cfg if cfg is not None else _cfg()
    out: dict[str, dict] = {}
    for tk, df in (panel or {}).items():
        try:
            if df is None or len(df) == 0 or "views" not in getattr(df, "columns", []):
                continue
            v = df["views"]
            z = attention_z(v, cfg)
            if z is None:
                continue
            last = float(v.dropna().iloc[-1])
            out[str(tk)] = {"z": z, "views": int(round(last)),
                            "asof": pd.Timestamp(v.index.max()).date().isoformat()}
        except Exception as e:  # noqa: BLE001 — one bad ticker never kills the map
            log.debug("attention_signals %s skipped: %s", tk, e)
    return out


def load_panel() -> dict[str, pd.DataFrame]:
    """Read data/attention/<ticker>.parquet (written by collectors.wiki_pageviews)."""
    d = config.data_dir() / "attention"
    if not d.exists():
        return {}
    panel: dict[str, pd.DataFrame] = {}
    for p in sorted(d.glob("*.parquet")):
        try:
            panel[p.stem] = pd.read_parquet(p).sort_index()
        except Exception as e:  # noqa: BLE001
            log.debug("attention load %s failed: %s", p.stem, e)
    return panel
