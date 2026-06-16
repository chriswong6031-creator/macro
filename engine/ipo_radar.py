"""IPO Radar — DISPLAY-ONLY, NEVER-SCORED IPO context layer.

Background (research/IPO_RADAR.md, 2026-06-16): the IPO day-1 "pop" is genuinely
predictable out-of-sample (Huang-Jiang-Li-Wu; Çolak-Fu-Hasan), BUT it is measured
from the *rationed offer price* and the opening trade already prices it in
(Ritter-Welch) — so it is NOT capturable for anyone without offer-price allocation.
Held from the first close, IPOs *underperform* (Ritter: median 3y −25.7%; the
Renaissance IPO ETF has trailed the S&P badly). So this module DOES NOT predict
pops. It is an honest AVOIDANCE + CONTEXT tool:

  * window_context()  — is the issuance window hot or cold RIGHT NOW (coincident
                        risk-appetite, reusing the validated macro de-risk read +
                        breadth/credit/spec legs). Describes, never forecasts.
  * aftermarket_basket() — the reality check: how the "buy new IPOs in the
                        secondary market" trade (IPO / FPX ETFs) has actually done
                        vs SPY. This is the honest anchor of the whole page.
  * pipeline_stats() / recent_listings() / upcoming_listings() — the deal calendar
                        from collectors/ipo_calendar (offer terms + SPAC flag).

NOTHING here is a scored signal and nothing here feeds any axis, regime, or
allocation. `SCORED = False` is asserted by tests/test_ipo.py (the never-score
invariant). All numbers are descriptive.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from lib import store

# Invariant marker read by tests: this layer must never become a scored input.
SCORED = False

RS_LOOKBACK = 63   # ~3 trading months for the relative-strength legs


# --------------------------------------------------------------------------- #
# price helpers (data/yahoo)
# --------------------------------------------------------------------------- #
def _close(ticker: str) -> pd.Series | None:
    try:
        df = store.read("yahoo", ticker)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or "close" not in df:
        return None
    return df["close"].astype(float).dropna()


def _rs(num: str, den: str, lookback: int = RS_LOOKBACK) -> float | None:
    """Trailing relative outperformance of `num` vs `den` over `lookback` sessions."""
    a, b = _close(num), _close(den)
    if a is None or b is None:
        return None
    r = (a / b.reindex(a.index).ffill()).dropna()
    if len(r) < lookback + 1:
        return None
    return float(r.iloc[-1] / r.iloc[-lookback - 1] - 1.0)


def _ann_ret(s: pd.Series | None, years: float) -> float | None:
    if s is None or s.empty:
        return None
    end = s.index[-1]
    start = end - pd.DateOffset(years=int(years))
    sl = s[s.index <= start]
    if sl.empty:
        return None
    p0 = float(sl.iloc[-1])
    if p0 <= 0:
        return None
    return float((float(s.iloc[-1]) / p0) ** (1.0 / years) - 1.0)


# --------------------------------------------------------------------------- #
# 1) IPO window — coincident risk-appetite backdrop (display-only)
# --------------------------------------------------------------------------- #
def window_context(risk_score: float | None = None) -> dict:
    """Hot/warm/cold issuance-window read. `risk_score` = the validated macro
    de-risk score (0-100, high = de-risk); passed in by the build so we reuse a
    PIT-validated read rather than invent a new one. All legs are coincident."""
    legs: list[dict] = []

    def add(key, label, value, state, note):
        legs.append({"key": key, "label": label, "value": value,
                     "state": state, "note": note})

    # macro risk backdrop (reuse the validated de-risk score; low = constructive)
    if risk_score is not None:
        rs = float(risk_score)
        st = ("constructive" if rs < 25 else "neutral" if rs < 50
              else "cautious" if rs < 75 else "hostile")
        add("macro", "Macro risk backdrop", round(rs),
            st, "validated de-risk score (reused, not new)")

    # volatility — calm = open window
    vix = _close("^VIX")
    if vix is not None and len(vix):
        v = float(vix.iloc[-1])
        st = ("constructive" if v < 16 else "neutral" if v < 22
              else "cautious" if v < 30 else "hostile")
        add("vix", "Volatility (VIX)", round(v, 1), st, "low vol = receptive tape")

    # credit appetite — HY outperforming IG = risk-on
    cr = _rs("HYG", "LQD")
    if cr is not None:
        st = "constructive" if cr > 0.005 else "cautious" if cr < -0.005 else "neutral"
        add("credit", "Credit appetite (HY vs IG)", round(cr * 100, 1), st,
            "high-yield leading = risk-on credit")

    # small-cap leadership — broad risk appetite
    sc = _rs("IWM", "SPY")
    if sc is not None:
        st = "constructive" if sc > 0.01 else "cautious" if sc < -0.01 else "neutral"
        add("smallcap", "Small-cap leadership (IWM vs SPY)", round(sc * 100, 1), st,
            "small-caps leading = appetite for risk/new names")

    # speculative appetite — high-beta vs low-vol
    sp = _rs("SPHB", "SPLV")
    if sp is not None:
        st = "constructive" if sp > 0.01 else "cautious" if sp < -0.01 else "neutral"
        add("spec", "Speculative appetite (high-beta vs low-vol)", round(sp * 100, 1), st,
            "high-beta leading = speculative bid")

    # IPO aftermarket trend — recent-IPO basket vs market
    ipo = _rs("IPO", "SPY")
    if ipo is not None:
        st = "constructive" if ipo > 0.01 else "cautious" if ipo < -0.01 else "neutral"
        add("ipo_etf", "IPO basket trend (IPO vs SPY)", round(ipo * 100, 1), st,
            "recent-IPO ETF leading = aftermarket demand")

    cons = sum(1 for l in legs if l["state"] == "constructive")
    host = sum(1 for l in legs if l["state"] in ("cautious", "hostile"))
    n = len(legs)
    if n == 0:
        band = "unknown"
    elif cons >= max(2, n * 0.5) and cons > host:
        band = "OPEN"
    elif host >= max(2, n * 0.5) and host > cons:
        band = "SHUT"
    else:
        band = "MIXED"

    return {
        "band": band, "constructive": cons, "hostile": host, "n_legs": n,
        "legs": legs,
        "note": ("Coincident risk-appetite read — it describes whether the issuance "
                 "window is open NOW; it does not forecast it, and it is never scored."),
    }


# --------------------------------------------------------------------------- #
# 2) Aftermarket basket — the honest reality check
# --------------------------------------------------------------------------- #
def aftermarket_basket() -> dict:
    """How the mechanical 'buy new IPOs in the secondary market' trade (Renaissance
    IPO ETF + First Trust IPOX) has actually done vs SPY. The page's honest anchor."""
    spy = _close("SPY")
    out = {"rows": [], "verdict": None, "as_of": None}
    if spy is not None and len(spy):
        out["as_of"] = spy.index[-1].strftime("%Y-%m-%d")
    names = {"IPO": "Renaissance IPO ETF", "FPX": "First Trust IPOX-100", "SPY": "S&P 500"}
    horizons = [("1y", 1), ("3y", 3), ("5y", 5)]
    series = {t: _close(t) for t in names}
    for t, label in names.items():
        s = series[t]
        row = {"ticker": t, "label": label}
        for hk, hy in horizons:
            row[hk] = _ann_ret(s, hy)
        out["rows"].append(row)

    ipo5, spy5 = _ann_ret(series.get("IPO"), 5), _ann_ret(spy, 5)
    if ipo5 is not None and spy5 is not None:
        out["ipo_5y"], out["spy_5y"] = ipo5, spy5
        out["gap_5y"] = ipo5 - spy5
        out["verdict"] = ("trails" if ipo5 < spy5 - 0.01 else
                          "tracks" if abs(ipo5 - spy5) <= 0.01 else "beats")
    return out


