"""Shared, GATED Tushare Pro client — premium A-share data, token-gated, keyless-safe.

Tushare Pro (tushare.pro) is a paid 积分 (credit) data service. This client is ONLY active
when the ``TUSHARE_TOKEN`` env var is set — the user's ¥1000 / 10000积分 membership. When the
token is ABSENT (the default in CI and locally without the secret) every call returns ``None``
and the Tushare collectors no-op, so the existing free akshare / Eastmoney stack and the keyless
CI build stay exactly as they are. The token is read from the environment ONLY and is never
written to disk or committed.

Direct HTTPS to the Tushare REST endpoint (``POST https://api.tushare.pro``) — no ``tushare`` pip
dependency, matching this repo's direct-Eastmoney-JSON convention. Notes:

  * SUFFIX NORMALISATION. Tushare uses ``.SH`` for Shanghai; THIS repo uses ``.SS`` (e.g.
    ``600519.SS``). Every returned ``ts_code`` is remapped ``.SH -> .SS`` so the per-name joins
    against the membership spine / search universe line up. ``.SZ`` / ``.BJ`` pass through;
    Eastmoney sector codes (``BK####.DC``) are left untouched.
  * THROTTLE. A per-endpoint minimum inter-call interval (``report_rc`` is rate-limited to
    1 call/hour on this tier; regular endpoints allow 500/min). The snapshot collectors make one
    whole-market call per endpoint per build, so the throttle mostly matters for the few
    per-window loops.
  * Best-effort: any network / auth / parse failure returns ``None`` (logged) — never raises into
    a build. An AUTH rejection additionally LATCHES into ``last_auth_error()`` so the one caller
    that can act on it (``collectors/china_tushare``) can distinguish "the vendor is refusing our
    credential" from "there were no rows"; degrading both to ``None`` is what kept the plane
    silently dark from 2026-07-27 to 2026-08-06.

See research/TUSHARE_INTEGRATION.md for the tier, endpoint→积分 map, and the validate-before-score
roadmap (every new premium feed lands display-only until china_validation proves it).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

log = logging.getLogger("tushare_client")

_API_URL = "https://api.tushare.pro"
_TIMEOUT = 30
_ENV = "TUSHARE_TOKEN"

# Per-endpoint minimum seconds between calls. report_rc (卖方盈利预测明细) is throttled to
# 1/hour on the 10000积分 tier; default is generous headroom under the 500/min regular lane.
_THROTTLE: dict[str, float] = {"report_rc": 3600.0}
_DEFAULT_THROTTLE = 0.35
_last_call: dict[str, float] = {}

# Vendor AUTH-class codes — the token VALUE is rejected, so every endpoint fails
# identically and no amount of retrying or waiting helps; only an operator can fix it.
# 40101 (``您的token不对，请确认。``) is the one observed in the wild: the plane went dark
# 2026-07-27 when the configured token started coming back 40101 on trade_cal / daily /
# daily_basic / moneyflow_dc alike (run 31095457182, asia job 2026-08-06 11:39Z).
# DELIBERATELY NARROW: 40203 is the rate-limit / entitlement code (频率超限, or 权限 for an
# above-tier endpoint) — a throttle and a tier gap are NOT a dead credential, and folding
# them in here would turn `report_rc`'s expected hourly throttle into a false
# "regenerate your token" alarm every single night.
_AUTH_CODES = frozenset({40101})

# Latest auth rejection, or None. Latched by query() on an auth-class code and cleared by
# the next code==0 response, so a re-issued token self-clears with no restart.
_auth_error: dict | None = None


def last_auth_error() -> "dict | None":
    """The most recent vendor auth rejection — ``{api_name, code, msg, ts}`` — or None.

    Exists because an auth failure is otherwise INVISIBLE: ``query()`` degrades every
    rejection to ``None``, so a rejected token looks exactly like an empty snapshot to
    every caller, the collectors return 0 rows, and the china_tushare heartbeat still
    reports ok (the plane was dark 2026-07-27 → 2026-08-06 with nothing in run_status
    saying so). Callers that can tell the difference — see
    ``collectors/china_tushare.ChinaTushareAdapter.fetch`` — read this to raise LOUDLY.

    A copy is returned so a caller cannot mutate the latch.
    """
    return dict(_auth_error) if _auth_error else None


def token() -> str | None:
    """The Tushare token from the environment, or None (the keyless default)."""
    t = (os.environ.get(_ENV) or "").strip()
    return t or None


def enabled() -> bool:
    """True only when a Tushare token is configured — the single gate every collector checks."""
    return token() is not None


def norm_ticker(code: str | None) -> str | None:
    """Tushare ts_code -> this repo's suffix convention (.SH -> .SS; .SZ/.BJ/.DC pass through)."""
    if not code:
        return None
    s = str(code).strip()
    if s.endswith(".SH"):
        return s[:-3] + ".SS"
    return s


def _throttle(api_name: str) -> None:
    gap = _THROTTLE.get(api_name, _DEFAULT_THROTTLE)
    last = _last_call.get(api_name)
    if last is not None:
        wait = gap - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_call[api_name] = time.monotonic()


