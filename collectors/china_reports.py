"""Sell-side research EVENT STREAM (研报) — rating / target-price / EPS revisions (W1 CNH).

A different PLANE from collectors/china_analyst.py, which stores the AGGREGATE
consensus SNAPSHOT (stock_profit_forecast_em: current coverage counts and the mean
forecast per name). This collector stores the per-REPORT event tape: every published
report in a trailing window with the house's rating, the house's PREVIOUS rating, the
target-price band and the EPS forecasts. Snapshot vs tape — no overlap, and the tape is
the only one of the two that can ever answer "what CHANGED, when".

Two stores under data/china_reports/:
  reports.parquet    one row per report (dedup infoCode keep-LAST — a same-day re-pull
                     corrects; a late-arriving field never duplicates the report).
  aggregates.parquet one row per publish DATE (dedup date keep-LAST), recomputed FROM
                     THE STORE after every append so the numbers always describe what is
                     actually on disk rather than what one night's page happened to see.

CONTEXT / INPUT TIER ONLY. Nothing is scored, ranked or promoted; the leg registers as
tier="pending" in engine/china_signal_lab.py (collected + accruing). REDISTRIBUTION
LIMIT: machine fields only — pdfUrl/attachments/report bodies are NEVER fetched.

VERIFIED ENDPOINT (live 2026-07-25, this runner):
  GET https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=100&industry=*
      &rating=*&ratingChange=*&beginTime=<D-3>&endTime=<D>&pageNo=<n>&fields=&qType=0
      &orgCode=&code=*&rcode=&p=<n>&pageNum=<n>&pageNumber=<n>
  All four page aliases are kept in sync — the API's own defensive idiom; sending only
  pageNo has been observed to be ignored by some deployments of this endpoint.
  Envelope: {hits, size, data, TotalPage, pageNo, currentYear}.

RATING SEMANTICS: the vendor's own ``ratingChange`` code is stored RAW for audit and
NEVER interpreted — its semantics are unverified (the live cross-tab shows 3 on plain
maintains and 2 on initiations, which is suggestive, not established). Our own
change_class() is derived from EastMoney's ORDINAL rating scale (verified live:
2=增持, 3=买入, higher = more bullish) and is fixture-pinned.

Politeness + budget: ≥1.0 s + jitter before EVERY request, 8-page nightly cap with a
LOUD log when the window has more (no silent capping), and a ~100 s in-collector
wall-clock guard. A 0-row day is a success; RuntimeError is raised only when every page
failed at transport level.
"""
from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_reports")

# ------------------------------------------------------------------ constants --

GROUP = "china_reports"
_ENDPOINT = "https://reportapi.eastmoney.com/report/list"
_REFERER = "https://data.eastmoney.com/report/"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_WINDOW_DAYS = 3        # nightly window is [D-3, D]: idempotent re-pull heals late arrivals
_PAGE_SIZE = 100
_PAGE_CAP = 8           # per night; a deeper window is logged loudly, never silently dropped
_PACE_S = 1.0
_JITTER_S = 0.3
_TIMEOUT = (10, 20)
_BUDGET_S = 100.0
_BACKFILL_WINDOW_DAYS = 7   # manual CLI only — never on the adapter path

_COLUMNS = (
    "info_code",             # EastMoney infoCode — the natural PIT key
    "publish_date",          # YYYY-MM-DD
    "code",
    "name",
    "org",                   # orgSName (issuing house)
    "title",
    "em_rating",             # emRatingName (买入 / 增持 / …)
    "em_rating_value",       # ordinal, stored as text
    "last_em_rating",
    "last_em_rating_value",
    "rating_change_raw",     # vendor code — AUDIT ONLY, semantics unverified, never read
    "change_class",          # OURS: upgrade / downgrade / maintain / no_prior / unrated
    "target_price_t",        # indvAimPriceT ('' allowed — most CN reports carry no target)
    "target_price_l",
    "eps_this",
    "eps_next",
    "forecast_year_base",    # currentYear from the envelope
    "month_count",           # count = 近一月个股研报数
    "market",
    "backfill",              # True only for rows written by the manual --backfill CLI
    "fetched_at",
)

_AGG_COLUMNS = (
    "date", "n_reports", "n_names", "n_orgs",
    "n_upgrade", "n_downgrade", "n_maintain", "n_no_prior", "n_unrated",
    "n_with_target", "fetched_at",
)


# ------------------------------------------------------------------ paths / stores --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _reports_path() -> Path:
    return _dir() / "reports.parquet"


def _aggregates_path() -> Path:
    return _dir() / "aggregates.parquet"


