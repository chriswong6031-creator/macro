"""research_vault.download_quota — file-based daily download ledger (RV W2).

Mirrors ``engine/neuralweb/brain_gateway._check_and_increment_quota`` verbatim in
spirit: a per-user, per-day JSON counter under the API's state dir, incremented
ONLY on an allowed download, with a **fail-open-but-LOUD** write (a broken ledger
must never lock out a paying subscriber — availability wins over a perfect cap,
exactly as the brain gateway reasons at its ``_write_quota``).

Limits: ``free``/``essential``/unknown = 0 (viewing + downloading are PRO-only;
Essential is a browse-and-teaser tier) · ``pro`` = 10/day · ``pro`` holding a
LIFETIME grant = 50/day. Period = UTC calendar day (``YYYY-MM-DD``).

State layout (masterplan §4):
    $MACRO_API_STATE_DIR/research_download_quota/dl_{safe_uid}_{YYYY-MM-DD}.json
    (default MACRO_API_STATE_DIR = /var/lib/macro-api)

SECURITY NOTE — the deliberate asymmetry with the tier resolver:
    * ENTITLEMENT resolution fails CLOSED (unknown → free → blocked). Never let a
      resolver error hand out paid access.
    * The download COUNTER fails OPEN (ledger I/O error → allow, uncapped, LOUD).
      Never let a broken state dir hard-lock a subscriber who already paid.
    These pull in opposite directions on purpose and are both correct: one guards
    the paywall, the other guards availability. (Same rule as brain_gateway.)

Pure + stdlib-only (json + os + re + datetime) → unit-testable offline; the router
injects ``now`` in tests to exercise the next-day period rollover.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("research_vault.download_quota")

# Daily download allowance per tier. Reading research is PRO-only, so free AND
# essential both get 0 (Essential is a browse-and-teaser tier); pro = 10/day.
LIMITS: dict[str, int] = {"free": 0, "essential": 0, "pro": 10}

# Raised allowance for a LIFETIME holder — a comp entitlement row with no period
# end, the same shape the account panel chips as "Lifetime". Applied only ON TOP OF
# a tier that already has a paid allowance (see `_limit_for`): the flag decides HOW
# MANY, never IF, so a comp/no-end row parked on free or essential (an admin downgrade
# writes exactly that shape) still gets 0.
LIFETIME_LIMITS: dict[str, int] = {"pro": 50}

# State dir mirrors brain_gateway (_STATE_DIR = MACRO_API_STATE_DIR default).
_STATE_DIR = Path(os.environ.get("MACRO_API_STATE_DIR", "/var/lib/macro-api"))
_SUBDIR = "research_download_quota"


def _quota_dir() -> Path:
    """Resolve the ledger dir fresh each call so tests can flip the env var."""
    base = Path(os.environ.get("MACRO_API_STATE_DIR", str(_STATE_DIR)))
    return base / _SUBDIR


def _safe_uid(user_id: str) -> str:
    """Filesystem-safe user id fragment (copied from brain_gateway._safe_uid).

    Collapses anything outside ``[A-Za-z0-9_-]`` to ``_`` and truncates to 64 —
    so a user id can never escape the ledger dir or inject a path separator.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", user_id or "")[:64]


def _period_key(now: datetime | None = None) -> str:
    """UTC calendar-day key (``YYYY-MM-DD``). Naive input is treated as UTC."""
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _resets_at(now: datetime | None = None) -> str:
    """ISO-8601 UTC midnight of the *next* day — when the day counter rolls over."""
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    n = n.astimezone(timezone.utc)
    # next UTC midnight
    from datetime import timedelta

    nxt = (n + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def _ledger_file(user_id: str, period: str) -> Path:
    return _quota_dir() / f"dl_{_safe_uid(user_id)}_{period}.json"


def _read(path: Path) -> dict:
    """Read a ledger file; missing/corrupt → ``{"count": 0}`` (copied idiom)."""
    try:
        if path.exists():
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
    except Exception:  # noqa: BLE001 — corrupt ledger reads as fresh
        pass
    return {"count": 0}


def _write(path: Path, data: dict) -> None:
    """Write a ledger file. Fail-open but LOUD (brain_gateway._write_quota idiom).

    A silently-failing counter write means the ledger stops advancing → the user
    would be uncapped until the state dir is fixed. We keep fail-open for
    availability (a broken ledger must never lock out a paying subscriber) but
    make it LOUD (``::error::``) so ops sees it instead of a swallowed warning.
    """
    try:
        _quota_dir().mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "::error::research_vault: DOWNLOAD QUOTA WRITE FAILED (%s) — ledger not "
            "advancing, downloads uncapped until the state dir is writable", exc)


