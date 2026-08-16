"""W5 §15.C/D battery — every §14 gate refuses on a mutated input.

THE PROPERTY UNDER TEST is not "the gates pass".  Today they all refuse, because
``prereg.PREREG_COMMIT``/``PREREG_DOC_SHA256`` are the ``UNSET`` sentinel.  The
property is that each gate refuses for its OWN reason on ITS OWN mutation and
passes on the correct input — i.e. that the gate discriminates.  A gate that
refuses everything is exactly as useless as one that refuses nothing, and the
UNSET state makes the first failure mode very easy to ship unnoticed.

NON-VACUITY.  Every refusal case is paired with a passing control built from the
same fixture, so a gate that stopped discriminating fails here rather than
quietly turning into an unconditional raise.

``prereg`` IS NEVER EDITED.  The frozen constants are the contract; the tests
reach them through ``monkeypatch.setattr``, which the gate modules see because
they read ``prereg.X`` at call time rather than binding at import.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import pytest

from engine.entry_radar.replay import gates, prereg

GOOD_COMMIT = "a" * 40
GOOD_SHA256 = "b" * 64

_AFTER_MARKER = (b"\n*(empty at freeze)*\n\n### A-1 2026-09-01 amendment\n"
                 b"some later, lawful, append-only amendment text\n")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _doc_bytes(body: bytes = b"# W5 prereg\n\nfrozen body text\n") -> bytes:
    """A synthetic prereg: frozen body, the §16 marker line, then amendments."""
    marker = prereg.PREREG_FROZEN_MARKER.encode("utf-8")
    return body + marker + b"; none at freeze)\n" + _AFTER_MARKER


def _budget_line(*, family: str | None = None, n: int | None = None,
                 reason: str | None = None) -> str:
    return json.dumps({
        "kind": "declared_budget",
        "family": prereg.TRIAL_FAMILY if family is None else family,
        "n": prereg.DECLARED_BUDGET if n is None else n,
        "reason": (f"w5_prereg={GOOD_COMMIT}; doc_sha256={GOOD_SHA256}; itemized §13"
                   if reason is None else reason),
        "config_hash": "deadbeef",
    })


def _other_family_line() -> str:
    """A pre-existing unrelated family — G-3's anti-truncation evidence."""
    return json.dumps({"family": "commodity_tsmom", "config_hash": "cafe",
                       "config": {"window": 63}})


def _good_ledger() -> list[str]:
    return [_other_family_line(), _budget_line()]


def _good_hashes() -> dict[str, str]:
    return dict(prereg.EXPECTED_SPEC_HASHES)


def _good_staging() -> dict[str, object]:
    return {"terminal_pin": prereg.TERMINAL_PIN,
            "fixtures": {"w2_slice_a": {"match": True, "n_dots": 7},
                         "w2_slice_b": {"match": True, "n_dots": 3}}}


@pytest.fixture()
def stamped(monkeypatch):
    """The post-PR-5b world: both identity constants set to test values."""
    monkeypatch.setattr(prereg, "PREREG_COMMIT", GOOD_COMMIT, raising=True)
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256", GOOD_SHA256, raising=True)
    return prereg


# =========================================================================== #
# G-1 — prereg frozen-prefix hash
# =========================================================================== #
def test_g1_refuses_while_sha_is_unset(monkeypatch):
    """The pre-stamp state refuses and NAMES why.  (The live module is stamped
    with the merged PR-5a identity — 416bb8ca… — so the sentinel state is
    reconstructed via monkeypatch; the refusal LOGIC is what this pins.)"""
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256", "UNSET")
    with pytest.raises(gates.PreregGateRefusal, match="G-1.*UNSET"):
        gates.check_doc_hash(_doc_bytes())


