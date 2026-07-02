"""scripts/recrawl_official_tape.py — Missing-Tape Leg A: Official Corpus Recrawler.

Spec: research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md D8, §4 W4 row,
      Appendix P4.

For every qbus row whose body_sha256 is non-empty AND source_tier == 1 (TIER1
official, e.g. gov.cn, Xinhua, PBOC, NDRC), recrawl the original URL at T+3d and
T+7d after first seen.  Compare the body hash of the fresh fetch to the stored
sha256.  Possible outcomes:

    unchanged  — body hash matches; content intact.
    edited     — body hash differs; quiet re-edit detected.
    gone       — HTTP 404 / non-200 / connection error.

Outcomes of "edited" or "gone" are emitted into qbus as new events with
theme=censorship_signal and the diff summary in the event title.  These events
carry direction=0 (RISK FLAG only, never a positive signal) per spec D8.

Storage: data/missing_tape/recrawl_log.parquet
Schema:
    item_id         — the original qbus item_id
    url             — original URL
    recrawl_at      — ISO date of the recrawl attempt
    lag_days        — days since _crawled_at (3 or 7)
    original_sha256 — stored body_sha256 from qbus
    fetched_sha256  — sha256 of the freshly fetched body ('' on error)
    status          — unchanged | edited | gone | error
    status_code     — HTTP status code (0 on connection error)

Pacing: STRICT 1 request per 5 seconds (browser UA, P4 / FREDGRAPH_UA precedent).
Caching: rows already logged at a given (item_id, lag_days) are never re-fetched.

Usage (called nightly by the collect pipeline):
    python scripts/recrawl_official_tape.py [--dry-run] [--max N]

Exit 0 always; never breaks the build.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("recrawl_official_tape")

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
# Recrawl at T+3d and T+7d after first seen.
LAG_DAYS: tuple[int, ...] = (3, 7)

# Minimum seconds between HTTP requests (P4 spec: 1req/5s).
PACE_SECONDS: float = 5.0

# Browser UA (FREDGRAPH_UA precedent; gov.cn IP sensitivity [P4]).
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# parquet path (config.data_dir() / "missing_tape" / "recrawl_log.parquet")
_LOG_COLS = (
    "item_id",
    "url",
    "recrawl_at",
    "lag_days",
    "original_sha256",
    "fetched_sha256",
    "status",          # unchanged | edited | gone | error
    "status_code",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _data_root() -> Path:
    """Resolve data/ via lib.config when available, else repo-relative fallback."""
    try:
        from lib import config
        return config.data_dir()
    except Exception:
        return ROOT / "data"


def _log_path(data_root: Path) -> Path:
    p = data_root / "missing_tape" / "recrawl_log.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_log(data_root: Path) -> pd.DataFrame:
    p = _log_path(data_root)
    if p.exists():
        try:
            return pd.read_parquet(p).reindex(columns=list(_LOG_COLS))
        except Exception as exc:
            LOG.warning("recrawl_log read failed: %s", exc)
    return pd.DataFrame(columns=list(_LOG_COLS))


def _save_log(df: pd.DataFrame, data_root: Path) -> None:
    p = _log_path(data_root)
    df.to_parquet(p, index=False)


def _already_logged(log_df: pd.DataFrame, item_id: str, lag: int) -> bool:
    """True if this (item_id, lag_days) pair already has an entry."""
    if log_df.empty:
        return False
    mask = (log_df["item_id"] == item_id) & (log_df["lag_days"] == lag)
    return bool(mask.any())


def body_sha256(body: bytes | str | None) -> str:
    """SHA-256 hex of body bytes/str, '' when absent. PURE."""
    if not body:
        return ""
    b = body if isinstance(body, bytes) else body.encode("utf-8", errors="replace")
    return hashlib.sha256(b).hexdigest()


def _fetch_body(url: str, timeout: int = 20) -> tuple[int, bytes]:
    """Fetch URL with browser UA.  Returns (status_code, body_bytes).
    On connection errors returns (0, b'')."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except Exception as exc:
        LOG.debug("fetch %s → %s", url, exc)
        return 0, b""


def _determine_status(
    original_sha: str,
    fetched_sha: str,
    status_code: int,
) -> str:
    """Map fetch outcome to one of: unchanged | edited | gone | error."""
    if status_code == 0:
        return "error"
    if status_code == 404 or status_code >= 400:
        return "gone"
    if not fetched_sha:
        return "error"
    if fetched_sha == original_sha:
        return "unchanged"
    return "edited"


# --------------------------------------------------------------------------- #
# qbus event emission for edited/gone rows
# --------------------------------------------------------------------------- #
def _emit_censorship_event(
    row_data: dict,
    status: str,
    recrawl_date: str,
    lag: int,
    dry_run: bool = False,
) -> None:
    """Emit one qbus event for an edited/gone detection.

    direction=0 — RISK FLAG semantics only, never a positive signal (spec D8).
    theme=censorship_signal.
    """
    if dry_run:
        LOG.info("[dry-run] would emit censorship_signal event for %s (status=%s)",
                 row_data.get("item_id"), status)
        return

    try:
        from engine import qbus
        from engine.qkernel import event_id as _event_id
    except Exception as exc:
        LOG.warning("qbus import failed — censorship event not emitted: %s", exc)
        return

    title = (
        f"[missing-tape] {status.upper()} at T+{lag}d: "
        f"{row_data.get('url', '')[:120]}"
    )
    item = {
        "desk": "missing_tape",
        "source": "recrawl_official_tape",
        "source_tier": 1,
        "lang": "zh",
        "url": row_data.get("url", ""),
        "title": title,
        "body_sha256": "",
        "seendate": recrawl_date,
        "_crawled_at": recrawl_date,
        "timestamp_quality": "CRAWL_BOUNDED",
        "entities": [],
        "themes": ["censorship_signal"],
        "importance_raw": 0.0,   # display/salience only; direction=0 per spec
    }
    # item_id computed by qbus.normalize_row
    try:
        qbus.append_items([item])
        LOG.info("emitted censorship_signal event: %s", title[:100])
    except Exception as exc:
        LOG.warning("qbus.append_items failed: %s", exc)


