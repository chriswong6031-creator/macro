"""13F Smart-Money TRADE TRACKER — turn the curated super-investor snapshots into a
graded, per-TRADE scorecard so we can see *who made the excellent trades*.

The neighbouring engine.smart_money diffs each fund's quarters into new/add/trim/exit
and answers "who holds this name". This module asks the sharper question the desk
actually cares about: **after a fund made a move, did it WORK?** For every position
change we place a look-ahead-free entry on the fund's PUBLIC filing date and measure
the SPY-relative ("excess") return — both at a fixed 63-session horizon (apples-to-
apples skill) and live-to-latest-close (the realised "front-ran the rally" P&L). From
those rows we roll up:

  * a per-fund SCORECARD (buy hit-rate, average excess, best/worst trade, A–D grade),
  * a LEADERBOARD ranking the tracked funds by trade quality,
  * BEST / WORST trade boards across every fund, and
  * a per-fund ROTATION view (what each fund rotated INTO vs OUT OF last quarter).

The motivating contrast, straight out of the data: **Tepper (Appaloosa)** rotated into
semis/memory — new TSM (Q3) and a built-up Micron + NVDA — and front-ran the AI/memory
leg; **Ackman (Pershing)** concentrated into the Mag-7 laggards (AMZN/MSFT/META). The
tracker surfaces that quality gap empirically rather than asserting it.

PRICE COVERAGE — the one real upgrade over engine.manager_quality: it scored on the
S&P-only breadth caches and was therefore BLIND to ADRs, so a manager's biggest, best
trades (TSM, BABA, PDD, JD …) never scored. Here the close panel is the UNION of the
breadth caches AND data/yahoo/<T>.parquet (total-return adjusted), with SPY as the
benchmark — so the globally-diversified super-investors are finally measured on their
whole book.

HONESTY (surfaced on the page): 13F is quarterly with a ~45-day lag, long-only US
equity stakes ≥ $100M — no shorts, options, or non-US/private positions. "Since-filing"
excess uses a VARIABLE hold (an older quarter's trade has run longer than a recent
one), so it is a realised-P&L read, not a fixed-horizon skill metric; the 63-day excess
is the apples-to-apples figure. This is descriptive CONTEXT and a *track record*, never
a buy list and never wired into any score/allocation.
"""
from __future__ import annotations

import glob
import logging
import os
from datetime import datetime, timezone

import pandas as pd

from engine.smart_money import (NOTE, _read_all, diff_snapshots, full_cusip_map,
                                name_ticker_map, resolve_tickers)
from lib import config

log = logging.getLogger(__name__)

# fixed horizon for the apples-to-apples skill leg (~one quarter of sessions — the 13F
# hold cadence), matching engine.manager_quality so the two stay comparable.
HORIZON = 63
# a position change must be at least this % of the reported book to make the BEST/WORST
# boards (filters rounding-level lots so a board entry is a real conviction trade).
MIN_CONVICTION_PCT = 1.0
# a fund needs this many priced buys before it is RANKED on the leaderboard (else it is
# listed "insufficient" — we never promote a fund off two lucky trades).
MIN_RANKED_BUYS = 5
# if the first priced session is more than this many calendar days after the filing
# date, the entry is a SNAP-FORWARD (the price series starts after the filing — e.g. an
# S&P name filed before the breadth cache begins). We keep the realised "since" read but
# DROP the fixed-horizon skill leg for it, so avg_buy_excess_h stays a true filing-anchored
# window. A normal weekend/holiday gap (1-3 sessions) is well under this.
SNAP_MAX_DAYS = 8
BENCHMARK = "SPY"
_BUY = {"new", "add"}
_SELL = {"trim", "exit"}

