"""Manager-Quality Score — the keystone that turns curated-13F CONTEXT into an
edge-aware read: backtest each tracked fund's PREDICTIVENESS so a skilled filer's
add outweighs a mediocre one's.

For every consecutive quarter pair we replay the fund's new/add/trim/exit actions
and measure the forward return from the **public filing date** (look-ahead-free —
`engine.smart_money.accumulation_trend` / `available_on` doctrine), over a fixed
horizon:
  * buy skill  = mean forward return on new/add
  * sell skill = mean NEGATIVE forward return on trim/exit (a good sell dodges a drop)
A fund's quality = the blend, z-scored cross-sectionally into a grade.

HONESTY: with only a handful of retained quarters and ~1y of prices this is
**descriptive, low-confidence CONTEXT** — it quality-WEIGHTS the smart-money panel
and flags high-quality clustering; it is NEVER fed into a scored allocation. It
deepens automatically as snapshots + price history accrue. Lessons baked in from
research/OWNERSHIP_SIGNALS_CASE_STUDY_REVIEW.md: filing-date entries, completed
horizon only, min-event gate, no single-cycle promotion.
"""
from __future__ import annotations

import logging

import pandas as pd

from engine.smart_money import (_read_all, diff_snapshots, full_cusip_map,
                                 name_ticker_map, resolve_tickers)
from lib import config

log = logging.getLogger(__name__)

DEFAULT_HORIZON = 63          # ~one quarter of trading days (the 13F hold cadence)
MIN_EVENTS = 8                # below this a fund's quality is "n/a" (insufficient)
_BUY = {"new", "add"}
_SELL = {"trim", "exit"}


def load_closes() -> pd.DataFrame | None:
    """Combined date×ticker close panel from the breadth caches. None if absent
    (caller degrades to an empty quality map)."""
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
    closes = pd.concat(frames, axis=1)
    closes = closes.loc[:, ~closes.columns.duplicated()]
    closes.index = pd.to_datetime(closes.index)
    return closes.sort_index()


def forward_return(closes: pd.DataFrame, ticker: str, entry: str,
                   horizon: int = DEFAULT_HORIZON) -> float | None:
    """Return from the first trading day on/after `entry` to `horizon` sessions
    later. None if the ticker is absent or the full horizon hasn't elapsed yet
    (so we never score an unfinished window). PURE."""
    if ticker not in closes.columns:
        return None
    s = closes[ticker].dropna()
    if s.empty:
        return None
    e = pd.Timestamp(entry)
    after = s.index[s.index >= e]
    if len(after) == 0:
        return None
    pos = s.index.get_loc(after[0])
    if pos + horizon >= len(s):          # horizon not fully elapsed -> skip
        return None
    p0, p1 = float(s.iloc[pos]), float(s.iloc[pos + horizon])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def market_forward_return(closes: pd.DataFrame, entry: str, horizon: int,
                          _cache: dict | None = None) -> float | None:
    """Equal-weight mean forward return across the whole close universe over the
    same window — the broad-market beta we subtract so skill measures SELECTION,
    not a rising tide (the case-study 'control for the dominant beta' lesson).
    Memoized per (entry, horizon)."""
    key = (entry, horizon)
    if _cache is not None and key in _cache:
        return _cache[key]
    e = pd.Timestamp(entry)
    after = closes.index[closes.index >= e]
    val = None
    if len(after):
        pos = closes.index.get_loc(after[0])
        if pos + horizon < len(closes):
            p0 = closes.iloc[pos]
            p1 = closes.iloc[pos + horizon]
            rets = (p1 / p0 - 1.0).replace([float("inf"), float("-inf")], pd.NA).dropna()
            if len(rets):
                val = float(rets.mean())
    if _cache is not None:
        _cache[key] = val
    return val


