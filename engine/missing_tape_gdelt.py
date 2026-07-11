"""engine/missing_tape_gdelt.py — Missing-Tape Leg B: Onshore/Offshore Divergence.

Spec: research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md D8 §4 W4, Appendix P4.

Queries the GDELT Project's free `timelinetone` API to build two daily average-tone
series for China coverage:

    onshore-zh  : sourcelang:chinese  sourcecountry:China  (domestic Chinese-language press)
    offshore-en : sourcelang:english  [query: China]       (English-language global coverage)

The DIVERGENCE is their spread: zh_tone − en_tone on any given day.  A widening
gap (zh_tone rising while en_tone falls, or vice versa) is consistent with
suppression of negative sentiment in the domestic tape.

An expanding-window z-score of the daily spread flags potential suppression:

    divergence_z = (today_spread − expanding_mean) / expanding_std

This is a RISK FLAG (direction=0), never a positive signal.  High z = risk-off
(suppression-suspect); low z = no flag.

Storage: data/missing_tape/tone_divergence.parquet
Columns:
    date                — YYYY-MM-DD
    zh_tone             — onshore avg tone (GDELT scale ≈ −10 to +10)
    en_tone             — offshore avg tone
    spread              — zh_tone − en_tone
    spread_expanding_z  — expanding-window z-score (requires ≥ 5 data points; else NaN)

Pacing: STRICT 1 request per 5 seconds (P4 spec).
Caching: existing parquet rows are NOT re-fetched (incremental append only).

GDELT API reference: https://api.gdeltproject.org/api/v2/timeline/timeline
  Required param: query=<keywords>
  Filter params:  sourcelang:chinese / sourcelang:english
  Mode:           timelinetone
  Format:         JSON

LEAF module — no engine imports, no scoring inputs, no render side-effects.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

LOG = logging.getLogger("missing_tape_gdelt")

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_PACE_SECONDS: float = 5.0

# Minimum data points before computing z-score (avoids spurious early flags).
_MIN_Z_WINDOW: int = 5

_COLS = ("date", "zh_tone", "en_tone", "spread", "spread_expanding_z", "fetch_status")


# --------------------------------------------------------------------------- #
# data path helpers
# --------------------------------------------------------------------------- #
def _data_root() -> Path:
    try:
        from lib import config
        return config.data_dir()
    except Exception:
        return ROOT / "data"


def _parquet_path(data_root: Path) -> Path:
    p = data_root / "missing_tape" / "tone_divergence.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_series(data_root: Path | None = None) -> pd.DataFrame:
    """Load the existing tone_divergence series.  Returns empty DF on miss."""
    p = _parquet_path(data_root or _data_root())
    if p.exists():
        try:
            df = pd.read_parquet(p).reindex(columns=list(_COLS))
            return df.sort_values("date").reset_index(drop=True)
        except Exception as exc:
            LOG.warning("tone_divergence load failed: %s", exc)
    return pd.DataFrame(columns=list(_COLS))


def _save_series(df: pd.DataFrame, data_root: Path) -> None:
    p = _parquet_path(data_root)
    df.to_parquet(p, index=False)


# --------------------------------------------------------------------------- #
# GDELT API
# --------------------------------------------------------------------------- #
def _gdelt_url(query: str, smoothing: int = 0, maxrecords: int = 1000) -> str:
    """Build the GDELT doc/doc timelinetone API URL for a given query string.

    W4 ITEM 2: endpoint changed from /api/v2/timeline/timeline (404) to
    /api/v2/doc/doc with mode=timelinetone (the correct GDELT v2 doc endpoint).
    """
    params = {
        "query": query,
        "mode": "timelinetone",
        "format": "json",
        "smoothing": smoothing,
        "maxrecords": maxrecords,
    }
    return f"{_GDELT_BASE}?{urllib.parse.urlencode(params)}"


def _fetch_gdelt(url: str, timeout: int = 30) -> tuple[list[dict], str]:
    """Fetch GDELT timelinetone JSON from the doc/doc endpoint.

    Returns (records, fetch_status) where:
      records:       list of {date, value} dicts (empty on any failure).
      fetch_status:  "ok" | "empty" | "http_<N>" | "error"

    W4 ITEM 2: 4xx/5xx HTTP responses are no longer swallowed silently —
    they are logged as WARNING with the status code and recorded in fetch_status.
    Never raises.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                raw = resp.read()
        except urllib.error.HTTPError as http_exc:
            LOG.warning("GDELT fetch HTTP %d for %s — check endpoint or rate limit",
                        http_exc.code, url[:120])
            return [], f"http_{http_exc.code}"
        if status != 200:
            LOG.warning("GDELT fetch non-200 status %d for %s", status, url[:120])
            return [], f"http_{status}"
        data = json.loads(raw)
        # GDELT v2 doc/doc timelinetone response shape:
        # {"timeline": [{"series": [{"date": "YYYYMMDDHHMMSS", "value": float}, ...]}]}
        # or flat: {"timeline": [{"date": ..., "value": ...}]}
        timeline = data.get("timeline", [])
        if not timeline:
            LOG.debug("GDELT fetch returned empty timeline for %s", url[:80])
            return [], "empty"
        first = timeline[0]
        if "series" in first:
            records = first["series"]
        else:
            # flat list
            records = timeline
        return records, "ok"
    except Exception as exc:
        LOG.debug("GDELT fetch error %s → %s", url[:100], exc)
        return [], "error"