def test_g1_passes_on_the_matching_frozen_prefix(monkeypatch):
    """CONTROL for every G-1 refusal below: the correct hash passes."""
    doc = _doc_bytes()
    want = hashlib.sha256(gates.frozen_prefix(doc)).hexdigest()
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256", want)
    receipt = gates.check_doc_hash(doc)
    assert receipt.gate == "G-1" and want in receipt.detail


def test_g1_refuses_when_the_frozen_body_is_mutated(monkeypatch):
    doc = _doc_bytes()
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256",
                        hashlib.sha256(gates.frozen_prefix(doc)).hexdigest())
    mutated = _doc_bytes(b"# W5 prereg\n\nfrozen body text EDITED\n")
    with pytest.raises(gates.PreregGateRefusal, match="G-1.*sha256"):
        gates.check_doc_hash(mutated)


def test_g1_ignores_lawful_amendments_appended_after_the_marker(monkeypatch):
    """B4: a §16 amendment appends AFTER the marker and never moves the hash.

    This is the property that keeps the amendment mechanism usable — without it
    the first lawful amendment would refuse the runner forever.
    """
    doc = _doc_bytes()
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256",
                        hashlib.sha256(gates.frozen_prefix(doc)).hexdigest())
    amended = doc + b"\n### A-2 2026-10-02 another amendment\nmore text\n"
    assert gates.frozen_prefix(amended) == gates.frozen_prefix(doc)
    assert gates.check_doc_hash(amended).gate == "G-1"


def test_g1_refuses_a_document_with_no_frozen_marker(monkeypatch):
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256", GOOD_SHA256)
    with pytest.raises(gates.PreregGateRefusal, match="G-1.*marker"):
        gates.check_doc_hash(b"# W5 prereg\n\nno amendment fence here\n")


# =========================================================================== #
# G-2 — merged ancestry
# =========================================================================== #
def test_g2_refuses_while_commit_is_unset(monkeypatch):
    """Pre-stamp sentinel refuses (reconstructed via monkeypatch post-stamp)."""
    monkeypatch.setattr(prereg, "PREREG_COMMIT", "UNSET")
    with pytest.raises(gates.PreregGateRefusal, match="G-2.*UNSET"):
        gates.check_merged_ancestry(lambda _sha: True)


def test_g2_passes_when_the_commit_is_an_ancestor(stamped):
    """CONTROL: a True ancestry answer on a well-formed sha passes."""
    assert gates.check_merged_ancestry(lambda _sha: True).gate == "G-2"


def test_g2_refuses_a_non_forty_hex_commit(monkeypatch):
    monkeypatch.setattr(prereg, "PREREG_COMMIT", "not-a-sha")
    with pytest.raises(gates.PreregGateRefusal, match="G-2.*40-hex"):
        gates.check_merged_ancestry(lambda _sha: True)


def test_g2_refuses_when_the_commit_is_not_an_ancestor(stamped):
    with pytest.raises(gates.PreregGateRefusal, match="G-2.*not an ancestor"):
        gates.check_merged_ancestry(lambda _sha: False)


def test_g2_refuses_when_the_ancestry_probe_raises(stamped):
    """Fail-closed: an unavailable git is NOT a pass."""
    def _boom(_sha):
        raise RuntimeError("git unavailable")
    with pytest.raises(gates.PreregGateRefusal, match="G-2.*fail-closed"):
        gates.check_merged_ancestry(_boom)


# =========================================================================== #
# G-3 — TrialLedger declared-budget admission
# =========================================================================== #
def test_g3_passes_on_a_well_formed_ledger(stamped):
    """CONTROL for every G-3 refusal below."""
    receipt = gates.check_budget_row(_good_ledger())
    assert receipt.gate == "G-3" and str(prereg.DECLARED_BUDGET) in receipt.detail


def test_g3_refuses_a_missing_budget_row(stamped):
    with pytest.raises(gates.PreregGateRefusal, match="G-3.*no declared_budget"):
        gates.check_budget_row([_other_family_line()])


