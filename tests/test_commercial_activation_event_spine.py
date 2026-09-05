"""CA1A Activation Event Spine — collector acceptance, envelope v1, and idempotency.

Behavioral proof of the acceptance tests in
research/commercial_activation/CLAUDE_ORCHESTRATOR_HANDOFF_V1_CA1A_EVENT_SPINE_20260903.md
§15, at the two layers CI can actually reach:

  * lib/growth_registry — the derivation + validation authority, tested pure;
  * POST /api/collect through the mounted route (TestClient, the
    tests/test_collect_throttle.py idiom) with the Supabase insert captured, so
    accept/drop/row-shape behavior is observed end to end without a network.

What CI cannot reach — the real PostgREST primary-key conflict and the browser
producers — is exactly the §16 production canary's job; nothing here claims it.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.main as m
from lib import growth_registry

client = TestClient(m.app)

V1_WIRES = {"intelligence.viewed", "personal.act", "watchlist.symbol_added", "watchlist.saved"}
LEGACY_WIRES = {"pageview", "route", "ticker_view", "search", "terminal_jump",
                "click", "scroll", "session_start", "heartbeat", "exit",
                "ad_exposure", "flowobs"}


def _iv_meta(**over):
    meta = {"surface": "flow_velocity", "surface_group": "read",
            "tier_seen": "anon", "rows_visible": 4}
    meta.update(over)
    return meta


def _v1_event(wire="intelligence.viewed", *, eid=None, schema=growth_registry.SCHEMA_VERSION,
              meta=None, **extra):
    e = {"type": wire, "site": "macro", "sid": "tab-1", "path": "/flow_velocity.html",
         "t": 1788480000000, "eid": eid or str(uuid.uuid4()), "schema": schema,
         "meta": _iv_meta() if meta is None else meta}
    e.update(extra)
    return e


@pytest.fixture()
def captured(monkeypatch):
    """Route /api/collect for a routable visitor and capture the would-be DB rows."""
    rows_seen: list[list[dict]] = []
    monkeypatch.setattr(m, "_mm_analytics_insert",
                        lambda rows, access_token=None: rows_seen.append(rows))
    # A genuinely GLOBAL address: the collector's _mm_is_loggable_ip guard uses
    # ipaddress.is_global, which correctly rejects the RFC 5737 TEST-NET ranges —
    # a documentation IP here silently drops every batch before the insert.
    monkeypatch.setattr(m, "_mm_client_ip", lambda request: "8.8.8.8")
    monkeypatch.setattr(m, "_collect_throttle", {})
    monkeypatch.setattr(m, "SUPABASE_SERVICE_ROLE_KEY", "test-key")
    return rows_seen


def _post(events):
    return client.post("/api/collect", json={"events": events})


def _flat(rows_seen):
    return [r for batch in rows_seen for r in batch]


# ── registry as the ONLY source of accepted wires (§15.1-3) ──────────────────────

def test_whitelist_is_the_registry_derivation():
    assert m._MM_EVENT_TYPES == growth_registry.accepted_wires()
    assert V1_WIRES <= set(m._MM_EVENT_TYPES)
    assert LEGACY_WIRES <= set(m._MM_EVENT_TYPES)
    assert m._MM_V1_WIRES == growth_registry.envelope_v1_wires()
    assert set(m._MM_V1_WIRES) == V1_WIRES


def test_unknown_wire_is_refused(captured):
    resp = _post([{"type": "made.up_wire", "sid": "tab-1"}])
    assert resp.status_code == 204
    assert _flat(captured) == []


# ── envelope v1: eid + schema (§15.4-6) ──────────────────────────────────────────

def test_new_wire_without_eid_is_refused(captured):
    e = _v1_event()
    del e["eid"]
    _post([e])
    assert _flat(captured) == []


def test_new_wire_with_malformed_eid_is_refused(captured):
    _post([_v1_event(eid="not-a-uuid")])
    assert _flat(captured) == []


def test_new_wire_without_exact_schema_is_refused(captured):
    _post([_v1_event(schema="growth_events.v2")])
    _post([_v1_event(schema=None)])
    assert _flat(captured) == []


def test_valid_eid_becomes_the_row_id(captured):
    eid = str(uuid.uuid4())
    _post([_v1_event(eid=eid)])
    rows = _flat(captured)
    assert len(rows) == 1 and rows[0]["id"] == eid
    assert rows[0]["type"] == "intelligence.viewed"
    assert rows[0]["meta"] == _iv_meta()


# ── idempotent replay (§15.7-8) ──────────────────────────────────────────────────

def test_exact_replay_reuses_the_same_row_identity_and_never_blocks(captured):
    """The collector's half of one-row replay: the SAME eid maps to the SAME row id
    on every delivery, the response stays 204 (non-blocking success), and the insert
    is conflict-safe (on_conflict=id + ignore-duplicates) so the DB's primary key
    ignores the duplicate instead of failing the batch."""
    eid = str(uuid.uuid4())
    assert _post([_v1_event(eid=eid)]).status_code == 204
    assert _post([_v1_event(eid=eid)]).status_code == 204
    rows = _flat(captured)
    assert [r["id"] for r in rows] == [eid, eid]


def test_insert_request_is_conflict_safe():
    """§15.8's mutation guard (handoff test 29): removing the conflict-safe insert or
    the eid→id mapping must turn something red. The request construction is the
    controllable layer: it must target on_conflict=id and prefer ignore-duplicates."""
    import inspect

    src = inspect.getsource(m._mm_analytics_insert)
    assert "on_conflict=id" in src, "insert lost its on_conflict=id target"
    assert "resolution=ignore-duplicates" in src, "insert lost ignore-duplicates"


# ── property validation and privacy (§15.9-12) ───────────────────────────────────

def test_wrong_enum_value_is_refused(captured):
    _post([_v1_event(meta=_iv_meta(surface_group="reading"))])
    assert _flat(captured) == []


def test_wrong_type_is_refused(captured):
    _post([_v1_event(meta=_iv_meta(rows_visible="4"))])
    _post([_v1_event(meta=_iv_meta(rows_visible=True))])
    assert _flat(captured) == []


def test_undeclared_property_is_refused(captured):
    _post([_v1_event(meta=_iv_meta(email="a@b.c"))])
    assert _flat(captured) == []


def test_raw_insider_tier_is_refused(captured):
    """`insider` is deliberately absent from the tier enum (lib/tiers.py law):
    normalization to `essential` happens at the emitter, and a raw arrival is
    rejected by the same closed-enum rule as any other invalid value."""
    _post([_v1_event(meta=_iv_meta(tier_seen="insider"))])
    assert _flat(captured) == []


def test_null_required_property_is_refused(captured):
    _post([_v1_event(meta=_iv_meta(surface=None))])
    meta = _iv_meta()
    del meta["rows_visible"]
    _post([_v1_event(meta=meta)])
    assert _flat(captured) == []


def test_oversized_string_property_is_refused(captured):
    _post([_v1_event(meta=_iv_meta(surface="x" * 201))])
    assert _flat(captured) == []


def test_no_private_fields_can_ride_a_v1_event(captured):
    """The closed property set IS the privacy boundary: email, names, holdings,
    notes, query text — none are declared, so none can land (§15.12)."""
    for banned in ("email", "name", "holdings", "position_size", "note", "query"):
        _post([_v1_event(meta=_iv_meta(**{banned: "leak"}))])
    assert _flat(captured) == []


def test_drop_diagnostics_are_bounded_and_counted(captured, monkeypatch):
    monkeypatch.setattr(m, "_MM_V1_DROP_COUNTS", {})
    _post([_v1_event(eid="bad")])
    _post([_v1_event(eid="bad")])
    assert m._MM_V1_DROP_COUNTS == {"intelligence.viewed:event_id_invalid": 2}


# ── legacy wires stay exactly as they were (§15.2, §15.26 surface) ───────────────

def test_legacy_wire_needs_no_envelope_and_gets_a_server_uuid(captured):
    _post([{"type": "pageview", "sid": "tab-1", "path": "/", "t": 1788480000000}])
    rows = _flat(captured)
    assert len(rows) == 1
    assert rows[0]["type"] == "pageview"
    uuid.UUID(rows[0]["id"])          # server-minted, well-formed
    assert rows[0]["meta"] is None


def test_legacy_flowobs_meta_passthrough_is_preserved(captured):
    """#6815's accepted convention rides intact: flowobs meta is a bounded
    passthrough, not schema-validated (it is not an envelope-v1 wire)."""
    _post([{"type": "flowobs", "sid": "tab-1",
            "meta": {"ev": "trust_open", "lens": None, "id": None, "sess": "2026-09-04"}}])
    rows = _flat(captured)
    assert len(rows) == 1
    assert rows[0]["meta"]["ev"] == "trust_open"


def test_batch_mixes_legacy_and_v1_and_drops_only_the_invalid(captured):
    good_eid = str(uuid.uuid4())
    _post([
        {"type": "pageview", "sid": "tab-1"},
        _v1_event(eid=good_eid),
        _v1_event(eid="broken"),
    ])
    rows = _flat(captured)
    assert len(rows) == 2
    assert {r["type"] for r in rows} == {"pageview", "intelligence.viewed"}
    assert any(r["id"] == good_eid for r in rows)


# ── product acts never block on analytics (§15.21) ───────────────────────────────

def test_collector_still_204s_when_the_sink_is_unconfigured(monkeypatch):
    monkeypatch.setattr(m, "_mm_client_ip", lambda request: "9.9.9.9")
    monkeypatch.setattr(m, "_collect_throttle", {})
    monkeypatch.setattr(m, "SUPABASE_SERVICE_ROLE_KEY", "")
    resp = _post([_v1_event()])
    assert resp.status_code == 204


def test_insert_helper_never_raises(monkeypatch):
    """_mm_analytics_insert is a background task: any transport failure is swallowed.
    (The client-side half — the page keeping its own state when the beacon dies — is
    a producer near-miss guard in test_ca1a_producers_contract.py.)"""
    monkeypatch.setattr(m, "SUPABASE_SERVICE_ROLE_KEY", "test-key")

    def _boom(req, timeout=None):
        raise OSError("sink down")

    monkeypatch.setattr(m.urllib.request, "urlopen", _boom)
    m._mm_analytics_insert([{"id": str(uuid.uuid4()), "type": "pageview"}])  # must not raise


# ── all four wires accept a canonical happy-path payload (§15.13/17/19 shapes) ───

def test_all_four_v1_wires_accept_their_canonical_payloads(captured):
    events = [
        _v1_event("intelligence.viewed"),
        _v1_event("personal.act", meta={"act": "watchlist_add", "surface": "watchlist"}),
        _v1_event("watchlist.symbol_added",
                  meta={"symbol": "NVDA", "count_after": 3, "storage": "local"}),
        _v1_event("watchlist.saved",
                  meta={"symbol_count": 3, "list_count": 1, "storage": "local"}),
    ]
    _post(events)
    rows = _flat(captured)
    assert [r["type"] for r in rows] == [e["type"] for e in events]