def load_reports() -> pd.DataFrame:
    path = _reports_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_reports: could not read reports.parquet: %s", e)
    return pd.DataFrame(columns=list(_COLUMNS))


def write_reports(rows: list[dict]) -> int:
    """Append report rows, dedup info_code keep-LAST. Returns net-new. Never raises."""
    if not rows:
        return 0
    try:
        new_df = pd.DataFrame(rows).reindex(columns=list(_COLUMNS))
        existing = load_reports()
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["info_code"], keep="last")
            net_new = len(merged)
        else:
            pre = existing["info_code"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["info_code"], keep="last")
            net_new = merged["info_code"].nunique() - pre
        merged = merged.sort_values(["publish_date", "info_code"],
                                    na_position="last").reset_index(drop=True)
        merged.to_parquet(_reports_path(), index=False)
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_reports.write_reports failed: %s", e)
        return 0


def load_aggregates() -> pd.DataFrame:
    path = _aggregates_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_AGG_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_reports: could not read aggregates.parquet: %s", e)
    return pd.DataFrame(columns=list(_AGG_COLUMNS))


def write_aggregates(rows: list[dict]) -> int:
    """Append daily aggregate rows, dedup date keep-LAST. Returns rows written."""
    if not rows:
        return 0
    try:
        new_df = pd.DataFrame(rows).reindex(columns=list(_AGG_COLUMNS))
        existing = load_aggregates()
        merged = new_df if existing.empty else pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date").reset_index(drop=True)
        merged.to_parquet(_aggregates_path(), index=False)
        return len(new_df)
    except Exception as e:  # noqa: BLE001
        log.error("china_reports.write_aggregates failed: %s", e)
        return 0


# ------------------------------------------------------------------ pure parsers --

def change_class(em_rating_value, last_em_rating_value) -> str:
    """Rating-move class from EastMoney's ORDINAL rating values. Pure, never raises.

    The scale is verified live: 2=增持, 3=买入 — higher is more bullish. Classes:

      'unrated'    the current report carries no usable rating value
      'no_prior'   the house has no usable previous rating (initiation / re-coverage)
      'upgrade'    current > previous
      'downgrade'  current < previous
      'maintain'   current == previous

    Non-numeric values are treated as unusable in the same order (current first),
    so a vendor schema drift degrades to 'unrated'/'no_prior' rather than crashing.
    """
    cur = str(em_rating_value if em_rating_value is not None else "").strip()
    last = str(last_em_rating_value if last_em_rating_value is not None else "").strip()
    if not cur:
        return "unrated"
    try:
        cur_i = int(float(cur))
    except (TypeError, ValueError):
        return "unrated"
    if not last:
        return "no_prior"
    try:
        last_i = int(float(last))
    except (TypeError, ValueError):
        return "no_prior"
    if cur_i > last_i:
        return "upgrade"
    if cur_i < last_i:
        return "downgrade"
    return "maintain"


def _text(value) -> str:
    """None-safe text (keeps a literal 0, which `or ''` would silently blank)."""
    return "" if value is None else str(value)


def _date_part(value) -> str:
    """'2026-07-25 00:00:00.000' → '2026-07-25'; '' when unparseable. Pure."""
    s = _text(value).strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


def parse_report_row(raw: dict, fetched_at: str, current_year="", backfill: bool = False) -> dict:
    """One /report/list row → one canonical reports.parquet row. Pure (no I/O)."""
    return {
        "info_code": _text(raw.get("infoCode")),
        "publish_date": _date_part(raw.get("publishDate")),
        "code": _text(raw.get("stockCode")),
        "name": _text(raw.get("stockName")),
        "org": _text(raw.get("orgSName")),
        "title": _text(raw.get("title")),
        "em_rating": _text(raw.get("emRatingName")),
        "em_rating_value": _text(raw.get("emRatingValue")),
        "last_em_rating": _text(raw.get("lastEmRatingName")),
        "last_em_rating_value": _text(raw.get("lastEmRatingValue")),
        "rating_change_raw": _text(raw.get("ratingChange")),
        "change_class": change_class(raw.get("emRatingValue"), raw.get("lastEmRatingValue")),
        "target_price_t": _text(raw.get("indvAimPriceT")),
        "target_price_l": _text(raw.get("indvAimPriceL")),
        "eps_this": _text(raw.get("predictThisYearEps")),
        "eps_next": _text(raw.get("predictNextYearEps")),
        "forecast_year_base": _text(current_year),
        "month_count": _text(raw.get("count")),
        "market": _text(raw.get("market")),
        "backfill": bool(backfill),
        "fetched_at": fetched_at,
    }