TRACKER_NOTE = (
    "Track record of curated super-investor 13F trades. Each move is entered on the "
    "fund's PUBLIC filing date (look-ahead-free) and scored vs SPY. Funds are ranked on "
    "the MEDIAN trade excess (outlier-robust) — the realised 'since' mean uses a variable "
    "hold (older trades have run longer) so it is P&L, not skill; the 63-day excess is the "
    "fixed-horizon figure. Some off-index names (foreign ADRs, small-caps) cannot be "
    "priced and are dropped, so each fund's coverage % is shown. "
    + NOTE)

TRACKER_NOTE_ZH = (
    "精选超级投资者 13F 交易的业绩记录。每笔操作以基金的公开申报日为入场点（无前视偏差），"
    "并以相对标普500的超额收益评分。基金按交易超额收益的中位数排名（抗异常值）——已实现的"
    "“自申报”均值采用可变持有期（较早的交易运行更久），因此是盈亏而非选股能力；63日超额收益"
    "为固定持有期口径。部分非指数成分（境外 ADR、小盘股）无法定价而被剔除，故每只基金均标注"
    "覆盖率。13F 持仓为季度披露、约45天滞后，仅含 ≥1亿美元的美股多头，不含空头、期权或非美持仓；"
    "为背景信息与业绩记录，并非买入建议或实时信号，且从不接入任何评分/配置。")


# --------------------------------------------------------------------------- #
# Unified close panel (breadth ∪ yahoo) + SPY benchmark.
# --------------------------------------------------------------------------- #
class ClosePanel:
    """Lazy close provider over the UNION of the breadth caches and the per-ticker
    data/yahoo parquets, with SPY as the benchmark. yahoo wins on overlap (deeper
    history; carries the ADRs the breadth caches omit). Reads disk; the math below is
    pure given a panel, so tests can substitute a fake with the same .get/.excess API."""

    def __init__(self, breadth: pd.DataFrame | None = None) -> None:
        self._breadth = breadth if breadth is not None else _breadth_panel()
        self._yahoo: dict[str, pd.Series | None] = {}
        self.spy = self.get(BENCHMARK)
        # newest close we can price against (SPY is the freshest universal series)
        self.thru = (str(self.spy.index[-1].date()) if self.spy is not None
                     and len(self.spy) else "")

    def _yahoo_close(self, ticker: str) -> pd.Series | None:
        if ticker in self._yahoo:
            return self._yahoo[ticker]
        p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
        s = None
        if p.exists():
            try:
                df = pd.read_parquet(p, columns=["close"])
                s = df["close"].dropna()
                s.index = pd.to_datetime(s.index)
                s = s.sort_index()
            except Exception:  # noqa: BLE001 — a malformed cache just degrades to None
                s = None
        self._yahoo[ticker] = s
        return s

    def get(self, ticker: str) -> pd.Series | None:
        """Close series for a ticker (yahoo first, then the breadth panel), or None."""
        if not ticker:
            return None
        ys = self._yahoo_close(ticker)
        if ys is not None and len(ys):
            return ys
        if self._breadth is not None and ticker in self._breadth.columns:
            s = self._breadth[ticker].dropna()
            if len(s):
                return s
        return None

    def excess(self, ticker: str, entry: str, horizon: int | None = None) -> dict | None:
        """SPY-relative return for `ticker` from the first session on/after `entry`.

        ``horizon=None`` → live-to-latest-close (variable hold). ``horizon=N`` → N
        sessions later, or None if that window has not fully elapsed yet (so an
        unfinished trade is never scored as a fixed-horizon result). Returns
        {abs, spy, excess, entry_date, end_date, hold_days} or None when the ticker /
        benchmark is unpriced or the entry post-dates all data."""
        s = self.get(ticker)
        if s is None or self.spy is None:
            return None
        e = pd.Timestamp(entry)
        after = s.index[s.index >= e]
        if len(after) == 0:
            return None
        pos0 = s.index.get_loc(after[0])
        if isinstance(pos0, slice):                  # duplicate index guard
            pos0 = pos0.start
        # snap-forward: the series starts after the requested entry (e.g. an S&P name
        # filed before the breadth cache begins). Honest for the realised "since" read,
        # but the fixed-horizon SKILL window would be mis-anchored, so drop it there.
        snap_days = int((s.index[pos0] - e).days)
        if horizon is not None:
            if snap_days > SNAP_MAX_DAYS:            # window not filing-anchored → not skill
                return None
            if pos0 + horizon >= len(s):             # window not complete → not scorable
                return None
            end_pos = pos0 + horizon
        else:
            end_pos = len(s) - 1
        if end_pos <= pos0:
            return None
        p0, p1 = float(s.iloc[pos0]), float(s.iloc[end_pos])
        if p0 <= 0:
            return None
        d0, d1 = s.index[pos0], s.index[end_pos]
        stock = p1 / p0 - 1.0
        bench = self._spy_window(d0, d1)
        if bench is None:
            return None
        return {
            "abs": round(stock, 4),
            "spy": round(bench, 4),
            "excess": round(stock - bench, 4),
            "entry_date": str(d0.date()),
            "end_date": str(d1.date()),
            "hold_days": int((d1 - d0).days),
            "entry_lag_days": max(0, snap_days),     # >SNAP_MAX_DAYS ⇒ snapped (since-only)
        }

    def _spy_window(self, d0: pd.Timestamp, d1: pd.Timestamp) -> float | None:
        sp = self.spy
        i0 = sp.index[sp.index >= d0]
        i1 = sp.index[sp.index <= d1]
        if len(i0) == 0 or len(i1) == 0:
            return None
        b0, b1 = float(sp.loc[i0[0]]), float(sp.loc[i1[-1]])
        return (b1 / b0 - 1.0) if b0 > 0 else None


