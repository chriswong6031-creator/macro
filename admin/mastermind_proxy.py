"""Proxy to the Mastermind trading bot's FastAPI app (W-AI Mastermind AI page).

The bot is a SEPARATE process (default http://127.0.0.1:8000; override via the
MASTERMIND_BOT_BASE env var). If the bot enforces bearer auth on these routes
(it does when MASTERMIND_AUTH_TOKEN is set bot-side), set MASTERMIND_BOT_TOKEN
on the admin server: when present, every forwarded request (GET and POST)
carries 'Authorization: Bearer <token>'. The token is read from the env at
request time and is never logged or echoed back in payloads.
The admin forwards a fixed WHITELIST of the bot's
/api/mastermind_ai routes — never an open proxy — so the operator can read the
bot's self-improvement loop state and post settings/directives from one console.

Fail-open contract: any transport failure returns
    ({"error": "bot unreachable", "detail": ...}, 502)
so the admin page renders an honest 'unreachable' card instead of a stack trace.
Upstream HTTP errors that carry JSON (e.g. a 400 validation reply) are passed
through with their original status so the UI can show the bot's own message.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_DEFAULT_BASE = "http://127.0.0.1:8000"

# Whitelisted bot routes (path must match exactly; GETs may carry a query string)
GET_PATHS = frozenset({
    "/api/mastermind_ai",
    "/api/mastermind_ai/loop_log",
    "/api/mastermind_ai/improvements",
    "/api/mastermind_ai/reflection",
})
POST_PATHS = frozenset({
    "/api/mastermind_ai/settings",
    "/api/mastermind_ai/directive",
    "/api/mastermind_ai/act_on_nudges",
    "/api/mastermind_ai/run",
})

_GET_TIMEOUT = 5
_POST_TIMEOUT = 10
_RUN_TIMEOUT = 30   # /run triggers a full bot cycle — give it longer


def base() -> str:
    return (os.environ.get("MASTERMIND_BOT_BASE", "").strip() or _DEFAULT_BASE).rstrip("/")


def _auth_header() -> dict:
    """Bearer for the bot's MASTERMIND_AUTH_TOKEN gate. Empty when unset. Never log the token."""
    token = os.environ.get("MASTERMIND_BOT_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _request(url: str, body: dict | None, timeout: int) -> tuple[dict, int]:
    """One forwarded request. Returns (json_payload, status)."""
    try:
        data = None
        headers = {"Accept": "application/json", **_auth_header()}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace") or "{}"
            try:
                payload = json.loads(raw)
            except Exception:  # noqa: BLE001
                payload = {"error": "bot returned non-JSON", "detail": raw[:500]}
            if not isinstance(payload, dict):
                payload = {"data": payload}
            return payload, resp.status
    except urllib.error.HTTPError as e:
        # Upstream answered with an error status — pass its JSON through when possible.
        try:
            raw = e.read().decode("utf-8", errors="replace")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload, e.code
            detail = raw[:500]
        except Exception:  # noqa: BLE001
            detail = str(e)
        return {"error": "bot unreachable", "detail": f"HTTP {e.code}: {detail}"}, 502
    except Exception as e:  # noqa: BLE001
        return {"error": "bot unreachable", "detail": str(e)}, 502


def forward_get(path: str, query: str = "") -> tuple[dict, int]:
    """Forward a whitelisted GET (query string passed through, e.g. loop_log?n=30)."""
    if path not in GET_PATHS:
        return {"error": f"unknown route {path}"}, 404
    url = base() + path + (f"?{query}" if query else "")
    return _request(url, None, _GET_TIMEOUT)


def forward_post(path: str, body: dict | None) -> tuple[dict, int]:
    """Forward a whitelisted POST with the JSON body as-is."""
    if path not in POST_PATHS:
        return {"ok": False, "error": f"unknown route {path}"}, 404
    timeout = _RUN_TIMEOUT if path.endswith("/run") else _POST_TIMEOUT
    return _request(base() + path, body or {}, timeout)
