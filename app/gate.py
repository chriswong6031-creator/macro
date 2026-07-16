"""Site-access gate module — IP/country blocklist for macro-api.

DEFAULT STATE IS SAFE: ships disabled, empty lists, FAIL-OPEN everywhere.
A missing/invalid/unreadable rules file is treated as {enabled:false} => allow all.

The gate is callable with zero external deps.  maxminddb is imported lazily so
the app starts cleanly whether or not the library (or the db file) is present.

Public surface
--------------
decide(ip, headers) -> ("allow" | "block-ip" | "block-country")
coming_soon_page()  -> str   (HTML body returned on a block)
status()            -> dict  (for /api/gate/status)
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Config: paths / env
# ---------------------------------------------------------------------------
_DEFAULT_STATE_PATH = "/var/lib/macro-api/site_gate.json"
_DEFAULT_COUNTRY_HEADER = "EO-Client-IPCountry"
_DEFAULT_GEOIP_DB = "/var/lib/macro-api/GeoLite2-Country.mmdb"
_DEFAULT_PAGE_PATH = "site/coming-soon.html"

_COUNTRY_HEADER_FALLBACKS = ["EO-Client-Country", "CF-IPCountry"]


def _state_path() -> Path:
    return Path(os.environ.get("SITE_GATE_STATE", _DEFAULT_STATE_PATH))


def _country_header_name() -> str:
    return os.environ.get("SITE_GATE_COUNTRY_HEADER", _DEFAULT_COUNTRY_HEADER)


def _geoip_db_path() -> Path:
    return Path(os.environ.get("GEOIP_DB", _DEFAULT_GEOIP_DB))


def _page_path() -> Path:
    raw = os.environ.get("SITE_GATE_PAGE", _DEFAULT_PAGE_PATH)
    p = Path(raw)
    if not p.is_absolute():
        # relative to MACRO_REPO / cwd
        repo = Path(os.environ.get("MACRO_REPO", Path.cwd()))
        p = repo / p
    return p


# ---------------------------------------------------------------------------
# Rules cache (keyed by file mtime so changes propagate without restart)
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_cached_rules: dict | None = None
_cached_mtime: float | None = None

_EMPTY_RULES: dict = {
    "version": 1,
    "enabled": False,
    "blocked_ips": [],
    "blocked_countries": [],
    "allow_ips": [],
    "updated_at": None,
    "updated_by": None,
}


def _load_rules() -> dict:
    """Load and cache the blocklist JSON by mtime.  Returns _EMPTY_RULES on any error."""
    global _cached_rules, _cached_mtime
    path = _state_path()
    try:
        st = path.stat()
        # Key on (mtime_ns, size) so a same-second rewrite (coarse-mtime fs) still
        # invalidates — this store's whole point is instant propagation.
        cache_key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return _EMPTY_RULES

    with _CACHE_LOCK:
        if _cached_mtime == cache_key and _cached_rules is not None:
            return _cached_rules
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return _EMPTY_RULES
        if not isinstance(raw, dict):
            return _EMPTY_RULES
        # Normalise the loaded dict: provide defaults for any missing keys.
        rules = {**_EMPTY_RULES, **raw}
        if not isinstance(rules.get("blocked_ips"), list):
            rules["blocked_ips"] = []
        if not isinstance(rules.get("blocked_countries"), list):
            rules["blocked_countries"] = []
        if not isinstance(rules.get("allow_ips"), list):
            rules["allow_ips"] = []
        _cached_rules = rules
        _cached_mtime = cache_key
        return rules


def _invalidate_cache() -> None:
    """Reset all module caches. Used by tests for isolation."""
    global _cached_rules, _cached_mtime, _last_country, _last_country_source
    with _CACHE_LOCK:
        _cached_rules = None
        _cached_mtime = None
    with _last_country_lock:
        _last_country = None
        _last_country_source = None
    _drop_geoip_reader()


# ---------------------------------------------------------------------------
# IP / CIDR matching
# ---------------------------------------------------------------------------

def _parse_network(entry: str):
    """Parse an IP address or CIDR into an ipaddress network object.  Returns None on error."""
    try:
        return ipaddress.ip_network(entry, strict=False)
    except (ValueError, TypeError):
        return None


def _ip_in_list(ip_str: str, entries: list[str]) -> bool:
    """Return True if ip_str matches any entry (addr or CIDR) in entries.  Malformed entries are ignored."""
    if not ip_str or ip_str == "unknown":
        return False
    try:
        addr = ipaddress.ip_address(ip_str)
    except (ValueError, TypeError):
        return False
    for entry in entries:
        net = _parse_network(entry)
        if net is None:
            continue
        try:
            if addr in net:
                return True
        except TypeError:
            # IPv4 addr vs IPv6 net (or vice-versa) — never match
            continue
    return False


# ---------------------------------------------------------------------------
# Country resolution
# ---------------------------------------------------------------------------

# In-process tracking of last resolved country for /api/gate/status
_last_country_lock = threading.Lock()
_last_country: str | None = None
_last_country_source: str | None = None  # e.g. "header:EO-Client-IPCountry" or "geoip"


def _update_last_country(country: str | None, source: str | None) -> None:
    global _last_country, _last_country_source
    with _last_country_lock:
        _last_country = country
        _last_country_source = source


# Module-scoped MaxMind reader cache. Opening the mmdb per request is a needless
# mmap+parse on the hot path Caddy hits for every page load, so we open once and
# reuse, re-opening only if the db file's (path, mtime) changes.
_geoip_lock = threading.Lock()
_geoip_reader = None  # maxminddb reader instance, or None
_geoip_reader_key: tuple | None = None  # (db_path_str, mtime_ns)


def _drop_geoip_reader() -> None:
    global _geoip_reader, _geoip_reader_key
    with _geoip_lock:
        if _geoip_reader is not None:
            try:
                _geoip_reader.close()
            except Exception:  # noqa: BLE001
                pass
        _geoip_reader = None
        _geoip_reader_key = None


def _get_geoip_reader():
    """Return a cached maxminddb reader, re-opening on db change.

    Returns None if the library or the db file is unavailable. Never raises.
    """
    global _geoip_reader, _geoip_reader_key
    db_path = _geoip_db_path()
    try:
        key = (str(db_path), db_path.stat().st_mtime_ns)
    except OSError:
        # db missing — discard any stale open reader
        if _geoip_reader is not None:
            _drop_geoip_reader()
        return None
    with _geoip_lock:
        if _geoip_reader is not None and _geoip_reader_key == key:
            return _geoip_reader
        try:
            import maxminddb  # noqa: PLC0415
            reader = maxminddb.open_database(str(db_path))
        except Exception:  # noqa: BLE001 — lib absent / bad db; fail-open (no geoip)
            return None
        if _geoip_reader is not None:
            try:
                _geoip_reader.close()
            except Exception:  # noqa: BLE001
                pass
        _geoip_reader = reader
        _geoip_reader_key = key
        return reader


def _resolve_country_header(headers: dict) -> tuple[str | None, str | None]:
    """Cheap country resolution from CDN headers (dict lookup only).

    Tries the configured header then known fallbacks. Header keys arrive
    lowercased in production (Starlette normalises ASGI header names), so we
    check both the configured casing and its lowercase form.
    Returns (ISO-alpha-2 upper, "header:<name>") or (None, None).
    """
    for hname in [_country_header_name()] + _COUNTRY_HEADER_FALLBACKS:
        val = (headers.get(hname) or headers.get(hname.lower()) or "").strip().upper()
        if len(val) == 2 and val.isalpha():
            return val, f"header:{hname}"
    return None, None


def _resolve_country_geoip(ip: str) -> tuple[str | None, str | None]:
    """Resolve country for the ALREADY-RESOLVED visitor IP via MaxMind GeoIP.

    Reuses the authoritative `ip` (from _mm_client_ip) — no header re-parsing —
    and the cached reader. Returns (ISO-alpha-2 upper, "geoip") or (None, None).
    """
    if not ip or ip == "unknown":
        return None, None
    reader = _get_geoip_reader()
    if reader is None:
        return None, None
    try:
        record = reader.get(ip)
        if record:
            cc = ((record.get("country") or {}).get("iso_code")) or ""
            if cc:
                return cc.upper(), "geoip"
    except Exception:  # noqa: BLE001 — bad IP / record; fail-open
        pass
    return None, None


# ---------------------------------------------------------------------------
# Coming-soon page cache
# ---------------------------------------------------------------------------

_PAGE_LOCK = threading.Lock()
_page_content: str | None = None
_page_mtime: float | None = None

_FALLBACK_PAGE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mastermind — Coming Soon</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;
     background:#0a0a0f;color:#e8e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.card{max-width:520px;width:90%;text-align:center;padding:56px 40px}
.logo{font-size:13px;letter-spacing:.25em;text-transform:uppercase;color:#6b6b80;margin-bottom:48px}
h1{font-size:clamp(2rem,6vw,3.2rem);font-weight:700;letter-spacing:-.02em;line-height:1.1;margin-bottom:20px}
h1 span{display:block;color:#6b6b80;font-size:.45em;font-weight:400;letter-spacing:.05em;margin-top:8px}
.sub{color:#9090a8;font-size:.95rem;line-height:1.65;margin-bottom:40px}
.zh{color:#7070a0;font-size:.9rem;margin-top:12px;font-weight:300}
.divider{width:40px;height:2px;background:linear-gradient(90deg,#5050ff,#9090ff);
         margin:32px auto;border-radius:2px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Mastermind</div>
  <h1>Coming Soon<span>Something remarkable is being built</span></h1>
  <div class="divider"></div>
  <p class="sub">This service is not available in your region at this time.</p>
  <p class="zh">此服务暂不对您所在地区开放。</p>
</div>
</body>
</html>"""