def _breadth_panel() -> pd.DataFrame | None:
    """Combined date×ticker close panel from the breadth caches (S&P large/small/mid),
    deduped on ticker. None if none are present (then the tracker degrades to yahoo-only
    coverage)."""
    frames = []
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            try:
                frames.append(pd.read_parquet(p))
            except Exception:  # noqa: BLE001
                continue
    if not frames:
        return None
    panel = pd.concat(frames, axis=1, sort=False)    # union of dates; sorted explicitly below
    panel = panel.loc[:, ~panel.columns.duplicated()]
    panel.index = pd.to_datetime(panel.index)
    return panel.sort_index()


# --------------------------------------------------------------------------- #
# Per-fund trade scoring (pure given a ClosePanel + resolver maps).
# --------------------------------------------------------------------------- #
def _trade_quality(action: str, since_excess: float | None) -> float | None:
    """Direction-aware skill of one trade from its SINCE excess: a BUY is skillful when
    the name then beat SPY (+excess); a SELL is skillful when it then LAGGED (−excess,
    i.e. the sale dodged underperformance). Returns the signed skill (higher = better)
    or None if unpriced. PURE."""
    if since_excess is None:
        return None
    if action in _BUY:
        return since_excess
    if action in _SELL:
        return -since_excess
    return None


