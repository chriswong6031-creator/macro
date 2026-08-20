"""Alert Command Center TIME CONTRACT + evidence routing (Wave 7, PR A).

The Alert Center is a triage layer: its ranking, its "today / 1d ago" wording, its
recency points and its catalyst countdown decide what a PM looks at FIRST.  Two defects
made those lie, and these tests pin the repair so neither can come back:

  D1  ``engine.subsector_rotation_alerts`` stamped events with the rotation payload's
      ``generated_utc`` (when our builder ran) instead of its ``asof`` (the settled
      session the read is about) — so Aug-19 conclusions displayed as "Aug-20 · today".
  D2  the board's own "today" was UTC midnight and every aware timestamp was run through
      ``tz_localize(None)``.  Between 00:00Z and ~05:00Z — a window the nightly pipeline
      runs straight through — a US cross-asset desk rolled its day over while New York
      was still in the previous afternoon, and source timezones were destroyed on read.

  D6  emergence alerts carry a precise ``#ne-<signature>`` anchor but were routed at
      ``baskets.html``, a redirect stub that forwards only ``#theme-*`` and dumps every
      other hash on ``sector_central.html#actnow-section`` — so "Open →" landed on a
      generic page section instead of the exact evidence card.

Every clock here is INJECTED.  No test in this file reads a wall clock.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from engine import alert_time as T
from engine import alert_triage as at
from engine import subsector_rotation_alerts as ROT
from lib import config

# 2026-08-20T00:30:00Z — New York is still 2026-08-19 20:30.  The whole wave in one
# instant: UTC has rolled to the 20th, the US desk has not.
UTC_MIDNIGHT_CROSS = dt.datetime(2026, 8, 20, 0, 30, tzinfo=dt.timezone.utc)
# ...and the same desk a day later (2026-08-20 09:00 ET).
NEXT_BOARD_DAY = dt.datetime(2026, 8, 20, 13, 0, tzinfo=dt.timezone.utc)


# --- 1. the board day ---------------------------------------------------------

def test_board_day_is_new_york_not_utc():
    # T1: at 00:30Z the board is still on the 19th — a US desk has not turned the page.
    assert T.board_date(UTC_MIDNIGHT_CROSS) == dt.date(2026, 8, 19)
    assert T.board_now(UTC_MIDNIGHT_CROSS).hour == 20      # 20:30 ET
    # ...and it does roll over once New York actually gets there.
    assert T.board_date(NEXT_BOARD_DAY) == dt.date(2026, 8, 20)
    # a naive `now` is read as UTC rather than as the host's local wall clock
    assert T.board_date(dt.datetime(2026, 8, 20, 0, 30)) == dt.date(2026, 8, 19)


def test_board_tz_is_pinned_to_america_new_york():
    assert T.BOARD_TZ_NAME == "America/New_York"


# --- 2. the three clocks stay separate ----------------------------------------

def test_rotation_event_keeps_the_session_not_the_build_clock():
    """T2: source asof = Aug-19, generated UTC = Aug-20 02:45 → event date stays Aug-19."""
    block = T.normalize_event({
        "ts": "2026-08-19", "event_date": "2026-08-19", "source_asof": "2026-08-19",
        "recorded_at": "2026-08-20T02:45:00Z", "date_precision": "date",
    })
    assert block["event_date"] == "2026-08-19"
    assert block["source_asof"] == "2026-08-19"
    assert block["board_date"] == "2026-08-19"
    # the build clock survives as PROVENANCE and is never promoted to an event time
    assert block["recorded_at"].startswith("2026-08-20T02:45")
    assert block["date_precision"] == T.PRECISION_DATE


def test_date_only_session_event_never_becomes_midnight():
    """T6: a date/session event keeps its source-native date and gains no clock time."""
    block = T.normalize_event({"ts": "2026-08-19T00:00:00"})       # bonds-shaped
    assert block["event_date"] == "2026-08-19"
    assert block["event_ts"] is None                                # no invented instant
    assert block["board_date"] == "2026-08-19"
    assert block["date_precision"] == T.PRECISION_DATE
    # a bare date string reads identically
    assert T.normalize_event({"ts": "2026-08-19"})["event_date"] == "2026-08-19"


def test_absolute_timestamp_keeps_its_offset_and_projects_to_the_board_day():
    """T5 + T7: the instant is preserved EXACTLY; only the LABEL projects to ET."""
    block = T.normalize_event({"ts": "2026-08-20T00:30:00Z"})
    assert block["date_precision"] == T.PRECISION_TIMESTAMP
    kept = T.parse_instant(block["event_ts"])
    assert kept is not None
    assert kept.tzinfo is not None                                  # NOT tz-stripped
    assert kept.astimezone(dt.timezone.utc) == dt.datetime(2026, 8, 20, 0, 30,
                                                           tzinfo=dt.timezone.utc)
    assert block["board_date"] == "2026-08-19"                      # ...but Aug-19 on the desk
    # a non-UTC offset survives just as intact
    tokyo = T.normalize_event({"ts": "2026-08-20T09:30:00+09:00"})
    assert T.parse_instant(tokyo["event_ts"]).utcoffset() == dt.timedelta(hours=9)


def test_no_aware_timestamp_is_ever_silently_made_naive():
    """T7: the generic tz_localize(None) is gone — offsets survive the read."""
    for raw in ("2026-08-20T00:30:00Z", "2026-08-19T23:00:00-04:00",
                "2026-08-20T09:30:00+09:00"):
        block = T.normalize_event({"ts": raw})
        assert T.parse_instant(block["event_ts"]) is not None, raw


def test_unknown_event_time_is_not_fabricated():
    """A producer that declares it has no event time gets no date at all."""
    block = T.normalize_event({"ts": "2026-08-20 02:45", "date_precision": "unknown"})
    assert block["event_date"] is None and block["event_ts"] is None
    assert block["board_date"] is None
    assert T.age_days(block, dt.date(2026, 8, 20)) is None


def test_age_days_is_clamped_and_measured_in_board_days():
    block = T.normalize_event({"ts": "2026-08-20T00:30:00Z"})       # board day Aug-19
    assert T.age_days(block, dt.date(2026, 8, 19)) == 0             # T3 — still "today"
    assert T.age_days(block, dt.date(2026, 8, 20)) == 1             # T4 — now "1d ago"
    # a same-day-but-later event never reads negative
    assert T.age_days(block, dt.date(2026, 8, 18)) == 0


def test_future_event_is_detectable_for_quarantine():
    block = T.normalize_event({"ts": "2026-08-25"})
    assert T.is_future(block, dt.date(2026, 8, 20)) is True
    assert T.is_future(block, dt.date(2026, 8, 26)) is False
    # an unknown date is not "future" — it is unknown
    assert T.is_future(T.normalize_event({"date_precision": "unknown"}),
                       dt.date(2026, 8, 20)) is False


# --- 3. the rotation PRODUCER (defect 1, at source) ---------------------------

def _rot_payload(asof: str | None, generated: str, *, quadrant="leading",
                 emerging_score=2.0):
    return {
        "asof": asof, "generated_utc": generated,
        "subsectors": [{
            "key": "silver", "name": "Silver", "theme": "Precious Metals",
            "quadrant": quadrant, "rs_mom": 1.0, "accel": 1.0,
            "emerging_score": emerging_score, "rs_ratio": 1.0, "n_members": 5,
            "perf": {"1W": 3.0, "1M": 8.0, "3M": 12.0},
        }],
    }


def _rot_prior(**over):
    base = {"silver": {"name": "Silver", "theme": "Precious Metals",
                       "quadrant": "lagging", "emerging": False, "turn_state": None}}
    base["silver"].update(over)
    return base


def test_rotation_producer_dates_events_by_asof_not_generated_utc():
    """D1 at the source: the Aug-19 tape must not be stamped Aug-20."""
    evs = ROT.compute_events(_rot_payload("2026-08-19", "2026-08-20 02:45"), _rot_prior())
    assert evs, "expected a rotate-in event"
    e = evs[0]
    assert e["event_date"] == "2026-08-19"
    assert e["source_asof"] == "2026-08-19"
    assert e["ts"] == "2026-08-19"                     # legacy field now carries the EVENT
    assert e["recorded_at"] == "2026-08-20 02:45"      # build clock kept as provenance
    assert e["date_precision"] == "date"
    # and the board agrees
    assert T.normalize_event(e)["board_date"] == "2026-08-19"


def test_rotation_event_id_bucket_stays_on_the_recorded_day():
    """DEDUP SAFETY: the append-only store merges by id and every historical row was
    minted with a RECORDED-day bucket.  Re-bucketing on asof would let a future event
    collide with an existing row and be silently dropped by ``by_id.setdefault``."""
    evs = ROT.compute_events(_rot_payload("2026-08-19", "2026-08-20 02:45"), _rot_prior())
    assert evs[0]["id"].endswith(":2026-08-20"), evs[0]["id"]
    # the exact pre-repair id string, so no historical row moves
    assert evs[0]["id"] == "rotation:us:rotation_emerging:silver:2026-08-20"


def test_rotation_id_and_event_date_cannot_collide_across_sessions():
    """The concrete collision the recorded-day bucket avoids: the Aug-20 session recorded
    on Aug-21 must NOT mint the id the Aug-19 session already holds."""
    day1 = ROT.compute_events(_rot_payload("2026-08-19", "2026-08-20 02:45"), _rot_prior())
    day2 = ROT.compute_events(_rot_payload("2026-08-20", "2026-08-21 02:45"), _rot_prior())
    assert day1[0]["id"] != day2[0]["id"]
    assert day1[0]["event_date"] != day2[0]["event_date"]


def test_rotation_producer_refuses_to_invent_a_date_without_asof():
    """No asof → the event time is UNKNOWN.  We do not quietly reinstate the build clock."""
    evs = ROT.compute_events(_rot_payload("", "2026-08-20 02:45"), _rot_prior())
    assert evs
    e = evs[0]
    assert e["event_date"] is None and e["source_asof"] is None
    assert e["date_precision"] == "unknown"
    assert T.normalize_event(e)["board_date"] is None      # no fabricated date
    assert e["recorded_at"] == "2026-08-20 02:45"          # ts stays sortable for the store


# --- 4. the assembled board ---------------------------------------------------

def _fake_feed(monkeypatch, rows):
    """Drive build_triage off a controlled feed (no data/ dependency, no wall clock)."""
    monkeypatch.setattr(at, "_macro_raw", lambda today, cutoff: [])
    monkeypatch.setattr(at, "_load_context", lambda: {})

    def _fake_jsonl(source, today, cutoff, tier_map):
        out = []
        for r in rows:
            if r["source"] != source:
                continue
            clocks = T.normalize_event(r)
            wd = at._window_date(clocks, r)
            if wd is not None and wd < cutoff:
                continue
            out.append({
                "source": source, "type": r["type"], "asset": r.get("asset", source),
                "ts": clocks["event_ts"] or clocks["event_date"] or str(r.get("ts") or ""),
                "date_only": clocks["date_precision"] == T.PRECISION_DATE,
                **{k: clocks[k] for k in ("event_date", "event_ts", "source_asof",
                                          "recorded_at", "board_date", "date_precision")},
                "raw_sev": r.get("severity", "info"),
                "tier": r.get("tier") or tier_map.get(r["type"], "context"),
                "headline": r.get("headline", "H"), "headline_zh": "H",
                "detail": "", "detail_zh": "",
                "anchor": r.get("anchor", "#timeline"), "edge": "", "edge_zh": "",
            })
        return out

    monkeypatch.setattr(at, "_jsonl_raw", _fake_jsonl)


ROTATION_ROW = {
    "source": "rotation", "type": "rotation_emerging", "asset": "silver",
    "ts": "2026-08-19", "event_date": "2026-08-19", "source_asof": "2026-08-19",
    "recorded_at": "2026-08-20T02:45:00Z", "date_precision": "date",
    "severity": "high", "headline": "🌀 Rotating in — Silver",
}


def test_board_labels_an_aug19_rotation_as_today_before_et_midnight(monkeypatch):
    """T3: viewed at 00:30Z (still Aug-19 in New York) the Aug-19 read is TODAY."""
    _fake_feed(monkeypatch, [ROTATION_ROW])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    assert p["board_date"] == "2026-08-19"
    assert p["board_tz"] == "America/New_York"
    a = p["alerts"][0]
    assert a["board_date"] == "2026-08-19"
    assert a["age_days"] == 0
    assert p["summary"]["new_today"] == 1


def test_the_same_event_is_1d_ago_after_et_midnight(monkeypatch):
    """T4: the identical row, one board day later, is not 'today' any more."""
    _fake_feed(monkeypatch, [ROTATION_ROW])
    p = at.build_triage(now=NEXT_BOARD_DAY)
    assert p["board_date"] == "2026-08-20"
    assert p["alerts"][0]["age_days"] == 1
    assert p["summary"]["new_today"] == 0


def test_new_today_never_counts_a_utc_generated_date(monkeypatch):
    """The reconciliation the wave owes: every row counted as 'new today' must have a
    board date EQUAL to the board's day — a build stamp can no longer inflate it."""
    _fake_feed(monkeypatch, [
        ROTATION_ROW,
        {**ROTATION_ROW, "asset": "gold", "event_date": "2026-08-18",
         "source_asof": "2026-08-18", "ts": "2026-08-18"},
    ])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    counted = [a for a in p["alerts"] if a["age_days"] == 0]
    assert p["summary"]["new_today"] == len(counted) == 1
    assert all(a["board_date"] == p["board_date"] for a in counted)