def test_g3_refuses_the_wrong_n(stamped):
    lines = [_other_family_line(), _budget_line(n=prereg.DECLARED_BUDGET - 1)]
    with pytest.raises(gates.PreregGateRefusal, match="G-3.*no declared_budget"):
        gates.check_budget_row(lines)


def test_g3_refuses_the_wrong_reason(stamped):
    lines = [_other_family_line(),
             _budget_line(reason="w5_prereg=SOMETHING_ELSE; itemized §13")]
    with pytest.raises(gates.PreregGateRefusal, match="G-3.*no declared_budget"):
        gates.check_budget_row(lines)


def test_g3_refuses_the_wrong_family(stamped):
    lines = [_other_family_line(), _budget_line(family="some_other_family")]
    with pytest.raises(gates.PreregGateRefusal, match="G-3.*no declared_budget"):
        gates.check_budget_row(lines)


def test_g3_refuses_a_ledger_holding_only_this_family(stamped):
    """The sparse-tree truncation signature: our row present, everyone else gone.

    A one-family trial ledger is not a clean ledger — it is the fleet's
    multiple-testing memory after a write into an unmaterialized tree replaced
    it.  Blessing it would silently reset every other family's honest N.
    """
    with pytest.raises(gates.PreregGateRefusal, match="G-3.*truncation"):
        gates.check_budget_row([_budget_line()])


def test_g3_tolerates_a_torn_final_line(stamped):
    """A torn line is skipped, never counted — and never crashes the gate."""
    assert gates.check_budget_row(
        [_other_family_line(), _budget_line(), '{"kind": "declared_bud']).gate == "G-3"


# --------------------------------------------------------------------------- #
# G-3 / M10 — the look-cell fence ("undeclared look ⇒ caught")
# --------------------------------------------------------------------------- #
def test_check_look_cell_admits_every_declared_cell():
    """CONTROL: all 253 enumerated cells pass, so the fence is not blanket-deny."""
    assert len(prereg.LOOK_CELLS) == prereg.DECLARED_BUDGET
    for cell in prereg.LOOK_CELLS:
        gates.check_look_cell(cell)


def test_check_look_cell_refuses_an_undeclared_cell():
    with pytest.raises(gates.PreregGateRefusal, match="not one of the"):
        gates.check_look_cell("q6_the_one_that_worked")


def test_check_look_cell_refuses_a_near_miss_of_a_declared_cell():
    """Near-misses are the realistic failure: a renamed cell is an UNDECLARED one."""
    assert "q1_primary" in prereg.LOOK_CELLS
    with pytest.raises(gates.PreregGateRefusal):
        gates.check_look_cell("q1_primary_v2")


def test_the_runners_own_look_cells_are_all_declared():
    """The runner must not be able to spend an undeclared look.

    ``scripts/entry_radar_replay.py`` routes every ``log_look`` through
    ``check_look_cell``, so an undeclared name is refused at run time — but that
    refusal would surface as a crashed replay hours in.  Pinning the runner's own
    cell names here makes a §13-illegal name a fast unit failure instead.
    """
    from scripts import entry_radar_replay as runner

    for key in runner._DETECTOR_LOOK_KEY.values():
        gates.check_look_cell(f"primary_table_{key}")
    gates.check_look_cell("refusal_census")
    # C4 is deliberately unmapped: it owns no primary table, and a name minted
    # for it would be undeclared.
    assert "C4_MTF_TURN@1" not in runner._DETECTOR_LOOK_KEY
    with pytest.raises(gates.PreregGateRefusal):
        gates.check_look_cell("primary_table_C4")