def _limit_for(tier: str, lifetime: bool = False) -> int:
    """Daily limit for a tier; any unknown/None tier → 0 (blocked).

    ``lifetime=True`` promotes an ALREADY-PAID tier to its :data:`LIFETIME_LIMITS`
    allowance. The ``base > 0`` guard is the fail-closed half of that promotion —
    entitlement resolution still decides whether the caller may download at all, so
    a lifetime flag arriving on a zero-allowance tier can never buy access.
    """
    t = (tier or "").strip().lower()
    base = int(LIMITS.get(t, 0))
    if lifetime and base > 0:
        return int(LIFETIME_LIMITS.get(t, base))
    return base


def _info(tier: str, remaining: int, limit: int, used: int,
          period: str, resets_at: str) -> dict:
    """Uniform quota-info payload (both check_and_increment + peek return this)."""
    return {
        "tier": tier,
        "remaining": max(0, int(remaining)),
        "limit": int(limit),
        "used": max(0, int(used)),
        "period": period,
        "resets_at": resets_at,
    }


def check_and_increment(
    user_id: str,
    tier: str,
    root: Path | None = None,  # accepted for signature-parity; unused (state is env-rooted)
    now: datetime | None = None,
    lifetime: bool = False,
) -> tuple[bool, dict]:
    """Check the daily download quota and INCREMENT the counter on an allow.

    Returns ``(allowed, info)`` where ``info`` =
    ``{tier, remaining, limit, used, period, resets_at}``.

    Semantics:
      * ``limit == 0`` (free/unknown tier) → always ``(False, info[remaining=0])``;
        no ledger touched.
      * ``count >= limit`` → ``(False, info[remaining=0, used=count])``; no increment.
      * otherwise → increment the day counter and return
        ``(True, info[remaining=limit-(count+1)])``.

    ``lifetime=True`` raises a paid tier's cap to :data:`LIFETIME_LIMITS` (pro:
    50/day) and changes nothing else — same ledger file, same day key, so a holder
    who is granted a lifetime pass mid-day keeps the downloads already spent.

    Fail-open (allow) on ledger I/O error, but LOUD (``_write`` logs ``::error::``).
    The increment happens BEFORE returning the allow, so a scripted caller cannot
    race past the limit — the server is authoritative.
    """
    period = _period_key(now)
    resets = _resets_at(now)
    limit = _limit_for(tier, lifetime)

    # Free / unknown tiers are blocked with zero allowance — never touch the ledger.
    if limit <= 0:
        return False, _info(tier, 0, 0, 0, period, resets)

    path = _ledger_file(user_id, period)
    data = _read(path)
    count = int(data.get("count") or 0)

    if count >= limit:
        return False, _info(tier, 0, limit, count, period, resets)

    # Allow → increment first (server-authoritative), then report the new remaining.
    data["count"] = count + 1
    _write(path, data)
    used = count + 1
    return True, _info(tier, limit - used, limit, used, period, resets)


def peek(
    user_id: str,
    tier: str,
    root: Path | None = None,  # signature-parity; unused
    now: datetime | None = None,
    lifetime: bool = False,
) -> dict:
    """Read-only view of today's download allowance (NO increment).

    Backs ``GET /api/research/quota``. Returns the same info shape as
    :func:`check_and_increment` without mutating the ledger, and honors ``lifetime``
    identically — the button's "N of 50 left today" copy reads this ``limit``.
    Never raises.
    """
    period = _period_key(now)
    resets = _resets_at(now)
    limit = _limit_for(tier, lifetime)

    if limit <= 0:
        return _info(tier, 0, 0, 0, period, resets)

    data = _read(_ledger_file(user_id, period))
    count = int(data.get("count") or 0)
    return _info(tier, limit - count, limit, count, period, resets)
