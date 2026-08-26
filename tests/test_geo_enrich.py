"""Regression coverage for the geo-enrich credential-admission boundary.

Production history this pins (run receipts in the PR body): the lane's last SUCCESS was
run #402 / 31698815868 at 2026-08-13T12:10:34Z. Every run from #403 / 31707633952 at
2026-08-13T13:57:48Z onward failed identically — an unhandled
`urllib.error.HTTPError: HTTP Error 401: Unauthorized` raised out of `_sql()` on the very
first Management API call (`pending_ips`). The SUPABASE_ACCESS_TOKEN repo secret was last
written 2026-07-14T13:08:18Z, exactly 30 days before that boundary: the Management API PAT
expired. Nothing in scripts/geo_enrich.py or .github/workflows/geo-enrich.yml had changed
since 2026-07-14.

Two defects are pinned here:

1. A REJECTED credential had no representation at all. The module already treats an ABSENT
   credential as a clean skip ("only genuine runtime failures should trip the run"), but a
   present-and-rejected one fell through to a bare urllib traceback — which is why the lane
   sat red for 13 days / ~370 runs with no statement anywhere of what had actually broken.

2. Worse, and latent: a credential rejection raised by `upsert()` was caught by the per-IP
   `except Exception: failed += 1` handler, so the loop ran to completion and returned
   ok=True -> exit 0. A PAT that lapsed mid-run (or lacked write scope) therefore painted
   the lane GREEN while writing nothing at all. `ip_geo` is LEFT JOINed by every
   admin/analytics_first_party.py view, so a false green there silently serves advancing
   events against frozen geography.

Unknown must stay unknown: the abstain paths (non-routable IP, unlocatable lookup) must
never write a row, never spend a lookup, and never advance fetched_at.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from scripts import geo_enrich


def _http_error(code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        geo_enrich.QUERY_URL, code, "Unauthorized", {}, io.BytesIO(body)
    )


@pytest.fixture
def configured(monkeypatch):
    """A lane whose secrets are present — the state production was in on 2026-08-13."""
    monkeypatch.setattr(geo_enrich, "PAT", "sbp_expired_token")
    monkeypatch.setattr(geo_enrich, "IPLOCATE_KEY", "iplocate_key")


# --------------------------------------------------------------------------------------
# Defect 1 — a rejected credential must be classified, not raised as a bare traceback.
# --------------------------------------------------------------------------------------

def test_sql_classifies_401_as_credential_rejected(monkeypatch):
    """The exact production wire response: Management API 401 on the SQL endpoint."""
    def _boom(req, timeout=None):
        raise _http_error(401, b'{"message":"Unauthorized"}')

    monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _boom)
    with pytest.raises(geo_enrich.CredentialRejected) as ex:
        geo_enrich._sql("select 1")
    assert ex.value.code == 401


def test_sql_classifies_403_as_credential_rejected(monkeypatch):
    """A revoked (rather than expired) PAT answers 403; same operator remedy."""
    def _boom(req, timeout=None):
        raise _http_error(403, b"Forbidden")

    monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _boom)
    with pytest.raises(geo_enrich.CredentialRejected):
        geo_enrich._sql("select 1")


def test_sql_does_not_swallow_a_non_auth_http_error(monkeypatch):
    """A 503 is a provider outage, NOT a credential fault — it must stay an HTTPError."""
    def _boom(req, timeout=None):
        raise _http_error(503, b"upstream down")

    monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _boom)
    with pytest.raises(urllib.error.HTTPError) as ex:
        geo_enrich._sql("select 1")
    assert ex.value.code == 503
    assert not isinstance(ex.value, geo_enrich.CredentialRejected)


def test_production_failure_is_reproduced_and_named(configured, monkeypatch):
    """THE current production failure: 401 on the first read. Must be a named terminal
    state, never an unhandled traceback."""
    def _reject(_query):
        raise geo_enrich.CredentialRejected(401, '{"message":"Unauthorized"}')

    monkeypatch.setattr(geo_enrich, "_sql", _reject)
    res = geo_enrich.run(10)
    assert res["ok"] is False
    assert res["reason"] == "credential_rejected"
    assert res["code"] == 401


def test_credential_rejection_exits_non_zero_with_a_line_start_annotation(
    configured, monkeypatch, capsys
):
    """Red is the truthful state for a broken credential — but it must NAME the cause.
    The annotation must START the line or GitHub silently drops it."""
    def _reject(_query):
        raise geo_enrich.CredentialRejected(401, "Unauthorized")

    monkeypatch.setattr(geo_enrich, "_sql", _reject)
    rc = geo_enrich.main()
    assert rc != 0, "a rejected credential must not report success"

    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if ln.startswith("::error")]
    assert ann, f"no line-start ::error annotation emitted; got:\n{out}"
    line = ann[0]
    assert "SUPABASE_ACCESS_TOKEN" in line, "the annotation must name the credential to rotate"
    assert "\n" not in line


# --------------------------------------------------------------------------------------
# Defect 2 — a credential rejection on the WRITE plane must never report success.
# --------------------------------------------------------------------------------------

def test_credential_rejected_during_upsert_never_reports_success(configured, monkeypatch):
    """The false-green hole: a PAT that lapses between the read and the writes used to be
    counted as a per-IP `failed`, yielding ok=True / exit 0 with zero rows written."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8", "1.1.1.1"])
    monkeypatch.setattr(
        geo_enrich, "iplocate", lambda ip: {"country_code": "US", "country": "United States"}
    )

    def _reject(_ip, _g):
        raise geo_enrich.CredentialRejected(401, "Unauthorized")

    monkeypatch.setattr(geo_enrich, "upsert", _reject)
    res = geo_enrich.run(10)
    assert res["ok"] is False, "a write-plane 401 must not be reported as a successful run"
    assert res["reason"] == "credential_rejected"
    assert res["enriched"] == 0
    assert geo_enrich.main() != 0


