"""Per-theme institutional flow rollup — scorecard dimension 3 (DISPLAY-ONLY).

directional=False: this module aggregates ETF holdings-change signals (conviction_pp,
accumulating/trimming labels) per thematic basket to expose WHERE institutional money
is moving across themes — NOT to predict forward returns.

The "A4 tell" from the doctrine: *flow reversing while price holds* (divergence=True)
is a qualitative warning, never a scored signal. All values are trailing-truth snapshots
of actual reported fund holdings, updated at the cadence of the upstream ETF snapshot
collector (typically 1-5 day lag).

Data access mirrors engine.holdings_signals.all_etf_signals() exactly:
  - reads data/etf_holdings/<ETF>/*.parquet via etf_signals()
  - reads data/holdings/<ARK_FUND>/*.parquet via etf_signals(is_active=True)
  - maps each ticker to its theme basket via engine.group_flow._setup()

Public API:
    theme_flow(region='us') -> dict[theme_id, ThemeFlowResult]

    ThemeFlowResult = {
        "flow_score":       float | None,   # mean conviction_pp across covered members
        "accumulating_pct": float | None,   # % of covered members being accumulated
        "divergence":       bool,           # flow_score<0 while basket rel-price flat/up
        "n_covered":        int,            # how many basket members have holdings data
        "n_members":        int,            # total basket members (active on last date)
        "flow_label":       str,            # "accumulating" / "distributing" / "mixed" / "n/a"
    }

Coverage is sparse by design: only tickers held by the configured ETF universe
(data/etf_holdings) and the active watchlist (data/holdings) appear.  When n_covered
is low the caller should treat flow_score and accumulating_pct as unreliable context,
not a view.
"""
from __future__ import annotations

import logging
from typing import TypedDict

import pandas as pd

from engine import group_flow
from engine.holdings_signals import all_etf_signals

log = logging.getLogger(__name__)

# Minimum fraction of basket members that must have holdings coverage before
# we emit a flow_score / accumulating_pct (rather than None / n/a).
_MIN_COVERED_FRAC = 0.10   # 10% coverage threshold — intentionally permissive


class ThemeFlowResult(TypedDict):
    flow_score: float | None        # mean conviction_pp (pp of fund weight); negative = net trimming
    accumulating_pct: float | None  # 0-1 fraction of covered members being accumulated
    divergence: bool                # flow negative while basket rel-price flat/up (the A4 tell)
    n_covered: int                  # members with ETF holdings data
    n_members: int                  # total basket members active on last date
    flow_label: str                 # "accumulating" / "distributing" / "mixed" / "n/a"


def _build_ticker_flow_map(signals: list[dict]) -> dict[str, list[float]]:
    """Aggregate conviction_pp values per ticker across all ETF signals.

    A single ticker may appear in multiple ETF snapshots — e.g. NVDA held by
    both ARKK and SMH.  We collect ALL conviction_pp readings so the rollup
    reflects the breadth of institutional interest, not just the loudest fund.
    """
    tmap: dict[str, list[float]] = {}
    for row in signals:
        tk = row.get("ticker")
        pp = row.get("conviction_pp")
        if tk and pp is not None:
            try:
                val = float(pp)
            except (TypeError, ValueError):
                continue
            tmap.setdefault(str(tk).upper(), []).append(val)
    return tmap


def _basket_rel_perf(lvl: pd.Series, bench: pd.Series, window: int = 5) -> float | None:
    """Trailing `window`-day relative return of the basket level vs benchmark.

    Returns None when the series is too short.  Positive = basket beat benchmark
    recently (price holding / rising relative to SPY).
    """
    if len(lvl) < window + 1 or len(bench) < window + 1:
        return None
    try:
        lv0, lv1 = lvl.iloc[-(window + 1)], lvl.iloc[-1]
        bv0, bv1 = bench.iloc[-(window + 1)], bench.iloc[-1]
        if any(pd.isna(x) or x == 0 for x in (lv0, lv1, bv0, bv1)):
            return None
        return float((lv1 / lv0 - 1.0) - (bv1 / bv0 - 1.0))
    except Exception:  # noqa: BLE001
        return None


