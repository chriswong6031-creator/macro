"""China A-share market-internals view-models.

Pure pandas over the parquet store — every function returns a plain-Python dict
(dates as ISO strings, numbers as float/int/None) or ``None`` if its source is
missing, so scripts/build_china.py can render panels without any reachability or
crash risk. Charts are built in build_china (plotly); this module only shapes data.

Panels:
  margin_meter()   融资融券 crowd meter — financing-as-%-of-float percentile (the COT
                   analog), net financing buy, maintenance ratio, margin froth share.
  southbound_flow() 南向资金 — daily net z-score, 20d cumulative, mainland-in-HK holdings.
  credit_tape()    new RMB loans + M1-M2 scissors + a FAI/retail/trade YoY macro tape.
  flow_snaps()     AH premium, limit-up/down speculation thermometer, ETF creations.
"""
from __future__ import annotations

import pandas as pd

from lib import store


def _pctile(s: pd.Series, v: float) -> int:
    """Percentile rank (0-100) of v within s."""
    s = s.dropna()
    if s.empty:
        return 0
    return int(round((s <= v).mean() * 100))


def _series(s: pd.Series, last_days: int | None = None, ndigits: int = 3) -> dict:
    """ISO-date + value arrays for a plotly line, optionally trimmed to a tail."""
    s = s.dropna()
    if last_days is not None and not s.empty:
        s = s.loc[s.index.max() - pd.Timedelta(days=last_days):]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), ndigits) for v in s]}


def margin_meter() -> dict | None:
    bal = store.read("china_margin", "balance")
    if bal is None or bal.empty or "fin_pct_float" not in bal.columns:
        return None
    s = bal["fin_pct_float"].dropna()
    if s.empty:
        return None
    latest = float(s.iloc[-1])
    peak = float(s.max())
    nfb = bal["net_fin_buy"].dropna()
    out = {
        "fin_pct_float": round(latest, 2),
        "pctile": _pctile(s, latest),                       # vs 2010-present
        "chg_20d": round(latest - float(s.iloc[-21]), 2) if len(s) > 21 else None,
        "peak": round(peak, 2),
        "peak_date": s.idxmax().strftime("%Y-%m"),
        "margin_total": round(float(bal["margin_total"].dropna().iloc[-1])),   # 亿元
        "net_fin_buy": round(float(nfb.iloc[-1]), 1) if not nfb.empty else None,
        "net_fin_buy_20d": round(float(nfb.tail(20).sum())) if not nfb.empty else None,
        "chart": _series(s, last_days=2200),                # ~6y line
    }
    dt = store.read("china_margin", "daily_trade")
    if dt is not None and not dt.empty:
        g = dt["guarantee_ratio"].dropna()
        t = dt["trade_amt_ratio"].dropna()
        inv = dt["liab_investors"].dropna()
        if not g.empty:
            out["guarantee_ratio"] = round(float(g.iloc[-1]), 1)
            out["guarantee_pctile"] = _pctile(g, float(g.iloc[-1]))
        if not t.empty:
            out["trade_amt_ratio"] = round(float(t.iloc[-1]), 1)
            out["trade_amt_pctile"] = _pctile(t, float(t.iloc[-1]))
        if not inv.empty:
            out["liab_investors"] = int(inv.iloc[-1])
    return out


def southbound_flow() -> dict | None:
    sb = store.read("china_connect", "southbound")
    if sb is None or sb.empty or "net" not in sb.columns:
        return None
    net = sb["net"].dropna()
    if net.empty:
        return None
    win = net.tail(252)
    mu, sd = float(win.mean()), float(win.std() or 1.0)
    latest = float(net.iloc[-1])
    cum20 = net.rolling(20).sum()
    out = {
        "net": round(latest, 1),
        "net_z": round((latest - mu) / sd, 2),
        "cum_20d": round(float(net.tail(20).sum()), 1),
        "pos_days_20": int((net.tail(20) > 0).sum()),
        "chart_cum": _series(cum20, last_days=730, ndigits=1),   # 20d-cumulative net, ~2y
    }
    hold = sb["hold_mktcap"].dropna() if "hold_mktcap" in sb.columns else pd.Series(dtype=float)
    if not hold.empty:
        out["hold_mktcap"] = round(float(hold.iloc[-1]))          # 亿元
        out["hold_chart"] = _series(hold, last_days=730, ndigits=0)
    nb = store.read("china_connect", "northbound")
    if nb is not None and not nb.empty and "turnover" in nb.columns:
        tn = nb["turnover"].dropna()
        if not tn.empty:
            out["nb_turnover"] = round(float(tn.iloc[-1]))
    return out