# --------------------------------------------------------------------------------------
# Canonical geography contract — these hold BEFORE and AFTER the repair. They exist so the
# credential fix cannot quietly trade a red lane for guessed geography: unknown stays
# unknown, an abstention spends nothing, and no path invents a city, country or coordinate.
# --------------------------------------------------------------------------------------

@pytest.fixture
def recorder(monkeypatch):
    """Capture every SQL statement the run would execute."""
    sql: list[str] = []
    monkeypatch.setattr(geo_enrich, "_sql", lambda q: sql.append(q) or [])
    return sql


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.4",        # RFC1918 private
        "127.0.0.1",       # loopback
        "169.254.10.1",    # link-local
        "192.168.1.10",    # private
        "fd00::1",         # IPv6 unique-local
        "::1",             # IPv6 loopback
        "not-an-ip",       # permanently malformed source value
        "",                # empty source value
    ],
)
def test_non_routable_or_malformed_ip_is_skipped_and_spends_nothing(
    configured, monkeypatch, recorder, ip
):
    """A bogon or a malformed string is never geolocatable. It must burn no IPLocate
    lookup and write no row — a NULL-pinned row would be excluded from pending_ips()
    forever, permanently freezing that IP."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: [ip])
    called: list[str] = []
    monkeypatch.setattr(geo_enrich, "iplocate", lambda i: called.append(i) or {})

    res = geo_enrich.run(10)
    assert called == [], f"spent a lookup on non-routable {ip!r}"
    assert recorder == [], f"wrote a row for non-routable {ip!r}"
    assert res["skipped"] == 1
    assert res["enriched"] == 0
    assert res["ok"] is True


def test_unlocatable_lookup_abstains_instead_of_guessing(configured, monkeypatch, recorder):
    """A 200 that places the IP nowhere is an ABSTENTION: no row, no guessed country,
    and the IP stays pending so a later run can retry."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["9.9.9.9"])
    monkeypatch.setattr(geo_enrich, "iplocate", lambda ip: {"asn": {"asn": "AS64496"}})

    res = geo_enrich.run(10)
    assert recorder == [], "an unlocatable IP must not be written at all"
    assert res["unresolved"] == 1
    assert res["enriched"] == 0
    assert res["ok"] is True