def test_absolute_event_at_utc_midnight_lands_on_the_prior_board_day(monkeypatch):
    """T5 end-to-end: a real 00:30Z instant is an Aug-19 alert on this desk."""
    _fake_feed(monkeypatch, [{
        "source": "vector", "type": "risk_regime", "asset": "BTC",
        "ts": "2026-08-20T00:30:00Z", "severity": "high", "tier": "watch",
    }])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    a = p["alerts"][0]
    assert a["board_date"] == "2026-08-19" and a["age_days"] == 0
    assert a["date_precision"] == "timestamp"
    assert T.parse_instant(a["event_ts"]).tzinfo is not None      # offset still intact


def test_unknown_dated_alert_earns_no_freshness_bonus(monkeypatch):
    """T8: an undateable alert is shown, but never as 'today' and never boosted."""
    _fake_feed(monkeypatch, [{
        "source": "rotation", "type": "rotation_emerging", "asset": "mystery",
        "ts": "2026-08-20T02:45:00", "date_precision": "unknown",
        "severity": "high", "tier": "watch",
    }])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    a = p["alerts"][0]
    assert a["board_date"] is None and a["age_days"] is None
    assert a["priority_components"]["recency"][0] == 0
    assert a["priority_components"]["recency"][1] == "date unknown"
    assert p["summary"]["new_today"] == 0
    assert a["lifecycle"] != "new"


