"""China A-share tactical-strategy registry — the China sibling of engine.strategies.

China's market does NOT reward the price-trend / 200-day-SMA timing that works on the
US index (A-shares are cyclical and mean-reverting, so naive trend WHIPSAWS — see
engine.china_allocation's momentum-overlay A/B, which is shipped as the honest
"timing doesn't help" panel). The durable edges here are signals ORTHOGONAL to price:

  * the CREDIT CYCLE — total social financing (TSF) is China's #1 equity driver; the
    credit IMPULSE (acceleration of de-seasonalised credit growth) leads the index;
  * RETAIL-LEVERAGE extremes — margin financing as a % of float topped the 2015 bubble;
  * the VOLATILITY regime — Moreira-Muir vol-management is one of the few timing
    signals that generalises across markets, China included.

Each strategy is ONE risk asset (CSI 300, total-return adjusted close) timed long/flat
in [0,1] against a low cash sleeve (China cash earns ~1.8%, so de-risking is a drawdown
trade, not a carry trade). It reuses the asset-agnostic harness from engine.strategies
(StrategySpec + _compose + _onto) and is rendered by scripts.build_china_strategies onto
the same scorecard grid + detail-page templates as the US suite. The China Income Vector
(the static income+gold+bond blend in engine.china_allocation) keeps its own bespoke page
and appears on the grid as a card with own_page="china_allocation.html".

DISPLAY-ONLY / experimental: these are independent of and never scored into
china_axes / china_regime / china_playbook. Backtests are net of 3 bps, total-return,
next-bar. Honest caveat: the TSF credit series only begins 2015 (~136 monthly prints),
so the credit legs rest on a short macro sample; the vol leg generalises to deeper history.
"""
from __future__ import annotations

import pandas as pd

from engine import equity_alloc as ea
from engine.indicators import pct_rank_window
from engine.strategies import StrategySpec, _compose, _onto
from lib import store

CSI300 = "510300.SS"
CHINA_CASH_PCT = 1.8       # onshore cash / money-market sleeve (~0.8-1.8%); a drawdown trade
_W5Y = 252 * 5


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def _cnclose(ticker: str) -> pd.Series:
    df = store.read("china", ticker)
    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype=float)
    return df["close"].astype(float).dropna()


def _china_col(group: str, key: str, col: str) -> pd.Series:
    df = store.read(group, key)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    c = col if col in df.columns else df.columns[0]
    return df[c].astype(float).dropna()


# Residual execution lag (trading days) applied AFTER availability-date stamping —
# a print released on availability_date can be acted on the next session. This
# replaces the old fixed 22-trading-day guess that (stamped at month-start) landed
# ~10 days BEFORE the real ~day 9-15 release, a systematic look-ahead on China's
# most market-moving macro print (audit #27).
_CREDIT_EXEC_LAG = 1


def _tsf_availability_stamp(series: pd.Series) -> pd.Series:
    """Re-index a reference-month-stamped TSF-derived series onto its PUBLICATION-
    availability dates, so a value only becomes actable on/after the print was
    actually released. Reads the collector's additive `availability_date` column
    (falling back to the conservative day-16-of-following-month model if the
    column is absent, e.g. a parquet written before this change). The returned
    series is indexed by availability date; downstream `_onto(..., lag)` then
    ffills it causally onto the price calendar and applies a small residual
    execution lag — NOT the old 22-trading-day peek."""
    if series is None or series.empty:
        return series
    df = store.read("china_credit", "tsf")
    ref_index = pd.to_datetime(series.index)
    if df is not None and "availability_date" in getattr(df, "columns", []):
        avail_map = pd.Series(pd.to_datetime(df["availability_date"]).to_numpy(),
                              index=pd.to_datetime(df.index))
        avail = ref_index.map(lambda d: avail_map.get(d, pd.NaT))
        avail = pd.to_datetime(pd.Series(avail, index=series.index))
        # Any reference date without a mapped availability (shouldn't happen) →
        # conservative model so we never fall back to a look-ahead.
        miss = avail.isna()
        if miss.any():
            from collectors.china_credit import tsf_availability_date
            avail[miss] = [tsf_availability_date(d) for d in ref_index[miss.to_numpy()]]
    else:
        from collectors.china_credit import tsf_availability_date
        avail = pd.Series([tsf_availability_date(d) for d in ref_index], index=series.index)
    out = pd.Series(series.to_numpy(), index=pd.DatetimeIndex(avail.to_numpy()))
    out = out[~out.index.isna()].sort_index()
    # If two reference months mapped to the same availability date (shouldn't for a
    # monthly series), keep the last.
    return out[~out.index.duplicated(keep="last")]


