"""Localhost-only HTTP server for the admin dashboard.

Stdlib http.server (no web framework / no new mandatory deps). Serves a single-page UI
from admin/static and a small JSON API under /api/*. Bind to 127.0.0.1 only — this is a
single-user local tool that edits the repo's config and drives the GitHub API.
"""
from __future__ import annotations

import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import (ai_cost, brief, config_store, content, flags, ga4, github_api,
               gitops, health)
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


def _repo_summary() -> dict:
    gh = github_api.available()
    return {
        "repo": f"{gh.get('owner')}/{gh.get('repo')}" if gh.get("owner") else None,
        "github_ok": gh["ok"],
        "has_token": gh["has_token"],
        "site_url": config_store.get_value("notify.site_url"),
        "ga_configured": ga4.status()["configured"],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MacroAdmin/1.0"

    # ---- low-level helpers --------------------------------------------------
    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

    def _guard(self, write: bool) -> str | None:
        """Reject requests that aren't genuinely same-origin localhost traffic.
        Defends this localhost tool against DNS-rebinding (Host check) and CSRF from
        a malicious page the user has open (Content-Type + Origin check on writes —
        a cross-site page cannot set Content-Type: application/json without a CORS
        preflight, which this server never grants). Returns an error string or None."""
        if not is_loopback_host(_host_only(self.headers.get("Host", ""))):
            return "non-loopback Host header rejected"
        if write:
            ct = (self.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
            if ct != "application/json":
                return "Content-Type must be application/json"
            origin = self.headers.get("Origin")
            if origin:
                port = self.server.server_address[1]
                allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
                if origin not in allowed:
                    return "cross-origin request rejected"
        return None

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        try:
            err = self._guard(write=False)
            if err:
                return self._json({"error": err}, 403)
            if path in ("/", "/index.html"):
                return self._file("index.html")
            if path in ("/app.js", "/styles.css"):
                return self._file(path.lstrip("/"))

            if path == "/api/summary":
                return self._json({
                    "meta": _repo_summary(),
                    "flags": flags.snapshot(),
                    "brief": brief.panel(),
                    "health": health.summary(),
                    "cost": ai_cost.estimate(),
                    "git": gitops.status(),
                })
            if path == "/api/flags":
                return self._json(flags.snapshot())
            if path == "/api/brief":
                return self._json(brief.panel())
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
            if path == "/api/git":
                return self._json(gitops.status())
            if path == "/api/deploy":
                wf = (q.get("workflow") or [None])[0]
                return self._json(github_api.list_runs(workflow=wf))
            if path == "/api/traffic":
                return self._json(ga4.status())
            if path == "/api/traffic/realtime":
                return self._json(ga4.realtime())
            if path == "/api/traffic/report":
                days = int((q.get("days") or ["7"])[0])
                return self._json(ga4.report(days=days))

            return self._json({"error": f"unknown route {path}"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            err = self._guard(write=True)
            if err:
                return self._json({"ok": False, "error": err}, 403)
            b = self._body()
            if path == "/api/flags/toggle":
                flag_path = b.get("path")
                value = bool(b.get("value"))
                if not flag_path or flag_path not in {f["path"] for f in flags.FLAGS}:
                    return self._json({"ok": False, "error": "unknown or unmanaged flag path"}, 400)
                return self._json(config_store.set_bool(flag_path, value))

            if path == "/api/brief/interval":
                target = b.get("target")
                if target not in ("master_brain", "ai_desk"):
                    return self._json({"ok": False, "error": "target must be master_brain or ai_desk"}, 400)
                return self._json(config_store.set_int(f"{target}.interval_days", b.get("days"), 1, 7))

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
                return self._json(gitops.commit(
                    message=b.get("message", "admin: config update"),
                    push=bool(b.get("push")),
                    confirm=bool(b.get("confirm")),
                ))

            return self._json({"error": f"unknown route {path}"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "error": str(e)}, 500)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    # This tool is intentionally localhost-only: every route is unauthenticated and
    # the write routes edit config.yml / drive git + GitHub Actions. Refuse to bind a
    # routable address (use an SSH tunnel for remote access instead).
    if not is_loopback_host(host):
        raise SystemExit(
            f"refusing to bind non-loopback host {host!r}: the admin API is "
            "unauthenticated and localhost-only. For remote access, run it on "
            "127.0.0.1 and use an SSH tunnel (ssh -L 8787:127.0.0.1:8787 <host>).")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"  Macro Admin → http://{host}:{port}")
    print("  (localhost-only; Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()
