"""HK market-context chips — pure display-tier context fragments.

Each chip function reads from existing committed stores and returns a small
dict suitable for embedding in the hk_standouts artifact under the key
``context_chips``.  All chips are fail-open: an absent or corrupt store
means the chip is simply absent from the output dict (key not emitted) —
never a build failure.

Return shape per chip (every field present or absent, never raises)::

    {
        "key":          str,              # machine-readable chip id
        "value":        float | None,     # primary numeric value (latest)
        "value_z":      float | None,     # z-score or secondary metric (optional)
        "state_en":     str,              # present-tense EN descriptor
        "state_zh":     str,              # present-tense ZH descriptor
        "as_of":        str | None,       # ISO-8601 date string
        "display_only": True,             # AUTHORITY FENCE — never feeds rank/gate
    }

AUTHORITY FENCE (HKRV-R5): nothing returned here may feed rank / size / gate /
K-counts.  Display / screen tier only.

COPY LAW (HKRV-R2/R3): all state strings are PRESENT-TENSE descriptors.
FORBIDDEN: forward-edge claims, predictive language.  Southbound flow is
CONTEXT ("who the marginal buyer is"), never a confirmer.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _r(v: Any, dec: int = 2) -> float | None:
    """Round to dec places; return None if not finite."""
    try:
        f = float(v)
        return round(f, dec) if np.isfinite(f) else None
    except Exception:
        return None


def _slope_z_scalar(s: pd.Series, slope_window: int, baseline_window: int,
                    use_log: bool = True) -> float | None:
    """Return the latest value of engine.indicators.slope_z(s, ...) as a scalar."""
    try:
        from engine.indicators import slope_z
        z = slope_z(s, slope_window, baseline_window, use_log=use_log)
        v = z.dropna()
        return _r(float(v.iloc[-1])) if not v.empty else None
    except Exception:
        return None


def _rolling_pctile_scalar(s: pd.Series, window: int) -> float | None:
    """Rolling percentile of the latest value within its own trailing window."""
    try:
        s = s.dropna()
        if len(s) < window:
            return None
        tail = s.iloc[-window:]
        v = float(s.iloc[-1])
        pct = float((tail <= v).sum()) / len(tail)
        return _r(pct, 3)
    except Exception:
        return None


def _read_store(group: str, name: str) -> pd.DataFrame | None:
    try:
        from lib import store
        return store.read(group, name)
    except Exception:
        return None


def _last_as_of(df: pd.DataFrame | None) -> str | None:
    try:
        if df is None or df.empty:
            return None
        return str(pd.Timestamp(df.index[-1]).date())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# (a) hstech_rs: HSTECH/HSI ratio 20d slope_z
# ---------------------------------------------------------------------------

def hstech_rs() -> dict | None:
    """HSTECH relative strength vs HSI: 20d slope_z of the price ratio.

    Source: hk store — 3033.HK (CSOP HS TECH ETF, proxy for ^HSTECH) and ^HSI.
    20d slope, 252d baseline.  Positive = HSTECH outperforming HSI.
    """
    try:
        hsi_df = _read_store("hk", "^HSI")
        tech_df = _read_store("hk", "3033.HK")
        if hsi_df is None or tech_df is None:
            return None
        if "close" not in hsi_df.columns or "close" not in tech_df.columns:
            return None
        ratio = (tech_df["close"] / hsi_df["close"].reindex(tech_df.index, method="ffill"))
        ratio = ratio.dropna()
        if len(ratio) < 30:
            return None
        z = _slope_z_scalar(ratio, slope_window=20, baseline_window=252, use_log=True)
        if z is None:
            return None
        if z > 1.0:
            state_en, state_zh = "HSTECH outperforming HSI", "科技股跑赢恒指"
        elif z < -1.0:
            state_en, state_zh = "HSTECH underperforming HSI", "科技股跑输恒指"
        else:
            state_en, state_zh = "HSTECH in line with HSI", "科技股与恒指持平"
        return {
            "key": "hstech_rs",
            "value": z,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(tech_df),
            "display_only": True,
        }
    except Exception as e:
        log.debug("hstech_rs failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (b) ah_compression: HSAHP 20d change z
# ---------------------------------------------------------------------------

def ah_compression() -> dict | None:
    """A/H premium compression: 20d change in the HSAHP index, z-scored vs 252d.

    Source: hk_ah_official/ah_spot.parquet — column 'hsahp' (market-wide A/H
    premium index; >100 = A-shares trade at a premium to H-shares).
    Negative z = premium compressing (A-shares getting cheaper vs HK).
    """
    try:
        df = _read_store("hk_ah_official", "ah_spot")
        if df is None or "hsahp" not in df.columns:
            return None
        s = df["hsahp"].dropna()
        if len(s) < 30:
            return None
        # 20d change z: mean of 20d changes / std of 20d changes over 252d
        chg20 = s.diff(20)
        z_val = _slope_z_scalar(s, slope_window=20, baseline_window=252, use_log=False)
        latest_chg = _r(float(chg20.dropna().iloc[-1])) if not chg20.dropna().empty else None
        latest_val = _r(float(s.iloc[-1]))
        if z_val is None:
            return None
        if z_val > 1.0:
            state_en = "A/H premium widening — A-shares pricier vs HK"
            state_zh = "A/H溢价扩大——A股相对港股更贵"
        elif z_val < -1.0:
            state_en = "A/H premium compressing — A-shares cheaper vs HK"
            state_zh = "A/H溢价收窄——A股相对港股更便宜"
        else:
            state_en = "A/H premium stable"
            state_zh = "A/H溢价稳定"
        return {
            "key": "ah_compression",
            "value": latest_val,
            "value_z": z_val,
            "chg_20d": latest_chg,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(df),
            "display_only": True,
        }
    except Exception as e:
        log.debug("ah_compression failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (c) southbound_agg: market-wide daily net flow level + 20d z
# ---------------------------------------------------------------------------

def southbound_agg() -> dict | None:
    """Aggregate southbound (SH+SZ connect) daily net flow: level + 20d z-score.

    Source: hk_connect/southbound_sh + southbound_sz — 'net' column (HKD mn).
    Present-tense context: who is the marginal buyer, NOT a confirmer.
    """
    try:
        sh = _read_store("hk_connect", "southbound_sh")
        sz = _read_store("hk_connect", "southbound_sz")
        if sh is None and sz is None:
            return None
        # combine on shared index; missing side treated as 0
        frames = []
        if sh is not None and "net" in sh.columns:
            frames.append(sh["net"].rename("sh"))
        if sz is not None and "net" in sz.columns:
            frames.append(sz["net"].rename("sz"))
        if not frames:
            return None
        combined = pd.concat(frames, axis=1).sum(axis=1).sort_index()
        combined = combined.dropna()
        if len(combined) < 5:
            return None
        latest = _r(float(combined.iloc[-1]))
        # 20d z
        z20 = None
        if len(combined) >= 30:
            tail = combined.iloc[-252:]
            mu, sig = float(tail.mean()), float(tail.std())
            if sig > 0:
                z20 = _r((float(combined.iloc[-1]) - mu) / sig)
        if latest is not None and latest > 0:
            state_en = "Southbound net inflow — mainland buyers active"
            state_zh = "南向资金净流入——内地资金主动买入"
        elif latest is not None and latest < 0:
            state_en = "Southbound net outflow — mainland sellers active"
            state_zh = "南向资金净流出——内地资金主动卖出"
        else:
            state_en = "Southbound flow near flat"
            state_zh = "南向资金流量接近持平"
        return {
            "key": "southbound_agg",
            "value": latest,
            "value_z": z20,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(
                sh if sh is not None else sz),
            "display_only": True,
        }
    except Exception as e:
        log.debug("southbound_agg failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (d) peg_funding: HIBOR 1m − SOFR spread + 20d change
# ---------------------------------------------------------------------------

def peg_funding() -> dict | None:
    """HKD peg-funding chip: HIBOR 1m minus SOFR spread + 20d change z.

    Source: hkma/interbank_liquidity (hibor_1m) and fred/SOFR.
    A positive spread means HKD funding is more expensive than USD;
    a sharply rising spread signals peg-defence demand / liquidity tightness.
    """
    try:
        hkma = _read_store("hkma", "interbank_liquidity")
        sofr_df = _read_store("fred", "SOFR")
        if hkma is None or "hibor_1m" not in hkma.columns:
            return None
        if sofr_df is None or sofr_df.empty:
            return None
        hibor = hkma["hibor_1m"].dropna()
        sofr_col = sofr_df.columns[0]
        sofr = sofr_df[sofr_col].dropna()
        combined = pd.concat([hibor.rename("hibor"), sofr.rename("sofr")],
                             axis=1).sort_index().ffill(limit=5)
        spread = (combined["hibor"] - combined["sofr"]).dropna()
        if len(spread) < 30:
            return None
        latest_spread = _r(float(spread.iloc[-1]))
        chg20 = _r(float(spread.diff(20).dropna().iloc[-1])) if len(spread) >= 21 else None
        z20 = None
        if len(spread) >= 252:
            tail = spread.iloc[-252:]
            mu, sig = float(tail.mean()), float(tail.std())
            if sig > 0:
                z20 = _r((float(spread.iloc[-1]) - mu) / sig)
        if latest_spread is not None and latest_spread > 0.5:
            state_en = "HIBOR above SOFR — HKD funding tight"
            state_zh = "港元同业拆借利率高于SOFR——港元资金偏紧"
        elif latest_spread is not None and latest_spread < -0.2:
            state_en = "HIBOR below SOFR — HKD funding loose"
            state_zh = "港元同业拆借利率低于SOFR——港元资金宽松"
        else:
            state_en = "HIBOR-SOFR spread near neutral"
            state_zh = "港元-SOFR利差接近中性"
        as_of = _last_as_of(hkma)
        return {
            "key": "peg_funding",
            "value": latest_spread,
            "value_z": z20,
            "chg_20d": chg20,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": as_of,
            "display_only": True,
        }
    except Exception as e:
        log.debug("peg_funding failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (e) rate_path: ZQ-implied 12m cuts in bp with state
# ---------------------------------------------------------------------------

def rate_path() -> dict | None:
    """Fed rate-path chip: ZQ-implied 12m cuts/hikes in basis points.

    Source: rate_futures/zq_path (m12 column) and fred/DFF (policy rate).
    implied_bp_12m = (zq_m12 − DFF) * 100.  Positive = cuts priced,
    negative = hikes priced.  State as of 07-10 reads 'hikes_priced';
    that honesty is the point.
    """
    try:
        zq_df = _read_store("rate_futures", "zq_path")
        dff_df = _read_store("fred", "DFF")
        if zq_df is None or dff_df is None:
            return None
        m12_col = "m12"
        if m12_col not in zq_df.columns:
            return None
        zq_m12 = zq_df[m12_col].dropna()
        dff_col = dff_df.columns[0]
        dff = dff_df[dff_col].dropna()
        if zq_m12.empty or dff.empty:
            return None
        # align on the most recent shared date
        combined = pd.concat([zq_m12.rename("m12"), dff.rename("dff")],
                             axis=1).sort_index().ffill(limit=5).dropna()
        if combined.empty:
            return None
        last = combined.iloc[-1]
        implied_bp = _r((float(last["m12"]) - float(last["dff"])) * 100, 0)
        latest_m12 = _r(float(last["m12"]))
        latest_dff = _r(float(last["dff"]))
        if implied_bp is None:
            return None
        # state mapping: implied_bp = (zq_m12 − DFF) * 100
        # positive → market prices HIGHER rates 12m out than today → hikes priced
        # negative → market prices LOWER rates 12m out than today → cuts priced
        if implied_bp >= 12.5:
            state = "hikes_priced"
            state_en = "Market prices rate hikes over next 12 months"
            state_zh = "市场为未来12个月定价加息"
        elif implied_bp > -12.5:
            state = "on_hold"
            state_en = "Market prices rates on hold over next 12 months"
            state_zh = "市场预期利率在未来12个月维持不变"
        else:
            state = "cuts_priced"
            state_en = "Market prices rate cuts over next 12 months"
            state_zh = "市场为未来12个月定价降息"
        return {
            "key": "rate_path",
            "value": implied_bp,
            "zq_m12": latest_m12,
            "dff": latest_dff,
            "state": state,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(combined.to_frame() if isinstance(combined, pd.Series) else combined),
            "display_only": True,
        }
    except Exception as e:
        log.debug("rate_path failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (f) cnh_basis: CNH_F − CNH_X z
# ---------------------------------------------------------------------------

def cnh_basis() -> dict | None:
    """Offshore CNH basis: futures (CNH=F) minus spot (CNH=X) z-score.

    A positive basis means the futures price is higher than spot (CNH under
    forward pressure); negative basis means forward discount (capital-outflow
    hedging demand).  Z-scored vs 252d rolling window.
    """
    try:
        cnh_f = _read_store("yahoo", "CNH=F")
        cnh_x = _read_store("yahoo", "CNH=X")
        if cnh_f is None or cnh_x is None:
            return None
        col_f = "close" if "close" in cnh_f.columns else cnh_f.columns[0]
        col_x = "close" if "close" in cnh_x.columns else cnh_x.columns[0]
        combined = pd.concat([cnh_f[col_f].rename("f"), cnh_x[col_x].rename("x")],
                             axis=1).sort_index().ffill(limit=2).dropna()
        basis = (combined["f"] - combined["x"]).dropna()
        if len(basis) < 30:
            return None
        latest = _r(float(basis.iloc[-1]), 5)
        z = None
        if len(basis) >= 252:
            tail = basis.iloc[-252:]
            mu, sig = float(tail.mean()), float(tail.std())
            if sig > 0:
                z = _r((float(basis.iloc[-1]) - mu) / sig)
        if z is not None and z > 1.0:
            state_en = "CNH futures at forward premium vs spot"
            state_zh = "在岸人民币期货溢价高于即期"
        elif z is not None and z < -1.0:
            state_en = "CNH futures at forward discount vs spot"
            state_zh = "在岸人民币期货折价低于即期"
        else:
            state_en = "CNH futures-spot basis near neutral"
            state_zh = "人民币期货-即期基差接近中性"
        return {
            "key": "cnh_basis",
            "value": latest,
            "value_z": z,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(cnh_f),
            "display_only": True,
        }
    except Exception as e:
        log.debug("cnh_basis failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (g) em_dm_rs: EEM/SPY 20/60/120d returns
# ---------------------------------------------------------------------------

def em_dm_rs() -> dict | None:
    """EM vs DM relative strength: EEM/SPY 20d, 60d, 120d return spreads.

    Source: yahoo/EEM and yahoo/SPY (close column).
    Positive = EM outperforming DM; negative = EM lagging.
    """
    try:
        eem = _read_store("yahoo", "EEM")
        spy = _read_store("yahoo", "SPY")
        if eem is None or spy is None:
            return None
        col_e = "close" if "close" in eem.columns else eem.columns[0]
        col_s = "close" if "close" in spy.columns else spy.columns[0]
        combined = pd.concat([eem[col_e].rename("eem"), spy[col_s].rename("spy")],
                             axis=1).sort_index().ffill(limit=2).dropna()
        if len(combined) < 25:
            return None
        results: dict[str, float | None] = {}
        for n, label in [(20, "20d"), (60, "60d"), (120, "120d")]:
            if len(combined) > n:
                r_eem = float(combined["eem"].iloc[-1]) / float(combined["eem"].iloc[-(n + 1)]) - 1.0
                r_spy = float(combined["spy"].iloc[-1]) / float(combined["spy"].iloc[-(n + 1)]) - 1.0
                results[label] = _r((r_eem - r_spy) * 100, 1)
            else:
                results[label] = None
        r20 = results.get("20d")
        if r20 is not None and r20 > 0:
            state_en = "EM outperforming DM in the near term"
            state_zh = "新兴市场近期跑赢发达市场"
        elif r20 is not None and r20 < 0:
            state_en = "EM underperforming DM in the near term"
            state_zh = "新兴市场近期跑输发达市场"
        else:
            state_en = "EM and DM returns near parity"
            state_zh = "新兴市场与发达市场回报接近持平"
        return {
            "key": "em_dm_rs",
            "value_20d": results.get("20d"),
            "value_60d": results.get("60d"),
            "value_120d": results.get("120d"),
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(eem),
            "display_only": True,
        }
    except Exception as e:
        log.debug("em_dm_rs failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (h) ashr_fxi: ASHR/FXI 20/60d spread (onshore vs offshore China)
# ---------------------------------------------------------------------------

def ashr_fxi() -> dict | None:
    """A-share vs offshore China spread: ASHR/FXI 20d and 60d return difference.

    Source: yahoo/ASHR (CSI 300 A-share ETF) and yahoo/FXI (China large-cap ETF).
    Positive = onshore A-shares outperforming offshore; negative = offshore leading.
    """
    try:
        ashr = _read_store("yahoo", "ASHR")
        fxi = _read_store("yahoo", "FXI")
        if ashr is None or fxi is None:
            return None
        col_a = "close" if "close" in ashr.columns else ashr.columns[0]
        col_f = "close" if "close" in fxi.columns else fxi.columns[0]
        combined = pd.concat([ashr[col_a].rename("ashr"), fxi[col_f].rename("fxi")],
                             axis=1).sort_index().ffill(limit=2).dropna()
        if len(combined) < 25:
            return None
        results: dict[str, float | None] = {}
        for n, label in [(20, "20d"), (60, "60d")]:
            if len(combined) > n:
                r_a = float(combined["ashr"].iloc[-1]) / float(combined["ashr"].iloc[-(n + 1)]) - 1.0
                r_f = float(combined["fxi"].iloc[-1]) / float(combined["fxi"].iloc[-(n + 1)]) - 1.0
                results[label] = _r((r_a - r_f) * 100, 1)
            else:
                results[label] = None
        r20 = results.get("20d")
        if r20 is not None and r20 > 1.0:
            state_en = "A-shares outperforming offshore China"
            state_zh = "A股跑赢境外中国股"
        elif r20 is not None and r20 < -1.0:
            state_en = "Offshore China outperforming A-shares"
            state_zh = "境外中国股跑赢A股"
        else:
            state_en = "A-share and offshore China returns near parity"
            state_zh = "A股与境外中国股回报接近持平"
        return {
            "key": "ashr_fxi",
            "value_20d": results.get("20d"),
            "value_60d": results.get("60d"),
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(ashr),
            "display_only": True,
        }
    except Exception as e:
        log.debug("ashr_fxi failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# (i) vhsi_pctile: ^HSIL 252d rolling percentile
# ---------------------------------------------------------------------------

def vhsi_pctile() -> dict | None:
    """VHSI (^HSIL) rolling 252d percentile — HK implied volatility positioning.

    Source: hk store, ticker ^HSIL.  Percentile of the latest close within its
    own trailing 252-session window (no lookahead).  High pctile = elevated fear.
    """
    try:
        df = _read_store("hk", "^HSIL")
        if df is None or "close" not in df.columns:
            return None
        s = df["close"].dropna()
        if len(s) < 30:
            return None
        latest_val = _r(float(s.iloc[-1]))
        pct = _rolling_pctile_scalar(s, window=252)
        if pct is None and len(s) >= 30:
            # fall back to whatever history we have
            pct = _rolling_pctile_scalar(s, window=len(s))
        if pct is not None and pct >= 0.8:
            state_en = "VHSI elevated — above 80th pctile of past year"
            state_zh = "波动率指数偏高——超过过去一年80百分位"
        elif pct is not None and pct <= 0.2:
            state_en = "VHSI depressed — below 20th pctile of past year"
            state_zh = "波动率指数偏低——低于过去一年20百分位"
        else:
            state_en = "VHSI in mid-range"
            state_zh = "波动率指数处于中等水平"
        return {
            "key": "vhsi_pctile",
            "value": latest_val,
            "pctile_252d": pct,
            "state_en": state_en,
            "state_zh": state_zh,
            "as_of": _last_as_of(df),
            "display_only": True,
        }
    except Exception as e:
        log.debug("vhsi_pctile failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# aggregate: compute all chips, fail-open on each
# ---------------------------------------------------------------------------

_CHIP_FUNCS = [
    hstech_rs,
    ah_compression,
    southbound_agg,
    peg_funding,
    rate_path,
    cnh_basis,
    em_dm_rs,
    ashr_fxi,
    vhsi_pctile,
]


def compute_all() -> dict[str, dict]:
    """Run every chip function; return a dict keyed by chip 'key'.

    Absent / error chips are silently dropped — never raises.
    """
    out: dict[str, dict] = {}
    for fn in _CHIP_FUNCS:
        try:
            chip = fn()
            if chip and isinstance(chip, dict) and "key" in chip:
                out[chip["key"]] = chip
        except Exception as e:  # noqa: BLE001 — each chip is independent
            log.debug("context chip %s failed: %s", fn.__name__, e)
    return out
