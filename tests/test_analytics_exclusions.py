"""Tests for admin/analytics_first_party.py — operator self-exclusion, table filtering,
and row caps (the pure, no-network parts).

The SQL is executed against the Supabase Management API in production; here we monkeypatch
`_query` to CAPTURE the generated SQL and assert on it, and monkeypatch `status` so the
`_guard` wrapper lets `run()` execute without a real PAT. No network is touched.
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import admin.analytics_first_party as a


# ---- pure string helpers ---------------------------------------------------
def test_sql_str_doubles_quotes():
    assert a._sql_str("o'brien@x.com") == "'o''brien@x.com'"
    assert a._sql_str("plain") == "'plain'"


def test_sanitize_q_strips_dangerous_chars_and_caps_length():
    # quotes, %, _, =, ;, parens all removed; email/uuid/ip chars kept
    assert a._sanitize_q("a' or 1=1;--") == "a or 11--"
    assert a._sanitize_q("bob@Example.com") == "bob@Example.com"
    assert a._sanitize_q("1.2.3.4") == "1.2.3.4"
    assert a._sanitize_q("2001:db8::1") == "2001:db8::1"
    assert a._sanitize_q("x" * 200) == "x" * 64          # length cap
    assert a._sanitize_q(None) == ""
    assert "'" not in a._sanitize_q("'''''")


def test_routable_excludes_loopback():
    p = a._routable("e.ip")
    assert "e.ip is not null" in p
    for bad in ("'::1'", "'127.0.0.1'", "'unknown'", "'localhost'"):
        assert bad in p


def test_not_excluded_keeps_null_visitor():
    # a bare `not in` would drop null rows via 3-valued logic — must be guarded
    assert a._not_excluded("e") == "(e.visitor_id is null or e.visitor_id not in (select visitor_id from excluded))"
    assert a._not_excluded("") == "(visitor_id is null or visitor_id not in (select visitor_id from excluded))"


# ---- config-driven CTE -----------------------------------------------------
def test_load_exclusions_reads_and_normalises(tmp_path, monkeypatch):
    p = tmp_path / "excl.json"
    p.write_text(json.dumps({
        "emails": ["Me@X.com", " demo@mastermind.test ", ""],
        "locations": [{"city": "Richmond", "country_code": "CA"}, "junk"],
    }))
    monkeypatch.setattr(a, "_EXCL_PATH", p)
    cfg = a._load_exclusions()
    assert cfg["emails"] == ["me@x.com", "demo@mastermind.test"]      # lowered, trimmed, blanks dropped
    assert cfg["locations"] == [{"city": "Richmond", "country_code": "CA"}]  # non-dict dropped


def test_load_exclusions_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "_EXCL_PATH", tmp_path / "nope.json")
    # fail-safe: nothing hidden/relabelled
    assert a._load_exclusions() == {"emails": [], "locations": [], "ips": [], "bots": {}, "geo_overrides": []}


def test_excluded_cte_contains_emails_and_location(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": ["me@x.com"],
        "locations": [{"city": "Richmond", "region": "British Columbia", "country_code": "CA"}],
        "ips": [], "bots": {}, "geo_overrides": [],
    })
    cte = a._excluded_cte()
    assert "'me@x.com'" in cte
    assert "lower(g.city) = lower('Richmond')" in cte
    assert "upper(g.country_code) = upper('CA')" in cte
    # the named CTEs are all present and the link hop is loopback-guarded
    for name in ("excl_users as", "excl_geo_ips as", "excl_ips as", "excl_seed as", "excl_link as", "excluded as"):
        assert name in cte
    assert "'::1'" in cte


def test_excluded_cte_empty_config_is_valid_and_matches_nothing(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions",
                        lambda: {"emails": [], "locations": [], "ips": [], "bots": {}, "geo_overrides": []})
    cte = a._excluded_cte()
    assert "auth.users where false" in cte
    assert "ip_geo where false" in cte
    assert "as ip where false" in cte      # empty excl_ips


# ---- surface functions: SQL generation (network monkeypatched) -------------
def _capture(monkeypatch, ret=None):
    seen = {"all": []}
    def fake_query(sql):
        seen["sql"] = sql
        seen["all"].append(sql)
        return list(ret) if ret is not None else []
    monkeypatch.setattr(a, "status", lambda: {"configured": True})
    monkeypatch.setattr(a, "_query", fake_query)
    return seen


def test_visitors_applies_exclusion_and_filter(monkeypatch):
    seen = _capture(monkeypatch)
    out = a.visitors(limit=250, q="a' or 1=1")
    assert out["ok"] is True and out["q"] == "a or 11"
    sql = seen["sql"]
    assert "with ident as" in sql and "excluded as" in sql
    assert "not in (select visitor_id from excluded)" in sql       # ev filtered
    assert "ilike '%a or 11%'" in sql                              # sanitized filter inlined
    assert "1=1" not in sql                                        # injection neutralised
    assert "limit 250" in sql


def test_visitors_limit_is_clamped(monkeypatch):
    seen = _capture(monkeypatch)
    a.visitors(limit=999999, q="")
    assert "limit 2000" in seen["sql"]                             # hi cap
    assert "ilike" not in seen["sql"]                              # no filter clause when q empty


def test_sessions_applies_exclusion_and_filter(monkeypatch):
    seen = _capture(monkeypatch)
    out = a.sessions(limit=500, q="richmond")
    assert out["q"] == "richmond"
    sql = seen["sql"]
    assert "excluded as" in sql
    assert "g.city ilike '%richmond%'" in sql
    assert "limit 500" in sql


def test_overview_and_realtime_filter_excluded(monkeypatch):
    seen = _capture(monkeypatch)
    a.overview(days=7)
    assert "not in (select visitor_id from excluded)" in seen["sql"]
    a.realtime()
    assert "not in (select visitor_id from excluded)" in seen["sql"]


def test_terminal_filters_search_events_by_operator(monkeypatch):
    seen = _capture(monkeypatch)
    a.terminal(days=7)
    joined = " ".join(seen["all"])
    assert "anon_id not in (select visitor_id from excluded)" in joined
    assert "user_id not in (select id from excl_users)" in joined


# ---- IP self-exclusion -----------------------------------------------------
def test_clean_ips_keeps_only_ip_chars():
    assert a._clean_ips(["50.92.196.43", " 170.124.173.16 ", "2001:db8::1", "junk!!", ""]) == \
        ["50.92.196.43", "170.124.173.16", "2001:db8::1"]


def test_ips_seed_the_excluded_set(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": [], "locations": [], "ips": ["50.92.196.43", "170.124.173.16"],
        "bots": {}, "geo_overrides": [],
    })
    cte = a._excluded_cte()
    assert "excl_ips as (select unnest(array['50.92.196.43','170.124.173.16']::text[]) as ip)" in cte
    assert "e.ip in (select ip from excl_ips)" in cte      # seeded


# ---- crawler / bot detection ----------------------------------------------
def test_bot_cte_signals_and_config_extension(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": [], "locations": [], "ips": [],
        "bots": {"ips": ["34.122.147.229"], "ua_pattern": "MyScanner", "org_pattern": "acme labs"},
        "geo_overrides": [],
    })
    cte = a._bot_cte()
    assert "'34.122.147.229'" in cte                        # config bot IP
    assert "e.ua ~*" in cte and "Googlebot" in cte and "MyScanner" in cte   # default + extension
    assert "g.is_hosting is true and coalesce(g.is_vpn, false) = false" in cte  # datacenter-not-VPN
    assert "g.org ~*" in cte and "meta platforms" in cte and "acme labs" in cte


def test_not_a_bot_predicate_null_safe():
    assert a._not_a_bot("e") == "(e.visitor_id is null or e.visitor_id not in (select visitor_id from bots))"


def test_geo_override_prefix_is_exempt_from_bot_detection(monkeypatch):
    # A manually relabelled prefix (a real VPN user) must never be auto-flagged as a bot.
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": [], "locations": [], "ips": [], "bots": {},
        "geo_overrides": [{"ip_prefix": "191.40.", "country_code": "HK"}],
    })
    cte = a._bot_cte()
    assert "and not (e.ip like '191.40.%')" in cte


def test_visitors_and_sessions_hide_bots_by_default(monkeypatch):
    seen = _capture(monkeypatch)
    a.visitors()
    assert "v.is_bot = 0" in seen["sql"] and "bots as (" in seen["sql"]
    a.sessions()
    assert "s.is_bot = 0" in seen["sql"]


def test_include_bots_reveals_them(monkeypatch):
    seen = _capture(monkeypatch)
    out = a.visitors(include_bots=True)
    assert out["include_bots"] is True
    assert "is_bot = 0" not in seen["sql"]                  # not filtered
    assert "as is_bot" in seen["sql"]                       # still labelled
    a.sessions(include_bots=True)
    assert "s.is_bot = 0" not in seen["sql"]


def test_overview_reports_bot_count_and_humans_only(monkeypatch):
    seen = _capture(monkeypatch)
    a.overview(days=7)
    joined = " ".join(seen["all"])
    assert "not in (select visitor_id from bots)" in joined                     # humans-only counts
    assert "e.visitor_id in (select visitor_id from bots)" in joined            # bots counted separately


# ---- geo overrides ---------------------------------------------------------
def test_apply_geo_overrides_relabels_by_prefix(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": [], "locations": [], "ips": [], "bots": {},
        "geo_overrides": [{"ip_prefix": "191.40.", "city": "Hong Kong", "region": "Hong Kong", "country_code": "HK"}],
    })
    rows = [
        {"ip": "191.40.7.49", "city": "Frankfurt am Main", "region": "Hesse", "country_code": "DE"},
        {"ip": "8.8.8.8", "city": "Mountain View", "region": "California", "country_code": "US"},
    ]
    out = a._apply_geo_overrides(rows)
    assert out[0]["city"] == "Hong Kong" and out[0]["country_code"] == "HK"     # relabelled
    assert out[1]["city"] == "Mountain View"                                    # untouched


def test_apply_geo_overrides_custom_key(monkeypatch):
    monkeypatch.setattr(a, "_load_exclusions", lambda: {
        "emails": [], "locations": [], "ips": [], "bots": {},
        "geo_overrides": [{"ip_prefix": "191.40.", "country_code": "HK"}],
    })
    rows = [{"last_ip": "191.40.9.9", "country_code": "DE"}]
    a._apply_geo_overrides(rows, "last_ip")
    assert rows[0]["country_code"] == "HK"
