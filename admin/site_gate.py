"""admin/site_gate.py — backend for the Site Access gate admin panel.

Reads and writes the runtime blocklist JSON that macro-api/gate.py enforces.
The store lives at SITE_GATE_STATE (default /var/lib/macro-api/site_gate.json).

WHY THIS WRITES LOCAL DISK EVEN IN DEPLOYED MODE
-------------------------------------------------
All other config mutations route through the GitHub Contents API (so the VPS
clone — which is ephemeral/read-only — picks them up on the next deploy).
The site-access blocklist is *instant operational state*: an operator who needs
to block an IP or a country right now cannot wait 10-60 minutes for a CI run.
The gate process (macro-api) and the admin server run on the *same* VPS, so a
direct write to /var/lib/macro-api/ is immediately visible to macro-api without
any restart or deploy.  This file must NEVER be committed to git — it holds
dynamic operational data, not repo content.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request as _urllib_request

_WRITE_LOCK = threading.Lock()

_DEFAULT_STATE_PATH = "/var/lib/macro-api/site_gate.json"
_GATE_STATUS_URL = "http://127.0.0.1:8000/api/gate/status"
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")

_EMPTY_RULES: dict[str, Any] = {
    "version": 1,
    "enabled": False,
    "blocked_ips": [],
    "blocked_countries": [],
    "allow_ips": [],
    "updated_at": None,
    "updated_by": None,
}


def _state_path() -> Path:
    return Path(os.environ.get("SITE_GATE_STATE", _DEFAULT_STATE_PATH))


def read_rules() -> dict:
    """Read the current gate rules from disk.  On any error returns the safe
    disabled default (fail-open contract: a bad file = allow everyone)."""
    try:
        p = _state_path()
        if not p.exists():
            return dict(_EMPTY_RULES)
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            return dict(_EMPTY_RULES)
        rules = dict(_EMPTY_RULES)
        rules.update({
            "enabled": bool(data.get("enabled", False)),
            "blocked_ips": list(data.get("blocked_ips") or []),
            "blocked_countries": list(data.get("blocked_countries") or []),
            "allow_ips": list(data.get("allow_ips") or []),
            "updated_at": data.get("updated_at"),
            "updated_by": data.get("updated_by"),
        })
        return rules
    except Exception:  # noqa: BLE001
        return dict(_EMPTY_RULES)


def _validate_ip_entries(entries: list) -> tuple[list[str], list[str]]:
    """Validate a list of IP/CIDR strings.  Returns (good, bad)."""
    good, bad = [], []
    for entry in entries:
        if not isinstance(entry, str):
            bad.append(repr(entry))
            continue
        entry = entry.strip()
        if not entry:
            continue
        try:
            # Try as a network (CIDR) first, then as a plain address.
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                ipaddress.ip_address(entry)
            good.append(entry)
        except ValueError:
            bad.append(entry)
    return good, bad


def _validate_country_entries(entries: list) -> tuple[list[str], list[str]]:
    """Validate + uppercase ISO-3166 alpha-2 country codes.  Returns (good, bad)."""
    good, bad = [], []
    for entry in entries:
        if not isinstance(entry, str):
            bad.append(repr(entry))
            continue
        entry = entry.strip()
        if not entry:
            continue
        if _COUNTRY_RE.match(entry):
            good.append(entry.upper())
        else:
            bad.append(entry)
    return good, bad


def _ip_in_list(ip_str: str, entries: list) -> bool:
    """True if ip_str (a single address) matches any entry (addr or CIDR). Mirrors
    app/gate.py:_ip_in_list so the admin's coverage check agrees with the gate's."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except (ValueError, TypeError):
        return False
    for entry in entries:
        try:
            net = ipaddress.ip_network(str(entry), strict=False)
        except (ValueError, TypeError):
            continue
        try:
            if addr in net:
                return True
        except TypeError:
            continue  # v4/v6 family mismatch
    return False


