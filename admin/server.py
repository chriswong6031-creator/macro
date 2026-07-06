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

from . import (actions, ai_cost, auth, brief, config_store, content, experiments,
               flags, ga4, github_api, github_config, gitops, health, neural_web,
               services, settings, system, umami, uptime_board, users, vector_override)
from .paths import STATIC

_CTYPES = {".html": "text/html; charset=utf-8",
           ".css": "text/css; charset=utf-8",
           ".js": "application/javascript; charset=utf-8"}

_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


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
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0:
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

    def _secure_cookie(self) -> bool:
        # Behind Caddy the real scheme is X-Forwarded-Proto; deployed = always TLS.
        if settings.deployed():
            return True
        xf = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        return xf == "https"

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
            if path == "/api/neural_web":
                return self._json(neural_web.panel())
            if path == "/api/neural_web/lobes":
                return self._json(neural_web.lobes_panel())
            if path == "/api/neural_web/lobe":
                return self._json(neural_web.lobe_detail((q.get("id") or [""])[0]))
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
            if path == "/api/git":
                return self._json(gitops.status())
            if path == "/api/deploy":
                wf = (q.get("workflow") or [None])[0]
                return self._json(github_api.list_runs(workflow=wf))
            # analytics — Umami primary, GA4 kept as a secondary source
            if path == "/api/analytics":
                return self._json(umami.status())
            if path == "/api/analytics/report":
                days = int((q.get("days") or ["7"])[0])
                return self._json(umami.report(days=days))
            if path == "/api/analytics/active":
                return self._json(umami.active())
            if path == "/api/traffic":
                return self._json(ga4.status())
            if path == "/api/traffic/realtime":
                return self._json(ga4.realtime())
            if path == "/api/traffic/report":
                days = int((q.get("days") or ["7"])[0])
                return self._json(ga4.report(days=days))
            # users (Supabase)
            if path == "/api/users":
                return self._json(users.summary())
            if path == "/api/users/recent":
                limit = int((q.get("limit") or ["30"])[0])
                return self._json(users.recent(limit=limit))
            # system / services
            if path == "/api/system":
                return self._json(system.snapshot())
            if path == "/api/services":
                return self._json(services.status())

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

            if path == "/api/brief/interval":
                target = b.get("target")
                if target not in ("master_brain", "ai_desk"):
                    return self._json({"ok": False, "error": "target must be master_brain or ai_desk"}, 400)
                dotted = f"{target}.interval_days"
                if settings.deployed():
                    return self._json(github_config.set_int(dotted, b.get("days"), 1, 7))
                return self._json(config_store.set_int(dotted, b.get("days"), 1, 7))

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