def score_fund_trades(slug: str, name: str, panel: ClosePanel,
                      name_map: dict[str, str], cusip_map: dict[str, str],
                      horizon: int = HORIZON, counters: dict | None = None) -> list[dict]:
    """Every priced position change across a fund's retained quarters, as scored trade
    rows. Iterates consecutive snapshot pairs (ascending), diffs → resolves → places a
    filing-date entry → scores excess (since + fixed-horizon). Rows missing a filing
    date or a price are dropped (look-ahead-free, coverage-honest).

    `counters` (optional out-dict) accumulates 'attempted'/'priced' move counts so the
    caller can expose a per-fund price-coverage fraction (some funds hold off-universe
    ADRs/small-caps we cannot price — that drop must be visible, not silent)."""
    snaps = _read_all(slug)                          # (period_end, filing_date, df) asc
    rows: list[dict] = []
    for i in range(len(snaps) - 1):
        _pe_prev, _fd_prev, prev = snaps[i]
        pe_cur, fd_cur, cur = snaps[i + 1]
        if not fd_cur:                               # no public date → can't place entry
            continue
        diff = diff_snapshots(prev, cur)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        diff = diff[diff["ticker"].notna()]
        if diff.empty:
            continue
        # collapse dual-class / multi-lot lines mapping to the same ticker (BRK-A+BRK-B,
        # FOX+FOXA…) so a fund is scored ONCE per name — mirrors compute_smart_money and
        # the sibling engines; without this a name-collision could double-count a fund.
        diff = (diff.sort_values("value_usd", ascending=False)
                .groupby("ticker", as_index=False)
                .agg(issuer=("issuer", "first"), action=("action", "first"),
                     pct_portfolio=("pct_portfolio", "sum"), value_usd=("value_usd", "sum"),
                     shares_change_pct=("shares_change_pct", "first")))
        for r in diff.itertuples(index=False):
            if r.action not in _BUY and r.action not in _SELL:
                continue                             # skip 'hold' — not a trade
            if counters is not None:
                counters["attempted"] = counters.get("attempted", 0) + 1
            since = panel.excess(r.ticker, fd_cur)
            if since is None:
                continue                             # unpriced → not on the record
            if counters is not None:
                counters["priced"] = counters.get("priced", 0) + 1
            fwd = panel.excess(r.ticker, fd_cur, horizon=horizon)
            scp = getattr(r, "shares_change_pct", None)
            rows.append({
                "slug": slug, "fund": slug.upper(), "name": name,
                "ticker": r.ticker, "issuer": str(getattr(r, "issuer", "") or ""),
                "action": r.action,
                "period_end": pe_cur, "filing_date": fd_cur,
                "pct_portfolio": round(float(r.pct_portfolio), 2),
                "shares_change_pct": (None if scp is None or pd.isna(scp)
                                      else round(float(scp), 1)),
                "since_excess": since["excess"], "since_abs": since["abs"],
                "spy_since": since["spy"], "hold_days": since["hold_days"],
                "fwd_excess": fwd["excess"] if fwd else None,
                "fwd_abs": fwd["abs"] if fwd else None,
                "quality": _trade_quality(r.action, since["excess"]),
            })
    return rows


def fund_scorecard(trades: list[dict]) -> dict:
    """Aggregate one fund's scored trades into a scorecard. PURE.

    `median_buy_excess` is the OUTLIER-ROBUST central trade (the leaderboard ranks on it
    so a couple of long-held lottery winners can't mint a grade). `avg_buy_excess` /
    `buy_hit_rate` are the SINCE-filing (variable-hold) realised figures; `avg_buy_excess_h`
    is the fixed-horizon, filing-anchored skill leg (snap-forward windows excluded)."""
    import statistics as _st
    buys = [t for t in trades if t["action"] in _BUY]
    sells = [t for t in trades if t["action"] in _SELL]
    buy_ex = [t["since_excess"] for t in buys if t["since_excess"] is not None]
    buy_h = [t["fwd_excess"] for t in buys if t["fwd_excess"] is not None]
    sell_skill = [-t["since_excess"] for t in sells if t["since_excess"] is not None]
    # rank/compare only priced, conviction-grade buys; guard None before max/min (PURE
    # invariant — a None since_excess would otherwise raise on the comparison key)
    rankable = [t for t in (buys if not any(t["pct_portfolio"] >= MIN_CONVICTION_PCT
                                            for t in buys) else
                            [b for b in buys if b["pct_portfolio"] >= MIN_CONVICTION_PCT])
                if t["since_excess"] is not None]
    best = max(rankable, key=lambda t: t["since_excess"], default=None)
    worst = min(rankable, key=lambda t: t["since_excess"], default=None)
    return {
        "n_trades": len(trades),
        "n_buys": len(buy_ex),
        "n_sells": len(sell_skill),
        "median_buy_excess": round(_st.median(buy_ex), 4) if buy_ex else None,
        "avg_buy_excess": round(sum(buy_ex) / len(buy_ex), 4) if buy_ex else None,
        "buy_hit_rate": (round(sum(1 for x in buy_ex if x > 0) / len(buy_ex), 3)
                         if buy_ex else None),
        "avg_buy_excess_h": round(sum(buy_h) / len(buy_h), 4) if buy_h else None,
        "n_buys_h": len(buy_h),
        "sell_skill": round(sum(sell_skill) / len(sell_skill), 4) if sell_skill else None,
        "best_trade": _slim(best),
        "worst_trade": _slim(worst),
    }