def _write_rules(rules: dict) -> None:
    """Atomically write rules to disk (tempfile + os.replace, same pattern as
    admin/config_store.py _write_lines)."""
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(rules, indent=2, default=str).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".site_gate.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, str(p))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def save_rules(payload: dict, caller_ip: str) -> dict:
    """Validate + persist updated gate rules.

    Parameters
    ----------
    payload:    dict with keys: enabled (bool), blocked_ips (list), blocked_countries (list).
    caller_ip:  the admin operator's real IP — always added to allow_ips so the operator
                can never lock themselves out of the admin panel.

    Returns
    -------
    {ok, rules, warnings} envelope or {ok:False, error, bad_ips, bad_countries}.
    """
    # --- validate enabled ---
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return {"ok": False, "error": "enabled must be a boolean"}

    # --- validate blocked_ips ---
    raw_ips = payload.get("blocked_ips")
    if not isinstance(raw_ips, list):
        return {"ok": False, "error": "blocked_ips must be a list"}
    good_ips, bad_ips = _validate_ip_entries(raw_ips)
    if bad_ips:
        return {"ok": False, "error": f"invalid IP/CIDR entries: {bad_ips}",
                "bad_ips": bad_ips}

    # --- validate blocked_countries ---
    raw_countries = payload.get("blocked_countries")
    if not isinstance(raw_countries, list):
        return {"ok": False, "error": "blocked_countries must be a list"}
    good_countries, bad_countries = _validate_country_entries(raw_countries)
    if bad_countries:
        return {"ok": False, "error": f"invalid country codes: {bad_countries}",
                "bad_countries": bad_countries}

    # --- allow_ips (prunable) ---
    # Sourced from the payload so the operator can REMOVE stale entries (old
    # home/VPN/mobile IPs that would otherwise bypass every block forever). If the
    # client omits the field, keep the stored list (backward-compatible).
    warnings: list[str] = []
    if "allow_ips" in payload:
        raw_allow = payload.get("allow_ips")
        if not isinstance(raw_allow, list):
            return {"ok": False, "error": "allow_ips must be a list"}
        current_allow, bad_allow = _validate_ip_entries(raw_allow)
        if bad_allow:
            return {"ok": False, "error": f"invalid allow_ips entries: {bad_allow}",
                    "bad_allow": bad_allow}
    else:
        current_allow = list(read_rules().get("allow_ips") or [])

    # --- self-lockout guard ---
    # Always ensure the caller's current IP is in allow_ips so the operator can
    # never permanently lock themselves out via a misconfigured blocklist. Validate
    # it as a real address first (never store a junk token), and skip when it's
    # already covered by an existing allow entry (no duplicate rows).
    if caller_ip and caller_ip not in ("-", "unknown", ""):
        try:
            ipaddress.ip_address(caller_ip)
        except ValueError:
            pass  # not a real IP (misconfigured proxy) — don't pollute the store
        else:
            if not _ip_in_list(caller_ip, current_allow):
                current_allow.append(caller_ip)

    # Warn if the caller's IP is also in the blocked set (it will still be
    # allowed because allow_ips takes precedence, but it's suspicious).
    if caller_ip:
        try:
            caller_addr = ipaddress.ip_address(caller_ip)
            for entry in good_ips:
                try:
                    net = ipaddress.ip_network(entry, strict=False)
                    if caller_addr in net:
                        warnings.append(
                            f"Your IP {caller_ip} is in the blocked_ips list "
                            f"({entry}). It has been kept in allow_ips so you "
                            "remain accessible, but review your blocklist."
                        )
                        break
                except ValueError:
                    if entry == caller_ip:
                        warnings.append(
                            f"Your IP {caller_ip} is in the blocked_ips list. "
                            "It has been kept in allow_ips so you remain "
                            "accessible, but review your blocklist."
                        )
                        break
        except ValueError:
            pass  # caller_ip not parseable; skip the check silently

    # --- atomic write ---
    with _WRITE_LOCK:
        rules: dict[str, Any] = {
            "version": 1,
            "enabled": enabled,
            "blocked_ips": good_ips,
            "blocked_countries": good_countries,
            "allow_ips": current_allow,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_by": "admin",
        }
        _write_rules(rules)

    return {"ok": True, "rules": rules, "warnings": warnings}


def gate_status() -> dict:
    """Best-effort HTTP GET to macro-api /api/gate/status.

    Returns the parsed JSON on success, or {ok:False} on any failure.
    Never raises.
    """
    try:
        req = _urllib_request.Request(
            _GATE_STATUS_URL,
            headers={"Accept": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=3) as resp:
            body = resp.read()
        return json.loads(body)
    except Exception:  # noqa: BLE001 — best-effort probe; macro-api may be down
        return {"ok": False}
