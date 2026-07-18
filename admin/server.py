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

import ipaddress
import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import (actions, ai_cost, alerts as _alerts_mod, analytics_first_party, auth, brief, causal_lab,
               codex_panel,
               config_store,
               content, context_lobe, experiments,
               flags, ga4, github_api, github_config, gitops, health, long_hold,
               live_runs,
               marketing,
               mastermind_proxy,
               metabolism_history,
               metabolism_panel,
               neural_web,
               orchestrator_chat,
               prophet,
               services, settings, site_gate, system, umami, uptime_board, users, vector_override)
from .paths import STATIC

_CTYPES = {".html": "text/html; charset=utf-8",
           ".css": "text/css; charset=utf-8",
           ".js": "application/javascript; charset=utf-8"}


def _int_param(q: dict, key: str, default: int, lo: int, hi: int) -> int:
    """Parse an integer query parameter, returning *default* on error and clamping to [lo, hi]."""
    try:
        v = int((q.get(key) or [default])[0])
    except (ValueError, TypeError):
        return default
    return max(lo, min(hi, v))


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


def _repo_summary() -> dict:
    gh = github_api.available()
    return {
        "repo": f"{gh.get('owner')}/{gh.get('repo')}" if gh.get("owner") else None,
        "github_ok": gh["ok"],
        "has_token": gh["has_token"],
        "site_url": config_store.get_value("notify.site_url"),
        "ga_configured": ga4.status()["configured"],
        "deployed": settings.deployed(),
        "auth_enabled": settings.auth_enabled(),
        "public_url": settings.public_url(),
        "integrations": _integrations(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MacroAdmin/2.0"

    # ---- low-level helpers --------------------------------------------------
    def _json(self, obj, code: int = 200, cookies: list[str] | None = None) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        for c in (cookies or []):
            self.send_header("Set-Cookie", c)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name: str) -> None:
        p = (STATIC / name).resolve()
        if not str(p).startswith(str(STATIC.resolve())) or not p.is_file():
            self._json({"error": "not found"}, 404)
            return
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _CTYPES.get(p.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
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
        """Real client IP for per-client login throttling. Behind Caddy the TCP peer
        is always loopback, so trust X-Forwarded-For (first hop) in deployed mode."""
        if settings.deployed():
            xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if xff:
                return xff
        try:
            return self.client_address[0]
        except Exception:  # noqa: BLE001
            return "-"

    def _real_client_ip(self) -> str:
        """The visitor IP as the SITE gate would see it — mirrors app/main.py
        _mm_client_ip: prefer the CDN real-client headers, then fall back to
        _client_id(). Used for the site-access gate's self-lockout allow-list so the
        IP we auto-allow matches the IP the gate actually evaluates on the site."""
        for k in ("EO-Connecting-IP", "CF-Connecting-IP", "True-Client-IP"):
            v = (self.headers.get(k) or "").strip()
            if v:
                return v.split(",")[0].strip()[:64]
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

            if path == "/api/summary":
                return self._json({
                    "meta": _repo_summary(),
                    "flags": flags.snapshot(),
                    "brief": brief.panel(),
                    "health": health.summary(),
                    "cost": ai_cost.estimate(),
                    "git": gitops.status(),
                    "system": system.snapshot(),
                    "services": services.status(),
                    "experiments": experiments.alert_summary(),
                })
            if path == "/api/flags":
                return self._json(flags.snapshot())
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
            # Marketing lobe admin pages
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
            if path == "/api/marketing/lobes":
                return self._json(marketing.lobes())
            if path == "/api/marketing/content":
                return self._json(marketing.content())
            if path == "/api/marketing/department":
                dept_id = (q.get("id") or [None])[0]
                return self._json(marketing.department(dept_id=dept_id))
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
            # Params are string-in; the reader int-clamps days/limit and allowlist-validates ids.
            if path == "/api/analytics/fp/overview":
                return self._json(analytics_first_party.overview(days=(q.get("days") or ["7"])[0]))
            if path == "/api/analytics/fp/pages":
                return self._json(analytics_first_party.pages(days=(q.get("days") or ["7"])[0], limit=(q.get("limit") or ["25"])[0]))
            if path == "/api/analytics/fp/geo":
                return self._json(analytics_first_party.geo(days=(q.get("days") or ["30"])[0], limit=(q.get("limit") or ["200"])[0]))
            if path == "/api/analytics/fp/sessions":
                return self._json(analytics_first_party.sessions(limit=(q.get("limit") or ["40"])[0]))
            if path == "/api/analytics/fp/visitors":
                return self._json(analytics_first_party.visitors(limit=(q.get("limit") or ["100"])[0]))
            if path == "/api/analytics/fp/session":
                return self._json(analytics_first_party.session((q.get("id") or [""])[0]))
            if path == "/api/analytics/fp/flow":
                return self._json(analytics_first_party.flow(days=(q.get("days") or ["7"])[0], limit=(q.get("limit") or ["40"])[0]))
            if path == "/api/analytics/fp/terminal":
                return self._json(analytics_first_party.terminal(days=(q.get("days") or ["7"])[0], limit=(q.get("limit") or ["25"])[0]))
            if path == "/api/analytics/fp/visitor":
                return self._json(analytics_first_party.visitor((q.get("id") or [""])[0]))
            if path == "/api/analytics/fp/realtime":
                return self._json(analytics_first_party.realtime())
            # users (Supabase)
            if path == "/api/users":
                return self._json(users.summary())
            if path == "/api/users/recent":
                limit = _int_param(q, "limit", 30, 1, 1000)
                return self._json(users.recent(limit=limit))
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

            if path == "/api/flags/toggle":
                flag_path = b.get("path")
                value = bool(b.get("value"))
                if not flag_path or flag_path not in {f["path"] for f in flags.FLAGS}:
                    return self._json({"ok": False, "error": "unknown or unmanaged flag path"}, 400)
                if settings.deployed():
                    return self._json(github_config.set_bool(flag_path, value))
                return self._json(config_store.set_bool(flag_path, value))

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

            if path == "/api/orchestrator/chat":
                return self._json(orchestrator_chat.chat(b.get("message", ""),
                                                         history=b.get("history")))

            if path == "/api/orchestrator/wake":
                return self._json(orchestrator_chat.wake())

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