def southbound_price_divergence(window: int = 63) -> dict | None:
    """DISPLAY-ONLY context chip: is the southbound-net FLOW trend pulling the same
    way as the HSI PRICE trend over a ~quarter window?  Descriptive, not a signal —
    NOT wired into hk_axes / hk_regime / MRS.  z-trend of window-cumulative southbound
    net vs window HSI return.  Returns None if either series is missing/too short."""
    sb = store.read("china_connect", "southbound")
    if sb is None or sb.empty or "net" not in sb.columns:
        return None
    net = sb["net"].dropna()
    px = store.read("hk", "^HSI")          # store sanitizes "^HSI" -> data/hk/_HSI.parquet
    if px is None or "close" not in px.columns:
        return None
    close = px["close"].dropna()
    # need a full window plus a baseline for the z, on BOTH series
    if len(net) < window + 20 or len(close) < window + 5:
        return {"state": "insufficient", "n_flow": int(len(net)), "n_px": int(len(close))}

    # FLOW trend: window-cumulative southbound net, z-scored vs its own 1y history
    cum = net.rolling(window).sum()
    base = cum.dropna().tail(252)
    if len(base) < 30:
        return {"state": "insufficient", "n_flow": int(len(net)), "n_px": int(len(close))}
    mu, sd = float(base.mean()), float(base.std() or 1.0)   # `or 1.0` zero-sigma guard, per southbound_flow()
    flow_z = (float(cum.iloc[-1]) - mu) / sd                # >0 = flows accelerating IN

    # PRICE trend: window return of HSI
    px_ret = float(close.iloc[-1] / close.iloc[-window] - 1.0)   # >0 = price up

    # deterministic neutral bands (z and pct both with a dead-zone to avoid flicker)
    Z_HI, RET_HI = 0.5, 0.02
    flow_up = flow_z >= Z_HI
    flow_dn = flow_z <= -Z_HI
    px_up = px_ret >= RET_HI
    px_dn = px_ret <= -RET_HI

    if (flow_up and px_up) or (flow_dn and px_dn):
        state = "confirms"          # flow and price agree (both up or both down)
    elif (flow_up and px_dn) or (flow_dn and px_up):
        state = "diverges"          # flow and price disagree
    else:
        state = "mixed"             # one or both in the dead-zone

    return {
        "state": state,             # confirms | diverges | mixed | insufficient
        "flow_z": round(flow_z, 2),
        "px_ret_pct": round(px_ret * 100, 1),
        "window_d": window,
    }


def _macro(name: str, col: str) -> pd.Series:
    df = store.read("china_macro", name)
    if df is None or df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].dropna()


def credit_tape() -> dict | None:
    loans = _macro("rmb_loan", "new_loans")
    loans_yoy = _macro("rmb_loan", "new_loans_yoy")
    ms = store.read("china_macro", "money_supply")
    scissors = pd.Series(dtype=float)
    if ms is not None and {"m1_yoy", "m2_yoy"}.issubset(ms.columns):
        scissors = (ms["m1_yoy"] - ms["m2_yoy"]).dropna()    # 剪刀差
    if loans.empty and scissors.empty:
        return None
    out: dict = {}
    if not loans.empty:
        out["new_loans"] = round(float(loans.iloc[-1]))                      # 亿元
        out["new_loans_yoy"] = round(float(loans_yoy.iloc[-1]), 1) if not loans_yoy.empty else None
        out["loans_chart"] = _series(loans, last_days=1130, ndigits=0)       # ~3y bars
    if not scissors.empty:
        out["scissors"] = round(float(scissors.iloc[-1]), 1)
        out["scissors_chart"] = _series(scissors, last_days=1130, ndigits=1)
    # social financing (社融) + credit impulse — the marquee China macro lead
    tsf = store.read("china_credit", "tsf")
    if tsf is not None and not tsf.empty and "tsf_total" in tsf.columns:
        t = tsf["tsf_total"].dropna()
        if len(t) >= 24:
            tsf12 = t.rolling(12).sum()
            impulse = (tsf12.pct_change(12) * 100).dropna()
            if not impulse.empty:
                out["credit_impulse"] = round(float(impulse.iloc[-1]), 1)
                out["credit_impulse_6mo"] = round(float(impulse.iloc[-7]), 1) if len(impulse) > 7 else None
                out["impulse_chart"] = _series(impulse, last_days=1900, ndigits=1)
                out["tsf_12m"] = round(float(tsf12.iloc[-1]) / 10000, 1)        # 万亿
                out["tsf_month"] = round(float(t.iloc[-1]))                      # 亿
                last = tsf.iloc[-1]
                g = lambda c: float(last.get(c) or 0)  # noqa: E731
                out["tsf_mix"] = {"bank": round(g("rmb_loans") + g("fx_loans")),
                                  "bond": round(g("corp_bonds")),
                                  "shadow": round(g("entrust") + g("trust") + g("accept_bills")),
                                  "equity": round(g("equity"))}
    # macro tape — latest YoY + a short spark per series
    tape = []
    for key, col, en, zh in (
        ("fai", "fai_yoy", "Fixed-asset inv.", "固定资产投资"),
        ("retail", "retail_yoy", "Retail sales", "社会消费品零售"),
        ("customs", "exports_yoy", "Exports", "出口"),
        ("customs", "imports_yoy", "Imports", "进口"),
    ):
        s = _macro(key, col)
        if s.empty:
            continue
        tape.append({"en": en, "zh": zh, "val": round(float(s.iloc[-1]), 1),
                     "spark": [round(float(v), 1) for v in s.tail(24)]})
    if tape:
        out["tape"] = tape
    return out or None


