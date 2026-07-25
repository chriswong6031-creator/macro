"""Tests for the live intraday breadth poller (Phase 2 engine lane).

No network anywhere: the pure join/count core (engine.live_breadth) and the
session-window + fail-soft logic (scripts.live_breadth_poller) are exercised
against synthetic fixtures. Session-window tests use FIXED datetimes across DST
boundaries — no wall-clock-dependent assertion that could flip after 5pm PDT
(UTC-fixture-bomb class).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from engine import live_breadth as lb
from scripts import live_breadth_poller as poller


# ── the gate-1 schema contract, asserted at the byte-key level ─────────────────

TIER_KEYS = {"key", "label", "univ", "n", "adv", "dec", "unch", "adv_pct",
             "pa50", "pa200", "nh", "nl", "net_nh"}
COMP_KEYS = {"n", "adv", "dec", "unch", "adv_pct", "pa50", "pa200", "net_nh"}
TOP_KEYS = {"schema", "asof", "delay_min", "session", "basis", "tiers", "comp", "meta"}


def _th(prev, ma50, ma200, hi52, lo52):
    return {"prev_close": prev, "ma50": ma50, "ma200": ma200,
            "hi52": hi52, "lo52": lo52}


# ── pure join / count ─────────────────────────────────────────────────────────

def test_basic_counts():
    """last vs prev_close -> adv/dec; last vs MA -> pa50/pa200; 52w band -> nh/nl."""
    th = {
        "AAA": _th(100, 90, 80, 120, 70),   # last 110 -> adv, >ma50, >ma200
        "BBB": _th(100, 90, 80, 120, 70),   # last 95  -> dec, >ma50, >ma200
        "CCC": _th(100, 90, 80, 120, 70),   # last 130 -> adv, new high
        "DDD": _th(100, 90, 80, 120, 70),   # last 65  -> dec, new low, <ma
    }
    last = {"AAA": 110, "BBB": 95, "CCC": 130, "DDD": 65}
    t = lb.compute_tier("large", "S&P 500", {"en": "Large cap", "zh": "大盘"}, th, last)
    assert t["n"] == 4
    assert t["adv"] == 2 and t["dec"] == 2 and t["unch"] == 0
    assert t["adv_pct"] == pytest.approx(50.0)
    # pa50: AAA,BBB,CCC above 90; DDD(65) below -> 3/4 = 75
    assert t["pa50"] == pytest.approx(75.0)
    # pa200: AAA,BBB,CCC above 80; DDD below -> 3/4 = 75
    assert t["pa200"] == pytest.approx(75.0)
    assert t["nh"] == 1 and t["nl"] == 1
    assert t["net_nh"] == 0
    assert set(t.keys()) == TIER_KEYS


def test_unchanged_name_not_an_advancer():
    """A halted / flat name (last == prev_close) is unch, never adv or dec, and is
    excluded from adv_pct's denominator (gate 4)."""
    th = {"FLAT": _th(100, 90, 80, 120, 70), "UP": _th(100, 90, 80, 120, 70)}
    last = {"FLAT": 100, "UP": 105}
    t = lb.compute_tier("mid", "S&P 400", {"en": "Mid cap", "zh": "中盘"}, th, last)
    assert t["adv"] == 1 and t["dec"] == 0 and t["unch"] == 1
    assert t["adv_pct"] == pytest.approx(100.0)   # 1 adv / (1 adv + 0 dec)
    assert t["n"] == 2


def test_missing_member_excluded_from_denominators():
    """A member absent from the snapshot is excluded from every count — never
    silently treated as unchanged (gate 4). The caller tallies it in meta."""
    th = {"HERE": _th(100, 90, 80, 120, 70), "GONE": _th(100, 90, 80, 120, 70)}
    last = {"HERE": 110}                        # GONE has no live price
    t = lb.compute_tier("small", "S&P 600", {"en": "Small cap", "zh": "小盘"}, th, last)
    assert t["n"] == 1                          # only HERE counted
    assert t["adv"] == 1 and t["dec"] == 0 and t["unch"] == 0


def test_zero_denominator_ratios_are_none():
    """No members with a live last -> ratios are None, not a ZeroDivisionError."""
    th = {"X": _th(100, 90, 80, 120, 70)}
    t = lb.compute_tier("large", "S&P 500", {"en": "L", "zh": "大"}, th, {})
    assert t["n"] == 0
    assert t["adv_pct"] is None and t["pa50"] is None and t["pa200"] is None
    assert t["nh"] == 0 and t["nl"] == 0


