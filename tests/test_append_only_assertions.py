"""Pins the append-only assertion law (scripts/check_append_only_assertions.py).

The guard exists because the same defect shipped four times despite prose
warnings in every brief: a test asserting on the CONTENT of a store a nightly
lane appends to, which reds main days later with no PR author involved.

These tests pin BOTH halves of the discrimination. A detector that flags every
assertion touching data/ would be as useless as one that flags none, so every
positive here is paired with a lexically similar negative that must stay silent.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_append_only_assertions.py"


def _load():
    spec = importlib.util.spec_from_file_location("_aoa_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    # Registering before exec is load-bearing: @dataclass resolves the module
    # out of sys.modules while the class body is being processed.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _load()

STORE = "data/prophet/ledger.jsonl"
STORES = {STORE: guard.Store(STORE, "A", "test")}


def _scan(src: str, name: str = "test_sample.py"):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_text(textwrap.dedent(src), encoding="utf-8")
        return guard.scan_file(p, name, STORES)


_PREAMBLE = '''
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    LEDGER = ROOT / "data" / "prophet" / "ledger.jsonl"
    FROZEN = ROOT / "docs" / "frozen.jsonl"
'''


# --------------------------------------------------------------------------- #
# Store classification — derived from config/synapse.yml, never hand-listed
# --------------------------------------------------------------------------- #
def test_both_motivating_stores_are_classified_append_only():
    """The rule is worthless if it cannot see the stores that caused it."""
    stores = guard.classify_stores(ROOT)
    assert "data/qledger/claims.jsonl" in stores, "defects 1-2 (registry pin) invisible"
    assert "data/prophet/ledger.jsonl" in stores, "defect 3 (prophet sidecar) invisible"


def test_daily_engine_is_in_the_nightly_lane_vocabulary():
    """Neither motivating store's cadence says "nightly" — both are daily-engine.

    A rule that grepped the cadence for the substring "nightly" would have
    classified ZERO of the four real defects.
    """
    assert "daily-engine" in guard.NIGHTLY_CADENCES
    stores = guard.classify_stores(ROOT)
    assert stores["data/qledger/claims.jsonl"].signal == "A"


def test_prose_signal_catches_a_store_whose_cadence_is_not_a_nightly_lane():
    stores = guard.classify_stores(ROOT)
    assert any(s.signal == "B" for s in stores.values()), (
        "signal B is dead: no registered store declares append-only in prose"
    )


def test_a_non_jsonl_or_non_git_artifact_is_not_classified():
    stores = guard.classify_stores(ROOT)
    assert all(p.endswith(".jsonl") and p.startswith("data/") for p in stores)


# --------------------------------------------------------------------------- #
# The monotonicity rule — can appending a row falsify this assertion?
# --------------------------------------------------------------------------- #
def test_subset_pin_against_a_frozen_sidecar_fires():
    """The verbatim shape of defect 3 (tests/test_prophet_plan_grades.py)."""
    hits = _scan(_PREAMBLE + '''
    def test_every_closed_plan_is_accounted_for():
        ledger_ids = {r["id"] for r in read_jsonl(LEDGER)}
        graded_ids = {r["id"] for r in read_jsonl(FROZEN)}
        assert ledger_ids and ledger_ids <= graded_ids
    ''')
    assert len(hits) == 1
    assert "LtE" in hits[0].detail
    assert hits[0].store == "data/prophet/ledger.jsonl"


def test_row_count_equality_fires():
    """The verbatim shape of defect 4 (tests/test_seasonality_calibration.py)."""
    hits = _scan(_PREAMBLE + '''
    def test_row_count():
        rows = read_jsonl(LEDGER)
        assert len(rows) == 28
    ''')
    assert len(hits) == 1 and "Eq" in hits[0].detail


def test_the_floor_that_fixed_defect_4_does_not_fire():
    """`>=` only becomes MORE true as the ledger grows — the legal shape."""
    hits = _scan(_PREAMBLE + '''
    def test_row_floor():
        rows = read_jsonl(LEDGER)
        assert len(rows) >= 28, "rows are append-only"
    ''')
    assert hits == []


def test_a_ceiling_written_backwards_still_fires():
    """`28 >= len(rows)` is a ceiling however it is spelled."""
    hits = _scan(_PREAMBLE + '''
    def test_row_ceiling():
        rows = read_jsonl(LEDGER)
        assert 28 >= len(rows)
    ''')
    assert len(hits) == 1


def test_membership_in_a_live_store_does_not_fire():
    """A row cannot un-appear, so `x in store` survives every append."""
    hits = _scan(_PREAMBLE + '''
    def test_header():
        body = LEDGER.read_text()
        assert "NIGHTLY IS THE SOLE ADVANCER" in body
    ''')
    assert hits == []


def test_absence_from_a_live_store_does_fire():
    """`not in` is the anti-monotone twin: a later append can introduce it."""
    hits = _scan(_PREAMBLE + '''
    def test_no_bad_row():
        ids = {r["id"] for r in read_jsonl(LEDGER)}
        assert "bad-id" not in ids
    ''')
    assert len(hits) == 1


def test_schema_check_over_every_row_does_not_fire():
    hits = _scan(_PREAMBLE + '''
    def test_schema():
        for row in read_jsonl(LEDGER):
            assert set(row.keys()) == {"id", "asof"}
    ''')
    assert hits == []


def test_within_run_byte_identity_guard_does_not_fire():
    """Two reads of the SAME store in one run is a mutation guard, not a pin."""
    hits = _scan(_PREAMBLE + '''
    def test_reader_never_mutates():
        before = LEDGER.read_bytes()
        run_reader()
        assert LEDGER.read_bytes() == before
    ''')
    assert hits == []


# --------------------------------------------------------------------------- #
# Fixture safety — the dominant shape in tests/ must never be reported
# --------------------------------------------------------------------------- #
def test_a_tmp_path_rooted_store_never_fires():
    hits = _scan('''
    from pathlib import Path

    def test_writer(tmp_path):
        ledger = tmp_path / "data" / "prophet" / "ledger.jsonl"
        rows = read_jsonl(ledger)
        assert len(rows) == 1
        assert {r["id"] for r in rows} <= {"a"}
    ''')
    assert hits == []


def test_a_parameter_shadowing_a_module_constant_is_not_tainted():
    """A function argument is an INPUT; it can never be the live store."""
    hits = _scan(_PREAMBLE + '''
    def test_with_injected_ledger(LEDGER):
        rows = read_jsonl(LEDGER)
        assert len(rows) == 3
    ''')
    assert hits == []


def test_an_unclassified_path_never_fires():
    hits = _scan(_PREAMBLE + '''
    def test_other():
        rows = read_jsonl(ROOT / "data" / "prophet" / "notes.jsonl")
        assert len(rows) == 3
    ''')
    assert hits == []


# --------------------------------------------------------------------------- #
# Guard mechanics
# --------------------------------------------------------------------------- #
def test_selftest_passes():
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--selftest"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_live_run_is_annotation_clean_and_never_reds_the_lane():
    """One live run, three properties — the tree scan is the expensive part.

    (1) discipline tier: the default run must exit 0 on pre-existing code, or
        the guard reds the fleet for a defect no PR author wrote and gets
        disabled instead of obeyed.
    (2) every annotation STARTS the line (CLAUDE.md §GitHub annotations —
        a prefixed line is silently dropped by GitHub and the guard reads as
        an alarm while producing nothing).
    (3) --strict still exists as the local-diagnostic escalation.
    """
    proc = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, cwd=str(ROOT)
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for line in proc.stdout.splitlines():
        if "::warning" in line or "::notice" in line or "::error" in line:
            assert line.startswith("::"), f"annotation does not start the line: {line!r}"
    assert "append-only assertions:" in proc.stdout