# --------------------------------------------------------------------------- #
# 3) deal calendar (collectors/ipo_calendar -> data/ipo/calendar.parquet)
# --------------------------------------------------------------------------- #
def _load() -> pd.DataFrame:
    try:
        from collectors.ipo_calendar import load_calendar
        return load_calendar()
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _size_band(v: float | None) -> str | None:
    if v is None:
        return None
    return ("mega" if v >= 1e9 else "large" if v >= 3e8
            else "mid" if v >= 1e8 else "small")


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    d = pd.to_datetime(iso, errors="coerce")
    if pd.isna(d):
        return None
    return int((datetime.now(timezone.utc).date() - d.date()).days)


def _since_offer(ticker: str | None, offer: float | None) -> float | None:
    """Return-vs-offer only when we already have the price series (rare: most
    fresh IPOs are outside our ETF-holdings universe). Honest blank otherwise."""
    if not ticker or not offer or offer <= 0:
        return None
    s = _close(ticker)
    if s is None or s.empty:
        return None
    return float(s.iloc[-1] / offer - 1.0)


def recent_listings(cal: pd.DataFrame | None = None, days: int = 120,
                    limit: int = 30) -> list[dict]:
    cal = _load() if cal is None else cal
    if cal.empty or "status" not in cal:
        return []
    p = cal[cal["status"] == "priced"].copy()
    if p.empty:
        return []
    p["_dsl"] = p["priced_date"].map(_days_since)
    p = p[p["_dsl"].notna() & (p["_dsl"] <= days)]
    p = p.sort_values("priced_date", ascending=False)
    rows = []
    for _, r in p.head(limit).iterrows():
        offer = r.get("offer_price")
        rows.append({
            "ticker": r.get("ticker"), "company": r.get("company"),
            "exchange": r.get("exchange"), "offer_price": offer,
            "size_usd": r.get("offer_value_usd"), "size_band": _size_band(r.get("offer_value_usd")),
            "priced_date": r.get("priced_date"), "days_since": int(r["_dsl"]),
            "is_spac": bool(r.get("is_spac")),
            "since_offer": _since_offer(r.get("ticker"), offer),
        })
    return rows