def test_none_ma_excluded_from_pa_denominator():
    """A member the cache holds too shallowly for a 200DMA (ma200 None) is excluded
    from pa200's denominator but still counted in adv/dec and pa50."""
    th = {
        "SHALLOW": _th(100, 90, None, 120, 70),  # no ma200
        "DEEP": _th(100, 90, 80, 120, 70),
    }
    last = {"SHALLOW": 110, "DEEP": 110}
    t = lb.compute_tier("large", "S&P 500", {"en": "L", "zh": "大"}, th, last)
    assert t["pa50"] == pytest.approx(100.0)     # both above ma50 -> 2/2
    assert t["pa200"] == pytest.approx(100.0)    # only DEEP has ma200 -> 1/1


def test_composite_is_member_weighted_and_labelless():
    """comp rolls up counts, weights pa50/pa200 by member count, and carries NO
    label/verdict/tone (stance is the surface's job — gate 1)."""
    big = lb.compute_tier("large", "S&P 500", {"en": "L", "zh": "大"},
                          {f"L{i}": _th(100, 90, 80, 120, 70) for i in range(100)},
                          {f"L{i}": (110 if i < 80 else 95) for i in range(100)})
    small = lb.compute_tier("small", "S&P 600", {"en": "S", "zh": "小"},
                            {f"S{i}": _th(100, 90, 80, 120, 70) for i in range(10)},
                            {f"S{i}": 95 for i in range(10)})   # all below ma50? no, 95>90
    p = lb.build_payload([big, small], asof="2026-07-24T14:00:00Z",
                         delay_min=15, session="rth", missing={"large": 1})
    assert p["comp"]["n"] == 110
    assert p["comp"]["adv"] == big["adv"] + small["adv"]
    # comp carries NO stance wording
    assert "label" not in p["comp"] and "verdict" not in p["comp"] and "tone" not in p["comp"]
    # weighted pa50 lands between the two tier values, closer to the larger tier
    assert big["pa50"] is not None and small["pa50"] is not None
    lo, hi = sorted((big["pa50"], small["pa50"]))
    assert lo <= p["comp"]["pa50"] <= hi
    assert p["meta"]["missing"] == {"large": 1}


# ── schema golden: byte-level key parity with the gate-1 contract ─────────────

def test_schema_key_parity():
    t = lb.compute_tier("large", "S&P 500", {"en": "L", "zh": "大"},
                        {"A": _th(100, 90, 80, 120, 70)}, {"A": 110})
    p = lb.build_payload([t], asof="2026-07-24T14:00:00Z", delay_min=15,
                         session="rth")
    assert set(p.keys()) == TOP_KEYS
    assert p["schema"] == "live.breadth.v1"
    assert p["basis"] == "poll"
    assert set(p["tiers"][0].keys()) == TIER_KEYS
    assert set(p["comp"].keys()) == COMP_KEYS
    assert set(p["tiers"][0]["label"].keys()) == {"en", "zh"}


def test_tier_order_and_keys_mirror_nightly():
    """Tier keys/order match build_site._BREADTH_TIERS (large, mid, small)."""
    assert [t[0] for t in lb.BREADTH_TIERS] == ["large", "mid", "small"]
    assert [t[1] for t in lb.BREADTH_TIERS] == ["breadth", "midcap_breadth", "smallcap_breadth"]
    assert [t[2] for t in lb.BREADTH_TIERS] == ["S&P 500", "S&P 400", "S&P 600"]


def test_payload_is_json_serialisable_finite():
    t = lb.compute_tier("large", "S&P 500", {"en": "L", "zh": "大"},
                        {"A": _th(100, 90, 80, 120, 70)}, {"A": 110})
    p = lb.build_payload([t], asof="x", delay_min=15, session="rth")
    # allow_nan=False path (mirrors write_payload) must not raise
    json.loads(json.dumps(p, allow_nan=False))


# ── symbol canonicalisation (single mapping, dot -> dash) ─────────────────────

def test_canonical_symbol_dot_to_dash():
    assert lb.canonical_symbol("BRK.B") == "BRK-B"
    assert lb.canonical_symbol("bf.b") == "BF-B"
    assert lb.canonical_symbol(" aapl ") == "AAPL"
    assert lb.canonical_symbol("BRK-B") == "BRK-B"   # already dash — idempotent


# ── session window across DST boundaries (fixed datetimes; no wall-clock) ──────

def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_session_rth_summer_edt():
    # 2026-07-24 (EDT, UTC-4): 14:00 UTC = 10:00 ET -> rth
    assert poller.session_tag(_utc(2026, 7, 24, 14, 0)) == "rth"


def test_session_rth_winter_est():
    # 2026-01-14 (EST, UTC-5): 15:00 UTC = 10:00 ET -> rth
    assert poller.session_tag(_utc(2026, 1, 14, 15, 0)) == "rth"


