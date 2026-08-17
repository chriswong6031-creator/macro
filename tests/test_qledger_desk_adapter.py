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
from pathlib import Path

import pandas as pd
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


# --------------------------------------------------------------------------- #
# P0d C2.3/C2.4 — THE demand_chain CONTROL LEG, AND THE REFUSALS IT COUNTS
#
# `demand_chain` is `matched_control_required`, but `_register_qledger_claims`
# passed no `sector_of` at all: every claim registered uncontrolled forever and
# the family's control-evidence clock could never start. The wiring is
# `qledger.membership_gics_sector_of(root)` — membership.parquet + the explicit
# alias normalisation census D0-2 requires — and EVERY candidate's control
# outcome is now counted, because a lookup that returns None on unrecognised
# vocabulary is a legal claim state and stayed dead four months unobserved
# (DSC:CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL).
# --------------------------------------------------------------------------- #
#: A membership store that speaks BOTH vocabularies at once — the real file's
#: measured shape (census D0-2) — plus an unknown value. "OFFIDX" is deliberately
#: absent from it (the ADR/off-index tail).
_MEMBERSHIP_SECTORS = {
    "NVDA": "Technology",                 # Yahoo   -> Information Technology -> XLK
    "MSFT": "Information Technology",     # GICS    -> XLK
    "JNJ": "Healthcare",                  # Yahoo   -> Health Care -> XLV
    "WEIRD": "Quantum Widgets",           # unknown -> `vocabulary_unmapped`, NAMED in the warning
}


def _seed_membership(root: Path) -> Path:
    d = Path(root) / "data" / "universe"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": list(_MEMBERSHIP_SECTORS),
                  "sector": list(_MEMBERSHIP_SECTORS.values())}
                 ).to_parquet(d / "membership.parquet")
    q._MEMBERSHIP_SECTORS.clear()         # the per-root parquet memo
    return Path(root)


def test_demand_chain_control_leg_resolves_through_membership_and_aliases(tmp_path):
    """END-TO-END (C2.3): a demand_chain run with the real wiring registers
    STORED claims carrying the right sector ETFs, across BOTH of the universe
    file's vocabularies, and starts the C3.1 control-evidence clock.

    MUTATION CONTROL: wire the RAW resolver instead
    (`sector_of=lambda t: q.sector_of_ticker(t, tmp_path)`, no alias
    normalisation). The Yahoo-vocabulary names (NVDA "Technology", JNJ
    "Healthcare") then reach `control_for_sector` unnormalised, register
    `control=None`, and this test fails on `stored["NVDA"]["control"] == "XLK"`.
    That is DSC:CONTROL-VOCABULARY-MISMATCH pinned as an executable check.
    """
    _seed_membership(tmp_path)
    rows = [_demand_chain_row(ticker=t)
            for t in ("NVDA", "MSFT", "JNJ", "WEIRD", "OFFIDX")]

    stats = qda.register_prospective(
        rows, family="demand_chain", root=tmp_path, today=TODAY,
        sector_of=q.membership_gics_sector_of(tmp_path),
        raw_sector_of=lambda t: q.sector_of_ticker(t, tmp_path), git_sha="c0ffee")

    assert stats["n_accepted"] == 5
    stored = {c["scope"]["key"]: c for c in q.load_claims(tmp_path)}
    assert stored["NVDA"]["control"] == "XLK"        # Yahoo vocabulary, normalised
    assert stored["MSFT"]["control"] == "XLK"        # GICS vocabulary, untouched
    assert stored["JNJ"]["control"] == "XLV"         # Yahoo vocabulary, normalised
    assert stored["WEIRD"].get("control") is None    # unknown value — refused, counted
    assert stored["OFFIDX"].get("control") is None   # absent from the universe file

    assert stats["control_policy"] == q.CONTROL_POLICY_REQUIRED
    assert stats["n_control_valid"] == 3
    assert stats["n_control_missing"] == 2
    # THE HONEST SPLIT (review round 2, F1). WEIRD's sector IS in the file, the
    # alias table cannot map it -> vocabulary_unmapped. OFFIDX has no row at all
    # -> sector_absent. Before the `raw_sector_of` probe both collapsed to
    # `sector_absent`, so the one family this wiring serves could not report the
    # refusal class census D0-2 exists to make countable.
    assert stats["control_refusals"] == {
        qda.CONTROL_REFUSAL_VOCABULARY: 1,
        qda.CONTROL_REFUSAL_SECTOR_ABSENT: 1,
    }

    # C3.1: the wiring actually starts the matched-control evidence clock, which
    # is the whole reason the control has to be resolved at REGISTRATION.
    clock = q.read_control_clock_start("demand_chain", tmp_path)
    assert clock is not None
    assert clock["control"] in {"XLK", "XLV"}


