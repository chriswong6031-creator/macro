"""Insider Intel — role-aware + freshness-honest insider analytics for the
Smart-Money Signal Desk S1.5 "Insider intelligence" boards.

Two independent lanes, two clocks:

  QUIVER LANE  (`quiver_flow`)  — data/quiver/insiders.parquet, daily-fresh
    per-transaction feed, NO titles. Market-wide net open-market flow per
    ticker over a trailing window. Its as-of is the max transaction Date in
    the store.
  PANEL LANE   (`panel_boards`) — data/sec_insider/insider_panel.parquet, the
    point-in-time Form-4 panel WITH titles/roles, published with ~45 days of
    lag (bulk quarterly refresh). C-suite boards, officer cluster buys, and
    the insider-power 0..100 score per name. Its as-of is the max
    filing_date in the panel.

HONESTY CONTRACT
----------------
SM2-R3 (no fusion): the two lanes carry SEPARATE as-of stamps and are never
  blended numerically. `build_insider_intel` places them side by side —
  each top-net row nests a `quiver` sub-dict (with the quiver as-of) and a
  `panel` sub-dict (with the panel as-of); no key ever sums or averages
  values across lanes. The template renders each board with its own
  freshness chip ("SEC bulk panel · through {asof} · ~45d publication lag"
  vs the daily quiver as-of).

PIT LAW: panel rows enter only when `filing_date <= asof` (the date the
  trade became public) — enforced by engine.insider_power._prep, which this
  module reuses rather than re-implementing role weights.

QUIVER DATA QUALITY (the −$6.2B OLPX lesson): the collector's dedup key
  includes `fileDate` (collectors/quiver.py InsidersAdapter), so re-filed
  trades DUPLICATE in the store. quiver_flow therefore drops duplicates on
  (Ticker, Date, Name, TransactionCode, Shares) before aggregating, and
  applies per-trade sanity gates: price > 0, shares > 0, and
  trade_usd <= usd_cap (default $500m). Open-market discipline: only
  TransactionCode P/S rows count; when the column is absent the
  AcquiredDisposedCode A/D fallback is used and the payload carries the
  honesty flag `"filter": "ad_code_only"` (grants/awards may leak in —
  the flag makes that legible downstream, never hidden).

DEGRADE-NEVER-RAISE: every public function returns None (or an
  empty-but-stamped dict) on any failure, with a logged warning. The desk
  build treats an absent lane as a hidden board, never a Jinja error.

All boards are DESCRIPTIVE reads — not forecasts, not a buy list.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_QUIVER_PATH = ("quiver", "insiders.parquet")
_PANEL_PATH = ("sec_insider", "insider_panel.parquet")

# Quiver-lane defaults — overridable via config smart_money.insider_intel.*
QUIVER_WINDOW_DAYS = 90       # trailing transaction-date window
MIN_TRADE_USD = 10_000        # per-trade floor (panel-store convention)
USD_SANITY_CAP = 500_000_000  # per-trade ceiling — kills re-file/fat-finger whales
MIN_NET_USD = 100_000         # per-ticker |net| floor to bound payload size

# Panel-lane defaults
PANEL_WINDOW_DAYS = 180       # trailing filing-date window for the boards
MIN_CSUITE_USD = 250_000      # min trade $ for the C-suite boards
MIN_CLUSTER_BUYERS = 3        # distinct officer/director buyer CIKs

# Board caps (payload-size discipline)
_CSUITE_CAP = 40
_CLUSTER_CAP = 25
_SCORES_CAP = 200
_TOP_NET_CAP = 25

# Natural dedup key for re-filed quiver rows — the collector key
# (collectors/quiver.py InsidersAdapter.key_cols) MINUS fileDate, which is
# exactly what makes re-files duplicate. Missing columns are skipped so the
# ad_code_only fallback frames still dedup on what they have.
_QUIVER_DEDUP_KEY = ("Ticker", "Date", "Name", "TransactionCode", "Shares")

# Short role pill for the C-suite boards, derived from the filer title.
# Checked in order — "President & CEO" reads as CEO. Kept keyword-compatible
# with engine.insider_power._TOP_TITLE (every match here is a "top" bucket).
_SHORT_ROLE = (
    (("CHIEF EXEC", "CEO"), "CEO"),
    (("CHIEF FIN", "CFO"), "CFO"),
    (("CHIEF OPER", "COO"), "COO"),
    (("CHAIR",), "Chair"),
    (("FOUNDER",), "Founder"),
    (("PRESIDENT",), "President"),
)

_warned_ad_only = False  # log the ad_code_only degradation once per process


def _short_role(title: str) -> str:
    """Compact role pill (CEO/CFO/COO/Chair/Founder/President) from a filer
    title; falls back to the generic top-exec label."""
    up = title.upper() if isinstance(title, str) else ""
    for keys, label in _SHORT_ROLE:
        if any(k in up for k in keys):
            return label
    return "Top exec"


# --------------------------------------------------------------------------- #
# Quiver lane — daily-fresh net open-market flow                               #
# --------------------------------------------------------------------------- #

def _load_quiver() -> pd.DataFrame | None:
    """Read data/quiver/insiders.parquet; None on any failure (logged)."""
    try:
        p = config.data_dir() / _QUIVER_PATH[0] / _QUIVER_PATH[1]
        if not p.exists():
            log.warning("quiver insiders store absent at %s", p)
            return None
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        log.warning("quiver insiders read failed", exc_info=True)
        return None


def quiver_flow(window_days: int = QUIVER_WINDOW_DAYS,
                min_trade_usd: float = MIN_TRADE_USD,
                usd_cap: float = USD_SANITY_CAP,
                _df: pd.DataFrame | None = None) -> dict | None:
    """Market-wide net open-market insider flow per ticker (quiver lane).

    Pipeline: dedup re-filed rows on (Ticker, Date, Name, TransactionCode,
    Shares) → trailing `window_days` window ending at the store's max Date →
    open-market filter (TransactionCode ∈ {P, S}; AcquiredDisposedCode A/D
    fallback with the `"filter": "ad_code_only"` honesty flag when the code
    column is absent) → per-trade sanity (price > 0, shares > 0,
    min_trade_usd <= trade_usd <= usd_cap) → per-ticker aggregation, keeping
    only names with |net_usd| >= 100k.

    `_df` is an optional DataFrame override for unit tests (bypasses disk).

    Returns
    -------
    {asof, window_days, filter, by_ticker: {T: {net_usd, buy_usd, sell_usd,
     n_buys, n_sells, n_buyers, last_date}}} — n_buyers is the distinct
    buyer-Name count when the Name column exists, else None (null-honest).
    None when the store is absent/empty or unclassifiable.
    """
    global _warned_ad_only

    df = _df if _df is not None else _load_quiver()
    if df is None or df.empty:
        return None
    required = {"Ticker", "Date", "Shares", "PricePerShare"}
    missing = required - set(df.columns)
    if missing:
        log.warning("quiver insiders missing required columns: %s", missing)
        return None

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Ticker"])
    if df.empty:
        return None

    # Re-filed trades duplicate (fileDate is in the collector dedup key) —
    # collapse them on the natural trade key BEFORE any aggregation (F1).
    subset = [c for c in _QUIVER_DEDUP_KEY if c in df.columns]
    df = df.drop_duplicates(subset=subset, keep="first")

    asof = df["Date"].max()
    cutoff = asof - pd.Timedelta(days=int(window_days))
    df = df[df["Date"] >= cutoff]

    # Open-market classification — TransactionCode is authoritative when
    # present (excludes grants/awards M/A/G/F...); AcquiredDisposedCode is
    # the honesty-flagged fallback (cannot separate grants from purchases).
    if "TransactionCode" in df.columns:
        code = df["TransactionCode"].astype(str).str.strip().str.upper()
        keep = code.isin({"P", "S"})
        df = df[keep].copy()
        is_buy = code[keep] == "P"
        filt = "open_market_ps"
    elif "AcquiredDisposedCode" in df.columns:
        ad = df["AcquiredDisposedCode"].astype(str).str.strip().str.upper()
        keep = ad.isin({"A", "D"})
        df = df[keep].copy()
        is_buy = ad[keep] == "A"
        filt = "ad_code_only"
        if not _warned_ad_only:
            log.warning("quiver insiders lack TransactionCode — falling back "
                        "to AcquiredDisposedCode (grants may count as buys); "
                        "payload flagged filter=ad_code_only")
            _warned_ad_only = True
    else:
        log.warning("quiver insiders lack both TransactionCode and "
                    "AcquiredDisposedCode — cannot classify trades")
        return None

    df["_is_buy"] = is_buy
    shares = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
    price = pd.to_numeric(df["PricePerShare"], errors="coerce").fillna(0.0)
    df["_trade_usd"] = shares * price
    # Per-trade sanity gates: positive price/shares, floor, and the whale cap
    # (a single $600m "trade" is a re-file/decimal artifact, not a signal).
    df = df[(shares > 0) & (price > 0)
            & (df["_trade_usd"] >= float(min_trade_usd))
            & (df["_trade_usd"] <= float(usd_cap))]

    asof_str = str(pd.Timestamp(asof).date())
    has_name = "Name" in df.columns
    by_ticker: dict[str, dict] = {}
    for ticker, g in df.groupby("Ticker", sort=False):
        buys = g[g["_is_buy"]]
        sells = g[~g["_is_buy"]]
        buy_usd = float(buys["_trade_usd"].sum())
        sell_usd = float(sells["_trade_usd"].sum())
        net_usd = buy_usd - sell_usd
        if abs(net_usd) < MIN_NET_USD:
            continue
        by_ticker[str(ticker)] = {
            "net_usd": round(net_usd, 0),
            "buy_usd": round(buy_usd, 0),
            "sell_usd": round(sell_usd, 0),
            "n_buys": int(len(buys)),
            "n_sells": int(len(sells)),
            "n_buyers": int(buys["Name"].nunique()) if has_name else None,
            "last_date": str(pd.Timestamp(g["Date"].max()).date()),
        }

    return {
        "asof": asof_str,
        "window_days": int(window_days),
        "filter": filt,
        "by_ticker": by_ticker,
    }


# --------------------------------------------------------------------------- #
# Panel lane — role-aware boards from the point-in-time Form-4 panel           #
# --------------------------------------------------------------------------- #

def _load_panel() -> pd.DataFrame | None:
    """Read data/sec_insider/insider_panel.parquet; None on failure (logged).

    Tries the column subset the boards need first (the panel is ~2.3M rows);
    falls back to a full read when the store predates a column.
    """
    cols = ["ticker", "filing_date", "trans_date", "rptownercik", "code",
            "is_officer", "is_director", "is_tenpct", "title",
            "shares", "price", "usd"]
    try:
        p = config.data_dir() / _PANEL_PATH[0] / _PANEL_PATH[1]
        if not p.exists():
            log.warning("sec_insider panel absent at %s", p)
            return None
        try:
            return pd.read_parquet(p, columns=cols)
        except Exception:  # noqa: BLE001 — schema drift: take whatever is there
            return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        log.warning("sec_insider panel read failed", exc_info=True)
        return None


def panel_boards(window_days: int = PANEL_WINDOW_DAYS,
                 asof: pd.Timestamp | str | None = None,
                 min_csuite_usd: float = MIN_CSUITE_USD,
                 min_cluster_buyers: int = MIN_CLUSTER_BUYERS,
                 extra_tickers: list[str] | None = None,
                 _df: pd.DataFrame | None = None) -> dict | None:
    """Role-aware insider boards from the SEC Form-4 panel (panel lane).

    Reuses engine.insider_power._prep for the causal slice (filing_date <=
    asof — the PIT gate), the open-market P/S re-filter (the collector
    already guarantees P/S; _prep re-asserts it defensively), and the role
    bucketing (top-exec / officer / director / 10% / other).

    `asof` defaults to the panel's max filing_date — the honest lane clock
    (the store refreshes in bulk with ~45d publication lag; the desk chips
    render "through {asof}"). `window_days` is effectively bounded by the
    insider_power series window (~24 months). `extra_tickers` extends the
    score universe (e.g. the quiver top-net names) so the desk can show the
    panel score NEXT TO quiver flow — side by side, never blended.
    `_df` is an optional DataFrame override for unit tests.

    Returns
    -------
    {asof, window_days,
     csuite_buys:  [{ticker, role_label, title, usd, shares, price,
                     trans_date, filing_date}...]  (code P, role bucket
                    "top", usd >= min_csuite_usd, ranked usd desc, cap 40),
     csuite_sells: [... same for code S, cap 40],
     cluster_buys: [{ticker, n_officer_buyers, buy_usd, last_date}...]
                    (>= min_cluster_buyers distinct officer/director buyer
                    CIKs, cap 25),
     scores: {T: {score, signal, confidence}}}   (insider_power.compute over
                    the union of board + extra tickers, cap 200)
    None when the panel or insider_power is unavailable.
    """
    try:
        from engine import insider_power as ip
    except Exception:  # noqa: BLE001
        log.warning("insider_power import failed — panel lane unavailable",
                    exc_info=True)
        return None

    panel = _df.copy() if _df is not None else _load_panel()
    if panel is None or panel.empty:
        return None
    if "filing_date" not in panel.columns or "code" not in panel.columns:
        log.warning("sec_insider panel missing filing_date/code — panel lane "
                    "unavailable")
        return None

    panel["filing_date"] = pd.to_datetime(panel["filing_date"], errors="coerce")
    panel = panel.dropna(subset=["filing_date"])
    if panel.empty:
        return None
    asof_ts = pd.Timestamp(asof) if asof is not None else panel["filing_date"].max()

    try:
        p = ip._prep(panel, asof_ts)
    except Exception:  # noqa: BLE001
        log.warning("insider_power._prep failed — panel lane unavailable",
                    exc_info=True)
        return None

    out = {
        "asof": str(pd.Timestamp(asof_ts).date()),
        "window_days": int(window_days),
        "csuite_buys": [],
        "csuite_sells": [],
        "cluster_buys": [],
        "scores": {},
    }
    if p.empty:
        return out  # honest empty — asof still renders the freshness chip

    lo = asof_ts - pd.Timedelta(days=int(window_days))
    win = p[p["filing_date"] > lo]
    if win.empty:
        return out
    if "trans_date" not in win.columns:
        win = win.copy()
        win["trans_date"] = pd.NaT

    def _csuite_rows(side: pd.DataFrame) -> list[dict]:
        rows: list[dict] = []
        for r in side.itertuples(index=False):
            title = r.title if isinstance(r.title, str) and r.title.strip() else ""
            rows.append({
                "ticker": str(r.ticker),
                "role_label": _short_role(title),
                "title": title or "Top exec",
                "usd": None if pd.isna(r.usd) else round(float(r.usd), 2),
                "shares": None if pd.isna(r.shares) else float(r.shares),
                "price": None if pd.isna(r.price) else round(float(r.price), 4),
                "trans_date": (pd.Timestamp(r.trans_date).strftime("%Y-%m-%d")
                               if pd.notna(r.trans_date) else None),
                "filing_date": pd.Timestamp(r.filing_date).strftime("%Y-%m-%d"),
            })
        return rows

    # C-suite boards: role bucket "top" (CEO/CFO/President/Chair/…), open-
    # market only (P buys / S sells), sized at min_csuite_usd or better.
    cs = win[win["role"] == "top"]
    usd_num = pd.to_numeric(cs["usd"], errors="coerce")
    sized = cs[usd_num >= float(min_csuite_usd)]
    out["csuite_buys"] = _csuite_rows(
        sized[sized["code"] == "P"].sort_values("usd", ascending=False)
        .head(_CSUITE_CAP))
    out["csuite_sells"] = _csuite_rows(
        sized[sized["code"] == "S"].sort_values("usd", ascending=False)
        .head(_CSUITE_CAP))

    # Cluster buys: >= min_cluster_buyers DISTINCT officer/director buyer
    # CIKs in the window — breadth of informed buying, not one big ticket.
    if "rptownercik" in win.columns:
        cb = win[win["code"] == "P"]
        informed = (cb["is_officer"].fillna(False).astype(bool)
                    | cb["is_director"].fillna(False).astype(bool))
        cb = cb[informed]
        clusters: list[dict] = []
        for ticker, g in cb.groupby("ticker", sort=False):
            n = int(g["rptownercik"].nunique())
            if n < int(min_cluster_buyers):
                continue
            clusters.append({
                "ticker": str(ticker),
                "n_officer_buyers": n,
                "buy_usd": round(float(pd.to_numeric(g["usd"], errors="coerce")
                                       .fillna(0.0).sum()), 2),
                "last_date": str(pd.Timestamp(g["filing_date"].max()).date()),
            })
        clusters.sort(key=lambda r: (r["n_officer_buyers"], r["buy_usd"]),
                      reverse=True)
        out["cluster_buys"] = clusters[:_CLUSTER_CAP]
    else:
        log.warning("sec_insider panel lacks rptownercik — cluster board "
                    "unavailable")

    # Insider-power scores for every board name (+ requested extras), capped.
    board_tickers = ([r["ticker"] for r in out["csuite_buys"]]
                     + [r["ticker"] for r in out["csuite_sells"]]
                     + [r["ticker"] for r in out["cluster_buys"]]
                     + [str(t) for t in (extra_tickers or [])])
    uniq = list(dict.fromkeys(board_tickers))[:_SCORES_CAP]
    if uniq:
        try:
            full = ip.compute(panel, asof=asof_ts, tickers=uniq)
            out["scores"] = {
                t: {"score": v.get("score"), "signal": v.get("signal"),
                    "confidence": v.get("confidence")}
                for t, v in full.items()
            }
        except Exception:  # noqa: BLE001
            log.warning("insider_power.compute failed — panel scores "
                        "unavailable", exc_info=True)

    return out


# --------------------------------------------------------------------------- #
# Orchestrator — two lanes side by side, never blended                         #
# --------------------------------------------------------------------------- #

def build_insider_intel(cfg: dict | None,
                        roster: set[str] | None = None) -> dict | None:
    """Assemble the S1.5 insider-intelligence payload from both lanes.

    Parameters
    ----------
    cfg : the `smart_money` config section; knobs read with .get() defaults
        from `cfg["insider_intel"]` (quiver_window_days, min_trade_usd,
        usd_sanity_cap, panel_window_days, min_csuite_usd,
        min_cluster_buyers, top_net_n) — absent config never breaks.
    roster : set of tickers currently held by tracked funds (caller-supplied;
        this module never reaches into the 13F store). None → no hits.

    Returns
    -------
    {quiver: quiver_flow() | None,
     panel: panel_boards() | None,
     top_net_buys:  [{ticker, quiver: {net_usd, buy_usd, sell_usd, n_buys,
                      n_sells, n_buyers, last_date, asof}, panel: {score,
                      signal, confidence, asof} | None, roster_hit}...],
     top_net_sells: [... most-negative first ...]}

    SM2-R3: each row's `quiver` sub-dict carries the quiver as-of and each
    `panel` sub-dict the panel as-of; quiver dollars and panel scores are
    NEVER combined into one figure — display side by side only.
    None when both lanes are unavailable.
    """
    ii_cfg = (cfg or {}).get("insider_intel", {}) or {}
    q_window = int(ii_cfg.get("quiver_window_days", QUIVER_WINDOW_DAYS))
    min_trade = float(ii_cfg.get("min_trade_usd", MIN_TRADE_USD))
    usd_cap = float(ii_cfg.get("usd_sanity_cap", USD_SANITY_CAP))
    p_window = int(ii_cfg.get("panel_window_days", PANEL_WINDOW_DAYS))
    min_csuite = float(ii_cfg.get("min_csuite_usd", MIN_CSUITE_USD))
    min_cluster = int(ii_cfg.get("min_cluster_buyers", MIN_CLUSTER_BUYERS))
    top_n = int(ii_cfg.get("top_net_n", _TOP_NET_CAP))

    quiver = None
    try:
        quiver = quiver_flow(window_days=q_window, min_trade_usd=min_trade,
                             usd_cap=usd_cap)
    except Exception:  # noqa: BLE001
        log.warning("quiver_flow failed — quiver lane unavailable",
                    exc_info=True)

    # Rank the quiver lane BEFORE the panel call so the panel lane can score
    # the top-net names too (side-by-side enrichment, never a blend).
    ranked_buys: list[tuple[str, dict]] = []
    ranked_sells: list[tuple[str, dict]] = []
    if quiver and quiver.get("by_ticker"):
        items = list(quiver["by_ticker"].items())
        pos = [(t, m) for t, m in items if (m.get("net_usd") or 0) > 0]
        neg = [(t, m) for t, m in items if (m.get("net_usd") or 0) < 0]
        ranked_buys = sorted(pos, key=lambda kv: kv[1].get("net_usd") or 0.0,
                             reverse=True)[:top_n]
        ranked_sells = sorted(neg,
                              key=lambda kv: kv[1].get("net_usd") or 0.0)[:top_n]

    extra = [t for t, _ in ranked_buys] + [t for t, _ in ranked_sells]
    panel = None
    try:
        panel = panel_boards(window_days=p_window,
                             min_csuite_usd=min_csuite,
                             min_cluster_buyers=min_cluster,
                             extra_tickers=extra or None)
    except Exception:  # noqa: BLE001
        log.warning("panel_boards failed — panel lane unavailable",
                    exc_info=True)

    if quiver is None and panel is None:
        return None

    roster = roster or set()
    scores = (panel or {}).get("scores", {}) or {}
    panel_asof = (panel or {}).get("asof")
    q_asof = (quiver or {}).get("asof")

    def _net_row(ticker: str, metrics: dict) -> dict:
        q_sub = dict(metrics)
        q_sub["asof"] = q_asof            # quiver clock, on the quiver dict
        ps = scores.get(ticker)
        p_sub = None
        if ps:
            p_sub = {"score": ps.get("score"), "signal": ps.get("signal"),
                     "confidence": ps.get("confidence"),
                     "asof": panel_asof}  # panel clock, on the panel dict
        return {"ticker": ticker, "quiver": q_sub, "panel": p_sub,
                "roster_hit": bool(ticker in roster)}

    return {
        "quiver": quiver,
        "panel": panel,
        "top_net_buys": [_net_row(t, m) for t, m in ranked_buys],
        "top_net_sells": [_net_row(t, m) for t, m in ranked_sells],
    }
