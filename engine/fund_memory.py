"""4-quarter fund memory engine — SM4-R2 (display-tier only).

Generalises the Grade-A methodology (scripts/research/smart_money_grade_a_q1_2026.py)
across the last 4 COMPLETED quarters × ALL tracked funds.

Methodology (mirrors the Grade-A script exactly):
  * buys = action in ("new", "add")  (SH-type rows; resolved ticker required)
  * inclusion filter: ticker is not null  (title_class / non-common filter omitted
    here — the 13F snapshots in data/smart_money/ are already share-type SH rows
    so non-common securities are mostly absent; caller can pre-filter if needed)
  * incremental_book_pct weight:
      new → pct_portfolio
      add → pct_portfolio × shares_change_pct / (100 + shares_change_pct)
  * decision-weighted 60-calendar-day return vs SPY (entry = anchor, exit = anchor+60)
  * horizon = 60 calendar days (rolled forward to next trading close present in panel)
  * anchor = period_end + 45 calendar days, snapped forward to next date in close panel
    CAVEAT: the common deadline anchor is optimistic for late/delinquent filers and
    after-close acceptances (their filing became public after the anchor). The Grade-A
    script bounded this with an acceptanceDateTime sensitivity; this engine does not —
    per SM4-R2 the deadline-cluster anchor is the ruling, so the bias is disclosed
    here and in the JSON note rather than corrected.
  * unsettled: exit date > price_thru → all that quarter's fields null

NEVER-BREAK: compute_memory() never raises; returns {} on any error.

UNITS: all excess/hit fields are DECIMAL FRACTIONS (0.042 = +4.2pp).
The template multiplies by 100 for display.

AXIS PURITY (SM2-R3): 13F axis only. No blending with insider/short-interest data.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

log = logging.getLogger(__name__)

HORIZON_DAYS = 60        # calendar days
ANCHOR_OFFSET_DAYS = 45  # period_end + 45 → anchor
BENCHMARK = "SPY"

# Minimum weight for a row to count inside the weighted average. Zero-weight rows
# still count toward n_priced/hit_60d (they are real priced positions); this floor
# only keeps them out of the weighted-mean denominator.
_MIN_INC_PCT = 1e-9


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _at_or_after(series: pd.Series, date: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """First (date, price) in series on or after `date`, or None."""
    eligible = series.index[series.index >= date]
    if len(eligible) == 0:
        return None
    actual = eligible[0]
    return actual, float(series.loc[actual])


def _weighted_average(values: pd.Series, weights: pd.Series) -> float | None:
    """Incremental-book-pct-weighted average of `values`. Returns None if no valid rows."""
    mask = values.notna() & weights.notna() & (weights > _MIN_INC_PCT)
    if not mask.any():
        return None
    num = float((values[mask] * weights[mask]).sum())
    den = float(weights[mask].sum())
    if den == 0:
        return None
    return num / den


def _select_last_n_quarters(periods: list[str], n: int = 4) -> list[str]:
    """Return the last `n` period_end strings from a sorted list."""
    if not periods:
        return []
    sorted_p = sorted(periods)
    return sorted_p[-n:]


# ---------------------------------------------------------------------------
# Close-panel price loader (reuses fund_followability's _default_price_loader)
# ---------------------------------------------------------------------------

def _make_price_loader(data_root: Path | None = None,
                       price_loader: Callable[[str], pd.Series | None] | None = None,
                       ) -> Callable[[str], pd.Series | None]:
    """Return a callable(ticker) -> Series|None using the local yahoo close panel."""
    if price_loader is not None:
        return price_loader
    from engine.fund_followability import _default_price_loader
    if data_root is not None:
        def _loader(ticker: str, _root=data_root) -> pd.Series | None:
            return _default_price_loader(ticker, _root)
        return _loader
    return _default_price_loader


# ---------------------------------------------------------------------------
# Core quarterly computation for one (fund, quarter) pair
# ---------------------------------------------------------------------------

def _quarter_result(
    slug: str,
    period_end: str,
    prev_df: pd.DataFrame | None,
    cur_df: pd.DataFrame,
    anchor: pd.Timestamp,
    spy_series: pd.Series,
    price_thru: pd.Timestamp,
    price_loader: Callable[[str], pd.Series | None],
    price_cache: dict[str, pd.Series | None],
) -> dict:
    """Compute per-(fund, quarter) metrics.

    Returns a dict with all schema fields; any field may be null.
    """
    base: dict = {
        "period_end": period_end,
        "anchor": anchor.date().isoformat(),
        "n_priced": 0,
        "dw_excess_60d": None,
        "new_dw_excess_60d": None,
        "add_dw_excess_60d": None,
        "hit_60d": None,
        "rank": None,
        "n_cohort": 0,
        "beat": None,
    }

    # SPY entry and exit (exit = first close on/after anchor + HORIZON_DAYS)
    spy_entry = _at_or_after(spy_series, anchor)
    if spy_entry is None:
        return base  # anchor is after all SPY data

    exit_target = anchor + pd.Timedelta(days=HORIZON_DAYS)

    # Check settlement: if exit_target > price_thru → unsettled window
    if exit_target > price_thru + pd.Timedelta(days=1):
        # window not yet closed — all fields null
        return base

    spy_exit = _at_or_after(spy_series, exit_target)
    if spy_exit is None:
        return base  # SPY price missing for exit date

    spy_p0 = spy_entry[1]
    spy_p1 = spy_exit[1]
    if spy_p0 <= 0:
        return base

    # Build diff: classify positions vs prior quarter
    from engine.smart_money import diff_snapshots, resolve_tickers, name_ticker_map, full_cusip_map

    try:
        diff = diff_snapshots(prev_df, cur_df)
    except Exception:  # noqa: BLE001
        return base

    if diff.empty:
        return base

    # Resolve tickers (best-effort; rows without ticker are dropped below)
    if "ticker" not in diff.columns:
        try:
            name_map = name_ticker_map()
            cusip_map, _ = full_cusip_map()
            diff = resolve_tickers(diff, name_map, cusip_map)
        except Exception:  # noqa: BLE001
            return base

    # Filter to buys with resolved tickers
    buys = diff[diff["action"].isin(["new", "add"]) & diff["ticker"].notna()].copy()
    if buys.empty:
        return base

    # Compute incremental_book_pct weight (mirrors Grade-A script exactly)
    buys["incremental_book_pct"] = buys["pct_portfolio"]
    add_mask = buys["action"] == "add"
    if add_mask.any():
        delta = buys.loc[add_mask, "shares_change_pct"].astype(float)
        # For "add": incremental = pct_portfolio * delta / (100 + delta)
        # Guard against zero/negative denominator
        denom = 100.0 + delta
        valid = denom.abs() > 1e-6
        buys.loc[add_mask & valid, "incremental_book_pct"] = (
            buys.loc[add_mask & valid, "pct_portfolio"] * delta[valid] / denom[valid]
        )
        # Where denominator invalid → use full pct_portfolio (degenerate case)

    # Collapse duplicate tickers (same as Grade-A script: sum incremental_book_pct)
    grouped = (buys.groupby("ticker", sort=False)
               .agg(
                   action=("action", lambda x: x.iloc[0] if x.nunique() == 1 else "mixed"),
                   incremental_book_pct=("incremental_book_pct", "sum"),
                   pct_portfolio=("pct_portfolio", "sum"),
               )
               .reset_index())

    # Price each ticker
    excesses: list[float] = []
    weights: list[float] = []
    actions_priced: list[str] = []
    new_exc: list[float] = []
    new_wts: list[float] = []
    add_exc: list[float] = []
    add_wts: list[float] = []

    for _, row in grouped.iterrows():
        ticker = str(row["ticker"])
        inc_pct = float(row["incremental_book_pct"])
        action = str(row["action"])

        if ticker not in price_cache:
            price_cache[ticker] = price_loader(ticker)
        series = price_cache[ticker]

        if series is None or len(series) == 0:
            continue

        entry_hit = _at_or_after(series, anchor)
        if entry_hit is None:
            continue
        exit_hit = _at_or_after(series, exit_target)
        if exit_hit is None:
            continue

        p0 = entry_hit[1]
        p1 = exit_hit[1]
        if p0 <= 0:
            continue

        stock_ret = p1 / p0 - 1.0
        spy_ret = spy_p1 / spy_p0 - 1.0
        excess = stock_ret - spy_ret

        excesses.append(excess)
        weights.append(inc_pct)
        actions_priced.append(action)

        if action in ("new", "mixed"):
            new_exc.append(excess)
            new_wts.append(inc_pct)
        if action in ("add", "mixed"):
            add_exc.append(excess)
            add_wts.append(inc_pct)

    n_priced = len(excesses)
    base["n_priced"] = n_priced

    if n_priced == 0:
        return base

    exc_s = pd.Series(excesses)
    wt_s = pd.Series(weights)

    dw_excess = _weighted_average(exc_s, wt_s)
    base["dw_excess_60d"] = dw_excess
    base["hit_60d"] = float(exc_s.gt(0).sum()) / n_priced
    base["beat"] = bool(dw_excess > 0) if dw_excess is not None else None

    if new_exc:
        base["new_dw_excess_60d"] = _weighted_average(
            pd.Series(new_exc), pd.Series(new_wts)
        )
    if add_exc:
        base["add_dw_excess_60d"] = _weighted_average(
            pd.Series(add_exc), pd.Series(add_wts)
        )

    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_memory(
    slugs: list[str],
    fund_names: dict[str, str],
    fund_grades: dict[str, str | None],
    books_by_fund: dict[str, dict[str, pd.DataFrame]],
    data_root: Path | None = None,
    price_loader: Callable[[str], pd.Series | None] | None = None,
) -> dict:
    """Compute the 4-quarter fund memory block.

    Parameters
    ----------
    slugs:
        All tracked fund slugs (52 funds); order is unimportant.
    fund_names:
        {slug: human-readable name}.
    fund_grades:
        {slug: grade string | None} from the leaderboard.
    books_by_fund:
        {slug: {period_end_str: DataFrame}} — the same object produced by
        fund_followability.load_books(); amended snapshots excluded by that loader.
    data_root:
        Override for data/ directory (tests inject a tmp_path here).
    price_loader:
        Optional injectable (ticker: str) -> pd.Series|None. Defaults to the
        yahoo/breadth close panel used by fund_followability.

    Returns
    -------
    dict conforming to the SM4-R2 schema (see module docstring), or {} on error.

    NEVER raises; any uncaught exception returns {}.
    """
    try:
        return _compute_memory_inner(
            slugs, fund_names, fund_grades, books_by_fund, data_root, price_loader
        )
    except Exception:  # noqa: BLE001 — NEVER-BREAK contract
        log.exception("fund_memory: compute_memory failed — returning {}")
        return {}


def _compute_memory_inner(
    slugs: list[str],
    fund_names: dict[str, str],
    fund_grades: dict[str, str | None],
    books_by_fund: dict[str, dict[str, pd.DataFrame]],
    data_root: Path | None,
    price_loader_override: Callable[[str], pd.Series | None] | None,
) -> dict:
    loader = _make_price_loader(data_root, price_loader_override)

    # Load SPY series for benchmark
    price_cache: dict[str, pd.Series | None] = {}
    spy_series = loader(BENCHMARK)
    if spy_series is None or len(spy_series) == 0:
        log.warning("fund_memory: SPY series unavailable — returning {}")
        return {}

    spy_series = spy_series.sort_index()
    price_thru = spy_series.index[-1]
    price_cache[BENCHMARK] = spy_series

    # Derive the universe of ALL period_ends across all funds
    all_periods: set[str] = set()
    for periods_dict in books_by_fund.values():
        all_periods.update(periods_dict.keys())

    if not all_periods:
        log.warning("fund_memory: no filing data found — returning {}")
        return {}

    # Pick last 4 completed quarters: use those where anchor+60d <= price_thru
    # First find ALL available quarters, then filter to settled ones, take last 4
    candidate_periods = sorted(all_periods)

    def _anchor_for(period_end: str) -> pd.Timestamp:
        pe = pd.Timestamp(period_end)
        raw_anchor = pe + pd.Timedelta(days=ANCHOR_OFFSET_DAYS)
        # snap forward to next date present in spy_series
        eligible = spy_series.index[spy_series.index >= raw_anchor]
        if len(eligible) == 0:
            return raw_anchor  # beyond data; will be detected as unsettled
        return eligible[0]

    def _is_settled(period_end: str) -> bool:
        anchor = _anchor_for(period_end)
        exit_target = anchor + pd.Timedelta(days=HORIZON_DAYS)
        return exit_target <= price_thru + pd.Timedelta(days=1)

    settled_periods = [p for p in candidate_periods if _is_settled(p)]
    if not settled_periods:
        log.warning("fund_memory: no settled quarters found")
        return {}

    # Take the last 4 settled quarters
    quarters = _select_last_n_quarters(settled_periods, n=4)
    anchors = {pe: _anchor_for(pe) for pe in quarters}

    # --- Per-fund, per-quarter computation ---
    # We need N quarters of results per fund; keep None-filled slots where fund has no data.
    fund_rows: dict[str, list[dict | None]] = {}  # slug → list of 4 entries

    for slug in slugs:
        fund_books = books_by_fund.get(slug, {})
        per_quarter: list[dict | None] = []

        for pe in quarters:
            anchor = anchors[pe]
            cur_df = fund_books.get(pe)
            if cur_df is None or cur_df.empty:
                # Fund has no filing for this quarter
                per_quarter.append(None)
                continue

            # Prior quarter: the snapshot immediately before pe in this fund's data
            fund_periods_sorted = sorted(fund_books.keys())
            pe_idx = fund_periods_sorted.index(pe) if pe in fund_periods_sorted else -1
            if pe_idx > 0:
                prev_pe = fund_periods_sorted[pe_idx - 1]
                prev_df = fund_books[prev_pe]
            else:
                prev_df = None

            qr = _quarter_result(
                slug=slug,
                period_end=pe,
                prev_df=prev_df,
                cur_df=cur_df,
                anchor=anchor,
                spy_series=spy_series,
                price_thru=price_thru,
                price_loader=loader,
                price_cache=price_cache,
            )
            per_quarter.append(qr)

        fund_rows[slug] = per_quarter

    # --- Intra-quarter cohort ranking (dense rank of dw_excess_60d desc) ---
    # rank only funds with n_priced > 0 for that quarter
    for q_idx in range(len(quarters)):
        # collect (slug, dw_excess_60d) for funds that scored this quarter
        scored: list[tuple[str, float]] = []
        for slug, rows in fund_rows.items():
            row = rows[q_idx]
            if row is not None and row.get("n_priced", 0) > 0 and row.get("dw_excess_60d") is not None:
                scored.append((slug, row["dw_excess_60d"]))

        n_cohort = len(scored)
        # dense rank (ties share the same rank)
        if scored:
            sorted_scored = sorted(scored, key=lambda x: x[1], reverse=True)
            # dense rank: same value → same rank; next distinct value → rank+1
            rank_map: dict[str, int] = {}
            cur_rank = 1
            prev_val: float | None = None
            for i, (s, val) in enumerate(sorted_scored):
                if prev_val is not None and val < prev_val:
                    cur_rank = i + 1
                rank_map[s] = cur_rank
                prev_val = val
        else:
            rank_map = {}

        for slug, rows in fund_rows.items():
            row = rows[q_idx]
            if row is not None:
                row["n_cohort"] = n_cohort
                if slug in rank_map:
                    row["rank"] = rank_map[slug]

    # --- Consolidated per-fund stats ---
    funds_out: dict[str, dict] = {}

    for slug in slugs:
        rows = fund_rows.get(slug, [None] * len(quarters))
        name = fund_names.get(slug, slug)
        grade = fund_grades.get(slug)

        # quarters_beat: count quarters where beat=True
        quarters_beat = sum(
            1 for r in rows if r is not None and r.get("beat") is True
        )
        # quarters_scored: quarters with dw_excess_60d not null
        quarters_scored = sum(
            1 for r in rows if r is not None and r.get("dw_excess_60d") is not None
        )

        # avg_dw_excess_60d: simple mean over scored quarters
        scored_vals = [r["dw_excess_60d"] for r in rows
                       if r is not None and r.get("dw_excess_60d") is not None]
        avg_dw_excess_60d = (sum(scored_vals) / len(scored_vals)
                             if scored_vals else None)

        # Fill nulls for quarters with no data
        by_quarter: list[dict | None] = []
        for q_idx, pe in enumerate(quarters):
            row = rows[q_idx] if q_idx < len(rows) else None
            if row is None:
                by_quarter.append({
                    "period_end": pe,
                    "anchor": anchors[pe].date().isoformat(),
                    "n_priced": 0,
                    "dw_excess_60d": None,
                    "new_dw_excess_60d": None,
                    "add_dw_excess_60d": None,
                    "hit_60d": None,
                    "rank": None,
                    "n_cohort": 0,
                    "beat": None,
                })
            else:
                by_quarter.append(row)

        funds_out[slug] = {
            "name": name,
            "grade": grade,
            "by_quarter": by_quarter,
            "quarters_beat": quarters_beat,
            "quarters_scored": quarters_scored,
            "avg_dw_excess_60d": avg_dw_excess_60d,
            "memory_rank": None,  # filled below
        }

    # --- Memory rank (quarters_beat desc, then avg_dw_excess_60d desc) ---
    # Only funds with quarters_scored >= 3 get a rank
    ranked_slugs = [
        s for s in slugs
        if (funds_out[s]["quarters_scored"] >= 3
            and funds_out[s]["avg_dw_excess_60d"] is not None)
    ]
    unranked_slugs = [s for s in slugs if s not in set(ranked_slugs)]

    # Sort ranked: quarters_beat desc, avg_dw_excess_60d desc
    ranked_slugs.sort(
        key=lambda s: (
            -funds_out[s]["quarters_beat"],
            -(funds_out[s]["avg_dw_excess_60d"] or 0.0),
        )
    )
    for rank_1based, slug in enumerate(ranked_slugs, start=1):
        funds_out[slug]["memory_rank"] = rank_1based

    built_utc = datetime.now(timezone.utc).isoformat()

    return {
        "as_of": price_thru.date().isoformat(),
        "built": built_utc,
        "horizon_days": HORIZON_DAYS,
        "benchmark": BENCHMARK,
        "quarters": quarters,
        "anchors": {pe: anchors[pe].date().isoformat() for pe in quarters},
        "funds": funds_out,
        "board": ranked_slugs,
        "unranked": unranked_slugs,
        "note": (
            "Decision-weighted (incremental-book-pct) 60-calendar-day excess vs SPY, "
            "anchor = period_end+45d snapped to next trading close (optimistic for "
            "late or after-close filers — anchor may precede public availability). "
            "Display-tier only — no calibrated key, no gauntlet promotion."
        ),
    }