def test_demand_chain_control_clock_uses_registration_today_not_wall_clock(tmp_path, monkeypatch):
    """`today=` must reach `_start_control_clocks_for`.

    Fixture asof is 2026-08-14; the next NYSE session (fill bar) is 2026-08-17.
    The registrar previously ignored `today` and used ``datetime.now(UTC).date()``.
    Once wall-clock UTC reached the fill bar, `_cohort_prospective` refused the
    same fixture and the clock never started — same main SHA went green on
    2026-08-16 and red on 2026-08-17.

    MUTATION CONTROL: drop `today=` from the `register_batch` call in
    `register_prospective`. With wall-clock frozen to the fill bar this test
    fails on `clock is None`.
    """
    from datetime import datetime, timezone

    _seed_membership(tmp_path)

    class _WallClockFillBar(datetime):
        @classmethod
        def now(cls, tz=None):
            stamp = datetime(2026, 8, 17, 15, 0, 0, tzinfo=timezone.utc)
            return stamp if tz is not None else stamp.replace(tzinfo=None)

    monkeypatch.setattr(q, "datetime", _WallClockFillBar)
    rows = [_demand_chain_row(ticker="NVDA")]
    qda.register_prospective(
        rows, family="demand_chain", root=tmp_path, today=TODAY,
        sector_of=q.membership_gics_sector_of(tmp_path), git_sha="c0ffee")
    clock = q.read_control_clock_start("demand_chain", tmp_path)
    assert clock is not None
    assert clock["control"] == "XLK"


def test_an_unmappable_membership_value_is_named_not_collapsed(tmp_path, capsys):
    """REVIEW ROUND 2, F1 (BLOCKING). `membership_gics_sector_of` answers None for
    BOTH "ticker absent from the universe file" and "vocabulary the alias table
    cannot map", so every D0-2 mismatch was counted as `sector_absent` and the
    nightly annotation named NOTHING — the one family this commit wires could not
    report the class the census demands ("normalise the alias set explicitly AND
    count what it refuses"). The raw probe tells them apart.

    MUTATION CONTROL: drop `raw_sector_of` (from this call, from
    `_classify_control`'s signature, or from the `demand_ledger` wiring). The
    refusal collapses back to `sector_absent`, the sample goes empty, and this
    test fails on `vocabulary_unmapped == 1` AND on `'Quantum Widgets'` being
    absent from the annotation body.
    """
    _seed_membership(tmp_path)
    rows = [_demand_chain_row(ticker=t) for t in ("NVDA", "WEIRD", "OFFIDX")]

    stats = qda.register_prospective(
        rows, family="demand_chain", root=tmp_path, today=TODAY, dry_run=True,
        sector_of=q.membership_gics_sector_of(tmp_path),
        raw_sector_of=lambda t: q.sector_of_ticker(t, tmp_path))

    assert stats["control_refusals"].get(qda.CONTROL_REFUSAL_VOCABULARY) == 1
    assert stats["control_refusals"].get(qda.CONTROL_REFUSAL_SECTOR_ABSENT) == 1

    annotations = [ln for ln in capsys.readouterr().out.splitlines()
                   if ln.startswith("::warning title=demand_chain-qledger-control-missing")]
    assert len(annotations) == 1, annotations
    assert "Quantum Widgets" in annotations[0], (
        "the annotation must NAME the value the alias table could not map — a "
        "bare count is what let census D0-1 stay dead for four months")


def test_the_raw_probe_never_invents_a_sector_for_an_absent_ticker(tmp_path, capsys):
    """The probe DISAMBIGUATES, it never manufactures: a ticker the universe file
    genuinely does not hold stays `sector_absent` and contributes no sample."""
    _seed_membership(tmp_path)
    stats = qda.register_prospective(
        [_demand_chain_row(ticker="OFFIDX")], family="demand_chain", root=tmp_path,
        today=TODAY, dry_run=True,
        sector_of=q.membership_gics_sector_of(tmp_path),
        raw_sector_of=lambda t: q.sector_of_ticker(t, tmp_path))

    assert stats["control_refusals"] == {qda.CONTROL_REFUSAL_SECTOR_ABSENT: 1}
    line = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning title=demand_chain-qledger-control-missing")][0]
    assert "unmapped sector value(s)" not in line