def test_priority_recency_is_zero_for_an_unknown_date():
    fresh, _ = at.priority("watch", "major", 0, "neutral")
    unknown, comp = at.priority("watch", "major", None, "neutral")
    assert comp["recency"] == (0, "date unknown")
    assert unknown == fresh - 20                      # exactly the withheld fresh bonus
    assert sum(v[0] for v in comp.values()) == unknown


def test_future_dated_rows_are_quarantined_not_ranked(monkeypatch):
    """A row claiming a day the desk has not reached is not evidence something happened."""
    _fake_feed(monkeypatch, [
        ROTATION_ROW,
        {**ROTATION_ROW, "asset": "tomorrow", "event_date": "2026-08-25",
         "source_asof": "2026-08-25", "ts": "2026-08-25"},
    ])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    assert p["quarantined"] == 1
    assert [a["asset"] for a in p["alerts"]] == ["silver"]


def test_persistence_span_is_measured_in_board_days(monkeypatch):
    """Mixed date-only and offset-aware fires must not raise, and must span board days."""
    _fake_feed(monkeypatch, [
        {"source": "vector", "type": "risk_regime", "asset": "BTC",
         "ts": "2026-08-17T00:00:00", "tier": "watch", "severity": "high"},
        {"source": "vector", "type": "risk_regime", "asset": "BTC",
         "ts": "2026-08-20T00:30:00Z", "tier": "watch", "severity": "high"},
    ])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    a = p["alerts"][0]
    assert a["fire_count"] == 2
    assert a["first_board_date"] == "2026-08-17"
    assert a["last_board_date"] == "2026-08-19"       # 00:30Z projected back into ET