def query(api_name: str, fields: str = "", *, _retries: int = 2,
          _return_empty: bool = False, **params) -> "pd.DataFrame | None":
    """Call one Tushare endpoint → DataFrame (ts_code normalised to .SS), or None.

    Returns None — never raises — when: no token (gate closed), the endpoint errors, access is
    denied / credits are short, or the response is empty. Callers that must distinguish a
    successful zero-row response from an unavailable endpoint can opt into an empty DataFrame
    with ``_return_empty=True``; the legacy default remains unchanged. A code-40203 rate-limit
    message is retried once after a pause; other non-zero codes degrade to None.

    The return contract is unchanged, but an auth-class rejection (see ``_AUTH_CODES``) is now
    also LATCHED into module state readable via ``last_auth_error()`` — every caller that only
    wants the frame is unaffected; the one caller that can raise on it (china_tushare) finally
    can. Any code==0 response clears the latch, so recovery needs no restart.
    """
    global _auth_error
    tok = token()
    if not tok:
        return None
    payload = {"api_name": api_name, "token": tok, "params": params or {}, "fields": fields}
    for attempt in range(_retries + 1):
        _throttle(api_name)
        try:
            # The paid token lives in the JSON body.  Never send it over plaintext HTTP and
            # never follow a vendor/proxy redirect that could move that body to a different
            # origin.  TLS certificate verification remains requests' fail-closed default.
            r = requests.post(
                _API_URL,
                json=payload,
                timeout=_TIMEOUT,
                allow_redirects=False,
            )
            if r.is_redirect or r.is_permanent_redirect or 300 <= r.status_code < 400:
                log.warning("tushare %s refused HTTP redirect", api_name)
                return None
            r.raise_for_status()
            d = r.json()
        except Exception as e:  # noqa: BLE001 — network/parse: one bad call never breaks a build
            # Exception text and vendor response bodies are untrusted and can echo a request.
            # Log only the exception class so credential-bearing payload state cannot escape.
            log.warning("tushare %s request failed (%s)", api_name, type(e).__name__)
            return None
        if not isinstance(d, dict):
            return None
        code = d.get("code")
        if code == 0:
            # Authenticated round-trip: whatever was wrong with the credential is over.
            # Cleared on code==0 regardless of row count — an empty snapshot is a DATA
            # answer, and treating it as "still broken" would leave a healed token latched.
            _auth_error = None
            data = d.get("data")
            # A successful empty is attested only by the vendor's real schema plus
            # an explicit items=[] payload.  Never synthesize caller-requested
            # columns from malformed code-0 responses: doing so can checkpoint a
            # permanently false empty source unit.
            if not isinstance(data, dict):
                return None
            cols = data.get("fields")
            items = data.get("items")
            if (
                not isinstance(cols, list)
                or not cols
                or not all(isinstance(column, str) and column for column in cols)
                or not isinstance(items, list)
                or not all(
                    isinstance(item, (list, tuple)) and len(item) == len(cols)
                    for item in items
                )
            ):
                return None
            try:
                df = pd.DataFrame(items, columns=cols)
            except (AssertionError, TypeError, ValueError):
                return None
            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].map(norm_ticker)
            return df if len(df) or _return_empty else None
        msg = str(d.get("msg") or "")
        # 频率超限 (rate-limited): pause and retry once; everything else is a hard miss. Regular
        # endpoints (500/min) clear in ~1s; only report_rc (in _THROTTLE) needs its long backoff.
        if code == 40203 and "频率" in msg and attempt < _retries:
            log.info("tushare %s rate-limited — backing off", api_name)
            time.sleep(max(_THROTTLE.get(api_name, _DEFAULT_THROTTLE), 1.0))
            continue
        if code in _AUTH_CODES:
            _auth_error = {
                "api_name": api_name,
                "code": code,
                "msg": "credential rejected by vendor",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        # Do not log the vendor message: an upstream/proxy error can echo arbitrary input.
        log.warning("tushare %s returned code=%s", api_name, code)
        return None
    return None


def _utc_today() -> datetime:
    return datetime.now(timezone.utc)


def latest_trade_date(exchange: str = "SSE") -> str | None:
    """Most recent OPEN exchange date (YYYYMMDD) on/before today, via trade_cal. None on miss."""
    end = _utc_today().strftime("%Y%m%d")
    start = (_utc_today() - timedelta(days=16)).strftime("%Y%m%d")
    df = query("trade_cal", exchange=exchange, start_date=start, end_date=end,
               fields="cal_date,is_open")
    if df is None or "cal_date" not in df.columns:
        return None
    opens = [str(c) for c, o in zip(df["cal_date"], df["is_open"]) if str(o) == "1" and str(c) <= end]
    return max(opens) if opens else None


def snapshot_by_date(api_name: str, fields: str = "", *, max_back: int = 6,
                     **extra) -> "tuple[pd.DataFrame | None, str | None]":
    """Whole-market snapshot for the latest day that actually has rows (walks back up to
    `max_back` calendar days from the latest trade date). Returns (df, trade_date) or (None, None).
    One ``trade_date=`` call returns every name, so this is the cheap way to pull a full snapshot."""
    anchor = latest_trade_date() or _utc_today().strftime("%Y%m%d")
    try:
        dt = datetime.strptime(anchor, "%Y%m%d")
    except ValueError:
        return None, None
    for i in range(max_back):
        ds = (dt - timedelta(days=i)).strftime("%Y%m%d")
        df = query(api_name, trade_date=ds, fields=fields, **extra)
        if df is not None and len(df):
            return df, ds
    return None, None