def test_a_raising_sector_resolver_is_logged_not_silent(tmp_path, caplog):
    """REVIEW ROUND 2, F2. A resolver that RAISES produced exactly the same claim
    as one that answered None, with no log at any level — a broken store, a bad
    closure or a renamed column read as "this ticker is off-index". Still
    non-fatal; no longer silent.

    MUTATION CONTROL: delete the `log.warning` from `translate_row`'s `except`
    (restore a bare `sector = None`) — this test fails on the empty caplog.
    """
    def _boom(_ticker):
        raise RuntimeError("membership store exploded")

    with caplog.at_level("WARNING", logger="qledger_desk_adapter"):
        stats = qda.register_prospective(
            [_demand_chain_row(ticker="NVDA")], family="demand_chain",
            root=tmp_path, today=TODAY, dry_run=True, sector_of=_boom)

    assert stats["n_candidates"] == 1              # non-fatal: the claim still registers
    assert stats["n_control_missing"] == 1
    hits = [r.getMessage() for r in caplog.records
            if "sector resolver raised" in r.getMessage()]
    assert hits, "a raising resolver must not be indistinguishable from a None one"
    assert "NVDA" in hits[0] and "membership store exploded" in hits[0]


def test_demand_ledger_passes_a_working_sector_resolver(tmp_path, monkeypatch):
    """`engine/demand_ledger.py::_register_qledger_claims` must actually HAND the
    adapter a resolver, and that resolver must answer with the canonical GICS
    sector NAME (never an ETF — `make_claim` does its own ETF lookup).

    It must ALSO hand over the un-normalised `raw_sector_of` probe, or every
    unmappable vocabulary value is reported as `sector_absent` and the nightly
    annotation names nothing (review round 2, F1).

    MUTATION CONTROL: drop the `sector_of=` kwarg from the
    `register_prospective` call in `_register_qledger_claims` — the captured
    kwargs then carry no `sector_of` and this test fails on the KeyError/None.
    SECOND MUTATION CONTROL: drop the `raw_sector_of=` kwarg from the same call —
    this test fails on `raw_of("WEIRD") == "Quantum Widgets"`.
    """
    from engine import demand_ledger

    captured: dict = {}

    def _capture(rows, **kwargs):
        captured["rows"] = list(rows)
        captured.update(kwargs)
        return {"stub": True}

    monkeypatch.setattr(qda, "register_prospective", _capture)
    out = demand_ledger._register_qledger_claims([_demand_chain_row()], tmp_path,
                                                 today=TODAY)

    assert out == {"stub": True}
    assert captured["family"] == "demand_chain"
    sector_of = captured.get("sector_of")
    assert sector_of is not None, "demand_chain must not register uncontrolled claims"

    _seed_membership(tmp_path)
    assert sector_of("NVDA") == "Information Technology"   # the NAME, not "XLK"
    assert sector_of("JNJ") == "Health Care"
    assert sector_of("WEIRD") is None                      # unknown vocabulary
    assert sector_of("OFFIDX") is None                     # absent from the file
    assert q.control_for_sector(sector_of("NVDA")) == "XLK"

    # ...and the RAW probe, which is the only thing that can tell those last two
    # Nones apart (F1). It returns the file's own value, un-normalised.
    raw_of = captured.get("raw_sector_of")
    assert raw_of is not None, (
        "without the raw probe every D0-2 mismatch is reported as sector_absent")
    assert raw_of("WEIRD") == "Quantum Widgets"
    assert raw_of("NVDA") == "Technology"                   # raw, NOT normalised
    assert raw_of("OFFIDX") is None


def test_control_refusals_are_split_by_cause(tmp_path):
    """C2.4: the four refusal causes are COUNTED SEPARATELY, because one operator
    lever fixes only one of them — `no_sector_source` is a wiring defect,
    `sector_absent` a universe gap, `vocabulary_unmapped` census D0-2's alias
    mismatch, `control_equals_subject_or_bench` C2.2's self-netting.

    MUTATION CONTROL: collapse the buckets into a single "missing" key in
    `_classify_control`. The two assertions on the exact `control_refusals` dict
    then fail.
    """
    no_resolver = qda.register_prospective(
        [_demand_chain_row(ticker="NVDA")], family="demand_chain",
        root=tmp_path / "a", today=TODAY, dry_run=True)
    assert no_resolver["control_refusals"] == {qda.CONTROL_REFUSAL_NO_SOURCE: 1}
    assert no_resolver["n_control_valid"] == 0

    # A RAW-vocabulary resolver — the D0-1 wiring shape: it hands `make_claim` a
    # value `control_for_sector` cannot map, and one that maps onto the subject.
    raw = {"NVDA": "Technology", "XLK": "Information Technology"}
    rows = [_demand_chain_row(ticker="NVDA"),      # unmapped vocabulary
            _demand_chain_row(ticker="XLK"),       # control == subject (C2.2)
            _demand_chain_row(ticker="OFFIDX")]    # resolver answers None
    stats = qda.register_prospective(rows, family="demand_chain",
                                     root=tmp_path / "b", today=TODAY,
                                     dry_run=True, sector_of=raw.get)

    assert stats["n_control_valid"] == 0
    assert stats["n_control_missing"] == 3
    assert stats["control_refusals"] == {
        qda.CONTROL_REFUSAL_VOCABULARY: 1,
        qda.CONTROL_REFUSAL_SELF_OR_BENCH: 1,
        qda.CONTROL_REFUSAL_SECTOR_ABSENT: 1,
    }


