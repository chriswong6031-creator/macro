"""Build the Congressional / Politician Disclosed Trades desk: render site/congress_trades.html.

Additive + display-only. Reads the Quiver congressional-disclosure history
(``data/quiver/congress.parquet`` — every STOCK-Act filing by a member of the U.S. House or
Senate) and turns it into a COPY-SIGNAL watchlist:

  * MEMBERSHIP — a ticker joins the watchlist the moment a member discloses a trade in it and
    stays ``ROLLOFF_DAYS`` (~half a year) from its MOST-RECENT disclosure before falling off;
    each new disclosure extends the timer.
  * IMPORTANCE — names disclosed by MORE (and bipartisan) members are flagged more important
    (distinct-member count in-window).
  * SCORE — every name is ranked by a composite of three sub-scores:
      1. CLUSTER  — the politician signal: distinct-member breadth, recency-weighted net-buy bias,
                    aggregate disclosed size, freshness, bipartisan bonus.
      2. TECHNICAL — the engine read from this name's own ``site/stockdata/<T>.json`` (conviction
                    band/size + the daily tech block); hard vetoes (cycle-blocked / parabolic /
                    avoid bucket) floor it low.
      3. BUYABLE-ZONE ("act now?") — is the name's SECTOR (regime ``sector_rs``) and THEME
                    (allocation ``ranks``) leading, and is the trend constructive?

DOCTRINE (CLAUDE.md / the desk): the politician cluster GENERATES the idea; the engine + zone
lenses CONFIRM it. A name five members bought that is extended / below its 200d / cycle-blocked
stays HIGH-interest but is NOT ``act_now`` — confirmation over prediction.

Returns 0 on ANY error so it can never break the daily build (mirrors build_alt_data.py).
Display / research only — never trades.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_congress")

# --- strategy knobs (in-code defaults; mirror Mastermind's congress_strategy.yml) -----------
ROLLOFF_DAYS = 182          # a ticker falls off ~half a year after its latest disclosure
HALFLIFE_DAYS = 45          # disclosure weight halves every N days (recency decay)
MIN_DISTINCT_MEMBERS = 2    # >= this many distinct members in-window → "important"
W_CLUSTER, W_TECHNICAL, W_ZONE = 0.40, 0.35, 0.25     # composite weights
MEMBERS_SATURATE_AT = 5
AMOUNT_SATURATE_USD = 500_000.0
ACT_MIN_ZONE, ACT_MIN_TECH = 55.0, 45.0
WATCH_TABLE_CAP = 80        # rows rendered in the watchlist table
FEED_CAP = 50               # rows rendered in the recent-disclosure feed

# sector → the sector-ETF the regime's RS table ranks (ported from Mastermind portfolio/lenses.py)
SECTOR_ETF = {
    "Financials": "XLF", "Financial Services": "XLF", "Technology": "XLK",
    "Information Technology": "XLK", "Industrials": "XLI", "Health Care": "XLV",
    "Healthcare": "XLV", "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP", "Energy": "XLE",
    "Materials": "XLB", "Basic Materials": "XLB", "Real Estate": "XLRE",
    "Utilities": "XLU", "Communication Services": "XLC", "Communications": "XLC",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _decay(report_date, asof) -> float:
    """Recency weight in (0,1]: 1.0 for a disclosure reported today, halving every HALFLIFE_DAYS."""
    if report_date is None:
        return 1.0
    try:
        age = max(0, (asof - report_date).days)
        return 0.5 ** (age / HALFLIFE_DAYS)
    except Exception:  # noqa: BLE001
        return 1.0


def _amount_range(rng, amount):
    """(low, high, mid) USD from Quiver's Range ('$1,001 - $15,000') and/or numeric Amount."""
    import re
    nums = [float(m.replace(",", "")) for m in re.findall(r"\$?\s*([\d,]+(?:\.\d+)?)", str(rng or ""))]
    low = high = None
    if len(nums) >= 2:
        low, high = nums[0], nums[1]
    elif len(nums) == 1:
        low = high = nums[0]
    amt = None
    try:
        if amount not in (None, "", "nan") and str(amount).lower() != "nan":
            amt = float(str(amount).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        amt = None
    mid = (low + high) / 2.0 if (low is not None and high is not None) else amt
    if low is None and amt is not None:
        low = high = amt
    return low, high, mid


def _side(transaction) -> str:
    t = str(transaction or "").strip().lower()
    if t.startswith("purchase") or t.startswith("buy"):
        return "buy"
    if t.startswith("sale") or t.startswith("sell"):
        return "sell"
    return "exchange"


def _party(p) -> str:
    s = str(p or "").strip().upper()
    return s[0] if s[:1] in ("D", "R", "I") else "?"


def _chamber(house) -> str:
    # NB: 'Representatives' contains the substring 'sen' (repre·sen·tatives), so test the
    # specific 'senate' marker, not a bare 'sen' membership.
    return "Senate" if str(house or "").strip().lower().startswith("sen") else "House"


# ---------------------------------------------------------------------------
# data load
# ---------------------------------------------------------------------------
def _load_window(asof):
    """Normalized in-window disclosures grouped by ticker: {ticker: [rows]}, plus the full feed."""
    import pandas as pd
    p = config.data_dir() / "quiver" / "congress.parquet"
    df = pd.read_parquet(p)
    df["_rd"] = pd.to_datetime(df.get("ReportDate"), errors="coerce")
    df["_td"] = pd.to_datetime(df.get("TransactionDate"), errors="coerce")
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=ROLLOFF_DAYS)
    rows = []
    for r in df.to_dict("records"):
        rd = r.get("_rd")
        tk = str(r.get("Ticker") or "").strip().upper()
        if not tk or tk in ("-", "N/A", "NONE", "NAN"):
            continue
        low, high, mid = _amount_range(r.get("Range"), r.get("Amount"))
        rd_date = rd.date() if rd is not None and not pd.isna(rd) else None
        td = r.get("_td")
        rows.append({
            "ticker": tk,
            "representative": str(r.get("Representative") or "").strip(),
            "party": _party(r.get("Party")),
            "chamber": _chamber(r.get("House")),
            "side": _side(r.get("Transaction")),
            "amount_low": low, "amount_high": high, "amount_mid": mid,
            "report_date": rd_date.isoformat() if rd_date else None,
            "_rd": rd_date,
            "transaction_date": td.date().isoformat() if (td is not None and not pd.isna(td)) else None,
            "excess_return": _f(r.get("ExcessReturn")),
        })
    in_window = [r for r in rows if r["_rd"] is not None and r["_rd"] >= cutoff.date()]
    by_ticker: dict[str, list] = {}
    for r in in_window:
        by_ticker.setdefault(r["ticker"], []).append(r)
    feed = sorted(rows, key=lambda r: (r["report_date"] or "", r["transaction_date"] or ""), reverse=True)
    return by_ticker, feed, len(rows)


