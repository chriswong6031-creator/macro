"""Insider Power — per-ticker, quality-weighted Form-4 insider score (0..100).

The StockInvest-style "Insider Power" read, built on the point-in-time SEC
Form-4 per-transaction panel (`collectors/sec_insider.backfill_panel` →
`data/sec_insider/insider_panel.parquet`). This is the per-NAME companion to the
cross-sectional research factor in `engine/insider_factor.py`: it reuses that
module's role weighting and the P/S open-market convention, but instead of
ranking the universe it emits a single 0..100 conviction score per ticker plus
the display payload the Mastermind Terminal "Insider" tab renders.

Construction (as-of a date D, over a trailing window of FILINGS). Each trade
carries a signed conviction weight:

    w = sign · role · recency · size
      sign     +1 buy (code P) / −1 sell (code S)
      role     CEO/CFO/… 1.5 · officer 1.0 · director 0.6 · 10% holder 0.3 · other 0.2
      recency  0.5 ** (age_days / 90)         # 90-day half-life
      size     log10(1 + usd / 1e4)           # compress $ so one $10m ticket
                                              #   doesn't drown a cluster of small buys

The score is the NET weight NORMALISED by gross activity, so it reads as a
quality-weighted balance in (−1, 1) rather than an unbounded sum that just
tracks how liquid the name is (a raw Σw saturates instantly for a mega-cap where
insiders sell every quarter — the exact "sum every trade into one number
destroys the signal" failure engine/insider_factor.py warns about):

    bal   = Σ w  /  (Σ |w| + K)               # K = activity floor → thin tapes pull to neutral
    score = 50 + 50 · tanh(GAIN · bal)        # 50 = neutral, →100 all-buy, →0 all-sell

It is quality-weighted, NOT a raw buy/sell count ratio: a single recent CEO
purchase can outweigh a pile of routine small director sales, and — because the
log-dollar term and role weights can flip the sign versus naive net dollars — a
name can carry a positive Power Score while its net-dollar VOLUME is negative.
That divergence is what drives the display confidence below.

Signals: ``insider_buy`` fires at score ≥ 60, ``insider_sell`` at score ≤ 40 —
the score-threshold booleans. The DISPLAY signal + confidence (the
"SELL SIGNAL — Low Confidence: contradicted by a positive Insider Power Score"
line) reads the naive net-dollar flow direction against the quality-weighted
score: when the two DISAGREE the signal is low-confidence, exactly the
StockInvest UX.

Everything is causal: a trade enters only once its FILING_DATE ≤ D (the date it
became public). Pure compute (no I/O) — `scripts/export_insider_power.py` feeds
it the panel slice and writes the per-ticker JSON artifacts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Title keywords that mark a top-of-house officer (weighted above a line officer)
# — kept in sync with engine/insider_factor._TOP_TITLE.
_TOP_TITLE = ("CHIEF EXEC", "CEO", "CHIEF FIN", "CFO", "PRESIDENT", "CHAIR",
              "FOUNDER", "CHIEF OPER", "COO", "PRINCIPAL EXEC", "PRINCIPAL FIN")

HALF_LIFE_DAYS = 90.0    # recency decay: a 90-day-old filing counts half
WINDOW_DAYS = 365        # trailing window that feeds the score + headline stats
SERIES_MONTHS = 24       # trailing months drawn in the buy/sell-volume chart
ACTIVITY_FLOOR = 2.0     # K: gross-weight floor → thin/one-off tapes stay near neutral
SCORE_GAIN = 2.0         # tanh gain on the normalised balance (spread the 0..100 range)
BUY_THRESHOLD = 60.0     # insider_buy fires at/above  (≈ +0.10 net weighted buy tilt)
SELL_THRESHOLD = 40.0    # insider_sell fires at/below (≈ −0.10 net weighted sell tilt)
MAX_TRADES = 40          # recent open-market trades kept for the display table

_ROLE_WEIGHT = {"top": 1.5, "officer": 1.0, "director": 0.6, "tenpct": 0.3, "other": 0.2}
_ROLE_LABEL = {"top": "Top exec", "officer": "Officer", "director": "Director",
               "tenpct": "10% owner", "other": "Insider"}


def _role_bucket(title: str, is_officer: bool, is_director: bool, is_tenpct: bool) -> str:
    """Bucket a filer into the conviction tiers used by role weighting."""
    up = title.upper() if isinstance(title, str) else ""
    if is_officer and any(k in up for k in _TOP_TITLE):
        return "top"
    if is_officer:
        return "officer"
    if is_director:
        return "director"
    if is_tenpct:
        return "tenpct"
    return "other"


def score_from_balance(net_w: float, gross_w: float) -> float:
    """Map the activity-normalised conviction balance onto the 0..100 scale.

    `net_w` = Σ signed weights, `gross_w` = Σ |weights|. The balance
    net_w / (gross_w + K) sits in (−1, 1); K keeps thin tapes near 50."""
    bal = net_w / (gross_w + ACTIVITY_FLOOR)
    return round(50.0 + 50.0 * math.tanh(SCORE_GAIN * bal), 1)


def _signal_and_confidence(score: float, net_usd: float, buyers: int, sellers: int) -> tuple[str, str, str]:
    """StockInvest-style headline signal + confidence + analysis breakdown.

    The naive net-dollar flow gives the buy/sell VOLUME signal; the quality-
    weighted `score` either confirms or contradicts it. Disagreement → low
    confidence (the score is the higher-quality read)."""
    if buyers == 0 and sellers == 0:
        return "NEUTRAL", "None", "No recent open-market insider activity."

    if net_usd > 0:
        flow = "BUY"
    elif net_usd < 0:
        flow = "SELL"
    else:
        flow = "BUY" if score >= 50 else "SELL"

    agree = (flow == "BUY" and score >= 50) or (flow == "SELL" and score <= 50)
    strength = abs(score - 50)
    breadth = buyers if flow == "BUY" else sellers

    if not agree:
        conf = "Low"
    elif strength >= 15 or breadth >= 3:
        conf = "High"
    else:
        conf = "Medium"

    s = f"{score:.0f}"
    if flow == "BUY":
        if agree:
            analysis = (f"BUY SIGNAL — {conf} Confidence: confirmed by a positive "
                        f"Insider Power Score ({s}); {buyers} insider buyer"
                        f"{'' if buyers == 1 else 's'} vs {sellers} seller"
                        f"{'' if sellers == 1 else 's'}.")
        else:
            analysis = (f"BUY SIGNAL — Low Confidence: contradicted by a negative "
                        f"Insider Power Score ({s}).")
    else:  # SELL
        if agree:
            analysis = (f"SELL SIGNAL — {conf} Confidence: confirmed by a negative "
                        f"Insider Power Score ({s}); {sellers} insider seller"
                        f"{'' if sellers == 1 else 's'} vs {buyers} buyer"
                        f"{'' if buyers == 1 else 's'}.")
        else:
            analysis = (f"SELL SIGNAL — Low Confidence: contradicted by a positive "
                        f"Insider Power Score ({s}).")
    return flow, conf, analysis


def _prep(panel: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Slice to causal open-market (P/S) trades in the trailing SERIES window and
    attach the per-row role weight, recency and compressed-dollar size."""
    lo = asof - pd.Timedelta(days=int(SERIES_MONTHS * 31))
    p = panel[(panel["code"].isin(("P", "S")))
              & (panel["filing_date"] <= asof)
              & (panel["filing_date"] > lo)].copy()
    if p.empty:
        return p
    bucket = [
        _role_bucket(t, o, d, x)
        for t, o, d, x in zip(p["title"].tolist(), p["is_officer"].tolist(),
                              p["is_director"].tolist(), p["is_tenpct"].tolist())
    ]
    p["role"] = bucket
    p["role_w"] = p["role"].map(_ROLE_WEIGHT).astype(float)
    age = (asof - p["filing_date"]).dt.days.clip(lower=0).to_numpy(dtype=float)
    p["recency"] = np.power(0.5, age / HALF_LIFE_DAYS)
    usd = p["usd"].fillna(0.0).abs().to_numpy(dtype=float)
    p["size_w"] = np.log10(1.0 + usd / 1e4)
    p["sign"] = np.where(p["code"].to_numpy() == "P", 1.0, -1.0)
    p["contrib"] = p["sign"] * p["role_w"] * p["recency"] * p["size_w"]
    p["month"] = p["filing_date"].dt.strftime("%Y-%m")
    return p