def test_log_look_refuses_before_it_writes(tmp_path):
    """Ordering: an undeclared cell must never reach the APPEND-ONLY ledger.

    A spurious row there cannot be withdrawn, so the fence has to come first.
    """
    from scripts import entry_radar_replay as runner

    ledger = tmp_path / "trial_ledger.jsonl"
    with pytest.raises(gates.PreregGateRefusal):
        runner.log_look("not_a_declared_cell", {"x": 1},
                        info_cutoff="2026-08-14", ledger_path=ledger)
    assert not ledger.exists(), "the ledger was written before the fence ran"
    # CONTROL: a declared cell does write.
    assert runner.log_look("refusal_census", {"panel": "A", "n_refusals": 0},
                           info_cutoff="2026-08-14", ledger_path=ledger) is True
    assert ledger.exists()


# =========================================================================== #
# G-4 — detector spec hashes
# =========================================================================== #
def test_g4_passes_on_the_frozen_registry():
    """CONTROL: the frozen hashes + a refusing F1 pass."""
    assert gates.check_spec_hashes(_good_hashes(), lambda: True).gate == "G-4"


def test_g4_refuses_a_spec_hash_mismatch():
    live = _good_hashes()
    live["C2_1D_TURN@1"] = "0" * 16
    with pytest.raises(gates.PreregGateRefusal, match="G-4.*C2_1D_TURN@1"):
        gates.check_spec_hashes(live, lambda: True)


def test_g4_refuses_a_missing_detector():
    live = _good_hashes()
    del live["C5_BOTTOM_WATCH@1"]
    with pytest.raises(gates.PreregGateRefusal, match="G-4.*C5_BOTTOM_WATCH@1"):
        gates.check_spec_hashes(live, lambda: True)


def test_g4_refuses_an_extra_unregistered_detector():
    live = _good_hashes()
    live["C6_SOMETHING_NEW@1"] = "1" * 16
    with pytest.raises(gates.PreregGateRefusal, match="G-4.*unregistered"):
        gates.check_spec_hashes(live, lambda: True)


def test_g4_refuses_when_f1_stops_refusing():
    """F1 acquiring a spec mid-replay would change what 'the family' means."""
    with pytest.raises(gates.PreregGateRefusal, match="G-4.*F1_FUSION"):
        gates.check_spec_hashes(_good_hashes(), lambda: False)


def test_g4_refuses_when_the_f1_probe_raises():
    def _boom():
        raise RuntimeError("registry exploded")
    with pytest.raises(gates.PreregGateRefusal, match="G-4.*fail-closed"):
        gates.check_spec_hashes(_good_hashes(), _boom)


def test_g4_frozen_hashes_match_the_live_registry():
    """The gate's premise: the W3 lock still describes the shipped detectors.

    Not a tautology — it recomputes from ``engine.entry_radar.detectors`` rather
    than from ``prereg``, so a detector edit that silently changed a spec hash
    fails HERE, which is the earliest place it can be caught.
    """
    from engine.entry_radar import detectors

    live = {did: detectors.get_spec(did).spec_hash for did in detectors.DETECTORS}
    assert live == dict(prereg.EXPECTED_SPEC_HASHES)


# =========================================================================== #
# G-5 — staged-Terminal fidelity
# =========================================================================== #
def test_g5_passes_on_a_matching_report():
    """CONTROL for every G-5 refusal below."""
    assert gates.check_staging_fidelity(_good_staging()).gate == "G-5"


def test_g5_refuses_a_pin_mismatch():
    report = _good_staging()
    report["terminal_pin"] = "f" * 40
    with pytest.raises(gates.PreregGateRefusal, match="G-5.*pin"):
        gates.check_staging_fidelity(report)


def test_g5_refuses_a_fixture_mismatch():
    report = _good_staging()
    report["fixtures"]["w2_slice_b"] = {"match": False, "n_dots": 2}
    with pytest.raises(gates.PreregGateRefusal, match="G-5.*w2_slice_b"):
        gates.check_staging_fidelity(report)


def test_g5_refuses_an_empty_report():
    """An ABSENT staging report must never read the same as a passing one."""
    with pytest.raises(gates.PreregGateRefusal):
        gates.check_staging_fidelity({})