def _slim(t: dict | None) -> dict | None:
    """A compact trade card for embedding in scorecards/leaderboards."""
    if not t:
        return None
    return {k: t[k] for k in ("ticker", "issuer", "action", "period_end", "filing_date",
                              "pct_portfolio", "shares_change_pct", "since_excess",
                              "since_abs", "spy_since", "hold_days", "fwd_excess") if k in t}


def _grade(z: float | None) -> str:
    if z is None:
        return "n/a"
    if z >= 0.5:
        return "A"
    if z >= 0.0:
        return "B"
    if z >= -0.5:
        return "C"
    return "D"


def rank_leaderboard(scorecards: dict[str, dict], min_buys: int = MIN_RANKED_BUYS) -> list[dict]:
    """Order funds by robust buy quality, cross-sectionally z-scored into an A–D grade
    over the funds that clear `min_buys` priced buys. Below-gate funds are kept (listed)
    but ungraded and sorted to the bottom. PURE.

    Rank key = MEDIAN since-filing buy excess (outlier-robust: a couple of long-held
    lottery winners can't carry a fund), tie-broken by buy hit-rate. The realised mean
    and the 63-day skill leg ride along as displayed context. The grade z is computed
    over eligible funds only, so a thin record can't earn an A."""
    eligible = {s: sc["median_buy_excess"] for s, sc in scorecards.items()
                if sc.get("n_buys", 0) >= min_buys and sc.get("median_buy_excess") is not None}
    vals = list(eligible.values())
    if len(vals) >= 3:
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
    else:
        mu, sd = 0.0, 0.0

    board = []
    for slug, sc in scorecards.items():
        med = eligible.get(slug)
        z = round((med - mu) / sd, 2) if (slug in eligible and sd > 0) else None
        board.append({
            "slug": slug, "name": sc.get("name", slug),
            "ranked": slug in eligible,
            "grade": _grade(z), "quality_z": z,
            "median_buy_excess": sc.get("median_buy_excess"),
            "avg_buy_excess": sc.get("avg_buy_excess"),
            "avg_buy_excess_h": sc.get("avg_buy_excess_h"),
            "buy_hit_rate": sc.get("buy_hit_rate"),
            "sell_skill": sc.get("sell_skill"),
            "n_buys": sc.get("n_buys", 0),
            "n_buys_h": sc.get("n_buys_h", 0),
            "n_trades": sc.get("n_trades", 0),
            "coverage_pct": sc.get("coverage_pct"),
            "best_trade": sc.get("best_trade"),
            "worst_trade": sc.get("worst_trade"),
            # Manager lag fields (None when unavailable — additive, no schema breakage)
            "turnover_pct": sc.get("turnover_pct"),
            "turnover_tier": sc.get("turnover_tier"),
            "holding_period_q": sc.get("holding_period_q"),
            "concentration_pct": sc.get("concentration_pct"),
            "n_holdings": sc.get("n_holdings"),
            "style": sc.get("style"),
            "status": sc.get("status"),
            # Decay chips at horizons 21/63/126 (252 omitted — frozen-until-matured)
            "decay": sc.get("decay"),
        })
    # eligible funds first (by robust median excess, then hit-rate), then the rest
    board.sort(key=lambda r: (
        0 if r["ranked"] else 1,
        -(r["median_buy_excess"] if r["median_buy_excess"] is not None else -9),
        -(r["buy_hit_rate"] if r["buy_hit_rate"] is not None else 0),
    ))
    for i, r in enumerate(board, 1):
        r["rank"] = i if r["ranked"] else None
    return board