def aggregate_rows(store: pd.DataFrame, dates: list[str], fetched_at: str,
                   allow_true_zero: bool = True) -> list[dict]:
    """Recompute the per-date aggregate FROM THE STORE for ``dates``. Pure.

    A date with no rows on disk yields a TRUE-ZERO row only when ``allow_true_zero``
    — i.e. the night's fetch succeeded completely. After a partial/capped pull the
    zero would be an artifact of our own truncation, so the date is SKIPPED and the
    gap is left visible instead of being written as fact.
    """
    out: list[dict] = []
    for date in dates:
        day = (store[store["publish_date"] == date]
               if not store.empty and "publish_date" in store.columns
               else pd.DataFrame(columns=list(_COLUMNS)))
        if day.empty and not allow_true_zero:
            continue
        classes = day["change_class"].tolist() if not day.empty else []
        # fillna BEFORE the string cast: a NaN target (possible only on a frame
        # reindexed from an older schema) would otherwise stringify to "nan" and be
        # counted as a real target price.
        n_with_target = 0 if day.empty else int(
            day["target_price_t"].fillna("").astype(str).str.strip().ne("").sum())
        out.append({
            "date": date,
            "n_reports": len(day),
            "n_names": int(day["code"].nunique()) if not day.empty else 0,
            "n_orgs": int(day["org"].nunique()) if not day.empty else 0,
            "n_upgrade": classes.count("upgrade"),
            "n_downgrade": classes.count("downgrade"),
            "n_maintain": classes.count("maintain"),
            "n_no_prior": classes.count("no_prior"),
            "n_unrated": classes.count("unrated"),
            "n_with_target": n_with_target,
            "fetched_at": fetched_at,
        })
    return out


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {"User-Agent": _UA, "Referer": _REFERER}


def _pace() -> None:
    """Politeness sleep before EVERY request: ≥1.0 s to the single upstream host."""
    time.sleep(_PACE_S + random.uniform(0.0, _JITTER_S))  # noqa: S311


def _clock() -> float:
    """Monotonic seconds. Indirected so the wall-clock guard is unit-testable."""
    return time.monotonic()


def _page_url(begin: str, end: str, page: int) -> str:
    """The window URL for one page. All four page aliases stay in sync (vendor idiom)."""
    return (f"{_ENDPOINT}?industryCode=*&pageSize={_PAGE_SIZE}&industry=*&rating=*"
            f"&ratingChange=*&beginTime={begin}&endTime={end}&pageNo={page}&fields="
            f"&qType=0&orgCode=&code=*&rcode=&p={page}&pageNum={page}&pageNumber={page}")


def _fetch_page(session, begin: str, end: str, page: int) -> dict:
    """Paced GET of one window page → parsed JSON. Raises on transport/HTTP failure."""
    _pace()
    r = session.get(_page_url(begin, end, page), headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from reportapi.eastmoney.com")
    r.raise_for_status()
    return r.json()


def _window(days: int = _WINDOW_DAYS) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=days)).isoformat(), today.isoformat()


def _window_dates(begin: str, end: str) -> list[str]:
    start = datetime.fromisoformat(begin).date()
    stop = datetime.fromisoformat(end).date()
    return [(start + timedelta(days=i)).isoformat() for i in range((stop - start).days + 1)]


def _pull_window(session, begin: str, end: str, fetched_at: str, t0: float,
                 backfill: bool = False) -> tuple[list[dict], int, int, bool]:
    """Page through one [begin, end] window. Returns (rows, ok_pages, failed_pages, capped)."""
    rows: list[dict] = []
    ok_pages = failed_pages = 0
    capped = False
    page = 1
    while page <= _PAGE_CAP:
        if _clock() - t0 > _BUDGET_S:
            capped = True
            log.warning("china_reports: %.0fs wall-clock guard hit at page %d of "
                        "[%s..%s] — keeping %d rows", _BUDGET_S, page, begin, end, len(rows))
            break
        try:
            payload = _fetch_page(session, begin, end, page)
        except Exception as e:  # noqa: BLE001 — per-page isolation
            failed_pages += 1
            log.warning("china_reports: [%s..%s] page %d failed: %s", begin, end, page, e)
            break
        ok_pages += 1
        current_year = payload.get("currentYear")
        data = [r for r in (payload.get("data") or []) if isinstance(r, dict)]
        rows.extend(parse_report_row(r, fetched_at, current_year, backfill) for r in data)
        try:
            total_pages = int(payload.get("TotalPage") or 1)
        except (TypeError, ValueError):
            total_pages = 1
        if page >= total_pages:
            break
        if page >= _PAGE_CAP:
            capped = True
            log.warning(
                "china_reports: [%s..%s] has %d pages but the nightly cap is %d — "
                "%d pages NOT fetched tonight (the rolling window re-pull heals the tail)",
                begin, end, total_pages, _PAGE_CAP, total_pages - _PAGE_CAP,
            )
            break
        page += 1
    return rows, ok_pages, failed_pages, capped


