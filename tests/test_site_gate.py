"""Tests for app/gate.py — site-access gate module.

Coverage:
  - disabled rules => allow
  - block by IP (exact match)
  - block by IP inside CIDR (v4 and v6)
  - allow_ips precedence over blocked_ips
  - block by country via header
  - country header absent + no geoip => country rules no-op => allow
  - missing rules file => fail-open allow
  - corrupt rules file => fail-open allow
  - malformed IP/CIDR entries are ignored silently
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the repo root is importable
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import app.gate as gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_rules(tmp_path: Path, rules: dict) -> Path:
    p = tmp_path / "site_gate.json"
    p.write_text(json.dumps(rules), encoding="utf-8")
    return p


def _rules(
    enabled: bool = True,
    blocked_ips: list | None = None,
    blocked_countries: list | None = None,
    allow_ips: list | None = None,
) -> dict:
    return {
        "version": 1,
        "enabled": enabled,
        "blocked_ips": blocked_ips or [],
        "blocked_countries": blocked_countries or [],
        "allow_ips": allow_ips or [],
        "updated_at": "2026-01-01T00:00:00Z",
        "updated_by": "test",
    }


def _decide(monkeypatch, tmp_path: Path, rules_dict: dict, ip: str, headers: dict | None = None):
    """Write rules, invalidate cache, then call gate.decide()."""
    rule_path = _write_rules(tmp_path, rules_dict)
    monkeypatch.setenv("SITE_GATE_STATE", str(rule_path))
    gate._invalidate_cache()
    return gate.decide(ip, headers or {})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_disabled_rules_allow(monkeypatch, tmp_path):
    """Master switch off => allow all, even if IP is in blocked list."""
    rules = _rules(enabled=False, blocked_ips=["1.2.3.4"])
    assert _decide(monkeypatch, tmp_path, rules, "1.2.3.4") == "allow"


def test_block_exact_ip(monkeypatch, tmp_path):
    rules = _rules(blocked_ips=["203.0.113.5"])
    assert _decide(monkeypatch, tmp_path, rules, "203.0.113.5") == "block-ip"


def test_allow_non_blocked_ip(monkeypatch, tmp_path):
    rules = _rules(blocked_ips=["203.0.113.5"])
    assert _decide(monkeypatch, tmp_path, rules, "203.0.113.6") == "allow"


def test_block_ip_in_cidr_v4(monkeypatch, tmp_path):
    """An IP inside a blocked CIDR should be blocked."""
    rules = _rules(blocked_ips=["198.51.100.0/24"])
    assert _decide(monkeypatch, tmp_path, rules, "198.51.100.99") == "block-ip"


def test_ip_outside_cidr_v4_allowed(monkeypatch, tmp_path):
    rules = _rules(blocked_ips=["198.51.100.0/24"])
    assert _decide(monkeypatch, tmp_path, rules, "198.51.101.1") == "allow"


def test_block_ip_in_cidr_v6(monkeypatch, tmp_path):
    """IPv6 CIDR blocking works."""
    rules = _rules(blocked_ips=["2001:db8::/32"])
    assert _decide(monkeypatch, tmp_path, rules, "2001:db8::1") == "block-ip"


def test_ip_outside_cidr_v6_allowed(monkeypatch, tmp_path):
    rules = _rules(blocked_ips=["2001:db8::/32"])
    assert _decide(monkeypatch, tmp_path, rules, "2001:db9::1") == "allow"


def test_allow_ips_precedence_over_blocked(monkeypatch, tmp_path):
    """An IP in allow_ips must be admitted even if it also appears in blocked_ips."""
    rules = _rules(
        blocked_ips=["203.0.113.9"],
        allow_ips=["203.0.113.9"],
    )
    assert _decide(monkeypatch, tmp_path, rules, "203.0.113.9") == "allow"


def test_allow_ips_cidr_precedence(monkeypatch, tmp_path):
    """allow_ips can be a CIDR and must take precedence over blocked_ips."""
    rules = _rules(
        blocked_ips=["10.0.0.0/8"],
        allow_ips=["10.0.1.0/24"],
    )
    # Inside allow CIDR: allow
    assert _decide(monkeypatch, tmp_path, rules, "10.0.1.5") == "allow"
    gate._invalidate_cache()
    # Outside allow CIDR but inside block CIDR: block
    assert _decide(monkeypatch, tmp_path, rules, "10.0.2.5") == "block-ip"


def test_block_by_country_header(monkeypatch, tmp_path):
    """Visitor whose country header matches a blocked country is blocked."""
    rules = _rules(blocked_countries=["RU", "KP"])
    headers = {"EO-Client-IPCountry": "RU"}
    monkeypatch.setenv("SITE_GATE_COUNTRY_HEADER", "EO-Client-IPCountry")
    assert _decide(monkeypatch, tmp_path, rules, "1.2.3.4", headers) == "block-country"


def test_allowed_country_passes(monkeypatch, tmp_path):
    rules = _rules(blocked_countries=["RU"])
    headers = {"EO-Client-IPCountry": "US"}
    monkeypatch.setenv("SITE_GATE_COUNTRY_HEADER", "EO-Client-IPCountry")
    assert _decide(monkeypatch, tmp_path, rules, "1.2.3.4", headers) == "allow"


def test_country_header_absent_no_geoip_allow(monkeypatch, tmp_path):
    """When country cannot be resolved and there's no geoip, country rules are a no-op => allow."""
    rules = _rules(blocked_countries=["CN"])
    # No country header, no geoip db
    monkeypatch.setenv("SITE_GATE_COUNTRY_HEADER", "EO-Client-IPCountry")
    monkeypatch.setenv("GEOIP_DB", "/nonexistent/GeoLite2-Country.mmdb")
    gate._invalidate_cache()
    assert _decide(monkeypatch, tmp_path, rules, "5.5.5.5", {}) == "allow"


