"""CCTV 新闻联播 archive backfill — W4 prerequisite for the Qualitative-Intelligence Upgrade.

Iterates 2016-02-03 → today (NEWEST-FIRST so decision-relevant recent years land first),
storing per-item broadcast rows in monthly parquet shards under the archive dir.

Usage
-----
  # Full backfill (newest → oldest), resumable:
  python scripts/backfill_cctv_archive.py [--out-dir PATH]

  # Just a single date (useful for testing):
  python scripts/backfill_cctv_archive.py --date 20250115 [--out-dir PATH]

  # Audit missing dates + stub-rate per year:
  python scripts/backfill_cctv_archive.py --gap-audit [--out-dir PATH]

  # Retry dates whose ALL rows were stubs/errors:
  python scripts/backfill_cctv_archive.py --repair [--out-dir PATH]

  # Probe a single sample year to estimate size before full commit:
  python scripts/backfill_cctv_archive.py --sample-year 2025 [--out-dir PATH]

Storage layout
--------------
  <out-dir>/YYYY-MM.parquet   — monthly shards (zstd)
  <out-dir>/backfill.log      — append-only progress log

Shard schema
------------
  date         : str  "YYYY-MM-DD"
  order_idx    : int  broadcast order (0 = 联播头条 / lead item)
  title        : str
  content      : str
  fetch_status : str  "ok" | "empty" | "stub" | "error"
  fetched_at   : str  ISO-8601 UTC
  listing_title: str  real item title from the day's listing page, recorded on
                      stub/error rows ("" elsewhere / when the listing fetch
                      fails). When the fetched row count matches the listing,
                      each row carries its own aligned title; otherwise (e.g. a
                      single-row whole-day stub) each stub/error row carries the
                      FULL newline-joined listing. Stub rows' own title/content
                      hold CCTV's error text, so this column is what lets
                      downstream day-level provability checks (see
                      _archive_day_items in backfill_china_communiques.py) test
                      real titles on stubbed days.

Stub detection
--------------
  akshare occasionally returns a single row with content like
  "对不起，可能是网络原因或无此页面" for old dates with page rot.
  These are stored (order survives) with fetch_status="stub" so they
  can be retried with --repair later.

Hang protection
---------------
  ak.news_cctv has no timeout and was measured live (2026-07-06) hanging
  indefinitely mid-run. Every call runs under a daemon-thread hard timeout
  (CCTV_FETCH_TIMEOUT_S); a timed-out day is stored as an error row without
  retry (a hung URL hangs again — --repair retries it later).
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "china_news" / "cctv_archive"

HISTORY_START = date(2016, 2, 3)   # akshare docstring: reliable from this date
STUB_SIGNATURES = (
    "对不起",
    "可能是网络原因",
    "无此页面",
    "404",
    "页面不存在",
)

# Hard ceiling on one day's full-transcript fetch. Measured live 2026-07-06: an
# akshare news_cctv call with no timeout hung the gapfill lane indefinitely
# (log ended mid-tqdm; the process sat idle for days). Same value as
# backfill_china_communiques.CCTV_FETCH_TIMEOUT_S (#1858).
CCTV_FETCH_TIMEOUT_S = 300

# Xinwen Lianbo per-day listing page — used only to recover real item titles
# for stub/error rows (1 request per stub/error day).
CCTV_LISTING_URL = "https://tv.cctv.com/lm/xwlb/day/{ds}.shtml"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

log = logging.getLogger("backfill_cctv")


def _call_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """Run fn(*args, **kwargs) in a daemon thread with a hard timeout.

    Raises TimeoutError on expiry; re-raises fn's exception otherwise. A daemon
    thread (not ThreadPoolExecutor) is required: a hung worker must not block
    interpreter exit via concurrent.futures' atexit join.
    """
    import threading
    result: list = []
    error: list = []

    def _target() -> None:
        try:
            result.append(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 — re-raised in caller thread
            error.append(exc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout_s}s")
    if error:
        raise error[0]
    return result[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_stub_row(row_text: str) -> bool:
    """Return True if this looks like a page-rot stub rather than real content."""
    return any(sig in row_text for sig in STUB_SIGNATURES)


def _shard_path(archive_dir: Path, dt: date) -> Path:
    return archive_dir / f"{dt.strftime('%Y-%m')}.parquet"


def _load_shard(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["date", "order_idx", "title", "content",
                                  "fetch_status", "fetched_at", "listing_title"])


def _save_shard(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd", index=False)


def _already_archived(archive_dir: Path, dt: date) -> bool:
    """True if this date appears in its shard (any fetch_status — even error)."""
    shard = _shard_path(archive_dir, dt)
    if not shard.exists():
        return False
    df = _load_shard(shard)
    return dt.strftime("%Y-%m-%d") in df["date"].values


def _all_stubs_or_error(archive_dir: Path, dt: date) -> bool:
    """True if this date is archived BUT all rows are stubs/errors."""
    shard = _shard_path(archive_dir, dt)
    if not shard.exists():
        return False
    df = _load_shard(shard)
    day_rows = df[df["date"] == dt.strftime("%Y-%m-%d")]
    if day_rows.empty:
        return False
    return (day_rows["fetch_status"].isin(["stub", "error"])).all()


def _upsert_day(archive_dir: Path, dt: date, rows: list[dict]) -> None:
    """Remove any existing rows for dt then append the new ones."""
    shard = _shard_path(archive_dir, dt)
    existing = _load_shard(shard)
    ds = dt.strftime("%Y-%m-%d")
    existing = existing[existing["date"] != ds]
    new_df = pd.DataFrame(rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    # Shards written before the listing_title column existed leave NaN here
    if "listing_title" in combined.columns:
        combined["listing_title"] = combined["listing_title"].fillna("")
    combined = combined.sort_values(["date", "order_idx"]).reset_index(drop=True)
    _save_shard(combined, shard)


def _log_line(archive_dir: Path, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}  {msg}"
    print(line, flush=True)
    log_path = archive_dir / "backfill.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_listing_titles(ds: str) -> list[str]:
    """Fetch the day's Xinwen Lianbo listing page → item titles in broadcast order.

    Best-effort: returns [] on any fetch/parse failure — listing-title recording
    must never fail the day. Only real article links (…VIDE….shtml) count; a
    throttle/soft-error page still renders nav <li><a> items and those must not
    be mistaken for the day's listing (same guard as
    backfill_china_communiques._cctv_listing_titles).
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        time.sleep(random.uniform(0.5, 1.5))
        resp = requests.get(CCTV_LISTING_URL.format(ds=ds), headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        titles: list[str] = []
        for li in soup.find_all("li"):
            a = li.find("a")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if title and "VIDE" in href:
                titles.append(title)
        return titles
    except Exception as exc:  # noqa: BLE001
        log.debug("  listing fetch failed for %s: %s", ds, exc)
        return []


def _annotate_listing_titles(rows: list[dict], ds: str) -> None:
    """Record real listing-page titles on stub/error rows (mutates rows).

    Stub/error rows carry CCTV's error text in title/content, losing the real
    item identity — which forces downstream day-level provability checks
    (_archive_day_items in backfill_china_communiques.py) to fall back to the
    network for the whole day. When the fetched row count matches the listing,
    every row gets its aligned listing_title; when counts differ (e.g. a
    single-row whole-day stub vs a 16-item listing) each stub/error row carries
    the FULL newline-joined listing so downstream checks can still test every
    real title. Rows keep listing_title="" when the listing fetch fails.
    """
    if not any(r["fetch_status"] in ("stub", "error") for r in rows):
        return
    titles = _fetch_listing_titles(ds)
    if not titles:
        return
    if len(titles) == len(rows):
        for r, title in zip(rows, titles):
            r["listing_title"] = title
    else:
        joined = "\n".join(titles)
        for r in rows:
            if r["fetch_status"] in ("stub", "error"):
                r["listing_title"] = joined


def fetch_day(dt: date, retries: int = 3) -> tuple[list[dict], str]:
    """Fetch one day from akshare, return (rows, fetch_status).

    fetch_status: "ok" | "empty" | "stub" | "error"
    rows is always a list — empty on empty/error.

    Every news_cctv call runs under a daemon-thread hard timeout
    (CCTV_FETCH_TIMEOUT_S). A timeout is NOT retried — measured live 2026-07-06
    a hung URL hangs again, so the day lands as an error row immediately and is
    retried later via --repair.
    """
    try:
        import akshare as ak
    except Exception as e:
        raise RuntimeError(f"akshare unavailable: {e}") from e

    ds = dt.strftime("%Y%m%d")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    last_exc: Exception | None = None

    _unset = object()
    raw = _unset
    for attempt in range(1, retries + 1):
        try:
            raw = _call_with_timeout(ak.news_cctv, CCTV_FETCH_TIMEOUT_S, date=ds)
            break
        except TimeoutError as exc:
            last_exc = exc
            log.warning("  %s hung >%ds — stored as error row, no retry (--repair later)",
                        ds, CCTV_FETCH_TIMEOUT_S)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                wait = 2 ** attempt + random.uniform(0, 1)
                log.debug("  retry %d/%d for %s after %.1fs (%s)", attempt, retries, ds, wait, exc)
                time.sleep(wait)

    if raw is _unset:
        # Retries exhausted or hung call timed out
        err_row = {
            "date": dt.strftime("%Y-%m-%d"),
            "order_idx": 0,
            "title": "",
            "content": f"FETCH_ERROR: {last_exc}",
            "fetch_status": "error",
            "fetched_at": fetched_at,
            "listing_title": "",
        }
        rows = [err_row]
        _annotate_listing_titles(rows, ds)
        return rows, "error"

    if raw is None or len(raw) == 0:
        return [], "empty"

    rows = []
    all_stub = True
    for idx, row in enumerate(raw.itertuples(index=False)):
        title = str(getattr(row, "title", "") or "")
        content = str(getattr(row, "content", "") or "")
        combined_text = title + content
        is_stub = _is_stub_row(combined_text)
        if not is_stub:
            all_stub = False
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "order_idx": idx,
            "title": title,
            "content": content,
            "fetch_status": "stub" if is_stub else "ok",
            "fetched_at": fetched_at,
            "listing_title": "",
        })

    _annotate_listing_titles(rows, ds)
    if all_stub and rows:
        return rows, "stub"
    return rows, "ok"