def market_turnover() -> dict | None:
    """Whole-market (沪+深) daily turnover, derived for free from the margin data:
    margin_trade_amt / trade_amt_ratio * 100. The canonical A-share retail-mania
    gauge — '万亿成交' (trillion-yuan turnover) = froth, sub-0.7T = apathy."""
    dt = store.read("china_margin", "daily_trade")
    if dt is None or dt.empty or not {"margin_trade_amt", "trade_amt_ratio"}.issubset(dt.columns):
        return None
    ratio = dt["trade_amt_ratio"].where(dt["trade_amt_ratio"] > 0)
    turn = (dt["margin_trade_amt"] / ratio * 100).dropna()    # 亿元
    if turn.empty:
        return None
    latest = float(turn.iloc[-1])
    # well-known two-market turnover bands (亿元)
    band = ("apathy" if latest < 7000 else "normal" if latest < 12000
            else "active" if latest < 18000 else "mania")
    return {
        "turnover_t": round(latest / 10000, 2),               # 万亿 / ¥T
        "pctile": _pctile(turn, latest),
        "band": band,
        "chart": _series(turn, last_days=900, ndigits=0),
    }


def pboc_policy() -> dict | None:
    """PBoC reserve-requirement-ratio (存款准备金率) policy events. RRR cuts = easing
    (frees bank liquidity), the most-watched China policy lever for equity liquidity."""
    d = store.read("china_macro", "rrr")
    if d is None or d.empty or "rrr_big" not in d.columns:
        return None
    big = d["rrr_big"].dropna()
    if big.empty:
        return None
    ev = d[d["rrr_change"].notna() & (d["rrr_change"] != 0)].sort_index()
    events = [{"date": idx.strftime("%Y-%m-%d"), "change": round(float(r["rrr_change"]), 2),
               "level": round(float(r["rrr_big"]), 2) if pd.notna(r["rrr_big"]) else None,
               "dir": "cut" if r["rrr_change"] < 0 else "hike"}
              for idx, r in ev.tail(6).iterrows()][::-1]   # newest first
    cut2y = d.loc[d.index >= (d.index.max() - pd.Timedelta(days=730)), "rrr_change"].dropna()
    net2y = round(float(cut2y.sum()), 2) if not cut2y.empty else 0.0
    return {"rrr_big": round(float(big.iloc[-1]), 2), "events": events, "last": events[0] if events else None,
            "net_2y": net2y, "bias": "easing" if net2y < 0 else "tightening" if net2y > 0 else "neutral"}


def flow_snaps() -> dict | None:
    out: dict = {}
    ah = store.read("china_flows", "ah_premium")
    if ah is not None and not ah.empty and "hsahp" in ah.columns:
        s = ah["hsahp"].dropna()
        if not s.empty:
            out["ah"] = {"level": round(float(s.iloc[-1]), 1),
                         "pctile": _pctile(s, float(s.iloc[-1])) if len(s) > 30 else None,
                         "n": int(len(s))}
    lb = store.read("china_flows", "limit_breadth")
    if lb is not None and not lb.empty and "zt" in lb.columns:
        last = lb.iloc[-1]
        out["limit"] = {
            "zt": int(last.get("zt", 0)), "dt": int(last.get("dt", 0)),
            "zb": int(last.get("zb", 0)),
            "seal_rate": round(float(last["seal_rate"]), 1) if pd.notna(last.get("seal_rate")) else None,
            "date": lb.index[-1].strftime("%Y-%m-%d"),
            "zt_chart": _series(lb["zt"], ndigits=0), "dt_chart": _series(lb["dt"], ndigits=0),
        }
    etf = store.read("china_flows", "etf_shares")
    if etf is not None and len(etf) >= 2:
        d = (etf.iloc[-1] - etf.iloc[-2])           # net creation in shares
        net = float(d.sum())
        out["etf"] = {"net_creation": round(net), "days": int(len(etf)),
                      "up": int((d > 0).sum()), "down": int((d < 0).sum())}
    elif etf is not None and len(etf) == 1:
        out["etf"] = {"building": True, "days": 1}
    return out or None