def test_country_header_case_insensitive_value(monkeypatch, tmp_path):
    """Country value is uppercased before comparison."""
    rules = _rules(blocked_countries=["RU"])
    monkeypatch.setenv("SITE_GATE_COUNTRY_HEADER", "EO-Client-IPCountry")
    # Header provides lowercase country code
    assert _decide(monkeypatch, tmp_path, rules, "1.2.3.4", {"EO-Client-IPCountry": "ru"}) == "block-country"


def test_block_by_country_header_lowercase_key(monkeypatch, tmp_path):
    """Production shape: Starlette normalises ASGI header NAMES to lowercase, so
    /api/gate/check passes dict(request.headers) with lowercase keys. The gate must
    resolve the country header regardless of key casing (guards the .lower() branch,
    which the mixed-case tests never exercise)."""
    rules = _rules(blocked_countries=["RU"])
    monkeypatch.setenv("SITE_GATE_COUNTRY_HEADER", "EO-Client-IPCountry")
    assert _decide(monkeypatch, tmp_path, rules, "1.2.3.4", {"eo-client-ipcountry": "RU"}) == "block-country"


def test_missing_rules_file_fail_open(monkeypatch, tmp_path):
    """A missing rules file must be treated as disabled => allow all."""
    monkeypatch.setenv("SITE_GATE_STATE", str(tmp_path / "nonexistent.json"))
    gate._invalidate_cache()
    assert gate.decide("1.2.3.4", {}) == "allow"


def test_corrupt_rules_file_fail_open(monkeypatch, tmp_path):
    """A corrupt/unparseable rules file => fail-open allow."""
    p = tmp_path / "site_gate.json"
    p.write_text("THIS IS NOT JSON", encoding="utf-8")
    monkeypatch.setenv("SITE_GATE_STATE", str(p))
    gate._invalidate_cache()
    assert gate.decide("1.2.3.4", {}) == "allow"


def test_invalid_json_type_fail_open(monkeypatch, tmp_path):
    """Rules file that parses to non-dict (e.g. a JSON array) => fail-open allow."""
    p = tmp_path / "site_gate.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setenv("SITE_GATE_STATE", str(p))
    gate._invalidate_cache()
    assert gate.decide("1.2.3.4", {}) == "allow"


def test_malformed_ip_entry_ignored(monkeypatch, tmp_path):
    """Malformed entries in blocked_ips are silently ignored; valid entries still work."""
    rules = _rules(blocked_ips=["NOT_AN_IP", "256.256.256.256", "203.0.113.5", "bad/cidr/extra"])
    gate._invalidate_cache()
    # The valid IP 203.0.113.5 must still be blocked
    assert _decide(monkeypatch, tmp_path, rules, "203.0.113.5") == "block-ip"
    gate._invalidate_cache()
    # A non-matching IP is allowed
    assert _decide(monkeypatch, tmp_path, rules, "1.1.1.1") == "allow"


def test_empty_rules_allow_all(monkeypatch, tmp_path):
    """An enabled gate with no lists should allow everyone."""
    rules = _rules(enabled=True)
    assert _decide(monkeypatch, tmp_path, rules, "8.8.8.8") == "allow"


def test_unknown_ip_string_fail_open(monkeypatch, tmp_path):
    """The 'unknown' IP sentinel (when no header provides an IP) => no block match => allow."""
    rules = _rules(blocked_ips=["0.0.0.0/0"])
    # "unknown" cannot be parsed as an IP; _ip_in_list returns False => falls through to country check => allow
    assert _decide(monkeypatch, tmp_path, rules, "unknown") == "allow"


# ---------------------------------------------------------------------------
# status() tests
# ---------------------------------------------------------------------------

def test_status_reflects_disabled(monkeypatch, tmp_path):
    rules = _rules(enabled=False, blocked_ips=["1.0.0.0/8"], blocked_countries=["CN"])
    rule_path = _write_rules(tmp_path, rules)
    monkeypatch.setenv("SITE_GATE_STATE", str(rule_path))
    gate._invalidate_cache()
    s = gate.status()
    assert s["ok"] is True
    assert s["enabled"] is False
    assert s["counts"]["ips"] == 1
    assert s["counts"]["countries"] == 1


def test_status_counts(monkeypatch, tmp_path):
    rules = _rules(
        enabled=True,
        blocked_ips=["1.2.3.4", "10.0.0.0/8"],
        blocked_countries=["RU", "KP"],
        allow_ips=["5.6.7.8"],
    )
    rule_path = _write_rules(tmp_path, rules)
    monkeypatch.setenv("SITE_GATE_STATE", str(rule_path))
    gate._invalidate_cache()
    s = gate.status()
    assert s["counts"] == {"ips": 2, "countries": 2, "allow": 1}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