def test_missing_controls_emit_one_bare_github_annotation(tmp_path, capsys):
    """C2.4 loudly: a required family with any missing control emits exactly ONE
    `::warning`, carrying the counts, the refusal split, and a SAMPLE of the
    offending vocabulary values — the thing that would have caught D0-1/D0-2 from
    a nightly log instead of from a four-months-later census.

    Asserted with `capsys` and `startswith("::")` on purpose: the annotation must
    be a BARE print. Through a logger it becomes `WARNING ::warning ...` and
    GitHub drops it silently (house law, tests/test_gh_annotation_line_start.py).
    """
    rows = [_demand_chain_row(ticker="NVDA"), _demand_chain_row(ticker="OFFIDX")]
    stats = qda.register_prospective(rows, family="demand_chain", root=tmp_path,
                                     today=TODAY, dry_run=True,
                                     sector_of={"NVDA": "Technology"}.get)

    assert stats["n_control_missing"] == 2
    annotations = [ln for ln in capsys.readouterr().out.splitlines()
                   if ln.startswith("::")]
    assert len(annotations) == 1, annotations
    line = annotations[0]
    assert line.startswith("::warning title=demand_chain-qledger-control-missing::")
    assert "vocabulary_unmapped=1" in line
    assert "sector_absent=1" in line
    assert "'Technology'" in line, (
        "the offending vocabulary value is the load-bearing part of the sample")


def test_a_fully_controlled_run_emits_no_control_annotation(tmp_path, capsys):
    """The annotation is a SIGNAL, not a nightly banner: a run whose controls all
    resolve stays silent."""
    _seed_membership(tmp_path)
    rows = [_demand_chain_row(ticker="NVDA"), _demand_chain_row(ticker="JNJ")]
    stats = qda.register_prospective(
        rows, family="demand_chain", root=tmp_path, today=TODAY, dry_run=True,
        sector_of=q.membership_gics_sector_of(tmp_path))

    assert stats["n_control_valid"] == 2 and stats["n_control_missing"] == 0
    assert stats["control_refusals"] == {}
    assert not [ln for ln in capsys.readouterr().out.splitlines()
                if "qledger-control-missing" in ln]


def test_a_benchmark_only_family_never_emits_the_control_annotation(tmp_path, capsys):
    """C1.4: whether a family needs a control is POLICY. `thematic_desk` is
    `benchmark_only` — the census measured its counterfactual as self-cancelling
    — so its uncontrolled claims are correct, counted, and silent."""
    stats = qda.register_prospective([_thematic_desk_row()], family="thematic_desk",
                                     root=tmp_path, today=TODAY, dry_run=True)

    assert stats["control_policy"] == q.CONTROL_POLICY_BENCHMARK_ONLY
    assert stats["n_control_missing"] == 1
    assert not [ln for ln in capsys.readouterr().out.splitlines()
                if "qledger-control-missing" in ln]


def test_dry_run_reports_the_control_accounting_too(tmp_path, capsys):
    """The classification runs BEFORE registration, so a `dry_run` reports the
    same control numbers the live path would — a wiring defect is visible from a
    rehearsal, not only after it has already registered a night of blind claims."""
    _seed_membership(tmp_path)
    rows = [_demand_chain_row(ticker=t) for t in ("NVDA", "OFFIDX")]
    kwargs = dict(family="demand_chain", today=TODAY,
                  sector_of=q.membership_gics_sector_of(tmp_path))
    dry = qda.register_prospective(rows, root=tmp_path, dry_run=True, **kwargs)
    capsys.readouterr()
    live = qda.register_prospective(rows, root=tmp_path, **kwargs)

    for key in ("control_policy", "n_control_valid", "n_control_missing",
                "control_refusals"):
        assert dry[key] == live[key], key
    assert dry["n_control_valid"] == 1 and dry["n_control_missing"] == 1
