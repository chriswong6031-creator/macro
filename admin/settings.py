"""Deployment configuration for the admin console.

The admin started life as a localhost-only, unauthenticated dev tool. To run it
publicly at admin.mastermind-x.com it gains a *deployed mode*: real password
auth, a configured public hostname, and trust of the local reverse proxy
(Caddy) for the client's scheme. Everything is driven by environment variables
(loaded from <repo>/.env locally — see paths._load_dotenv — or the systemd
EnvironmentFile on the VPS, admin/deploy/admin.service).

Local mode (default): binds 127.0.0.1; auth is optional (dev convenience — if
ADMIN_PASSWORD is unset, the panel is open, exactly like before).
Deployed mode (ADMIN_DEPLOYED=1): password REQUIRED (refuses to start without
one), trusts X-Forwarded-Proto from the loopback proxy, and answers to the
configured public Host (DNS-rebinding guard otherwise rejects it).
"""
from __future__ import annotations

import os
import secrets

from . import paths  # noqa: F401  — importing loads <repo>/.env into os.environ


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def deployed() -> bool:
    return _env("ADMIN_DEPLOYED").lower() in ("1", "true", "yes", "on")


def admin_password() -> str | None:
    return _env("ADMIN_PASSWORD") or None


def auth_enabled() -> bool:
    """Auth is enforced whenever a password is set (always true in deployed mode)."""
    return bool(admin_password())


def allowed_hosts() -> set[str]:
    """Public hostnames the panel will answer to (besides loopback). The
    DNS-rebinding guard rejects any other Host header."""
    raw = _env("ADMIN_ALLOWED_HOSTS") or "admin.mastermind-x.com"
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


# Process-stable session-signing secret. Prefer an explicit env value so signed
# session cookies survive a service restart; otherwise mint an ephemeral one
# (sessions reset on restart — fine for a single operator, never silently weak).
_EPHEMERAL_SECRET = secrets.token_hex(32)


def session_secret() -> bytes:
    return (_env("ADMIN_SESSION_SECRET") or _EPHEMERAL_SECRET).encode()


def session_ttl_hours() -> int:
    try:
        return max(1, min(720, int(_env("ADMIN_SESSION_TTL_HOURS") or "168")))
    except ValueError:
        return 168


def public_url() -> str:
    return _env("ADMIN_PUBLIC_URL") or "https://admin.mastermind-x.com"


# ---- integration credentials (all optional; panels degrade gracefully) ------
def supabase_pat() -> str | None:
    """Supabase Personal Access Token (sbp_…) for the Management API."""
    return _env("SUPABASE_ACCESS_TOKEN") or _env("SUPABASE_PAT") or None


def supabase_project_ref() -> str:
    return _env("SUPABASE_PROJECT_REF") or "fsldfzlxyavsuwqbceod"


def umami_api_key() -> str | None:
    return _env("UMAMI_API_KEY") or None


def umami_website_id() -> str:
    return _env("UMAMI_WEBSITE_ID") or "d7734c31-99fa-4949-bcde-bec41fbfb2cf"


def umami_api_base() -> str:
    return (_env("UMAMI_API_BASE") or "https://api.umami.is/v1").rstrip("/")


def umami_dashboard_url() -> str:
    return _env("UMAMI_DASHBOARD_URL") or "https://cloud.umami.is"


def startup_check() -> None:
    """Fail closed: refuse to start a *deployed* (publicly reachable) panel with no
    password — that would expose config edits + Actions dispatch to the internet."""
    if deployed() and not admin_password():
        raise SystemExit(
            "ADMIN_DEPLOYED=1 but ADMIN_PASSWORD is empty — refusing to start a "
            "public admin with no auth. Set ADMIN_PASSWORD in the service env "
            "(admin/deploy/admin.service → /etc/macro-admin.env).")