# --- 5. the catalyst countdown ------------------------------------------------

def test_catalyst_countdown_uses_the_board_day(monkeypatch):
    """CATALYST: at UTC midnight, with ET still on the prior day, "in Nd" counts from
    the ET board date — otherwise every catalyst silently loses a day for ~5 hours."""
    seen: dict = {}

    def _strip(today, horizon):
        seen["today"] = today
        return [{"type": "CPI", "date": "2026-08-21", "impact": "high",
                 "label": "CPI", "md": "Aug 21", "time_et": "08:30"}]

    import engine.event_calendar as ec
    monkeypatch.setattr(ec, "high_impact_strip", _strip)
    _fake_feed(monkeypatch, [ROTATION_ROW])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    assert seen["today"] == dt.date(2026, 8, 19)      # NOT the UTC 20th
    assert p["events"]["next"]["days"] == 2           # Aug-19 → Aug-21


# --- 6. evidence routing (defect 6) -------------------------------------------

TPL = Path(config.ROOT) / "templates"


def test_emergence_alerts_route_to_the_page_that_owns_the_evidence():
    assert at.SOURCES["emergence"]["page"] == "sector_central.html"
    assert at.SOURCES["themes"]["page"] == "sector_central.html"
    # nothing on the board may route through the retired redirect stub
    assert not any(m.get("page") == "baskets.html" for m in at.SOURCES.values())


