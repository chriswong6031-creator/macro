"""Alert Command Center COVERAGE + RECURRENCE authority (Wave 7, PR B).

Two defects let the board claim more than its evidence supported:

  D3  A FAILED SOURCE LOOKED LIKE A QUIET ONE.  Every reader degraded to ``[]``, so
      "bonds read fine and had nothing to say" and "the bonds reader crashed" were
      mathematically identical.  The pressure gauge is computed from what survived, so
      if the dead feed had been carrying stress events, losing it LOWERED the score and
      produced a more constructive headline — an outage could make the product look
      safer.

  D4/D5  RECURRENCE IMPERSONATED PERSISTENCE.  ``streak_days`` was
      ``(last - first).days`` — elapsed span, not a streak — and >=3 fires over >=3 days
      was called "persisting" AND accepted as severity corroboration.  Silver fired 3
      times across 29 days and was presented as a 29-day persistent condition holding a
      `major` band at priority 60; without that fake corroborator it is 48.  60 is also
      the outbound push floor, so this reached notifications.

Every clock is injected.  No wall-clock reads.
"""
from __future__ import annotations

import datetime as dt

import pytest

from engine import alert_time as T
from engine import alert_triage as at

NOW = dt.datetime(2026, 8, 20, 13, 0, tzinfo=dt.timezone.utc)   # 09:00 ET, Aug-20
BOARD = dt.date(2026, 8, 20)


# --- 1. typed source reads ----------------------------------------------------

def test_read_states_are_four_distinct_answers():
    assert len({at.READ_OK, at.READ_OK_ZERO, at.READ_NO_COVERAGE, at.READ_UNAVAILABLE}) == 4


def test_a_crashed_reader_is_unavailable_not_zero_events(monkeypatch):
    """The control this wave exists for: a raising feed must NOT report 'no alerts'."""
    import engine.bonds_alerts as B

    def _boom():
        raise OSError("simulated store corruption")

    monkeypatch.setattr(B, "load_events", _boom)
    r = at._jsonl_raw("bonds", BOARD, BOARD - dt.timedelta(days=30), at._BONDS_TIER)
    assert r["state"] == at.READ_UNAVAILABLE
    assert r["events"] == []
    assert "OSError" in (r["reason"] or "")            # internal only — never rendered


def test_a_successful_empty_read_is_zero_events_not_unavailable(monkeypatch):
    """A transition-event store can legitimately be quiet for weeks.  That is health,
    not failure — and 'latest event is old' is NOT a failure either."""
    import engine.bonds_alerts as B
    monkeypatch.setattr(B, "load_events", lambda: [])
    r = at._jsonl_raw("bonds", BOARD, BOARD - dt.timedelta(days=30), at._BONDS_TIER)
    assert r["state"] == at.READ_OK_ZERO
    assert r["reason"] is None


def test_events_all_outside_the_window_still_read_ok_zero(monkeypatch):
    """An old-but-readable store is OK_ZERO — never 'unavailable'."""
    import engine.bonds_alerts as B
    monkeypatch.setattr(B, "load_events", lambda: [
        {"ts": "2020-01-01T00:00:00", "type": "credit_band", "severity": "high"}])
    r = at._jsonl_raw("bonds", BOARD, BOARD - dt.timedelta(days=30), at._BONDS_TIER)
    assert r["state"] == at.READ_OK_ZERO


def test_a_missing_store_is_no_coverage_not_a_failure(monkeypatch, tmp_path):
    """First run / a feed that has never produced: disclosed, but not a hole where
    evidence used to be — so it must NOT degrade the board."""
    import engine.watchlist_alerts as W
    monkeypatch.setattr(W, "load_events", lambda: [])
    monkeypatch.setattr(W, "_path", lambda: tmp_path / "nope.jsonl")
    r = at._jsonl_raw("watchlist", BOARD, BOARD - dt.timedelta(days=30), at._WATCHLIST_TIER)
    assert r["state"] == at.READ_NO_COVERAGE
    cov = at.coverage_report([r], at.READ_OK)
    assert cov["state"] == "complete"                  # never-produced != evidence lost


