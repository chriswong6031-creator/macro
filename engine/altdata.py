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
def offexchange_flow(top: int = 15) -> list[dict]:
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
def inst_13f_changes(top: int = 15) -> dict:
    df = _read("sec13f_changes")
    if df is None or df.empty:
        return {"adds": [], "trims": []}
    d = pd.DataFrame({
        "ticker": df.get("Ticker", pd.Series(dtype=object)).map(_s),
        "fund": df.get("Fund", pd.Series(dtype=object)).map(_s),
        "period": df.get("ReportPeriod", pd.Series(dtype=object)).map(lambda v: (_s(v) or "")[:10]),
        "chg_usd": df.get("Change", pd.Series(dtype=object)).map(_f),
        "chg_shares": df.get("Change_Share", pd.Series(dtype=object)).map(_f),
    })
    d = d[d["ticker"].notna() & d["chg_usd"].notna()]
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
def trump_trades(n: int = 60) -> list[dict]:
    df = _read("trump")
    if df is None or df.empty:
        return []
    d = df.copy()
    d = d.assign(_d=_dt(d.get("Filed"))).sort_values("_d", ascending=False, na_position="last")
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
def convergence(signals: dict, top: int = 25) -> list[dict]:
    """Tickers lit up by several independent channels at once — the connection /
    unusual-activity layer. Each channel votes once; score = distinct channels."""
    channels: dict[str, dict] = {}

    def add(ticker, channel, detail):
        tk = _s(ticker)
        if not tk:
            return
        channels.setdefault(tk, {"ticker": tk, "channels": {}, "score": 0})
        if channel not in channels[tk]["channels"]:
            channels[tk]["channels"][channel] = detail
            channels[tk]["score"] += 1

    for r in signals.get("political", {}).get("buys", []):
        add(r["ticker"], "congress_buy", f"{r['members']} members net +{r['net']}")
    for r in signals.get("gov_contracts", []):
        add(r["ticker"], "gov_contract", f"${r['total_usd']:,.0f} awarded")
    for r in signals.get("lobbying", []):
        add(r["ticker"], "lobbying", f"${r['spend_usd']:,.0f} lobbied")
    for r in signals.get("insiders", {}).get("buys", []):
        add(r["ticker"], "insider_buy", f"${r['net_usd']:,.0f} net insider buy")
    for r in signals.get("offexchange", []):
        if r.get("lean") == "accumulation":
            add(r["ticker"], "darkpool_accum", f"DPI {r['dpi']}")
    for r in signals.get("cnbc", []):
        if (r.get("Direction") or "").lower() in ("buy", "final trade"):
            add(r.get("Ticker"), "cnbc_pick", r.get("Traders"))
    for r in signals.get("inst_13f", {}).get("adds", [])[:10]:
        add(r["ticker"], "13f_add", f"{r['fund']} +${r['chg_usd']:,.0f}")
    for r in signals.get("trump", []):
        if r.get("side") == "buy":
            add(r["ticker"], "trump_buy", r.get("company"))

    rows = [c for c in channels.values() if c["score"] >= 2]
    for c in rows:
        c["channel_list"] = list(c["channels"].keys())
        c["why"] = " · ".join(f"{k}: {v}" for k, v in c["channels"].items() if v)
        del c["channels"]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:top]


# --------------------------------------------------------------------------- feed
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
    signals["lobbying"] = safe(lobbying_spikes, [])
    signals["offexchange"] = safe(offexchange_flow, [])
    signals["insiders"] = safe(insider_netflow, {"buys": [], "sells": []})
    signals["inst_13f"] = safe(inst_13f_changes, {"adds": [], "trims": []})
    signals["trump"] = safe(trump_trades, [])
    signals["corporate_donors"] = safe(corporate_donors, [])
    signals["news"] = safe(news_recent, [])
    signals["wsb"] = safe(wsb_top, [])
    signals["cnbc"] = datasets.get("cnbc", {}).get("recent", [])[:25]
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
