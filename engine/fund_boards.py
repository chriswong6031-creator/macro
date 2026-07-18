"""13F Smart-Money board assembly — pure display-tier functions.

DISPLAY ONLY — nothing here feeds any calibrated key, Neural Web organ,
allocation gate, or escalation path. These are scoreboards and boards
for a display page, operator-ordered 2026-07-18.

Axis purity (SM2-R3): every score is 13F-lane only (fund holdings/filings/
outcomes). Insider positions, short interest, and 13D/G data are NEVER
blended into any score here — they may appear as separate context columns
in downstream templates but must not enter arithmetic here.

Filing lag caveat: 13F filings lag period-end by up to 45 days.
Excess returns are anchored on the PUBLIC filing date (look-ahead-free),
never the period-end date.

Banned names (blocklist-guarded): ownership_pressure, sponsorship,
breakaway. Use: follow_score, rotation_iq, front_run, fade.

No import-time I/O.  All disk reads are inside load_* helpers.
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import date, datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. cap_bucket + load_cap_sources
# ---------------------------------------------------------------------------

def load_cap_sources(data_root: Optional[pathlib.Path] = None) -> tuple:
    """Load membership + polygon_universe reference parquets.

    Returns (membership_df, polygon_df).  Either may be None on missing files
    or import errors — callers must guard for None.

    membership_df columns: ticker (str), group (str in {sp500,sp400,sp600}),
      sector (str), active (bool).
    polygon_df: index=ticker, columns include market_cap_usd (float).
    """
    try:
        import pandas as pd
    except ImportError:
        log.warning("load_cap_sources: pandas not available")
        return None, None

    root = data_root or (_REPO_ROOT / "data")

    membership_df = None
    polygon_df = None

    try:
        p = root / "universe" / "membership.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "active" in df.columns:
                df = df[df["active"].astype(bool)]
            membership_df = df
    except Exception:  # noqa: BLE001
        log.warning("load_cap_sources: membership.parquet unreadable", exc_info=True)

    try:
        p = root / "polygon_universe" / "reference.parquet"
        if p.exists():
            polygon_df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        log.warning("load_cap_sources: polygon reference.parquet unreadable", exc_info=True)

    return membership_df, polygon_df


def cap_bucket(
    ticker: str,
    membership_df=None,
    polygon_df=None,
) -> dict:
    """Return cap-size bucket and market cap for *ticker*.

    Bucket logic:
      sp500 membership -> "large"
      sp400 membership -> "mid"
      sp600 membership -> "small"
      absent from S&P 1500 -> "off_index"

    market_cap_usd is pulled from polygon_df when available (index=ticker).
    Returns {"bucket": str, "market_cap_usd": float|None}.
    """
    ticker = str(ticker).strip().upper()
    bucket = "off_index"
    market_cap = None

    # Determine bucket from S&P membership
    if membership_df is not None:
        try:
            row = membership_df[membership_df["ticker"] == ticker]
            if not row.empty:
                grp = str(row.iloc[0]["group"]).lower()
                if grp == "sp500":
                    bucket = "large"
                elif grp == "sp400":
                    bucket = "mid"
                elif grp == "sp600":
                    bucket = "small"
        except Exception:  # noqa: BLE001
            log.debug("cap_bucket: membership lookup failed for %s", ticker)

    # Pull market cap from polygon
    if polygon_df is not None:
        try:
            if ticker in polygon_df.index:
                val = polygon_df.loc[ticker, "market_cap_usd"]
                if val is not None:
                    import math
                    if not math.isnan(float(val)):
                        market_cap = float(val)
        except Exception:  # noqa: BLE001
            log.debug("cap_bucket: polygon lookup failed for %s", ticker)

    return {"bucket": bucket, "market_cap_usd": market_cap}


# ---------------------------------------------------------------------------
# 2. build_best_buys
# ---------------------------------------------------------------------------

def _filing_age_days(filing_date_str: str) -> int:
    """Return age in calendar days from filing_date string ('YYYY-MM-DD') to today."""
    try:
        fd = date.fromisoformat(str(filing_date_str)[:10])
        return (date.today() - fd).days
    except Exception:  # noqa: BLE001
        return 90  # default to old if unparseable


def _freshness_score(age_days: int) -> float:
    """Decay score: 1.0 at <=7d, linear to 0.2 at 90d, 0.2 floor beyond 90d.

    Formula:
        if age <= 7: 1.0
        elif age <= 90: 1.0 - (age - 7) * (0.8 / 83)
        else: 0.2
    """
    if age_days <= 7:
        return 1.0
    if age_days <= 90:
        return round(1.0 - (age_days - 7) * (0.8 / 83), 4)
    return 0.2


def _incr_pct(action: str, pct_book: float, shares_change_pct) -> float:
    """Incremental weight from Grade-A study formula.

    new  -> pct_book
    add  -> pct_book * chg / (100 + chg)
             guard: chg <= -100 or None -> fall back to pct_book * 0.5
    """
    if action == "new":
        return float(pct_book)
    # add
    try:
        chg = float(shares_change_pct)
    except (TypeError, ValueError):
        chg = None
    if chg is None or chg <= -100:
        return float(pct_book) * 0.5
    return float(pct_book) * chg / (100.0 + chg)


def build_best_buys(
    initiations: list[dict],
    followability: dict,
    sector_flows: Optional[dict],
    cap_sources,
    top_n: int = 40,
) -> list[dict]:
    """Build the ranked Best-Buys board from Grade-A fund initiations.

    Parameters
    ----------
    initiations:
        Latest-quarter new/add items.  Each dict must have:
        ticker, issuer, action, pct_book, shares_change_pct, filing_date,
        since_excess, sector.  Optionally: slug, name, follow_tier,
        follow_score (keyed under the fund sub-dict).
    followability:
        {slug: {"follow_tier": str, "follow_score": float, "n": int, ...}}
        follow_tier in {"follow", "watch", "insufficient", "fade"}
    sector_flows:
        {sector_name: {"net_inflow": bool}} or None (treated as unknown).
    cap_sources:
        (membership_df, polygon_df) tuple as returned by load_cap_sources().
    top_n:
        Number of rows to return (default 40).

    Returns
    -------
    List of dicts sorted by desk_rank_score desc, length <= top_n.

    Score components (each 0–1, before weighting):
        conviction  = min(1, max_incr_pct / 5)
        quality     = best fund follow_score / 100  (insufficient -> 0.35 flat)
        confluence  = min(1, (n_qualified_funds - 1) / 3)
                      + 0.15 if sector net inflow (capped at 1.0)
        freshness   = decay by filing age (1.0 <=7d, linear to 0.2 at 90d)

    desk_rank_score = 100 * (0.35*conviction + 0.30*quality
                             + 0.25*confluence + 0.10*freshness)

    QUALIFIED funds: follow_tier in ("follow", "watch").
    "fade" funds are EXCLUDED from this board (operator: ignore consistent losers).
    "insufficient" counts at half quality weight but is NOT excluded.

    13F axis only — no insider or short-interest inputs.
    """
    membership_df, polygon_df = cap_sources if cap_sources else (None, None)

    # Group initiations by ticker
    by_ticker: dict[str, list[dict]] = {}
    for row in initiations:
        ticker = str(row.get("ticker", "") or "").strip().upper()
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(row)

    result: list[dict] = []

    for ticker, rows in by_ticker.items():
        # Build per-fund entries
        fund_entries: list[dict] = []
        action_counts = {"new": 0, "add": 0}
        latest_filing = ""
        sector_val = None
        issuer_val = ""
        since_excess_vals: list[float] = []

        for row in rows:
            action = str(row.get("action", "") or "").lower()
            if action not in ("new", "add"):
                continue

            pb = float(row.get("pct_book") or 0.0)
            chg = row.get("shares_change_pct")
            ip = _incr_pct(action, pb, chg)

            slug = str(row.get("slug") or row.get("fund") or "")
            fund_info = (followability or {}).get(slug, {})
            tier = str(fund_info.get("follow_tier") or row.get("follow_tier") or "insufficient").lower()
            score = fund_info.get("follow_score") or row.get("follow_score")
            try:
                fs = float(score)
            except (TypeError, ValueError):
                fs = 0.0

            # Operator rule: fade funds excluded from this board
            if tier == "fade":
                continue

            name = fund_info.get("name") or row.get("name") or row.get("fund_name") or slug

            fund_entries.append({
                "slug": slug,
                "name": name,
                "follow_tier": tier,
                "follow_score": fs,
                "action": action,
                "incr_pct": round(ip, 4),
            })

            action_counts[action] = action_counts.get(action, 0) + 1

            fd = str(row.get("filing_date") or "")
            if fd > latest_filing:
                latest_filing = fd

            if not sector_val:
                sector_val = row.get("sector")
            if not issuer_val:
                issuer_val = str(row.get("issuer") or "")

            se = row.get("since_excess")
            if se is not None:
                try:
                    since_excess_vals.append(float(se))
                except (TypeError, ValueError):
                    pass

        if not fund_entries:
            continue

        # Compute components
        incr_pcts = [fe["incr_pct"] for fe in fund_entries]
        max_ip = max(incr_pcts)
        sum_ip = sum(incr_pcts)

        conviction = min(1.0, max_ip / 5.0)

        # Quality: best fund follow_score / 100; insufficient -> 0.35 flat
        # QUALIFIED = follow | watch (not insufficient, not fade)
        qualified = [fe for fe in fund_entries if fe["follow_tier"] in ("follow", "watch")]
        n_qualified = len(qualified)

        best_score = None
        for fe in fund_entries:
            tier = fe["follow_tier"]
            fs = fe["follow_score"]
            if tier in ("follow", "watch"):
                if best_score is None or fs > best_score:
                    best_score = fs
        if best_score is None:
            # Only insufficient funds
            quality = 0.35
        else:
            quality = min(1.0, best_score / 100.0)

        sector_inflow = None
        if sector_flows and sector_val and sector_val in sector_flows:
            sector_inflow = bool(sector_flows[sector_val].get("net_inflow"))

        base_confluence = min(1.0, (n_qualified - 1) / 3.0) if n_qualified >= 1 else 0.0
        sector_bonus = 0.15 if sector_inflow else 0.0
        confluence = min(1.0, base_confluence + sector_bonus)

        age = _filing_age_days(latest_filing) if latest_filing else 90
        freshness = _freshness_score(age)

        desk_rank_score = round(
            100.0 * (0.35 * conviction + 0.30 * quality + 0.25 * confluence + 0.10 * freshness),
            2,
        )

        cb = cap_bucket(ticker, membership_df, polygon_df)

        since_med: Optional[float] = None
        if since_excess_vals:
            sorted_se = sorted(since_excess_vals)
            mid = len(sorted_se) // 2
            if len(sorted_se) % 2 == 0 and len(sorted_se) > 1:
                since_med = (sorted_se[mid - 1] + sorted_se[mid]) / 2.0
            else:
                since_med = sorted_se[mid]

        result.append({
            "ticker": ticker,
            "issuer": issuer_val,
            "sector": sector_val,
            "cap_bucket": cb["bucket"],
            "market_cap_usd": cb["market_cap_usd"],
            "actions": {"new": action_counts["new"], "add": action_counts["add"]},
            "n_funds": len(fund_entries),
            "funds": fund_entries,
            "incr_pct_max": round(max_ip, 4),
            "incr_pct_sum": round(sum_ip, 4),
            "sector_inflow": sector_inflow,
            "latest_filing": latest_filing,
            "freshness_d": age,
            "since_excess_med": since_med,
            "desk_rank_score": desk_rank_score,
            "components": {
                "conviction": round(conviction, 4),
                "quality": round(quality, 4),
                "confluence": round(confluence, 4),
                "freshness": round(freshness, 4),
            },
        })

    result.sort(key=lambda r: r["desk_rank_score"], reverse=True)
    return result[:top_n]


# ---------------------------------------------------------------------------
# 3. build_small_mid_board
# ---------------------------------------------------------------------------

def build_small_mid_board(
    best_buys_rows_or_initiations,
    followability: dict,
    cap_sources,
    min_incr_pct: float = 1.5,
    top_n: int = 25,
) -> list[dict]:
    """Small/mid-cap conviction board.

    Accepts either the output of build_best_buys() (list[dict] with cap_bucket,
    incr_pct_max, funds keys) or raw initiations (in which case build_best_buys
    is called internally with no sector_flows).

    Filter criteria (ALL must pass):
      1. cap_bucket in ("mid", "small", "off_index")
      2. incr_pct_max >= min_incr_pct
      3. At least one fund with follow_tier == "follow" OR follow_score >= 55

    off_index rows get "off_index_note": True (cap unknown; outside S&P 1500,
    typically small/micro).

    Adds "why": short receipt string listing qualifying fund + incr_pct + bucket.

    Returns same row shape as build_best_buys rows, sorted by desk_rank_score desc,
    length <= top_n.
    """
    # Normalize input: if it looks like raw initiations (no cap_bucket key), run
    # build_best_buys first
    rows = best_buys_rows_or_initiations
    if rows and "cap_bucket" not in rows[0]:
        rows = build_best_buys(rows, followability, None, cap_sources, top_n=1000)

    filtered: list[dict] = []
    for row in rows:
        bucket = row.get("cap_bucket", "off_index")
        if bucket not in ("mid", "small", "off_index"):
            continue
        max_ip = row.get("incr_pct_max", 0.0)
        if max_ip < min_incr_pct:
            continue

        funds = row.get("funds", [])
        qualifying_funds = [
            f for f in funds
            if f.get("follow_tier") == "follow" or float(f.get("follow_score") or 0) >= 55
        ]
        if not qualifying_funds:
            continue

        out = dict(row)
        out["off_index_note"] = (bucket == "off_index")

        # Build why receipt
        why_parts = [
            f"{f['slug']}:{round(f['incr_pct'],2)}pp/{f['follow_tier']}"
            for f in qualifying_funds[:3]
        ]
        out["why"] = f"bucket={bucket} incr_max={max_ip:.2f}pp | " + ", ".join(why_parts)

        filtered.append(out)

    filtered.sort(key=lambda r: r.get("desk_rank_score", 0), reverse=True)
    return filtered[:top_n]


# ---------------------------------------------------------------------------
# 4. build_sector_consensus
# ---------------------------------------------------------------------------

def build_sector_consensus(
    books_latest_pair: dict,
    followability: dict,
    classifications: dict,
    min_rotator_iq_n: int = 6,
) -> list[dict]:
    """Sector consensus across PROVEN ROTATORS (descriptive screen).

    This is a descriptive screen only; n is printed on every row.
    'Descriptive screen; n printed' — not a validated claim.

    PROVEN ROTATOR criteria (printed on output, not a validated gate):
      rotation_iq.n_calls >= min_rotator_iq_n AND rotation_iq.hit_rate >= 0.5

    Parameters
    ----------
    books_latest_pair:
        {slug: {"prev": {sector: weight_pp}, "curr": {sector: weight_pp},
                "rotation_iq": {"score": float, "n_calls": int, "hit_rate": float}}}
        OR
        {slug: {"prev": pd.DataFrame, "curr": pd.DataFrame, ...}}
        Both shapes accepted (dict-of-weight-dicts preferred for display).
    followability:
        {slug: {"follow_tier": str, "follow_score": float, ...}}
    classifications:
        {ticker: {"sector": str, ...}} — used to look up tickers' sectors for top_buys.
    min_rotator_iq_n:
        Minimum n_calls to count as a proven rotator (default 6).

    Returns
    -------
    List of per-sector dicts, sorted by iq_weighted_delta_pp desc:
        {sector, iq_weighted_delta_pp, breadth_up, breadth_down,
         top_buys, n_proven, n_fade_excluded, method_note}
    """
    sector_agg: dict[str, dict] = {}  # sector -> accumulator

    n_fade_excluded_total = 0

    for slug, book in (books_latest_pair or {}).items():
        # Exclude fade funds
        tier = (followability or {}).get(slug, {}).get("follow_tier", "insufficient")
        if tier == "fade":
            n_fade_excluded_total += 1
            continue

        riq = book.get("rotation_iq") or {}
        n_calls = int(riq.get("n_calls") or 0)
        hit_rate = float(riq.get("hit_rate") or 0.0)

        # Proven rotator screen (descriptive)
        if n_calls < min_rotator_iq_n or hit_rate < 0.5:
            continue

        iq_score = float(riq.get("score") or 0.0)

        prev_weights: dict = book.get("prev") or {}
        curr_weights: dict = book.get("curr") or {}

        # Normalize: accept DataFrames (with sector, weight_pp cols) or plain dicts
        try:
            import pandas as pd
            if hasattr(prev_weights, "iterrows"):
                prev_weights = {r["sector"]: r["weight_pp"] for _, r in prev_weights.iterrows()}
            if hasattr(curr_weights, "iterrows"):
                curr_weights = {r["sector"]: r["weight_pp"] for _, r in curr_weights.iterrows()}
        except ImportError:
            pass

        all_sectors = set(list(prev_weights.keys()) + list(curr_weights.keys()))

        for sector in all_sectors:
            prev_pp = float(prev_weights.get(sector) or 0.0)
            curr_pp = float(curr_weights.get(sector) or 0.0)
            delta = curr_pp - prev_pp

            agg = sector_agg.setdefault(sector, {
                "sector": sector,
                "iq_weighted_delta_pp": 0.0,
                "breadth_up": 0,
                "breadth_down": 0,
                "top_buys_raw": {},  # ticker -> sum incr_pct
                "n_proven": 0,
                "n_fade_excluded": 0,
            })
            agg["iq_weighted_delta_pp"] += delta * (iq_score / 100.0)
            if delta >= 0.5:
                agg["breadth_up"] += 1
            elif delta <= -0.5:
                agg["breadth_down"] += 1
            agg["n_proven"] += 1

            # Contribute top_buys: tickers from curr book in this sector
            tickers_in_sector = book.get("tickers_curr", {}).get(sector, [])
            for item in tickers_in_sector:
                tk = item.get("ticker", "") if isinstance(item, dict) else str(item)
                ip = float(item.get("incr_pct", 0.0) if isinstance(item, dict) else 0.0)
                agg["top_buys_raw"][tk] = agg["top_buys_raw"].get(tk, 0.0) + ip

    METHOD_NOTE = ("descriptive screen; n printed — proven-rotator filter applies "
                   "n_calls >= %d AND hit_rate >= 0.50; not a validated predictive claim." % min_rotator_iq_n)

    result = []
    for sector, agg in sector_agg.items():
        raw_buys = agg.pop("top_buys_raw")
        top_buys = sorted(raw_buys.items(), key=lambda x: x[1], reverse=True)[:5]
        agg["top_buys"] = [{"ticker": t, "incr_pct_sum": round(ip, 4)} for t, ip in top_buys]
        agg["n_fade_excluded"] = n_fade_excluded_total
        agg["method_note"] = METHOD_NOTE
        agg["iq_weighted_delta_pp"] = round(agg["iq_weighted_delta_pp"], 4)
        result.append(agg)

    result.sort(key=lambda r: r["iq_weighted_delta_pp"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# 5. load_grade_a_card
# ---------------------------------------------------------------------------

def load_grade_a_card(root: Optional[pathlib.Path] = None) -> Optional[dict]:
    """Parse the Grade-A 2026Q1 research artifact files.

    Reads from research/artifacts/SMART_MONEY_GRADE_A_2026Q1/:
      - fund_horizon_summary.csv
      - fund_action_horizon_summary.csv
      - metadata.json

    Returns
    -------
    {
        "frozen": True,
        "as_of": metadata.tracker_price_thru,
        "period": metadata.report_period,
        "anchor": metadata.common_return_anchor,
        "rows": [
            {
                "fund": str,
                "name": str,
                "n_priced": int,
                "dw_return_60d": float,
                "dw_excess_60d": float,
                "new_dw_excess_60d": float,  # action-level decision_weighted_excess_60d, action=new
                "add_dw_excess_60d": float,  # action-level decision_weighted_excess_60d, action=add
                "hit_60d": float,            # hit_rate_60d
                "book_impact_pp": float,     # estimated_book_contribution_60d_pp
            }
        ] sorted by dw_excess_60d desc
    }
    None if any required file is absent (degrade-safe).
    """
    artifact_root = root or (_REPO_ROOT / "research" / "artifacts" / "SMART_MONEY_GRADE_A_2026Q1")

    try:
        import pandas as pd
    except ImportError:
        log.warning("load_grade_a_card: pandas not available")
        return None

    # Check all required files exist
    horizon_path = artifact_root / "fund_horizon_summary.csv"
    action_path = artifact_root / "fund_action_horizon_summary.csv"
    meta_path = artifact_root / "metadata.json"

    for p in (horizon_path, action_path, meta_path):
        if not p.exists():
            log.warning("load_grade_a_card: missing %s — returning None", p)
            return None

    try:
        meta = json.loads(meta_path.read_text())
    except Exception:  # noqa: BLE001
        log.warning("load_grade_a_card: metadata.json unreadable", exc_info=True)
        return None

    try:
        horizon_df = pd.read_csv(horizon_path)
        action_df = pd.read_csv(action_path)
    except Exception:  # noqa: BLE001
        log.warning("load_grade_a_card: CSV read failed", exc_info=True)
        return None

    # Build action lookup: {fund: {action: decision_weighted_excess_60d}}
    # FIX 5: source New/Add split from ACTION-LEVEL EXCESS (decision_weighted_excess_60d)
    # so the card is units-consistent (everything excess vs SPY); keys renamed to
    # new_dw_excess_60d / add_dw_excess_60d.
    action_lookup: dict[str, dict[str, float]] = {}
    for _, row in action_df.iterrows():
        fund = str(row.get("fund") or "")
        act = str(row.get("action") or "").lower()
        val = row.get("decision_weighted_excess_60d")
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            val_f = None
        action_lookup.setdefault(fund, {})[act] = val_f

    rows = []
    for _, row in horizon_df.iterrows():
        fund = str(row.get("fund") or "")
        fund_actions = action_lookup.get(fund, {})

        def _f(col):
            try:
                return float(row.get(col))
            except (TypeError, ValueError):
                return None

        rows.append({
            "fund": fund,
            "name": str(row.get("fund_name") or fund),
            "n_priced": int(row.get("n_priced") or 0),
            "dw_return_60d": _f("decision_weighted_return_60d"),
            "dw_excess_60d": _f("decision_weighted_excess_60d"),
            "new_dw_excess_60d": fund_actions.get("new"),   # action-level excess (FIX 5)
            "add_dw_excess_60d": fund_actions.get("add"),   # action-level excess (FIX 5)
            "hit_60d": _f("hit_rate_60d"),
            "book_impact_pp": _f("estimated_book_contribution_60d_pp"),
        })

    rows.sort(key=lambda r: (r["dw_excess_60d"] or -999), reverse=True)

    return {
        "frozen": True,
        "as_of": meta.get("tracker_price_thru"),
        "period": meta.get("report_period"),
        "anchor": meta.get("common_return_anchor"),
        "rows": rows,
    }
