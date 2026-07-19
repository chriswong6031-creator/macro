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

NEUTRAL-BY-DEFAULT (v2). The balance above still collapses to ≈−1 for a
sell-ONLY tape (every trade sign=−1 → Σw=−Σ|w|), which would read "maximally
bearish" for the routine 10b5-1 / equity-comp selling that is the NULL state at
nearly every large cap. House epistemics: **absence of buys is not evidence of
bearishness.** So when a name has no meaningful discretionary buying
(gross_buy ≈ 0) the score is FLOORED at the neutral band (≥40) and the signal is
NEUTRAL with ``routine_only=True`` — UNLESS the selling itself clears an
*informative-sell* bar. That bar is built only from features that separate
informative from routine selling, all computable from today's panel:

    cluster      ≥3 distinct rptownercik selling inside a 30–45d window
    baseline_z   heaviest RECENT sell_usd month ≥ BASELINE_Z σ above the name's
                 OWN older monthly sell_usd mean, taken over the 24-month series
                 slice (SERIES_MONTHS) — recent ≤90d vs the older remainder, not
                 a fixed trailing-12m window
    into_weakness a PROXY only: the recent volume-weighted sell price sits below
                 the name's own median older insider-print price (a sparse mix of
                 buys and sells) — NOT a market-price decline detector
    top_exec     a CEO/CFO/… (role bucket "top") among the RECENT sellers

The score may drop below the floor only when ≥2 of those fire; confidence "High"
requires cluster + (baseline_z or into_weakness). A RECENCY gate applies on top:
if the most-recent open-market trade is >90d old the signal decays to NEUTRAL
and confidence to None (a 2025 sell is not a 2026-07 signal).

It is quality-weighted, NOT a raw buy/sell count ratio: a single recent CEO
purchase can outweigh a pile of routine small director sales, and — because the
log-dollar term and role weights can flip the sign versus naive net dollars — a
name can carry a positive Power Score while its net-dollar VOLUME is negative.
That divergence is what drives the display confidence below.

Signals: ``insider_buy`` fires at score ≥ 60 (semantics unchanged);
``insider_sell`` now requires the INFORMATIVE-sell bar (not merely score ≤ 40),
so routine sell-only tapes never manufacture a bearish escalation. The DISPLAY
signal ∈ {BUY, SELL, NEUTRAL} + confidence ∈ {High, Medium, Low, None} is driven
by the posture above; ``routine_only`` / ``posture_reason`` / ``last_trade_age_d``
are additive display fields so consumers can render an explicit "no signal —
routine selling only" state instead of a red gauge.

Everything is causal: a trade enters only once its FILING_DATE ≤ D (the date it
became public). Pure compute (no I/O) — `scripts/export_insider_power.py` feeds
it the panel slice and writes the per-ticker JSON artifacts.

SCOPE. This neutral-by-default v2 math lives ONLY in this per-ticker Terminal
scorer. The SEPARATE cross-sectional catalog scorer in
`engine/insider_power_signals.py` (``insider_power()`` ~:222-334 and its
``insider_sell`` catalog signal ~:569) still uses the v1 saturating
50+50·tanh(raw/scale) construction and is DELIBERATELY untouched here (deferred;
it feeds the tech_score composite). Do not read this v2 fix as repo-wide.
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

# ── Neutral-by-default posture (v2) ──────────────────────────────────────────
# House epistemics: absence of buys is NOT evidence of bearishness. Routine,
# spread-out, baseline-sized selling at an equity-comp firm is the null state.
NEUTRAL_FLOOR = 45.0     # a buy-less routine tape floors here (mid-neutral band) …
NEUTRAL_MIN = 40.0       #   … and only drops to/below the sell threshold when the bar clears
GROSS_BUY_EPS = 1e-9     # "no meaningful discretionary buying" threshold on gross_buy weight
CLUSTER_MIN_SELLERS = 3  # ≥3 distinct rptownercik selling …
CLUSTER_WINDOW_DAYS = 45 #   … inside a 30–45d window → a coordinated cluster
BASELINE_Z = 1.5         # monthly sell_usd this far above the name's own older-months mean (24m series)
STALE_DAYS = 90          # most-recent open-market trade older than this → signal decays
INFORMATIVE_MIN_FIRE = 2 # score may drop below the floor only when ≥2 features fire
RECENT_SELL_DAYS = 90    # the "recent" selling burst tested against the older trailing tape

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