def _ticker_payload(g: pd.DataFrame, ticker: str, asof: pd.Timestamp) -> dict:
    """Build one ticker's Insider Power artifact from its prepared trade slice."""
    win_lo = asof - pd.Timedelta(days=WINDOW_DAYS)
    win = g[g["filing_date"] > win_lo]
    buys = win[win["code"] == "P"]
    sells = win[win["code"] == "S"]

    score = score_from_balance(float(win["contrib"].sum()), float(win["contrib"].abs().sum()))
    buyers = int(buys["rptownercik"].nunique())
    sellers = int(sells["rptownercik"].nunique())
    buy_usd = float(buys["usd"].fillna(0.0).sum())
    sell_usd = float(sells["usd"].fillna(0.0).sum())
    buy_shares = float(buys["shares"].fillna(0.0).sum())
    sell_shares = float(sells["shares"].fillna(0.0).sum())
    net_usd = buy_usd - sell_usd

    signal, confidence, analysis = _signal_and_confidence(score, net_usd, buyers, sellers)

    # ── monthly buy/sell volume series (full SERIES window, oldest→newest) ──
    months = pd.period_range(
        pd.Timestamp(asof).to_period("M") - (SERIES_MONTHS - 1),
        pd.Timestamp(asof).to_period("M"), freq="M").strftime("%Y-%m")
    b_usd = g[g["code"] == "P"].groupby("month")["usd"].sum()
    s_usd = g[g["code"] == "S"].groupby("month")["usd"].sum()
    b_sh = g[g["code"] == "P"].groupby("month")["shares"].sum()
    s_sh = g[g["code"] == "S"].groupby("month")["shares"].sum()
    series = []
    for m in months:
        bu = float(b_usd.get(m, 0.0) or 0.0)
        su = float(s_usd.get(m, 0.0) or 0.0)
        series.append({
            "month": m,
            "buy_usd": round(bu, 2),
            "sell_usd": round(su, 2),
            "buy_shares": float(b_sh.get(m, 0.0) or 0.0),
            "sell_shares": float(s_sh.get(m, 0.0) or 0.0),
            "net_usd": round(bu - su, 2),
        })

    # ── recent individual open-market trades (newest first) for the table + markers ──
    recent = g.sort_values("filing_date", ascending=False).head(MAX_TRADES)
    trades = []
    for r in recent.itertuples(index=False):
        trades.append({
            "date": pd.Timestamp(r.filing_date).strftime("%Y-%m-%d"),
            "trade_date": pd.Timestamp(r.trans_date).strftime("%Y-%m-%d") if pd.notna(r.trans_date) else None,
            "code": r.code,
            "side": "buy" if r.code == "P" else "sell",
            "role": _ROLE_LABEL.get(r.role, "Insider"),
            "title": (r.title if isinstance(r.title, str) and r.title.strip() else _ROLE_LABEL.get(r.role, "Insider")),
            "shares": None if pd.isna(r.shares) else float(r.shares),
            "price": None if pd.isna(r.price) else round(float(r.price), 4),
            "usd": None if pd.isna(r.usd) else round(float(r.usd), 2),
            "weight": round(float(r.role_w), 2),
        })

    return {
        "ticker": ticker,
        "asof": pd.Timestamp(asof).strftime("%Y-%m-%d"),
        "window_days": WINDOW_DAYS,
        "score": score,
        "signal": signal,
        "confidence": confidence,
        "analysis": analysis,
        "insider_buy": bool(score >= BUY_THRESHOLD),
        "insider_sell": bool(score <= SELL_THRESHOLD),
        "buyers": buyers,
        "sellers": sellers,
        "buy_usd": round(buy_usd, 2),
        "sell_usd": round(sell_usd, 2),
        "net_usd": round(net_usd, 2),
        "buy_shares": buy_shares,
        "sell_shares": sell_shares,
        "series": series,
        "trades": trades,
    }


def compute(panel: pd.DataFrame, asof: pd.Timestamp | str | None = None,
            tickers: list[str] | None = None) -> dict[str, dict]:
    """Return ``{ticker: payload}`` for every ticker with open-market (P/S)
    activity in the trailing window before `asof`.

    `panel` is the per-transaction Form-4 panel (columns: ticker, filing_date,
    trans_date, rptownercik, code, is_officer/is_director/is_tenpct, title,
    shares, price, usd). `asof` defaults to the panel's latest filing date.
    `tickers` optionally restricts the universe (case-insensitive)."""
    if asof is None:
        asof = panel["filing_date"].max()
    asof = pd.Timestamp(asof)
    p = _prep(panel, asof)
    if p.empty:
        return {}
    if tickers:
        want = {t.upper() for t in tickers}
        p = p[p["ticker"].str.upper().isin(want)]
    out: dict[str, dict] = {}
    for ticker, g in p.groupby("ticker", sort=False):
        payload = _ticker_payload(g, str(ticker), asof)
        # Skip names with zero activity in the SCORE window (series-only tails):
        if payload["buyers"] == 0 and payload["sellers"] == 0:
            continue
        out[str(ticker)] = payload
    return out