# --------------------------------------------------------------------------- #
# legs (each [0,1], 1 = de-risk; raw on native index — score fns wrap with _onto)
# --------------------------------------------------------------------------- #
def _credit_derisk() -> pd.Series:
    """China credit-impulse de-risk: TSF is a monthly FLOW with heavy January
    seasonality → de-seasonalise via a trailing-12m SUM, take YoY % (credit-growth
    proxy), then the 6-month change of that growth (credit-impulse ACCELERATION). De-risk
    = 36-month rolling percentile of the NEGATED impulse: contracting credit → high de-risk.

    Uses canon.credit_impulse_ACCEL (audit #12) — the 2nd-derivative. This is a DIFFERENT
    series than china_radar's credit-impulse LEVEL (1st-derivative); the shared "credit
    impulse" label used to hide that these leveraged-GTAA books read acceleration while the
    radar chip reads the level. Byte-identical to the prior local."""
    tsf = _china_col("china_credit", "tsf", "tsf_total")
    if tsf.empty:
        return pd.Series(dtype=float)
    from engine import canon
    impulse = canon.credit_impulse_accel(tsf)
    derisk = pct_rank_window(-impulse, 36)
    # Re-stamp from reference-month-start to PUBLICATION-availability date so the
    # leg can never act on the impulse before the market saw the print (audit #27).
    return _tsf_availability_stamp(derisk)


def _margin_derisk() -> pd.Series:
    """Retail-leverage euphoria guard: margin financing as a % of float market cap
    (the 2015 bubble top read 4.70). De-risk = 5y rolling percentile — leverage at a
    multi-year extreme → de-risk."""
    mg = _china_col("china_margin", "balance", "fin_pct_float")
    if mg.empty:
        return pd.Series(dtype=float)
    return pct_rank_window(mg, _W5Y)


def _vol_derisk(close: pd.Series) -> pd.Series:
    """Moreira-Muir realized-vol guard: 21d realized vol on a 5y rolling percentile.
    High vol → de-risk (vol is persistent and precedes drawdowns)."""
    return pct_rank_window(close.pct_change().rolling(21).std(), _W5Y)


# --------------------------------------------------------------------------- #
# score builders (port of /tmp/research_china_ashare.py, validated metrics)
# --------------------------------------------------------------------------- #
def _sc_credit_vol(ctx, bench) -> dict:
    i = bench.index
    return _compose({
        "credit": {"series": _onto(_credit_derisk(), i, _CREDIT_EXEC_LAG),
                   "weight": 1.0, "lag": _CREDIT_EXEC_LAG,
                   "label": "Credit impulse contracting"},
        "vol": {"series": _onto(_vol_derisk(bench), i, 1), "weight": 0.5, "lag": 1,
                "label": "Realized volatility"},
    }, i)


def _sc_volmanaged(ctx, bench) -> dict:
    i = bench.index
    return _compose({
        "vol": {"series": _onto(_vol_derisk(bench), i, 1), "weight": 1.0, "lag": 1,
                "label": "Realized volatility"},
    }, i)


def _sc_credit_margin(ctx, bench) -> dict:
    i = bench.index
    return _compose({
        "credit": {"series": _onto(_credit_derisk(), i, _CREDIT_EXEC_LAG),
                   "weight": 1.0, "lag": _CREDIT_EXEC_LAG,
                   "label": "Credit impulse contracting"},
        "margin": {"series": _onto(_margin_derisk(), i, 1), "weight": 0.5, "lag": 1,
                   "label": "Margin-leverage euphoria"},
    }, i)


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #
def _make(cfg: dict) -> StrategySpec:
    score_fn = cfg["score"]
    income = cfg.get("income", 2.0)

    def benchmark(ctx):
        return _cnclose(CSI300)

    def cash_yield(ctx):
        return pd.Series(float(CHINA_CASH_PCT), index=_cnclose(CSI300).index)

    def risk_yield(ctx, income=income):
        return pd.Series(float(income), index=_cnclose(CSI300).index)

    def score(ctx, bench, score_fn=score_fn):
        return score_fn(ctx, bench)

    def alloc(ctx, bench, score_fn=score_fn):
        sc = score_fn(ctx, bench)["score"]
        return ea.glide_path(sc).reindex(bench.index, method="ffill").fillna(1.0)

    return StrategySpec(
        key=cfg["key"], icon=cfg["icon"], name_en=cfg["name_en"], name_zh=cfg["name_zh"],
        thesis_en=cfg["thesis_en"], thesis_zh=cfg["thesis_zh"],
        bench_en="CSI 300", bench_zh="沪深300", cash_en="Cash (MMF)", cash_zh="现金（货基）",
        risk_word_en=cfg["risk_word_en"], risk_word_zh=cfg["risk_word_zh"],
        benchmark=benchmark, alloc=alloc, cash_yield=cash_yield, risk_yield=risk_yield,
        score=score, experimental=True, caveat_en=cfg["caveat_en"], caveat_zh=cfg["caveat_zh"])