def test_session_pre_and_post_edt():
    # 12:00 UTC = 08:00 ET (EDT) -> pre ; 21:00 UTC = 17:00 ET -> post
    assert poller.session_tag(_utc(2026, 7, 24, 12, 0)) == "pre"
    assert poller.session_tag(_utc(2026, 7, 24, 21, 0)) == "post"


def test_session_closed_overnight_and_weekend():
    # 07:00 UTC = 03:00 ET -> closed (before 04:00 pre-open)
    assert poller.session_tag(_utc(2026, 7, 24, 7, 0)) == "closed"
    # Saturday 2026-07-25 14:00 UTC -> closed
    assert poller.session_tag(_utc(2026, 7, 25, 14, 0)) == "closed"


def test_session_dst_transition_days():
    """The exact DST switch days: the tag depends on the ET wall clock, not a
    fixed UTC offset. 2026 US DST: spring-forward Mar 8, fall-back Nov 1."""
    # Mar 8 2026 (spring forward at 02:00->03:00 ET): 14:00 UTC = 10:00 EDT -> rth
    assert poller.session_tag(_utc(2026, 3, 9, 14, 0)) == "rth"   # Monday after
    # Nov 2 2026 (Monday after fall-back, now EST UTC-5): 15:00 UTC = 10:00 EST -> rth
    assert poller.session_tag(_utc(2026, 11, 2, 15, 0)) == "rth"
    # Same 14:00 UTC on Nov 2 = 09:00 EST -> pre (offset flipped vs summer)
    assert poller.session_tag(_utc(2026, 11, 2, 14, 0)) == "pre"


def test_within_rth_window_edges():
    # 09:25 ET (13:25 UTC EDT) inside; 16:05 ET (20:05 UTC) inside; 16:06 outside
    assert poller.within_rth(_utc(2026, 7, 24, 13, 25)) is True
    assert poller.within_rth(_utc(2026, 7, 24, 20, 5)) is True
    assert poller.within_rth(_utc(2026, 7, 24, 20, 6)) is False
    assert poller.within_rth(_utc(2026, 7, 25, 14, 0)) is False    # Saturday


# ── stale-snapshot delay stamping ─────────────────────────────────────────────

def test_delay_min_adds_snapshot_staleness(monkeypatch):
    """delay_min = vendor floor + minutes since the freshest snapshot ts."""
    monkeypatch.setattr(poller, "_delay_floor", lambda: 15)

    class _Store:
        by_tier = {"large": {"A": _th(100, 90, 80, 120, 70)}}
    now = _utc(2026, 7, 24, 14, 0)
    snap_ts = _utc(2026, 7, 24, 13, 42)          # 18 min stale
    p = poller.build_breadth(_Store(), {"A": 110}, now=now, snapshot_ts=snap_ts)
    assert p["delay_min"] == 15 + 18
    assert p["session"] == "rth"
    assert p["tiers"][0]["adv"] == 1


# ── fail-soft: offline / no-snapshot emits empty tiers, never crashes ──────────

def test_build_breadth_offline_empty(monkeypatch):
    monkeypatch.setattr(poller, "_delay_floor", lambda: 15)

    class _Store:
        by_tier = {"large": {"A": _th(100, 90, 80, 120, 70)}}
    p = poller.build_breadth(_Store(), {}, now=_utc(2026, 7, 24, 14, 0), offline=True)
    assert p["tiers"] == []
    assert p["comp"]["n"] == 0 and p["comp"]["pa50"] is None
    assert p["meta"]["note"] == "offline"
    assert set(p.keys()) == TOP_KEYS


def test_empty_payload_shape():
    p = lb.empty_payload(asof="x", delay_min=15, session="closed", note="no_key")
    assert set(p.keys()) == TOP_KEYS
    assert p["tiers"] == [] and p["basis"] == "poll"
    assert set(p["comp"].keys()) == COMP_KEYS


# ── fetch_full_market key handling (no network) ───────────────────────────────

def test_fetch_offline_short_circuits():
    last, status, ts = poller.fetch_full_market(offline=True)
    assert last == {} and status == "offline" and ts is None


def test_fetch_no_key(monkeypatch):
    monkeypatch.setattr(poller.config, "secret", lambda name: None)
    last, status, ts = poller.fetch_full_market(offline=False)
    assert last == {} and status == "no_key" and ts is None


# ── the --once --offline CLI path emits a well-formed file, never crashes ──────

def test_cli_once_offline_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(poller.config, "site_dir", lambda: tmp_path)
    rc = poller.main(["--once", "--offline"])
    assert rc == 0
    out = tmp_path / "live" / "breadth.json"
    assert out.exists()
    p = json.loads(out.read_text())
    assert set(p.keys()) == TOP_KEYS
    assert p["basis"] == "poll"
    # offline -> empty tiers, fail-soft
    assert p["tiers"] == []
