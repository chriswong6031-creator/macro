"""FX Stress & Regime Radar — read the JOINT configuration of currency moves.

The rest of the forex page reads the dollar regime and scores each pair on its
idiosyncratic (ex-dollar) residual. This module adds the layer the user asked for:
read the *configuration across currencies* — using BOTH the literal move and its
VELOCITY / ACCELERATION — to NAME the macro scenario it looks like (carry unwind,
broad-dollar tightening, EM capital flight, acute safe-haven flight, reflation
melt-up, FX-intervention risk) and attach an HONEST, EMPIRICAL probability.

What "probability" means here (load-bearing honesty):
  It is a PAST-TENSE conditional base rate, never a forecast. For each scenario we
  build a causal stress INTENSITY in [0,1] over all history, define a leak-free
  forward ADVERSE OUTCOME (e.g. the carry basket drawing down >=6% within 10d), and
  report P(outcome | intensity >= today's intensity) measured over the whole record,
  alongside the unconditional base rate, the sample count n (and an overlap-deflated
  n_eff = n/N), and a Wilson 95% interval on both. "On the N days at least this
  stressed, X% saw the adverse move within Nd (base rate B%)." We did NOT search a
  threshold to maximize this — today's reading is the only condition — so there is no
  multiple-testing bias to correct, and no peg-window excision (this is a descriptive
  realized frequency, not a fitted UIP/carry weight).

Strictly causal: every intensity leg at t uses only data <= t (rolling moments are
shift(1)-ed to exclude t); the forward label uses (t, t+N] identically across all
history; y_t is NaN for t > T-N. DISPLAY-ONLY: nothing here is ever scored, fed to a
conviction/allocation, or collapsed into BUY/SELL. Pegs (managed USD/CNH) and
interventions (USD/JPY MoF, SNB) truncate distributions — those scenarios carry an
`illustrative` flag. FX direction is famously unforecastable (Meese-Rogoff); this is
the observed base rate, not a forecast.

Pure module: every function guards missing data and returns {} (or a degraded dict)
rather than raising, so build_forex can never break the site. See LIMITATIONS.md and
research/FOREX_DASHBOARD.md (§7 honesty bar).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import forex_signals as fxs

log = logging.getLogger(__name__)

EPS = 1e-9


def _slog(s: pd.Series) -> pd.Series:
    """log() that NaNs out non-positive values (WTI went negative in Apr-2020)."""
    return np.log(s.where(s > 0))

# Currency archetype groups (base codes; rising strength = base appreciates vs USD).
FUNDERS = ["JPY", "CHF"]                       # havens / funders rally in risk-off
CARRY = ["AUD", "MXN", "BRL"]                  # high-carry / commodity / EM risk
RISK_BROAD = ["AUD", "CAD", "MXN", "BRL", "EUR", "GBP"]
RISK_REFL = ["AUD", "CAD", "MXN", "BRL"]
EM = ["MXN", "BRL", "CNH"]
ADV = ["EUR", "GBP", "JPY"]


# --------------------------------------------------------------------------- #
# causal velocity / level primitives
# --------------------------------------------------------------------------- #
def _z_causal(g: pd.Series, w: int = 252, mp: int = 60) -> pd.Series:
    """Rolling z-score whose mean/std EXCLUDE t (shift(1) the moments) — strictly
    causal: z_t uses only the distribution of g strictly before t."""
    g = g.astype(float)
    m = g.rolling(w, min_periods=mp).mean().shift(1)
    sd = g.rolling(w, min_periods=mp).std().shift(1)
    # clip to a sane range: a near-constant rolling window (sparse/stale series) can make
    # sd→0 and z explode to hundreds of sigma; the leg only needs "extreme", so cap it.
    return ((g - m) / sd.replace(0, np.nan)).clip(-8.0, 8.0)


def _ewma_vol(r: pd.Series, halflife: int = 20) -> pd.Series:
    """Causal EWMA realized vol = sqrt(EWMA(r^2)); floored so velocity never blows up."""
    v = np.sqrt(r.pow(2).ewm(halflife=halflife, min_periods=max(5, halflife // 2)).mean())
    floor = v.rolling(252, min_periods=20).median() * 0.25
    return v.clip(lower=floor.fillna(EPS)).replace(0, np.nan)


def _velocity(level: pd.Series, length: int = 5, halflife: int = 20) -> pd.Series:
    """Speed of the recent move = mean per-day log return over `length` / EWMA vol.
    Coincident (uses data <= t); higher |.| = a faster move."""
    lg = _slog(level)
    r = lg.diff()
    ret = lg.diff(length) / float(length)
    return ret / _ewma_vol(r, halflife)


def _accel(vel: pd.Series) -> pd.Series:
    return vel.diff()


def _pctile_causal(s: pd.Series, lb: int) -> pd.Series:
    """Rolling percentile rank of s_t within its trailing `lb` window (incl. t)."""
    mp = max(60, lb // 8)
    return s.rolling(lb, min_periods=mp).apply(
        lambda x: (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan, raw=True)


def _dist_to_ma_z(s: pd.Series, ma: int = 200, w: int = 756, mp: int = 120) -> pd.Series:
    """Distance of s above its `ma`-day MA, in z-units of that distance (causal)."""
    d = s - s.rolling(ma, min_periods=ma // 2).mean()
    return _z_causal(d, w, mp)


def _basket(strength: dict, members: list[str], idx: pd.Index) -> pd.Series | None:
    """Equal-weight log-strength index over the present members (mean of log prices)."""
    cols = [strength[m].reindex(idx) for m in members if m in strength]
    if not cols:
        return None
    return pd.concat(cols, axis=1).mean(axis=1)


def _mean_pairwise_corr(rets: dict, members: list[str], idx: pd.Index, w: int) -> pd.Series | None:
    """Mean of the rolling pairwise correlations among the members' return series."""
    present = [m for m in members if m in rets]
    if len(present) < 2:
        return None
    mp = max(5, w // 2)
    pair_corrs = []
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            a = rets[present[i]].reindex(idx)
            b = rets[present[j]].reindex(idx)
            pair_corrs.append(a.rolling(w, min_periods=mp).corr(b))
    if not pair_corrs:
        return None
    return pd.concat(pair_corrs, axis=1).mean(axis=1)


# --------------------------------------------------------------------------- #
# leg intensity helpers
# --------------------------------------------------------------------------- #
def _sub_intensity(drive: pd.Series, thr: float) -> pd.Series:
    """Map a positive-toward-scenario "drive" to a sub-intensity in [0,1], rescaled
    so the fire threshold sits at ~0.6 and saturates near 1.5x the threshold."""
    if thr == 0:
        thr = 1.0
    z = drive * (2.0 / abs(thr))                       # threshold -> z≈2
    return ((z - 0.5) / 2.5).clip(0.0, 1.0)


def _leg_value(drive: float | None, thr: float) -> float | None:
    """Signed [-1,1] value for the fbar display (≈0.67 at the fire threshold)."""
    if drive is None or not np.isfinite(drive) or thr == 0:
        return None
    return float(np.clip(drive / (abs(thr) * 1.5), -1.0, 1.0))


def _and(*series: pd.Series) -> pd.Series:
    """AND of several z-like drives = their elementwise minimum (all must be high)."""
    return pd.concat(list(series), axis=1).min(axis=1)


def _or(*series: pd.Series) -> pd.Series:
    return pd.concat(list(series), axis=1).max(axis=1)


# --------------------------------------------------------------------------- #
# forward (leak-free) outcome helpers — strictly (t, t+N]
# --------------------------------------------------------------------------- #
def _fwd_extreme(s: pd.Series, n: int, kind: str) -> pd.Series:
    """Extreme (min/max) of s over the FORWARD window (t, t+N]. NaN if < n forward obs."""
    fut = s.shift(-1)                                  # start at t+1
    rev = fut[::-1].rolling(n, min_periods=n).agg("min" if kind == "min" else "max")[::-1]
    return rev


def _fwd_drawdown(level: pd.Series, n: int) -> pd.Series:
    """Worst forward return over (t, t+N] = min(level[t+1..t+N]) / level_t - 1."""
    fmin = _fwd_extreme(level, n, "min")
    return fmin / level - 1.0


def _fwd_runup(level: pd.Series, n: int) -> pd.Series:
    fmax = _fwd_extreme(level, n, "max")
    return fmax / level - 1.0


def _fwd_max_increase(level: pd.Series, n: int) -> pd.Series:
    """Largest forward INCREASE in level over (t, t+N] (for spreads/OAS in pct pts)."""
    return _fwd_extreme(level, n, "max") - level


def _fwd_count_above(s: pd.Series, n: int, thresh: float) -> pd.Series:
    above = (s > thresh).astype(float).shift(-1)
    return above[::-1].rolling(n, min_periods=n).sum()[::-1]


def _fwd_min_daily_ret(level: pd.Series, n: int) -> pd.Series:
    """Worst single-day return within (t, t+N] (intervention-gap detector)."""
    r1 = level.pct_change()
    return _fwd_extreme(r1, n, "min")


# --------------------------------------------------------------------------- #
# feature panel
# --------------------------------------------------------------------------- #
def _build_features(strength: dict, resid_ret: dict, drivers: dict, results: dict,
                    idx: pd.Index, cfg: dict) -> dict:
    """All named feature series the scenario legs reference, computed once, causal."""
    rcfg = cfg.get("regime", {})
    zw = int(rcfg.get("z_lookback_d", 252))
    zmp = int(rcfg.get("z_min_periods", 60))
    hl = int(rcfg.get("ewma_halflife_d", 20))
    F: dict[str, pd.Series] = {}

    def drv(name):
        s = drivers.get(name)
        return None if s is None else s.reindex(idx).ffill()

    def basket_ret_z(members, w, zlb=zw, zmp_=zmp):
        b = _basket(strength, members, idx)
        if b is None:
            return None
        return _z_causal(b.diff(w), zlb, zmp_)

    # --- cross-currency velocity baskets (strength = base-vs-USD, rising=base up) ---
    F["funder_5d_z"] = basket_ret_z(FUNDERS, 5)
    F["funder_20d_z"] = basket_ret_z(FUNDERS, 20)
    F["carry_5d_z"] = basket_ret_z(CARRY, 5)
    F["risk_5d_z"] = basket_ret_z(RISK_BROAD, 5)
    F["risk_20d_z"] = basket_ret_z(RISK_REFL, 20)
    F["em_10d_z"] = basket_ret_z(EM, 10)
    F["adv_10d_z"] = basket_ret_z(ADV, 10)

    # carry unwind discriminator: funders surging while carry crashes (nets the USD leg)
    if F.get("funder_5d_z") is not None and F.get("carry_5d_z") is not None:
        F["funder_minus_carry"] = F["funder_5d_z"] - F["carry_5d_z"]
    if F.get("risk_20d_z") is not None and F.get("funder_20d_z") is not None:
        F["risk_minus_funder"] = F["risk_20d_z"] - F["funder_20d_z"]

    # JPY acceleration (yen disorderly strength)
    if "JPY" in strength:
        vel = _velocity(strength["JPY"], 5, hl).reindex(idx)
        F["jpy_accel_z"] = _z_causal(_accel(vel), zw, zmp)

    # breadth: share of the 9 pairs where USD strengthened over 20d
    usd_up = []
    for base, s in strength.items():
        if base == "USD":
            continue
        usd_up.append((s.reindex(idx).diff(20) < 0).astype(float))   # base WEAKER vs USD
    if usd_up:
        F["usd_up_breadth"] = pd.concat(usd_up, axis=1).mean(axis=1)

    # risk-basket breadth down (share of risk legs falling over 5d)
    risk_dn = [(strength[m].reindex(idx).diff(5) < 0).astype(float) for m in RISK_BROAD if m in strength]
    if risk_dn:
        F["risk_dn_breadth"] = pd.concat(risk_dn, axis=1).mean(axis=1)

    # residual co-movement (contagion / dispersion)
    F["carry_resid_corr"] = _mean_pairwise_corr(resid_ret, ["AUD", "MXN", "BRL"], idx, 10)
    F["all_resid_corr"] = _mean_pairwise_corr(resid_ret, list(resid_ret.keys()), idx, 20)

    # --- dollar legs ---
    bdxy = drv("broad_dollar")
    if bdxy is not None:
        lg = _slog(bdxy)
        F["bdxy_20d_z"] = _z_causal(lg.diff(20), 756, 120)
        F["bdxy_pctile"] = _pctile_causal(bdxy, 1260)
        F["bdxy_dist200_z"] = _dist_to_ma_z(bdxy, 200, 756, 120)
    for nm, key in (("broad_afe", "afe_20d_z"), ("broad_eme", "eme_20d_z")):
        s = drv(nm)
        if s is not None:
            F[key] = _z_causal(_slog(s).diff(20), 756, 120)

    # --- risk drivers ---
    vix = drv("vix")
    if vix is not None:
        F["vix_level"] = vix
        F["dvix_z"] = _z_causal(vix.diff(1), zw, zmp)
        F["vix_pctile"] = _pctile_causal(vix, 756)
    move = drv("move")
    if move is not None:
        F["dmove_z"] = _z_causal(move.diff(1), zw, zmp)
    hy = drv("hy_oas")
    if hy is not None:
        F["hy_d5_z"] = _z_causal(hy.diff(5), zw, zmp)
        F["hy_pctile"] = _pctile_causal(hy, 756)
        F["hy_d20_z"] = _z_causal(hy.diff(20), zw, zmp)
    emoas = drv("em_oas")
    if emoas is not None:
        F["emoas_d5_z"] = _z_causal(emoas.diff(5), zw, zmp)
        F["emoas_pctile"] = _pctile_causal(emoas, 504)
    real = drv("us10y_real")
    if real is not None:
        F["dreal_20d_z"] = _z_causal(real.diff(20), zw, zmp)
    nfci = drv("nfci")
    if nfci is not None:
        F["dnfci_20d_z"] = _z_causal(nfci.diff(20), zw, zmp)
    be = drv("breakeven_10y")
    if be is not None:
        F["dbe_20d_z"] = _z_causal(be.diff(20), zw, zmp)
    for nm, k5, k20 in (("copper", "copper_5d_z", "copper_20d_z"),
                        ("gold", "gold_5d_z", None), ("oil", None, "oil_20d_z")):
        s = drv(nm)
        if s is None:
            continue
        lg = _slog(s)
        if k5:
            F[k5] = _z_causal(lg.diff(5), zw, zmp)
        if k20:
            F[k20] = _z_causal(lg.diff(20), zw, zmp)
    spy = drv("spy")
    if spy is not None:
        lg = _slog(spy)
        F["spy_5d_z"] = _z_causal(lg.diff(5), zw, zmp)
    eem = drv("eem")
    if eem is not None:
        F["eem_10d_z"] = _z_causal(_slog(eem).diff(10), zw, zmp)

    # gold-minus-spy flight-to-safety dispersion
    if F.get("gold_5d_z") is not None and F.get("spy_5d_z") is not None:
        F["gold_minus_spy"] = F["gold_5d_z"] - F["spy_5d_z"]

    # CNH offshore-onshore basis (positive bps = offshore weaker = outflow stress)
    cnh = _cnh_basis_series(results, drivers, idx)
    if cnh is not None:
        F["cnh_basis_bps"] = cnh
        F["cnh_basis_5d_z"] = _z_causal(cnh.diff(5), zw, zmp)

    # EM strength drawdown (MXN/BRL/CNH) from trailing peak
    emb = _basket(strength, EM, idx)
    if emb is not None:
        lvl = np.exp(emb)
        F["em_drawdown"] = lvl / lvl.rolling(252, min_periods=60).max() - 1.0

    # --- USD/JPY intervention features (on the quote, ≈161) ---
    if "JPY" in strength:
        quote = np.exp(-strength["JPY"]).reindex(idx)     # USDJPY quote = 1/(JPY-vs-USD)
        F["usdjpy_quote"] = quote
        F["usdjpy_20d_ret"] = np.log(quote).diff(20)
        F["usdjpy_20d_z"] = _z_causal(np.log(quote).diff(20), zw, zmp)
        F["usdjpy_pctile"] = _pctile_causal(quote, 252)
        F["usdjpy_new_high"] = (quote >= quote.rolling(252, min_periods=120).max() - EPS).astype(float)
        up = (quote.diff() > 0).astype(float)
        F["usdjpy_persist"] = up.rolling(10, min_periods=10).mean()
        rv = quote.pct_change().rolling(5).std()
        F["usdjpy_rvol_z"] = _z_causal(rv, zw, zmp)
    if "CHF" in strength:
        F["chf_vel_z"] = _z_causal(_velocity(strength["CHF"], 5, hl).reindex(idx), zw, zmp)
    us2 = drv("us2y")
    if us2 is not None and "JPY" in strength:
        # US-JP front-end rate-differential trend (jp short via results carry_diff proxy unavailable here)
        F["us2y_20d_z"] = _z_causal(us2.diff(20), zw, zmp)

    return F


def _cnh_basis_series(results: dict, drivers: dict, idx: pd.Index) -> pd.Series | None:
    """Offshore(CNH=F) vs onshore(DEXCHUS) basis in bps via forex_signals.cnh_basis."""
    cnh = results.get("USDCNH")
    on = drivers.get("cny_onshore")
    if cnh is None or on is None or "close" not in cnh:
        return None
    try:
        off = (1.0 / cnh["close"]).rename("off")        # close is CNH-vs-USD (inverted) -> raw USD/CNH
        b = fxs.cnh_basis(off, on, {})
        return b["cnh_basis_bps"].reindex(idx)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# scenario registry — each leg: (id, kind, en, zh, make(F)->drive, thr)
# drive is positive-toward-the-scenario; fired = drive >= thr.
# --------------------------------------------------------------------------- #
def _f(F, name):
    return F.get(name)


def _scenarios() -> list[dict]:
    def L(id_, kind, en, zh, make, thr):
        return {"id": id_, "kind": kind, "en": en, "zh": zh, "make": make, "thr": thr}

    return [
        {"key": "carry_unwind", "name_en": "Carry Unwind / Yen-Funded Deleveraging",
         "name_zh": "套息平仓 / 日元融资去杠杆", "min_legs": 3, "N": 10, "illustrative": False,
         "disc_en": "Funders surge while carry/EM crash together — the discriminator vs a plain dollar move.",
         "disc_zh": "融资货币飙升、套息/新兴市场同步崩跌 — 区别于单纯美元波动的关键。",
         "legs": [
             L("funder_5d_z", "velocity", "Funders (JPY/CHF) surging", "融资货币（日元/瑞郎）飙升",
               lambda F: _f(F, "funder_5d_z"), 2.5),
             L("carry_5d_z", "velocity", "Carry basket (AUD/MXN/BRL) crashing", "套息篮子（澳/墨/巴）崩跌",
               lambda F: (-_f(F, "carry_5d_z")) if _f(F, "carry_5d_z") is not None else None, 2.0),
             L("funder_minus_carry", "cross_currency", "Funder−carry divergence", "融资−套息背离",
               lambda F: _f(F, "funder_minus_carry"), 4.0),
             L("carry_resid_corr", "cross_currency", "EM residual co-movement (contagion)", "新兴残差共动（传染）",
               lambda F: (_f(F, "carry_resid_corr") / 0.3) if _f(F, "carry_resid_corr") is not None else None, 2.0),
             L("dvix_z", "risk_driver", "Equity-vol spike", "股市波动飙升",
               lambda F: _f(F, "dvix_z"), 2.0),
             L("jpy_accel_z", "velocity", "Yen acceleration", "日元加速",
               lambda F: _f(F, "jpy_accel_z"), 2.0),
         ]},
        {"key": "dollar_wrecking_ball", "name_en": "Broad-Dollar Wrecking Ball / Global Tightening",
         "name_zh": "广义美元压路机 / 全球紧缩", "min_legs": 3, "N": 20, "illustrative": False,
         "disc_en": "Broad USD strength across BOTH advanced and EM legs, on broad breadth — a global squeeze, not one pair.",
         "disc_zh": "美元在发达与新兴两端全面走强、广度高 — 全球性挤压而非单一货币对。",
         "legs": [
             L("bdxy_20d_z", "velocity", "Broad USD rising fast", "广义美元快速上行",
               lambda F: _f(F, "bdxy_20d_z"), 1.5),
             L("bdxy_pctile", "level", "Broad USD stretched (level)", "广义美元水平偏高",
               lambda F: ((_f(F, "bdxy_pctile") - 0.5) / 0.15) if _f(F, "bdxy_pctile") is not None else None, 2.33),
             L("usd_up_breadth", "cross_currency", "USD up vs most pairs (breadth)", "美元对多数货币上行（广度）",
               lambda F: ((_f(F, "usd_up_breadth") - 0.5) / 0.15) if _f(F, "usd_up_breadth") is not None else None, 1.87),
             L("adv_vs_em_usd", "cross_currency", "Advanced AND EM USD legs up", "发达与新兴美元同步走强",
               lambda F: _and(_f(F, "afe_20d_z"), _f(F, "eme_20d_z"))
               if _f(F, "afe_20d_z") is not None and _f(F, "eme_20d_z") is not None else None, 1.0),
             L("dreal_20d_z", "risk_driver", "Real yields rising", "实际收益率上行",
               lambda F: _f(F, "dreal_20d_z"), 1.0),
             L("dnfci_20d_z", "risk_driver", "Financial conditions tightening", "金融条件收紧",
               lambda F: _f(F, "dnfci_20d_z"), 1.0),
         ]},
        {"key": "em_crisis_capital_flight", "name_en": "EM Crisis / Capital Flight",
         "name_zh": "新兴市场危机 / 资本外逃", "min_legs": 3, "N": 20, "illustrative": True,
         "disc_en": "EM uniquely punished (vs advanced FX) with credit + CNH-basis stress — managed CNH makes this illustrative.",
         "disc_zh": "新兴市场（相对发达货币）独受打击，伴随信用与离岸人民币基差压力 — 受管理的离岸人民币使其仅供示意。",
         "legs": [
             L("em_resid_10d_z", "velocity", "EM weakening (ex-dollar)", "新兴走弱（剔除美元）",
               lambda F: (-_f(F, "em_10d_z")) if _f(F, "em_10d_z") is not None else None, 2.0),
             L("em_minus_adv_z", "cross_currency", "EM punished vs advanced FX", "新兴相对发达货币受罚",
               # eme_20d_z>0 = EM weak vs USD; adv_10d_z>0 = advanced FX strong vs USD. Their SUM
               # is high only when EM falls WHILE advanced holds/rallies (EM-specific), and stays
               # quiet in a broad USD-up move where advanced ALSO weakens — the discriminator.
               lambda F: (_f(F, "eme_20d_z") + _f(F, "adv_10d_z"))
               if _f(F, "eme_20d_z") is not None and _f(F, "adv_10d_z") is not None else None, 1.5),
             L("emoas_d5_z", "risk_driver", "EM credit spreads widening", "新兴信用利差走阔",
               lambda F: _or(_f(F, "emoas_d5_z"), ((_f(F, "emoas_pctile") - 0.5) / 0.15) if _f(F, "emoas_pctile") is not None else None)
               if _f(F, "emoas_d5_z") is not None else None, 2.0),
             L("cnh_basis", "cross_currency", "Offshore CNH outflow stress", "离岸人民币外流压力",
               lambda F: (_f(F, "cnh_basis_bps") / 100.0) if _f(F, "cnh_basis_bps") is not None else None, 2.0),
             L("em_fx_drawdown", "level", "EM-FX drawdown from peak", "新兴货币自高点回撤",
               lambda F: ((-_f(F, "em_drawdown")) / 0.05) if _f(F, "em_drawdown") is not None else None, 2.0),
             L("eem_10d_z", "risk_driver", "EM equities falling", "新兴股市下跌",
               lambda F: (-_f(F, "eem_10d_z")) if _f(F, "eem_10d_z") is not None else None, 1.5),
         ]},
        {"key": "haven_flight_risk_off", "name_en": "Acute Safe-Haven Flight / Risk-Off",
         "name_zh": "急性避险 / 风险规避", "min_legs": 3, "N": 15, "illustrative": False,
         "disc_en": "Havens (USD/JPY/CHF/gold) bid as risk currencies fall broadly, with a vol & credit spike.",
         "disc_zh": "避险资产（美元/日元/瑞郎/黄金）受买盘，风险货币普跌，波动与信用同步飙升。",
         "legs": [
             L("haven_5d_z", "velocity", "Haven basket bid", "避险篮子受买盘",
               lambda F: _f(F, "funder_5d_z"), 2.0),
             L("risk_dn_breadth", "cross_currency", "Risk currencies falling (breadth)", "风险货币普跌（广度）",
               lambda F: _and(((_f(F, "risk_dn_breadth") - 0.5) / 0.15) if _f(F, "risk_dn_breadth") is not None else None,
                              (-_f(F, "risk_5d_z")) if _f(F, "risk_5d_z") is not None else None)
               if _f(F, "risk_dn_breadth") is not None and _f(F, "risk_5d_z") is not None else None, 1.87),
             L("vol_spike", "risk_driver", "Equity/bond vol spike", "股/债波动飙升",
               lambda F: _or(_f(F, "dvix_z"), _f(F, "dmove_z")) if _f(F, "dvix_z") is not None else None, 2.5),
             L("hy_d5_z", "risk_driver", "HY credit spreads widening", "高收益信用利差走阔",
               lambda F: _or(_f(F, "hy_d5_z"), ((_f(F, "hy_pctile") - 0.5) / 0.12) if _f(F, "hy_pctile") is not None else None)
               if _f(F, "hy_d5_z") is not None else None, 2.0),
             L("growth_scare", "cross_currency", "Growth-scare (copper + commodity-FX down)", "增长恐慌（铜与商品货币下跌）",
               lambda F: _and((-_f(F, "copper_5d_z")) if _f(F, "copper_5d_z") is not None else None,
                              (-_f(F, "risk_5d_z")) if _f(F, "risk_5d_z") is not None else None)
               if _f(F, "copper_5d_z") is not None and _f(F, "risk_5d_z") is not None else None, 1.5),
             L("gold_minus_spy", "level", "Gold outrunning equities", "黄金跑赢股票",
               lambda F: _f(F, "gold_minus_spy"), 2.5),
         ]},
        {"key": "reflation_risk_on", "name_en": "Reflation / Risk-On Melt-Up",
         "name_zh": "再通胀 / 风险偏好上行", "min_legs": 3, "N": 20, "illustrative": False,
         "disc_en": "Risk/commodity currencies lead funders with easy credit & low vol — the mirror of carry unwind (overextension is the risk).",
         "disc_zh": "风险/商品货币领先融资货币，信用宽松、波动低 — 套息平仓的镜像（过度延伸才是风险）。",
         "legs": [
             L("risk_20d_z", "velocity", "Risk/commodity FX leading", "风险/商品货币领先",
               lambda F: _f(F, "risk_20d_z"), 1.5),
             L("risk_minus_funder", "cross_currency", "Risk−funder divergence", "风险−融资背离",
               lambda F: _f(F, "risk_minus_funder"), 2.5),
             L("commodity_tailwind", "risk_driver", "Copper & oil tailwind", "铜与原油顺风",
               lambda F: _and(_f(F, "copper_20d_z"), _f(F, "oil_20d_z"))
               if _f(F, "copper_20d_z") is not None and _f(F, "oil_20d_z") is not None else None, 1.0),
             L("credit_vol_compress", "risk_driver", "Credit tightening & vol low", "信用收窄、波动低",
               lambda F: _and((-_f(F, "hy_d20_z")) if _f(F, "hy_d20_z") is not None else None,
                              ((0.3 - _f(F, "vix_pctile")) / 0.15) if _f(F, "vix_pctile") is not None else None)
               if _f(F, "hy_d20_z") is not None and _f(F, "vix_pctile") is not None else None, 1.0),
             L("dbe_20d_z", "risk_driver", "Inflation breakevens rising", "通胀盈亏平衡上行",
               lambda F: _f(F, "dbe_20d_z"), 1.0),
             L("low_resid_corr", "level", "FX dispersion (benign)", "外汇分化（良性）",
               lambda F: ((0.35 - _f(F, "all_resid_corr")) / 0.15) if _f(F, "all_resid_corr") is not None else None, 1.0),
         ]},
        {"key": "intervention_risk", "name_en": "FX Intervention Risk (BoJ/MoF · SNB)",
         "name_zh": "外汇干预风险（日银/财务省 · 瑞士央行）", "min_legs": 2, "N": 10, "illustrative": True,
         "disc_en": "Disorderly one-way USD/JPY into stretched highs (or CHF/CNH strain) — official intervention truncates the distribution.",
         "disc_zh": "美元/日元单边无序冲向偏高水平（或瑞郎/离岸人民币承压）— 官方干预会截断分布。",
         "legs": [
             L("usdjpy_velocity", "velocity", "USD/JPY rising fast (yen weak)", "美元/日元快速上行（日元偏弱）",
               lambda F: _f(F, "usdjpy_20d_z"), 2.0),
             L("usdjpy_level", "level", "USD/JPY at stretched highs", "美元/日元处于偏高水平",
               lambda F: _and(((_f(F, "usdjpy_pctile") - 0.5) / 0.15) if _f(F, "usdjpy_pctile") is not None else None,
                              (_f(F, "usdjpy_new_high") * 3.0) if _f(F, "usdjpy_new_high") is not None else None)
               if _f(F, "usdjpy_pctile") is not None and _f(F, "usdjpy_new_high") is not None else None, 3.0),
             L("usdjpy_persistence", "velocity", "Disorderly one-way move", "无序单边走势",
               lambda F: _and(((_f(F, "usdjpy_persist") - 0.5) / 0.15) if _f(F, "usdjpy_persist") is not None else None,
                              _f(F, "usdjpy_rvol_z"))
               if _f(F, "usdjpy_persist") is not None and _f(F, "usdjpy_rvol_z") is not None else None, 1.0),
             L("snb_cnh_strain", "level", "CHF haven inflow / CNH strain", "瑞郎避险流入 / 离岸人民币承压",
               lambda F: _or(_f(F, "chf_vel_z"), (_f(F, "cnh_basis_5d_z")) if _f(F, "cnh_basis_5d_z") is not None else None)
               if _f(F, "chf_vel_z") is not None else None, 2.0),
             L("rate_diff_context", "risk_driver", "US-front-end rate trend (context)", "美国短端利率趋势（背景）",
               lambda F: _f(F, "us2y_20d_z"), 1.0),
         ]},
    ]


# --------------------------------------------------------------------------- #
# forward labels per scenario (leak-free)
# --------------------------------------------------------------------------- #
def _forward_labels(F: dict, strength: dict, drivers: dict, idx: pd.Index, cfg: dict) -> dict:
    """y_t in {0,1}: did this scenario's defining adverse outcome occur in (t, t+N]?"""
    rcfg = cfg.get("regime", {})
    th = (rcfg.get("scenarios", {}) or {})

    def drv(name):
        s = drivers.get(name)
        return None if s is None else s.reindex(idx).ffill()

    def basket_level(members):
        b = _basket(strength, members, idx)
        return None if b is None else np.exp(b)

    Y: dict[str, pd.Series] = {}
    spy = drv("spy")
    eem = drv("eem")
    vix = drv("vix")
    hy = drv("hy_oas")
    emoas = drv("em_oas")

    def _theta(key, sub, default):
        return float(((th.get(key, {}) or {}).get("theta", {}) or {}).get(sub, default))

    # carry unwind: carry basket DD <=-6% OR SPY <=-8% OR VIX>35 within 10d
    carry_lvl = basket_level(CARRY)
    if carry_lvl is not None:
        cond = _fwd_drawdown(carry_lvl, 10) <= _theta("carry_unwind", "carry_dd", -0.06)
        if spy is not None:
            cond = cond | (_fwd_drawdown(spy, 10) <= _theta("carry_unwind", "spy_dd", -0.08))
        if vix is not None:
            cond = cond | (_fwd_count_above(vix, 10, _theta("carry_unwind", "vix_level", 35)) >= 1)
        Y["carry_unwind"] = _mask_tail(cond, carry_lvl, 10)

    # dollar wrecking ball: EEM DD <=-8% OR EM_OAS +75bp within 20d
    if eem is not None:
        cond = _fwd_drawdown(eem, 20) <= _theta("dollar_wrecking_ball", "eem_dd", -0.08)
        if emoas is not None:
            cond = cond | (_fwd_max_increase(emoas, 20) >= _theta("dollar_wrecking_ball", "emoas_bp", 75) / 100.0)
        Y["dollar_wrecking_ball"] = _mask_tail(cond, eem, 20)

    # EM crisis: EM basket further DD <=-8% OR EM_OAS +150bp within 20d
    em_lvl = basket_level(EM)
    if em_lvl is not None:
        cond = _fwd_drawdown(em_lvl, 20) <= _theta("em_crisis_capital_flight", "em_resid_dd", -0.08)
        if emoas is not None:
            cond = cond | (_fwd_max_increase(emoas, 20) >= _theta("em_crisis_capital_flight", "emoas_bp", 150) / 100.0)
        Y["em_crisis_capital_flight"] = _mask_tail(cond, em_lvl, 20)

    # haven flight: SPY DD <=-10% OR VIX>35 for >=3d OR HY +150bp within 15d
    if spy is not None:
        cond = _fwd_drawdown(spy, 15) <= _theta("haven_flight_risk_off", "spy_dd", -0.10)
        if vix is not None:
            cond = cond | (_fwd_count_above(vix, 15, _theta("haven_flight_risk_off", "vix_level", 35)) >= 3)
        if hy is not None:
            cond = cond | (_fwd_max_increase(hy, 15) >= _theta("haven_flight_risk_off", "hyoas_bp", 150) / 100.0)
        Y["haven_flight_risk_off"] = _mask_tail(cond, spy, 15)

    # reflation: risk basket reversal <=-6% within 20d (overextension failure)
    refl_lvl = basket_level(RISK_REFL)
    if refl_lvl is not None:
        cond = _fwd_drawdown(refl_lvl, 20) <= _theta("reflation_risk_on", "risk_reversal", -0.06)
        Y["reflation_risk_on"] = _mask_tail(cond, refl_lvl, 20)

    # intervention: USD/JPY single-day gap <=-2.5% within 10d
    if "usdjpy_quote" in F:
        q = F["usdjpy_quote"]
        cond = _fwd_min_daily_ret(q, 10) <= _theta("intervention_risk", "usdjpy_1d_gap", -0.025)
        Y["intervention_risk"] = _mask_tail(cond, q, 10)

    return Y


def _mask_tail(cond: pd.Series, ref: pd.Series, n: int) -> pd.Series:
    """Boolean->float {0,1}; NaN where < n forward obs exist (window not realized)."""
    y = cond.astype(float)
    valid = _fwd_extreme(ref, n, "min").notna()        # has a full forward window
    y[~valid] = np.nan
    return y


# --------------------------------------------------------------------------- #
# empirical conditional-exceedance probability
# --------------------------------------------------------------------------- #
def _wilson(p: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0 or not np.isfinite(p):
        return (float("nan"), float("nan"))
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (float(np.clip(center - half, 0, 1)), float(np.clip(center + half, 0, 1)))


def scenario_probability(intensity: pd.Series, y: pd.Series, n_grid: int,
                         n_min: float = 9.0, z: float = 1.96) -> dict:
    """Conditional exceedance frequency P(outcome | intensity >= today's), with a
    base rate, overlap-deflated n_eff = n_raw/N, Wilson CIs, and suppression statuses.
    Pure descriptive statistic — NEVER a forecast."""
    out = {"status": "building", "N": int(n_grid), "n_raw": 0, "n_eff": 0.0,
           "p_cond": None, "base_rate": None, "abs_lift": None, "rel_lift": None,
           "wilson_lo": None, "wilson_hi": None, "base_wilson_lo": None,
           "base_wilson_hi": None, "ci_separated": False, "i0_pctile": None}
    if intensity is None or y is None:
        return out
    I = intensity.astype(float)
    i0 = I.dropna()
    if i0.empty:
        return out
    I0 = float(i0.iloc[-1])
    out["i0"] = round(I0, 4)
    valid = I.notna() & y.notna()                      # t <= T-N with a defined intensity
    Iv, Yv = I[valid], y[valid]
    if len(Iv) < 20:
        out["status"] = "building"
        return out
    out["i0_pctile"] = round(float((Iv < I0).mean()), 3)
    base = float(Yv.mean())
    base_n_eff = len(Yv) / max(1, n_grid)
    cond = Iv >= I0
    n_raw = int(cond.sum())
    out["n_raw"] = n_raw
    n_eff = n_raw / max(1, n_grid)
    out["n_eff"] = round(n_eff, 1)
    out["base_rate"] = round(base, 4)
    bl, bh = _wilson(base, base_n_eff, z)
    out["base_wilson_lo"], out["base_wilson_hi"] = round(bl, 4), round(bh, 4)
    if n_raw <= 2:
        out["status"] = "unprecedented"
        return out
    p_cond = float(Yv[cond].mean())
    out["p_cond"] = round(p_cond, 4)
    out["abs_lift"] = round(p_cond - base, 4)
    out["rel_lift"] = round(p_cond / base, 2) if base > 0 else None
    lo, hi = _wilson(p_cond, n_eff, z)
    out["wilson_lo"], out["wilson_hi"] = round(lo, 4), round(hi, 4)
    out["ci_separated"] = bool(lo > bh or hi < bl)
    out["status"] = "insufficient" if n_eff < n_min else "ok"
    return out


# --------------------------------------------------------------------------- #
# top-level assembly
# --------------------------------------------------------------------------- #
def _strength_panel(results: dict, drivers: dict, cfg: dict):
    """base-code -> log(base-vs-USD close); 'USD' -> log(broad dollar). + residual returns."""
    assets = cfg["assets"]
    strength, resid_ret = {}, {}
    idxs = []
    for pair, df in results.items():
        if pair == "_dollar" or df is None or df.empty or "close" not in df:
            continue
        base = assets.get(pair, {}).get("base", pair)
        c = df["close"].dropna()
        strength[base] = _slog(c)
        idxs.append(c.index)
        if "resid_close" in df:
            resid_ret[base] = _slog(df["resid_close"]).diff()
    bdxy = drivers.get("broad_dollar")
    if bdxy is not None:
        strength["USD"] = _slog(bdxy)
        idxs.append(bdxy.index)
    if not idxs:
        return None, None, None
    idx = idxs[0]
    for i in idxs[1:]:
        idx = idx.union(i)
    idx = idx.sort_values()
    idx = idx[idx.weekday < 5]                       # drop sparse weekend FX prints (artifact source)
    return strength, resid_ret, idx


def fx_stress_regime(results: dict, dol: pd.DataFrame, drivers: dict, cfg: dict) -> dict:
    """Read the joint currency configuration -> named scenarios + empirical probabilities.
    Returns {} on missing data (never raises). DISPLAY-ONLY — never scored."""
    try:
        if dol is None or dol.empty or len(dol) < 300:
            return {}
        rcfg = cfg.get("regime", {})
        strength, resid_ret, idx = _strength_panel(results, drivers, cfg)
        if strength is None:
            return {}
        F = _build_features(strength, resid_ret, drivers, results, idx, cfg)
        Y = _forward_labels(F, strength, drivers, idx, cfg)
        scfg = rcfg.get("scenarios", {}) or {}
        pcfg = rcfg.get("probability", {}) or {}
        n_min = float(pcfg.get("n_min_eff", 9))

        scen_out = []
        for scn in _scenarios():
            key = scn["key"]
            sc = scfg.get(key, {}) or {}
            weights = sc.get("weights", {}) or {}
            # build each leg's drive + sub-intensity over all history
            subs, wts, fired_legs, n_fired = [], [], [], 0
            present_w, total_w = 0.0, 0.0
            for leg in scn["legs"]:
                w = float(weights.get(leg["id"], 1.0))
                total_w += w
                drive = leg["make"](F)
                if drive is None:
                    fired_legs.append({"id": leg["id"], "kind": leg["kind"], "en": leg["en"],
                                       "zh": leg["zh"], "fired": False, "value": None, "absent": True})
                    continue
                drive = drive.reindex(idx).astype(float)
                thr = float(leg["thr"])
                sub = _sub_intensity(drive, thr)
                subs.append(sub * w)
                wts.append(drive.notna().astype(float) * w)
                present_w += w
                dval = drive.dropna()
                d_today = float(dval.iloc[-1]) if len(dval) else None
                fired = bool(d_today is not None and d_today >= thr)
                n_fired += int(fired)
                fired_legs.append({"id": leg["id"], "kind": leg["kind"], "en": leg["en"],
                                   "zh": leg["zh"], "fired": fired,
                                   "value": _leg_value(d_today, thr), "absent": False})
            if not subs:
                continue
            num = pd.concat(subs, axis=1).sum(axis=1)
            den = pd.concat(wts, axis=1).sum(axis=1)
            intensity = (num / den.replace(0, np.nan))
            # require >= half the weight present AND >= 2 legs present that day
            present_legs = pd.concat([w for w in wts], axis=1)
            n_present = (present_legs > 0).sum(axis=1)
            intensity = intensity.where((den >= 0.5 * total_w) & (n_present >= 2))
            iv = intensity.dropna()
            i_today = float(iv.iloc[-1]) if len(iv) else None
            prob = scenario_probability(intensity, Y.get(key), scn["N"], n_min=n_min)
            min_legs = int(sc.get("min_legs", scn["min_legs"]))
            scen_out.append({
                "key": key, "name_en": scn["name_en"], "name_zh": scn["name_zh"],
                "intensity_today": round(100 * i_today, 1) if i_today is not None else 0.0,
                "n_fired": n_fired, "min_legs": min_legs,
                "active": bool(n_fired >= min_legs),
                "fired_legs": fired_legs, "prob": prob,
                "illustrative": bool(sc.get("illustrative", scn["illustrative"])),
                "disc_en": scn["disc_en"], "disc_zh": scn["disc_zh"],
            })

        active = [s for s in scen_out if s["active"]]
        dominant = max(active, key=lambda s: s["intensity_today"])["key"] if active else None
        spans = [strength[k].dropna() for k in strength if len(strength[k].dropna())]
        hist0 = min(s.index.min() for s in spans) if spans else idx.min()
        return {
            "scenarios": scen_out,
            "dominant": dominant,
            "n_active": len(active),
            "as_of": idx.max().strftime("%Y-%m-%d"),
            "history_span": f"{hist0.date()}..{idx.max().date()}",
            "caveats": True,
        }
    except Exception as e:  # noqa: BLE001 — radar must never break the build
        log.warning("fx_stress_regime failed (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# per-currency move kinematics table
# --------------------------------------------------------------------------- #
_CCY_ZH = {"USD": "美元", "EUR": "欧元", "JPY": "日元", "GBP": "英镑", "AUD": "澳元",
           "CAD": "加元", "CHF": "瑞郎", "CNH": "离岸人民币", "MXN": "墨西哥比索", "BRL": "巴西雷亚尔"}
_CCY_ORDER = ["USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "CNH", "MXN", "BRL"]


def fx_kinematics_table(results: dict, drivers: dict, cfg: dict) -> dict:
    """Per-currency move kinematics: literal 1d/5d/20d % move, velocity-z, acceleration-z,
    realized-vol percentile, and the idiosyncratic (ex-dollar) 5d move. COINCIDENT,
    display-only — never scored. Returns {} on failure."""
    try:
        rcfg = cfg.get("regime", {})
        kcfg = rcfg.get("kinematics", {}) or {}
        lw = kcfg.get("lit_windows_d", [1, 5, 20])
        rvw = int(kcfg.get("rvol_window_d", 20))
        rvlb = int(kcfg.get("rvol_pctile_lookback_d", 504))
        hl = int(rcfg.get("ewma_halflife_d", 20))
        zw = int(rcfg.get("z_lookback_d", 252))
        zmp = int(rcfg.get("z_min_periods", 60))
        strength, resid_ret, idx = _strength_panel(results, drivers, cfg)
        if strength is None:
            return {}
        rows = []
        for ccy in _CCY_ORDER:
            if ccy not in strength:
                continue
            lg = strength[ccy].reindex(idx)
            level = np.exp(lg)
            def pct(w):
                v = lg.diff(w)
                vv = v.dropna()
                return round(100 * (np.exp(float(vv.iloc[-1])) - 1), 2) if len(vv) else None
            vel = _velocity(level, 5, hl)
            vz = _z_causal(vel, zw, zmp).dropna()
            az = _z_causal(_accel(vel), zw, zmp).dropna()
            rvol = level.pct_change().rolling(rvw).std()
            rvp = _pctile_causal(rvol, rvlb).dropna()
            vel_z = float(vz.iloc[-1]) if len(vz) else None
            acc_z = float(az.iloc[-1]) if len(az) else None
            # idiosyncratic (ex-dollar) 5d move from residual returns
            resid5 = None
            if ccy in resid_ret:
                rr = resid_ret[ccy].reindex(idx).rolling(5).sum().dropna()
                if len(rr):
                    resid5 = round(100 * (np.exp(float(rr.iloc[-1])) - 1), 2)
            state_en, state_zh = _kin_state(vel_z, acc_z)
            rows.append({
                "ccy": ccy, "label_en": ccy, "label_zh": _CCY_ZH.get(ccy, ccy),
                "lit_1d_pct": pct(lw[0]), "lit_5d_pct": pct(lw[1]), "lit_20d_pct": pct(lw[2]),
                "vel_z": round(vel_z, 2) if vel_z is not None else None,
                "accel_z": round(acc_z, 2) if acc_z is not None else None,
                "rvol_pctile": round(float(rvp.iloc[-1]), 2) if len(rvp) else None,
                "resid_5d_pct": resid5,
                "state_en": state_en, "state_zh": state_zh,
            })
        if not rows:
            return {}
        return {"rows": rows, "as_of": idx.max().strftime("%Y-%m-%d"), "caveat": True}
    except Exception as e:  # noqa: BLE001
        log.warning("fx_kinematics_table failed (%s)", e)
        return {}


def _kin_state(vel_z: float | None, acc_z: float | None) -> tuple[str, str]:
    if vel_z is None:
        return ("—", "—")
    if abs(vel_z) < 0.75:
        return ("quiet", "平静")
    up = vel_z > 0
    accel = acc_z is not None and ((acc_z > 0.5) if up else (acc_z < -0.5))
    fading = acc_z is not None and ((acc_z < -0.5) if up else (acc_z > 0.5))
    dirn = ("up", "升") if up else ("down", "跌")
    if accel:
        return (f"accelerating {dirn[0]}", f"加速{dirn[1]}")
    if fading:
        return (f"fading {dirn[0]}", f"{dirn[1]}势消退")
    return (f"moving {dirn[0]}", f"{dirn[1]}势")
