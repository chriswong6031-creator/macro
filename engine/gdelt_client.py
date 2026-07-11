"""Shared GDELT fetch client for all artlist callers.

LEAF · CONTEXT-ONLY · DISPLAY-TIER. is_context_only=True.

WHY THIS EXISTS
---------------
GDELT's free API enforces one request every 5 seconds per IP.  As of 2026-06-20
the nightly pipeline had nine modules hitting the same endpoint in uncoordinated
bursts; the shared runner IP entered a rate-limit penalty box and has returned 429
on every request since.  This module is the single HTTP funnel that all GDELT
artlist callers must route through so the per-IP pacing rule is honoured globally,
not per-module.

Nine caller modules were identified:
  engine/news_vector.py, engine/news_common.py, engine/macro_news.py,
  engine/china_news.py, engine/catalyst_stock.py, engine/catalyst_tone.py,
  engine/commodity_news.py, engine/missing_tape_gdelt.py, collectors/hk_gdelt.py

engine/macro_news.py is handled by a separate lane and must NOT be wired here yet.
engine/missing_tape_gdelt.py and collectors/hk_gdelt.py use the timeline (not
artlist) endpoint and their own Session/urllib transport; they are left to their own
pacing and noted in the PR body.

THROTTLE MECHANISM
------------------
A stamp file under data/gdelt/last_request is locked with fcntl.flock before each
request.  The lock-holder reads the stamp, sleeps until >= min_interval seconds have
passed, writes a fresh stamp, then releases the lock before issuing the HTTP request.
This gives cross-process serialisation on a single machine (all nightly jobs run on
the same Mac Studio).

RETRY POLICY (bounded to stay under render budget)
---------------------------------------------------
  429 -> sleep 30s -> one retry
  429 again -> sleep 75s -> final retry
  429 on final -> return (None, 'rate_limited')
  non-200 or non-json -> return (None, 'fetch_error')
  Worst-case total wait per call: ~6s throttle + 30s + 75s < 2.5 minutes.
  Never raises.

CACHE SEMANTICS
---------------
If cache_path is given and a fresh file (age < cache_ttl_s) exists, the cached
articles are returned immediately WITHOUT hitting the network.  On a successful
response the result is written to cache_path.  Failures are NEVER cached — caching
a failure would suppress retries for the full TTL and silently stall accrual stores.
"""
from __future__ import annotations

import fcntl
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_UA = "macro-dashboard/1.0 (research)"

# ── config key: gdelt.min_request_interval_s (float, default 6.0) ──────────


def _min_interval() -> float:
    """Cross-module pacing floor in seconds.  Reads config.yml gdelt block if
    present; falls back to 6.0 (1 second above GDELT's 5s/IP rule)."""
    try:
        gdelt_cfg = config.load().get("gdelt") or {}
        v = gdelt_cfg.get("min_request_interval_s")
        if v is not None:
            return max(1.0, float(v))
    except Exception:  # noqa: BLE001 — config unavailable; use default
        pass
    return 6.0


def _stamp_path() -> Path:
    """Cross-process throttle stamp file.  Created on first use."""
    p = config.data_dir() / "gdelt" / "last_request"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _throttle(min_interval: float) -> None:
    """Cross-process rate limiter.  Acquires an exclusive lock on the stamp file,
    sleeps until >= min_interval seconds since the last stamped request, writes a
    fresh stamp, then releases the lock.  Never raises."""
    try:
        stamp = _stamp_path()
        # open for read+write, create if absent
        fd = open(stamp, "a+")  # noqa: WPS515 — need fd for flock
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            fd.seek(0)
            raw = fd.read().strip()
            try:
                last_ts = float(raw)
            except (ValueError, TypeError):
                last_ts = 0.0
            now_ts = time.monotonic()
            # Use wall-clock for the stamp value (monotonic for the sleep calculation)
            elapsed = now_ts - last_ts
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            # write wall-clock unix time so the stamp survives process restart
            fd.seek(0)
            fd.truncate()
            fd.write(str(time.monotonic()))
            fd.flush()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
    except Exception as e:  # noqa: BLE001 — throttle failure must never block a request
        log.debug("gdelt_client throttle error (non-fatal): %s", e)