# --- 2. coverage authority ----------------------------------------------------

def _reads(**states):
    return [at._read(s, st, []) for s, st in states.items()]


def test_a_consequential_outage_makes_the_board_partial():
    cov = at.coverage_report(
        _reads(macro=at.READ_OK, bonds=at.READ_UNAVAILABLE, commodity=at.READ_OK),
        at.READ_OK)
    assert cov["state"] == "partial"
    assert "Bonds" in cov["blocking"]
    assert cov["n_unavailable"] == 1


def test_a_non_consequential_outage_is_disclosed_but_not_blocking():
    """Forex/themes cannot contribute act-tier or stress weight, so their absence cannot
    make the pressure gauge look calmer.  Disclose it; do not withdraw the read."""
    cov = at.coverage_report(
        _reads(macro=at.READ_OK, bonds=at.READ_OK, commodity=at.READ_OK,
               vector=at.READ_OK, forex=at.READ_UNAVAILABLE),
        at.READ_OK)
    assert cov["state"] == "complete"
    assert "Forex" in cov["unavailable"] and cov["blocking"] == []


def test_an_unreadable_backdrop_makes_the_board_partial():
    """CONTEXT FAILURE: a missing cross-asset backdrop is missing evidence, not a
    neutral reading that happened to confirm nothing."""
    cov = at.coverage_report(
        _reads(macro=at.READ_OK, bonds=at.READ_OK, commodity=at.READ_OK,
               vector=at.READ_OK),
        at.READ_UNAVAILABLE)
    assert cov["state"] == "partial" and cov["backdrop_missing"] is True


def test_partial_coverage_withdraws_the_whole_tape_verdict():
    """The core product rule: an outage may not buy a calmer headline."""
    cov = at.coverage_report(_reads(bonds=at.READ_UNAVAILABLE), at.READ_OK)
    br = at._board_read([], {"cross_asset": {}, "risk_backdrop": {}}, cov)
    assert br["stance"] == "partial"
    assert br["score"] is None                          # no score invented, high OR low
    assert "Partial tape read" in br["one_liner"]
    assert "Bonds" in br["one_liner"]
    assert "盘面读数不完整" in br["one_liner_zh"]
    # and it never claims a direction
    for word in ("broadly constructive", "leaning risk-off", "The tape is mixed"):
        assert word not in br["one_liner"]


def test_partial_coverage_does_not_invent_a_conservative_score_either():
    """Unknown stays unknown — we do not swap a falsely reassuring number for a falsely
    alarming one."""
    cov = at.coverage_report(_reads(macro=at.READ_UNAVAILABLE), at.READ_OK)
    br = at._board_read([], {}, cov)
    assert br["score"] is None
    assert br["stance"] not in ("risk-off", "mixed", "constructive")


def test_complete_coverage_still_produces_a_normal_read():
    cov = at.coverage_report(
        _reads(macro=at.READ_OK, bonds=at.READ_OK_ZERO, commodity=at.READ_OK,
               vector=at.READ_OK), at.READ_OK)
    br = at._board_read([], {"cross_asset": {"verdict": "diversified"},
                             "risk_backdrop": {}}, cov)
    assert br["stance"] in ("risk-off", "mixed", "constructive")
    assert br["score"] is not None
    assert br["coverage"] == "complete"


# --- 3. the end-to-end outage fixture the wave specified ----------------------

def _stress_row(source, type_, sev="high", tier=None, ts="2026-08-20"):
    return {"source": source, "type": type_, "asset": source, "ts": ts,
            "event_date": ts, "board_date": ts, "event_ts": None, "source_asof": ts,
            "recorded_at": None, "date_precision": "date", "date_only": True,
            "raw_sev": sev, "tier": tier or "act", "headline": f"{source} stress",
            "headline_zh": "", "detail": "", "detail_zh": "", "anchor": "#x",
            "edge": "", "edge_zh": ""}