def test_g5_refuses_a_report_with_no_fixture_comparisons():
    with pytest.raises(gates.PreregGateRefusal, match="G-5.*no fixture"):
        gates.check_staging_fidelity({"terminal_pin": prereg.TERMINAL_PIN,
                                      "fixtures": {}})


def test_g5_refuses_a_truthy_but_non_true_match():
    """``match: 1`` is not ``match: True`` — the gate demands the bool."""
    report = _good_staging()
    report["fixtures"]["w2_slice_a"] = {"match": 1}
    with pytest.raises(gates.PreregGateRefusal, match="G-5.*w2_slice_a"):
        gates.check_staging_fidelity(report)


# =========================================================================== #
# G-6 — holdout fence (battery D)
# =========================================================================== #
def test_g6_admits_a_fit_era_decision():
    """CONTROL: an in-era session passes silently."""
    assert gates.check_decision_in_era(date(2015, 6, 1)) is None


def test_g6_admits_a_test_era_decision():
    assert gates.check_decision_in_era(prereg.HOLDOUT_BOUNDARY) is None


def test_g6_refuses_a_holdout_decision():
    beyond = prereg.HOLDOUT_BOUNDARY + timedelta(days=1)
    with pytest.raises(gates.PreregGateRefusal, match="G-6.*holdout"):
        gates.check_decision_in_era(beyond)


def test_g6_refuses_a_pre_era_decision():
    before = prereg.REPLAY_ERA_START - timedelta(days=1)
    with pytest.raises(gates.PreregGateRefusal, match="G-6.*predates"):
        gates.check_decision_in_era(before)


def test_g6_boundary_is_inclusive_on_the_test_side_and_exclusive_beyond():
    """The boundary cannot slide: the named date is IN, the next day is OUT."""
    gates.check_decision_in_era(prereg.HOLDOUT_BOUNDARY)
    with pytest.raises(gates.PreregGateRefusal):
        gates.check_decision_in_era(prereg.HOLDOUT_BOUNDARY + timedelta(days=1))


# =========================================================================== #
# run_all — ordering and the shipped all-refuse state
# =========================================================================== #
def test_run_all_refuses_today_on_g1_first():
    """Order matters: the FIRST refusal a reader sees names the actual blocker."""
    with pytest.raises(gates.PreregGateRefusal, match="^G-1"):
        gates.run_all(doc_bytes=_doc_bytes(),
                      is_ancestor_of_head=lambda _s: True,
                      ledger_lines=_good_ledger(),
                      live_hashes=_good_hashes(),
                      f1_refuses=lambda: True,
                      staging_report=_good_staging())


def test_run_all_passes_end_to_end_when_every_input_is_correct(monkeypatch):
    """THE NON-VACUITY PROOF for the whole gate battery.

    With the identity constants stamped and every injected input correct, all
    five gates return receipts.  Without this test the suite above would be
    satisfied by a ``run_all`` that raised unconditionally.
    """
    doc = _doc_bytes()
    monkeypatch.setattr(prereg, "PREREG_COMMIT", GOOD_COMMIT)
    monkeypatch.setattr(prereg, "PREREG_DOC_SHA256",
                        hashlib.sha256(gates.frozen_prefix(doc)).hexdigest())
    reason = (f"w5_prereg={prereg.PREREG_COMMIT}; "
              f"doc_sha256={prereg.PREREG_DOC_SHA256}; itemized §13")
    receipts = gates.run_all(
        doc_bytes=doc,
        is_ancestor_of_head=lambda _s: True,
        ledger_lines=[_other_family_line(), _budget_line(reason=reason)],
        live_hashes=_good_hashes(),
        f1_refuses=lambda: True,
        staging_report=_good_staging())
    assert [r.gate for r in receipts] == ["G-1", "G-2", "G-3", "G-4", "G-5"]