def fund_rotation(slug: str, name: str, trades: list[dict], top_holdings: list[dict],
                  latest_period: str) -> dict:
    """The fund's MOST-RECENT-quarter rotation: what it bought INTO vs sold OUT OF,
    each tagged with how the move has done since (excess vs SPY). PURE."""
    latest = [t for t in trades if t["period_end"] == latest_period]
    into = sorted((t for t in latest if t["action"] in _BUY),
                  key=lambda t: -t["pct_portfolio"])
    out = sorted((t for t in latest if t["action"] in _SELL),
                 key=lambda t: (t["shares_change_pct"] if t["shares_change_pct"]
                                is not None else 0))
    return {
        "slug": slug, "name": name, "period_end": latest_period,
        "into": [_slim(t) for t in into[:10]],
        "out": [_slim(t) for t in out[:10]],
        "top_holdings": top_holdings,
    }


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def _top_holdings(slug: str, panel_unused, name_map, cusip_map,
                  latest_trades_by_ticker: dict[str, dict], top_n: int = 8) -> tuple[list[dict], str, str, float]:
    """Latest snapshot's top holdings (resolved, % of book), each tagged with the
    quarter's action. Returns (rows, period_end, filing_date, book_value_usd)."""
    snaps = _read_all(slug)
    if not snaps:
        return [], "", "", 0.0
    period_end, filing_date, snap = snaps[-1]
    eq = snap[snap.get("sh_type", "SH") == "SH"].copy()
    if eq.empty:
        return [], period_end, filing_date, 0.0
    eq = resolve_tickers(eq, name_map, cusip_map)
    book = float(eq["value_usd"].sum()) or 1.0
    per = (eq[eq["ticker"].notna()].groupby("ticker", as_index=False)
           .agg(issuer=("issuer", "first"), value_usd=("value_usd", "sum")))
    per["pct"] = 100.0 * per["value_usd"] / book
    rows = []
    for r in per.sort_values("value_usd", ascending=False).head(top_n).itertuples(index=False):
        tr = latest_trades_by_ticker.get(r.ticker)
        rows.append({
            "ticker": r.ticker, "issuer": str(r.issuer or ""),
            "pct": round(float(r.pct), 2),
            "action": tr["action"] if tr else "hold",
            "since_excess": tr["since_excess"] if tr else None,
        })
    return rows, period_end, filing_date, round(book, 0)