def upcoming_listings(cal: pd.DataFrame | None = None, limit: int = 15) -> list[dict]:
    cal = _load() if cal is None else cal
    if cal.empty or "status" not in cal:
        return []
    u = cal[cal["status"] == "upcoming"].copy()
    if u.empty:
        return []
    u = u.sort_values("expected_date", na_position="last")
    rows = []
    for _, r in u.head(limit).iterrows():
        rows.append({
            "ticker": r.get("ticker"), "company": r.get("company"),
            "exchange": r.get("exchange"),
            "range_low": r.get("range_low"), "range_high": r.get("range_high"),
            "size_usd": r.get("offer_value_usd"), "size_band": _size_band(r.get("offer_value_usd")),
            "expected_date": r.get("expected_date"), "is_spac": bool(r.get("is_spac")),
        })
    return rows


def pipeline_stats(cal: pd.DataFrame | None = None) -> dict:
    cal = _load() if cal is None else cal
    if cal.empty or "status" not in cal:
        return {"available": False}
    priced = cal[cal["status"] == "priced"].copy()
    priced["_dsl"] = priced["priced_date"].map(_days_since)
    p30 = priced[priced["_dsl"].notna() & (priced["_dsl"] <= 30)]
    p90 = priced[priced["_dsl"].notna() & (priced["_dsl"] <= 90)]
    op90 = p90[~p90["is_spac"].astype(bool)]
    spac90 = int(p90["is_spac"].astype(bool).sum())
    wd = cal[cal["status"] == "withdrawn"].copy()
    wd["_dsw"] = wd["withdraw_date"].map(_days_since)
    upcoming_n = int((cal["status"] == "upcoming").sum())
    filed_n = int((cal["status"] == "filed").sum())
    med_size = (float(op90["offer_value_usd"].median())
                if "offer_value_usd" in op90 and op90["offer_value_usd"].notna().any() else None)
    n90 = len(p90)
    spac_pct = round(spac90 / n90 * 100) if n90 else None
    # descriptive pace/froth tags (no base-rate edge claimed)
    pace = ("busy" if n90 >= 45 else "normal" if n90 >= 15 else "quiet")
    froth = ("elevated SPAC share" if (spac_pct or 0) >= 40 else None)
    return {
        "available": True,
        "priced_30d": len(p30), "priced_90d": n90,
        "operating_90d": len(op90), "spac_90d": spac90, "spac_pct_90d": spac_pct,
        "withdrawn_90d": int((wd["_dsw"].notna() & (wd["_dsw"] <= 90)).sum()),
        "upcoming_n": upcoming_n, "filed_n": filed_n,
        "median_op_size_90d": med_size, "pace": pace, "froth": froth,
    }


# --------------------------------------------------------------------------- #
# top-level snapshot for the build + landing card
# --------------------------------------------------------------------------- #
def radar_snapshot(risk_score: float | None = None) -> dict:
    cal = _load()
    win = window_context(risk_score=risk_score)
    after = aftermarket_basket()
    pipe = pipeline_stats(cal)
    return {
        "scored": False,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "as_of": after.get("as_of"),
        "window": win,
        "aftermarket": after,
        "pipeline": pipe,
        "recent": recent_listings(cal),
        "upcoming": upcoming_listings(cal),
        "disclaimer": ("The day-1 IPO pop is an allocation good measured from the "
                       "rationed offer price — it is not capturable without an "
                       "allocation, and held from the first close IPOs underperform. "
                       "This is an avoidance + context tool, not a buy signal."),
    }