def test_country_only_resolution_is_accepted_without_inventing_finer_detail(
    configured, monkeypatch, recorder
):
    """Known country / unknown city is a legitimate resolution state — stored as country
    with NULL city, never backfilled with a guessed city or coordinates."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["9.9.9.9"])
    monkeypatch.setattr(
        geo_enrich, "iplocate",
        lambda ip: {"country": "Singapore", "country_code": "SG"},
    )

    res = geo_enrich.run(10)
    assert res["enriched"] == 1
    assert len(recorder) == 1
    stmt = recorder[0]
    assert "'Singapore'" in stmt and "'SG'" in stmt
    # city / lat / lon carried through as SQL NULL, not as a fabricated value.
    for col, val in (("city", None), ("lat", None), ("lon", None)):
        assert f"{col}" in stmt
    assert stmt.count("null") >= 3, f"finer detail must stay null, got: {stmt}"


def test_exact_location_is_stored_with_source_grounded_values(
    configured, monkeypatch, recorder
):
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8"])
    monkeypatch.setattr(
        geo_enrich, "iplocate",
        lambda ip: {
            "country": "United States", "country_code": "US", "subdivision": "California",
            "city": "Mountain View", "latitude": 37.386, "longitude": -122.084,
            "asn": {"asn": "AS15169", "name": "Google LLC"},
            "privacy": {"is_vpn": False, "is_hosting": True},
        },
    )

    res = geo_enrich.run(10)
    assert res["enriched"] == 1
    stmt = recorder[0]
    for token in ("'8.8.8.8'", "'United States'", "'US'", "'California'",
                  "'Mountain View'", "37.386", "-122.084", "'AS15169'", "'Google LLC'"):
        assert token in stmt, f"{token} missing from upsert: {stmt}"


def test_correction_updates_the_existing_row_and_opens_no_second_plane(
    configured, monkeypatch, recorder
):
    """A corrected location must update the canonical row keyed by the entity's IP —
    never append a competing row, and never key by the human-readable place name."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8"])
    monkeypatch.setattr(
        geo_enrich, "iplocate",
        lambda ip: {"country": "United States", "country_code": "US", "city": "Ashburn"},
    )
    geo_enrich.run(10)
    stmt = recorder[0]
    assert "insert into public.ip_geo" in stmt
    assert "on conflict (ip) do update" in stmt, "correction must update, not duplicate"
    assert stmt.count("insert into") == 1
    assert "fetched_at = now()" in stmt


def test_rerun_is_idempotent_for_unchanged_input(configured, monkeypatch):
    """Two runs over identical source data emit identical SQL — a retry rewrites nothing new."""
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8"])
    monkeypatch.setattr(
        geo_enrich, "iplocate",
        lambda ip: {"country": "United States", "country_code": "US", "city": "Ashburn"},
    )
    runs = []
    for _ in range(2):
        seen: list[str] = []
        monkeypatch.setattr(geo_enrich, "_sql", lambda q, s=seen: s.append(q) or [])
        geo_enrich.run(10)
        runs.append(seen)
    assert runs[0] == runs[1]


# --------------------------------------------------------------------------------------
# Freshness / transient-outage semantics.
# --------------------------------------------------------------------------------------