def _informative_sell_features(win: pd.DataFrame, g: pd.DataFrame,
                               asof: pd.Timestamp) -> dict:
    """Extract the four causal features that separate INFORMATIVE from routine
    selling for the score-window sells in `win` (a prepared slice; `g` is the
    ticker's full series-window slice used for the price/baseline references).

    All firing features read the RECENT (≤RECENT_SELL_DAYS) slice of sells only,
    so a stale burst cannot supply the informative bar; the OLDER remainder of the
    series-window slice supplies the name's own baseline / price reference.

    Returns a dict of bool flags + the numbers behind them:
      cluster       ≥ CLUSTER_MIN_SELLERS distinct rptownercik selling inside a
                    CLUSTER_WINDOW_DAYS window among the RECENT sells (a coordinated
                    exit, not a base rate)
      baseline_z    the heaviest RECENT sell-$ month is ≥ BASELINE_Z σ above the
                    name's OWN OLDER monthly sell-$ mean. The baseline spans the
                    OLDER part of the ~24-month series slice (SERIES_MONTHS), not a
                    fixed trailing-12m window; sample sd (ddof=1).
      into_weakness a PROXY: the RECENT volume-weighted sell price is below the
                    name's median OLDER insider-print price. That reference is a
                    sparse mix of buy and sell prints — it is NOT a market-price
                    decline detector, only a same-name cheaper-than-before proxy.
      top_exec      a role-bucket "top" (CEO/CFO/…) insider is among the RECENT
                    sellers

    Everything is causal: only `win`/`g` rows already gated by filing_date≤asof
    reach here (the caller preserves the insider_power.py:174 gate)."""
    sells = win[win["code"] == "S"]
    feats = {
        "cluster": False, "baseline_z": False,
        "into_weakness": False, "top_exec": False,
        "cluster_sellers": 0, "baseline_z_val": 0.0,
    }
    if sells.empty:
        return feats

    # Split the window into a RECENT selling burst vs the OLDER trailing tape
    # (both causal — all rows are already filing_date≤asof). The recent burst is
    # what a signal reads; the older tape is the name's own baseline / price ref.
    # ALL firing features (cluster, top_exec, baseline_z, into_weakness) read the
    # RECENT (≤RECENT_SELL_DAYS) slice only — a stale burst must not supply the
    # informative bar while a single recent routine trade defeats the recency gate.
    recent_lo = asof - pd.Timedelta(days=RECENT_SELL_DAYS)
    recent = sells[sells["filing_date"] > recent_lo]
    older = g[g["filing_date"] <= recent_lo]
    if recent.empty:
        return feats

    # ── cluster: distinct RECENT sellers inside a tight window ────────────────
    # Scan each recent seller-filing as a window anchor; a cluster is ≥N distinct
    # CIKs whose sells fall inside [anchor, anchor+CLUSTER_WINDOW_DAYS]. Scoped to
    # the recent slice so a stale burst can no longer fire the cluster feature.
    fd = recent["filing_date"]
    max_distinct = 0
    for anchor in fd.unique():
        a = pd.Timestamp(anchor)
        inwin = recent[(fd >= a) & (fd <= a + pd.Timedelta(days=CLUSTER_WINDOW_DAYS))]
        max_distinct = max(max_distinct, int(inwin["rptownercik"].nunique()))
    feats["cluster_sellers"] = max_distinct
    feats["cluster"] = max_distinct >= CLUSTER_MIN_SELLERS

    # ── baseline exceedance: heaviest RECENT sell-$ month vs the name's OWN
    #    older monthly sell-$ mean (baseline = older months of the 24m series
    #    slice, NOT a fixed trailing-12m window). Abstains without a
    #    ≥3-month older baseline to compare against. ─────────────────────────
    older_sells = older[older["code"] == "S"]
    if not recent.empty and not older_sells.empty:
        base = older_sells.groupby("month")["usd"].sum().astype(float)
        if len(base) >= 3:
            # sample sd (ddof=1) — baseline min length is 3 so it is defined;
            # slightly raises the firing bar vs population sd (de-escalation-safe).
            mu, sd = float(base.mean()), float(base.std(ddof=1))
            peak = float(recent.groupby("month")["usd"].sum().max())
            if sd > 0:
                z = (peak - mu) / sd
                feats["baseline_z_val"] = round(z, 2)
                feats["baseline_z"] = z >= BASELINE_Z

    # ── into-weakness: RECENT vwap sell price below the name's OLDER trailing
    #    trade-price reference (median of older trade prices). Abstains without
    #    an older tape to anchor against (stays False). ──────────────────────
    if "price" in sells.columns and not recent.empty:
        ref_px = pd.to_numeric(older["price"], errors="coerce").dropna()
        sp = pd.to_numeric(recent["price"], errors="coerce")
        sh = pd.to_numeric(recent["shares"], errors="coerce")
        w = (sp.notna() & sh.notna() & (sh > 0))
        if len(ref_px) >= 1 and w.any():
            vwap = float((sp[w] * sh[w]).sum() / sh[w].sum())
            ref = float(ref_px.median())
            if ref > 0:
                feats["into_weakness"] = vwap < ref

    # ── top-exec participation (RECENT slice only) ───────────────────────────
    feats["top_exec"] = bool((recent["role"] == "top").any())
    return feats