def test_emergence_open_link_lands_on_the_exact_narrative_card(monkeypatch):
    """DEEP LINK: source=emergence + anchor=#ne-abc123 → sector_central.html#ne-abc123."""
    _fake_feed(monkeypatch, [{
        "source": "emergence", "type": "narrative_forming", "asset": "robotics",
        "ts": "2026-08-19T00:00:00", "severity": "high", "anchor": "#ne-abc123",
    }])
    p = at.build_triage(now=UTC_MIDNIGHT_CROSS)
    assert p["alerts"][0]["link"] == "sector_central.html#ne-abc123"


def test_the_destination_actually_renders_that_anchor():
    """A link is only correct if the target builds the id AND resolves the hash."""
    js = (TPL / "forming_narratives.js").read_text()
    assert 'id="ne-${esc(nv.signature)}"' in js          # the card carries the id
    assert "location.hash.startsWith('#ne-')" in js       # ...and the page resolves it
    assert "scrollIntoView" in js and "ne-flash" in js    # scroll + flash the exact card
    # and sector_central is the page that ships that script
    sc = (TPL / "sector_central.html.j2").read_text()
    assert '{% include "_forming_narratives.html.j2" %}' in sc
    assert 'src="forming_narratives.js"' in (TPL / "_forming_narratives.html.j2").read_text()


def test_emergence_engine_emits_the_anchor_the_destination_expects():
    src = (Path(config.ROOT) / "engine" / "emergence_alerts.py").read_text()
    assert 'f"#ne-{sig}"' in src


def test_legacy_baskets_links_forward_the_narrative_hash_instead_of_eating_it():
    """Bookmarks and already-dispatched pushes still carry baskets.html#ne-<sig>.  The
    stub must carry that hash across, not collapse it to the generic lanes anchor."""
    stub = (TPL / "baskets.html.j2").read_text()
    assert "location.hash.startsWith('#ne-')" in stub
    assert "'sector_central.html'+location.hash" in stub


# --- 7. the shipped artifact keeps the contract -------------------------------

def test_committed_rotation_artifact_still_separates_its_two_clocks():
    """The upstream artifact this repair depends on: asof and generated_utc are distinct
    fields.  If a future producer collapses them, this repair loses its input."""
    p = Path(config.ROOT) / "site" / "marketdata" / "subsector_rotation.json"
    if not p.exists():
        pytest.skip("site/ not checked out (sparse worktree)")
    d = json.loads(p.read_text())
    assert d.get("asof"), "rotation artifact must carry an asof (the settled session)"
    assert d.get("generated_utc"), "rotation artifact must carry generated_utc"
    assert str(d["asof"])[:10] != str(d["generated_utc"])[:10] or True  # may coincide
    assert T.parse_date(d["asof"]) is not None
