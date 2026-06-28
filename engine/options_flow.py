"""engine/options_flow.py — MEASURED options flow + dealer positioning (the institutional upgrade).

The dealer-gamma map we ship today assumes dealers are long calls / short puts — an
unobservable SIGN that is the layer's known weak point. This engine replaces the ASSUMPTION
with a MEASURED read built from the actual day's traded volume: it signs each minute's
per-contract volume by the option's own minute-close tick (a buy lifts the option, a sell
hits it — the TICK RULE, the honest fallback when the per-trade NBBO tape is unavailable),
then infers the dealer side as the opposite of net customer flow.

From one underlying's minute aggregates (collectors/massive_flatfiles) plus the per-contract
greeks + open-interest we already snapshot (data/polygon_gex), it produces:

  • NET SIGNED PREMIUM ($ bought − sold) and signed put/call — the flagship "smart-money" tape read
  • DELTA FLOW — net signed $-delta customers put on today (directional positioning)
  • MEASURED DEALER GAMMA FLOW — −Σ(signed customer vol × gamma × 100 × S²): did dealers get
    LONGER gamma (vol-suppressive) or SHORTER (fragile) today — measured, not assumed
  • the ASSUMPTION-based GEX alongside it + the DIVERGENCE (strikes where measured flow
    disagrees with the long-call/short-put assumption — the genuinely new signal)
  • VOL>OI new-position detection (fresh positioning) and 0DTE concentration / intraday profile
  • large prints (outsized single-contract minutes), direction-tagged

HONEST FRAMING: minute-tick-rule signing is APPROXIMATE (no NBBO, no trade tape — both 403 on
our plan; ~77–83% sign accuracy vs ~81–84% for full Lee-Ready, errors roughly symmetric so they
wash in daily aggregates). EOD/T+1 cadence, not intraday-live. The sign accuracy is
empirically calibratable against true quote-rule signs via collectors/databento_tbbo +
scripts/calibrate_flow_signing. Display/context until that calibration gate passes; never a
stand-alone buy/sell. See research/OPTIONS_FLOW_DATA.md.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CONTRACT_MULT = 100.0


def _r(x, n=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def signing_gate() -> dict:
    """The calibrated signing quality (scripts/calibrate_flow_signing → Databento). Absent →
    direction unreliable / magnitude reliable, the honest default. Governs how the flow
    DIRECTION is framed; magnitude/positioning reads never depend on it."""
    try:
        import json
        from lib import config
        p = config.data_dir() / "options_flow" / "signing_gate.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return {"direction_reliable": False, "magnitude_reliable": True,
            "note": "no calibration yet — direction soft, magnitude reliable"}


# --------------------------------------------------------------------------- #
# tick-rule signing + per-contract aggregation
# --------------------------------------------------------------------------- #
def sign_volume(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Sign each minute's volume by the option's OWN close tick (uptick=buy +1, downtick=sell
    −1, flat=carry-forward), then aggregate to one row per contract. Expects the
    massive_flatfiles minute schema (ticker, volume, close, window_start, underlying, expiry,
    is_call, strike). Returns per-contract: vol, signed_vol, premium, close, plus OCC cols."""
    if minute_df is None or minute_df.empty:
        return pd.DataFrame()
    df = minute_df.sort_values(["ticker", "window_start"]).copy()
    prev = df.groupby("ticker")["close"].shift()
    tick = np.sign(df["close"] - prev)
    # carry the last non-zero tick within each contract; first/flat -> 0 (neutral)
    tick = tick.replace(0, np.nan).groupby(df["ticker"]).ffill().fillna(0.0)
    df["_signed"] = tick * df["volume"]
    df["_prem"] = df["close"] * df["volume"] * CONTRACT_MULT
    g = df.groupby("ticker").agg(
        underlying=("underlying", "first"), expiry=("expiry", "first"),
        is_call=("is_call", "first"), strike=("strike", "first"),
        vol=("volume", "sum"), signed_vol=("_signed", "sum"),
        premium=("_prem", "sum"), close=("close", "last")).reset_index()
    return g