def _featured(by_fund: dict, leaderboard: list[dict], pair: list[str]) -> dict | None:
    """The marquee head-to-head. Defaults to the configured pair (Tepper vs Ackman);
    falls back to leaderboard top-vs-bottom if a pinned fund is missing/unscored. The
    higher MEDIAN buy excess is the 'winner'; the card carries the full robust stat set
    (median, realised mean, 63-day skill, hit-rate) so the gap is never headlined on a
    single outlier-fragile number."""
    def card(slug: str) -> dict | None:
        f = by_fund.get(slug)
        if not f or not f.get("scorecard"):
            return None
        sc = f["scorecard"]
        into = [t for t in (f.get("rotation", {}).get("into") or [])
                if t.get("since_excess") is not None]
        return {
            "slug": slug, "name": f["name"],
            "median_buy_excess": sc.get("median_buy_excess"),
            "avg_buy_excess": sc.get("avg_buy_excess"),
            "avg_buy_excess_h": sc.get("avg_buy_excess_h"),
            "buy_hit_rate": sc.get("buy_hit_rate"),
            "grade": next((r["grade"] for r in leaderboard if r["slug"] == slug), "n/a"),
            "best_trade": sc.get("best_trade"),
            "worst_trade": sc.get("worst_trade"),
            "rotation_into": sorted(into, key=lambda t: -(t["since_excess"] or 0))[:5],
            "top_holdings": f.get("rotation", {}).get("top_holdings", [])[:5],
        }

    a = card(pair[0]) if len(pair) > 0 else None
    b = card(pair[1]) if len(pair) > 1 else None
    if not (a and b):                                # fall back to empirical extremes
        ranked = [r for r in leaderboard if r["ranked"]]
        if len(ranked) >= 2:
            a, b = card(ranked[0]["slug"]), card(ranked[-1]["slug"])
    if not (a and b):
        return None
    winner, laggard = (a, b) if (a["median_buy_excess"] or -9) >= (b["median_buy_excess"] or -9) else (b, a)
    def _gap(key):
        wv, lv = winner.get(key), laggard.get(key)
        return round(wv - lv, 4) if (wv is not None and lv is not None) else None
    return {"winner": winner, "laggard": laggard,
            "excess_gap": _gap("median_buy_excess"),        # gap on the ranking (robust) key
            "hit_gap": _gap("buy_hit_rate"),
            "realised_gap": _gap("avg_buy_excess")}         # the dramatic realised-P&L gap (context)