def _load_page() -> str:
    """Load the coming-soon page, cached by mtime.  Falls back to built-in HTML on any error."""
    global _page_content, _page_mtime
    path = _page_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _FALLBACK_PAGE

    with _PAGE_LOCK:
        if _page_mtime == mtime and _page_content is not None:
            return _page_content
        try:
            content = path.read_text(encoding="utf-8")
            _page_content = content
            _page_mtime = mtime
            return content
        except Exception:  # noqa: BLE001
            return _FALLBACK_PAGE


# ---------------------------------------------------------------------------
# Decision function
# ---------------------------------------------------------------------------

def decide(ip: str, headers: dict) -> str:
    """Return 'allow', 'block-ip', or 'block-country'.

    Never raises; any internal error => 'allow' (fail-open).

    Parameters
    ----------
    ip       : real visitor IP string (from _mm_client_ip helper in main.py)
    headers  : dict-like of request headers (lowercased or not; we try both cases)
    """
    try:
        rules = _load_rules()
    except Exception:  # noqa: BLE001
        return "allow"

    try:
        if not rules.get("enabled", False):
            return "allow"

        # Step 4: allow_ips precedence (allow always wins over any block)
        allow_ips = rules.get("allow_ips") or []
        if _ip_in_list(ip, allow_ips):
            return "allow"

        # Step 5: blocked_ips
        blocked_ips = rules.get("blocked_ips") or []
        if _ip_in_list(ip, blocked_ips):
            return "block-ip"

        # Step 6+7: country. The header lookup is cheap (dict.get), so we always
        # run it — that keeps the admin health badge honest even before any
        # country rule exists. The GeoIP DB read is the only expensive step, so
        # we only pay it when there are country rules AND the header didn't
        # resolve, and we feed it the already-resolved `ip` (no header re-parse).
        blocked_countries = rules.get("blocked_countries") or []
        country, source = _resolve_country_header(headers)
        if country is None and blocked_countries:
            country, source = _resolve_country_geoip(ip)
        _update_last_country(country, source)
        if blocked_countries and country and country in blocked_countries:
            return "block-country"

        return "allow"
    except Exception:  # noqa: BLE001
        return "allow"