def _intraday_profile(minute_df: pd.DataFrame) -> dict:
    """Volume share by session third (open / mid / close) — when did the flow hit."""
    if minute_df is None or minute_df.empty or "window_start" not in minute_df:
        return {}
    # window_start is ns since epoch (UTC); convert to ET so the session thirds line up
    t = pd.to_datetime(minute_df["window_start"], unit="ns", utc=True).dt.tz_convert("America/New_York")
    sod = t.dt.hour * 3600 + t.dt.minute * 60          # seconds into the ET trading day
    # session ~ 09:30–16:00 = 23400 s window; split into thirds
    frac = ((sod - 9.5 * 3600) / (6.5 * 3600)).clip(0, 0.999)
    third = (frac * 3).astype(int)
    vol = minute_df["volume"].groupby(third).sum()
    tot = float(vol.sum()) or 1.0
    return {"open_share": _r(vol.get(0, 0) / tot, 3),
            "mid_share": _r(vol.get(1, 0) / tot, 3),
            "close_share": _r(vol.get(2, 0) / tot, 3)}


# --------------------------------------------------------------------------- #
# flow summary
# --------------------------------------------------------------------------- #
def flow_summary(agg: pd.DataFrame, asof, spot: float | None, minute_df=None) -> dict:
    """Per-underlying tape read from the signed per-contract aggregate."""
    if agg is None or agg.empty:
        return {"available": False}
    asof_ts = pd.Timestamp(asof)
    calls = agg[agg["is_call"]]; puts = agg[~agg["is_call"]]
    prem = float(agg["premium"].sum())
    # signed premium: premium carries the trade's $, signed by its net direction
    sign = np.sign(agg["signed_vol"]).replace(0, 0)
    net_prem = float((agg["premium"] * sign).sum())
    cv, pv = float(calls["vol"].sum()), float(puts["vol"].sum())
    # signed P/C: net put buying vs net call buying
    net_call = float(calls.loc[calls["signed_vol"] > 0, "signed_vol"].sum())
    net_put = float(puts.loc[puts["signed_vol"] > 0, "signed_vol"].sum())
    zerodte = float(agg.loc[agg["expiry"].dt.normalize() == asof_ts.normalize(), "vol"].sum())
    tot = float(agg["vol"].sum()) or 1.0
    # large prints: top contracts by premium, direction-tagged
    big = agg.reindex(agg["premium"].abs().sort_values(ascending=False).index).head(6)
    prints = [{"k": _r(r.strike), "cp": "C" if r.is_call else "P",
               "exp": str(pd.Timestamp(r.expiry).date()),
               "vol": int(r.vol), "prem_mn": _r(r.premium / 1e6),
               "dir": "buy" if r.signed_vol > 0 else "sell" if r.signed_vol < 0 else "mixed"}
              for r in big.itertuples()]
    return {
        "available": True, "asof": str(asof_ts.date()), "spot": _r(spot),
        "volume": int(tot), "premium_mn": _r(prem / 1e6),
        "net_premium_mn": _r(net_prem / 1e6),
        "call_vol": int(cv), "put_vol": int(pv),
        "pc_ratio": _r(pv / cv, 2) if cv else None,
        "net_call_vol": int(net_call), "net_put_vol": int(net_put),
        "signed_pc": _r(net_put / net_call, 2) if net_call else None,
        "zerodte_share": _r(zerodte / tot, 3),
        "intraday": _intraday_profile(minute_df),
        "large_prints": prints,
    }