def _parse_gdelt_date(raw: str) -> str | None:
    """Convert GDELT date strings to YYYY-MM-DD.

    GDELT uses two formats:
      • YYYYMMDDHHMMSS (14-char compact) — e.g. "20261201120000"
      • YYYY-MM-DD (ISO date) — e.g. "2026-07-02"
    Returns None for unrecognised strings.
    """
    raw = str(raw).strip()
    # ISO date format: YYYY-MM-DD (10 chars, contains hyphens at [4] and [7])
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]
    # Compact format: YYYYMMDDHHMMSS (digits only, at least 8 chars)
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def _series_to_dict(records: list[dict]) -> dict[str, float]:
    """Convert GDELT records to {YYYY-MM-DD: tone_value} dict."""
    out: dict[str, float] = {}
    for r in records:
        d = _parse_gdelt_date(r.get("date", ""))
        v = r.get("value")
        if d and v is not None:
            try:
                out[d] = float(v)
            except (TypeError, ValueError):
                pass
    return out


# --------------------------------------------------------------------------- #
# divergence z-score (PURE, injectable for testing)
# --------------------------------------------------------------------------- #
def compute_divergence_z(spreads: list[float], min_window: int = _MIN_Z_WINDOW) -> list[float]:
    """Expanding-window z-score of the spread series.

    Returns NaN for positions where the window is smaller than min_window.
    PURE: no I/O, no clock reads.

    Parameters
    ----------
    spreads:
        Ordered list of daily spread values (zh_tone − en_tone).
    min_window:
        Minimum number of prior observations before computing z.
    """
    zs: list[float] = []
    for i, val in enumerate(spreads):
        window = spreads[:i]          # exclude current point from the distribution
        if len(window) < min_window:
            zs.append(float("nan"))
            continue
        import statistics
        mu = statistics.mean(window)
        sigma = statistics.stdev(window) if len(window) >= 2 else 0.0
        if sigma == 0.0:
            zs.append(0.0)
        else:
            zs.append((val - mu) / sigma)
    return zs


# --------------------------------------------------------------------------- #
# incremental update
# --------------------------------------------------------------------------- #
def _dates_to_fetch(existing_df: pd.DataFrame, today: date) -> list[str]:
    """Return YYYY-MM-DD strings not yet in the series, from earliest gap to yesterday."""
    yesterday = today - timedelta(days=1)
    if existing_df.empty:
        # Seed from 90 days ago (baseline for z-score warmup)
        start = today - timedelta(days=90)
    else:
        last_date = pd.to_datetime(existing_df["date"]).max().date()
        start = last_date + timedelta(days=1)
    dates = []
    d = start
    while d <= yesterday:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    return dates