def _fund_skill(slug: str, closes: pd.DataFrame, name_map, cusip_map,
                horizon: int, mkt_cache: dict) -> dict:
    """Replay one fund's action history → {buys[], sells[]} of MARKET-RELATIVE
    forward returns (excess over the equal-weight universe)."""
    snaps = _read_all(slug)              # (period_end, filing_date, df) ascending
    buys, sells = [], []
    for i in range(len(snaps) - 1):
        _pe_prev, _fd_prev, prev = snaps[i]
        _pe_cur, fd_cur, cur = snaps[i + 1]
        if not fd_cur:                   # no public date -> can't place a look-ahead-free entry
            continue
        bench = market_forward_return(closes, fd_cur, horizon, mkt_cache)
        if bench is None:                # window not complete -> skip the whole quarter
            continue
        diff = diff_snapshots(prev, cur)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        diff = diff[diff["ticker"].notna()]
        for r in diff.itertuples(index=False):
            ret = forward_return(closes, r.ticker, fd_cur, horizon)
            if ret is None:
                continue
            excess = ret - bench         # selection, not beta
            if r.action in _BUY:
                buys.append(excess)
            elif r.action in _SELL:
                sells.append(-excess)    # a good sell precedes UNDER-performance -> positive skill
    return {"buys": buys, "sells": sells}


def _blend(buys: list[float], sells: list[float]) -> float | None:
    b = sum(buys) / len(buys) if buys else None
    s = sum(sells) / len(sells) if sells else None
    if b is not None and s is not None:
        return 0.5 * b + 0.5 * s
    return b if b is not None else s


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


def compute_manager_quality(cfg: dict | None = None, *, horizon: int = DEFAULT_HORIZON,
                            min_events: int = MIN_EVENTS) -> dict:
    """{slug: {quality_z, quality_raw, buy_skill, sell_skill, n_events, n_buys,
    n_sells, grade, horizon, confidence}}. Empty if no prices/snapshots.
    `quality_z` is cross-sectional over funds clearing `min_events`; funds below
    the gate get grade 'n/a' and no z (descriptive-insufficient)."""
    cfg = cfg if cfg is not None else (config.load().get("smart_money", {}) or {})
    funds = cfg.get("funds", {}) or {}
    closes = load_closes()
    if not funds or closes is None or closes.empty:
        return {}
    name_map = name_ticker_map()
    cusip_map, _ = full_cusip_map()
    mkt_cache: dict = {}                  # memoized market benchmark per (date, horizon)

    raw: dict[str, dict] = {}
    for slug in funds:
        sk = _fund_skill(slug, closes, name_map, cusip_map, horizon, mkt_cache)
        n = len(sk["buys"]) + len(sk["sells"])
        raw[slug] = {
            "buy_skill": round(sum(sk["buys"]) / len(sk["buys"]), 4) if sk["buys"] else None,
            "sell_skill": round(sum(sk["sells"]) / len(sk["sells"]), 4) if sk["sells"] else None,
            "quality_raw": _blend(sk["buys"], sk["sells"]),
            "n_events": n, "n_buys": len(sk["buys"]), "n_sells": len(sk["sells"]),
        }

    # cross-sectional z over funds that clear the event gate
    eligible = {s: r["quality_raw"] for s, r in raw.items()
                if r["n_events"] >= min_events and r["quality_raw"] is not None}
    vals = list(eligible.values())
    if len(vals) >= 3:
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        sd = var ** 0.5
    else:
        mu, sd = 0.0, 0.0

    out: dict[str, dict] = {}
    for slug, r in raw.items():
        qz = None
        if slug in eligible and sd > 0:
            qz = round((eligible[slug] - mu) / sd, 2)
        out[slug] = {
            **r,
            "quality_raw": round(r["quality_raw"], 4) if r["quality_raw"] is not None else None,
            "quality_z": qz,
            "grade": _grade(qz),
            "horizon": horizon,
            "confidence": "descriptive",   # low-N, never a scored alpha
        }
    n_graded = sum(1 for v in out.values() if v["grade"] != "n/a")
    log.info("manager_quality: %d funds, %d graded (>=%d events), horizon %dd",
             len(out), n_graded, min_events, horizon)
    return out