def _feed(monkeypatch, per_source: dict, *, context=True):
    """per_source: {name: (state, rows)} — drives build_triage through the real
    coverage plumbing without touching data/."""
    def _one(source):
        state, rows = per_source.get(source, (at.READ_OK_ZERO, []))
        return at._read(source, state, rows)

    monkeypatch.setattr(at, "_macro_raw", lambda today, cutoff: _one("macro"))
    monkeypatch.setattr(at, "_jsonl_raw",
                        lambda source, today, cutoff, tier_map: _one(source))
    ctx = {"_state": at.READ_OK, "asof": "2026-08-20", "regime": {},
           "cross_asset": {"verdict": "diversified"}, "risk_backdrop": {}}
    monkeypatch.setattr(at, "_load_context",
                        lambda: ctx if context else {"_state": at.READ_UNAVAILABLE})


def test_bonds_outage_cannot_turn_the_board_constructive(monkeypatch):
    """THE FIXTURE: macro ok, bonds RAISES, commodity ok.  The board keeps rendering
    what it has, but it may not report a calm whole-tape read."""
    _feed(monkeypatch, {
        "macro": (at.READ_OK, [_stress_row("macro", "nfci_tightening", tier="watch")]),
        "bonds": (at.READ_UNAVAILABLE, []),
        "commodity": (at.READ_OK, [_stress_row("commodity", "risk_regime", tier="watch")]),
    })
    p = at.build_triage(now=NOW)
    st = {s["source"]: s["state"] for s in p["coverage"]["sources"]}
    assert st["bonds"] == at.READ_UNAVAILABLE
    assert p["coverage_state"] == "partial"
    assert p["board_read"]["stance"] == "partial"
    assert p["board_read"]["score"] is None
    assert p["board_read"]["stance"] != "constructive"
    # the surviving alerts are still rendered and still usable
    assert len(p["alerts"]) == 2


def test_the_control_a_healthy_empty_bonds_read_keeps_the_board_complete(monkeypatch):
    """Same shape, but bonds SUCCEEDS with zero events.  Board stays authoritative."""
    _feed(monkeypatch, {
        "macro": (at.READ_OK, [_stress_row("macro", "nfci_tightening", tier="watch")]),
        "bonds": (at.READ_OK_ZERO, []),
        "commodity": (at.READ_OK, [_stress_row("commodity", "risk_regime", tier="watch")]),
    })
    p = at.build_triage(now=NOW)
    st = {s["source"]: s["state"] for s in p["coverage"]["sources"]}
    assert st["bonds"] == at.READ_OK_ZERO
    assert p["coverage_state"] == "complete"
    assert p["board_read"]["stance"] in ("risk-off", "mixed", "constructive")
    assert p["board_read"]["score"] is not None


def test_losing_a_stress_feed_can_never_raise_the_apparent_calm(monkeypatch):
    """The exact arithmetic that made an outage look safe: drop a stress-carrying feed
    and the surviving-subset score FALLS. It must not be published as a stance."""
    full = {
        "macro": (at.READ_OK, [_stress_row("macro", "nfci_tightening", tier="watch")]),
        "bonds": (at.READ_OK, [_stress_row("bonds", "credit_band"),
                               _stress_row("bonds", "repo_stress")]),
        "commodity": (at.READ_OK, [_stress_row("commodity", "risk_regime", tier="watch")]),
    }
    _feed(monkeypatch, full)
    complete = at.build_triage(now=NOW)
    outage = dict(full, bonds=(at.READ_UNAVAILABLE, []))
    _feed(monkeypatch, outage)
    degraded = at.build_triage(now=NOW)
    # the subset really would have scored lower — that is the trap
    assert complete["board_read"]["score"] is not None
    # ...and the degraded board refuses to publish any score at all
    assert degraded["board_read"]["score"] is None
    assert degraded["board_read"]["stance"] == "partial"