def update(
    *,
    today: date | None = None,
    data_root: Path | None = None,
    dry_run: bool = False,
    max_requests: int | None = None,
) -> pd.DataFrame:
    """Fetch GDELT tone for missing dates and append to the series.

    Returns the full updated DataFrame.
    """
    today = today or date.today()
    data_root = data_root or _data_root()

    existing = load_series(data_root)
    missing_dates = _dates_to_fetch(existing, today)

    if not missing_dates:
        LOG.info("tone_divergence: up to date, no new dates to fetch")
        return existing

    LOG.info("tone_divergence: fetching %d dates (max_requests=%s)",
             len(missing_dates), max_requests)

    # GDELT timelinetone can return a range; we fetch the full history in ONE
    # call per lane (zh / en) to minimise round-trips, then filter to missing dates.
    # Rate: 1req/5s → 2 requests total per daily run.

    new_rows: list[dict] = []
    n_requests = 0

    def _pace() -> None:
        # shared per-IP pace gate — coordinates with every other GDELT caller
        # in the lane (news_vector, macro_news, hk_gdelt, ...), not just this one
        from engine import gdelt_client
        gdelt_client.wait_turn(_PACE_SECONDS)

    # Onshore (Chinese-language, sourced from China)
    _pace()
    zh_url = _gdelt_url("China sourcelang:chinese sourcecountry:China")
    zh_records, zh_status = _fetch_gdelt(zh_url)
    n_requests += 1
    zh_by_date = _series_to_dict(zh_records)
    LOG.info("zh tone: %d data points (fetch_status=%s)", len(zh_by_date), zh_status)

    if max_requests is not None and n_requests >= max_requests:
        LOG.info("max_requests=%d reached after zh fetch, skipping en", max_requests)
        en_by_date: dict[str, float] = {}
        en_status = "skipped"
    else:
        _pace()
        en_url = _gdelt_url("China sourcelang:english")
        en_records, en_status = _fetch_gdelt(en_url)
        n_requests += 1
        en_by_date = _series_to_dict(en_records)
        LOG.info("en tone: %d data points (fetch_status=%s)", len(en_by_date), en_status)

    # Build rows for missing dates where we have both lanes
    missing_set = set(missing_dates)
    all_dates = sorted(missing_set & (set(zh_by_date) | set(en_by_date)))

    # Combined fetch status: "ok" if both lanes ok, else the non-ok status.
    fetch_status_combined = "ok" if (zh_status == "ok" and en_status in ("ok", "skipped")) else \
        f"zh:{zh_status},en:{en_status}"

    for d in all_dates:
        zh_v = zh_by_date.get(d)
        en_v = en_by_date.get(d)
        if zh_v is None or en_v is None:
            continue  # skip partial days
        spread = zh_v - en_v
        new_rows.append({
            "date": d,
            "zh_tone": round(zh_v, 4),
            "en_tone": round(en_v, 4),
            "spread": round(spread, 4),
            "spread_expanding_z": float("nan"),  # recomputed below
            "fetch_status": fetch_status_combined,
        })

    if not new_rows:
        LOG.info("tone_divergence: no new complete rows (GDELT may lag 24–48h)")
        return existing

    new_df = pd.DataFrame(new_rows, columns=list(_COLS))
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"], keep="first")
    combined = combined.sort_values("date").reset_index(drop=True)

    # Recompute z-scores across the full series so historical values are consistent.
    spreads = combined["spread"].tolist()
    zs = compute_divergence_z(spreads, min_window=_MIN_Z_WINDOW)
    combined["spread_expanding_z"] = zs

    if not dry_run:
        _save_series(combined, data_root)
    LOG.info("tone_divergence: total %d rows (added %d)", len(combined), len(new_rows))
    return combined


def latest_divergence_z(data_root: Path | None = None) -> float:
    """Return the most recent spread_expanding_z value (NaN if unavailable)."""
    df = load_series(data_root)
    if df.empty:
        return float("nan")
    val = df["spread_expanding_z"].dropna()
    if val.empty:
        return float("nan")
    return float(val.iloc[-1])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-requests", type=int, default=None)
    args = p.parse_args()
    try:
        df = update(dry_run=args.dry_run, max_requests=args.max_requests)
        z = latest_divergence_z()
        LOG.info("latest divergence_z=%.3f (n=%d rows)", z, len(df))
    except Exception as exc:  # noqa: BLE001
        LOG.error("tone_divergence update failed: %s", exc, exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
