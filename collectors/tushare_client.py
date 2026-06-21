"""Shared, GATED Tushare Pro client — premium A-share data, token-gated, keyless-safe.

Tushare Pro (tushare.pro) is a paid 积分 (credit) data service. This client is ONLY active
when the ``TUSHARE_TOKEN`` env var is set — the user's ¥1000 / 10000积分 membership. When the
token is ABSENT (the default in CI and locally without the secret) every call returns ``None``
and the Tushare collectors no-op, so the existing free akshare / Eastmoney stack and the keyless
CI build stay exactly as they are. The token is read from the environment ONLY and is never
written to disk or committed.

Direct HTTP to the Tushare REST endpoint (``POST http://api.tushare.pro``) — no ``tushare`` pip
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
    a build.

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

_API_URL = "http://api.tushare.pro"
_TIMEOUT = 30
_ENV = "TUSHARE_TOKEN"

# Per-endpoint minimum seconds between calls. report_rc (卖方盈利预测明细) is throttled to
# 1/hour on the 10000积分 tier; default is generous headroom under the 500/min regular lane.
_THROTTLE: dict[str, float] = {"report_rc": 3600.0}
_DEFAULT_THROTTLE = 0.35
_last_call: dict[str, float] = {}


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


def query(api_name: str, fields: str = "", *, _retries: int = 2, **params) -> "pd.DataFrame | None":
    """Call one Tushare endpoint → DataFrame (ts_code normalised to .SS), or None.

    Returns None — never raises — when: no token (gate closed), the endpoint errors, access is
    denied / credits are short, or the response is empty. A code-40203 rate-limit message is
    retried once after a pause; other non-zero codes degrade to None.
    """
    tok = token()
    if not tok:
        return None
    payload = {"api_name": api_name, "token": tok, "params": params or {}, "fields": fields}
    for attempt in range(_retries + 1):
        _throttle(api_name)
        try:
            r = requests.post(_API_URL, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            d = r.json()
        except Exception as e:  # noqa: BLE001 — network/parse: one bad call never breaks a build
            log.warning("tushare %s request failed (%s)", api_name, e)
            return None
        code = d.get("code")
        if code == 0:
            data = d.get("data") or {}
            cols = data.get("fields") or []
            items = data.get("items") or []
            if not cols:
                return None
            df = pd.DataFrame(items, columns=cols)
            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].map(norm_ticker)
            return df if len(df) else None
        msg = (d.get("msg") or "")[:120]
        # 频率超限 (rate-limited): pause and retry once; everything else is a hard miss. Regular
        # endpoints (500/min) clear in ~1s; only report_rc (in _THROTTLE) needs its long backoff.
        if code == 40203 and "频率" in msg and attempt < _retries:
            log.info("tushare %s rate-limited — backing off", api_name)
            time.sleep(max(_THROTTLE.get(api_name, _DEFAULT_THROTTLE), 1.0))
            continue
        log.warning("tushare %s returned code=%s msg=%s", api_name, code, msg)
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
