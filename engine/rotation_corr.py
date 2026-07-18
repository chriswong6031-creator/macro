"""engine/rotation_corr.py — correlation regime-break detector (Family D, Rotation Events v2).

corr_break: fires when two series' raw rolling correlation surges AND their SPY-residual
correlation also shows an idiosyncratic regime change — the FINDING 2 two-part gate that
fires on the operator's actual signal (SMH~mag7-EW raw=0.654) while blocking broad-selloff
false-fires (pairs co-moving ONLY through SPY have resid-rise ≈ 0 and do NOT pass).

attribute_break: idio-only attribution for the leading driver inside a complex — ranks
probes by their SPY-and-complex-common-adjusted 7-session idiosyncratic return. The probe
with the most negative idio is the leader. FINDING 5: GOOGL confirmed as argmin on
07-17 tape via idio decomposition (raw near-tie GOOGL/TSLA, idio decisively GOOGL).

Pure functions — no I/O.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import basket_index
from engine.rotation_universe import PARAMS_V2

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ internals ----

def _residual_corr(
    ra: pd.Series,
    rb: pd.Series,
    bench: pd.Series,
    beta_win: int,
) -> pd.Series:
    """Rolling SPY-residual correlation between ra and rb.

    For each day t:
      beta_a(t) = cov(ra[-beta_win:], bench[-beta_win:]) / var(bench[-beta_win:])
      resid_a(t) = ra(t) - beta_a(t) * bench(t)      (then same for b)
      corr_resid(t) = rolling corr of resid_a, resid_b over corr_win

    Uses beta_win (attribution_beta_win=60) as the OLS window and corr_win (=10) for
    the final correlation, per PARAMS_V2.
    """
    corr_win = PARAMS_V2["corr_win"]
    # align to common index
    idx = ra.dropna().index.intersection(rb.dropna().index).intersection(bench.dropna().index)
    if len(idx) < beta_win + corr_win + 5:
        return pd.Series(dtype=float)

    ra_a = ra.loc[idx]
    rb_a = rb.loc[idx]
    bv = bench.loc[idx]

    # rolling beta (expanding min window = beta_win, then rolling)
    def _roll_beta(r_x: pd.Series, r_b: pd.Series) -> pd.Series:
        betas = np.full(len(r_x), np.nan)
        arr_x = r_x.values
        arr_b = r_b.values
        for i in range(beta_win - 1, len(r_x)):
            seg_x = arr_x[i - beta_win + 1 : i + 1]
            seg_b = arr_b[i - beta_win + 1 : i + 1]
            vb = float(np.var(seg_b, ddof=1))
            if not vb or not np.isfinite(vb):
                betas[i] = 0.0
            else:
                betas[i] = float(np.cov(seg_x, seg_b, ddof=1)[0, 1]) / vb
        return pd.Series(betas, index=r_x.index)

    ret_a = ra_a.pct_change()
    ret_b = rb_a.pct_change()
    ret_bench = bv.pct_change()

    beta_a = _roll_beta(ret_a, ret_bench)
    beta_b = _roll_beta(ret_b, ret_bench)

    resid_a = ret_a - beta_a * ret_bench
    resid_b = ret_b - beta_b * ret_bench

    # rolling correlation of residuals
    corr_resid = resid_a.rolling(corr_win, min_periods=corr_win).corr(resid_b)
    return corr_resid.reindex(ra.index)


# ------------------------------------------------------------------ family D ----

def corr_break(
    a_close: pd.Series,
    b_close: pd.Series,
    spy: pd.Series,
    params: dict | None = None,
) -> dict | None:
    """Two-part correlation regime-break gate (FINDING 2+3 fix).

    Fires when ALL of:
      RAW gate  : raw corr10.iloc[-1] >= corr_raw_level  AND
                  (raw corr10.iloc[-1] - raw corr10.iloc[-(corr_prior_lag+1)]) >= corr_raw_rise
      RESID gate: (resid_corr10.iloc[-1] - resid_corr10.iloc[-(corr_prior_lag+1)]) >= corr_resid_rise
                  (idiosyncratic regime change — broad-selloff discriminator)
      BOTH-FELL : both_fell = ((ra<0)&(rb<0)).iloc[-both_fell_window:].sum() >= both_fell_min
      BASE gate : 20d baseline of raw corr10 <= corr_base_max (was diversifying)
      + 2-session confirm (caller must check confirm_days in step_cross_pairs)

    Returns dict with corr receipt or None.
    """
    p = params or PARAMS_V2
    corr_win = p["corr_win"]
    prior_lag = p["corr_prior_lag"]
    beta_win = p["attribution_beta_win"]
    both_win = p["both_fell_window"]

    # align all three series
    idx = (a_close.dropna().index
           .intersection(b_close.dropna().index)
           .intersection(spy.dropna().index))
    needed = beta_win + corr_win + prior_lag + both_win + 5
    if len(idx) < needed:
        return None

    a = a_close.loc[idx]
    b = b_close.loc[idx]
    bv = spy.loc[idx]

    ra = a.pct_change().dropna()
    rb = b.pct_change().dropna()

    # raw rolling correlation
    corr_raw = ra.rolling(corr_win, min_periods=corr_win).corr(rb)
    if len(corr_raw.dropna()) < prior_lag + 2:
        return None

    cur_raw = float(corr_raw.iloc[-1])
    lag_raw = float(corr_raw.iloc[-(prior_lag + 1)])
    if not (np.isfinite(cur_raw) and np.isfinite(lag_raw)):
        return None

    # RAW gate
    raw_rise = cur_raw - lag_raw
    if cur_raw < p["corr_raw_level"] or raw_rise < p["corr_raw_rise"]:
        return None

    # BASE gate — 20d prior baseline of raw corr should have been low (was diversifying)
    # baseline = mean of corr_raw over [-(prior_lag+21):-(prior_lag+1)] (the "before" window)
    base_window = corr_raw.iloc[-(prior_lag + 21) : -(prior_lag + 1)].dropna()
    if len(base_window) >= 5:
        baseline_corr = float(base_window.mean())
        if baseline_corr > p["corr_base_max"]:
            return None
    # if insufficient history for baseline check — skip (not a hard block)

    # BOTH-FELL gate
    both_fell_mask = (ra < 0) & (rb < 0)
    # reindex to shared idx
    both_fell_mask = both_fell_mask.reindex(idx).fillna(False)
    both_fell_n = int(both_fell_mask.iloc[-both_win:].sum())
    if both_fell_n < p["both_fell_min"]:
        return None

    # RESID gate — idiosyncratic coupling must also be rising
    corr_resid = _residual_corr(a_close.loc[idx], b_close.loc[idx], bv, beta_win)
    if len(corr_resid.dropna()) < prior_lag + 2:
        return None
    cur_resid = float(corr_resid.iloc[-1]) if np.isfinite(float(corr_resid.iloc[-1])) else np.nan
    lag_resid = float(corr_resid.iloc[-(prior_lag + 1)])
    if not (np.isfinite(cur_resid) and np.isfinite(lag_resid)):
        return None
    resid_rise = cur_resid - lag_resid
    if resid_rise < p["corr_resid_rise"]:
        return None

    asof = str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1])
    return {
        "corr10_raw": round(cur_raw, 4),
        "corr_raw_rise": round(raw_rise, 4),
        "corr_resid": round(cur_resid, 4),
        "corr_resid_rise": round(resid_rise, 4),
        "both_fell_10": both_fell_n,
        "baseline_corr": round(float(base_window.mean()) if len(base_window) >= 5 else float("nan"), 4),
        "state": "break",
        "asof": asof,
    }


# ------------------------------------------------------------------ attribution ----

def attribute_break(
    complex_cfg: dict,
    closes: dict[str, pd.Series],
    spy: pd.Series,
    params: dict | None = None,
) -> dict | None:
    """Idio-only attribution for the break leader inside a complex.

    For each attribution_probe ticker, computes:
      idio7 = Σ_{last 7} (r_probe_ex_spy − beta_sec · complex_common_return)

    where:
      r_probe_ex_spy = ret_probe(t) − beta_spy(t) · ret_spy(t)
      complex_common = EW mean of complex attribution_members' returns (day t)
      beta_sec = cov(r_probe_ex_spy, complex_common) / var(complex_common)
                 estimated over attribution_beta_win sessions

    leader = argmin(idio7) — the probe with the most negative idiosyncratic return.
    FINDING 5: this cleanly separates GOOGL (−4.58% idio) from TSLA (−3.72%) on 07-17.

    Returns dict or None (if insufficient data or fewer than 2 probes resolve).
    """
    p = params or PARAMS_V2
    beta_win = p["attribution_beta_win"]
    L = p["attribution_L"]

    probes = complex_cfg.get("attribution_probes", [])
    members = complex_cfg.get("attribution_members", [])
    if not probes or not members:
        return None

    # complex common return — EW mean of attribution_members' returns
    member_rets = []
    for m in members:
        s = closes.get(m)
        if s is not None:
            member_rets.append(s.pct_change())
    if not member_rets:
        return None
    common_ret = pd.concat(member_rets, axis=1).mean(axis=1).dropna()

    spy_ret = spy.pct_change()

    # load probe returns
    probe_rets: dict[str, pd.Series] = {}
    for ticker in probes:
        df = basket_index._load_member_ohlcv(ticker)
        if df is not None and "close" in df:
            s = df["close"].dropna().pct_change()
            if len(s.dropna()) >= beta_win + L + 5:
                probe_rets[ticker] = s

    if len(probe_rets) < 2:
        return None

    # compute idio7 for each probe
    idio_by_probe: dict[str, float] = {}
    for ticker, ret in probe_rets.items():
        # align to common idx with spy and complex_common
        idx = (ret.dropna().index
               .intersection(spy_ret.dropna().index)
               .intersection(common_ret.dropna().index))
        if len(idx) < beta_win + L + 5:
            continue

        r_p = ret.loc[idx]
        r_spy = spy_ret.loc[idx]
        r_com = common_ret.loc[idx]

        # step 1: SPY beta and residual
        spy_seg = r_spy.iloc[-(beta_win + L):-L] if len(r_spy) >= beta_win + L else r_spy.iloc[:beta_win]
        p_seg = r_p.iloc[-(beta_win + L):-L] if len(r_p) >= beta_win + L else r_p.iloc[:beta_win]
        vb = float(spy_seg.var(ddof=1))
        beta_spy = (float(np.cov(p_seg.values, spy_seg.values, ddof=1)[0, 1]) / vb
                    if vb and np.isfinite(vb) else 0.0)
        r_ex_spy = r_p - beta_spy * r_spy

        # step 2: complex common beta
        com_seg = r_com.iloc[-(beta_win + L):-L] if len(r_com) >= beta_win + L else r_com.iloc[:beta_win]
        ex_seg = r_ex_spy.iloc[-(beta_win + L):-L] if len(r_ex_spy) >= beta_win + L else r_ex_spy.iloc[:beta_win]
        vc = float(com_seg.var(ddof=1))
        beta_com = (float(np.cov(ex_seg.values, com_seg.values, ddof=1)[0, 1]) / vc
                    if vc and np.isfinite(vc) else 0.0)

        # step 3: idio7 = sum of last 7 idiosyncratic returns
        idio_ret = r_ex_spy - beta_com * r_com
        idio7 = float(idio_ret.iloc[-L:].sum())
        if np.isfinite(idio7):
            idio_by_probe[ticker] = round(idio7, 4)

    if len(idio_by_probe) < 2:
        return None

    leader_ticker = min(idio_by_probe, key=idio_by_probe.get)
    leader_idio = idio_by_probe[leader_ticker]

    # the "leader" in the payload is the resolved series key (not the probe ticker),
    # per spec §2 family D: leader = resolved series key, detail_en names the probe ticker.
    # Map the winning probe back to its containing attribution_member. The spec example:
    # GOOGL is in mag7_basket → leader="mag7_basket". Default is members[0] (spec: "mag7_basket"
    # is listed first for the tech complex, so it is the fallback when the probe map is absent).
    # attribution_probe_members maps probe ticker → series key; absent → use members[0].
    probe_to_member = complex_cfg.get("attribution_probe_members") or {}
    leader_series = probe_to_member.get(leader_ticker, members[0] if members else "mag7_basket")

    detail_en = (f"{leader_ticker} idiosyncratic decline ({leader_idio*100:+.1f}% "
                 f"over {L} sessions) led the coupling")
    detail_zh = (f"{leader_ticker} 特异性下跌（{L}个交易日内 {leader_idio*100:+.1f}%）主导了联动")

    return {
        "leader": leader_series,
        "leader_probe": leader_ticker,
        "detail_en": detail_en,
        "detail_zh": detail_zh,
        "idio_by_probe": idio_by_probe,
    }
