"""Alternative-data engine (Quiver suite).

Reads the append-only event tables written by ``collectors/quiver.py`` and produces:

  * a machine-readable FEED (``data/altdata/feed.json`` + ``site/altdata/feed.json``)
    that the external reasoning brain (the Claude-CLI mastermind app) consumes, and
  * lightweight DETERMINISTIC signals (display-only) for the Alternative Data page:
    political net-flow (Congress/Senate/House), government-contract leaders,
    lobbying spikes, off-exchange dark-pool flow, insider net-buying, CNBC picks,
    institutional 13F changes, Donald-Trump trades, WSB attention, and a cross-signal
    CONVERGENCE roll-up — tickers lit up by several independent political / insider /
    contract channels at once (the "connection" + "unusual activity" layer).

Design rules (match the repo):
  * Pure reads + pandas. No network, no LLM. Deterministic.
  * Every section is wrapped so a missing/malformed table degrades to empty — the
    builder never crashes.
  * DISPLAY / CONTEXT ONLY. Nothing here writes into a scored axis, allocation, or
    regime. The score/narrative/model wiring is a deliberate next phase that must go
    through the falsifiable gate, not a naive signal dump.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import pandas as pd

from lib import config
from engine import altdata_models as models

log = logging.getLogger(__name__)

# dataset -> (emoji, en, zh, the column to treat as the event date)
DATASETS: dict[str, tuple[str, str, str, str]] = {
    "trump":          ("🟥", "Donald Trump trades", "特朗普交易", "Filed"),
    "congress":       ("🏛️", "Congress trading", "国会交易", "ReportDate"),
    "senate":         ("🏛️", "Senate trading", "参议院交易", "Date"),
    "house":          ("🏛️", "House trading", "众议院交易", "Date"),
    "govcontracts":   ("📜", "Government contracts", "政府合同", "Date"),
    "lobbying":       ("💼", "Corporate lobbying", "企业游说", "Date"),
    "offexchange":    ("🌑", "Off-exchange / dark pool", "场外/暗池", "Date"),
    "insiders":       ("👔", "Insider trading", "内部人交易", "fileDate"),
    "sec13f":         ("🏦", "Institutional 13F", "机构13F", "Date"),
    "sec13f_changes": ("🏦", "13F position changes", "13F持仓变化", "Date"),
    "cnbc":           ("📺", "CNBC stock picks", "CNBC选股", "Upload_Time"),
    "wallstreetbets": ("🦍", "WallStreetBets", "WSB热度", "_collected"),
    "twitter":        ("🐦", "Twitter following", "推特关注", "Date"),
    "spacs":          ("🛰️", "SPAC sentiment", "SPAC情绪", "Time"),
    "patents":        ("🔬", "US patents", "美国专利", "Date"),
    "flights":        ("✈️", "Corporate flights", "企业航班", "Date"),
    "corpdonors":     ("💸", "Corporate donors", "企业捐赠", "Uploaded"),
    "news":           ("📰", "Quiver news feed", "Quiver新闻", "time"),
    "congressholdings": ("📁", "Congress holdings", "国会持仓", "_collected"),
    "bills":          ("📑", "Bill summaries", "法案摘要", "_first_seen"),
    "appratings":     ("📱", "App ratings", "应用评分", "Time"),
    "topshareholders": ("🏛️", "Top shareholders", "主要股东", "_collected"),
    "execcomp":       ("💰", "Executive comp", "高管薪酬", "_collected"),
}

_MISSING = {"", "nan", "none", "nat", "null", "<na>"}


# --------------------------------------------------------------------------- coercion
def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _MISSING else s


def _f(v) -> float:
    s = _s(v)
    if s is None:
        return float("nan")
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _usd(v) -> float:
    """Parse a dollar amount or a range like '$1,001 - $15,000' -> midpoint."""
    s = _s(v)
    if s is None:
        return float("nan")
    nums = re.findall(r"[\d][\d,]*\.?\d*", s.replace("$", ""))
    vals = [float(n.replace(",", "")) for n in nums if n.replace(",", "").replace(".", "").isdigit()]
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def _dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))


def _read(dataset: str) -> pd.DataFrame | None:
    p = config.data_dir() / "quiver" / f"{dataset}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read %s: %s", dataset, e)
        return None


def _side(txn: str | None) -> str | None:
    if not txn:
        return None
    t = txn.lower()
    if "purchase" in t or "buy" in t:
        return "buy"
    if "sale" in t or "sell" in t:
        return "sell"
    return None


def _records(df: pd.DataFrame, date_col: str | None, n: int = 25) -> list[dict]:
    """Most-recent-first, json-safe rows, long strings truncated."""
    if df is None or df.empty:
        return []
    d = df.copy()
    if date_col and date_col in d.columns:
        d = d.assign(_d=_dt(d[date_col])).sort_values("_d", ascending=False, na_position="last").drop(columns="_d")
    d = d.head(n)
    out = []
    for _, row in d.iterrows():
        rec = {}
        for k, v in row.items():
            sv = _s(v)
            if sv is not None and len(sv) > 220:
                sv = sv[:217] + "…"
            rec[k] = sv
        out.append(rec)
    return out


# --------------------------------------------------------------------------- political
def _political_frame() -> pd.DataFrame:
    frames = []
    for ds, datecol, whocol in (("congress", "TransactionDate", "Representative"),
                                ("senate", "Date", "Senator"),
                                ("house", "Date", "Representative")):
        df = _read(ds)
        if df is None or df.empty:
            continue
        d = pd.DataFrame()
        d["ticker"] = df.get("Ticker", pd.Series(dtype=object)).map(_s)
        d["date"] = _dt(df[datecol]) if datecol in df else pd.NaT
        d["side"] = df.get("Transaction", pd.Series(dtype=object)).map(_s).map(_side)
        d["member"] = df.get(whocol, pd.Series(dtype=object)).map(_s)
        d["bioguide"] = df.get("BioGuideID", pd.Series(dtype=object)).map(_s)
        d["party"] = df.get("Party", pd.Series(dtype=object)).map(_s)
        d["usd"] = df.get("Range", df.get("Amount", pd.Series(dtype=object))).map(_usd)
        d["chamber"] = ds
        frames.append(d)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def political_netflow(window_days: int = 90, top: int = 15) -> dict:
    df = _political_frame()
    if df.empty:
        return {"buys": [], "sells": []}
    cutoff = _now() - pd.Timedelta(days=window_days)
    df = df[(df["date"] >= cutoff) & df["ticker"].notna() & df["side"].notna()]
    if df.empty:
        return {"buys": [], "sells": []}
    rows = []
    for tk, g in df.groupby("ticker"):
        buys = int((g["side"] == "buy").sum())
        sells = int((g["side"] == "sell").sum())
        rows.append({
            "ticker": tk,
            "net": buys - sells,
            "buys": buys,
            "sells": sells,
            "members": int(g["bioguide"].nunique()),
            "est_usd": round(float(g.loc[g["side"] == "buy", "usd"].sum(skipna=True)), 0),
            "parties": "/".join(sorted({p for p in g["party"].dropna().unique()})) or None,
        })
    rows.sort(key=lambda r: (r["net"], r["members"]), reverse=True)
    buys = [r for r in rows if r["net"] > 0][:top]
    sells = sorted([r for r in rows if r["net"] < 0], key=lambda r: r["net"])[:top]
    return {"buys": buys, "sells": sells}


# --------------------------------------------------------------------------- gov contracts
def gov_contract_leaders(window_days: int = 30, top: int = 15) -> list[dict]:
    df = _read("govcontracts")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "usd": df.get("Amount", pd.Series(dtype=object)).map(_f),
        "agency": df.get("Agency", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & d["date"].notna()]
    if d.empty:
        return []
    now = _now()
    cur = d[d["date"] >= now - pd.Timedelta(days=window_days)]
    prior = d[(d["date"] < now - pd.Timedelta(days=window_days)) & (d["date"] >= now - pd.Timedelta(days=2 * window_days))]
    pri_sum = prior.groupby("ticker")["usd"].sum()
    rows = []
    for tk, g in cur.groupby("ticker"):
        tot = float(g["usd"].sum(skipna=True))
        p = float(pri_sum.get(tk, 0.0))
        rows.append({
            "ticker": tk,
            "total_usd": round(tot, 0),
            "contracts": int(len(g)),
            "agencies": int(g["agency"].nunique()),
            "accel_x": round(tot / p, 2) if p > 0 else None,
            "top_agency": g.groupby("agency")["usd"].sum().idxmax() if g["agency"].notna().any() else None,
        })
    rows.sort(key=lambda r: r["total_usd"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- gov grants/loans
def gov_grant_leaders(recent_m: int = 6, top: int = 20) -> list[dict]:
    """Per-ticker federal GRANT/LOAN money (USAspending assistance awards) — the CHIPS/DOE/IRA
    flow the contracts feed and Quiver are both blind to. Reads the monthly
    [month x ticker] grants_loans store frame; emits recent-window $ + recent-vs-prior accel.
    Grant obligations are lumpy/monthly, so the window is wider than the daily-contract one."""
    try:
        from lib import store
        wide = store.read("usaspending", "grants_loans")
    except Exception:  # noqa: BLE001
        return []
    if wide is None or wide.empty:
        return []
    monthly = wide.sort_index()
    lag = 2  # most-recent grant months are still posting
    if lag and len(monthly) > lag:
        monthly = monthly.iloc[:-lag]
    if monthly.empty:
        return []
    recent = monthly.iloc[-recent_m:].sum(min_count=1)
    prior = monthly.iloc[-2 * recent_m:-recent_m].sum(min_count=1) if len(monthly) >= 2 * recent_m else None
    rows = []
    for tk in monthly.columns:
        v = recent.get(tk)
        tot = float(v) if pd.notna(v) else 0.0
        if tot <= 0:
            continue
        p = float(prior.get(tk)) if (prior is not None and pd.notna(prior.get(tk))) else 0.0
        rows.append({
            "ticker": tk,
            "total_usd": round(tot, 0),
            "accel_x": round(tot / p, 2) if p > 0 else None,
        })
    rows.sort(key=lambda r: r["total_usd"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- finnhub trio
def _finnhub(dataset: str) -> pd.DataFrame | None:
    p = config.data_dir() / "finnhub" / f"{dataset}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read finnhub/%s: %s", dataset, e)
        return None


def analyst_trends(top: int = 25) -> list[dict]:
    """Analyst recommendation tilt (Finnhub): per-ticker bull ratio + revision-delta.

    Fix #43a: `hot` (the convergence-channel trigger) is now based on the validated
    REVISION-DELTA construction from engine.analyst_revisions, NOT the consensus level.
    analyst_revisions.py:4-7 states the consensus level "is near-useless and
    optimism-skewed … we score the DELTA, never the level." A ticker fires hot when
    direction=='upgrading' (net-buy count rose vs prior snapshot) — the signal the
    literature (Womack 1996; Barber-Lehavy-McNichols-Trueman 2001) validates.

    The `bull_ratio` level is still carried as display context (never the trigger)
    so callers that render it as a label continue working unchanged.
    """
    from engine import analyst_revisions  # local import to keep module boundary clean
    df = _finnhub("recommendation")
    if df is None or df.empty:
        return []
    # Build the revision-delta map: {ticker -> {direction, revision_delta, ...}}
    rev_map = analyst_revisions.revision_map(df)
    rows = []
    for _, r in df.iterrows():
        tk = _s(r.get("ticker"))
        sb, b, h, s, ss = (_f(r.get(k)) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
        tot = sum(x for x in (sb, b, h, s, ss) if pd.notna(x))
        if not tk or tot <= 0:
            continue
        bull = (((sb if pd.notna(sb) else 0) + (b if pd.notna(b) else 0)) / tot)
        # Use the validated revision-DELTA as the hot trigger (level is display-only context)
        rev = rev_map.get(tk) or {}
        upgrading = rev.get("direction") == "upgrading"
        rows.append({"ticker": tk, "bull_ratio": round(bull, 2),
                     "rising": upgrading,            # kept for backward-compat display label
                     "revision_delta": rev.get("revision_delta"),
                     "hot": upgrading})              # DELTA-based, not level-based
    rows.sort(key=lambda r: r["bull_ratio"], reverse=True)
    return rows[:top]


def insider_mspr(top: int = 25) -> list[dict]:
    """Finnhub insider sentiment (MSPR, monthly net-buy score -100..100). `hot` when the latest
    MSPR is strongly positive — a pre-aggregated cross-check on the open-market insider feeds."""
    df = _finnhub("insider_sentiment")
    if df is None or df.empty:
        return []
    df = df.assign(_ym=df.get("year").astype("float") * 100 + df.get("month").astype("float"))
    rows = []
    for tk, g in df.groupby("ticker"):
        tk = _s(tk)
        if not tk:
            continue
        latest = g.sort_values("_ym").iloc[-1]
        mspr = _f(latest.get("mspr"))
        if pd.isna(mspr):
            continue
        rows.append({"ticker": tk, "mspr": round(float(mspr), 1), "hot": mspr >= 20})
    rows.sort(key=lambda r: r["mspr"], reverse=True)
    return rows[:top]


def earnings_beats(top: int = 25) -> list[dict]:
    """Finnhub earnings surprises. `hot` when the most recent quarter beat estimates clearly."""
    df = _finnhub("earnings")
    if df is None or df.empty:
        return []
    df = df.assign(_d=_dt(df.get("period")))
    rows = []
    for tk, g in df.groupby("ticker"):
        tk = _s(tk)
        if not tk:
            continue
        latest = g.sort_values("_d").iloc[-1]
        sp = _f(latest.get("surprisePercent"))
        if pd.isna(sp):
            continue
        rows.append({"ticker": tk, "surprise_pct": round(float(sp), 1), "hot": sp >= 5.0})
    rows.sort(key=lambda r: r["surprise_pct"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- unusual options
def unusual_options(min_oi: float = 5000.0, mult_hot: float = 3.0, top: int = 20) -> list[dict]:
    """Per-underlying UNUSUAL options activity from the ALREADY-STORED Polygon per-strike chains
    (data/polygon_gex/chains/*.parquet — no new API calls). For each name: today's total
    volume/open-interest ratio vs its own recent baseline. A vol/OI ratio spiking >= `mult_hot`x
    the baseline = an options-flow surge (institutional positioning) the tape may not price yet;
    the put/call volume split gives the lean. Display/context only."""
    import glob
    d = config.data_dir() / "polygon_gex" / "chains"
    files = sorted(glob.glob(str(d / "*.parquet")))[-12:]
    if len(files) < 2:
        return []
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(f, columns=["underlying", "oi", "volume", "is_call", "asof"]))
        except Exception:  # noqa: BLE001
            continue
    if len(frames) < 2:
        return []
    df = pd.concat(frames, ignore_index=True)
    df["asof"] = _dt(df.get("asof"))
    df = df[df["underlying"].map(_s).notna() & df["asof"].notna()]
    if df.empty:
        return []
    rows = []
    for tk, g in df.groupby("underlying"):
        by_day = g.groupby("asof").agg(vol=("volume", "sum"), oi=("oi", "sum"))
        by_day = by_day[by_day["oi"] > 0].sort_index()
        if len(by_day) < 2:
            continue
        ratio = (by_day["vol"] / by_day["oi"])
        latest_day = by_day.index.max()
        cur = float(ratio.iloc[-1])
        base = float(ratio.iloc[:-1].median())
        if base <= 1e-9 or float(by_day["oi"].iloc[-1]) < min_oi:
            continue
        mult = cur / base
        today = g[g["asof"] == latest_day]
        call_v = float(today.loc[today["is_call"] == True, "volume"].sum())  # noqa: E712
        put_v = float(today.loc[today["is_call"] == False, "volume"].sum())  # noqa: E712
        pc = round(put_v / call_v, 2) if call_v > 0 else None
        rows.append({
            "ticker": _s(tk), "vol_oi": round(cur, 3), "mult": round(mult, 2),
            "put_call": pc, "lean": ("put-skew" if pc and pc > 1.3 else "call-skew" if pc and pc < 0.7 else "balanced"),
            "hot": mult >= mult_hot,
        })
    rows.sort(key=lambda r: r["mult"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- clinical trials
def clinical_events(start_days: int = 120, halt_days: int = 120, top: int = 25) -> list[dict]:
    """Per-ticker clinical pipeline events (collectors/clinicaltrials.py ->
    data/clinicaltrials/trials.parquet): a new Phase-3 START (first_post in window, positive
    pipeline channel) and/or a recent HALT (TERMINATED/SUSPENDED/WITHDRAWN — a risk flag carried
    as a caption, NOT a bullish channel)."""
    p = config.data_dir() / "clinicaltrials" / "trials.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read clinicaltrials: %s", e)
        return []
    if df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("ticker", pd.Series(dtype=object)).map(_s),
        "first_post": _dt(df.get("first_post")),
        "last_update": _dt(df.get("last_update")),
        "is_halt": df.get("is_halt", pd.Series(dtype=bool)).fillna(False).astype(bool),
        "title": df.get("title", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna()]
    if d.empty:
        return []
    now = _now()
    out = []
    for tk, g in d.groupby("ticker"):
        starts = g[(g["first_post"].notna()) & (g["first_post"] >= now - pd.Timedelta(days=start_days))]
        halts = g[(g["is_halt"]) & (g["last_update"].notna()) & (g["last_update"] >= now - pd.Timedelta(days=halt_days))]
        if starts.empty and halts.empty:
            continue
        rec = {"ticker": tk, "phase3_starts": int(len(starts)), "halts": int(len(halts)),
               "hot": len(starts) >= 1}
        if len(starts):
            rec["sample"] = starts.sort_values("first_post", ascending=False).iloc[0]["title"]
        out.append(rec)
    out.sort(key=lambda r: (r["phase3_starts"], -r["halts"]), reverse=True)
    return out[:top]


# --------------------------------------------------------------------------- news sentiment
def news_sentiment_signals(top: int = 25) -> list[dict]:
    """Per-ticker editorial-news lean (Polygon news insights -> data/polygon/news_sentiment.parquet).
    `hot` when the latest snapshot's bullish ratio is high over a real article base. Low-weight
    context — abundant but noisy."""
    p = config.data_dir() / "polygon" / "news_sentiment.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read polygon news_sentiment: %s", e)
        return []
    if df.empty:
        return []
    df = df.assign(_d=_dt(df.get("snapshot_date")))
    rows = []
    for tk, g in df.groupby("ticker"):
        tk = _s(tk)
        if not tk:
            continue
        latest = g.sort_values("_d").iloc[-1]
        arts = _f(latest.get("articles"))
        br = _f(latest.get("bull_ratio"))
        if pd.isna(arts) or arts < 5 or pd.isna(br):
            continue
        rows.append({"ticker": tk, "bull_ratio": round(float(br), 2), "articles": int(arts),
                     "hot": br >= 0.6})
    rows.sort(key=lambda r: r["bull_ratio"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- hugging face
def hf_momentum(top: int = 15) -> list[dict]:
    """Per-ticker Hugging Face model-download VELOCITY (collectors/huggingface.py ->
    data/huggingface/downloads.parquet snapshots). The level is not a signal; the WoW change in
    the trailing-30d download rate is. `hot` = rising AND at/above the cross-section's median
    rise — relative AI-model adoption momentum. Needs >=2 snapshots (else degrades to empty)."""
    p = config.data_dir() / "huggingface" / "downloads.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read huggingface downloads: %s", e)
        return []
    if df.empty:
        return []
    df = df.assign(d=_dt(df.get("snapshot_date")))
    df = df[df["d"].notna()]
    rows = []
    for tk, g in df.groupby("ticker"):
        g = g.sort_values("d")
        if g["d"].nunique() < 2:
            continue
        latest = g.iloc[-1]
        cutoff = latest["d"] - pd.Timedelta(days=7)
        earlier = g[g["d"] <= cutoff]
        prior = earlier.iloc[-1] if len(earlier) else g.iloc[-2]
        cur, pre = float(latest["downloads_30d"]), float(prior["downloads_30d"])
        if pre <= 0:
            continue
        rows.append({"ticker": _s(tk), "downloads_30d": round(cur, 0),
                     "wow_pct": round((cur - pre) / pre * 100, 1)})
    risers = [r["wow_pct"] for r in rows if r["wow_pct"] > 0]
    if risers:
        med = float(pd.Series(risers).median())
        for r in rows:
            r["hot"] = r["wow_pct"] > 0 and r["wow_pct"] >= med
    rows.sort(key=lambda r: r["wow_pct"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- github momentum
def github_momentum(top: int = 20) -> list[dict]:
    """Per-ticker GitHub star VELOCITY (collectors/github_repos.py -> data/github/repo_stars.parquet
    snapshots). `hot` = rising AND at/above the cross-section's median rise — developer-mindshare
    momentum. Needs >=2 snapshots (else empty). Low-weight context."""
    p = config.data_dir() / "github" / "repo_stars.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read github repo_stars: %s", e)
        return []
    if df.empty:
        return []
    df = df.assign(d=_dt(df.get("snapshot_date")))
    df = df[df["d"].notna()]
    rows = []
    for tk, g in df.groupby("ticker"):
        g = g.sort_values("d")
        if g["d"].nunique() < 2:
            continue
        latest = g.iloc[-1]
        cutoff = latest["d"] - pd.Timedelta(days=7)
        earlier = g[g["d"] <= cutoff]
        prior = earlier.iloc[-1] if len(earlier) else g.iloc[-2]
        cur, pre = float(latest["stars"]), float(prior["stars"])
        if pre <= 0:
            continue
        rows.append({"ticker": _s(tk), "stars": int(cur),
                     "wow_pct": round((cur - pre) / pre * 100, 2)})
    risers = [r["wow_pct"] for r in rows if r["wow_pct"] > 0]
    if risers:
        med = float(pd.Series(risers).median())
        for r in rows:
            r["hot"] = r["wow_pct"] > 0 and r["wow_pct"] >= med
    rows.sort(key=lambda r: r["wow_pct"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- openFDA
def fda_events(approval_days: int = 45, label_days: int = 120, top: int = 25) -> list[dict]:
    """Per-ticker FDA catalysts (collectors/openfda.py -> data/openfda/approvals.parquet):
    a NEW approval (ORIG/AP) in the last `approval_days`, or a LABEL expansion (SUPPL/EFFICACY/AP)
    in the last `label_days`. The healthcare catalyst layer the political/contract feeds miss."""
    p = config.data_dir() / "openfda" / "approvals.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read openfda approvals: %s", e)
        return []
    if df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("ticker", pd.Series(dtype=object)).map(_s),
        "kind": df.get("kind", pd.Series(dtype=object)).map(_s),
        "date": pd.to_datetime(df.get("status_date"), format="%Y%m%d", errors="coerce"),
        "drug": df.get("drug_name", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & d["kind"].notna() & d["date"].notna()]
    if d.empty:
        return []
    now = _now()
    out, seen = [], set()
    # newest first so the most recent catalyst per (ticker,kind) wins
    for _, r in d.sort_values("date", ascending=False).iterrows():
        win = approval_days if r["kind"] == "approval" else label_days
        if r["date"] < now - pd.Timedelta(days=win):
            continue
        key = (r["ticker"], r["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"ticker": r["ticker"], "kind": r["kind"], "drug": r["drug"],
                    "date": r["date"].date().isoformat()})
        if len(out) >= top:
            break
    return out


# --------------------------------------------------------------------------- material 8-K
# The LHB-R7 expansion widened collection to 12 item codes for long-hold consumers, but
# this channel feeds material_8k convergence (altdata_models) and intel_discovery's
# _LEADING_CHANNELS scoring — its firing bar must not shift from a data-lane change, so
# it stays pinned to the original six. Must equal collectors/edgar_8k.LEGACY_VELOCITY_ITEMS
# (sync-guarded in tests/test_edgar_8k_items.py). Widening this set = a deliberate
# signal-change PR with its own review, never a side effect.
_LEGACY_8K_ITEMS = frozenset({"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"})


def material_events(window_days: int = 30, top: int = 25) -> list[dict]:
    """Per-ticker count of MATERIAL 8-K filings in the last `window_days` (collectors/edgar_8k.py
    -> data/edgar/material_8k_events.parquet). A cluster (>=2) = a burst of filing-time
    corporate activity (material agreements / acquisitions / financings / leadership) the tape
    may not have fully digested. Counts are pinned to _LEGACY_8K_ITEMS — see above."""
    p = config.data_dir() / "edgar" / "material_8k_events.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("altdata: cannot read material_8k_events: %s", e)
        return []
    if df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("filing_date")),
        "items": df.get("items", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & d["date"].notna()]
    if d.empty:
        return []
    d = d[d["date"] >= _now() - pd.Timedelta(days=window_days)]
    if d.empty:
        return []
    # Row-level legacy pin: an 8-K whose items are all expansion-only codes does not count.
    legacy_mask = d["items"].map(
        lambda blob: bool(set(str(blob or "").split(",")) & _LEGACY_8K_ITEMS)
    )
    d = d[legacy_mask]
    if d.empty:
        return []
    rows = []
    for tk, g in d.groupby("ticker"):
        items = sorted(
            {c for blob in g["items"].dropna() for c in str(blob).split(",") if c}
            & _LEGACY_8K_ITEMS
        )
        rows.append({"ticker": tk, "count": int(len(g)), "items": ", ".join(items[:6])})
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- lobbying
def lobbying_spikes(window_days: int = 45, top: int = 15) -> list[dict]:
    df = _read("lobbying")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "usd": df.get("Amount", pd.Series(dtype=object)).map(_f),
        "issue": df.get("Issue", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & d["date"].notna()]
    if d.empty:
        return []
    now = _now()
    cur = d[d["date"] >= now - pd.Timedelta(days=window_days)]
    prior = d[(d["date"] < now - pd.Timedelta(days=window_days)) & (d["date"] >= now - pd.Timedelta(days=2 * window_days))]
    pri = prior.groupby("ticker")["usd"].sum()
    rows = []
    for tk, g in cur.groupby("ticker"):
        tot = float(g["usd"].sum(skipna=True))
        p = float(pri.get(tk, 0.0))
        rows.append({
            "ticker": tk,
            "spend_usd": round(tot, 0),
            "filings": int(len(g)),
            "spike_x": round(tot / p, 2) if p > 0 else None,
            "top_issue": (g["issue"].dropna().iloc[0].split("\n")[0].strip() if g["issue"].notna().any() else None),
        })
    # surface genuine spikes first (new or accelerating spenders), then raw size
    rows.sort(key=lambda r: (r["spike_x"] is None, r["spike_x"] or 0, r["spend_usd"]), reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- off-exchange
def _business_days_since(dt: pd.Timestamp) -> int:
    """Calendar days minus weekends between dt and now (approximate business days)."""
    now = _now()
    if pd.isna(dt) or dt > now:
        return 0
    return int(pd.bdate_range(dt, now).size)


def offexchange_flow(top: int = 15, stale_bdays: int = 10) -> list[dict]:
    """Off-exchange / dark-pool flow. Adds a `stale` flag when the latest date is
    more than `stale_bdays` business days old. FINRA publication lag is ~10 business
    days, so the flag fires only beyond that expected lag to avoid false positives."""
    df = _read("offexchange")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("Date")),
        "short": df.get("OTC_Short", pd.Series(dtype=object)).map(_f),
        "total": df.get("OTC_Total", pd.Series(dtype=object)).map(_f),
        "dpi": df.get("DPI", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna() & d["date"].notna() & (d["total"] > 0)]
    if d.empty:
        return []
    latest = d["date"].max()
    d = d[d["date"] == latest]
    # Freshness guard: flag when latest date exceeds FINRA publication lag.
    # `stale` is produced here as a data-first field; the display layer does not yet
    # consume it — wiring is deferred to Wave-2 (template work out of scope for this PR).
    stale = bool(pd.notna(latest) and _business_days_since(latest) > stale_bdays)
    rows = []
    for _, r in d.iterrows():
        rows.append({
            "ticker": r["ticker"],
            "date": latest.date().isoformat(),
            "otc_total": round(float(r["total"]), 0),
            "dpi": round(float(r["dpi"]), 3) if pd.notna(r["dpi"]) else None,
            # low DPI (off-exchange short ratio) + high volume reads as net accumulation
            "lean": ("accumulation" if pd.notna(r["dpi"]) and r["dpi"] < 0.40
                     else "distribution" if pd.notna(r["dpi"]) and r["dpi"] > 0.60 else "balanced"),
            "stale": stale,
        })
    rows.sort(key=lambda r: r["otc_total"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- insiders
def insider_netflow(window_days: int = 90, top: int = 15) -> dict:
    df = _read("insiders")
    if df is None or df.empty:
        return {"buys": [], "sells": []}
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "date": _dt(df.get("fileDate", df.get("Date"))),
        "code": df.get("TransactionCode", pd.Series(dtype=object)).map(_s),
        "ad": df.get("AcquiredDisposedCode", pd.Series(dtype=object)).map(_s),
        "shares": df.get("Shares", pd.Series(dtype=object)).map(_f),
        "px": df.get("PricePerShare", pd.Series(dtype=object)).map(_f),
        "ten": df.get("isTenPercentOwner", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna() & d["date"].notna()]
    d = d[d["date"] >= _now() - pd.Timedelta(days=window_days)]
    # open-market purchases (P) / sales (S) only — the informative subset
    d = d[d["code"].isin(["P", "S"])]
    if d.empty:
        return {"buys": [], "sells": []}
    d["value"] = (d["shares"].fillna(0) * d["px"].fillna(0)).abs()
    rows = []
    for tk, g in d.groupby("ticker"):
        b = g[g["code"] == "P"]
        s = g[g["code"] == "S"]
        rows.append({
            "ticker": tk,
            "buy_usd": round(float(b["value"].sum()), 0),
            "sell_usd": round(float(s["value"].sum()), 0),
            "net_usd": round(float(b["value"].sum() - s["value"].sum()), 0),
            "buyers": int(len(b)),
            "sellers": int(len(s)),
        })
    buys = sorted([r for r in rows if r["net_usd"] > 0], key=lambda r: r["net_usd"], reverse=True)[:top]
    sells = sorted([r for r in rows if r["net_usd"] < 0], key=lambda r: r["net_usd"])[:top]
    return {"buys": buys, "sells": sells}


# --------------------------------------------------------------------------- 13F
def inst_13f_changes(top: int = 15, window_days: int = 200) -> dict:
    """13F position changes. `window_days` filters on the filing's ReportPeriod (the
    actual reporting quarter-end date) so multi-year-old positions cannot anchor channels
    indefinitely. 13Fs are quarterly with a 45-day filing deadline, so 200 days always
    covers the two most recent report periods even across a cycle gap. Note: the `Date`
    column in sec13f_changes.parquet is the Quiver ingest timestamp (span ~24 days across
    the full table), NOT the filing period — filtering on `Date` is a no-op vs stale data."""
    df = _read("sec13f_changes")
    if df is None or df.empty:
        return {"adds": [], "trims": []}
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "fund": df.get("Fund", pd.Series(dtype=object)).map(_s),
        "period": df.get("ReportPeriod", pd.Series(dtype=object)).map(lambda v: (_s(v) or "")[:10]),
        "report_period": _dt(df.get("ReportPeriod")),
        "chg_usd": df.get("Change", pd.Series(dtype=object)).map(_f),
        "chg_shares": df.get("Change_Share", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna() & d["chg_usd"].notna()]
    if d.empty:
        return {"adds": [], "trims": []}
    # Filter to positions whose ReportPeriod is within the last `window_days`.
    # ReportPeriod is the filing's quarter-end date (e.g. 2026-03-31), NOT the ingest date.
    cutoff = _now() - pd.Timedelta(days=window_days)
    if d["report_period"].notna().any():
        d = d[d["report_period"].isna() | (d["report_period"] >= cutoff)]
    if d.empty:
        return {"adds": [], "trims": []}

    def _pack(g):
        return [{"ticker": r.ticker, "fund": r.fund, "period": r.period,
                 "chg_usd": round(float(r.chg_usd), 0), "chg_shares": round(float(r.chg_shares), 0) if pd.notna(r.chg_shares) else None}
                for r in g.itertuples()]
    adds = _pack(d.sort_values("chg_usd", ascending=False).head(top))
    trims = _pack(d.sort_values("chg_usd", ascending=True).head(top))
    return {"adds": adds, "trims": trims}


# --------------------------------------------------------------------------- trump
def trump_trades(n: int = 60, window_days: int = 365) -> list[dict]:
    """Donald Trump stock trades. `window_days` filters by Filed date to prevent
    indefinitely-old trades from anchoring the trump channel indefinitely."""
    df = _read("trump")
    if df is None or df.empty:
        return []
    d = df.copy()
    d = d.assign(_d=_dt(d.get("Filed"))).sort_values("_d", ascending=False, na_position="last")
    # Apply time window on Filed date
    cutoff = _now() - pd.Timedelta(days=window_days)
    if d["_d"].notna().any():
        d = d[d["_d"].isna() | (d["_d"] >= cutoff)]
    out = []
    for _, r in d.head(n).iterrows():
        out.append({
            "ticker": _s(r.get("Ticker")),
            "company": _s(r.get("Company")),
            "side": _side(_s(r.get("Transaction"))),
            "transaction": _s(r.get("Transaction")),
            "est_usd": round(_usd(r.get("Amount")), 0) if pd.notna(_usd(r.get("Amount"))) else None,
            "amount": _s(r.get("Amount")),
            "filed": _s(r.get("Filed")),
            "traded": _s(r.get("Traded")),
            "excess_return": _f(r.get("ExcessReturn")) if pd.notna(_f(r.get("ExcessReturn"))) else None,
        })
    return out


# --------------------------------------------------------------------------- wsb
def wsb_top(top: int = 20) -> list[dict]:
    df = _read("wallstreetbets")
    if df is None or df.empty:
        return []
    latest = df.get("_collected")
    if latest is not None and df["_collected"].notna().any():
        df = df[df["_collected"] == df["_collected"].max()]
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "mentions": df.get("Count", pd.Series(dtype=object)).map(_f),
        "sentiment": df.get("Sentiment", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna()].sort_values("mentions", ascending=False).head(top)
    return [{"ticker": r.ticker, "mentions": int(r.mentions) if pd.notna(r.mentions) else None,
             "sentiment": round(float(r.sentiment), 3) if pd.notna(r.sentiment) else None}
            for r in d.itertuples()]


# --------------------------------------------------------------------------- corporate donors
def corporate_donors(top: int = 15) -> list[dict]:
    df = _read("corpdonors")
    if df is None or df.empty:
        return []
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "amount": df.get("TransactionAmount", pd.Series(dtype=object)).map(_f),
        "politician": df.get("CandidateName", pd.Series(dtype=object)).map(_s),
    })
    d = d[d["ticker"].notna()]
    if d.empty:
        return []
    rows = []
    for tk, g in d.groupby("ticker"):
        rows.append({
            "ticker": tk,
            "total_usd": round(float(g["amount"].sum(skipna=True)), 0),
            "donations": int(len(g)),
            "politicians": int(g["politician"].nunique()),
        })
    rows.sort(key=lambda r: r["total_usd"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- news
def news_recent(n: int = 20) -> list[dict]:
    df = _read("news")
    if df is None or df.empty:
        return []
    d = df.assign(_d=_dt(df.get("time"))).sort_values("_d", ascending=False, na_position="last").head(n)
    out = []
    for _, r in d.iterrows():
        out.append({
            "headline": _s(r.get("headline")),
            "ticker": _s(r.get("Ticker")),
            "category": _s(r.get("category")),
            "time": _s(r.get("time")),
            "url": _s(r.get("url")),
        })
    return out


# --------------------------------------------------------------------------- convergence
def convergence(signals: dict, top: int = 25, affiliations: dict | None = None) -> list[dict]:
    """Tickers lit up by several independent channels at once — the connection /
    unusual-activity layer. Delegates to the single WEIGHTED kernel
    (``altdata_models.channel_records``) so the cross-sectional display and the per-ticker
    substrate agree. ``score`` = distinct channels (count); ``weighted_score`` ranks by
    channel QUALITY (an insider cluster outranks a WSB mention). Ranked by weight."""
    recs = models.channel_records(signals, affiliations=affiliations)
    rows = []
    for tk, r in recs.items():
        if r["count"] < 2:
            continue
        detail = r.get("channel_detail", {})
        rows.append({
            "ticker": tk,
            "score": r["count"],
            "weighted_score": r["weighted_score"],
            "channel_list": r["channels"],
            "why": " · ".join(f"{c}: {detail[c]}" for c in r["channels"] if detail.get(c)),
        })
    rows.sort(key=lambda r: (r["weighted_score"], r["score"]), reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- feed
def special_situations_signal() -> list[dict]:
    """P3.3 handshake: read the Special-Situations desk's last per-ticker emit and surface
    high-confidence events so they light an Alt-Data convergence channel on the same name.
    Display-only + slow signal, so last-known is fine; absent/low-confidence -> dropped.
    (Build order: alt-data runs before special-situations, so this consumes yesterday's
    emit — acceptable for a multi-week 13D/deal signal.)"""
    p = config.ROOT / "site" / "allocationdata" / "special_situations.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for tk, r in (data.get("by_ticker") or {}).items():
        if str(r.get("confidence") or "").lower() == "low":
            continue                              # never propagate unverified keyword guesses
        cat = r.get("category")
        out.append({"ticker": tk, "category": cat, "confidence": r.get("confidence"),
                    "activist": cat == "Activist Campaigns",
                    "filer": r.get("activist_filer"), "detail": cat})
    return out


def build_feed() -> dict:
    now = datetime.now(timezone.utc)
    datasets: dict[str, dict] = {}
    for ds, (emoji, en, zh, datecol) in DATASETS.items():
        df = _read(ds)
        if df is None or df.empty:
            datasets[ds] = {"emoji": emoji, "label_en": en, "label_zh": zh,
                            "rows": 0, "last_seen": None, "recent": []}
            continue
        last = _dt(df[datecol]).max() if datecol in df else pd.NaT
        datasets[ds] = {
            "emoji": emoji, "label_en": en, "label_zh": zh,
            "rows": int(len(df)),
            "last_seen": last.date().isoformat() if pd.notna(last) else None,
            "recent": _records(df, datecol, n=25),
        }

    signals: dict = {}
    safe = lambda fn, default: _safe(fn, default)
    signals["political"] = safe(political_netflow, {"buys": [], "sells": []})
    signals["gov_contracts"] = safe(gov_contract_leaders, [])
    signals["gov_grants"] = safe(gov_grant_leaders, [])
    signals["fda"] = safe(fda_events, [])
    signals["hf"] = safe(hf_momentum, [])
    signals["material_8k"] = safe(material_events, [])
    signals["special_situations"] = safe(special_situations_signal, [])   # P3.3 event-desk handshake
    # deferred sources (existing keys / keyless; gated ones degrade to empty)
    signals["unusual_options"] = safe(unusual_options, [])
    signals["analyst"] = safe(analyst_trends, [])
    signals["insider_mspr"] = safe(insider_mspr, [])
    signals["earnings"] = safe(earnings_beats, [])
    signals["news_sentiment"] = safe(news_sentiment_signals, [])
    signals["clinical"] = safe(clinical_events, [])
    signals["github"] = safe(github_momentum, [])
    signals["lobbying"] = safe(lobbying_spikes, [])
    signals["offexchange"] = safe(offexchange_flow, [])
    signals["insiders"] = safe(insider_netflow, {"buys": [], "sells": []})
    signals["inst_13f"] = safe(inst_13f_changes, {"adds": [], "trims": []})
    signals["trump"] = safe(trump_trades, [])
    signals["corporate_donors"] = safe(corporate_donors, [])
    signals["news"] = safe(news_recent, [])
    signals["wsb"] = safe(wsb_top, [])
    signals["cnbc"] = datasets.get("cnbc", {}).get("recent", [])[:25]
    # newly-activated Quiver feeds (were collected-but-unused) — now real signals
    signals["app_ratings"] = safe(models.app_ratings_momentum, [])
    signals["patents"] = safe(models.patent_velocity, [])
    signals["bills"] = safe(models.bill_catalysts, [])
    signals["congress_holdings"] = safe(models.congress_holdings, {})
    signals["flights"] = safe(models.flights_proximity, [])
    signals["exec_comp"] = safe(models.exec_comp, [])
    signals["retail"] = _safe(lambda: models.retail_attention(signals.get("wsb", [])), [])
    signals["convergence"] = _safe(lambda: convergence(signals), [])

    feed = {
        "generated_utc": now.isoformat(),
        "as_of": now.date().isoformat(),
        "schema": "altdata.feed.v1",
        "source": "Quiver Quantitative (Trader plan)",
        "note": ("Deterministic alt-data signals + normalized event feed for the "
                 "reasoning brain. Display/context-only — not a scored axis."),
        "datasets": datasets,
        "signals": signals,
    }
    _write(feed)
    return feed


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        log.warning("altdata signal %s failed: %s", getattr(fn, "__name__", fn), e)
        return default


def _write(feed: dict) -> None:
    for base in (config.data_dir() / "altdata", config.ROOT / "site" / "altdata"):
        base.mkdir(parents=True, exist_ok=True)
        (base / "feed.json").write_text(json.dumps(feed, indent=2, default=str))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    f = build_feed()
    print(f"feed: {len(f['datasets'])} datasets, "
          f"{sum(d['rows'] for d in f['datasets'].values())} rows, "
          f"{len(f['signals']['convergence'])} convergence tickers")
