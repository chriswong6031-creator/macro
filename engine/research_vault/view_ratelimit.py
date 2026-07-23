"""research_vault.view_ratelimit — per-user+IP hourly soft cap on /view (RV W2).

``/api/research/view`` streams the FULL PDF bytes to an authenticated paid user,
so it is the surface a subscriber could script to bulk-scrape the whole vault.
The download route is quota-metered (5/20 a day); the *view* route is not, so it
needs its own anti-scrape control. This is that control: a soft hourly cap keyed
on BOTH the user id AND the client IP (a shared account behind one box still gets
throttled; a rotating-IP scraper on one account still gets throttled).

Default cap: ~60 views/hour (env ``RESEARCH_VIEW_HOURLY`` overrides). Period = UTC
hour (``YYYY-MM-DDTHH``). Dual ledger, allowed only if BOTH are under the cap; on
allow BOTH increment. Reported ``remaining`` is the WORSE of the two.

SECURITY:
  * The raw IP is NEVER written to a filename — it is sha256-hashed first, so the
    ledger dir cannot leak visitor IPs and a crafted IP string cannot inject a
    path (the hash is hex-only). ``_safe_uid`` further sanitizes both keys.
  * Fail-OPEN but LOUD on ledger I/O error — a broken state dir must not hard-lock
    a paying subscriber out of the viewer (same rule as the download quota).

State layout (mirrors the download quota, separate subdir):
    $MACRO_API_STATE_DIR/research_view_rl/vh_{safe_uid}_{YYYY-MM-DDTHH}.json   (user)
    $MACRO_API_STATE_DIR/research_view_rl/vip_{iphash}_{YYYY-MM-DDTHH}.json    (IP)

Pure + stdlib-only → offline-testable; ``now`` is injectable for period tests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("research_vault.view_ratelimit")

_STATE_DIR = Path(os.environ.get("MACRO_API_STATE_DIR", "/var/lib/macro-api"))
_SUBDIR = "research_view_rl"

_DEFAULT_HOURLY = 60


def _hourly_limit() -> int:
    """Resolve the hourly cap fresh each call (env override, sane fallback)."""
    raw = os.environ.get("RESEARCH_VIEW_HOURLY", "")
    try:
        v = int(raw)
        return v if v > 0 else _DEFAULT_HOURLY
    except (TypeError, ValueError):
        return _DEFAULT_HOURLY


def _rl_dir() -> Path:
    base = Path(os.environ.get("MACRO_API_STATE_DIR", str(_STATE_DIR)))
    return base / _SUBDIR


def _safe_uid(user_id: str) -> str:
    """Filesystem-safe fragment (brain_gateway._safe_uid idiom)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", user_id or "")[:64]


def _hash_ip(ip: str) -> str:
    """sha256 the IP → 16 hex chars. NEVER put a raw IP in a filename.

    Empty/unknown IP → 'noip' so a missing IP still meters (a scraper can't dodge
    the cap by hiding its address — the user ledger still applies)."""
    if not ip or ip == "unknown":
        return "noip"
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _period_key(now: datetime | None = None) -> str:
    """UTC hour key (``YYYY-MM-DDTHH``). Naive input treated as UTC."""
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def _user_file(user_id: str, period: str) -> Path:
    return _rl_dir() / f"vh_{_safe_uid(user_id)}_{period}.json"


def _ip_file(ip_hash: str, period: str) -> Path:
    return _rl_dir() / f"vip_{_safe_uid(ip_hash)}_{period}.json"


def _read(path: Path) -> dict:
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:  # noqa: BLE001
        pass
    return {"count": 0}


def _write(path: Path, data: dict) -> None:
    """Fail-open but LOUD (a broken ledger must not lock a subscriber out)."""
    try:
        _rl_dir().mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "::error::research_vault: VIEW RATE-LIMIT WRITE FAILED (%s) — not "
            "advancing, view throttle uncapped until the state dir is writable", exc)


def allow(
    user_id: str,
    ip: str,
    root: Path | None = None,  # signature-parity; unused (env-rooted state)
    now: datetime | None = None,
) -> tuple[bool, dict]:
    """Check + increment the hourly view cap for (user, IP).

    Returns ``(allowed, {remaining, limit})``. Allowed only when BOTH the user
    counter and the IP counter are under the cap; on allow both increment and
    ``remaining`` is the worse of the two. Fail-open (allow) on I/O error.
    """
    limit = _hourly_limit()
    period = _period_key(now)

    uf = _user_file(user_id, period)
    ipf = _ip_file(_hash_ip(ip), period)

    ucount = int(_read(uf).get("count") or 0)
    icount = int(_read(ipf).get("count") or 0)

    if ucount >= limit or icount >= limit:
        worst = min(limit - ucount, limit - icount)
        return False, {"remaining": max(0, worst), "limit": limit}

    udata = _read(uf)
    udata["count"] = ucount + 1
    _write(uf, udata)

    idata = _read(ipf)
    idata["count"] = icount + 1
    _write(ipf, idata)

    remaining = min(limit - (ucount + 1), limit - (icount + 1))
    return True, {"remaining": max(0, remaining), "limit": limit}


def peek(user_id: str, ip: str, now: datetime | None = None) -> dict:
    """Read-only remaining views this hour (no increment). For the quota route."""
    limit = _hourly_limit()
    period = _period_key(now)
    ucount = int(_read(_user_file(user_id, period)).get("count") or 0)
    icount = int(_read(_ip_file(_hash_ip(ip), period)).get("count") or 0)
    remaining = min(limit - ucount, limit - icount)
    return {"remaining": max(0, remaining), "limit": limit}
