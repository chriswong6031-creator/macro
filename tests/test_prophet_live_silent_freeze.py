"""Hostile matrix for the 2026-08 US Prophet Live silent-freeze class.

Between 2026-07-30T17:20:56Z and 2026-08-26 the US Prophet Live lane published
nothing across ~18 NYSE sessions. Every individual component reported success:

  * the systemd timer fired every 5 minutes and the service exited 0;
  * the evaluator computed correct states from a correct pack and quote tape;
  * ``/api/status`` had no opinion about the lane at all;
  * the external dead-man printed "VPS live plane healthy" for 27 days.

The initiating fault was that the 2026-07-30 cutover installed the unit and made
the VPS the primary writer without ever seeding R2 credentials, so
``r2io.client()`` returned None, ``r2_put_json`` returned False, and ``main()``
returned 0 -- forever.

Each test below is a MUTATION KILL: it fails against the pre-incident behaviour.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import check_vps_live_health as H
from scripts import prophet_live_evaluator as E

NOW = datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc)  # 11:00 ET, mid-session


# --------------------------------------------------------------------------
# Evaluator exit contract (commission D3/D4/D5, hostile matrix 1-5, 13)
# --------------------------------------------------------------------------

def test_publication_is_required_by_default_on_a_real_pass():
    """The contract is fail-CLOSED: a real pass owes a publication unless told
    otherwise. Pre-incident this was inverted and every failure exited 0."""
    assert E.publication_required(dry_run=False) is True


def test_dry_run_owes_no_publication():
    assert E.publication_required(dry_run=True) is False


def test_explicit_opt_out_is_honoured_for_dev_and_ci():
    assert E.publication_required(dry_run=False, explicit=False) is False


def test_env_opt_out_is_honoured(monkeypatch):
    monkeypatch.setenv("PROPHET_LIVE_REQUIRE_PUBLISH", "0")
    assert E.publication_required(dry_run=False) is False


def test_kill_switch_is_an_intentional_stand_down_not_a_fault(monkeypatch):
    """Hostile matrix 13. The kill switch means publication is deliberately off,
    so it must not exit nonzero -- but it must also never be mistaken for a
    healthy publish (the dead-man still reds on the un-advancing pass_ts)."""
    monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", "1")
    assert E.no_publish_set() is True
    assert E.publication_required(dry_run=False) is False


def test_unexpected_exception_exits_nonzero(monkeypatch, capsys):
    """Hostile matrix 1. ``main()`` used to swallow every exception and return 0,
    justified as avoiding "80 reds a day". On a product lane behind a dead-man
    that turns a dead producer into a permanently successful one."""
    def boom(*a, **k):
        raise RuntimeError("synthetic evaluator explosion")

    monkeypatch.setattr(E, "run", boom)
    rc = E.main([])
    assert rc != 0, "an unexpected evaluator failure must not exit 0"
    out = capsys.readouterr().out
    assert out.startswith("::error") or "\n::error" in out, (
        "the annotation must start its line to be visible in Actions"
    )


# --------------------------------------------------------------------------
# Status projection + dead-man (commission D1/D2, hostile matrix 6-12, 14-16)
# --------------------------------------------------------------------------

def _payload(prophet: dict | None, **checks) -> dict:
    """A minimally healthy envelope carrying only the prophet_live check.

    Every other lane is given a passing shape so the assertions below can attribute
    a failure to prophet_live alone.
    """
    base = {
        "quotes": {"age_min": 1.0, "resolved": 500},
        "release_publications": {"age_min": 1.0},
        "orchestrator": {"age_min": 1.0, "lanes": {}},
    }
    base.update(checks)
    if prophet is not None:
        base["prophet_live"] = prophet
    return {"status": "ok", "checks": base}


def _healthy_prophet(**over) -> dict:
    p = {
        "expected_now": True,
        "status": "ok",
        "reason": None,
        "schema": "prophet_live.states/v1",
        "pass_ts": (NOW - timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
        "quote_asof": (NOW - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "session_et": "2026-08-26",
        "pack_as_of": "2026-08-25",
        "pack_expected": "2026-08-25",
        "pack_ok": True,
        "producer": "macro-live-prophet.service",
    }
    p.update(over)
    return p


def _prophet_failures(payload: dict) -> list[str]:
    return [f for f in H.evaluate(payload, now=NOW) if f.startswith("prophet_live")]


def test_healthy_lane_is_quiet():
    assert _prophet_failures(_payload(_healthy_prophet())) == []


def test_missing_prophet_check_reds_during_the_session():
    """Hostile matrix 10 + commission D1/D2. This is the mutation that matters
    most: for 27 days the dead-man had NO prophet_live opinion and printed
    healthy. Absence during a session must be a failure, deliberately unlike the
    ABSENT-OK precedent used by the cn_prophet_live and breadth lanes."""
    assert _prophet_failures(_payload(None)) != []


def test_unparseable_artifact_reds():
    """Hostile matrix 11."""
    assert _prophet_failures(_payload(_healthy_prophet(status="unparseable"))) != []


def test_absent_served_artifact_reds():
    """The observed production state on 2026-08-26: no served file at all."""
    assert _prophet_failures(
        _payload(_healthy_prophet(status="absent", reason="served artifact missing"))
    ) != []


def test_stale_pass_ts_reds():
    """Hostile matrix 6. The producer fires every 5 minutes; 40 minutes of silence
    is a dead lane and must page inside two 10-minute monitoring cadences."""
    stale = (NOW - timedelta(minutes=40)).isoformat().replace("+00:00", "Z")
    assert _prophet_failures(_payload(_healthy_prophet(pass_ts=stale))) != []


def test_fresh_mtime_cannot_hide_a_stale_semantic_clock():
    """Hostile matrix 7/16 -- the load-bearing one. A deploy that copies an old
    file rewrites mtime without advancing a single semantic clock, and a dead
    producer leaves a byte-present artifact behind. Freshness is graded from the
    ABSOLUTE pass_ts only, so a young `served_age_min` must not rescue it."""
    stale = (NOW - timedelta(hours=27 * 24)).isoformat().replace("+00:00", "Z")
    payload = _payload(_healthy_prophet(pass_ts=stale, served_age_min=0.2))
    assert _prophet_failures(payload) != []


def test_stale_quote_clock_reds():
    """Hostile matrix 8."""
    stale = (NOW - timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
    assert _prophet_failures(_payload(_healthy_prophet(quote_asof=stale))) != []


def test_wrong_pack_session_reds():
    """Hostile matrix 9 + defect D12. A same-day or weekend `as_of` darkened 11 of
    the 18 sessions lost in this incident, so it is graded by name rather than
    hidden inside a generic dark status."""
    payload = _payload(_healthy_prophet(
        pack_as_of="2026-08-22", pack_expected="2026-08-25", pack_ok=False))
    assert any("pack" in f for f in _prophet_failures(payload))


def test_globally_dark_artifact_reds_during_a_session():
    payload = _payload(_healthy_prophet(status="dark", reason="stale_pack"))
    assert _prophet_failures(payload) != []


def test_missing_producer_reds():
    assert _prophet_failures(_payload(_healthy_prophet(producer=None))) != []


def test_closed_market_does_not_false_page():
    """Hostile matrix 14. Outside an expected session a stale last-session
    artifact is legitimate evidence of nothing being wrong."""
    stale = (NOW - timedelta(hours=18)).isoformat().replace("+00:00", "Z")
    payload = _payload(_healthy_prophet(
        expected_now=False, pass_ts=stale, quote_asof=stale, status="dark"))
    assert _prophet_failures(payload) == []


def test_unavailable_session_law_fails_closed():
    """A status surface that cannot evaluate the session law must not read healthy."""
    assert _prophet_failures(_payload(_healthy_prophet(expected_now=None))) != []


def test_absolute_age_helper_rejects_unusable_stamps():
    assert H._abs_age_min(None, NOW) is None
    assert H._abs_age_min("", NOW) is None
    assert H._abs_age_min("not-a-timestamp", NOW) is None
    assert H._abs_age_min(NOW.isoformat(), NOW) == pytest.approx(0.0, abs=0.01)


def test_naive_stamp_is_treated_as_utc_not_local():
    """A naive stamp must not silently acquire the monitor's local offset -- that
    would make a stale clock look fresh (or vice versa) by up to a day."""
    naive = (NOW - timedelta(minutes=30)).replace(tzinfo=None).isoformat()
    assert H._abs_age_min(naive, NOW) == pytest.approx(30.0, abs=0.01)


# --------------------------------------------------------------------------
# Unit / deployment invariants (commission D6/D11, hostile matrix 18-20)
# --------------------------------------------------------------------------

def test_timer_persistent_stays_false():
    """Hostile matrix 20 + commission D11. A reboot-missed intraday timer must
    never replay old 'live' moments after boot; historical recovery belongs to an
    explicit PIT replay, not systemd catch-up."""
    from pathlib import Path
    unit = Path(__file__).resolve().parents[1] / "app/deploy/macro-live-prophet.timer"
    assert "Persistent=false" in unit.read_text()


def test_github_backstop_stays_scheduled_off_under_vps_primary():
    """Hostile matrix 18 + commission D6. Two scheduled writers must never be
    armed at once; the backstop self-disables while the VPS is primary."""
    from pathlib import Path
    wf = Path(__file__).resolve().parents[1] / ".github/workflows/prophet-live.yml"
    text = wf.read_text()
    assert "VPS_LIVE_PRIMARY" in text, (
        "the backstop must keep gating itself on the host-primary flag"
    )


# --------------------------------------------------------------------------
# Ownership identity (2026-08-26 production proof gap)
# --------------------------------------------------------------------------

def test_the_evaluator_stamps_an_owner_on_every_published_artifact(monkeypatch):
    """The dead-man reds on `missing producer (unowned lane)`, so the producing
    side must actually stamp one — on LIVE and on globally DARK artifacts alike.

    Caught by the real §9 production proof on 2026-08-26: the lane published
    correctly for the first time in 27 days and the heartbeat still went red,
    because the check graded a field nothing wrote. A dark pass is still a pass
    this lane is accountable for, so the stamp sits after the single LS.evaluate
    call rather than on the live branch only.
    """
    import inspect
    src = inspect.getsource(E.run)
    assert '"producer"' in src, "run() must stamp an owner onto the artifact meta"
    stamp = src.index('art["meta"]["producer"]')
    branch = src.index('art["status"] == "dark"')
    assert stamp < branch, (
        "the producer stamp must precede the dark/live branch so a globally dark "
        "artifact is owned too"
    )