# ---------------------------------------------------------------------------
# Date-range helpers
# ---------------------------------------------------------------------------

def _all_dates(end: date | None = None) -> list[date]:
    """All dates from HISTORY_START to end (inclusive), NEWEST FIRST."""
    end = end or date.today()
    out: list[date] = []
    cur = end
    while cur >= HISTORY_START:
        out.append(cur)
        cur -= timedelta(days=1)
    return out   # newest first


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_backfill(archive_dir: Path, repair: bool = False, pace_min: float = 2.0,
                 pace_max: float = 4.0) -> None:
    dates = _all_dates()
    total = len(dates)
    _log_line(archive_dir, f"BACKFILL START: {total} dates ({HISTORY_START}→{dates[-1]}) newest-first, repair={repair}")

    done = 0
    skipped = 0
    errors = 0
    stubs = 0
    t0 = time.time()

    for i, dt in enumerate(dates):
        if _already_archived(archive_dir, dt):
            if repair and _all_stubs_or_error(archive_dir, dt):
                pass   # fall through to re-fetch
            else:
                skipped += 1
                continue

        rows, status = fetch_day(dt)

        if status == "empty":
            # Weekend/holiday/not-yet-published — store a sentinel so we know we checked
            rows = [{
                "date": dt.strftime("%Y-%m-%d"),
                "order_idx": 0,
                "title": "",
                "content": "",
                "fetch_status": "empty",
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "listing_title": "",
            }]

        _upsert_day(archive_dir, dt, rows)

        if status == "error":
            errors += 1
        elif status == "stub":
            stubs += 1
        done += 1

        # Progress log every 10 days or on milestones
        if done % 10 == 0 or done <= 5:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done - skipped) / rate if rate > 0 else float("inf")
            eta_str = (
                str(timedelta(seconds=int(remaining))) if remaining < 1e9 else "?"
            )
            _log_line(
                archive_dir,
                f"  {i+1}/{total} date={dt} done={done} skip={skipped} err={errors} "
                f"stub={stubs} rate={rate:.2f}d/s ETA={eta_str}"
            )
        else:
            log.debug("  %s %s %d rows", dt, status, len(rows))

        # Politeness sleep (not after last item)
        if i < total - 1:
            time.sleep(random.uniform(pace_min, pace_max))

    elapsed = time.time() - t0
    _log_line(
        archive_dir,
        f"BACKFILL COMPLETE: done={done} skipped={skipped} errors={errors} stubs={stubs} "
        f"elapsed={timedelta(seconds=int(elapsed))}"
    )


