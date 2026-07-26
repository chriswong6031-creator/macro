"""Sell-side research EVENT STREAM (研报) — rating / target-price / EPS revisions (W1 CNH).

A different PLANE from collectors/china_analyst.py, which stores the AGGREGATE
consensus SNAPSHOT (stock_profit_forecast_em: current coverage counts and the mean
forecast per name). This collector stores the per-REPORT event tape: every published
report in a trailing window with the house's rating, the house's PREVIOUS rating, the
target-price band and the EPS forecasts. Snapshot vs tape — no overlap, and the tape is
the only one of the two that can ever answer "what CHANGED, when".

Two stores under data/china_reports/:
  reports.parquet    one row per report (dedup infoCode keep-LAST — a same-day re-pull
                     corrects; a late-arriving field never duplicates the report). Rows
                     carry fetched_at ("last observed") AND first_seen ("first observed",
                     preserved through every correction).
  aggregates.parquet one row per publish DATE (dedup date keep-LAST), recomputed FROM
                     THE STORE after every append so the numbers always describe what is
                     actually on disk rather than what one night's page happened to see.
                     A date is only written when tonight's pull can prove it was fetched
                     COMPLETELY — see aggregate_rows' boundary rule.
Both stores are written through a tmp sibling + os.replace, and an existing-but-
unreadable store ABORTS the append rather than being replaced by tonight's rows.

CONTEXT / INPUT TIER ONLY. Nothing is scored, ranked or promoted, and there is no
dedicated surface — the leg appears only as a pending-tier inventory row in the
signal-lab scorecard (engine/china_signal_lab.py, rendered on china_altdata with a 待验
badge). REDISTRIBUTION LIMIT: machine fields only — pdfUrl/attachments/report bodies are
NEVER fetched.

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
import os
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
    "fetched_at",            # LAST observation of this info_code
    "first_seen",            # FIRST observation — never overwritten by a correction
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


def _read_store(path: Path, columns: tuple[str, ...]) -> pd.DataFrame | None:
    """The store reindexed to ``columns``, an EMPTY frame when ABSENT, None when UNREADABLE.

    Three different facts, which is why this is not a plain try/except returning an
    empty frame: "absent" is the first night (append freely), while "present but
    unreadable" means the accrued history is still on disk and we simply cannot see
    it — taking the empty-store branch there would replace all of it with tonight's
    handful of rows. The caller ABORTS on None.
    """
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        return pd.read_parquet(path).reindex(columns=list(columns))
    except Exception as e:  # noqa: BLE001
        log.error("china_reports: %s is present but UNREADABLE (%s)", path.name, e)
        return None


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` via a tmp sibling + os.replace — never a truncated store.

    The asia lane runs under a hard job kill that has fired mid-chain before; a
    to_parquet() straight onto the live path turns that kill into a corrupt file.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — never leave a half-written sibling behind
        tmp.unlink(missing_ok=True)
        raise


def _restore_first_seen(merged: pd.DataFrame, existing: pd.DataFrame,
                        key: list[str]) -> pd.DataFrame:
    """Carry each key's ORIGINAL first_seen through the keep-LAST merge. Pure.

    fetched_at means "last observed" and advances on every correction; first_seen
    means "first observed" and must not. It is the one question an append-only PIT
    store exists to answer, and a keep-LAST dedup would otherwise overwrite it every
    time a report's target price or EPS is corrected. Keys absent from ``existing``
    keep tonight's stamp.
    """
    if existing.empty or "first_seen" not in existing.columns:
        return merged
    prior = existing[[*key, "first_seen"]].astype(str)
    prior = prior[prior["first_seen"].str.strip().ne("")
                  & ~prior["first_seen"].isin(("nan", "None", "NaT", "<NA>"))]
    if prior.empty:
        return merged
    prior = prior.sort_values("first_seen").drop_duplicates(subset=key, keep="first")
    lookup = dict(zip(zip(*(prior[c] for c in key)), prior["first_seen"]))
    out = merged.copy()
    out["first_seen"] = [
        lookup.get(k, cur)
        for k, cur in zip(zip(*(out[c].astype(str) for c in key)), out["first_seen"])
    ]
    return out


def load_reports() -> pd.DataFrame:
    """Existing reports.parquet, or an empty frame with the canonical schema.

    A present-but-unreadable store also reads as empty HERE — a reader must not
    crash — but write_reports() checks readability separately and aborts, so the
    empty frame can never be written back over the real one.
    """
    df = _read_store(_reports_path(), _COLUMNS)
    return pd.DataFrame(columns=list(_COLUMNS)) if df is None else df


def write_reports(rows: list[dict], keep_existing: bool = False) -> int:
    """Append report rows, dedup info_code keep-LAST. Returns net-new. Never raises.

    ``keep_existing`` flips the resolution to keep-FIRST for info_codes ALREADY on
    disk — the manual backfill path. A row recovered months later must never overwrite
    the one observed live on the night it published, nor flip that row's backfill flag.

    first_seen is carried through the merge, so a correction advances fetched_at
    without destroying the first-observation time. An existing-but-UNREADABLE
    reports.parquet ABORTS the append (returns 0, file left in place for manual
    recovery) rather than being replaced by tonight's window.
    """
    if not rows:
        return 0
    try:
        existing = _read_store(_reports_path(), _COLUMNS)
        if existing is None:
            log.error("china_reports: ABORTING the reports.parquet append — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            return 0
        new_df = pd.DataFrame(rows).reindex(columns=list(_COLUMNS))
        new_df["first_seen"] = new_df["first_seen"].fillna(new_df["fetched_at"])
        if keep_existing and not existing.empty:
            known = set(existing["info_code"].astype(str))
            new_df = new_df[~new_df["info_code"].astype(str).isin(known)]
            if new_df.empty:
                return 0
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["info_code"], keep="last")
            net_new = len(merged)
        else:
            pre = existing["info_code"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["info_code"], keep="last")
            merged = _restore_first_seen(merged, existing, ["info_code"])
            net_new = merged["info_code"].nunique() - pre
        merged = merged.sort_values(["publish_date", "info_code"],
                                    na_position="last").reset_index(drop=True)
        _atomic_write(merged, _reports_path())
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_reports.write_reports failed: %s", e)
        return 0


def load_aggregates() -> pd.DataFrame:
    """Existing aggregates.parquet, or an empty canonical frame (see load_reports)."""
    df = _read_store(_aggregates_path(), _AGG_COLUMNS)
    return pd.DataFrame(columns=list(_AGG_COLUMNS)) if df is None else df


def write_aggregates(rows: list[dict]) -> int:
    """Append daily aggregate rows, dedup date keep-LAST. Returns rows written.

    An unreadable store aborts the append exactly as write_reports does.
    """
    if not rows:
        return 0
    try:
        existing = _read_store(_aggregates_path(), _AGG_COLUMNS)
        if existing is None:
            log.error("china_reports: ABORTING the aggregates.parquet append — the "
                      "accrued store is unreadable and is left untouched for manual "
                      "recovery")
            return 0
        new_df = pd.DataFrame(rows).reindex(columns=list(_AGG_COLUMNS))
        merged = new_df if existing.empty else pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date").reset_index(drop=True)
        _atomic_write(merged, _aggregates_path())
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
                   allow_true_zero: bool = True, boundary_date: str = "") -> list[dict]:
    """Recompute the per-date aggregate FROM THE STORE for ``dates``. Pure.

    A daily aggregate is a permanent fact: the rolling window moves forward, so a date
    that falls out of it is never re-pulled and whatever was written for it stands
    forever. Two guards therefore keep OUR OWN truncation out of the tape:

      ``boundary_date``   the OLDEST publish date tonight's fetch actually reached.
                          The vendor serves publishDate DESC, so a capped/failed pull
                          truncates that day PART-WAY through its reports — its stored
                          rows are an undercount, not the day's total. Dates ON OR
                          BEFORE the boundary are SKIPPED; only strictly newer ones,
                          which the DESC order guarantees were served in full, get a
                          row. Empty ('' — a clean pull) skips nothing.
      ``allow_true_zero`` a date with no rows on disk yields a 0-report row only when
                          the night's fetch completed cleanly. After a partial pull the
                          zero would be an artifact of our truncation, so the date is
                          skipped and the gap stays visible instead of becoming fact.

    A suppressed date inside the current window can still earn its aggregate on a later
    clean night; one that ages out of the window simply never gets one, which is the
    honest outcome — we never observed it completely.
    """
    out: list[dict] = []
    for date in dates:
        if boundary_date and date <= boundary_date:
            continue
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
                 backfill: bool = False) -> tuple[list[dict], int, int, bool, int]:
    """Page through one [begin, end] window.

    Returns (rows, ok_pages, failed_pages, capped, empty_key_rows). ``capped`` means
    tonight's view of the window is INCOMPLETE for any reason — the page cap, the
    wall-clock guard, or a vendor envelope we could not read the page count out of —
    and the caller must not stamp the window's oldest fetched day as a complete fact.
    """
    rows: list[dict] = []
    ok_pages = failed_pages = empty_key = 0
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
        parsed = [parse_report_row(r, fetched_at, current_year, backfill) for r in data]
        # info_code IS the dedup key: an empty one collapses every keyless row of the
        # night into a SINGLE stored row, so they are dropped here and counted instead.
        keyed = [r for r in parsed if r["info_code"]]
        empty_key += len(parsed) - len(keyed)
        rows.extend(keyed)
        raw_total = payload.get("TotalPage")
        try:
            total_pages = int(raw_total)
        except (TypeError, ValueError):
            # A vendor rename of this field used to read as "1 page" — the plane would
            # silently shrink to one page a night while still reporting a CLEAN pull.
            capped = True
            log.warning(
                "china_reports: [%s..%s] page %d carried no usable 'TotalPage' (got %r) "
                "— treating the window as CAPPED, not complete; check the envelope for "
                "a renamed page-count field", begin, end, page, raw_total,
            )
            break
        if page >= total_pages:
            break
        if page >= _PAGE_CAP:
            capped = True
            log.warning(
                "china_reports: [%s..%s] has %d pages but the nightly cap is %d — "
                "%d pages NOT fetched tonight. DESC ordering means the missing pages are "
                "the window's OLDEST day, so its aggregate is suppressed tonight (it can "
                "still land on a later clean night while the day stays in the window)",
                begin, end, total_pages, _PAGE_CAP, total_pages - _PAGE_CAP,
            )
            break
        page += 1
    if empty_key:
        log.warning("china_reports: %d fetched row(s) carried no infoCode — SKIPPED, not "
                    "stored: the dedup key is info_code, so storing them would collapse "
                    "the whole batch into one row", empty_key)
    return rows, ok_pages, failed_pages, capped, empty_key


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

    rows, ok_pages, failed_pages, capped, empty_key = _pull_window(
        session, begin, end, fetched_at, t0)
    if ok_pages == 0:
        raise RuntimeError(
            f"china_reports: every page of [{begin}..{end}] failed at transport level"
        )

    n_new = write_reports(rows)
    # Aggregates are recomputed FROM THE STORE (not from tonight's page buffer) so the
    # counts describe everything on disk for those dates, including rows collected on
    # previous nights within the same rolling window.
    clean = failed_pages == 0 and not capped
    # After anything less than a clean pull, the OLDEST publish date we reached was
    # truncated mid-count by the DESC page order — exclude it and everything older.
    # With no rows at all, nothing tonight is provably complete, so `end` suppresses
    # the whole window.
    boundary = "" if clean else min(
        (r["publish_date"] for r in rows if r["publish_date"]), default=end)
    if not clean:
        log.warning("china_reports: partial/capped pull — no aggregate row for [%s..%s] "
                    "dates on or before %s (gap logged, not written as fact)",
                    begin, end, boundary)
    store = _read_store(_reports_path(), _COLUMNS)
    if store is None:
        # Recomputing "from the store" when the store cannot be read would stamp a
        # window of zeros over real daily facts.
        log.error("china_reports: reports.parquet unreadable — aggregates NOT recomputed")
        n_agg = 0
    else:
        n_agg = write_aggregates(aggregate_rows(
            store, _window_dates(begin, end), fetched_at, clean, boundary))

    codes = {r["code"] for r in rows if r["code"]}
    log.info("china_reports: window=[%s..%s] pages_ok=%d pages_failed=%d rows=%d "
             "empty_key=%d net_new=%d names=%d aggregates=%d%s",
             begin, end, ok_pages, failed_pages, len(rows), empty_key, n_new, len(codes),
             n_agg, " [CAPPED]" if capped else "")
    # n_nulls: rows dropped for an empty infoCode. There is no per-name resolution step
    # on this plane, so it is the only coverage null it can produce — the column is kept
    # for schema uniformity with the other three W1 sentinels.
    return {"n_new": n_new, "n_fetched": len(rows), "n_failed": failed_pages,
            "n_nulls": empty_key, "universe": len(codes), "shard": ok_pages}


def backfill(start: str, end: str) -> int:
    """MANUAL range backfill in 7-day windows — never called from the adapter path.

    Rows are stamped backfill=True so the PIT tape can always separate "observed on
    the night it published" from "recovered later", and they are written keep-FIRST
    (write_reports(keep_existing=True)): a recovered row can never overwrite one that
    was observed live, nor flip that row's backfill flag to True.

    Aggregates are NOT written here. A backfilled row that lands on a date still
    inside the nightly rolling window DOES fold into that window's aggregate on the
    next clean nightly recompute — those are real reports and the aggregate is a
    recompute from the store, not an append. A backfilled date OUTSIDE any future
    window simply never gets an aggregate row: it was never observed live, and
    manufacturing one here would blur exactly the distinction the flag exists for.
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
        rows, ok_pages, failed_pages, _, empty_key = _pull_window(
            session, lo.isoformat(), hi.isoformat(), fetched_at, t0, backfill=True)
        n = write_reports(rows, keep_existing=True)
        total += n
        log.info("china_reports backfill: [%s..%s] pages_ok=%d failed=%d rows=%d "
                 "empty_key=%d net_new=%d",
                 lo, hi, ok_pages, failed_pages, len(rows), empty_key, n)
        lo = hi + timedelta(days=1)
    log.info("china_reports backfill: %d net-new rows [%s..%s]", total, start, end)
    return total


# ------------------------------------------------------------------ adapter --

class ChinaReportsAdapter(Adapter):
    """Sell-side rating/TP/EPS revision stream (W1 CNH) — context/input tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_reports`` starts with ``china`` so it is auto-assigned to the asia lane.

    fetch() returns a COVERAGE sentinel rather than a bare count, so
    data/china_reports/refresh.parquet is a readable run ledger: n_new/n_fetched say
    what landed, n_failed counts pages that broke at transport, and n_nulls counts rows
    dropped for an empty infoCode (kept for schema uniformity with the other three W1
    sentinels — this plane has no per-name resolution step to fail). What the sentinel
    does NOT prove is that the window was fetched completely: ``shard`` is the number of
    pages that answered, and whether the pull was capped lives in the log line and in
    which dates aggregates.parquet gained a row.
    """

    name = "china_reports"
    group = GROUP
    stale_after_days = 4

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent).
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in
             ("n_new", "n_fetched", "n_failed", "n_nulls", "universe", "shard")},
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
