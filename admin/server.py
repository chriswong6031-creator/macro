"""HTTP server for the admin console.

Stdlib http.server (no web framework / no new mandatory deps). Serves a
single-page UI from admin/static and a JSON API under /api/*.

Two run modes (see settings.py):
  • Local (default): binds 127.0.0.1; auth optional (open if no ADMIN_PASSWORD,
    exactly like the original localhost tool).
  • Deployed (ADMIN_DEPLOYED=1): still BINDS 127.0.0.1 — Caddy reverse-proxies
    admin.mastermind-x.com to it — but now password auth is REQUIRED, the
    configured public Host is accepted, and X-Forwarded-Proto from the local
    proxy is trusted for the Secure cookie flag. Config mutations route through
    the GitHub Contents API (the VPS clone is read-only/ephemeral) instead of a
    local working-tree edit.

Security model when auth is enabled: a signed session cookie gates every /api/*
route except the login/session/health probes; writes additionally require a
double-submit CSRF header and a same-origin Origin + JSON Content-Type.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import threading
import time
from collections import OrderedDict
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import (actions, ai_cost, alerts as _alerts_mod, allies_store, analytics_first_party, auth, brain_guest, brief, causal_lab,
               chronicle,
               codex_panel,
               config_store,
               content, context_lobe, email_center, entitlements, experiments,
               flags, ga4, github_api, github_config, gitops, health, long_hold,
               live_runs,
               marketing,
               marketing_floor,
               mastermind_logs,
               mastermind_proxy,
               metabolism_history,
               metabolism_panel,
               neural_web,
               orchestrator_chat,
               personas,
               press,
               prophet,
               revenue,
               services, settings, site_gate,
               support_tickets,
               system, trade_memory, umami, uptime_board, users, vector_override)
from .paths import STATIC

_CTYPES = {".html": "text/html; charset=utf-8",
           ".css": "text/css; charset=utf-8",
           ".js": "application/javascript; charset=utf-8"}

# The SPA bundle is public (the authenticated data is not), so give it
# content-addressed URLs and let the browser/edge keep each immutable revision.
# index.html itself remains no-store and always points at the current hashes.
_STATIC_ASSET_NAMES = ("app.js", "styles.css")
_STATIC_ASSET_VERSIONS = {
    name: hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]
    for name in _STATIC_ASSET_NAMES
}

# Page panels are read-only snapshots assembled from files and integrations. Several
# take hundreds of milliseconds (or more on the VPS) to fold, while a human commonly
# switches away and back within a few seconds. Keep serialized successful responses
# briefly in-process. Browser caching remains forbidden because these payloads contain
# private operator data; the session guard runs before this cache is consulted.
_API_CACHE_TTL_S = 15.0
_API_CACHE_MAX_ENTRIES = 256
_API_RESPONSE_CACHE: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_API_RESPONSE_CACHE_LOCK = threading.Lock()
_API_RESPONSE_CACHE_GENERATION = 0
_API_CACHE_BYPASS_PATHS = {
    "/api/session",
    "/api/auth-check",
    "/api/live_runs",
    "/api/analytics/fp/realtime",
}


def _cacheable_api_get(path: str, query: dict) -> bool:
    return (
        path.startswith("/api/")
        and path not in _API_CACHE_BYPASS_PATHS
        and (query.get("force") or ["0"])[0].lower() not in {"1", "true", "yes", "on"}
    )


def _cached_api_body(key: str) -> bytes | None:
    now = time.monotonic()
    with _API_RESPONSE_CACHE_LOCK:
        cached = _API_RESPONSE_CACHE.get(key)
        if cached is None:
            return None
        expires_at, body = cached
        if expires_at <= now:
            _API_RESPONSE_CACHE.pop(key, None)
            return None
        _API_RESPONSE_CACHE.move_to_end(key)
        return body


def _store_api_body(key: str, body: bytes, generation: int) -> None:
    now = time.monotonic()
    with _API_RESPONSE_CACHE_LOCK:
        if generation != _API_RESPONSE_CACHE_GENERATION:
            return
        expired = [k for k, (expires_at, _) in _API_RESPONSE_CACHE.items()
                   if expires_at <= now]
        for old_key in expired:
            _API_RESPONSE_CACHE.pop(old_key, None)
        _API_RESPONSE_CACHE[key] = (now + _API_CACHE_TTL_S, body)
        _API_RESPONSE_CACHE.move_to_end(key)
        while len(_API_RESPONSE_CACHE) > _API_CACHE_MAX_ENTRIES:
            _API_RESPONSE_CACHE.popitem(last=False)


def _clear_response_cache() -> None:
    global _API_RESPONSE_CACHE_GENERATION
    with _API_RESPONSE_CACHE_LOCK:
        _API_RESPONSE_CACHE.clear()
        _API_RESPONSE_CACHE_GENERATION += 1


def _response_cache_generation() -> int:
    with _API_RESPONSE_CACHE_LOCK:
        return _API_RESPONSE_CACHE_GENERATION


def _server_cache_namespace(server) -> str:
    namespace = getattr(server, "_admin_cache_namespace", None)
    if namespace is None:
        # Object ids may be reused after a short-lived test/dev server shuts down.
        namespace = f"{id(server):x}-{time.monotonic_ns():x}"
        setattr(server, "_admin_cache_namespace", namespace)
    return namespace

# Content-Security-Policy for the console document + every API response. default-src
# 'none' is the floor. script-src/style-src keep 'unsafe-inline' because the hand-rolled
# SPA renders ~31 inline on*= handlers + inline style attributes (refactoring those to
# delegated listeners is the follow-up that lets us drop 'unsafe-inline' from script-src);
# https://unpkg.com is the Leaflet map on Analytics -> Map. The real teeth even with
# inline scripts allowed: connect-src 'self' stops an injected script exfiltrating to an
# external origin, and object-src/base-uri/form-action shut the classic XSS pivots.
_CSP = ("default-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'")


def _int_param(q: dict, key: str, default: int, lo: int, hi: int) -> int:
    """Parse an integer query parameter, returning *default* on error and clamping to [lo, hi]."""
    try:
        v = int((q.get(key) or [default])[0])
    except (ValueError, TypeError):
        return default
    return max(lo, min(hi, v))


def _mm_log_filters(q: dict) -> dict:
    """Build the mastermind_logs filter dict from a parsed query string.

    Recognised params: surface, lane, model, mode, graded (yes|no|all),
    thumb (up|down|all), starred (1), error (1), search (substring), since (ISO/date),
    thinking (1 → only rows carrying a reasoning trace), contra (1 → only rows the
    deterministic conflict scan hits), verdict (LLM contradiction label).
    """
    def one(key: str) -> str:
        return (q.get(key) or [""])[0].strip()
    return {
        "surface": one("surface") or "all",
        "lane": one("lane") or "all",
        "model": one("model"),
        "mode": one("mode"),
        "graded": one("graded") or "all",
        "thumb": one("thumb") or "all",
        "starred": one("starred") in ("1", "true", "yes", "on"),
        "error": one("error") in ("1", "true", "yes", "on"),
        "has_thinking": one("thinking") in ("1", "true", "yes", "on"),
        "contra": one("contra") in ("1", "true", "yes", "on"),
        "verdict": one("verdict"),
        "q": one("search"),
        "since": one("since"),
    }


def _sanitize_target_id(raw) -> str | None:
    """Allow ONLY [a-z0-9-] in an allies target_id (path-traversal guard).

    Returns the id if it is non-empty and matches the allowlist, else None.
    This runs before any filesystem read of a per-target kit file.
    """
    import re  # noqa: PLC0415
    s = str(raw or "")
    if s and re.fullmatch(r"[a-z0-9-]+", s):
        return s
    return None


_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}

# W-AI: orchestrator settings editable from the Master Brain page.
# key → (kind, lo, hi); ints are REJECTED (400) outside [lo, hi], never clamped.
_ORCH_SETTINGS_SPEC = {
    "review_every_n_runs": ("int", 2, 50),
    "site_rows": ("int", 10, 365),
    "ingest_bot_feedback": ("bool", None, None),
    "brief_attention_nudges": ("bool", None, None),
}

# W-AI: Prophet settings editable from the Prophet admin page.
# key → (kind, lo, hi); ints REJECTED (400) outside [lo, hi], never clamped.
_PROPHET_SETTINGS_SPEC = {
    "autopsy_cap_per_cycle":         ("int",  0,  50),
    "fable_enabled":                 ("bool", None, None),
    "deliberation_daily_token_cap":  ("int",  0,  5_000_000),
}


def validate_prophet_setting(key, value) -> tuple[bool, str | None, object]:
    """Server-side validation for POST /api/prophet/settings.
    Returns (ok, error, coerced_value)."""
    spec = _PROPHET_SETTINGS_SPEC.get(key or "")
    if not spec:
        return False, (f"unknown prophet setting {key!r}; "
                       f"allowed: {sorted(_PROPHET_SETTINGS_SPEC)}"), None
    kind, lo, hi = spec
    if kind == "bool":
        if not isinstance(value, bool):
            return False, f"{key} must be a boolean", None
        return True, None, value
    if isinstance(value, bool):
        return False, f"{key} must be an integer", None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        return False, f"{key} must be an integer", None
    if not (lo <= value <= hi):
        return False, f"{key} must be between {lo} and {hi}", None
    return True, None, value


# W-AI: Marketing lobe settings (read-only echo — config_store targets config.yml
# and has no set_string; marketing settings live in config/marketing.yml with string
# enum knobs, so no write path is wired; display only).
_MARKETING_SETTINGS_SPEC = {
    "trial_variant":      ("enum", ["7_trading_days", "14_calendar_days", "value_moment_limited"]),
    "desk_network_stage": ("enum", ["A", "B", "C"]),
    "paid_enabled":       ("bool", None),
    "auditor_strict":     ("bool", None),
}


def validate_marketing_setting(key, value) -> tuple[bool, str | None, object]:
    """Server-side validation for marketing settings (read-only; no POST route wired).
    Returns (ok, error, coerced_value).  Provided for completeness and future use."""
    spec = _MARKETING_SETTINGS_SPEC.get(key or "")
    if not spec:
        return False, (f"unknown marketing setting {key!r}; "
                       f"allowed: {sorted(_MARKETING_SETTINGS_SPEC)}"), None
    kind = spec[0]
    if kind == "bool":
        if not isinstance(value, bool):
            return False, f"{key} must be a boolean", None
        return True, None, value
    if kind == "enum":
        choices = spec[1]
        if value not in choices:
            return False, f"{key} must be one of {choices}", None
        return True, None, value
    return False, f"unsupported kind {kind!r}", None


def validate_orchestrator_setting(key, value) -> tuple[bool, str | None, object]:
    """Server-side validation for POST /api/orchestrator/settings.
    Returns (ok, error, coerced_value)."""
    spec = _ORCH_SETTINGS_SPEC.get(key or "")
    if not spec:
        return False, (f"unknown orchestrator setting {key!r}; "
                       f"allowed: {sorted(_ORCH_SETTINGS_SPEC)}"), None
    kind, lo, hi = spec
    if kind == "bool":
        if not isinstance(value, bool):
            return False, f"{key} must be a boolean", None
        return True, None, value
    if isinstance(value, bool):
        return False, f"{key} must be an integer", None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        return False, f"{key} must be an integer", None
    if not (lo <= value <= hi):
        return False, f"{key} must be between {lo} and {hi}", None
    return True, None, value


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().strip("[]")
    if h in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _host_only(host_header: str) -> str:
    """Strip the :port (and IPv6 brackets) from a Host header."""
    h = (host_header or "").strip()
    if h.startswith("["):                 # [::1]:port
        return h[1:].split("]")[0]
    if ":" in h and h.count(":") >= 2:   # bare IPv6 (e.g. ::1) — no port component
        return h
    return h.rsplit(":", 1)[0] if ":" in h else h


def _integrations() -> dict:
    return {
        "umami": umami.status()["configured"],
        "supabase": users.status()["configured"],
        "github_write": github_config.available(),
        "github_read": github_api.available()["ok"],
    }


def _repo_summary(cfg: dict | None = None) -> dict:
    gh = github_api.available()
    return {
        "repo": f"{gh.get('owner')}/{gh.get('repo')}" if gh.get("owner") else None,
        "github_ok": gh["ok"],
        "has_token": gh["has_token"],
        "site_url": config_store.get_value("notify.site_url", cfg),
        "ga_configured": ga4.status()["configured"],
        "deployed": settings.deployed(),
        "auth_enabled": settings.auth_enabled(),
        "public_url": settings.public_url(),
        "integrations": _integrations(),
    }


def _summary_payload() -> dict:
    """Build the landing snapshot while parsing the large config only once."""
    def _safe(fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    shared_cfg = _safe(config_store.read_config)
    if not isinstance(shared_cfg, dict) or set(shared_cfg) == {"error"}:
        shared_cfg = None

    result = {
        "meta": _safe(lambda: _repo_summary(shared_cfg)),
        "flags": _safe(lambda: flags.snapshot(shared_cfg)),
        "brief": _safe(lambda: brief.panel(shared_cfg)),
        "health": _safe(health.summary),
        "cost": _safe(lambda: ai_cost.estimate(shared_cfg)),
        "git": _safe(gitops.status),
        "system": _safe(system.snapshot),
        "services": _safe(services.status),
        "experiments": _safe(experiments.alert_summary),
    }
    if isinstance(result["health"], dict) and "error" not in result["health"]:
        result["health"] = {
            k: v for k, v in result["health"].items()
            if k not in ("source_rows", "markets")
        }
    if isinstance(result["cost"], dict) and "error" not in result["cost"]:
        result["cost"] = {
            k: result["cost"].get(k)
            for k in ("monthly_usd", "effective_daily_usd")
        }
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "MacroAdmin/2.0"

    # ---- low-level helpers --------------------------------------------------
    def _json(self, obj, code: int = 200, cookies: list[str] | None = None) -> None:
        body = json.dumps(obj, default=str).encode()
        cache_key = getattr(self, "_response_cache_key", None)
        cache_status = None
        if code == 200 and cache_key:
            key, generation = cache_key
            _store_api_body(key, body, generation)
            cache_status = "MISS"
        self._response_cache_key = None
        self._json_body(body, code=code, cookies=cookies, cache_status=cache_status)

    def _json_body(self, body: bytes, code: int = 200,
                   cookies: list[str] | None = None,
                   cache_status: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cache_status:
            self.send_header("X-Admin-Cache", cache_status)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", _CSP)
        for c in (cookies or []):
            self.send_header("Set-Cookie", c)
        self.end_headers()
        self.wfile.write(body)

    def _csv(self, filename: str, body: bytes) -> None:
        """A real file download, not a JSON envelope the client re-wraps.

        The other export on this console (mastermind response logs) returns its CSV as a
        string inside JSON and lets app.js build a Blob. That is the right shape for an
        export the operator filters interactively; it is the wrong shape here, where a
        roster can run to tens of thousands of rows: JSON-escaping the whole file and
        holding two copies of it in browser memory to save one round trip is a bad trade,
        and `Content-Disposition` lets the link be an ordinary <a download> that the
        session cookie already authorises.

        Same security headers as _json, plus nosniff — the browser must not be talked
        into rendering a text/csv body as anything else.
        """
        safe = re.sub(r'[^A-Za-z0-9._-]', "_", filename or "export.csv")[:120] or "export.csv"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", _CSP)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name: str) -> None:
        p = (STATIC / name).resolve()
        if not str(p).startswith(str(STATIC.resolve())) or not p.is_file():
            self._json({"error": "not found"}, 404)
            return
        body = p.read_bytes()
        if name == "index.html":
            for asset_name, version in _STATIC_ASSET_VERSIONS.items():
                body = body.replace(
                    asset_name.encode(),
                    f"{asset_name}?v={version}".encode(),
                )
        self.send_response(200)
        self.send_header("Content-Type", _CTYPES.get(p.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        if name in _STATIC_ASSET_VERSIONS:
            version = _STATIC_ASSET_VERSIONS[name]
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("ETag", f'"{version}"')
        else:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", _CSP)
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0:
                return {}
            if n > 1_000_000:
                return {}
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            return {}

    def log_message(self, fmt, *args):  # quieter console
        return

    # ---- auth / cookies -----------------------------------------------------
    def _cookies(self) -> SimpleCookie:
        c = SimpleCookie()
        raw = self.headers.get("Cookie")
        if raw:
            try:
                c.load(raw)
            except Exception:  # noqa: BLE001
                pass
        return c

    def _cookie_val(self, name: str) -> str | None:
        m = self._cookies().get(name)
        return m.value if m else None

    def _authed(self) -> bool:
        return auth.valid_session(self._cookie_val(auth.SESSION_COOKIE))

    def _client_id(self) -> str:
        """Real client IP for per-client login throttling. SECURITY: the admin host is
        grey-cloud / direct-to-origin (see app/deploy/Caddyfile), so the HTTP client is
        the open internet and any forwarding header it sends is untrusted. Caddy injects
        the verified TCP peer as X-Admin-Client-IP (header_up replaces a spoofed one) —
        trust that first. Fall back to the LAST X-Forwarded-For hop, which is the element
        Caddy appends (the real peer); the FIRST hop is attacker-controlled and must
        never be trusted — reading it let a brute-force client rotate the header per
        request to land every guess in a fresh lockout bucket and defeat the throttle."""
        if settings.deployed():
            trusted = (self.headers.get("X-Admin-Client-IP") or "").strip()
            if trusted:
                return trusted[:64]
            hops = [h.strip() for h in (self.headers.get("X-Forwarded-For") or "").split(",") if h.strip()]
            if hops:
                return hops[-1][:64]
        try:
            return self.client_address[0]
        except Exception:  # noqa: BLE001
            return "-"

    def _real_client_ip(self) -> str:
        """The visitor IP for the site-access gate's self-lockout allow-list. SECURITY:
        the admin host is NOT behind the site's CDN, so the CDN real-client headers
        (EO-/CF-Connecting-IP, True-Client-IP) are never set by our infra here — an
        inbound one is attacker-supplied and must not be honoured (it would let a caller
        poison the gate's auto-allow list). Use the verified IP from _client_id(); the
        operator's public IP is the same whether they reach the admin host directly or
        the CDN-fronted site, so the auto-allowed IP still matches what the gate sees."""
        return self._client_id()

    def _secure_cookie(self) -> bool:
        # Deployed mode is always behind Caddy/TLS — Secure flag is always set.
        # Local mode binds loopback-only over plain http; X-Forwarded-Proto from
        # the request is spoofable by any caller, so the Secure flag is never set
        # (it would be useless over http anyway).
        return settings.deployed()

    def _set_cookies(self, session: str, csrf: str, clear: bool = False) -> list[str]:
        attrs = "; Path=/; SameSite=Strict"
        if self._secure_cookie():
            attrs += "; Secure"
        age = 0 if clear else settings.session_ttl_hours() * 3600
        sv, cv = ("" if clear else session), ("" if clear else csrf)
        return [
            f"{auth.SESSION_COOKIE}={sv}; HttpOnly{attrs}; Max-Age={age}",
            f"{auth.CSRF_COOKIE}={cv}{attrs}; Max-Age={age}",   # readable by JS (double-submit)
        ]

    def _host_ok(self) -> bool:
        host = _host_only(self.headers.get("Host", "")).lower()
        if is_loopback_host(host):
            return True
        return settings.deployed() and host in settings.allowed_hosts()

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True   # non-browser / same-origin fetch without Origin
        allowed = set()
        port = self.server.server_address[1]
        allowed |= {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        if settings.deployed():
            for h in settings.allowed_hosts():
                allowed.add(f"https://{h}")
        return origin in allowed

    def _guard(self, write: bool) -> tuple[str, int] | None:
        """Transport-level checks: Host (DNS-rebinding), and for writes the
        Content-Type + Origin (CSRF). Returns (error, status) or None."""
        if not self._host_ok():
            return ("Host not allowed", 403)
        if write:
            ct = (self.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
            if ct != "application/json":
                return ("Content-Type must be application/json", 415)
            if not self._origin_ok():
                return ("cross-origin request rejected", 403)
        return None

    # ---- GET ----------------------------------------------------------------
    _PUBLIC_GET = {"/", "/index.html", "/app.js", "/styles.css", "/favicon.ico",
                   "/healthz", "/api/session"}

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        self._response_cache_key = None
        try:
            g = self._guard(write=False)
            if g:
                return self._json({"error": g[0]}, g[1])

            # public, no-auth surfaces
            if path in ("/", "/index.html"):
                return self._file("index.html")
            if path in ("/app.js", "/styles.css"):
                return self._file(path.lstrip("/"))
            if path == "/favicon.ico":
                return self._json({}, 204)
            if path == "/healthz":
                return self._json({"ok": True, "service": "macro-admin",
                                   "deployed": settings.deployed()})
            if path == "/api/session":
                return self._json({
                    "auth_enabled": settings.auth_enabled(),
                    "authenticated": (not settings.auth_enabled()) or self._authed(),
                    "deployed": settings.deployed(),
                    "public_url": settings.public_url(),
                    "integrations": _integrations(),
                })

            # everything else under /api requires a session when auth is on
            if settings.auth_enabled() and not self._authed():
                return self._json({"error": "authentication required"}, 401)

            if _cacheable_api_get(path, q):
                cache_key = f"{_server_cache_namespace(self.server)}:{self.path}"
                cached_body = _cached_api_body(cache_key)
                if cached_body is not None:
                    return self._json_body(cached_body, cache_status="HIT")
                self._response_cache_key = (cache_key, _response_cache_generation())

            # Caddy uses this same-origin, cookie-authenticated probe before
            # serving /research-tools/* from the generated site tree.
            if path == "/api/auth-check":
                return self._json({"ok": True, "authenticated": True})

            if path == "/api/summary":
                # Each component is isolated so one failure degrades one landing tile.
                # The full Health/AI-Cost tabs still fetch their dedicated endpoints.
                return self._json(_summary_payload())
            if path == "/api/flags":
                return self._json(flags.snapshot())
            if path == "/api/brain/guest":
                # Mastermind AI guest-access knob (anonymous free Fast lane). Read-only state
                # for the card; the POST twin persists changes.
                return self._json({"ok": True, "guest": brain_guest.read()})
            if path == "/api/brief":
                return self._json(brief.panel())
            if path == "/api/experiments":
                return self._json(experiments.panel())
            if path == "/api/vector_override":
                # OWNER-ONLY (W3/D2): behind the same auth as every other panel;
                # numbers only, no action affordances (D3).
                return self._json(vector_override.panel())
            if path == "/api/long_hold":
                return self._json(long_hold.panel())
            if path == "/api/context_lobe":
                return self._json(context_lobe.panel())
            if path == "/api/causal_lab":
                return self._json(causal_lab.panel())
            if path == "/api/neural_web":
                return self._json(neural_web.panel())
            if path == "/api/neural_web/lobes":
                return self._json(neural_web.lobes_panel())
            if path == "/api/neural_web/lobe":
                return self._json(neural_web.lobe_detail((q.get("id") or [""])[0]))
            # W-AI: Master Brain (orchestrator) page + Mastermind AI bot proxy
            if path == "/api/orchestrator":
                return self._json(neural_web.orchestrator_panel())
            # W-AI: Prophet NW lobe governor page
            if path == "/api/prophet":
                return self._json(prophet.panel())
            if path == "/api/prophet/trade-memory":
                return self._json(trade_memory.panel())
            # Marketing lobe admin pages
            # The floor/model-desk/lanes trio is the operator's view INSIDE the
            # factory: per-station yield with every loss named, model routing +
            # key-pool balancer, and the X-growth lanes' live/dark state.
            if path == "/api/marketing/floor":
                return self._json(marketing_floor.floor())
            if path == "/api/marketing/models":
                return self._json(marketing_floor.models())
            if path == "/api/marketing/lanes":
                return self._json(marketing_floor.lanes())
            if path == "/api/marketing/overview":
                return self._json(marketing.overview())
            if path == "/api/marketing/departments":
                return self._json(marketing.departments())
            if path == "/api/marketing/channels":
                return self._json(marketing.channels())
            if path == "/api/marketing/campaigns":
                return self._json(marketing.campaigns())
            if path == "/api/marketing/experiments":
                return self._json(marketing.experiments())
            if path == "/api/marketing/ad-central":
                return self._json(marketing.ad_central())
            if path == "/api/marketing/lobes":
                return self._json(marketing.lobes())
            if path == "/api/marketing/content":
                return self._json(marketing.content())
            if path == "/api/marketing/lab":
                return self._json(marketing.lab())
            if path == "/api/marketing/sentinel":
                return self._json(marketing.sentinel())
            if path == "/api/marketing/radar":
                return self._json(marketing.radar())
            if path == "/api/marketing/seo":
                return self._json(marketing.seo())
            if path == "/api/marketing/department":
                dept_id = (q.get("id") or [None])[0]
                return self._json(marketing.department(dept_id=dept_id))
            if path == "/api/marketing/outbox":
                return self._json(marketing.outbox())
            # The reply desk's SEPARATE queue (XG-W4). Lives in host state
            # (~/.mastermind/reply_desk), not the repo — Buffer cannot reply, so
            # these never travel the outbox rail.
            if path == "/api/marketing/reply-queue":
                return self._json(marketing.reply_queue())
            # XG-W6 learning loop: the weekly hook x format x register x account
            # scorecard plus the learned-rule version log that ships beside it.
            # Operator console only — nothing here is user-facing.
            if path == "/api/marketing/learning":
                return self._json(marketing.learning_scorecard())
            # XG-W6 account health + network tripwire + the halt registry.
            # Read-only: opening this panel can neither trip nor clear a halt.
            if path == "/api/marketing/health":
                return self._json(marketing.account_health())
            if path == "/api/marketing/publish":
                return self._json(marketing.publisher())
            # The rejection box — everything rejected since the last export.
            if path == "/api/marketing/rejections":
                return self._json(marketing.rejections_pending())
            if path == "/api/marketing/outbox/media":
                from .paths import ROOT as _REPO_ROOT  # noqa: PLC0415
                req_path = (q.get("path") or [""])[0]
                if not req_path:
                    return self._json({"error": "path parameter required"}, 400)
                media_root = (_REPO_ROOT / "data" / "marketing" / "outbox" / "media").resolve()
                resolved = (_REPO_ROOT / req_path).resolve()
                if not str(resolved).startswith(str(media_root) + "/") or not resolved.is_file():
                    return self._json({"error": "not found"}, 404)
                body = resolved.read_bytes()
                ctype = "image/svg+xml" if resolved.suffix == ".svg" else "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                # SVG opened directly is an active document (scripts execute);
                # this CSP neutralizes that. <img> embedding is unaffected.
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; style-src 'unsafe-inline'; sandbox")
                self.end_headers()
                self.wfile.write(body)
                return
            # Allies (ecosystem) cockpit — MKT-D11. Read-only; the page never
            # contacts anyone. Status is folded from the operator ledger.
            if path == "/api/marketing/allies":
                return self._json(marketing.allies())
            if path == "/api/marketing/allies/kit":
                raw = (q.get("target_id") or [""])[0]
                # Sanitise: allow ONLY [a-z0-9-] before any filesystem read.
                tid = _sanitize_target_id(raw)
                if not tid:
                    return self._json({"ok": False, "error": "invalid target_id"}, 400)
                return self._json(marketing.allies_kit(target_id=tid))
            # Chronicle (market context timeline) admin inspector — read-only.
            if path == "/api/chronicle/overview":
                return self._json(chronicle.overview())
            # Persona Network roster (config/personas/ ⋈ desk_network) — read-only.
            if path == "/api/personas/roster":
                return self._json(personas.roster())
            # Press (D14 Media Network W1) inspector — read-only, fail-soft.
            if path == "/api/press/overview":
                return self._json(press.overview())
            # W-AI: Mastermind AI response log — batch-evaluatable corpus of every
            # user-facing answer (Macro brain + Terminal copilot), ingested from R2.
            if path == "/api/mastermind_ai/response_logs":
                limit = _int_param(q, "limit", 100, 1, 500)
                return self._json(mastermind_logs.logs(limit=limit, filters=_mm_log_filters(q)))
            if path == "/api/mastermind_ai/response_logs/export":
                fmt = (q.get("fmt") or ["jsonl"])[0]
                return self._json(mastermind_logs.export(filters=_mm_log_filters(q), fmt=fmt))
            # One row's reasoning trace, fetched when the operator expands that row —
            # the list response carries only thinking_meta (see mastermind_logs.logs).
            if path == "/api/mastermind_ai/response_logs/thinking":
                return self._json(mastermind_logs.thinking_trace((q.get("id") or [""])[0]))
            # W2 answer-quality harness: the latest weekly LLM-judge summary
            # (scripts/run_brain_eval.py → data/mastermind/eval_summary_latest.json).
            # Read-only, no params; absent file answers 200 with {ok: false}.
            if path == "/api/mastermind_ai/response_logs/eval_summary":
                return self._json(mastermind_logs.eval_summary())
            if path in mastermind_proxy.GET_PATHS:
                payload, code = mastermind_proxy.forward_get(path, u.query)
                return self._json(payload, code)
            if path == "/api/health":
                return self._json(health.summary())
            if path == "/api/cost":
                return self._json(ai_cost.estimate())
            if path == "/api/content":
                return self._json(content.inventory())
            if path == "/api/content/links":
                return self._json(content.link_check())
            if path == "/api/uptime":
                return self._json(content.uptime())
            if path == "/api/uptime/all":
                return self._json(uptime_board.probe_all())
            # Standalone ops/debug routes — no SPA callers; kept for curl/ops debugging only.
            if path == "/api/git":
                return self._json(gitops.status())
            if path == "/api/deploy":
                _wf_raw = (q.get("workflow") or [None])[0]
                _ALLOWED_WF = {"daily.yml", "pages.yml", "weekly.yml"}
                wf = _wf_raw if _wf_raw in _ALLOWED_WF else None
                return self._json(github_api.list_runs(workflow=wf))
            # analytics — Umami primary, GA4 kept as a secondary source
            if path == "/api/analytics":
                return self._json(umami.status())
            if path == "/api/analytics/report":
                days = _int_param(q, "days", 7, 1, 365)
                return self._json(umami.report(days=days))
            if path == "/api/analytics/active":
                return self._json(umami.active())
            if path == "/api/traffic":
                return self._json(ga4.status())
            if path == "/api/traffic/realtime":
                return self._json(ga4.realtime())
            if path == "/api/traffic/report":
                days = _int_param(q, "days", 7, 1, 365)
                return self._json(ga4.report(days=days))
            # first-party analytics (self-hosted; reads analytics_events/search_events/ip_geo).
            # Params are string-in; the reader int-clamps days/limit/gap and allowlist-validates
            # ids. `gap` = idle minutes that end a visit (default 30) — the knob behind the
            # per-tab/per-origin session stitching.
            if path == "/api/analytics/fp/overview":
                return self._json(analytics_first_party.overview(days=(q.get("days") or ["7"])[0], minutes=(q.get("minutes") or [None])[0], gap=(q.get("gap") or [None])[0]))
            if path == "/api/analytics/fp/pages":
                return self._json(analytics_first_party.pages(days=(q.get("days") or ["7"])[0], minutes=(q.get("minutes") or [None])[0], limit=(q.get("limit") or ["25"])[0]))
            if path == "/api/analytics/fp/geo":
                return self._json(analytics_first_party.geo(days=(q.get("days") or ["30"])[0], minutes=(q.get("minutes") or [None])[0], limit=(q.get("limit") or ["200"])[0]))
            if path == "/api/analytics/fp/sessions":
                return self._json(analytics_first_party.sessions(
                    limit=(q.get("limit") or ["100"])[0], q=(q.get("q") or [""])[0],
                    include_bots=(q.get("bots") or ["0"])[0] in ("1", "true", "yes"),
                    minutes=(q.get("minutes") or [None])[0], gap=(q.get("gap") or [None])[0]))
            if path == "/api/analytics/fp/visitors":
                return self._json(analytics_first_party.visitors(
                    limit=(q.get("limit") or ["250"])[0], q=(q.get("q") or [""])[0],
                    include_bots=(q.get("bots") or ["0"])[0] in ("1", "true", "yes"),
                    minutes=(q.get("minutes") or [None])[0], gap=(q.get("gap") or [None])[0]))
            if path == "/api/analytics/fp/session":
                return self._json(analytics_first_party.session(
                    (q.get("id") or [""])[0], gap=(q.get("gap") or [None])[0]))
            if path == "/api/analytics/fp/flow":
                return self._json(analytics_first_party.flow(days=(q.get("days") or ["7"])[0], minutes=(q.get("minutes") or [None])[0], limit=(q.get("limit") or ["40"])[0]))
            if path == "/api/analytics/fp/terminal":
                return self._json(analytics_first_party.terminal(days=(q.get("days") or ["7"])[0], minutes=(q.get("minutes") or [None])[0], limit=(q.get("limit") or ["25"])[0]))
            if path == "/api/analytics/fp/visitor":
                return self._json(analytics_first_party.visitor(
                    (q.get("id") or [""])[0], gap=(q.get("gap") or [None])[0]))
            if path == "/api/analytics/fp/realtime":
                return self._json(analytics_first_party.realtime())
            # users (Supabase)
            if path == "/api/users":
                return self._json(users.summary())
            if path == "/api/users/recent":
                limit = _int_param(q, "limit", 30, 1, 1000)
                return self._json(users.recent(limit=limit))
            if path == "/api/users/subscribers":
                limit = _int_param(q, "limit", 200, 1, 500)
                return self._json(users.subscribers(limit=limit))
            # entitlements roster (MNZ W2): auth.users(name,email) ⋈ user_entitlements,
            # filterable by tier/status, searchable, paged. Read via the same Management-API
            # PAT path as /api/users; writes are the POST /api/entitlements/action twin.
            if path == "/api/entitlements":
                return self._json(entitlements.list_users(
                    tier=(q.get("tier") or [None])[0],
                    status=(q.get("status") or [None])[0],
                    search=(q.get("search") or q.get("q") or [None])[0],
                    page=_int_param(q, "page", 1, 1, 100_000),
                    page_size=_int_param(q, "page_size", 50, 1, 200)))
            # support tickets (SEE W1): the operator inbox over public.support_tickets.
            # Read via the SAME Management-API PAT path as /api/users and /api/entitlements;
            # the writes are the POST /api/support_tickets/action twin below.
            if path == "/api/support_tickets":
                return self._json(support_tickets.panel(
                    status=(q.get("status") or [None])[0],
                    q=(q.get("q") or q.get("search") or [None])[0],
                    page=_int_param(q, "page", 1, 1, 100_000),
                    page_size=_int_param(q, "page_size", 50, 1, 200)))
            if path == "/api/support_tickets/detail":
                return self._json(support_tickets.detail((q.get("id") or [""])[0]))
            # Email Center (SEE W4): the roster + segments, the suppression list, the
            # SMTP card and the campaign queue. Same Management-API PAT lane as the two
            # routes above; the writes are the POST twins below.
            if path == "/api/email_center":
                return self._json(email_center.panel(
                    segment=(q.get("segment") or [None])[0],
                    q=(q.get("q") or q.get("search") or [None])[0],
                    page=_int_param(q, "page", 1, 1, 100_000),
                    page_size=_int_param(q, "page_size", 50, 1, 200)))
            if path == "/api/email_center/suppression":
                return self._json(email_center.suppression(
                    q=(q.get("q") or q.get("search") or [None])[0],
                    page=_int_param(q, "page", 1, 1, 100_000),
                    page_size=_int_param(q, "page_size", 50, 1, 200)))
            if path == "/api/email_center/mail":
                return self._json(email_center.mail_status(
                    limit=_int_param(q, "limit", 20, 1, 100)))
            if path == "/api/email_center/campaigns":
                return self._json(email_center.campaigns(
                    limit=_int_param(q, "limit", 25, 1, 100)))
            # The one non-JSON route on this console. Auth is the same session gate every
            # /api path above passed; CSV is a GET, so it carries no CSRF token for the
            # same reason no other GET here does — a double-submit cookie guards writes.
            if path == "/api/email_center/export.csv":
                out = email_center.export_csv(
                    segment=(q.get("segment") or [None])[0],
                    q=(q.get("q") or q.get("search") or [None])[0])
                if isinstance(out, dict):
                    return self._json(out, 503 if out.get("setup_steps") else 400)
                name, blob = out
                return self._csv(name, blob)
            # revenue analytics (billing/revenue suite): MRR/ARR, sub counts, real collected
            # cash, forward projections, and comp give-away counts — computed live from Stripe
            # (Subscription/Invoice + the entitlements comp read), ~60s in-process cache. ?force=1
            # busts the cache for a fresh pull. Stripe unconfigured → {ok:false} (honest empty state).
            if path == "/api/revenue":
                force = (q.get("force") or ["0"])[0] in ("1", "true", "yes")
                return self._json(revenue.summary(force=force))
            # system / services
            if path == "/api/system":
                return self._json(system.snapshot())
            if path == "/api/services":
                return self._json(services.status())
            if path == "/api/alerts":
                # Operator capture feed (RUL-8: authed only, no public write endpoint).
                limit = _int_param(q, "limit", 60, 1, 1000)
                return self._json(_alerts_mod.panel(limit=limit))
            if path == "/api/codex":
                return self._json(codex_panel.panel())
            if path == "/api/live_runs":
                return self._json(live_runs.snapshot())
            if path == "/api/metabolism":
                return self._json(metabolism_panel.panel())
            if path == "/api/metabolism/keys":
                return self._json(metabolism_panel.keys())
            if path == "/api/metabolism/history":
                limit = _int_param(q, "limit", 100, 1, 1000)
                return self._json(metabolism_history.history(limit=limit))
            if path == "/api/site_gate":
                rules = site_gate.read_rules()
                return self._json({
                    "ok": True,
                    "rules": {
                        "enabled": rules["enabled"],
                        "blocked_ips": rules["blocked_ips"],
                        "blocked_countries": rules["blocked_countries"],
                        "allow_ips": rules["allow_ips"],
                        "updated_at": rules.get("updated_at"),
                    },
                    "your_ip": self._real_client_ip(),
                    "site_url": config_store.get_value("notify.site_url"),
                    "gate_status": site_gate.gate_status(),
                })

            if path == "/api/metabolism/achievements":
                try:
                    from admin import metabolism_achievements  # noqa: PLC0415
                    return self._json(metabolism_achievements.achievements())
                except ImportError:
                    return self._json(
                        {"error": "achievements module not yet available", "cycles": []}, 503
                    )
                except Exception as _ae:  # noqa: BLE001
                    return self._json(
                        {"error": f"achievements unavailable: {_ae}", "cycles": []}, 503
                    )

            return self._json({"error": f"unknown route {path}"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        self._response_cache_key = None
        try:
            g = self._guard(write=True)
            if g:
                return self._json({"ok": False, "error": g[0]}, g[1])
            b = self._body()

            # login is the one write allowed pre-session (the password IS the proof)
            if path == "/api/login":
                ok, err = auth.password_ok(b.get("password"), self._client_id())
                if not ok:
                    return self._json({"ok": False, "error": err or "login failed"}, 401)
                csrf = auth.new_csrf()
                _clear_response_cache()
                return self._json({"ok": True},
                                  cookies=self._set_cookies(auth.mint_session(), csrf))
            if path == "/api/logout":
                # CSRF double-submit intentionally omitted: logout is idempotent and
                # SameSite=Strict + Origin check in _guard already prevent cross-site reads.
                return self._json({"ok": True},
                                  cookies=self._set_cookies("", "", clear=True))

            # all other writes require a session + CSRF when auth is enabled
            if settings.auth_enabled():
                if not self._authed():
                    return self._json({"ok": False, "error": "authentication required"}, 401)
                if not auth.csrf_ok(self._cookie_val(auth.CSRF_COOKIE),
                                    self.headers.get(auth.CSRF_HEADER)):
                    return self._json({"ok": False, "error": "CSRF token missing/invalid"}, 403)

            # A successful write may change any composed panel. Clearing the small
            # in-process cache keeps operator actions immediately self-consistent.
            _clear_response_cache()

            if path == "/api/flags/toggle":
                flag_path = b.get("path")
                value = bool(b.get("value"))
                if not flag_path or flag_path not in {f["path"] for f in flags.FLAGS}:
                    return self._json({"ok": False, "error": "unknown or unmanaged flag path"}, 400)
                if settings.deployed():
                    return self._json(github_config.set_bool(flag_path, value))
                return self._json(config_store.set_bool(flag_path, value))

            # Mastermind AI guest-access knob — anonymous free Fast lane on/off + daily cap.
            # NOT routed through config_store/github_config (those target config.yml + a deploy);
            # this is a gitignored, hot-reloaded JSON the gateway re-reads within ~20s.
            if path == "/api/brain/guest":
                enabled = bool(b.get("enabled"))
                raw_limit = b.get("daily_limit")
                if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
                    return self._json({"ok": False, "error": "daily_limit must be an integer"}, 400)
                res = brain_guest.write(enabled, raw_limit)
                return self._json(res, 200 if res.get("ok") else 400)

            if path == "/api/analytics/fp/geo_enrich":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                return self._json(analytics_first_party.geo_enrich_now(budget=b.get("budget") or 300))

            if path == "/api/brief/interval":
                target = b.get("target")
                if target not in ("master_brain", "ai_desk"):
                    return self._json({"ok": False, "error": "target must be master_brain or ai_desk"}, 400)
                dotted = f"{target}.interval_days"
                if settings.deployed():
                    return self._json(github_config.set_int(dotted, b.get("days"), 1, 7))
                return self._json(config_store.set_int(dotted, b.get("days"), 1, 7))

            # W-AI: Master Brain (orchestrator) surface
            if path == "/api/orchestrator/settings":
                key = b.get("key")
                ok, err, value = validate_orchestrator_setting(key, b.get("value"))
                if not ok:
                    return self._json({"ok": False, "error": err}, 400)
                dotted = f"orchestrator.{key}"
                kind, lo, hi = _ORCH_SETTINGS_SPEC[key]
                if kind == "bool":
                    if settings.deployed():
                        return self._json(github_config.set_bool(dotted, value))
                    return self._json(config_store.set_bool(dotted, value))
                if settings.deployed():
                    return self._json(github_config.set_int(dotted, value, lo, hi))
                return self._json(config_store.set_int(dotted, value, lo, hi))

            # W-AI: Prophet NW lobe governor settings
            if path == "/api/prophet/settings":
                key = b.get("key")
                ok, err, value = validate_prophet_setting(key, b.get("value"))
                if not ok:
                    return self._json({"ok": False, "error": err}, 400)
                dotted = f"prophet.{key}"
                kind, lo, hi = _PROPHET_SETTINGS_SPEC[key]
                if kind == "bool":
                    if settings.deployed():
                        return self._json(github_config.set_bool(dotted, value))
                    return self._json(config_store.set_bool(dotted, value))
                if settings.deployed():
                    return self._json(github_config.set_int(dotted, value, lo, hi))
                return self._json(config_store.set_int(dotted, value, lo, hi))

            # Owner-private Trade Memory intake. Personal trade facts go to
            # Supabase only; never through the GitHub config mutation path.
            if path == "/api/prophet/trade-memory":
                result = trade_memory.record(b)
                return self._json(result, 200 if result.get("ok") else 400)

            # REJECT — terminal kill WITH a reason, unlike hold (reversible,
            # stays in the rail). Writes data/marketing/rejections.jsonl, which
            # the review-sheet export reads.
            if path == "/api/marketing/outbox/reject":
                item_id = b.get("id")
                reason = b.get("reason") or b.get("note") or None
                if not item_id or not isinstance(item_id, str):
                    return self._json({"ok": False, "error": "id required"}, 400)
                res = marketing.reject_outbox(item_id, reason=reason)
                return self._json(res, 200 if res.get("ok") else 400)

            # REPLY DESK (XG-W4) — approve/hold one draft. Approving does NOT
            # post: at M0 nothing leaves at all, and at M1 the item is handed to
            # the desktop session, which is the only sender.
            if path == "/api/marketing/reply-queue/decide":
                item_id = b.get("id")
                decision = b.get("decision")
                note = b.get("note") or None
                if decision not in ("approve", "hold"):
                    return self._json({"ok": False, "error": "decision must be 'approve' or 'hold'"}, 400)
                if not item_id or not isinstance(item_id, str):
                    return self._json({"ok": False, "error": "id required"}, 400)
                res = marketing.decide_reply(item_id, decision, note=note)
                return self._json(res, 200 if res.get("ok") else 400)

            # REPLY DESK — terminal kill with a reason. Rejections are the taste
            # corpus, and a reject also releases the thread's one-owner lock.
            if path == "/api/marketing/reply-queue/reject":
                item_id = b.get("id")
                reason = b.get("reason") or b.get("note") or None
                if not item_id or not isinstance(item_id, str):
                    return self._json({"ok": False, "error": "id required"}, 400)
                res = marketing.reject_reply(item_id, reason=reason)
                return self._json(res, 200 if res.get("ok") else 400)

            # XG-W6 — clear ONE halted account. The health monitor cannot clear
            # its own trip, so this route is the only way a halt ends. It halts
            # nothing: there is deliberately no "halt account" route, because a
            # halt is a consequence of measured telemetry, not a button.
            if path == "/api/marketing/health/clear-halt":
                account_id = b.get("account_id") or b.get("account")
                actor = b.get("actor") or "admin"
                note = b.get("note") or None
                if not isinstance(account_id, str) or not account_id.strip():
                    return self._json({"ok": False, "error": "account_id required"}, 400)
                if note is not None and not isinstance(note, str):
                    return self._json({"ok": False, "error": "note must be a string"}, 400)
                res = marketing.clear_halt(account_id, actor=str(actor), note=note)
                return self._json(res, 200 if res.get("ok") else 400)

            # XG-W6 — roll back one applied learned rule. Charter §8: a rule
            # that cannot be reverted may not be learned, so every applied rule
            # has a live path back through here.
            if path == "/api/marketing/learning/rollback":
                version_id = b.get("version_id") or b.get("id")
                actor = b.get("actor") or "admin"
                if not isinstance(version_id, str) or not version_id.strip():
                    return self._json({"ok": False, "error": "version_id required"}, 400)
                res = marketing.rollback_learned_rule(version_id, actor=str(actor))
                return self._json(res, 200 if res.get("ok") else 400)

            # Export the rejection box as an annotatable markdown sheet. Clears
            # the box by default (rows stay in the ledger; only the view resets).
            if path == "/api/marketing/rejections/export":
                res = marketing.export_rejections(mark=b.get("mark", True) is not False)
                return self._json(res, 200 if res.get("ok") else 400)

            if path == "/api/marketing/outbox/decide":
                item_id = b.get("id")
                item_ids = b.get("ids")
                decision = b.get("decision")
                note = b.get("note") or None
                if decision not in ("approve", "hold"):
                    return self._json({"ok": False, "error": "decision must be 'approve' or 'hold'"}, 400)
                # Batch form: {"ids": [...]} — bulk approve/hold from the admin.
                if item_ids is not None:
                    if (not isinstance(item_ids, list) or not item_ids
                            or not all(isinstance(i, str) for i in item_ids)):
                        return self._json({"ok": False, "error": "ids must be a non-empty list of strings"}, 400)
                    if len(item_ids) > 200:
                        return self._json({"ok": False, "error": "at most 200 ids per request"}, 400)
                    res = marketing.decide_outbox_batch(item_ids, decision, note=note)
                    return self._json({"ok": True, "decision": decision, **res})
                # Single form: {"id": "..."} (original contract, kept verbatim)
                if not item_id:
                    return self._json({"ok": False, "error": "id required"}, 400)
                ok = marketing.decide_outbox(item_id, decision, note=note)
                if not ok:
                    return self._json({"ok": False, "error": "unknown item id or write failed"}, 400)
                return self._json({"ok": True, "id": item_id, "decision": decision})

            # Publisher DRY-RUN: compute the "would post" report in-process. This
            # NEVER touches the network and NEVER writes the ledger (dry_run_report
            # calls no transition() / _append_activity()). An optional "account"
            # narrows the report to one desk. Safe with no confirm gate — it has
            # no side effects.
            if path == "/api/marketing/publish/dryrun":
                account = b.get("account") or None
                if account is not None and not isinstance(account, str):
                    return self._json({"ok": False, "error": "account must be a string"}, 400)
                return self._json(marketing.publisher_dryrun(account=account))

            # Sentinel: record an operator exception for one held post. Writes an
            # append-only row that the NEXT nightly gate reads — nothing posts now.
            if path == "/api/marketing/sentinel/allow":
                item_id = b.get("item_id")
                reason = b.get("reason")
                if not isinstance(item_id, str) or not item_id.strip():
                    return self._json({"ok": False, "error": "item_id required"}, 400)
                if not isinstance(reason, str) or not reason.strip():
                    return self._json({"ok": False,
                                       "error": "reason required — say why this post is safe to allow"}, 400)
                res = marketing.sentinel_allow(item_id, reason)
                return self._json(res, 200 if res.get("ok") else 400)

            # Intelligence Desk: queue ONE reviewed draft into the outbox. The
            # operator's click IS the approval, but not the evidence — the handler
            # re-reads the story and the draft from the desk snapshot server-side
            # and runs the canonical press-lane gate chain against the desk's own
            # text, so a tampered or merely stale browser payload cannot post copy
            # no gate saw. This route therefore validates SHAPE only.
            #
            # Refusals come back as {ok:false, reason, detail}: `reason` names the
            # gate that fired and the panel keys its message off it, so pass the
            # handler's dict through untouched rather than flattening it into the
            # `error` shape the guards above use.
            if path == "/api/marketing/intelligence/approve":
                story_id = b.get("story_id")
                draft_id = b.get("draft_id")
                if not isinstance(story_id, str) or not story_id.strip():
                    return self._json({"ok": False, "error": "story_id required"}, 400)
                if not isinstance(draft_id, str) or not draft_id.strip():
                    return self._json({"ok": False, "error": "draft_id required"}, 400)
                res = marketing.intelligence_approve(story_id, draft_id)
                return self._json(res, 200 if res.get("ok") else 400)

            # Desk on/off: merge-write data/marketing/account_overrides.json. Local
            # checkout commits+pushes it; the deployed VPS admin (no git auth) commits
            # it to main via the GitHub Contents API — handled in marketing.accounts_
            # toggle, so this route no longer refuses in deployed mode.
            if path == "/api/marketing/accounts/toggle":
                account_id = b.get("account_id")
                if not isinstance(account_id, str) or not account_id.strip():
                    return self._json({"ok": False, "error": "account_id required"}, 400)
                if "enabled" not in b or not isinstance(b.get("enabled"), bool):
                    return self._json({"ok": False, "error": "enabled must be a boolean"}, 400)
                note = b.get("note")
                if note is not None and not isinstance(note, str):
                    return self._json({"ok": False, "error": "note must be a string"}, 400)
                res = marketing.accounts_toggle(account_id, b.get("enabled"), note=note)
                return self._json(res, 200 if res.get("ok") else 400)

            if path == "/api/orchestrator/chat":
                return self._json(orchestrator_chat.chat(b.get("message", ""),
                                                         history=b.get("history")))

            if path == "/api/orchestrator/wake":
                return self._json(orchestrator_chat.wake())

            # W-AI: Mastermind AI response log — pull new rows from R2, and write
            # operator eval verdicts (grade/thumb/star/tags/note) to the local sidecar.
            if path == "/api/mastermind_ai/response_logs/refresh":
                return self._json(mastermind_logs.refresh())
            if path == "/api/mastermind_ai/response_logs/rate":
                ok_v, err_msg, cleaned = mastermind_logs.validate_rate_body(b)
                if not ok_v:
                    return self._json({"ok": False, "error": err_msg}, 400)
                return self._json(mastermind_logs.rate(cleaned, evaluator="operator"))
            # Contradiction assessment (LLM tier): label the un-verdicted candidates
            # 'system_error' vs 'market_divergence'. Fail-soft — a missing
            # DEEPSEEK_API_KEY answers 200 with {ok: false, error: "no_llm_key"}.
            if path == "/api/mastermind_ai/response_logs/classify":
                try:
                    # The module owns the ceiling — a literal here silently diverges the
                    # day the batch cap moves.
                    _lim = max(1, min(mastermind_logs._CLASSIFY_LIMIT_MAX,
                                      int(b.get("limit") or 20)))
                except (TypeError, ValueError):
                    _lim = 20
                return self._json(mastermind_logs.classify_contradictions(limit=_lim))

            if path in mastermind_proxy.POST_PATHS:
                payload, code = mastermind_proxy.forward_post(path, b)
                return self._json(payload, code)

            if path == "/api/deploy/dispatch":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                wf = b.get("workflow", "daily.yml")
                if wf not in ("daily.yml", "pages.yml", "weekly.yml"):
                    return self._json({"ok": False, "error": "workflow not allowed"}, 400)
                ref = b.get("ref", "main")
                if ref != "main":   # never let pages.yml publish a non-main branch's site/
                    return self._json({"ok": False, "error": "ref must be main"}, 400)
                return self._json(github_api.dispatch(workflow=wf, ref=ref))

            if path == "/api/git/commit":
                if settings.deployed():
                    return self._json({"ok": False, "error":
                                       "not available in deployed mode — flag edits commit "
                                       "directly to main via the GitHub API"}, 400)
                return self._json(gitops.commit(
                    message=b.get("message", "admin: config update"),
                    push=bool(b.get("push")),
                    confirm=bool(b.get("confirm")),
                ))

            if path == "/api/actions":
                surface = b.get("surface", "")
                action = b.get("action", "")
                direction_note = b.get("direction_note", "")
                alert_emit_ts = b.get("alert_emit_ts")
                if not surface:
                    return self._json({"ok": False, "error": "surface required"}, 400)
                if action not in actions.VALID_ACTIONS:
                    return self._json({"ok": False,
                                       "error": f"action must be one of {sorted(actions.VALID_ACTIONS)}"}, 400)
                row = actions.append_action(
                    surface=surface,
                    action=action,
                    direction_note=direction_note,
                    alert_emit_ts=alert_emit_ts,
                )
                return self._json({"ok": True, "row": row})

            # Operator entitlement mutation (MNZ W2 + MNZ-R3): manual tier change, trial
            # extend/reset, free passes, remove-comp. Single-operator console → the audit
            # actor is the constant "operator" (no user DB; matches actions/allies ledgers).
            # Comp-over-live-Stripe is refused unless force+cancel_stripe (see entitlements.py).
            if path == "/api/entitlements/action":
                payload, code = entitlements.act(b, operator="operator")
                return self._json(payload, code)

            # Support ticket transitions (SEE W1): reply / resolve / close / reopen.
            # Legality is decided inside the module against the ticket's CURRENT status
            # read from the database — a client-sent status is never trusted. A reply
            # also emails the ticket's address through app/mailer.py (mail-off safe:
            # the message is still appended and the response carries email_status).
            if path == "/api/support_tickets/action":
                payload, code = support_tickets.act(
                    b.get("ticket_id", ""), b.get("action", ""), b.get("body"),
                    operator="operator")
                return self._json(payload, code)

            # Email Center writes (SEE W4). Suppression add/remove is compliance-
            # sensitive: REMOVE re-enables marketing email to a person who asked us to
            # stop, so the module requires confirm=true in the request itself (a browser
            # confirm() is not an authorisation), refuses to lift a bounce or a complaint,
            # and records the removal in the operator action ledger.
            if path == "/api/email_center/suppression":
                act = (b.get("action") or "").strip()
                if act not in email_center.SUPPRESSION_ACTIONS:
                    return self._json(
                        {"ok": False,
                         "error": f"action must be one of {sorted(email_center.SUPPRESSION_ACTIONS)}"},
                        400)
                if act == "add":
                    payload, code = email_center.suppress(
                        b.get("email", ""), b.get("reason", "manual"), operator="operator")
                else:
                    payload, code = email_center.unsuppress(
                        b.get("email", ""), confirm=bool(b.get("confirm")), operator="operator")
                return self._json(payload, code)

            # Campaign composer: save / queue / abort / delete. Queuing only marks the
            # row — app/marketing_emails.py drains it, and only when the operator has
            # armed MAIL_MARKETING_ENABLED + MAIL_CAMPAIGNS_ENABLED on the API host, so
            # nothing on this console can put mail on the wire by itself.
            if path == "/api/email_center/campaign":
                payload, code = email_center.campaign_action(
                    b.get("action", ""),
                    campaign_id=b.get("id"),
                    subject_en=b.get("subject_en", ""), subject_zh=b.get("subject_zh", ""),
                    body_en=b.get("body_en", ""), body_zh=b.get("body_zh", ""),
                    segment=b.get("segment", ""), operator="operator")
                return self._json(payload, code)

            # Allies (MKT-D11): record an operator status transition. This is a
            # decision-recording write — it NEVER contacts anyone. The transition
            # is validated against the folded current status before it is stamped.
            if path == "/api/marketing/allies/transition":
                raw_id = b.get("target_id", "")
                target_id = _sanitize_target_id(raw_id)
                to_status = b.get("to_status", "")
                note = b.get("note", "")
                if not target_id:
                    return self._json({"ok": False, "error": "invalid target_id"}, 400)
                if to_status not in allies_store.VALID_STATUSES:
                    return self._json({"ok": False,
                                       "error": f"to_status must be one of {list(allies_store.VALID_STATUSES)}"}, 400)
                # Fold to find the target's CURRENT status (server-authoritative,
                # never trusts a client-supplied from_status).
                panel = marketing.allies()
                tgt = next((t for t in (panel.get("targets") or [])
                            if str(t.get("target_id")) == target_id), None)
                if tgt is None:
                    return self._json({"ok": False, "error": f"unknown target_id {target_id!r}"}, 400)
                current = tgt.get("status", allies_store.SEED_STATUS)
                if not allies_store.is_legal(current, to_status):
                    return self._json({"ok": False,
                                       "error": f"illegal transition {current} -> {to_status}",
                                       "current_status": current,
                                       "legal_next": allies_store.legal_next(current)}, 400)
                row = allies_store.append_transition(
                    target_id=target_id,
                    from_status=current,
                    to_status=to_status,
                    note=note,
                )
                return self._json({"ok": True, "row": row})

            if path == "/api/metabolism/toggle":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Actions read + "
                                                "Variables read/write) to control the loop "
                                                "from here."}, 503)
                arm = bool(b.get("armed"))
                new_value = "false" if arm else "true"
                ok = github_api.set_repo_variable("AUTONOMY_PAUSED", new_value)
                if not ok:
                    return self._json({"ok": False,
                                       "error": "Failed to update AUTONOMY_PAUSED — check that "
                                                "GH_TOKEN has Variables write permission."}, 500)
                return self._json({"ok": True, "armed": arm, "variable_value": new_value})

            if path == "/api/metabolism/throttle":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Variables read/write) "
                                                "to set throttle variables."}, 503)
                ok_v, errors, to_set = metabolism_panel.validate_throttle_body(b)
                if not ok_v:
                    return self._json({"ok": False, "errors": errors}, 400)
                if not to_set:
                    return self._json({"ok": False,
                                       "error": "no valid fields provided; supply intensity, "
                                                "pace, or keys_enabled"}, 400)
                set_results: dict[str, bool] = {}
                for var_name, value in to_set.items():
                    set_results[var_name] = github_api.set_repo_variable(var_name, value)
                failed = {k: v for k, v in set_results.items() if not v}
                if failed:
                    return self._json({"ok": False,
                                       "error": f"Failed to set variable(s): {list(failed)}; "
                                                "check GH_TOKEN has Variables write permission.",
                                       "set": set_results}, 500)
                return self._json({"ok": True, "set": set_results})

            if path == "/api/metabolism/run":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Actions write) "
                                                "to dispatch workflows."}, 503)
                ok_v, err_msg, workflow, inputs = metabolism_panel.validate_run_body(b)
                if not ok_v:
                    return self._json({"ok": False, "error": err_msg}, 400)
                # Manual run: check if all keys are >=90% weekly (manual_floor_pct).
                # Fail-soft — if budget_gate unavailable, allow the run.
                try:
                    from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
                    verdict = gate_verdict("manual")
                    if verdict.get("blocked"):
                        reason = verdict.get("reason") or "All keys ≥90% weekly — wait for a weekly reset."
                        return self._json({"ok": False, "error": reason, "blocked": True}, 409)
                except ImportError:
                    pass  # budget_gate not available; allow the run
                except Exception:  # noqa: BLE001
                    pass  # fail-soft
                result = github_api.dispatch(workflow=workflow, ref="main",
                                             inputs=inputs or None)
                return self._json(result)

            if path == "/api/metabolism/rununtil":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Variables read/write + "
                                                "Actions write) to set auto-run mode."}, 503)
                ok_v, err_msg, mode = metabolism_panel.validate_rununtil_body(b)
                if not ok_v:
                    return self._json({"ok": False, "error": err_msg}, 400)
                # For arm modes, check manual block (budget_gate) fail-soft.
                if mode != "off":
                    try:
                        from engine.metabolism.budget_gate import gate_verdict  # noqa: PLC0415
                        verdict = gate_verdict("manual")
                        if verdict.get("blocked"):
                            reason = verdict.get("reason") or "All keys ≥90% weekly — wait for a weekly reset."
                            # 409 intentional: arm-time manual-floor refusal — sessions likely
                            # cannot finish when all keys are ≥90% weekly.  Operator must wait
                            # for a weekly window to reset before re-arming.
                            return self._json({"ok": False, "error": reason, "blocked": True}, 409)
                    except ImportError:
                        pass
                    except Exception:  # noqa: BLE001
                        pass
                # Set the METAB_RUN_UNTIL repo variable.
                set_ok = github_api.set_repo_variable("METAB_RUN_UNTIL", mode)
                if not set_ok:
                    return self._json({"ok": False,
                                       "error": "Failed to set METAB_RUN_UNTIL — check that "
                                                "GH_TOKEN has Variables write permission."}, 500)
                # For arm modes, dispatch metabolism-cycle.yml to start the first loop.
                # Pass run_until_continue=true and depth=0 so the chain takes the
                # auto budget-gate branch (not the manual-floor branch).
                dispatch_result: dict | None = None
                if mode != "off":
                    dispatch_result = github_api.dispatch(
                        workflow="metabolism-cycle.yml", ref="main",
                        inputs={"run_until_continue": "true", "depth": "0"},
                    )
                return self._json({
                    "ok": True,
                    "mode": mode,
                    "dispatched": dispatch_result is not None and bool(dispatch_result.get("ok")),
                })

            if path == "/api/site_gate/save":
                result = site_gate.save_rules(b, self._real_client_ip())
                if not result.get("ok"):
                    return self._json(result, 400)
                return self._json(result)

            if path == "/api/codex/mode":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Variables read/write) "
                                                "to set Codex mode variables."}, 503)
                ok_v, errors, to_set = codex_panel.validate_mode_body(b)
                if not ok_v:
                    return self._json({"ok": False, "errors": errors}, 400)
                if not to_set:
                    return self._json({"ok": False,
                                       "error": "no valid fields provided; supply mode, "
                                                "interval_hours, or lanes"}, 400)
                set_results: dict[str, bool] = {}
                for var_name, value in to_set.items():
                    set_results[var_name] = github_api.set_repo_variable(var_name, value)
                failed = {k: v for k, v in set_results.items() if not v}
                if failed:
                    return self._json({"ok": False,
                                       "error": f"Failed to set variable(s): {list(failed)}; "
                                                "check GH_TOKEN has Variables write permission.",
                                       "set": set_results}, 500)
                return self._json({"ok": True, "set": set_results})

            if path == "/api/marketing/seo/run":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Actions write) "
                                                "to dispatch the SEO audit workflow."}, 503)
                result = github_api.dispatch(workflow="seo-director.yml", ref="main")
                return self._json(result)

            if path == "/api/marketing/seo/toggle":
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Variables read/write) "
                                                "to arm or pause the SEO director."}, 503)
                enabled = bool(b.get("enabled"))
                new_value = "true" if enabled else "false"
                ok = github_api.set_repo_variable("SEO_DIRECTOR_ENABLED", new_value)
                if not ok:
                    return self._json({"ok": False,
                                       "error": "Failed to update SEO_DIRECTOR_ENABLED — check that "
                                                "GH_TOKEN has Variables write permission."}, 500)
                return self._json({"ok": True, "enabled": enabled, "variable_value": new_value})

            # Publisher ARM/DISARM: write the MARKETING_PUBLISH_ENABLED repo VARIABLE
            # ("1" armed / "0" dark) — the single source of truth the
            # marketing-publish.yml workflow reads. Mirrors the SEO toggle above;
            # marketing.arm_publisher() is the fail-soft plumbing. Works deployed
            # (github_api uses a PAT, no local shell needed).
            if path == "/api/marketing/publish/arm":
                if "enabled" not in b or not isinstance(b.get("enabled"), bool):
                    return self._json({"ok": False, "error": "enabled must be a boolean"}, 400)
                res = marketing.arm_publisher(b.get("enabled"))
                return self._json(res, 200 if res.get("ok") else 400)

            # BREAKING DISPATCH ("Post now"): start a marketing-publish run scoped
            # to one outbox item, which the runner approves and sends immediately
            # instead of waiting for its 2-hourly ladder slot. Works deployed
            # (github_api dispatches with a PAT — no local shell). Every safety
            # gate still runs inside that run; see marketing.post_now().
            if path == "/api/marketing/publish/post_now":
                iid = b.get("item_id") or b.get("id")
                if not isinstance(iid, str) or not iid.strip():
                    return self._json({"ok": False,
                                       "error": "item_id required"}, 400)
                res = marketing.post_now(iid)
                return self._json(res, 200 if res.get("ok") else 400)

            # Buffer token paste-box: set the BUFFER_TOKEN repo SECRET via
            # `gh secret set` (stdin — the token is NEVER in argv, logs, or the
            # response). Local-only (gh login lives on the operator's Mac): refused
            # in deployed mode inside marketing.set_buffer_token() with an honest
            # GitHub-UI fallback. The response carries only {ok, note[, token_present]}.
            if path == "/api/marketing/publish/token":
                tok = b.get("token")
                if not isinstance(tok, str) or not tok.strip():
                    return self._json({"ok": False,
                                       "error": "token required — paste the Buffer personal "
                                                "API token, then Save."}, 400)
                res = marketing.set_buffer_token(tok)
                return self._json(res, 200 if res.get("ok") else 400)

            if path == "/api/codex/run":
                if not b.get("confirm"):
                    return self._json({"ok": False, "error": "confirm required"}, 400)
                if not github_api.token():
                    return self._json({"ok": False,
                                       "error": "No GitHub token configured. Set GH_TOKEN in "
                                                "/etc/macro-admin.env (needs Actions write) "
                                                "to dispatch workflows."}, 503)
                ok_v, err_msg, inputs = codex_panel.validate_run_body(b)
                if not ok_v:
                    return self._json({"ok": False, "error": err_msg}, 400)
                result = github_api.dispatch(workflow="codex-research.yml", ref="main",
                                             inputs=inputs or None)
                return self._json(result)

            return self._json({"error": f"unknown route {path}"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "error": str(e)}, 500)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    # Always bind loopback: in deployed mode Caddy reverse-proxies the public
    # host to 127.0.0.1, so the panel itself never needs a routable socket.
    # Refusing a non-loopback bind keeps the unauthenticated-by-mistake failure
    # mode impossible.
    if not is_loopback_host(host):
        raise SystemExit(
            f"refusing to bind non-loopback host {host!r}: the admin binds "
            "127.0.0.1 and is exposed via a reverse proxy (Caddy) + auth, never "
            "directly. For remote access use admin.mastermind-x.com or an SSH tunnel.")
    settings.startup_check()
    httpd = ThreadingHTTPServer((host, port), Handler)
    mode = "DEPLOYED (auth required)" if settings.deployed() else (
        "local + auth" if settings.auth_enabled() else "local (open)")
    print(f"  Macro Admin → http://{host}:{port}   [{mode}]")
    print("  Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()