def run_single_date(archive_dir: Path, ds: str) -> None:
    dt = datetime.strptime(ds, "%Y%m%d").date()
    _log_line(archive_dir, f"SINGLE DATE: {dt}")
    rows, status = fetch_day(dt)
    if status == "empty":
        rows = [{
            "date": dt.strftime("%Y-%m-%d"),
            "order_idx": 0,
            "title": "",
            "content": "",
            "fetch_status": "empty",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "listing_title": "",
        }]
    _upsert_day(archive_dir, dt, rows)
    _log_line(archive_dir, f"  {dt} -> {status}, {len(rows)} rows")


def run_gap_audit(archive_dir: Path) -> None:
    dates = _all_dates()
    from collections import defaultdict
    year_stats: dict[int, dict] = defaultdict(lambda: {"total": 0, "missing": 0, "stub": 0, "error": 0, "ok": 0, "empty": 0})

    for dt in dates:
        yr = dt.year
        year_stats[yr]["total"] += 1
        ds = dt.strftime("%Y-%m-%d")
        shard = _shard_path(archive_dir, dt)
        if not shard.exists():
            year_stats[yr]["missing"] += 1
            continue
        df = _load_shard(shard)
        day_rows = df[df["date"] == ds]
        if day_rows.empty:
            year_stats[yr]["missing"] += 1
            continue
        statuses = day_rows["fetch_status"].value_counts().to_dict()
        for s in ("ok", "empty", "stub", "error"):
            year_stats[yr][s] += statuses.get(s, 0)

    print("\n=== CCTV Archive Gap Audit ===")
    print(f"{'Year':<6} {'Total':<7} {'Missing':<9} {'OK-days':<9} {'Empty':<7} {'Stub':<6} {'Error':<6}")
    for yr in sorted(year_stats.keys()):
        s = year_stats[yr]
        print(f"{yr:<6} {s['total']:<7} {s['missing']:<9} {s['ok']:<9} {s['empty']:<7} {s['stub']:<6} {s['error']:<6}")

    print()
    all_missing = []
    for dt in reversed(dates):  # oldest first for readability
        if not _already_archived(archive_dir, dt):
            all_missing.append(dt.strftime("%Y-%m-%d"))
    if all_missing:
        print(f"Missing dates ({len(all_missing)}):")
        for d in all_missing[:50]:
            print(f"  {d}")
        if len(all_missing) > 50:
            print(f"  ... and {len(all_missing)-50} more")
    else:
        print("No missing dates — archive is complete.")