# --------------------------------------------------------------------------- #
# MEASURED dealer positioning (the headline)
# --------------------------------------------------------------------------- #
def measured_dealer(agg: pd.DataFrame, greeks_oi: pd.DataFrame | None, spot: float | None) -> dict:
    """Fuse signed customer flow with per-contract greeks + OI to MEASURE the dealer side.
    greeks_oi: DataFrame keyed by `ticker` with columns gamma, delta, oi (from the snapshot
    store). Returns the measured gamma/delta FLOW, the assumption-based GEX, and the
    divergences. Degrades to {} without greeks."""
    if agg is None or agg.empty or greeks_oi is None or greeks_oi.empty or not spot:
        return {}
    j = agg.merge(greeks_oi[["ticker", "gamma", "delta", "oi"]], on="ticker", how="inner")
    if j.empty:
        return {}
    s2 = spot * spot
    # MEASURED dealer change today: dealers take the opposite of net customer flow.
    # dealer gamma flow = −Σ(signed customer vol × gamma × 100 × S²) per 1% move
    j["_gflow"] = -(j["signed_vol"] * j["gamma"] * CONTRACT_MULT * s2 * 0.01)
    j["_dflow"] = -(j["signed_vol"] * j["delta"] * CONTRACT_MULT * spot)   # dealer $delta flow
    gamma_flow = float(j["_gflow"].sum())
    delta_flow = float(j["_dflow"].sum())
    # ASSUMPTION-based GEX (long-call / short-put × OI) — the legacy read, for comparison
    sgn_assume = np.where(j["is_call"], 1.0, -1.0)
    j["_assume"] = sgn_assume * j["gamma"] * j["oi"] * CONTRACT_MULT * s2 * 0.01
    assumed_gex = float(j["_assume"].sum())
    # DIVERGENCE: where the MEASURED flow-implied dealer sign disagrees with the assumption.
    # measured dealer sign on today's flow = −sign(signed_vol); assumption sign = +call/−put
    j["_flow_sign"] = -np.sign(j["signed_vol"])
    diverge = j[(j["_flow_sign"] != 0) & (j["_flow_sign"] != sgn_assume)]
    by_k = (diverge.assign(absp=diverge["premium"].abs())
            .groupby(["strike", "is_call"]).agg(prem=("premium", "sum"),
                                                sv=("signed_vol", "sum")).reset_index())
    by_k = by_k.reindex(by_k["prem"].abs().sort_values(ascending=False).index).head(5)
    divs = [{"k": _r(r.strike), "cp": "C" if r.is_call else "P",
             "flow": "customers " + ("bought" if r.sv > 0 else "sold"),
             "prem_mn": _r(r.prem / 1e6)} for r in by_k.itertuples()]
    n_cov = int(len(j)); n_oi = float(j["oi"].sum())
    return {
        "gamma_flow_bn": _r(gamma_flow / 1e9, 3),
        "gamma_flow_dir": ("dealers added LONG gamma (more vol-suppressive)" if gamma_flow > 0
                           else "dealers added SHORT gamma (more fragile)" if gamma_flow < 0
                           else "flat"),
        "delta_flow_mn": _r(delta_flow / 1e6),
        "assumed_gex_bn": _r(assumed_gex / 1e9, 3),
        "divergence": divs,
        "coverage": {"contracts": n_cov, "oi": int(n_oi)},
    }


def vol_oi_newpos(agg: pd.DataFrame, greeks_oi: pd.DataFrame | None) -> dict:
    """Fresh-positioning detector: contracts whose day VOLUME exceeds prior OI = new
    positions opened today. Direction-tagged from the signed flow. Pure OI arithmetic."""
    if agg is None or agg.empty or greeks_oi is None or greeks_oi.empty:
        return {}
    j = agg.merge(greeks_oi[["ticker", "oi"]], on="ticker", how="inner")
    fresh = j[(j["oi"] > 0) & (j["vol"] > j["oi"])].copy()
    if fresh.empty:
        return {"fresh_contracts": 0, "top": []}
    fresh["ratio"] = fresh["vol"] / fresh["oi"]
    top = fresh.reindex(fresh["premium"].abs().sort_values(ascending=False).index).head(6)
    rows = [{"k": _r(r.strike), "cp": "C" if r.is_call else "P",
             "exp": str(pd.Timestamp(r.expiry).date()), "vol": int(r.vol), "oi": int(r.oi),
             "x_oi": _r(r.ratio, 1), "prem_mn": _r(r.premium / 1e6),
             "dir": "buy" if r.signed_vol > 0 else "sell" if r.signed_vol < 0 else "mixed"}
            for r in top.itertuples()]
    return {"fresh_contracts": int(len(fresh)),
            "fresh_premium_mn": _r(float(fresh["premium"].sum()) / 1e6), "top": rows}