def test_transient_provider_outage_writes_nothing_and_leaves_the_ip_pending(
    configured, monkeypatch, recorder
):
    """A provider 5xx must not destroy last-known-good, must not stamp anything fresh, and
    must leave the IP pending for the next run. It is not a lane failure."""
    def _down(ip):
        raise _http_error(503, b"service unavailable")

    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8"])
    monkeypatch.setattr(geo_enrich, "iplocate", _down)

    res = geo_enrich.run(10)
    assert recorder == [], "a transient outage must not touch the canonical row"
    assert res["enriched"] == 0
    assert res["failed"] == 1
    assert res["ok"] is True
    assert geo_enrich.main() == 0


def test_rate_limit_stops_early_and_is_not_a_failure(configured, monkeypatch, recorder):
    """A 429 ends the run cleanly; the remaining IPs stay pending for the next cron tick."""
    def _limited(ip):
        raise _http_error(429, b"too many requests")

    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8", "1.1.1.1"])
    monkeypatch.setattr(geo_enrich, "iplocate", _limited)

    res = geo_enrich.run(10)
    assert res["rate_limited"] is True
    assert res["ok"] is True
    assert recorder == []


def test_absent_credential_remains_a_clean_skip(monkeypatch, capsys):
    """Unchanged contract: a not-yet-configured lane exits 0 — it is not broken, it is off.
    This is what distinguishes it from a REJECTED credential, which is broken and stays red."""
    monkeypatch.setattr(geo_enrich, "PAT", "")
    monkeypatch.setattr(geo_enrich, "IPLOCATE_KEY", "")
    assert geo_enrich.main() == 0
    assert "skipping (not configured)" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# The lane holds TWO credentials. A dead IPLocate key fails every lookup identically, so
# it is the same whole-run fault as a dead PAT — and left in the per-IP `failed` counter it
# reproduces the same false green. The annotation must name the RIGHT secret to rotate.
# --------------------------------------------------------------------------------------

def test_a_dead_iplocate_key_is_a_whole_run_fault_not_a_per_ip_failure(
    configured, monkeypatch, recorder
):
    # Drive the REAL iplocate() through a faked socket, so the classification itself is
    # under test end-to-end rather than stubbed past.
    def _rejected(req, timeout=None):
        raise _http_error(401, b"invalid api key")

    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8", "1.1.1.1"])
    monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _rejected)

    res = geo_enrich.run(10)
    assert res["ok"] is False, "a dead IPLocate key must not report a successful run"
    assert res["reason"] == "credential_rejected"
    assert res["credential"] == "IPLOCATE_API_KEY"
    assert res["enriched"] == 0
    assert recorder == []


def test_iplocate_classifies_401_but_not_429_or_5xx(monkeypatch):
    """429 stays a rate limit and 5xx stays a transient outage — neither is a rejection."""
    for code, expected in ((401, geo_enrich.CredentialRejected),
                           (403, geo_enrich.CredentialRejected),
                           (429, urllib.error.HTTPError),
                           (503, urllib.error.HTTPError)):
        def _boom(req, timeout=None, _c=code):
            raise _http_error(_c, b"x")

        monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _boom)
        with pytest.raises(expected):
            geo_enrich.iplocate("8.8.8.8")
        if expected is urllib.error.HTTPError:
            monkeypatch.setattr(geo_enrich.urllib.request, "urlopen", _boom)
            with pytest.raises(urllib.error.HTTPError) as ex:
                geo_enrich.iplocate("8.8.8.8")
            assert not isinstance(ex.value, geo_enrich.CredentialRejected)


def test_the_annotation_names_the_credential_that_was_actually_rejected(
    configured, monkeypatch, capsys
):
    monkeypatch.setattr(geo_enrich, "pending_ips", lambda n: ["8.8.8.8"])

    def _rejected(ip):
        raise geo_enrich.CredentialRejected(401, "bad key", credential="IPLOCATE_API_KEY")

    monkeypatch.setattr(geo_enrich, "iplocate", _rejected)
    assert geo_enrich.main() != 0
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::error")][0]
    assert "IPLOCATE_API_KEY" in line
    assert "SUPABASE_ACCESS_TOKEN" not in line, "must not tell the operator to rotate the wrong secret"