def coming_soon_page() -> str:
    """Return the coming-soon HTML body."""
    return _load_page()


# ---------------------------------------------------------------------------
# Status (for /api/gate/status)
# ---------------------------------------------------------------------------

def status() -> dict:
    """Return a status dict.  Cheap — reads cached rule state only."""
    try:
        rules = _load_rules()
    except Exception:  # noqa: BLE001
        rules = _EMPTY_RULES

    with _last_country_lock:
        last_country = _last_country
        last_source = _last_country_source

    db_ok = _get_geoip_reader() is not None

    # Honest health: only claim a live source once a real request actually
    # resolved a country through it (last_source). GeoIP counts as available if
    # its db loads. Otherwise detection is genuinely 'unavailable' — the badge
    # tells the operator to enable the EdgeOne country header.
    if last_source:
        cd_source = last_source
    elif db_ok:
        cd_source = "geoip"
    else:
        cd_source = "unavailable"

    return {
        "ok": True,
        "enabled": bool(rules.get("enabled", False)),
        "counts": {
            "ips": len(rules.get("blocked_ips") or []),
            "countries": len(rules.get("blocked_countries") or []),
            "allow": len(rules.get("allow_ips") or []),
        },
        "country_detection": {
            "source": cd_source,
            "last_seen_country": last_country,
            "geoip_db": db_ok,
            "header_name": _country_header_name(),
        },
        "updated_at": rules.get("updated_at"),
    }