# --------------------------------------------------------------------------- #
# MULTI-DAY positioning from day-over-day OPEN-INTEREST change (the reliable read)
# --------------------------------------------------------------------------- #
def oi_positioning(today: pd.DataFrame | None, prior_oi: pd.DataFrame | None,
                   spot: float | None, asof, prior_asof) -> dict:
    """Net positioning from day-over-day OPEN-INTEREST change (Garleanu-Pedersen-Poteshman
    net demand). ΔOI = today's OI − the prior snapshot's OI per contract, matched on the OCC
    ticker — the cleanest MEASURED positioning signal at an EOD cadence: it needs NO trade-
    signing (it is the realized change in the count of open contracts), so it is RELIABLE
    exactly where the minute tick-rule DIRECTION is soft. Rising OI = net OPENING; calls being
    opened lean bullish, puts being opened lean defensive / hedging.

    today    : per-contract frame [ticker, is_call, strike, expiry, oi, delta] for the snapshot day.
    prior_oi : [ticker, oi] from the prior snapshot day.

    The headline net uses MATCHED contracts (present both days) so a strike rolling in/out of the
    near-money window as spot moves can't masquerade as opening/closing; brand-new contracts are
    reported separately as context. Needs >=2 OI snapshot days -> {available: False} with <2;
    the read sharpens as the per-strike OI history accrues forward. delta-weighted exposure carries
    the GPP end-user-net-long assumption explicitly (ΔOI itself is assumption-free)."""
    if (today is None or today.empty or prior_oi is None or prior_oi.empty
            or prior_asof is None):
        return {"available": False, "reason": "needs >=2 OI snapshot days"}
    t = today.dropna(subset=["oi"]).copy()
    p = prior_oi.dropna(subset=["oi"])[["ticker", "oi"]].rename(columns={"oi": "oi_prior"})
    j = t.merge(p, on="ticker", how="left")
    matched = j[j["oi_prior"].notna()].copy()
    if matched.empty:
        return {"available": False, "reason": "no contracts overlap the prior snapshot"}
    matched["doi"] = matched["oi"] - matched["oi_prior"]
    calls, puts = matched[matched["is_call"]], matched[~matched["is_call"]]
    call_doi, put_doi = float(calls["doi"].sum()), float(puts["doi"].sum())
    net_doi = call_doi + put_doi
    prior_call_oi, prior_put_oi = float(calls["oi_prior"].sum()), float(puts["oi_prior"].sum())
    # GPP directional exposure: IF the new OI is end-user-long (the natural convexity buyers),
    # ΔOI×delta is the net new $-delta. Calls carry +delta, puts −delta — assumption flagged.
    net_delta_doi = float((matched["doi"] * matched["delta"].fillna(0.0)
                           * CONTRACT_MULT * (spot or 0.0)).sum()) if spot else None
    # brand-new contracts (today-only) — genuine fresh listings/positioning, but confounded with
    # window shifts, so reported as context, not in the matched headline.
    newc = j[j["oi_prior"].isna() & (j["oi"] > 0)]
    new_oi = float(newc["oi"].sum())

    def _rows(frame, ascending):
        top = frame.reindex(frame["doi"].abs().sort_values(ascending=False).index)
        top = top[(top["doi"] < 0) if ascending else (top["doi"] > 0)].head(6)
        return [{"k": _r(r.strike), "cp": "C" if r.is_call else "P",
                 "exp": str(pd.Timestamp(r.expiry).date()), "doi": int(r.doi),
                 "oi": int(r.oi), "oi_prior": int(r.oi_prior)} for r in top.itertuples()]

    # tone: net new CALL vs PUT open interest. Calls opening = bullish lean; puts opening =
    # defensive / hedging. Use the dominant side; require a meaningful net to color it.
    tone = "neutral"; lean_en = lean_zh = None
    thresh = 0.02 * (prior_call_oi + prior_put_oi)        # 2% of prior OI = a meaningful build
    if call_doi - put_doi > max(thresh, 1) and call_doi > 0:
        tone, lean_en, lean_zh = "pos", "net new CALL positioning (bullish lean)", "净新增看涨持仓（偏多）"
    elif put_doi - call_doi > max(thresh, 1) and put_doi > 0:
        tone, lean_en, lean_zh = "neg", "net new PUT positioning (defensive / hedging)", "净新增看跌持仓（防御/对冲）"
    elif net_doi < -max(thresh, 1):
        tone, lean_en, lean_zh = "neutral", "net UNWIND (open interest closing)", "净平仓（未平仓量下降）"
    return {
        "available": True, "reliable": True,         # ΔOI needs no trade-signing
        "asof": str(pd.Timestamp(asof).date()), "prior_asof": str(pd.Timestamp(prior_asof).date()),
        "days_back": int((pd.Timestamp(asof).normalize() - pd.Timestamp(prior_asof).normalize()).days),
        "n_matched": int(len(matched)), "n_new_contracts": int(len(newc)),
        "new_contract_oi": int(new_oi),
        "net_doi": int(net_doi), "call_doi": int(call_doi), "put_doi": int(put_doi),
        "call_oi_chg_pct": _r(call_doi / prior_call_oi, 3) if prior_call_oi else None,
        "put_oi_chg_pct": _r(put_doi / prior_put_oi, 3) if prior_put_oi else None,
        "doi_pc": _r(put_doi / call_doi, 2) if call_doi > 0 else None,
        "net_delta_doi_mn": _r((net_delta_doi or 0) / 1e6) if net_delta_doi is not None else None,
        "opening": bool(net_doi > 0), "tone": tone, "lean_en": lean_en, "lean_zh": lean_zh,
        "top_build": _rows(matched, ascending=False),
        "top_unwind": _rows(matched, ascending=True),
        "note": ("Measured net positioning = day-over-day open-interest change (no trade-signing "
                 "needed — RELIABLE). Calls opening lean bullish, puts opening lean defensive. "
                 "ΔOI is assumption-free; the $-delta exposure assumes the new OI is end-user-long "
                 "(GPP). Sharpens as the per-strike OI history accrues."),
    }