# --------------------------------------------------------------------------- #
# main pipeline
# --------------------------------------------------------------------------- #
def _eligible_qbus_rows(data_root: Path, today: date) -> list[dict]:
    """Return qbus TIER1 rows with a body_sha256 that are old enough for T+3."""
    try:
        from engine.qbus import read_items
    except Exception as exc:
        LOG.warning("qbus import failed: %s", exc)
        return []

    df = read_items()
    if df is None or df.empty:
        return []

    # Filter to TIER1 rows with a body hash
    df = df[
        (df["source_tier"].astype(str) == "1")
        & (df["body_sha256"].fillna("") != "")
    ]
    if df.empty:
        return []

    # Only rows first seen at least LAG_DAYS[0] days ago
    min_lag = min(LAG_DAYS)
    cutoff = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
              - timedelta(days=min_lag)).isoformat()

    crawled = pd.to_datetime(df["_crawled_at"], errors="coerce", utc=True)
    df = df[crawled <= pd.Timestamp(cutoff)]
    if df.empty:
        return []

    rows = df[["item_id", "url", "body_sha256", "_crawled_at"]].to_dict("records")
    return rows


def run(
    *,
    dry_run: bool = False,
    max_rows: int | None = None,
    today: date | None = None,
    data_root: Path | None = None,
) -> pd.DataFrame:
    """Execute the recrawl pass.  Returns the updated log DataFrame.

    Parameters
    ----------
    dry_run:
        If True, fetch but do NOT write parquet or emit qbus events.
    max_rows:
        Cap on the number of (item_id, lag) pairs to fetch per run (rate guard).
    today:
        Inject a date for testing (default: real UTC today).
    data_root:
        Override data directory (for tests).
    """
    today = today or date.today()
    data_root = data_root or _data_root()

    log_df = _load_log(data_root)
    eligible = _eligible_qbus_rows(data_root, today)

    LOG.info("recrawl: %d TIER1 rows eligible, %d already logged",
             len(eligible), len(log_df))

    new_rows: list[dict] = []
    n_fetched = 0
    last_fetch = 0.0

    for row in eligible:
        item_id = str(row.get("item_id", ""))
        url = str(row.get("url", ""))
        original_sha = str(row.get("body_sha256", ""))

        try:
            first_seen = pd.Timestamp(str(row.get("_crawled_at", ""))).date()
        except Exception:
            continue

        for lag in LAG_DAYS:
            recrawl_date = first_seen + timedelta(days=lag)
            if recrawl_date > today:
                continue  # not due yet
            if _already_logged(log_df, item_id, lag):
                continue  # already done

            if max_rows is not None and n_fetched >= max_rows:
                LOG.info("max_rows=%d reached, stopping", max_rows)
                break

            # Rate-limit
            elapsed = time.monotonic() - last_fetch
            if elapsed < PACE_SECONDS:
                time.sleep(PACE_SECONDS - elapsed)

            LOG.debug("fetching lag=%dd url=%s", lag, url[:80])
            status_code, body = _fetch_body(url)
            last_fetch = time.monotonic()
            n_fetched += 1

            fetched_sha = body_sha256(body) if body else ""
            status = _determine_status(original_sha, fetched_sha, status_code)

            rec = {
                "item_id": item_id,
                "url": url,
                "recrawl_at": recrawl_date.isoformat(),
                "lag_days": lag,
                "original_sha256": original_sha,
                "fetched_sha256": fetched_sha,
                "status": status,
                "status_code": status_code,
            }
            new_rows.append(rec)
            LOG.info("recrawl item_id=%s lag=%dd status=%s code=%d",
                     item_id[:12], lag, status, status_code)

            if status in ("edited", "gone"):
                _emit_censorship_event(row, status, recrawl_date.isoformat(),
                                       lag, dry_run=dry_run)

        if max_rows is not None and n_fetched >= max_rows:
            break

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=list(_LOG_COLS))
        merged = pd.concat([log_df, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["item_id", "lag_days"], keep="first")
        if not dry_run:
            _save_log(merged, data_root)
        LOG.info("recrawl: wrote %d new rows (dry_run=%s)", len(new_rows), dry_run)
        return merged

    return log_df


def deletion_rate(log_df: pd.DataFrame | None = None, data_root: Path | None = None) -> float:
    """Fraction of recrawled rows that are 'gone'.  Used by the artifact emitter."""
    if log_df is None:
        log_df = _load_log(data_root or _data_root())
    if log_df.empty:
        return 0.0
    return float((log_df["status"] == "gone").sum() / len(log_df))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch but do not write parquet or emit qbus events.")
    p.add_argument("--max", type=int, default=None, dest="max_rows",
                   help="Max (item_id, lag) pairs to fetch per run.")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = _parse_args(argv)
    try:
        run(dry_run=args.dry_run, max_rows=args.max_rows)
    except Exception as exc:  # noqa: BLE001
        LOG.error("recrawl_official_tape failed: %s", exc, exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