def test_a_reader_that_raises_at_the_boundary_degrades_instead_of_killing_the_page(monkeypatch):
    """The readers guard their own internals, but this module's contract is that a bad
    feed degrades a SECTION and never fails the build.  A reader that raises at the call
    boundary must still land as `unavailable` — and must still make the board partial,
    not silently drop out of the coverage list."""
    real = at._jsonl_raw

    def _explode(source, today, cutoff, tier_map):
        if source == "commodity":
            raise RuntimeError("boundary explosion")
        return real(source, today, cutoff, tier_map)

    monkeypatch.setattr(at, "_jsonl_raw", _explode)
    monkeypatch.setattr(at, "_macro_raw",
                        lambda today, cutoff: at._read("macro", at.READ_OK_ZERO, []))
    p = at.build_triage(now=NOW)                     # must not raise
    st = {s["source"]: s["state"] for s in p["coverage"]["sources"]}
    assert st["commodity"] == at.READ_UNAVAILABLE
    assert p["coverage_state"] == "partial"


def test_missing_backdrop_is_disclosed_not_treated_as_confirmation(monkeypatch):
    _feed(monkeypatch, {"macro": (at.READ_OK, [_stress_row("macro", "hy_oas_widening",
                                                           tier="watch")])},
          context=False)
    p = at.build_triage(now=NOW)
    assert p["coverage"]["backdrop_missing"] is True
    assert p["coverage_state"] == "partial"
    # a missing backdrop must not be laundered into a cross-asset confirmation
    assert all(a["cross_asset_tag"] != "confirm" for a in p["alerts"])


# --- 4. recurrence is not persistence ----------------------------------------

def test_three_sparse_fires_across_a_month_are_recurring_not_persisting():
    """The mission's exact fixture: Jun 01 / Jun 15 / Jun 30."""
    inst = [{"ts": f"2026-06-{d:02d}T00:00:00"} for d in (1, 15, 30)]
    rec = at._recurrence(inst)
    assert rec["fire_count"] == 3
    assert rec["span_days"] == 29
    assert rec["continuity_verified"] is False
    life = at.lifecycle_of(rec["fire_count"], rec["span_days"], age_days=0,
                           continuity_verified=rec["continuity_verified"])
    assert life == "recurring"
    assert life != "persisting"


def test_the_span_field_is_not_named_or_treated_as_a_streak():
    rec = at._recurrence([{"ts": "2026-06-01T00:00:00"}, {"ts": "2026-06-30T00:00:00"}])
    assert "span_days" in rec
    assert "streak_days" not in rec          # the misnomer is gone from the fact set
    assert rec["span_days"] == 29


def test_new_is_about_the_first_appearance_not_the_latest_firing():
    """Measured on the live board 2026-08-20: rotation rows that had fired twice, 29 days
    apart, were labelled "new" because the old rule only looked at the LATEST fire."""
    assert at.lifecycle_of(fire_count=2, span_days=29, age_days=0) == "recurring"
    assert at.lifecycle_of(fire_count=1, span_days=0, age_days=0) == "new"


def test_persisting_requires_source_verified_continuity():
    verified = at._recurrence([
        {"ts": "2026-06-01T00:00:00", "continuity_verified": True},
        {"ts": "2026-06-15T00:00:00", "continuity_verified": True},
        {"ts": "2026-06-30T00:00:00", "continuity_verified": True}])
    assert verified["continuity_verified"] is True
    assert at.lifecycle_of(3, 29, 0, continuity_verified=True) == "persisting"