def _flow_label(flow_score: float | None, accumulating_pct: float | None) -> str:
    if flow_score is None:
        return "n/a"
    if accumulating_pct is not None and accumulating_pct >= 0.60:
        return "accumulating"
    if accumulating_pct is not None and accumulating_pct <= 0.35:
        return "distributing"
    return "mixed"


def theme_flow(region: str = "us") -> dict[str, ThemeFlowResult]:
    """Per-theme institutional flow rollup from ETF holdings-change signals.

    For each basket in the region's membership:
      - maps basket members to their ETF-holdings conviction_pp (mean over all
        ETFs holding that ticker)
      - aggregates to a theme-level flow_score and accumulating_pct
      - sets divergence=True when flow is net negative while recent relative
        price is flat or positive (the A4 tell)

    Returns an empty dict on any critical failure — never raises.
    directional=False: display-only, not a scored forward-return signal.
    """
    result: dict[str, ThemeFlowResult] = {}

    # 1. Pull the live setup (membership + closes + bench) — mirrors theme_scoring.py
    try:
        s = group_flow._setup(region)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_flow: _setup(%s) failed: %s", region, exc)
        return result
    if s is None:
        return result

    mem = s["mem"]
    rets = s["rets"]
    bench = s["bench"]
    idx = s["idx"]

    # 2. Fetch all ETF holdings signals once — the expensive network/disk read
    try:
        signals = all_etf_signals()
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_flow: all_etf_signals() failed: %s", exc)
        signals = []

    ticker_flow = _build_ticker_flow_map(signals)

    # 3. Enumerate baskets (same iteration pattern as theme_scoring.compute_theme_intel)
    bdict = mem.get("baskets", {})
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]

    for bid, b in items:
        members = b.get("members", [])

        # Active members on the last available date (PIT — honour added/removed)
        last_date = idx[-1] if len(idx) else None
        active_tickers: list[str] = []
        for m in members:
            tk = m.get("ticker", "")
            if not tk or tk not in rets.columns:
                continue
            try:
                added = pd.Timestamp(m["added"])
                removed = pd.Timestamp(m["removed"]) if m.get("removed") else None
            except Exception:  # noqa: BLE001
                continue
            if last_date is None or last_date < added:
                continue
            if removed is not None and last_date >= removed:
                continue
            active_tickers.append(tk)

        n_members = len(active_tickers)

        # Coverage: which active members appear in the ETF flow map?
        covered = [tk for tk in active_tickers if tk.upper() in ticker_flow]
        n_covered = len(covered)

        # Below the minimum coverage threshold: surface counts but keep scores None
        min_needed = max(1, int(round(n_members * _MIN_COVERED_FRAC)))
        if n_covered < min_needed:
            result[str(bid)] = ThemeFlowResult(
                flow_score=None,
                accumulating_pct=None,
                divergence=False,
                n_covered=n_covered,
                n_members=n_members,
                flow_label="n/a",
            )
            continue

        # Per-ticker: mean conviction_pp across all ETFs holding that ticker
        per_ticker_pp: list[float] = []
        acc_count = 0
        for tk in covered:
            pp_vals = ticker_flow[tk.upper()]
            mean_pp = sum(pp_vals) / len(pp_vals)
            per_ticker_pp.append(mean_pp)
            if mean_pp > 0:
                acc_count += 1

        flow_score = round(sum(per_ticker_pp) / len(per_ticker_pp), 4)
        accumulating_pct = round(acc_count / n_covered, 4)

        # Divergence: net outflow while basket relative price is flat or positive
        from engine.baskets import _ew_level
        lvl = _ew_level(rets, members, idx)
        rel_ret = _basket_rel_perf(lvl, bench, window=5)
        # rel_ret >= 0 => flat/up vs benchmark; flow_score < 0 => net outflow
        divergence = bool(flow_score < 0 and rel_ret is not None and rel_ret >= -0.001)

        result[str(bid)] = ThemeFlowResult(
            flow_score=flow_score,
            accumulating_pct=accumulating_pct,
            divergence=divergence,
            n_covered=n_covered,
            n_members=n_members,
            flow_label=_flow_label(flow_score, accumulating_pct),
        )

    return result