# ------------------------------------------------------------------ nightly refresh --

def refresh() -> dict:
    """Pull the trailing [D-3, D] report window, append, recompute daily aggregates.

    Raises RuntimeError only when NO page fetched successfully (total transport
    failure — the honest circuit-breaker signal). A successful fetch that returned
    zero reports is a normal quiet day: n_new=0 and true-zero aggregate rows.

    Returns the sentinel counters the adapter writes to data/china_reports/refresh.parquet.
    """
    import requests  # lazy

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    begin, end = _window()
    session = requests.Session()

    rows, ok_pages, failed_pages, capped = _pull_window(session, begin, end, fetched_at, t0)
    if ok_pages == 0:
        raise RuntimeError(
            f"china_reports: every page of [{begin}..{end}] failed at transport level"
        )

    n_new = write_reports(rows)
    # Aggregates are recomputed FROM THE STORE (not from tonight's page buffer) so the
    # counts describe everything on disk for those dates, including rows collected on
    # previous nights within the same rolling window.
    allow_true_zero = failed_pages == 0 and not capped
    if not allow_true_zero:
        log.warning("china_reports: partial/capped pull — true-zero aggregate rows "
                    "suppressed for [%s..%s] (gap logged, not written as fact)", begin, end)
    n_agg = write_aggregates(
        aggregate_rows(load_reports(), _window_dates(begin, end), fetched_at, allow_true_zero)
    )

    codes = {r["code"] for r in rows if r["code"]}
    log.info("china_reports: window=[%s..%s] pages_ok=%d pages_failed=%d rows=%d "
             "net_new=%d names=%d aggregates=%d%s",
             begin, end, ok_pages, failed_pages, len(rows), n_new, len(codes), n_agg,
             " [CAPPED]" if capped else "")
    return {"n_new": n_new, "n_fetched": len(rows), "n_failed": failed_pages,
            "universe": len(codes), "shard": ok_pages}


def backfill(start: str, end: str) -> int:
    """MANUAL range backfill in 7-day windows — never called from the adapter path.

    Rows are stamped backfill=True so the PIT tape can always separate "observed on
    the night it published" from "recovered later". Aggregates are NOT written here:
    a backfilled day was never observed live, and stamping it into the daily tape
    would blur exactly that distinction.
    """
    import requests  # lazy

    session = requests.Session()
    fetched_at = datetime.now(timezone.utc).isoformat()
    total = 0
    lo = datetime.fromisoformat(start).date()
    stop = datetime.fromisoformat(end).date()
    while lo <= stop:
        hi = min(lo + timedelta(days=_BACKFILL_WINDOW_DAYS - 1), stop)
        t0 = _clock()  # per-window budget: a manual backfill still paces politely
        rows, ok_pages, failed_pages, _ = _pull_window(
            session, lo.isoformat(), hi.isoformat(), fetched_at, t0, backfill=True)
        n = write_reports(rows)
        total += n
        log.info("china_reports backfill: [%s..%s] pages_ok=%d failed=%d rows=%d net_new=%d",
                 lo, hi, ok_pages, failed_pages, len(rows), n)
        lo = hi + timedelta(days=1)
    log.info("china_reports backfill: %d net-new rows [%s..%s]", total, start, end)
    return total


# ------------------------------------------------------------------ adapter --

class ChinaReportsAdapter(Adapter):
    """Sell-side rating/TP/EPS revision stream (W1 CNH) — context/input tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_reports`` starts with ``china`` so it is auto-assigned to the asia lane.
    fetch() returns a COVERAGE sentinel — not a bare count — so
    data/china_reports/refresh.parquet is a readable run ledger.
    """

    name = "china_reports"
    group = GROUP
    stale_after_days = 4

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent).
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in ("n_new", "n_fetched", "n_failed", "universe", "shard")},
            index=[idx],
        )
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                    help="MANUAL range backfill YYYY-MM-DD YYYY-MM-DD (never nightly)")
    a = ap.parse_args()
    if a.backfill:
        print(f"china_reports backfill: {backfill(a.backfill[0], a.backfill[1])} net-new rows")
        return 0
    s = refresh()
    print(f"china_reports: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