def test_the_board_publishes_recurrence_facts_per_alert(monkeypatch):
    rows = [_stress_row("rotation", "rotation_emerging", tier="watch", ts=d)
            for d in ("2026-07-22", "2026-08-05", "2026-08-20")]
    for r in rows:
        r["asset"] = "commmetalssilver"
    _feed(monkeypatch, {"rotation": (at.READ_OK, rows)})
    a = at.build_triage(now=NOW)["alerts"][0]
    assert a["fire_count"] == 3
    assert a["span_days"] == 29
    assert a["lifecycle"] == "recurring"
    assert a["first_board_date"] == "2026-07-22"
    assert a["last_board_date"] == "2026-08-20"
    assert a["continuity_verified"] is False


# --- 5. recurrence is not severity corroboration -----------------------------

def test_sparse_recurrence_no_longer_preserves_a_band():
    """CORROBORATION: an unbacktested watch-major with only sparse recurrence is still
    demoted.  This is the ranking half of the defect, not just copy."""
    doc = {"backtested": False}
    band, why = at.corroborated_severity("major", "watch", "neutral", doc,
                                         fire_count=3, span_days=29)
    assert band == "minor" and why == "uncorroborated"


def test_the_legitimate_corroborators_are_untouched():
    doc = {"backtested": False}
    # genuine cross-asset confirmation keeps the band
    assert at.corroborated_severity("major", "watch", "confirm", doc, 1, 0) == ("major", None)
    # a validated backtest keeps the band
    assert at.corroborated_severity("major", "watch", "neutral",
                                    {"backtested": True}, 1, 0) == ("major", None)
    # true act-tier authority keeps the band
    assert at.corroborated_severity("major", "act", "neutral", doc, 1, 0) == ("major", None)
    # source-verified persistence keeps the band
    assert at.corroborated_severity("major", "watch", "neutral", doc, 3, 29,
                                    continuity_verified=True) == ("major", None)


def test_the_cap_remains_demote_only():
    """Article-2: no path through this function may RAISE a band."""
    rank = {"minor": 0, "major": 1, "critical": 2}
    for band in ("minor", "major", "critical"):
        for tier in ("act", "watch", "context"):
            for ca in ("confirm", "neutral", "diverge"):
                for bt in (True, False):
                    for fc, sp, cv in ((0, 0, False), (9, 60, False), (9, 60, True)):
                        out, _ = at.corroborated_severity(
                            band, tier, ca, {"backtested": bt}, fc, sp, cv)
                        assert rank[out] <= rank[band]


# --- 6. outbound dispatch: the priority that reached notifications -----------

def test_the_silver_shaped_case_drops_below_the_push_floor(monkeypatch):
    """PUSH AUDIT.  A watch-tier, high-severity, unbacktested rotation alert firing 3×
    across 29d scored 22 + 18 + 20 = 60 — exactly the default push threshold — solely
    because bare recurrence declined its demotion.  Without that it is 22 + 6 + 20 = 48.
    This is an intentional correctness change to outbound dispatch."""
    rows = [_stress_row("rotation", "rotation_emerging", tier="watch", ts=d)
            for d in ("2026-07-22", "2026-08-05", "2026-08-20")]
    for r in rows:
        r["asset"] = "commmetalssilver"
    _feed(monkeypatch, {"rotation": (at.READ_OK, rows)})
    a = at.build_triage(now=NOW)["alerts"][0]
    assert a["severity"] == "minor"
    assert a["severity_capped"] == "uncorroborated"
    assert a["priority"] == 48
    assert a["priority"] < 60                       # below the default push floor
    # the arithmetic is exactly the withheld severity points, nothing else moved
    assert a["priority_components"]["conviction"][0] == 22
    assert a["priority_components"]["severity"][0] == 6
    assert a["priority_components"]["recency"][0] == 20