def _f(x):
    try:
        v = float(x)
        return v if v == v else None     # drop NaN
    except (TypeError, ValueError):
        return None


_SD_CACHE: dict[str, dict] = {}


def _stockdata(ticker: str, site: Path) -> dict:
    t = ticker.upper()
    if t in _SD_CACHE:
        return _SD_CACHE[t]
    d: dict = {}
    try:
        fp = site / "stockdata" / f"{t}.json"
        if fp.exists():
            d = json.loads(fp.read_text())
    except Exception:  # noqa: BLE001
        d = {}
    _SD_CACHE[t] = d
    return d


# ---------------------------------------------------------------------------
# the engine read: technical + buyable-zone, from the name's own published signals
# ---------------------------------------------------------------------------
def _engine_read(sd: dict, sector_rs: dict, alloc_ranks: dict, n_themes: int) -> dict:
    out = {"covered": False, "technical": None, "zone": None, "blocked": False, "extended": False,
           "downtrend": False, "sector_dir": None, "theme_dir": None, "trend_dir": None,
           "band": None, "verdict": None, "timing": None, "price": None}
    if not sd:
        return out
    conv = sd.get("conviction") or {}
    tech = sd.get("tech") or {}
    if not tech and not conv:
        return out
    out["covered"] = True
    out["band"] = conv.get("band")
    out["verdict"] = conv.get("verdict")
    out["price"] = tech.get("price")
    size = conv.get("size") or {}
    ext = conv.get("ext") if isinstance(conv.get("ext"), dict) else {}
    grade = (ext or {}).get("grade")
    parabolic = bool((ext or {}).get("parabolic"))
    bucket = size.get("bucket")
    pct = size.get("pct")
    blocked = bool(conv.get("cycle_blocked")) or bucket == "avoid" or parabolic or (pct == 0)

    a50, a200 = tech.get("above50"), tech.get("above200")
    p200 = tech.get("pct_vs_200dma")
    macd, rsi, off = tech.get("macd_pos"), tech.get("rsi14"), tech.get("off_52w_high_pct")
    extended = grade in ("stretched", "extended", "parabolic") or (isinstance(p200, (int, float)) and p200 >= 30)
    below200_broken = a200 is False and (p200 is None or p200 <= -2)
    offv = off if isinstance(off, (int, float)) else 0
    downtrend = below200_broken or (a50 is False and offv <= -18) or (a50 is False and macd is False and offv <= -16)
    uptrend = (a50 is True and a200 is True and macd is True
               and (rsi is None or 45 <= rsi <= 75) and (off is None or off > -12))

    # --- TECHNICAL sub-score ---
    if blocked:
        technical = 15.0
    else:
        s = 50.0
        s += {"strong": 18, "high": 12, "moderate": 4, "low": -6, "avoid": -25}.get((out["band"] or "").lower(), 0)
        s += 8 if a200 is True else (-15 if a200 is False else 0)
        s += 4 if a50 is True else (-6 if a50 is False else 0)
        s += 5 if macd is True else (-4 if macd is False else 0)
        if isinstance(off, (int, float)):
            s += 5 if off > -12 else (-8 if off <= -18 else 0)
        if isinstance(rsi, (int, float)) and 45 <= rsi <= 70:
            s += 3
        if extended:
            s -= 10
        technical = _clamp(s)

    # --- BUYABLE-ZONE sub-score ---
    sec = sd.get("sector") or (sd.get("factors") or {}).get("sector")
    etf = SECTOR_ETF.get(sec)
    srs = sector_rs.get(etf) if etf else None
    sector_dir = None
    if srs:
        a200s = srs.get("above_200d_trend")
        pctile = srs.get("pctile_252d")
        mom60 = srs.get("mom_60d_pct")
        lagging = a200s is False and ((pctile if pctile is not None else 100) < 35 or (mom60 or 0) <= -12)
        sector_dir = "bull" if (a200s and (pctile or 0) >= 70) else "bear" if lagging else "neutral"

    theme_dir = None
    mem = sd.get("baskets_membership") or []
    slug = None
    if isinstance(mem, list) and mem:
        slug = mem[0].get("slug") if isinstance(mem[0], dict) else (mem[0] if isinstance(mem[0], str) else None)
    rk = alloc_ranks.get(slug) if slug else None
    if rk and n_themes:
        rank = rk.get("rank")
        if rank is not None:
            leader = rank <= max(1, n_themes / 3.0) and rk.get("eligible") is not False
            laggard = rank > 2.0 * n_themes / 3.0 or rk.get("eligible") is False
            theme_dir = "bear" if laggard else "bull" if leader else "neutral"

    trend_dir = "bear" if downtrend else "bull" if uptrend else "neutral"
    zone = 50.0
    zone += {"bull": 20.0, "bear": -25.0}.get(sector_dir, 0.0)
    zone += {"bull": 12.0, "bear": -12.0}.get(theme_dir, 0.0)
    zone += {"bull": 18.0, "neutral": 4.0, "bear": -30.0}.get(trend_dir, 0.0)
    if extended:
        zone -= 15.0

    if blocked:
        timing = "engine-blocked — wait"
    elif downtrend:
        timing = "downtrend — avoid the catch"
    elif extended:
        timing = "extended — wait for a base"
    elif trend_dir == "bull" and sector_dir != "bear":
        timing = "uptrend confirmed, sector leading"
    elif trend_dir == "neutral":
        timing = "constructive pullback"
    else:
        timing = "mixed / unconfirmed"

    out.update({"technical": round(technical, 1), "zone": round(_clamp(zone), 1), "blocked": blocked,
                "extended": extended, "downtrend": downtrend, "sector_dir": sector_dir,
                "theme_dir": theme_dir, "trend_dir": trend_dir, "timing": timing})
    return out