_CAV_CREDIT = (
    "China-specific, display-only / experimental. Benchmark = CSI 300 (510300) total-return "
    "ETF close (2012→); the cash sleeve is a flat ~1.8% (onshore cash earns little). The credit "
    "leg rests on the TSF series, which begins 2015 (~136 monthly prints) — a short macro sample; "
    "the print is lagged ~1 month. Full Phase-0 (leave-one-crisis-out, deflated-Sharpe) is a fast-follow.",
    "中国特定，仅展示 / 实验性。基准 = 沪深300（510300）总回报 ETF 收盘价（2012 年起）；现金腿为固定约 "
    "1.8%（境内现金收益很低）。信用腿依赖社融数据，自 2015 年起（约 136 个月度样本）——宏观样本较短；数据滞后约 1 个月。"
    "完整 Phase-0（留一危机、贬值夏普）为后续跟进。")
_CAV_VOL = (
    "China-specific, display-only / experimental. Benchmark = CSI 300 (510300) total-return ETF "
    "close (2012→); cash sleeve a flat ~1.8%. Volatility management is a well-established, "
    "price-orthogonal signal (Moreira-Muir) that also beats buy-&-hold on the deeper Shanghai "
    "Composite — so the edge is not a CSI-300-window artifact. Turnover is higher (~3x/yr). "
    "Full Phase-0 is a fast-follow.",
    "中国特定，仅展示 / 实验性。基准 = 沪深300（510300）总回报 ETF 收盘价（2012 年起）；现金腿固定约 1.8%。"
    "波动率管理是成熟且与价格正交的信号（Moreira-Muir），在更长历史的上证综指上同样跑赢买入持有——因此优势并非"
    "沪深300 区间的偶然。换手率较高（约每年 3 次）。完整 Phase-0 为后续跟进。")


_NEW_CFG: list[dict] = [
    {"key": "cn_credit_vol", "icon": "🪙", "score": _sc_credit_vol,
     "name_en": "Credit-Impulse + Vol-Managed", "name_zh": "信用脉冲 + 波动率管理",
     "risk_word_en": "Credit contracting", "risk_word_zh": "信用收缩", "income": 2.2,
     "thesis_en": "China's #1 driver is the credit cycle, not price trend: own CSI 300 when the credit impulse is positive, step aside when it contracts — with a light vol guard for the panics the slow macro print misses.",
     "thesis_zh": "中国第一驱动力是信用周期而非价格趋势：信用脉冲为正时持有沪深300，收缩时退避——叠加轻量波动率护栏以应对慢宏观数据漏掉的恐慌。",
     "caveat_en": _CAV_CREDIT[0], "caveat_zh": _CAV_CREDIT[1]},
    {"key": "cn_volmanaged", "icon": "🌊", "score": _sc_volmanaged,
     "name_en": "Volatility-Managed CSI 300", "name_zh": "波动率管理 沪深300",
     "risk_word_en": "Vol spiking", "risk_word_zh": "波动率飙升", "income": 2.2,
     "thesis_en": "Moreira-Muir: scale exposure down when CSI 300's own realized volatility is elevated — a price-orthogonal signal that cuts China's deep bears without the mean-reversion whipsaw that sinks trend timers here.",
     "thesis_zh": "Moreira-Muir：当沪深300自身已实现波动率升高时降低敞口——一个与价格正交的信号，可削减中国的深度熊市，又避免趋势择时在此频繁打脸。",
     "caveat_en": _CAV_VOL[0], "caveat_zh": _CAV_VOL[1]},
    {"key": "cn_credit_margin", "icon": "🛡️", "score": _sc_credit_margin,
     "name_en": "Credit + Margin-Euphoria Guard", "name_zh": "信用 + 融资狂热护栏",
     "risk_word_en": "Leverage euphoria", "risk_word_zh": "杠杆狂热", "income": 2.2,
     "thesis_en": "Two slow, fundamentals-based de-risk signals with no price input: lean out of CSI 300 when the credit impulse contracts AND retail margin leverage is at a multi-year euphoric extreme (the 2015-bubble top signal). The shallowest drawdown of the family.",
     "thesis_zh": "两条慢节奏、基本面驱动、不含价格的降险信号：信用脉冲收缩且散户融资杠杆处于多年狂热极值（2015 年泡沫见顶信号）时减仓沪深300。本系列中回撤最浅。",
     "caveat_en": _CAV_CREDIT[0], "caveat_zh": _CAV_CREDIT[1]},
]

CHINA_STRATEGIES: list[StrategySpec] = [_make(c) for c in _NEW_CFG]


def by_key(key: str) -> StrategySpec | None:
    return next((s for s in CHINA_STRATEGIES if s.key == key), None)


# per-leg display metadata (colour + 中文) for the China detail pages' score breakdown
CN_LEG_META = {
    "credit": ("#C0392B", "信用脉冲收缩"),
    "vol": ("#7c3aed", "已实现波动率"),
    "margin": ("#e0a106", "融资杠杆狂热"),
}
# compact stance labels (risk asset / cash) per strategy key
CN_STANCE = {
    "cn_credit_vol": ("CSI 300", "沪深300", "Cash", "现金"),
    "cn_volmanaged": ("CSI 300", "沪深300", "Cash", "现金"),
    "cn_credit_margin": ("CSI 300", "沪深300", "Cash", "现金"),
}