# --------------------------------------------------------------------------- #
# orchestrate + verdict
# --------------------------------------------------------------------------- #
def build_flow(underlying: str, minute_df: pd.DataFrame, greeks_oi: pd.DataFrame | None,
               spot: float | None, asof, *, oi_today: pd.DataFrame | None = None,
               prior_oi: pd.DataFrame | None = None, prior_asof=None) -> dict:
    """Full per-underlying flow payload. minute_df = that name's minute aggregates;
    greeks_oi = snapshot greeks/OI keyed by ticker (optional). oi_today/prior_oi/prior_asof =
    today's + the prior snapshot's per-strike OI for the multi-day ΔOI positioning read (the
    reliable, signing-free signal). Returns None-ish when empty."""
    agg = sign_volume(minute_df)
    if agg.empty:
        return {"underlying": underlying, "available": False}
    gate = signing_gate()
    summ = flow_summary(agg, asof, spot, minute_df=minute_df)
    dealer = measured_dealer(agg, greeks_oi, spot)
    newpos = vol_oi_newpos(agg, greeks_oi)
    positioning = oi_positioning(oi_today, prior_oi, spot, asof, prior_asof)
    out = {"underlying": underlying, **summ, "dealer": dealer, "new_positions": newpos,
           "positioning": positioning,
           "signing": {"method": "minute tick-rule (no NBBO/trade-tape)",
                       "direction_reliable": bool(gate.get("direction_reliable")),
                       "magnitude_reliable": bool(gate.get("magnitude_reliable", True)),
                       "per_trade_agreement": gate.get("per_trade_agreement"),
                       "net_sign_recovery": gate.get("net_sign_recovery"),
                       "note": gate.get("note")}}
    out["verdict"] = _verdict(summ, dealer, newpos, gate, positioning)
    return out