def test_a_genuinely_corroborated_alert_still_clears_the_floor(monkeypatch):
    """The repair must not deafen the board: a backtested family keeps its band."""
    rows = [_stress_row("commodity", "risk_regime", tier="watch", ts=d)
            for d in ("2026-07-22", "2026-08-20")]
    _feed(monkeypatch, {"commodity": (at.READ_OK, rows)})
    a = at.build_triage(now=NOW)["alerts"][0]
    if a["validation"].get("backtested") is True:
        assert a["severity"] == "major" and a["priority"] >= 60
    else:                                            # registry unavailable in this env
        pytest.skip("signal_lab registry not resolvable here")


def test_push_dedup_ledger_behaviour_is_unchanged(tmp_path):
    """The recurrence repair changes WHICH alerts qualify, never how sends are deduped."""
    store = tmp_path / "push_sent.jsonl"
    now = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.timezone.utc)
    at._append_sent(store, {"source": "rotation", "type": "rotation_emerging",
                            "asset": "commmetalssilver", "headline": "h", "priority": 60}, now)
    seen = at._load_recent_sends(store, 6, now)
    assert ("rotation", "rotation_emerging", "commmetalssilver") in seen
    # outside the window it no longer suppresses
    later = now + dt.timedelta(hours=7)
    assert ("rotation", "rotation_emerging", "commmetalssilver") not in \
        at._load_recent_sends(store, 6, later)


def test_push_is_still_config_gated_off_by_default(monkeypatch):
    monkeypatch.setattr(at.config, "load", lambda: {})
    assert at.push_priority_alerts() == []


# --- 7. the page renders both states -----------------------------------------

def _render(payload):
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    from lib import config
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env.get_template("alerts.html.j2").render(**payload)


def test_partial_board_renders_the_missing_family_and_no_gauge(monkeypatch):
    _feed(monkeypatch, {
        "macro": (at.READ_OK, [_stress_row("macro", "nfci_tightening", tier="watch")]),
        "bonds": (at.READ_UNAVAILABLE, []),
    })
    html = _render(at.build_triage(now=NOW))
    assert "{{" not in html and "Undefined" not in html
    assert "Partial tape read" in html
    assert "PARTIAL READ" in html
    assert "读数不完整" in html
    # No needle is DRAWN from a partial read.  Assert on rendered markup, not on the
    # stylesheet — `.gauge-mark` is a CSS rule and is in the <style> block either way.
    assert '<div class="gauge-mark"' not in html
    assert "The tape is broadly constructive" not in html
    assert '<span class="covpill">' in html          # the partial-coverage strip rendered
    assert "Bonds" in html


def test_complete_board_renders_the_gauge_and_a_stance(monkeypatch):
    _feed(monkeypatch, {
        "macro": (at.READ_OK, [_stress_row("macro", "nfci_tightening", tier="watch")]),
        "bonds": (at.READ_OK_ZERO, []),
        "commodity": (at.READ_OK_ZERO, []),
        "vector": (at.READ_OK_ZERO, []),
    })
    html = _render(at.build_triage(now=NOW))
    assert "{{" not in html and "Undefined" not in html
    assert '<div class="gauge-mark"' in html         # the needle IS drawn on a full read
    assert "Partial tape read" not in html
    assert '<span class="covpill">' not in html


def test_the_card_says_re_fired_and_never_persisting_for_a_generic_log(monkeypatch):
    rows = [_stress_row("rotation", "rotation_emerging", tier="watch", ts=d)
            for d in ("2026-07-22", "2026-08-05", "2026-08-20")]
    for r in rows:
        r["asset"] = "commmetalssilver"
    _feed(monkeypatch, {"rotation": (at.READ_OK, rows)})
    html = _render(at.build_triage(now=NOW))
    assert "re-fired" in html and "重复触发" in html
    # rendered PILLS, not the stylesheet (both classes exist in the <style> block)
    assert '<span class="lifepill life-recurring">' in html
    assert '<span class="lifepill life-persisting">' not in html
    # the quick filter followed the vocabulary
    assert 'data-quick="recurring"' in html
    assert 'data-quick="persisting"' not in html
