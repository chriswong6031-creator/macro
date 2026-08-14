"""Tests for engine/qledger_desk_adapter.py — Eval OS P3 PROSPECTIVE
registration for stock_desk / thematic_desk / demand_chain.

THE ABSOLUTE CONSTRAINT UNDER TEST: nothing retrospective ever registers. A
prior attempt (branch claude/eval-os-t9-adoption, never merged) was refused
3/3 by adversarial review because stock_desk/thematic_desk claims were
anchored and priced at a close already 1-4 completed sessions in the past —
the graded window had already started printing bars by the time the row was
"registered". `outcome_not_yet_determined` is the fix, and the test below
(`test_stale_asof_is_refused_as_retrospective`) is the one this whole program
turns on: a thesis whose window has already begun MUST be refused.

Hermetic: tmp_path stores only, no network, no live data/qledger. No price
mocking is needed anywhere in this file — every function under test here is
either pure calendar arithmetic (`outcome_not_yet_determined`, via
`qledger.resolve_horizon_window`) or metadata assembly from an already-priced
row's own `entry_levels` dict (`translate_row`); nothing reads the parquet
price layer during registration (grading is a separate, later nightly step,
out of scope for this file).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from engine import qledger as q
from engine import qledger_desk_adapter as qda
from engine import qledger_evidence_clock as qclock
from lib import nyse_calendar as nc

# A fixed, real trading session used as "today" throughout this file so every
# assertion is deterministic regardless of the wall-clock date the suite runs
# on. 2026-08-14 is a Friday NYSE session (asserted below, once, as a canary).
TODAY = date(2026, 8, 14)
# The next session strictly after TODAY — every genuinely-fresh claim's
# resolved fill bar lands here.
NEXT_SESSION = nc.session_n_forward(TODAY, 1)
# Five sessions BEFORE today — stale enough that its own "next session after"
# fill bar is itself before TODAY, i.e. already printed.
STALE_ASOF = nc.session_n_back(TODAY, 5).isoformat()


def test_today_is_a_real_session_canary():
    # If this ever goes stale (a calendar rule changed under us), every other
    # assertion in this file is built on a bad anchor — fail loud here first.
    assert nc.is_session(TODAY)
    assert NEXT_SESSION > TODAY


# --------------------------------------------------------------------------- #
# row fixtures — shaped EXACTLY like the real engines' theses.jsonl rows
# --------------------------------------------------------------------------- #
def _stock_desk_row(*, ticker="CARR", lean="constructive", asof=None, horizon_d=20,
                    id_suffix="1", entry=None) -> dict:
    asof = asof if asof is not None else TODAY.isoformat()
    op, thr = ("<", -0.05) if lean == "constructive" else (">", 0.05)
    check = ({"kind": "soft", "reason": "neutral lean — not scored"} if lean == "neutral"
             else {"kind": "rel_return", "subject_ticker": ticker, "vs": "SPY",
                   "op": op, "threshold": thr, "horizon_d": horizon_d})
    return {
        "id": f"{asof}-{ticker}-tok-{id_suffix}", "logged_at": "2026-08-14T21:05:00+00:00",
        "state_asof": asof, "ticker": ticker, "lean": lean, "conviction": "low",
        "horizon_d": horizon_d, "falsifier": {"text": "changes this read", "check": check},
        "check_by": None, "entry_levels": entry or {ticker: 100.0, "SPY": 550.0},
        "engine_verdict": "Leader", "status": "open", "scored_at": None,
        "outcome": None, "realized": None,
    }


def _thematic_desk_row(*, subject_ticker="XLK", lean="overweight", asof=None,
                       horizon_d=20, market="us", id_suffix="1", entry=None) -> dict:
    asof = asof if asof is not None else TODAY.isoformat()
    op, thr = ("<", -0.05) if lean == "overweight" else (">", 0.05)
    check = {"kind": "theme_rel_return", "theme_id": "ai-infra", "subject_ticker": subject_ticker,
             "vs": "SPY", "group": "yahoo", "op": op, "threshold": thr, "horizon_d": horizon_d}
    return {
        "id": f"{market}-{asof}-tok-{id_suffix}", "market": market, "subject": "AI Infrastructure",
        "lean": lean, "conviction": "low", "horizon_d": horizon_d, "thesis": "thesis text",
        "evidence": [], "dissent": "dissent text",
        "falsifier": {"text": "changes this read", "check": check}, "check_by": None,
        "logged_at": "2026-08-14T21:05:00+00:00", "state_asof": asof,
        "entry_levels": entry or {subject_ticker: 220.0, "SPY": 550.0},
    }


def _demand_chain_row(*, ticker="NVDA", lean="outperform", asof=None, horizon_d=126,
                      entry=None) -> dict:
    asof = asof if asof is not None else TODAY.isoformat()
    op, thr = ("<", -0.05) if lean == "outperform" else (">", 0.05)
    return {
        "id": f"{asof}-ai_datacenter-{ticker}", "logged_at": "2026-08-14T21:05:00+00:00",
        "state_asof": asof, "chain": "ai_datacenter", "vintage": f"ai_datacenter:{ticker}:2026:x",
        "subject": ticker, "lean": lean, "conviction": "low", "horizon_d": horizon_d,
        "divergence": "ahead_of_consensus" if lean == "outperform" else "consensus_at_risk",
        "trend": "accelerating", "yoy_pct": 40.0, "tier": "compute",
        "falsifier": {"text": "changes this read",
                      "check": {"kind": "rel_return", "subject_ticker": ticker, "vs": "SPY",
                                "op": op, "threshold": thr, "horizon_d": horizon_d}},
        "check_by": None, "entry_levels": entry or {ticker: 900.0, "SPY": 550.0},
        "status": "open", "scored_at": None, "outcome": None, "realized": None,
    }


# --------------------------------------------------------------------------- #
# direction is a TABLE LOOKUP from the declared lean, never inferred
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lean, want", [("constructive", 1), ("cautious", -1), ("avoid", -1)])
def test_stock_desk_direction_from_lean_table(lean, want):
    row = _stock_desk_row(lean=lean)
    direction = qda._FAMILIES["stock_desk"].lean_direction.get(lean)
    assert direction == want
    claim = qda.translate_row(row, family="stock_desk", direction=direction,
                              timestamp_quality="CRAWL_BOUNDED")
    assert claim["direction"] == want


def test_stock_desk_neutral_lean_is_a_declared_no_call_not_direction_zero():
    # "neutral" is absent from the lean table -> None -> the caller (register_
    # prospective) skips it. It must NEVER become direction=0.
    assert qda._FAMILIES["stock_desk"].lean_direction.get("neutral") is None


@pytest.mark.parametrize("lean, want", [("overweight", 1), ("underweight", -1), ("avoid", -1)])
def test_thematic_desk_direction_from_lean_table(lean, want):
    assert qda._FAMILIES["thematic_desk"].lean_direction.get(lean) == want


@pytest.mark.parametrize("lean, want", [("outperform", 1), ("underperform", -1)])
def test_demand_chain_direction_from_lean_table(lean, want):
    assert qda._FAMILIES["demand_chain"].lean_direction.get(lean) == want


def test_no_family_table_ever_maps_a_lean_to_zero():
    # A direct, permanent invariant: this adapter has no path that can produce
    # a salience (direction=0) claim, because no table entry is 0.
    for fam, cfg in qda._FAMILIES.items():
        assert 0 not in cfg.lean_direction.values(), fam


# --------------------------------------------------------------------------- #
# translation — priceable leg comes from the falsifier, never the display label
# --------------------------------------------------------------------------- #
def test_translate_reads_scope_key_from_falsifier_not_display_label():
    # thematic_desk's `subject` is the unpriceable theme NAME ("AI
    # Infrastructure"); the claim's scope_key must be the resolved proxy ETF.
    row = _thematic_desk_row(subject_ticker="XLK")
    claim = qda.translate_row(row, family="thematic_desk", direction=1,
                              timestamp_quality="CRAWL_BOUNDED")
    assert claim is not None
    assert claim["scope"]["key"] == "XLK"
    assert claim["scope"]["key"] != row["subject"]
    assert claim["bench"] == "SPY"


def test_translate_skips_soft_unscorable_thesis():
    row = _stock_desk_row(lean="neutral")     # kind="soft", no subject_ticker
    claim = qda.translate_row(row, family="stock_desk", direction=1,     # direction irrelevant here
                              timestamp_quality="CRAWL_BOUNDED")
    assert claim is None


def test_translate_requires_a_stable_source_id():
    row = _demand_chain_row()
    row["id"] = ""
    claim = qda.translate_row(row, family="demand_chain", direction=1,
                              timestamp_quality="CRAWL_BOUNDED")
    assert claim is None


def test_translate_preserves_the_declared_ruler_verbatim():
    cases = (
        ("stock_desk", 20, _stock_desk_row(horizon_d=20)),
        ("thematic_desk", 20, _thematic_desk_row(horizon_d=20)),
        ("demand_chain", 126, _demand_chain_row(horizon_d=126)),
    )
    for fam, horizon_d, row in cases:
        claim = qda.translate_row(row, family=fam, direction=1,
                                  timestamp_quality="CRAWL_BOUNDED")
        assert claim["horizon_d"] == horizon_d
        assert claim["horizon_unit"] == q.HORIZON_UNIT_TRADING       # NO calendar approximation


# --------------------------------------------------------------------------- #
# THE FORWARD-ONLY GATE — the defect the whole program exists to close
# --------------------------------------------------------------------------- #
def test_fresh_asof_is_not_yet_determined():
    row = _stock_desk_row(asof=TODAY.isoformat())
    claim = qda.translate_row(row, family="stock_desk", direction=1,
                              timestamp_quality="CRAWL_BOUNDED")
    ok, reason = qda.outcome_not_yet_determined(claim, TODAY)
    assert ok, reason


def test_stale_asof_is_refused_as_retrospective():
    """THE test. A thesis whose state_asof is stale enough that its window's
    fill bar has already printed by `today` MUST be refused — this is the
    exact defect (B1) the prior, refuted attempt shipped."""
    row = _stock_desk_row(asof=STALE_ASOF)
    claim = qda.translate_row(row, family="stock_desk", direction=1,
                              timestamp_quality="CRAWL_BOUNDED")
    ok, reason = qda.outcome_not_yet_determined(claim, TODAY)
    assert not ok
    assert reason.startswith(qda.REASON_RETROSPECTIVE)


def test_asof_equal_to_fill_session_is_still_retrospective():
    # Boundary: an asof whose OWN next session is exactly `today` (not after
    # it) must also be refused — "not yet determined" is a STRICT inequality.
    one_session_back = nc.session_n_back(TODAY, 1).isoformat()
    row = _demand_chain_row(asof=one_session_back)
    claim = qda.translate_row(row, family="demand_chain", direction=1,
                              timestamp_quality="CRAWL_BOUNDED")
    window = q.claim_window(claim, claim["horizon_d"])
    assert window.fill_date == TODAY               # confirms the boundary is exact
    ok, _ = qda.outcome_not_yet_determined(claim, TODAY)
    assert not ok


# --------------------------------------------------------------------------- #
# thematic_desk region scoping — canada/hk/china excluded (no price parquet)
# --------------------------------------------------------------------------- #
def test_thematic_desk_non_us_region_is_excluded():
    for region in ("canada", "hk", "china"):
        row = _thematic_desk_row(market=region)
        assert not qda._FAMILIES["thematic_desk"].region_filter(row)
    us_row = _thematic_desk_row(market="us")
    assert qda._FAMILIES["thematic_desk"].region_filter(us_row)


# --------------------------------------------------------------------------- #
# register_prospective — dry run (real registrar, throwaway temp store)
# --------------------------------------------------------------------------- #
def test_dry_run_reports_zero_rejected_zero_direction_zero_and_is_idempotent():
    rows = [
        _stock_desk_row(ticker="CARR", lean="constructive", id_suffix="1"),
        _stock_desk_row(ticker="LOSER", lean="cautious", id_suffix="2"),
        _stock_desk_row(ticker="NEUT", lean="neutral", id_suffix="3"),   # no-call, must not register
    ]
    stats = qda.register_prospective(rows, family="stock_desk", root="/should/never/be/touched",
                                     today=TODAY, dry_run=True)
    assert stats["error"] is None
    assert stats["n_rows"] == 3
    assert stats["n_skipped_no_call"] == 1            # the neutral row
    assert stats["n_retrospective_skipped"] == 0
    assert stats["n_candidates"] == 2
    assert stats["n_accepted"] == 2
    assert stats["n_rejected"] == 0                   # 0 rejected by _validate_claim
    # idempotency: a second dry run (fresh temp store each call) reports the
    # identical shape — the translation/gate logic is deterministic.
    stats2 = qda.register_prospective(rows, family="stock_desk", root="/should/never/be/touched",
                                      today=TODAY, dry_run=True)
    assert stats2["n_accepted"] == stats["n_accepted"]
    assert stats2["n_rejected"] == 0


def test_dry_run_never_touches_the_given_root(tmp_path):
    untouched = tmp_path / "real_repo_root"
    untouched.mkdir()
    rows = [_demand_chain_row()]
    qda.register_prospective(rows, family="demand_chain", root=untouched, today=TODAY,
                             dry_run=True)
    assert list(untouched.rglob("*")) == []           # nothing written under the real root


# --------------------------------------------------------------------------- #
# register_prospective — live write path + idempotency + retrospective refusal
# --------------------------------------------------------------------------- #
def test_live_registration_writes_open_claims_and_is_idempotent(tmp_path):
    rows = [_stock_desk_row(ticker="CARR", lean="constructive", id_suffix="1")]
    stats1 = qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY,
                                      git_sha="deadbeef")
    assert stats1["n_accepted"] == 1
    assert stats1["n_rejected"] == 0
    claims = q.load_claims(tmp_path)
    assert len(claims) == 1
    assert claims[0]["status"] == q.STATUS_OPEN
    assert claims[0]["horizon_unit"] == q.HORIZON_UNIT_TRADING
    assert claims[0]["horizon_d"] == 20

    # re-run with the SAME rows: idempotent, no duplicate line in the store.
    stats2 = qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY,
                                      git_sha="deadbeef")
    assert stats2["n_accepted"] == 1
    assert len(q.load_claims(tmp_path)) == 1          # still exactly one row


def test_live_registration_never_writes_a_retrospective_claim(tmp_path):
    rows = [_stock_desk_row(ticker="CARR", lean="constructive", asof=STALE_ASOF)]
    stats = qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY)
    assert stats["n_retrospective_skipped"] == 1
    assert stats["n_candidates"] == 0
    assert stats["n_accepted"] == 0
    # THE hard constraint made executable: a retrospective row leaves NO trace
    # in the store at all — not even a status=rejected row. register_batch is
    # never even called for it.
    assert q.load_claims(tmp_path) == []


# --------------------------------------------------------------------------- #
# "could not look" vs "looked, found nothing" — must be told apart
# --------------------------------------------------------------------------- #
def test_source_error_short_circuits_before_any_translation(tmp_path, capsys):
    stats = qda.register_prospective([_stock_desk_row()], family="stock_desk", root=tmp_path,
                                     today=TODAY, source_error="ledger read raised OSError")
    assert stats["source_error"] == "ledger read raised OSError"
    assert stats["n_rows"] == 0                       # nothing was even iterated
    assert q.load_claims(tmp_path) == []
    out = capsys.readouterr().out
    assert any(line.startswith("::warning") for line in out.splitlines())


def test_zero_candidates_from_a_clean_read_is_not_a_source_error(tmp_path):
    stats = qda.register_prospective([], family="stock_desk", root=tmp_path, today=TODAY)
    assert stats["source_error"] is None
    assert stats["n_rows"] == 0
    assert stats["error"] is None


def test_register_batch_failure_is_loud_and_counted(tmp_path, monkeypatch, capsys):
    def _boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(qda.qledger, "register_batch", _boom)
    rows = [_stock_desk_row()]
    stats = qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY)
    assert stats["error"] == "disk full"
    out = capsys.readouterr().out
    assert any(line.startswith("::error") for line in out.splitlines())


# --------------------------------------------------------------------------- #
# evidence clock start — fires on the FIRST accepted claim, never on a dry run
# --------------------------------------------------------------------------- #
def test_evidence_clock_starts_on_first_live_acceptance(tmp_path):
    assert qclock.read_start("stock_desk", root=tmp_path) is None
    rows = [_stock_desk_row(ticker="CARR", lean="constructive")]
    stats = qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY,
                                     git_sha="cafef00d")
    assert stats["clock_started"] is True
    rec = qclock.read_start("stock_desk", root=tmp_path)
    assert rec is not None
    assert rec["declared_horizon_d"] == 20
    assert rec["horizon_unit"] == q.HORIZON_UNIT_TRADING
    assert rec["git_sha"] == "cafef00d"


def test_dry_run_never_starts_the_evidence_clock(tmp_path):
    rows = [_stock_desk_row(ticker="CARR", lean="constructive")]
    qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY, dry_run=True)
    assert qclock.read_start("stock_desk", root=tmp_path) is None


def test_retrospective_only_batch_never_starts_the_evidence_clock(tmp_path):
    rows = [_stock_desk_row(ticker="CARR", lean="constructive", asof=STALE_ASOF)]
    qda.register_prospective(rows, family="stock_desk", root=tmp_path, today=TODAY)
    assert qclock.read_start("stock_desk", root=tmp_path) is None


# --------------------------------------------------------------------------- #
# demand_chain @ 126 — registers at its OWN declared ruler, verbatim
# --------------------------------------------------------------------------- #
def test_demand_chain_registers_at_its_true_126d_ruler(tmp_path):
    rows = [_demand_chain_row(ticker="NVDA", lean="outperform", horizon_d=126)]
    stats = qda.register_prospective(rows, family="demand_chain", root=tmp_path, today=TODAY,
                                     git_sha="abc123")
    assert stats["n_accepted"] == 1
    claim = q.load_claims(tmp_path)[0]
    assert claim["horizon_d"] == 126                  # NOT shortened to reach a faster verdict
    assert claim["horizon_unit"] == q.HORIZON_UNIT_TRADING
    # P0b (in_scope_horizons for the <=63 ladder) is a DIFFERENT agent's file
    # region and is untouched here; the grading ladder for this claim today is
    # whatever engine/qledger.py's in_scope_horizons(126) already returns —
    # this test only pins that registration itself is not blocked or altered
    # by that ladder.
    assert q.in_scope_horizons(126) == sorted(set(q.in_scope_horizons(126)))