def _parse_articles(raw_json: dict) -> list[dict]:
    """Normalise raw GDELT artlist JSON into {title, url, domain, seendate(ISO)}
    dicts.  PURE — no network, no clock."""
    out: list[dict] = []
    for a in raw_json.get("articles") or []:
        sd = a.get("seendate", "")
        try:
            iso = datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            iso = sd
        out.append({
            "title":   a.get("title", ""),
            "url":     a.get("url", ""),
            "domain":  a.get("domain", ""),
            "seendate": iso,
        })
    return out


def get_articles(
    params: dict,
    *,
    timeout: int = 30,
    cache_path: "str | Path | None" = None,
    cache_ttl_s: "int | None" = None,
    min_interval: "float | None" = None,
) -> "tuple[list | None, str | None]":
    """Fetch a GDELT artlist with cross-process throttling, bounded retries, and
    optional read-through caching.

    Parameters
    ----------
    params:
        GDELT query parameters dict (query, mode, format, maxrecords, etc.).
        Must include at least ``query`` and ``mode=artlist``.
    timeout:
        HTTP request timeout in seconds.
    cache_path:
        If given, serve a fresh cache file first and write-through on success.
        Failures are NEVER cached.
    cache_ttl_s:
        Cache TTL in seconds.  Ignored when cache_path is None.
    min_interval:
        Per-call override of the cross-process pacing floor (seconds).
        Defaults to the config value (gdelt.min_request_interval_s, default 6.0).

    Returns
    -------
    (articles, degraded_reason)
        articles         list of {title, url, domain, seendate} dicts, or None on
                         final failure (two retries exhausted).
        degraded_reason  None on success, 'rate_limited' on persistent 429,
                         'fetch_error' on any other failure, 'no_articles' when the
                         response was valid but empty.
    """
    interval = min_interval if min_interval is not None else _min_interval()

    # ── cache read ──────────────────────────────────────────────────────────
    if cache_path is not None and cache_ttl_s is not None:
        cp = Path(cache_path)
        if cp.exists():
            try:
                age = datetime.now(timezone.utc).timestamp() - cp.stat().st_mtime
                if age < cache_ttl_s:
                    blob = json.loads(cp.read_text())
                    articles = blob.get("articles")
                    reason = blob.get("degraded_reason")
                    if articles is not None:
                        return articles, reason
            except Exception:  # noqa: BLE001 — stale/corrupt cache: fall through to fetch
                pass

    # ── fetch with throttle + bounded retry ─────────────────────────────────
    import requests  # local import — requests is a runtime dep, not always present at import time

    RETRY_SLEEPS = (30, 75)   # sleep before retry[0], sleep before retry[1]
    r = None
    reason: str | None = None

    for attempt in range(len(RETRY_SLEEPS) + 1):   # 0, 1, 2 → up to 3 attempts
        _throttle(interval)
        try:
            r = requests.get(GDELT_URL, params=params, timeout=timeout,
                             headers={"User-Agent": _UA})
        except Exception as e:  # noqa: BLE001 — network error
            log.warning("gdelt_client: network error on attempt %d: %s", attempt, e)
            reason = "fetch_error"
            break

        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "")
            if "json" not in ct:
                # GDELT sometimes returns 200 + plain-text on rate-limit
                log.warning(
                    "gdelt_client: 200 but Content-Type=%r (rate-limit text?); attempt %d",
                    ct, attempt,
                )
                reason = "rate_limited"
                if attempt < len(RETRY_SLEEPS):
                    time.sleep(RETRY_SLEEPS[attempt])
                    continue
                return None, reason
            # success path
            try:
                data = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("gdelt_client: JSON parse failed: %s", e)
                return None, "fetch_error"
            articles = _parse_articles(data)
            if not articles:
                reason = "no_articles"
            else:
                reason = None
            # ── cache write on success ONLY ─────────────────────────────────
            if cache_path is not None and articles:
                try:
                    cp = Path(cache_path)
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
                except Exception:  # noqa: BLE001
                    pass
            return articles, reason

        if r.status_code == 429:
            log.warning("gdelt_client: 429 rate-limited on attempt %d", attempt)
            reason = "rate_limited"
            if attempt < len(RETRY_SLEEPS):
                time.sleep(RETRY_SLEEPS[attempt])
                continue
            # final attempt also 429
            return None, reason

        # other non-200
        log.warning("gdelt_client: HTTP %d on attempt %d", r.status_code, attempt)
        reason = "fetch_error"
        break

    return None, reason