# ---------------------------------------------------------------------------
# cluster aggregation + composite score
# ---------------------------------------------------------------------------
def _aggregate(ticker: str, trades: list, asof) -> dict:
    from datetime import date as _date
    members = sorted({t["representative"] for t in trades if t["representative"]})
    buys = [t for t in trades if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell"]
    buy_parties = sorted({t["party"] for t in buys if t["party"] in ("D", "R", "I")})
    buy_notional = sum((t["amount_mid"] or 0.0) for t in buys)
    w_buy = sum(_decay(t["_rd"], asof) for t in buys)
    w_sell = sum(_decay(t["_rd"], asof) for t in sells)
    recency = max((_decay(t["_rd"], asof) for t in trades), default=0.0)
    rds = [t["_rd"] for t in trades if t["_rd"]]
    last_report = max(rds) if rds else None
    bipartisan = len([p for p in buy_parties if p in ("D", "R")]) >= 2
    n_distinct = len(members)

    breadth = min(n_distinct / MEMBERS_SATURATE_AT, 1.0)
    buy_ratio = (w_buy / (w_buy + w_sell)) if (w_buy + w_sell) > 0 else 0.5
    size = min(buy_notional / AMOUNT_SATURATE_USD, 1.0)
    cluster = 100.0 * (0.40 * breadth + 0.25 * buy_ratio + 0.20 * size + 0.15 * recency)
    if bipartisan:
        cluster += 8.0

    expiry = (last_report + timedelta(days=ROLLOFF_DAYS)) if last_report else None
    days_left = (expiry - asof).days if expiry else None

    by_member: dict[str, dict] = {}
    for t in sorted(trades, key=lambda x: x["report_date"] or "", reverse=True):
        m = t["representative"]
        if not m:
            continue
        rec = by_member.setdefault(m, {"representative": m, "party": t["party"], "chamber": t["chamber"],
                                       "n": 0, "last_side": t["side"], "last_report": t["report_date"],
                                       "notional": 0.0})
        rec["n"] += 1
        rec["notional"] += (t["amount_mid"] or 0.0)

    return {
        "ticker": ticker, "n_disclosures": len(trades), "n_distinct_members": n_distinct,
        "members": members, "member_detail": sorted(by_member.values(), key=lambda r: -r["notional"]),
        "n_buys": len(buys), "n_sells": len(sells),
        "buy_notional": round(buy_notional), "buy_parties": buy_parties, "bipartisan": bipartisan,
        "important": n_distinct >= MIN_DISTINCT_MEMBERS,
        "last_report": last_report.isoformat() if last_report else None,
        "expires": expiry.isoformat() if expiry else None, "days_left": days_left,
        "recency": round(recency, 3), "cluster_score": round(_clamp(cluster), 1),
    }


def _score(agg: dict, eng: dict) -> dict:
    cluster = agg["cluster_score"]
    tech, zone = eng.get("technical"), eng.get("zone")
    covered = eng.get("covered", False)

    if covered:
        # Full composite: cluster + technical + zone with neutral fill-ins for missing legs.
        tw = W_CLUSTER + W_TECHNICAL + W_ZONE
        composite = (W_CLUSTER * cluster + W_TECHNICAL * (tech if tech is not None else 50.0)
                     + W_ZONE * (zone if zone is not None else 50.0)) / tw
        # Apply blocked/downtrend/extended multiplier vetoes only for covered names; an uncovered
        # name has no engine to veto it, so letting these multipliers fire on stale/absent signals
        # would be misleading and was also bypassed entirely before (composite used neutral fill-ins
        # that dodged the check).  Keeping them under the covered branch restores the intended guard.
        if eng.get("blocked") or eng.get("downtrend"):
            composite *= 0.6
        elif eng.get("extended"):
            composite *= 0.85
        unconfirmed = False
    else:
        # Uncovered: no engine read → only the cluster signal is real.  Use cluster-only composite
        # (W_CLUSTER weight normalised to 1.0) and skip all multiplier vetoes.  The neutral 50.0
        # gift previously awarded for missing technical/zone inflated uncovered scores by ~30 points,
        # letting them outrank vetoed covered names.  Audit finding: brief #4.
        composite = W_CLUSTER * cluster          # = 0.40 × cluster; intentionally un-normalised
        unconfirmed = True

    act_now = bool(covered and tech is not None and zone is not None and zone >= ACT_MIN_ZONE
                   and tech >= ACT_MIN_TECH and not (eng.get("blocked") or eng.get("downtrend") or eng.get("extended")))
    return {**agg, "name": None, "composite": round(composite, 1), "act_now": act_now,
            "unconfirmed": unconfirmed,
            "technical_score": tech, "zone_score": zone, "covered": covered,
            "band": eng.get("band"), "verdict": eng.get("verdict"), "timing": eng.get("timing"),
            "sector_dir": eng.get("sector_dir"), "theme_dir": eng.get("theme_dir"),
            "trend_dir": eng.get("trend_dir"), "extended": eng.get("extended"),
            "downtrend": eng.get("downtrend"), "blocked": eng.get("blocked"), "price": eng.get("price")}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        site = config.ROOT / "site"
        asof = datetime.now(timezone.utc).date()
        by_ticker, feed, n_total = _load_window(asof)

        # scoring substrates (regime sector RS + theme allocation ranks), guarded
        sector_rs: dict = {}
        try:
            reg = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
            sector_rs = {r.get("ticker"): r for r in (reg.get("sector_rs") or []) if r.get("ticker")}
        except Exception as e:  # noqa: BLE001
            log.warning("regime sector_rs load failed (%s)", e)
        alloc_ranks: dict = {}
        n_themes = 0
        try:
            alloc = json.loads((site / "allocationdata" / "allocation.json").read_text())
            ranks = alloc.get("ranks") or []
            n_themes = alloc.get("n_themes") or len(ranks)
            alloc_ranks = {r.get("id"): r for r in ranks if r.get("id")}
        except Exception as e:  # noqa: BLE001
            log.warning("allocation ranks load failed (%s)", e)

        items = []
        for tk, trades in by_ticker.items():
            agg = _aggregate(tk, trades, asof)
            sd = _stockdata(tk, site)
            eng = _engine_read(sd, sector_rs, alloc_ranks, n_themes)
            row = _score(agg, eng)
            row["name"] = sd.get("name")
            items.append(row)
        # Covered rows always rank above unconfirmed (uncovered) rows; within each bucket sort by
        # composite descending.  The template receives a single list and is unchanged.
        items.sort(key=lambda a: (1 if a["unconfirmed"] else 0, -a["composite"]))

        # attach company names to the recent-disclosure feed too
        for r in feed[:FEED_CAP]:
            r["name"] = _stockdata(r["ticker"], site).get("name")

        summary = {
            "n_disclosures_window": sum(len(v) for v in by_ticker.values()),
            "n_total": n_total,
            "n_tickers": len(items),
            "n_important": sum(1 for a in items if a["important"]),
            "n_act_now": sum(1 for a in items if a["act_now"]),
            "n_bipartisan": sum(1 for a in items if a["bipartisan"]),
            "as_of": (feed[0]["report_date"] if feed else asof.isoformat()),
        }

        built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
        try:
            html = env.get_template("congress_trades.html.j2").render(
                summary=summary, items=items[:WATCH_TABLE_CAP], n_shown=min(len(items), WATCH_TABLE_CAP),
                feed=feed[:FEED_CAP], window_days=ROLLOFF_DAYS, generated_utc=built,
                weights={"cluster": W_CLUSTER, "technical": W_TECHNICAL, "zone": W_ZONE},
                active_section="research", active_page="congress_trades",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("congress render failed — skipping (additive): %s", e)
            return 0
        site.mkdir(exist_ok=True)
        write_page(site / "congress_trades.html", html)
        log.info("wrote %s/congress_trades.html (%d watchlist tickers, %d in-window disclosures, %d KB)",
                 site, summary["n_tickers"], summary["n_disclosures_window"], len(html) // 1024)
        return 0
    except Exception as e:  # noqa: BLE001 — never break the daily build
        log.warning("congress page failed — skipping (additive): %s", e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
