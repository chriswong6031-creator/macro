"""Ownership event wire — chronological merge of 13F deltas, 13D/G events, and
insider clusters for the Smart Money v2 Ownership Intelligence Desk (SM2-R3).

HONESTY CONTRACT
----------------
SM2-R3 (no fusion): Every row in the wire carries its native axis stamp and native
  as-of date. This module CONCATENATES three independent input streams; it never
  blends, interpolates, or normalises values across axes. The axis field on each row
  names which source produced it and carries the only as-of date valid for that row.

PIT LAW: `filing_date` is the only look-ahead-free anchor for 13F rows. The 13D/G
  rows use `date_filed` from the filings store. Insider rows use the latest
  transaction date from the quiver store (best-effort; stale stamp is printed when
  the store is more than 7 days old, never hidden).

INSIDER SOURCE SELECTION: at runtime, this module compares the max date in
  data/quiver/insiders.parquet against the max date in data/sec_insider/insider.parquet
  (quarter summary). It uses the FRESHER store. Because sec_insider is a quarterly
  panel summary (buy_usd/sell_usd/n_buys/n_sells per quarter) while quiver insiders
  carry individual transactions, the selection is made on date freshness; the selected
  source is stamped on every insider wire row via `axis`.

FILING-SEASON CLOCK: `filing_season_clock()` is a pure function (injected today) that
  computes the expected quarter, deadline, and days-to-deadline as of any date.
  The latest completed calendar quarter's 45-day filing deadline drives the clock.

NIGHTLY ONLY: This module computes event rows but does NOT advance any forward
  ledger; ledger advancement is owned by ownership_ledger.py and is gated behind the
  COLLECT_LANE=nightly environment variable (see that module for the guard pattern).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Lookback window for 13D/G events in the main wire (calendar days).
# The activists BOARD uses its own 45-day feed (_13DG_LOOKBACK_ACTIVISTS = 45)
# built separately in build_smart_money._build_activists; the main wire keeps
# 14 days so the combined row count stays manageable.
_13DG_LOOKBACK_DAYS = 14
_13DG_LOOKBACK_ACTIVISTS = 45

# Minimum absolute % of fund book to surface on the wire (new/add rows).
_MIN_BOOK_PCT = 0.0    # surface all; the board filters by action

# Per-trade USD sanity cap for quiver insider rows: a single Form-4 print above this
# is a data artefact (re-filed/fat-fingered — the -$6.2B OLPX cluster), and the row
# is DROPPED, never clipped. Same per-trade default as engine.insider_intel
# (config: smart_money.insider_intel.usd_sanity_cap).
_TRADE_USD_CAP = 500_000_000

# Re-filed Form 4s land as exact duplicates on these columns in the quiver store
# (fileDate is part of the collector's dedup key — F1), so the wire must collapse
# them before clustering.
_QUIVER_DEDUP_COLS = ("Ticker", "Date", "Name", "TransactionCode", "Shares")

# One-shot latch: the TransactionCode fallback warns once per process, not per call.
_TXN_CODE_WARNED = False

# Keys expected on a wire row — strict schema so the template and tests can rely on it.
WIRE_SCHEMA = (
    "date", "axis", "type", "slug", "fund", "ticker", "issuer",
    "action", "magnitude", "unit", "asof_note",
)


# --------------------------------------------------------------------------- #
# Filing-season clock (pure; inject today for unit tests)                      #
# --------------------------------------------------------------------------- #

def _latest_completed_quarter(today: date) -> date:
    """The most-recent calendar quarter-end strictly before `today`.

    Returns the last day of the quarter (2026-03-31, 2026-06-30, 2025-12-31 …).
    """
    month = today.month
    if month >= 10:
        return date(today.year, 9, 30)
    if month >= 7:
        return date(today.year, 6, 30)
    if month >= 4:
        return date(today.year, 3, 31)
    return date(today.year - 1, 12, 31)


def filing_season_clock(funds: dict[str, dict],
                        fund_filings: dict[str, dict] | None = None,
                        today: date | None = None) -> dict:
    """Pure date-math summary of the current filing-season state.

    Parameters
    ----------
    funds : {slug: spec} from config — the active roster.
    fund_filings : {slug: {period_end: str, filing_date: str}} — each fund's most-recent
        on-disk snapshot metadata. None → every fund is 'pending'.
    today : date override for unit tests; defaults to date.today().

    Returns
    -------
    {
        next_deadline : "YYYY-MM-DD"  (quarter_end + 45 calendar days),
        days_to_deadline : int        (negative = window already closed),
        quarter_state : "window_open" | "window_closed" | "between",
        quarter_end : "YYYY-MM-DD"    (the completed quarter period-end),
        filed_pending : [
            {slug, name, period_end, filing_date, status}
            # status: "filed" | "pending" | "lapsed"
        ],
    }

    quarter_state logic:
      * We expect filings for `quarter_end`. The filing window opens the day after
        quarter_end and closes at `next_deadline` (quarter_end + 45 days).
      * "window_open"  : today is in [quarter_end+1, next_deadline] — filings expected.
      * "window_closed": today is AFTER next_deadline — window lapsed.
      * "between"      : today is BEFORE the window opened (i.e., today <= quarter_end).
        This handles the rare case where today IS the quarter-end date itself.
    """
    today = today or date.today()
    qend = _latest_completed_quarter(today)
    deadline = qend + timedelta(days=45)
    days_to_dl = (deadline - today).days

    # Determine quarter_state
    if today <= qend:
        quarter_state = "between"
    elif today > deadline:
        quarter_state = "window_closed"
    else:
        quarter_state = "window_open"

    fund_filings = fund_filings or {}
    grid = []
    for slug, spec in funds.items():
        meta = fund_filings.get(slug, {})
        period_end = meta.get("period_end", "") or ""
        filing_date = meta.get("filing_date", "") or ""
        # Closed funds (status: closed in config) do not file; skip them in the
        # filed/pending counts but include them in the grid as a muted indicator.
        if str(spec.get("status", "")).lower() == "closed":
            status = "closed"
        else:
            # A fund has "filed" for this expected quarter if its latest on-disk
            # period_end matches the expected quarter_end string.
            expected_pe = str(qend)
            if period_end == expected_pe:
                status = "filed"
            elif quarter_state == "window_open":
                status = "pending"
            else:
                status = "lapsed"
        grid.append({
            "slug": slug,
            "name": spec.get("name", slug),
            "period_end": period_end,
            "filing_date": filing_date,
            "status": status,
        })

    return {
        "next_deadline": str(deadline),
        "days_to_deadline": days_to_dl,
        "quarter_state": quarter_state,
        "quarter_end": str(qend),
        "filed_pending": grid,
    }


# --------------------------------------------------------------------------- #
# 13F delta axis                                                                #
# --------------------------------------------------------------------------- #

def _13f_rows(funds: dict[str, dict]) -> list[dict]:
    """Wire rows from the latest consecutive 13F snapshot pair per fund.

    Uses engine.smart_money.diff_snapshots on (prev, latest) — the standard
    PIT-honest diff. Emits one row per new/add/trim/exit action with:
      axis      = "13f"
      type      = action ("new", "add", "trim", "exit")
      magnitude = pct_portfolio for new/add/trim; value_usd for exits (since
                  pct_portfolio is 0 on exits by construction in diff_snapshots)
      unit      = "pct_book" | "usd"
      date      = filing_date of the latest snapshot (the PUBLIC look-ahead-free date)

    Also emits amendment rows (type="13f_amendment") from smart_money.amendment_delta
    for each fund that has an amendments directory.

    SM2-R3: no blending. Every row stamps ONLY the 13F filing_date as its as-of.
    """
    from engine.smart_money import (
        _read_two, diff_snapshots, resolve_tickers,
        name_ticker_map, full_cusip_map, amendment_delta,
        _snapshot_filing_date,
    )

    name_map = name_ticker_map()
    cusip_map, _ = full_cusip_map()
    rows: list[dict] = []

    for slug, spec in funds.items():
        prev, latest = _read_two(slug)
        if latest is None or latest.empty:
            continue
        filing_date = _snapshot_filing_date(latest)
        if not filing_date:
            continue  # no public date — cannot place a look-ahead-free row

        diff = diff_snapshots(prev, latest)
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)

        for r in diff.itertuples(index=False):
            if r.action == "hold":
                continue
            ticker = getattr(r, "ticker", None)
            issuer = str(getattr(r, "issuer", "") or "")
            pct = getattr(r, "pct_portfolio", None)
            val = getattr(r, "value_usd", None)

            if r.action == "exit":
                magnitude = round(float(val), 0) if val else None
                unit = "usd"
            else:
                magnitude = round(float(pct), 2) if pct is not None else None
                unit = "pct_book"

            rows.append({
                "date": filing_date,
                "axis": "13f",
                "type": r.action,
                "slug": slug,
                "fund": spec.get("name", slug),
                "ticker": ticker,
                "issuer": issuer,
                "action": r.action,
                "magnitude": magnitude,
                "unit": unit,
                "asof_note": f"13F filing {filing_date}",
            })

        # Amendment deltas — type "13f_amendment"
        try:
            for ad in amendment_delta(slug):
                rows.append({
                    "date": ad.get("amendment_filing_date", filing_date),
                    "axis": "13f",
                    "type": "13f_amendment",
                    "slug": slug,
                    "fund": spec.get("name", slug),
                    "ticker": None,
                    "issuer": ad.get("issuer", ""),
                    "action": "amendment",
                    "magnitude": ad.get("pct_change_shares"),
                    "unit": "pct_shares_change",
                    "asof_note": f"13F-HR/A amendment {ad.get('amendment_filing_date', '')}",
                })
        except Exception:  # noqa: BLE001
            log.debug("amendment_delta failed for %s", slug, exc_info=True)

    return rows


# --------------------------------------------------------------------------- #
# 13D/G activist axis                                                           #
# --------------------------------------------------------------------------- #

def _roster_tickers(funds: dict[str, dict]) -> set[str]:
    """Flat set of resolved tickers currently held by ANY tracked fund."""
    from engine.smart_money import _read_two, diff_snapshots, resolve_tickers, name_ticker_map, full_cusip_map
    name_map = name_ticker_map()
    cusip_map, _ = full_cusip_map()
    tickers: set[str] = set()
    for slug in funds:
        _, latest = _read_two(slug)
        if latest is None or latest.empty:
            continue
        diff = diff_snapshots(None, latest)  # treat all as "new" to get full roster
        if diff.empty:
            continue
        diff = resolve_tickers(diff, name_map, cusip_map)
        for t in diff["ticker"].dropna():
            tickers.add(str(t))
    return tickers


def _13dg_rows(lookback_days: int = _13DG_LOOKBACK_DAYS,
               roster: set[str] | None = None) -> list[dict]:
    """Wire rows from the 13D/G filings store.

    Uses engine.beneficial_ownership to load the enriched filings and classify each
    event. Restricts to `lookback_days` calendar days of history.

    Adds a boolean `roster_hit` field: True when the filing's ticker is also held by
    a tracked fund.

    SM2-R3: no blending. Rows carry `date_filed` as their as-of date.
    """
    try:
        from engine.beneficial_ownership import _load_enrichment, classify_filer_type
    except ImportError:
        log.debug("beneficial_ownership import failed — 13D/G axis empty")
        return []

    enr = _load_enrichment()
    if enr is None or enr.empty:
        return []

    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=lookback_days))
    cutoff_ts = pd.Timestamp(cutoff)

    # Require ticker + date_filed
    req_cols = {"ticker", "date_filed", "form_type"}
    if not req_cols <= set(enr.columns):
        log.debug("beneficial_ownership filings missing required columns: %s", req_cols - set(enr.columns))
        return []

    df = enr.copy()
    df["_parsed_date"] = pd.to_datetime(df["date_filed"], errors="coerce")
    df = df.dropna(subset=["_parsed_date", "ticker"])
    df = df[df["_parsed_date"] >= cutoff_ts]
    if df.empty:
        return []

    roster = roster or set()
    rows: list[dict] = []
    for r in df.itertuples(index=False):
        form = str(getattr(r, "form_type", "") or "")
        ticker = str(getattr(r, "ticker", "") or "").strip().upper()
        # Use _parsed_date if accessible, else fall back to date_filed string
        parsed = getattr(r, "_parsed_date", None)
        if parsed is not None and str(parsed) not in ("", "nan", "None"):
            date_filed = str(parsed)[:10]
        else:
            date_filed = str(getattr(r, "date_filed", ""))[:10]
        filer = str(getattr(r, "filer", "") or "") if hasattr(r, "filer") else ""
        filer_type = str(getattr(r, "filer_type", "") or "") if hasattr(r, "filer_type") else classify_filer_type(filer)
        company = str(getattr(r, "company", "") or "") if hasattr(r, "company") else ""

        # Derive signal from classify logic (re-use beneficial_ownership classification)
        from engine.beneficial_ownership import _is_13d, _is_13g
        if _is_13d(form):
            if filer_type == "passive_giant":
                signal = "low"
            else:
                signal = "high"
            action = "13d"
        elif _is_13g(form):
            if filer_type == "passive_giant":
                signal = "noise"
            else:
                signal = "low"
            action = "13g"
        else:
            continue  # skip non-13D/G

        rows.append({
            "date": date_filed,
            "axis": "13dg",
            "type": form,
            "slug": "",
            "fund": filer or "unknown",
            "ticker": ticker or None,
            "issuer": company,
            "action": action,
            "magnitude": None,
            "unit": None,
            "asof_note": f"13D/G filing {date_filed}",
            # Extra fields for the activist board (not in base WIRE_SCHEMA — bonus context)
            "signal": signal,
            "filer_type": filer_type,
            "roster_hit": (ticker in roster) if ticker else False,
        })

    # Dedupe repeated custodial re-files: for the same (filer, ticker, form_type) keep
    # only the newest filing within the window. Custodial 13G/A re-files from passive
    # giants (e.g. BlackRock, Vanguard) can flood the window with near-identical rows.
    seen_keys: set[tuple] = set()
    deduped: list[dict] = []
    # Sort newest-first so we keep the most recent filing per key
    rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    for r in rows:
        key = (r.get("fund", ""), r.get("ticker", ""), r.get("type", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(r)
        else:
            log.debug("13dg_rows: dropped duplicate custodial re-file "
                      "filer=%s ticker=%s form=%s date=%s",
                      r.get("fund"), r.get("ticker"), r.get("type"), r.get("date"))
    return deduped


# --------------------------------------------------------------------------- #
# Insider axis                                                                  #
# --------------------------------------------------------------------------- #

def _check_insider_freshness() -> tuple[str, str | None, str]:
    """Compare max dates in both insider stores; return (store_key, asof, note).

    Returns ("quiver", asof_str, note) or ("sec_insider", asof_str, note) or
    ("none", None, note) when both are absent/stale.

    HONESTY: never fake freshness. If both stores are absent, returns ("none", None, ...).
    """
    quiver_date: date | None = None
    sec_date: date | None = None

    try:
        p = config.data_dir() / "quiver" / "insiders.parquet"
        if p.exists():
            df = pd.read_parquet(p, columns=["Date"])
            if not df.empty:
                quiver_date = pd.to_datetime(df["Date"]).max().date()
    except Exception:  # noqa: BLE001
        pass

    try:
        p = config.data_dir() / "sec_insider" / "insider.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            # sec_insider is a quarterly summary (quarter column); extract max quarter date
            if "quarter" in df.columns and not df.empty:
                max_q = str(df["quarter"].max())
                if max_q and len(max_q) >= 7:
                    # quarter format "YYYY-Q#" or "YYYY-MM-DD"
                    try:
                        if "-Q" in max_q:
                            yr, qn = max_q.split("-Q")
                            month = int(qn) * 3
                            day = {3: 31, 6: 30, 9: 30, 12: 31}.get(month, 30)
                            sec_date = date(int(yr), month, day)
                        else:
                            sec_date = pd.Timestamp(max_q).date()
                    except Exception:
                        pass
    except Exception:  # noqa: BLE001
        pass

    today = date.today()

    def _stale_note(d: date, store: str) -> str:
        lag = (today - d).days
        return f"{store} insiders as-of {d} ({lag}d lag)"

    if quiver_date is None and sec_date is None:
        return "none", None, "insider stores absent — no insider rows"

    if quiver_date is None:
        note = _stale_note(sec_date, "sec_insider")  # type: ignore[arg-type]
        return "sec_insider", str(sec_date), note

    if sec_date is None:
        note = _stale_note(quiver_date, "quiver")
        return "quiver", str(quiver_date), note

    if quiver_date >= sec_date:
        note = _stale_note(quiver_date, "quiver")
        return "quiver", str(quiver_date), note
    else:
        note = _stale_note(sec_date, "sec_insider")
        return "sec_insider", str(sec_date), note


def _insider_rows(roster: set[str]) -> list[dict]:
    """Wire rows from the fresher of the two insider stores.

    Restricted to tickers in `roster` (tracked fund holdings). Each row is a
    cluster summary: {n_buys, n_sells, net_usd} for the ticker over the available
    recent window.

    Stamps the axis as "form4/quiver-insider" or "form4/sec-insider" per the store used.
    If both stores are stale (>7d), emits rows with the honest stale stamp but no data.

    SM2-R3: insider rows are independent axis rows — they carry no 13F or short-volume
    derived fields. `axis` makes the source explicit on every row.
    """
    store_key, asof, note = _check_insider_freshness()
    if store_key == "none" or asof is None:
        return []

    if store_key == "quiver":
        return _insider_rows_quiver(roster, asof, note)
    else:
        return _insider_rows_sec(roster, asof, note)


def _insider_rows_quiver(roster: set[str], asof: str, note: str,
                          _df: pd.DataFrame | None = None) -> list[dict]:
    """Cluster-style insider rows from data/quiver/insiders.parquet.

    `_df` is an optional DataFrame override for unit tests (bypasses disk read).
    """
    if _df is not None:
        df = _df
    else:
        try:
            p = config.data_dir() / "quiver" / "insiders.parquet"
            if not p.exists():
                return []
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            log.debug("quiver insiders read failed", exc_info=True)
            return []

    if df.empty or "Ticker" not in df.columns:
        return []

    df = df[df["Ticker"].isin(roster)].copy()
    if df.empty:
        return []

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    # Use a 90-day window for the cluster
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=90)
    df = df[df["Date"] >= cutoff]
    if df.empty:
        return []

    # Re-filed Form 4s DUPLICATE in the quiver store (fileDate is part of the
    # collector's dedup key, so an amended filing lands as a second identical row) —
    # collapse them before clustering so a re-file never double-counts a trade.
    # Name is required as the disambiguator: without it two same-day, same-size
    # trades by DIFFERENT insiders would be wrongly merged, so the dedup is skipped
    # (degrade, don't guess).
    dedup_cols = [c for c in _QUIVER_DEDUP_COLS if c in df.columns]
    if "Name" in dedup_cols and {"Ticker", "Date", "Shares"} <= set(dedup_cols):
        df = df.drop_duplicates(subset=dedup_cols)

    # Open-market only: TransactionCode P (purchase) / S (sale). Grants, awards and
    # option exercises are compensation plumbing, not conviction — counting them as
    # buys is how a routine stock award reads as a giant insider buy. When the
    # column is absent (older store / test frames) keep the A/D behaviour, warn
    # once, and leave the note unchanged so the page never claims a filter that
    # did not run.
    global _TXN_CODE_WARNED
    if "TransactionCode" in df.columns:
        df = df[df["TransactionCode"].astype(str).str.upper().isin({"P", "S"})]
        if df.empty:
            return []
        note = note + " · open-market only"
    elif not _TXN_CODE_WARNED:
        log.warning("quiver insiders: TransactionCode column absent — falling back "
                    "to AcquiredDisposedCode only (grants/awards not excluded)")
        _TXN_CODE_WARNED = True

    # Classify: AcquiredDisposedCode A=Buy, D=Sell
    df["is_buy"] = df["AcquiredDisposedCode"].astype(str).str.upper() == "A"
    df["is_sell"] = df["AcquiredDisposedCode"].astype(str).str.upper() == "D"
    df["trade_usd"] = (pd.to_numeric(df.get("Shares", 0), errors="coerce").fillna(0)
                       * pd.to_numeric(df.get("PricePerShare", 0), errors="coerce").fillna(0))

    # Per-trade sanity (F1): positive price and share count, and a hard per-trade
    # USD cap — an absurd print (re-file artefact / fat finger) is DROPPED, never
    # clipped, so one bad row cannot mint a billion-dollar phantom cluster.
    if "PricePerShare" in df.columns and "Shares" in df.columns:
        px = pd.to_numeric(df["PricePerShare"], errors="coerce").fillna(0)
        sh = pd.to_numeric(df["Shares"], errors="coerce").fillna(0)
        df = df[(px > 0) & (sh > 0)]
    df = df[df["trade_usd"].abs() <= _TRADE_USD_CAP]
    if df.empty:
        return []

    rows: list[dict] = []
    for ticker, g in df.groupby("Ticker"):
        n_buys = int(g["is_buy"].sum())
        n_sells = int(g["is_sell"].sum())
        net_usd = round(float(g.loc[g["is_buy"], "trade_usd"].sum()
                              - g.loc[g["is_sell"], "trade_usd"].sum()), 0)
        action = "insider_buy_cluster" if n_buys > n_sells else (
            "insider_sell_cluster" if n_sells > n_buys else "insider_mixed")
        rows.append({
            "date": asof,
            "axis": "form4/quiver-insider",
            "type": "insider_cluster",
            "slug": "",
            "fund": "insiders",
            "ticker": str(ticker),
            "issuer": "",
            "action": action,
            "magnitude": net_usd,
            "unit": "usd",
            "asof_note": note,
            # bonus cluster fields
            "n_buys": n_buys,
            "n_sells": n_sells,
            "net_usd": net_usd,
            "roster_hit": True,
        })
    return rows


def _insider_rows_sec(roster: set[str], asof: str, note: str) -> list[dict]:
    """Cluster-style insider rows from data/sec_insider/insider.parquet (quarterly summary)."""
    try:
        p = config.data_dir() / "sec_insider" / "insider.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        log.debug("sec_insider read failed", exc_info=True)
        return []

    # sec_insider has (buy_usd, sell_usd, n_buys, n_sells, net_usd, quarter) indexed by ticker
    if df.empty:
        return []

    # Filter to roster tickers
    idx_col = df.index.name or "ticker"
    if hasattr(df.index, "name") and df.index.name:
        df = df[df.index.isin(roster)]
    elif "ticker" in df.columns:
        df = df[df["ticker"].isin(roster)]
    else:
        return []

    rows: list[dict] = []
    for ticker in df.index:
        r = df.loc[ticker]
        n_buys = int(r.get("n_buys", 0) or 0)
        n_sells = int(r.get("n_sells", 0) or 0)
        net_usd = float(r.get("net_usd", 0) or 0)
        action = "insider_buy_cluster" if n_buys > n_sells else (
            "insider_sell_cluster" if n_sells > n_buys else "insider_mixed")
        rows.append({
            "date": asof,
            "axis": "form4/sec-insider",
            "type": "insider_cluster",
            "slug": "",
            "fund": "insiders",
            "ticker": str(ticker),
            "issuer": "",
            "action": action,
            "magnitude": net_usd,
            "unit": "usd",
            "asof_note": note,
            "n_buys": n_buys,
            "n_sells": n_sells,
            "net_usd": net_usd,
            "roster_hit": True,
        })
    return rows


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

def build_wire(funds: dict[str, dict],
               lookback_13dg: int = _13DG_LOOKBACK_DAYS,
               today: date | None = None) -> tuple[list[dict], dict]:
    """Build the ownership event wire and filing-season clock.

    Parameters
    ----------
    funds : {slug: spec} roster from config.
    lookback_13dg : calendar-day window for 13D/G events.
    today : override for the filing-season clock (for tests).

    Returns
    -------
    (wire_rows, clock_dict)

    wire_rows : list of dicts each conforming to WIRE_SCHEMA (plus optional extras).
      Sorted descending by `date` (reverse-chronological). Within the same date,
      13f rows come first, 13dg second, insider third (natural ordering within each
      call). SM2-R3: no blending — each row's `axis` field marks its origin and
      its `asof_note` carries the single look-ahead-free timestamp for that axis.

    clock_dict : output of `filing_season_clock()` — includes `filed_pending` grid.
    """
    today = today or date.today()

    # Collect 13F rows
    wire_13f: list[dict] = []
    try:
        wire_13f = _13f_rows(funds)
    except Exception:  # noqa: BLE001
        log.warning("13F axis failed — continuing without it", exc_info=True)

    # Build roster from 13F data (for roster_hit on other axes)
    roster: set[str] = set()
    try:
        roster = _roster_tickers(funds)
    except Exception:  # noqa: BLE001
        log.debug("roster_tickers failed", exc_info=True)

    # Collect 13D/G rows
    wire_13dg: list[dict] = []
    try:
        wire_13dg = _13dg_rows(lookback_days=lookback_13dg, roster=roster)
    except Exception:  # noqa: BLE001
        log.warning("13D/G axis failed — continuing without it", exc_info=True)

    # Collect insider rows
    wire_insider: list[dict] = []
    try:
        wire_insider = _insider_rows(roster)
    except Exception:  # noqa: BLE001
        log.warning("insider axis failed — continuing without it", exc_info=True)

    # PER-AXIS caps, then concatenate — never blend. A single global newest-first
    # cap starves the slow axis: between filing windows the 13F deltas (all dated
    # ~May 15) would be entirely displaced by daily insider clusters, leaving the
    # 13F filter empty. Each axis keeps its own newest slice; insider clusters are
    # additionally ranked by |net_usd| so the 60 biggest clusters survive, not the
    # 60 most recent micro-prints.
    _CAP_13F, _CAP_13DG, _CAP_INSIDER = 80, 60, 60
    n_before = (len(wire_13f), len(wire_13dg), len(wire_insider))
    wire_13f = sorted(wire_13f, key=lambda r: r.get("date", ""), reverse=True)[:_CAP_13F]
    wire_13dg = sorted(wire_13dg, key=lambda r: r.get("date", ""), reverse=True)[:_CAP_13DG]
    wire_insider = sorted(wire_insider,
                          key=lambda r: abs(r.get("net_usd") or 0),
                          reverse=True)[:_CAP_INSIDER]
    all_rows = wire_13f + wire_13dg + wire_insider

    # Sort descending by date (reverse-chronological), preserving within-date order
    all_rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    log.info("build_wire: per-axis caps — emitting %d rows "
             "(13f %d->%d, 13dg %d->%d, insider %d->%d)",
             len(all_rows), n_before[0], len(wire_13f),
             n_before[1], len(wire_13dg), n_before[2], len(wire_insider))

    # Build fund_filings for the clock (latest period_end / filing_date per slug)
    fund_filings: dict[str, dict] = {}
    try:
        from engine.smart_money import _read_all, _snapshot_filing_date
        for slug in funds:
            snaps = _read_all(slug)
            if snaps:
                pe, fd, _ = snaps[-1]
                fund_filings[slug] = {"period_end": pe, "filing_date": fd}
    except Exception:  # noqa: BLE001
        log.debug("fund_filings build failed", exc_info=True)

    clock = filing_season_clock(funds, fund_filings=fund_filings, today=today)

    return all_rows, clock


def freshness_axes(wire_rows: list[dict], clock: dict) -> list[dict]:
    """Build the per-axis freshness descriptors for the desk payload.

    Returns a list of {key, label, asof, lag_note, tier} dicts for each distinct
    axis observed in the wire, plus short_volume and short_interest as separate axes
    (read directly from their stores, not from the wire).

    tier thresholds: green <= 11 days lag, amber <= 45 days, red > 45 days.
    SM2-R3: short_volume.asof and short_interest.settlement_date are SEPARATE keys
    in separate sub-dicts in the crowding payload — they must never share a column.
    These freshness descriptors serve the UX header, not the crowding table.
    """
    today = date.today()

    def _lag_days(asof_str: str | None) -> int | None:
        if not asof_str:
            return None
        try:
            return (today - pd.Timestamp(asof_str).date()).days
        except Exception:
            return None

    def _tier(lag: int | None) -> str:
        if lag is None:
            return "red"
        if lag <= 11:
            return "green"
        if lag <= 45:
            return "amber"
        return "red"

    # 13F: the honest as-of is the MAJORITY quarter on display, not the newest single
    # filing — one early filer must not paint the whole axis green while 50/51 funds
    # sit on last quarter's data. asof = the modal period_end across funds; the tier is
    # measured from that period_end (data age), and the note carries the bulk filing
    # date plus how many funds have already filed a newer quarter.
    axes_map: dict[str, dict] = {}
    fp = clock.get("filed_pending", [])
    pe_counts: dict[str, int] = {}
    for r in fp:
        pe = r.get("period_end") or ""
        if pe:
            pe_counts[pe] = pe_counts.get(pe, 0) + 1
    majority_pe = max(pe_counts, key=lambda k: (pe_counts[k], k)) if pe_counts else None
    maj_filings = [r["filing_date"] for r in fp
                   if r.get("filing_date") and r.get("period_end") == majority_pe]
    bulk_filed = max(maj_filings) if maj_filings else None
    n_ahead = sum(1 for r in fp
                  if r.get("period_end") and majority_pe and r["period_end"] > majority_pe)
    lag_13f = _lag_days(majority_pe)
    note = f"quarter-end data; bulk filed by {bulk_filed or 'unknown'} (~45-day lag)"
    if n_ahead:
        note += f"; {n_ahead}/{len(fp)} funds already filed a newer quarter"
    axes_map["13f"] = {
        "key": "13f",
        "label": "13F Holdings",
        "asof": majority_pe or "unavailable",
        "lag_note": note,
        "tier": _tier(lag_13f),
    }

    # 13D/G: latest date from wire
    dg_dates = [r["date"] for r in wire_rows if r.get("axis") == "13dg"]
    latest_dg = max(dg_dates) if dg_dates else None
    lag_dg = _lag_days(latest_dg)
    axes_map["13dg"] = {
        "key": "13dg",
        "label": "13D/G Filings",
        "asof": latest_dg or "unavailable",
        "lag_note": "5-business-day filing deadline (post-Feb-2024 rule)",
        "tier": _tier(lag_dg),
    }

    # Insider: from wire, derive the store label from the axis field
    ins_rows = [r for r in wire_rows if r.get("axis", "").startswith("form4")]
    latest_ins = max((r["date"] for r in ins_rows), default=None)
    ins_label = next((r["axis"] for r in ins_rows), "form4/quiver-insider")
    lag_ins = _lag_days(latest_ins)
    axes_map["insider"] = {
        "key": "insider",
        "label": "Insider Transactions",
        "asof": latest_ins or "unavailable",
        "lag_note": f"Form 4 ~2-day filing lag; source: {ins_label}",
        "tier": _tier(lag_ins),
    }

    # Short volume: read directly from the FINRA short-volume panel
    try:
        from engine.short_volume import load_panel
        sv_panel = load_panel()
        if sv_panel is not None and "date" in sv_panel.columns:
            sv_asof = str(pd.to_datetime(sv_panel["date"]).max().date())
        else:
            sv_asof = None
    except Exception:  # noqa: BLE001
        sv_asof = None
    lag_sv = _lag_days(sv_asof)
    axes_map["short_volume"] = {
        "key": "short_volume",
        "label": "Short Volume (FINRA daily)",
        "asof": sv_asof or "unavailable",
        "lag_note": "daily FINRA off-exchange; typically T+1 lag",
        "tier": _tier(lag_sv),
    }

    # Short interest: from the FINRA settlement file
    try:
        p = config.data_dir() / "finra" / "short_interest.parquet"
        if p.exists():
            si_df = pd.read_parquet(p)
            if "settlement_date" in si_df.columns and not si_df.empty:
                si_asof = str(pd.to_datetime(si_df["settlement_date"]).max().date())
            else:
                si_asof = None
        else:
            si_asof = None
    except Exception:  # noqa: BLE001
        si_asof = None
    lag_si = _lag_days(si_asof)
    axes_map["short_interest"] = {
        "key": "short_interest",
        "label": "Short Interest (FINRA bi-monthly)",
        "asof": si_asof or "unavailable",
        "lag_note": "bi-monthly settlement; ~2-week update cadence",
        "tier": _tier(lag_si),
    }

    # Return in display order: 13f, 13dg, insider, short_volume, short_interest
    return [axes_map[k] for k in ("13f", "13dg", "insider", "short_volume", "short_interest")]