def compute_tracker(cfg: dict | None = None) -> dict | None:
    """Build the full tracker payload. Reads the smart_money snapshots + the unified
    close panel; returns None if there is nothing to score. Additive/optional — the
    build script swallows any failure so the daily run never breaks."""
    cfg = cfg if cfg is not None else (config.load().get("smart_money", {}) or {})
    funds = cfg.get("funds", {}) or {}
    if not funds:
        return None
    tcfg = cfg.get("tracker", {}) or {}
    horizon = int(tcfg.get("horizon_days", HORIZON))
    min_conv = float(tcfg.get("min_conviction_pct", MIN_CONVICTION_PCT))
    board_n = int(tcfg.get("board_top_n", 25))
    pair = list(tcfg.get("featured_pair", ["appaloosa", "pershing"]))

    panel = ClosePanel()
    name_map = name_ticker_map()
    cusip_map, _ = full_cusip_map()

    all_trades: list[dict] = []
    by_fund: dict[str, dict] = {}
    scorecards: dict[str, dict] = {}
    as_of_dates, filing_dates = [], []

    for slug, spec in funds.items():
        name = spec.get("name", slug)
        counters: dict = {}
        trades = score_fund_trades(slug, name, panel, name_map, cusip_map, horizon, counters)
        all_trades.extend(trades)
        sc = fund_scorecard(trades)
        sc["name"] = name
        # per-fund price coverage — what fraction of this fund's resolvable moves we could
        # actually price (off-universe ADRs/small-caps are unpriced and dropped). Surfaced
        # so a thin-coverage fund's grade is read with the right grain of salt.
        att, pri = counters.get("attempted", 0), counters.get("priced", 0)
        sc["n_attempted"] = att
        sc["coverage_pct"] = round(100.0 * pri / att, 1) if att else None
        # ---- Manager lag diagnostics (additive; tolerant of missing equiv table) ----
        try:
            from engine.manager_lag import (fund_turnover as _ft,
                                            effective_holding_period as _ehp,
                                            lag_tier as _lt,
                                            concentration_top10 as _ct10,
                                            n_holdings as _nh,
                                            _load_equiv_table as _let,
                                            _read_all_snaps_for_lag)
        except ImportError:
            pass
        else:
            try:
                equiv = _let()
                ft = _ft(slug, equiv)
                snaps = _read_all_snaps_for_lag(slug)
                hp_q = _ehp(snaps, equiv) if len(snaps) >= 2 else None
                # config hint from spec metadata (tolerant of missing keys)
                hint = spec.get("turnover_hint")
                lt = _lt(ft["mean_turnover_pct"], hp_q, hint=hint,
                         n_pairs=ft["n_pairs"])
                # concentration and n_holdings from latest snapshot
                latest_snap = snaps[-1][2] if snaps else None
                conc = _ct10(latest_snap, equiv) if latest_snap is not None else None
                nh = _nh(latest_snap, equiv) if latest_snap is not None else None
                sc["turnover_pct"] = ft["mean_turnover_pct"]
                sc["turnover_tier"] = lt["tier"]
                sc["turnover_source"] = lt["source"]
                sc["holding_period_q"] = hp_q
                sc["concentration_pct"] = conc
                sc["n_holdings"] = nh
                # Config metadata — tolerant of missing keys (spec may be a thin dict)
                sc["style"] = spec.get("style", "unclassified")
                sc["status"] = spec.get("status", "active")
            except Exception:  # noqa: BLE001
                log.debug("manager_lag integration failed for %s", slug, exc_info=True)
        # ---- Decay chips: median since-filing SPY-excess at h21/h63/h126 per fund ----
        try:
            import statistics as _st
            buy_trades = [t for t in trades if t["action"] in _BUY]
            decay: dict[str, dict] = {}
            for h in (21, 63, 126):
                exs = [panel.excess(t["ticker"], t["filing_date"], horizon=h)
                       for t in buy_trades if t.get("filing_date")]
                vals = [e["excess"] for e in exs if e is not None]
                decay[f"h{h}"] = {"med": round(_st.median(vals), 4) if vals else None,
                                   "n": len(vals)}
            sc["decay"] = decay
        except Exception:  # noqa: BLE001
            log.debug("decay chips failed for %s", slug, exc_info=True)
        scorecards[slug] = sc
        # latest-quarter action map (for tagging current holdings) + top book
        latest_period = max((t["period_end"] for t in trades), default="")
        latest_by_tk = {t["ticker"]: t for t in trades if t["period_end"] == latest_period}
        top, period_end, filing_date, book = _top_holdings(
            slug, panel, name_map, cusip_map, latest_by_tk)
        if period_end:
            as_of_dates.append(period_end)
        if filing_date:
            filing_dates.append(filing_date)
        rot = fund_rotation(slug, name, trades, top, latest_period or period_end)
        by_fund[slug] = {
            "slug": slug, "name": name,
            "period_end": period_end, "filing_date": filing_date,
            "book_value_usd": book,
            "scorecard": sc, "rotation": rot,
        }

    if not all_trades:
        return None

    leaderboard = rank_leaderboard(scorecards)
    # pin the configured "follow closely" funds (e.g. Tepper) for the page to surface
    follow = set(tcfg.get("featured_funds", ["appaloosa"]))
    for r in leaderboard:
        r["featured"] = r["slug"] in follow

    buys = [t for t in all_trades if t["action"] in _BUY
            and t["since_excess"] is not None and t["pct_portfolio"] >= min_conv]
    best_trades = sorted(buys, key=lambda t: -t["since_excess"])[:board_n]
    worst_trades = sorted(buys, key=lambda t: t["since_excess"])[:board_n]

    featured = _featured(by_fund, leaderboard, pair)

    n_priced = sum(1 for t in all_trades if t["since_excess"] is not None)
    return {
        "as_of": max(as_of_dates) if as_of_dates else "",
        "latest_filing": max(filing_dates) if filing_dates else "",
        "built": datetime.now(timezone.utc).isoformat(),
        "note": {"en": TRACKER_NOTE, "zh": TRACKER_NOTE_ZH},
        "benchmark": BENCHMARK,
        "horizon_days": horizon,
        "coverage": {
            "funds": len(by_fund),
            "trades_scored": n_priced,
            "price_thru": panel.thru,
        },
        "featured": featured,
        "leaderboard": leaderboard,
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "by_fund": by_fund,
    }