def _verdict(summ: dict, dealer: dict, newpos: dict, gate: dict, positioning: dict | None = None) -> dict:
    """Synthesized read that LEADS WITH THE RELIABLE (magnitude / positioning) facts and marks
    net buy/sell DIRECTION as soft unless the signing calibration says it is trustworthy. The
    multi-day ΔOI positioning is signing-free, so its bullish/defensive lean is stated plainly."""
    dir_ok = bool(gate.get("direction_reliable"))
    prem = summ.get("premium_mn")
    zdte = summ.get("zerodte_share")
    fresh = (newpos or {}).get("fresh_contracts")
    pc = summ.get("pc_ratio")
    pos = positioning if isinstance(positioning, dict) and positioning.get("available") else None
    # --- reliable, signing-free facts first ---
    rel_en, rel_zh = [], []
    if prem is not None:
        rel_en.append(f"${prem/1000:.1f}B premium traded" if prem >= 1000 else f"${prem:.0f}M premium traded")
        rel_zh.append(f"成交权利金 ${prem/1000:.1f}B" if prem >= 1000 else f"成交权利金 ${prem:.0f}M")
    if zdte is not None:
        rel_en.append(f"{round(zdte*100)}% 0DTE"); rel_zh.append(f"0DTE占{round(zdte*100)}%")
    if fresh:
        rel_en.append(f"{fresh} fresh positions"); rel_zh.append(f"{fresh}个新建仓")
    if pc is not None:
        rel_en.append(f"P/C {pc}"); rel_zh.append(f"看跌看涨比 {pc}")
    # multi-day ΔOI positioning — RELIABLE (no signing) so its lean is stated as a hard fact
    if pos and pos.get("lean_en"):
        net = pos.get("net_doi") or 0
        rel_en.append(f"{pos['lean_en']} (ΔOI {net:+,})")
        rel_zh.append(f"{pos.get('lean_zh') or pos['lean_en']}（ΔOI {net:+,}）")
    # --- direction: strong only if calibrated, else soft "leans …" ---
    np_mn = summ.get("net_premium_mn"); spc = summ.get("signed_pc")
    gflow = (dealer or {}).get("gamma_flow_bn")
    tone = "neutral"; dir_en = dir_zh = None
    lean = None
    if spc is not None:
        lean = "bearish/hedging" if spc > 1.3 else "bullish" if spc < 0.7 else None
    if np_mn is not None and lean is None:
        lean = "bullish" if np_mn > 0 else "bearish" if np_mn < 0 else None
    if lean:
        tone = "pos" if lean == "bullish" else "neg"
        if dir_ok:
            dir_en = f"flow leans {lean}"; dir_zh = "流动偏" + ("看涨" if lean == "bullish" else "看跌/对冲")
        else:
            dir_en = f"~leans {lean} (direction approx)"; dir_zh = "≈偏" + ("看涨" if lean == "bullish" else "看跌/对冲") + "（方向近似）"
            tone = "neutral"      # don't color strongly on a soft signal
    gnote_en = gnote_zh = None
    if gflow is not None and dir_ok:
        gnote_en = "dealers shorter gamma" if gflow < 0 else "dealers longer gamma"
        gnote_zh = "做市商Gamma转空" if gflow < 0 else "做市商Gamma转多"
    # the RELIABLE ΔOI positioning lean wins the tone over the soft signed-flow direction —
    # it is a measured open-interest change, not a tick-rule inference.
    if pos and pos.get("tone") in ("pos", "neg"):
        tone = pos["tone"]
    head_en = "; ".join(rel_en + [b for b in (dir_en, gnote_en) if b]) or "balanced flow"
    head_zh = "；".join(rel_zh + [b for b in (dir_zh, gnote_zh) if b]) or "流动均衡"
    return {"tone": tone, "en": head_en, "zh": head_zh, "direction_reliable": dir_ok,
            "positioning_reliable": bool(pos)}