def run_sample_year(archive_dir: Path, year: int, pace_min: float = 2.0,
                    pace_max: float = 4.0) -> None:
    """Scrape one year and project full archive size."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    today = date.today()
    end = min(end, today)

    dates = []
    cur = end
    while cur >= start:
        dates.append(cur)
        cur -= timedelta(days=1)

    _log_line(archive_dir, f"SAMPLE YEAR {year}: {len(dates)} dates")
    done = 0
    for i, dt in enumerate(dates):
        if _already_archived(archive_dir, dt):
            done += 1
            continue
        rows, status = fetch_day(dt)
        if status == "empty":
            rows = [{
                "date": dt.strftime("%Y-%m-%d"),
                "order_idx": 0,
                "title": "",
                "content": "",
                "fetch_status": "empty",
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "listing_title": "",
            }]
        _upsert_day(archive_dir, dt, rows)
        done += 1
        if done % 20 == 0:
            _log_line(archive_dir, f"  {done}/{len(dates)} done")
        if i < len(dates) - 1:
            time.sleep(random.uniform(pace_min, pace_max))

    # Measure bytes
    total_bytes = sum(p.stat().st_size for p in archive_dir.glob("*.parquet"))
    archive_years = (today - HISTORY_START).days / 365.25
    year_bytes = sum(
        p.stat().st_size for p in archive_dir.glob(f"{year}-*.parquet")
    )
    projected_bytes = year_bytes * archive_years
    _log_line(archive_dir,
              f"SAMPLE YEAR {year} COMPLETE: year_bytes={year_bytes/1e6:.2f}MB "
              f"projected_full={projected_bytes/1e6:.1f}MB "
              f"(archive_years={archive_years:.1f})")
    print(f"\nSIZE DECISION: projected full archive = {projected_bytes/1e6:.1f} MB")
    if projected_bytes < 150e6:
        print("  -> COMMIT-OK: projected <150MB; shards are committable (no gitignore needed)")
    else:
        print("  -> ADD to .gitignore: projected >150MB; note in PR body")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    logging.basicConfig(level=level, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="CCTV 新闻联播 archive backfill")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT),
                        help=f"Archive directory (default: {DEFAULT_OUT})")
    parser.add_argument("--date", help="Fetch a single date YYYYMMDD")
    parser.add_argument("--gap-audit", action="store_true",
                        help="Print missing dates + stub-rate per year")
    parser.add_argument("--repair", action="store_true",
                        help="Retry dates whose rows are all stub/error")
    parser.add_argument("--sample-year", type=int, metavar="YEAR",
                        help="Scrape one year and project full archive size")
    parser.add_argument("--pace-min", type=float, default=2.0,
                        help="Minimum sleep between days (s)")
    parser.add_argument("--pace-max", type=float, default=4.0,
                        help="Maximum sleep between days (s)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    archive_dir = Path(args.out_dir).expanduser().resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)

    if args.gap_audit:
        run_gap_audit(archive_dir)
    elif args.date:
        run_single_date(archive_dir, args.date)
    elif args.sample_year:
        run_sample_year(archive_dir, args.sample_year, args.pace_min, args.pace_max)
    else:
        run_backfill(archive_dir, repair=args.repair,
                     pace_min=args.pace_min, pace_max=args.pace_max)


if __name__ == "__main__":
    main()