def _score_and_posture(base_score: float, gross_buy: float, feats: dict,
                       last_trade_age_d: int | None, buyers: int, sellers: int,
                       net_usd: float) -> dict:
    """Apply the neutral-by-default posture on top of the raw balance score.

    Returns {score, signal, confidence, routine_only, posture_reason, analysis,
    informative_sell}. `base_score` is score_from_balance(...) — the raw
    quality-weighted balance; this function only ever DE-ESCALATES it (floors a
    buy-less tape into the neutral band unless the informative bar clears)."""
    n_fire = sum(bool(feats.get(k)) for k in
                 ("cluster", "baseline_z", "into_weakness", "top_exec"))
    informative = n_fire >= INFORMATIVE_MIN_FIRE
    stale = (last_trade_age_d is not None and last_trade_age_d > STALE_DAYS)

    # No activity at all → honest neutral.
    if buyers == 0 and sellers == 0:
        return {"score": round(base_score, 1), "signal": "NEUTRAL",
                "confidence": "None", "routine_only": True,
                "posture_reason": "No recent open-market insider activity.",
                "analysis": "No recent open-market insider activity.",
                "informative_sell": False}

    buy_less = gross_buy <= GROSS_BUY_EPS

    # ── the sell-only / dominant-sell posture ────────────────────────────────
    if buy_less:
        if stale:
            score = max(base_score, NEUTRAL_FLOOR)
            reason = (f"Insiders only sold, and the most recent sale is "
                      f"{last_trade_age_d}d old — stale tape, no current signal.")
            return {"score": round(score, 1), "signal": "NEUTRAL",
                    "confidence": "None", "routine_only": True,
                    "posture_reason": reason, "analysis": reason,
                    "informative_sell": False}
        if not informative:
            # Routine selling only — floor into the neutral band, no signal.
            score = max(base_score, NEUTRAL_FLOOR)
            reason = ("Insiders only sold in the window — routine at equity-comp "
                      "firms; no informative buy/sell tilt.")
            return {"score": round(score, 1), "signal": "NEUTRAL",
                    "confidence": "None", "routine_only": True,
                    "posture_reason": reason, "analysis": reason,
                    "informative_sell": False}
        # Informative selling — the bar cleared; the score may go below the floor.
        # Confidence High needs cluster + (baseline_z or into_weakness).
        high = feats["cluster"] and (feats["baseline_z"] or feats["into_weakness"])
        conf = "High" if high else "Medium"
        score = round(min(base_score, NEUTRAL_MIN), 1)
        bits = []
        if feats["cluster"]:
            bits.append(f"{feats['cluster_sellers']} insiders sold in a tight window")
        if feats["baseline_z"]:
            bits.append("volume well above this name's own baseline")
        if feats["into_weakness"]:
            bits.append("selling into price weakness")
        if feats["top_exec"]:
            bits.append("top-exec participation")
        reason = "Informative selling — " + "; ".join(bits) + "."
        return {"score": score, "signal": "SELL", "confidence": conf,
                "routine_only": False, "posture_reason": reason,
                "analysis": reason, "informative_sell": True}

    # ── mixed / buy-present tape → StockInvest-style flow-vs-score read ───────
    if stale:
        score = round(base_score, 1)
        reason = (f"Most recent open-market trade is {last_trade_age_d}d old — "
                  "stale tape, signal decayed to neutral.")
        return {"score": score, "signal": "NEUTRAL", "confidence": "None",
                "routine_only": False, "posture_reason": reason,
                "analysis": reason, "informative_sell": False}

    score = round(base_score, 1)
    if net_usd > 0:
        flow = "BUY"
    elif net_usd < 0:
        flow = "SELL"
    else:
        flow = "BUY" if score >= 50 else "SELL"
    agree = (flow == "BUY" and score >= 50) or (flow == "SELL" and score <= 50)
    strength = abs(score - 50)
    breadth = buyers if flow == "BUY" else sellers
    s = f"{score:.0f}"

    if flow == "BUY":
        if not agree:
            conf, analysis = "Low", (
                f"BUY SIGNAL — Low Confidence: contradicted by a negative "
                f"Insider Power Score ({s}).")
        else:
            conf = "High" if (strength >= 15 or breadth >= 3) else "Medium"
            analysis = (f"BUY SIGNAL — {conf} Confidence: confirmed by a positive "
                        f"Insider Power Score ({s}); {buyers} insider buyer"
                        f"{'' if buyers == 1 else 's'} vs {sellers} seller"
                        f"{'' if sellers == 1 else 's'}.")
        return {"score": score, "signal": "BUY", "confidence": conf,
                "routine_only": False, "posture_reason": analysis,
                "analysis": analysis, "informative_sell": False}

    # flow == SELL with buys also present — sell only reads bearish when the
    # informative bar clears; otherwise it is a low-confidence / neutral read.
    if not agree:
        analysis = (f"SELL SIGNAL — Low Confidence: contradicted by a positive "
                    f"Insider Power Score ({s}).")
        return {"score": score, "signal": "SELL", "confidence": "Low",
                "routine_only": False, "posture_reason": analysis,
                "analysis": analysis, "informative_sell": False}
    if informative:
        high = feats["cluster"] and (feats["baseline_z"] or feats["into_weakness"])
        conf = "High" if high else "Medium"
        analysis = (f"SELL SIGNAL — {conf} Confidence: confirmed by a negative "
                    f"Insider Power Score ({s}); {sellers} insider seller"
                    f"{'' if sellers == 1 else 's'} vs {buyers} buyer"
                    f"{'' if buyers == 1 else 's'}.")
        return {"score": score, "signal": "SELL", "confidence": conf,
                "routine_only": False, "posture_reason": analysis,
                "analysis": analysis, "informative_sell": True}
    # net-dollar sell but no informative bar → de-escalate to weak/neutral.
    analysis = ("Net selling, but spread-out and baseline-sized — no informative "
                "sell signal.")
    return {"score": max(score, NEUTRAL_FLOOR) if score < NEUTRAL_FLOOR else score,
            "signal": "NEUTRAL", "confidence": "Low", "routine_only": False,
            "posture_reason": analysis, "analysis": analysis,
            "informative_sell": False}


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

    # Split the gross weight into buy / sell legs — a buy-less tape (gross_buy≈0)
    # takes the neutral-by-default posture (see _score_and_posture).
    gross_buy = float(buys["contrib"].abs().sum())
    base_score = score_from_balance(float(win["contrib"].sum()),
                                    float(win["contrib"].abs().sum()))
    buyers = int(buys["rptownercik"].nunique())
    sellers = int(sells["rptownercik"].nunique())
    buy_usd = float(buys["usd"].fillna(0.0).sum())
    sell_usd = float(sells["usd"].fillna(0.0).sum())
    buy_shares = float(buys["shares"].fillna(0.0).sum())
    sell_shares = float(sells["shares"].fillna(0.0).sum())
    net_usd = buy_usd - sell_usd

    # Recency gate: age (days) of the most recent open-market trade in the
    # SCORE window (None when the window is empty). `_stale` mirrors the gate
    # _score_and_posture applies (STALE_DAYS) so insider_buy/sell can be held
    # back on a decayed tape.
    if not win.empty:
        last_trade_age_d = int((asof - win["filing_date"].max()).days)
    else:
        last_trade_age_d = None
    _stale = (last_trade_age_d is not None and last_trade_age_d > STALE_DAYS)

    feats = _informative_sell_features(win, g, asof)
    posture = _score_and_posture(base_score, gross_buy, feats, last_trade_age_d,
                                 buyers, sellers, net_usd)
    score = posture["score"]
    signal = posture["signal"]
    confidence = posture["confidence"]
    analysis = posture["analysis"]
    routine_only = posture["routine_only"]
    posture_reason = posture["posture_reason"]
    informative_sell = posture["informative_sell"]

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
        # v2 additive display fields — let consumers render an explicit
        # "no signal — routine selling only" state instead of a red gauge.
        "routine_only": bool(routine_only),
        "posture_reason": posture_reason,
        "last_trade_age_d": last_trade_age_d,
        # insider_buy fires at/above the buy threshold BUT is recency-gated the
        # same way the signal is (STALE_DAYS): a >90d-old buy cluster emits
        # signal=NEUTRAL/confidence=None, so flagging insider_buy=True on it would
        # be an internally contradictory payload. Gating it here (a de-escalation
        # that only suppresses a stale buy flag) mirrors insider_sell's structure.
        # insider_sell requires the INFORMATIVE-sell bar (not merely score ≤
        # threshold), so a routine sell-only tape never manufactures an escalation.
        "insider_buy": bool(score >= BUY_THRESHOLD and not _stale),
        "insider_sell": bool(informative_sell and score <= SELL_THRESHOLD),
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
