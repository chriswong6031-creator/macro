"""Prophet US forensics: why don't current winners surface?

Read-only audit over committed caches (last bar 2026-07-31). Measures:
  A. Top-150 63d runners (and top-50 21d): today-eligibility + dominant excluder leg.
  B. Eligibility-days over the last 63 sessions per runner (tier_stream, PIT basis)
     + forward return from first eligible day.
  C. Full-universe today-eligible set: count + sector histogram vs runner sectors.
  D. CN vs US admit character: trailing 63d return + drawdown-from-high at admission.
  E. PLTR / DLBY case traces.
Writes JSON results next to itself. No repo writes.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner_audit_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)
warnings.filterwarnings("ignore")

from engine import confluence_tiers as ct  # noqa: E402
from engine.confluence_tiers import (  # noqa: E402
    _rsi_macd, _stoch_rsi_kd, _tf_bars, _xup, _since,
    BUY_RSI_MAX, CONF_W, FRESH_TICKS, OB, OS,
)
from engine.technicals import rsi  # noqa: E402


def load_universe() -> tuple[pd.DataFrame, dict[str, str]]:
    frames = []
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        c = pd.read_parquet(f"data/{grp}/_closes_cache.parquet")
        frames.append(c)
    idx = frames[1].index  # longest
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()]
    sec = pd.read_parquet("data/breadth/ticker_sectors.parquet")
    sector = dict(zip(sec["ticker"], sec["sector"]))
    return wide, sector


def leg_attribution(c: pd.Series) -> dict:
    """Recompute the cascade's last-bar legs to name the dominant excluder.

    Mirrors confluence_tiers.cascade() leg-by-leg (close-only)."""
    c = c.dropna()
    if len(c) < ct.MIN_HISTORY:
        return {"excluder": "insufficient_history"}
    if not isinstance(c.index, pd.DatetimeIndex):
        c = c.copy()
        c.index = pd.to_datetime(c.index)
    di = c.index
    last = len(di) - 1
    sm, smk = _tf_bars(c, 2)
    m2, s2 = _rsi_macd(sm)
    h2 = m2 - s2
    mb2 = _xup(m2, s2)
    slope2 = h2 - h2.shift(1)
    btc = (-h2 / slope2)
    imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= ct.EARLY_CROSS_BARS)).fillna(False)
    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    r14_3 = rsi(ss3, ct.RSI_LEN)
    m3, s3 = _rsi_macd(ss3)
    mb3 = _xup(m3, s3)
    wk = c.resample("W-FRI").last().dropna()
    wm, ws = _rsi_macd(wk)
    wbull = (wm >= ws).shift(1)
    from engine.confluence_tiers import _to_daily
    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)  # noqa: E731
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    r14_d = td(r14_3, sk3)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    mb2_d = td(mb2.fillna(False), smk, "event")
    mb3_d = td(mb3.fillna(False), sk3, "event")
    fromos3 = d3.rolling(CONF_W).min() < OS
    fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
    wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
    imm2_d = td(imm2.fillna(False), smk).fillna(False)

    k3n, d3n = float(k3_d.iloc[last]), float(d3_d.iloc[last])
    m3n, s3n = float(m3_d.iloc[last]), float(s3_d.iloc[last])
    r14n = float(r14_d.iloc[last]) if pd.notna(r14_d.iloc[last]) else np.nan
    stoch_ob = (k3n >= OB) or (d3n >= OB)
    stoch_bear = k3n < d3n
    macd_bear = m3n < s3n
    rsi_block = bool(pd.notna(r14n) and r14n >= BUY_RSI_MAX)
    # tick ages of the two cross families
    from engine.confluence_tiers import _ticks_since
    idx3 = np.where(mb3_d.fillna(False).to_numpy())[0]
    cross3_date = di[int(idx3[-1])] if len(idx3) else None
    t1_ticks = _ticks_since(sk3, cross3_date)
    confirm3 = (wbull_d | fromos3_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)
    idx2 = np.where(t2_buy.to_numpy())[0]
    t2_ticks = _ticks_since(smk, di[int(idx2[-1])]) if len(idx2) else None
    # raw 2D cross age ignoring vetoes (to detect "cross happened, veto ate it")
    idx2raw = np.where(mb2_d.fillna(False).to_numpy())[0]
    t2raw_ticks = _ticks_since(smk, di[int(idx2raw[-1])]) if len(idx2raw) else None

    vetoed = stoch_ob or stoch_bear or macd_bear
    legs = {
        "stoch_ob": bool(stoch_ob), "stoch_bear": bool(stoch_bear),
        "macd_bear": bool(macd_bear), "rsi_block": rsi_block,
        "k3": round(k3n, 1), "d3": round(d3n, 1), "rsi3d": (round(r14n, 1) if pd.notna(r14n) else None),
        "t1_ticks": t1_ticks, "t2_ticks": t2_ticks, "t2raw_ticks": t2raw_ticks,
        "recent3": bool(recent3_d.iloc[last]),
        "imm2": bool(imm2_d.iloc[last]),
    }
    # dominant excluder, in cascade evaluation order
    if vetoed:
        which = [n for n, f in (("stoch_ob", stoch_ob), ("stoch_bear", stoch_bear),
                                ("macd_bear", macd_bear)) if f]
        legs["excluder"] = "not_topped_veto(" + "+".join(which) + ")"
    else:
        t1_fresh = t1_ticks is not None and t1_ticks <= FRESH_TICKS
        t2_active = t2_ticks is not None and t2_ticks <= FRESH_TICKS
        if t1_fresh or t2_active:
            legs["excluder"] = None  # would be eligible (cascade-level)
        elif rsi_block and t2raw_ticks is not None and t2raw_ticks <= FRESH_TICKS:
            legs["excluder"] = "rsi_cap_on_fresh_cross"
        elif (t1_ticks is not None and t1_ticks > FRESH_TICKS) or \
             (t2raw_ticks is not None and t2raw_ticks > FRESH_TICKS):
            legs["excluder"] = "freshness_expired"
        elif not legs["recent3"]:
            legs["excluder"] = "no_recent_3d_stoch_cross"
        else:
            legs["excluder"] = "no_cross"
    return legs


def eligibility_window(c: pd.Series, lookback: int = 63) -> dict:
    st = ct.tier_stream(c)
    if st.empty:
        return {"days_eligible": None}
    tail = st.tail(lookback)
    elig = tail["eligible"]
    days = int(elig.sum())
    out = {"days_eligible": days}
    if days:
        first = tail.index[elig.to_numpy().nonzero()[0][0]]
        cc = c.dropna()
        px0 = float(cc.loc[:first].iloc[-1])
        pxN = float(cc.iloc[-1])
        out["first_eligible"] = str(first.date())
        out["fwd_ret_from_first_pct"] = round((pxN / px0 - 1) * 100, 2)
        out["tiers_seen"] = sorted({t for t in tail.loc[elig, "tier"] if t})
    return out


def main() -> None:
    wide, sector = load_universe()
    res: dict = {"asof": str(wide.index[-1].date())}

    valid = wide.columns[wide.notna().sum() >= ct.MIN_HISTORY]
    px = wide[valid]
    r63 = (px.iloc[-1] / px.iloc[-64] - 1).dropna()
    r21 = (px.iloc[-1] / px.iloc[-22] - 1).dropna()
    top63 = r63.sort_values(ascending=False).head(150)
    top21 = r21.sort_values(ascending=False).head(50)

    # A+B: excluder + eligibility window for top63 runners
    runner_rows = []
    for t, ret in top63.items():
        c = px[t]
        legs = leg_attribution(c)
        win = eligibility_window(c)
        runner_rows.append({"ticker": t, "r63_pct": round(ret * 100, 1),
                           "sector": sector.get(t, "?"), **legs, **win})
    res["top63_runners"] = runner_rows
    exc = pd.Series([r["excluder"] or "ELIGIBLE_TODAY" for r in runner_rows]).value_counts()
    res["top63_excluder_hist"] = exc.to_dict()
    res["top63_eligible_days_dist"] = pd.Series(
        [r["days_eligible"] for r in runner_rows if r["days_eligible"] is not None]
    ).describe().round(2).to_dict()
    res["top63_never_eligible_63d"] = int(sum(1 for r in runner_rows if r["days_eligible"] == 0))

    # top-21d fast movers, same treatment (lighter)
    fast_rows = []
    for t, ret in top21.items():
        legs = leg_attribution(px[t])
        fast_rows.append({"ticker": t, "r21_pct": round(ret * 100, 1),
                          "sector": sector.get(t, "?"), "excluder": legs.get("excluder")})
    res["top21_runners"] = fast_rows
    res["top21_excluder_hist"] = pd.Series(
        [r["excluder"] or "ELIGIBLE_TODAY" for r in fast_rows]).value_counts().to_dict()

    # C: full-universe today-eligible via cascade (raw-cross T1 basis)
    elig_today = []
    for t in valid:
        v = ct.cascade(px[t])
        if v.get("eligible"):
            elig_today.append({"ticker": t, "tier": v.get("tier"),
                               "sector": sector.get(t, "?")})
    res["universe_n"] = int(len(valid))
    res["eligible_today_n"] = len(elig_today)
    res["eligible_today_by_sector"] = pd.Series(
        [e["sector"] for e in elig_today]).value_counts().to_dict()
    res["runner_sector_hist"] = pd.Series(
        [r["sector"] for r in runner_rows]).value_counts().to_dict()
    res["eligible_today"] = elig_today

    # D: admit-character US vs CN — trailing 63d ret + dd-from-high at admission day
    def admit_character(closes: pd.DataFrame, n_sample: int, label: str) -> dict:
        rng = np.random.RandomState(7)
        cols = list(closes.columns[closes.notna().sum() >= 260])
        rng.shuffle(cols)
        cols = cols[:n_sample]
        rets, dds = [], []
        for t in cols:
            c = closes[t].dropna()
            st = ct.tier_stream(c)
            if st.empty:
                continue
            st = st.tail(90)
            adm = st.index[st["eligible"] & st["tier"].isin(["T1", "T2"])]
            cc = c
            for d in adm:
                pos = cc.index.searchsorted(d)
                if pos < 64:
                    continue
                p = float(cc.iloc[pos])
                rets.append(p / float(cc.iloc[pos - 63]) - 1)
                hi = float(cc.iloc[max(0, pos - 252):pos + 1].max())
                dds.append(p / hi - 1)
        return {
            "label": label, "n_admissions": len(rets),
            "trail63_ret_pct": {k: round(v * 100, 1) for k, v in
                                pd.Series(rets).describe().items()} if rets else None,
            "dd_from_252d_high_pct": {k: round(v * 100, 1) for k, v in
                                      pd.Series(dds).describe().items()} if dds else None,
        }

    res["admit_character_us"] = admit_character(px, 400, "US")
    try:
        cn = pd.read_parquet("data/china_search/closes.parquet")
        res["admit_character_cn"] = admit_character(cn, 400, "CN")
    except Exception as e:  # noqa: BLE001
        res["admit_character_cn"] = {"error": str(e)}

    # E: case traces
    cases = {}
    for t in ("PLTR", "MSFT", "ORCL", "NOW", "CRWD", "PANW", "SNOW", "DDOG", "MDB", "TEAM"):
        if t not in px.columns:
            cases[t] = {"error": "not in cache"}
            continue
        legs = leg_attribution(px[t])
        win = eligibility_window(px[t])
        cases[t] = {**legs, **win, "r63_pct": round(float(r63.get(t, np.nan)) * 100, 1)}
    res["cases"] = cases
    # DLBY from yahoo store
    try:
        from engine import store
        df = store.read("yahoo", "DLBY")
        if df is not None and "close" in df:
            s = df["close"].dropna()
            cases["DLBY"] = {**leg_attribution(s), **eligibility_window(s),
                             "last_bar": str(s.index[-1].date()),
                             "r63_pct": round((float(s.iloc[-1]) / float(s.iloc[-64]) - 1) * 100, 1)
                             if len(s) > 64 else None}
        else:
            cases["DLBY"] = {"error": "no yahoo store row"}
    except Exception as e:  # noqa: BLE001
        cases["DLBY"] = {"error": str(e)}

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)

    print("asof", res["asof"], "| universe", res["universe_n"],
          "| eligible today", res["eligible_today_n"])
    print("\nTOP-63d-RUNNER EXCLUDERS:")
    for k, v in res["top63_excluder_hist"].items():
        print(f"  {k:42s} {v}")
    print("never-eligible in last 63 sessions:", res["top63_never_eligible_63d"], "/ 150")
    print("\nTOP-21d EXCLUDERS:")
    for k, v in res["top21_excluder_hist"].items():
        print(f"  {k:42s} {v}")
    print("\nELIGIBLE-TODAY sectors:", res["eligible_today_by_sector"])
    print("RUNNER sectors:        ", res["runner_sector_hist"])
    print("\nADMIT CHARACTER US:", json.dumps(res["admit_character_us"], indent=1))
    print("ADMIT CHARACTER CN:", json.dumps(res["admit_character_cn"], indent=1))
    print("\nCASES:")
    for t, cse in cases.items():
        print(" ", t, json.dumps(cse, default=str)[:360])


if __name__ == "__main__":
    main()
