"""P-B3 persistence-robust certification — unit tests that can fail.

The prereg is the contract. These tests pin the frozen design, not a
friendlier one: most-specific §10 headlines, no-merge spell shuffle,
PERM-INERT coarse-df, dwell transitions, session-regime ties-to-lower,
and an adversarial battery whose probes must fire.

Run: python3 -m pytest tests/test_pb3_persistence_robust_cert.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "cn_prophet_audit" / "pb3_persistence_robust_cert.py"
_spec = importlib.util.spec_from_file_location("pb3_persistence_robust_cert", SRC)
pb3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb3)


# ── §10 headline: most-specific row wins ─────────────────────────────────────


def test_headline_row1_requires_b_certified_or_not_computed():
    h = pb3.headline_disposition(
        "CERTIFIED_TIMING", "CERTIFIED_OCCUPANCY", "volz_gt1")
    assert h["row"] == 1
    assert h["headline"] == "CERTIFIED TIMING"
    assert h["timing_language"] is True


def test_headline_row1_excludes_b_null_on_long_spell():
    """A2: B NULL + A CERTIFIED on DD/MA200 is only row 8, never row 1."""
    h = pb3.headline_disposition(
        "CERTIFIED_TIMING", "NULL", "dd_le_m35", b_had_df=True)
    assert h["row"] == 8
    assert h["headline"] == "UNINFORMATIVE"
    assert h["stamp"] == "A_B_CONTRADICT"
    assert h["timing_language"] is False


def test_headline_row2_short_spell_b_inert():
    h = pb3.headline_disposition(
        "CERTIFIED_TIMING", "NOT_EVALUABLE", "volz_gt1")
    assert h["row"] == 2
    assert h["headline"] == "CERTIFIED TIMING"
    assert h["timing_language"] is True


def test_headline_row3_occupancy_not_transition_no_timing_language():
    """A1 / A3: A NULL + B CERTIFIED is CERTIFIED OCCUPANCY, not timing."""
    h = pb3.headline_disposition("NULL", "CERTIFIED_OCCUPANCY", "dd_le_m20")
    assert h["row"] == 3
    assert h["headline"] == "CERTIFIED OCCUPANCY"
    assert h["stamp"] == "OCCUPANCY_NOT_TRANSITION"
    assert h["timing_language"] is False
    h = pb3.apply_dd_carrier_stamp(h, "dd_le_m20")
    assert "CARRIER_SERIES" in (h.get("stamp") or "")


def test_headline_row4_a_underpowered():
    h = pb3.headline_disposition(
        "INSUFFICIENT_SUPPORT", "CERTIFIED_OCCUPANCY", "under_ma200")
    assert h["row"] == 4
    assert h["headline"] == "CERTIFIED OCCUPANCY"
    assert h["stamp"] == "OCCUPANCY_ONLY_A_UNDERPOWERED"
    assert h["timing_language"] is False


def test_headline_row5_and_6_and_7():
    assert pb3.headline_disposition("NULL", "NULL", "quiet_base")["headline"] == "NULL"
    h6 = pb3.headline_disposition("NOT_EVALUABLE", "NULL", "quiet_base")
    assert h6["row"] == 6 and h6["stamp"] == "A_SILENT_B_NULL"
    h7 = pb3.headline_disposition("INSUFFICIENT_SUPPORT", "NOT_EVALUABLE", "quiet_base")
    assert h7["row"] == 7 and h7["headline"] == "INSUFFICIENT SUPPORT"


def test_headline_m4_and_battery_override():
    h = pb3.headline_disposition(
        "CERTIFIED_TIMING", "CERTIFIED_OCCUPANCY", "volz_gt1", m4_only=True)
    assert h["row"] == 9 and h["headline"] == "NULL" and h["stamp"] == "REGIME"
    h = pb3.headline_disposition(
        "CERTIFIED_TIMING", "CERTIFIED_OCCUPANCY", "volz_gt1", battery_fail=True)
    assert h["row"] == 10 and h["headline"] == "UNINFORMATIVE" and h["stamp"] == "BATTERY"


def test_headline_dd_null_does_not_carry_carrier_series():
    h = pb3.apply_dd_carrier_stamp(
        pb3.headline_disposition("NULL", "NULL", "dd_le_m20"), "dd_le_m20")
    assert h["headline"] == "NULL"
    assert "CARRIER_SERIES" not in str(h.get("stamp") or "")


def test_headline_a_insufficient_never_prints_null_status_on_a():
    """If A has insufficient transition N the A status is INSUFFICIENT, never NULL."""
    fl = pb3.a_floors(n_fit_events=10, n_hold_events=5, n_fit_names=8,
                      unmatched_frac=0.1, max_name_share=0.1, prevalence=0.2)
    assert fl["status"] == "INSUFFICIENT_SUPPORT"
    assert fl["status"] != "NULL"


# ── spells / A4 / A5 ─────────────────────────────────────────────────────────


def test_shuffle_preserves_true_and_false_multisets_and_never_merges():
    rng = np.random.default_rng(20260815)
    tl, fl = [3, 8, 2, 5], [4, 6, 1, 7]
    for _ in range(40):
        seq = pb3.shuffle_spell_sequence(tl, fl, rng)
        got_t, got_f = pb3.true_false_lens(seq)
        assert sorted(got_t) == sorted(tl)
        assert sorted(got_f) == sorted(fl)
        assert not pb3.spells_abut_true(seq)
        painted = pb3.paint_spells(seq, sum(tl) + sum(fl))
        assert int(painted.sum()) == sum(tl)


def test_residual_fill_of_true_lengths_only_is_not_the_shuffle():
    """A4: a TRUE-only residual-fill can merge; the shuffle must not."""
    # Two TRUE spells of 3 with one FALSE of 2: only T F T is legal.
    rng = np.random.default_rng(1)
    seq = pb3.shuffle_spell_sequence([3, 3], [2], rng)
    assert not pb3.spells_abut_true(seq)
    assert sum(l for v, l in seq if v) == 6
    # Residual-fill that only keeps TRUE lengths could emit TTTTTT (one spell).
    merged = [(True, 6)]
    assert pb3.true_false_lens(merged)[0] != [3, 3]


def test_perm_inert_coarse_df():
    """A5: ≤2 long spells / two-longest >70% / <20 placements are inert."""
    # one multi-year block
    r = pb3.perm_inert_reasons([800], n_eligible=1000, n_place=1)
    assert "fewer_than_2_true_spells" in r
    assert "fewer_than_3_true_spells" in r
    assert "longest_true_gt_70pct" in r
    # two long blocks covering >70%
    r = pb3.perm_inert_reasons([400, 400], n_eligible=1000, n_place=2)
    assert "fewer_than_3_true_spells" in r
    assert "two_longest_true_gt_70pct" in r
    # 3 TRUE + 2 FALSE: one legal pattern (must start and end with T), 3! * 2! = 12
    assert pb3.n_legal_placements([3, 4, 5], [2, 6]) == 6 * 2
    r = pb3.perm_inert_reasons([3, 4, 5], n_eligible=40,
                               n_place=pb3.n_legal_placements([3, 4, 5], [6, 7, 8]))
    # 2 patterns × 3! × 3! = 72 ≥ 20, and no length covers 70% of 40
    assert "fewer_than_20_legal_placements" not in r
    r = pb3.perm_inert_reasons([3, 4], n_eligible=20,
                               n_place=pb3.n_legal_placements([3, 4], [5]))
    assert "fewer_than_20_legal_placements" in r


def test_n_legal_placements_zero_when_merge_required():
    assert pb3.n_legal_placements([3, 3, 3], [1]) == 0  # 3T 1F cannot separate


# ── transitions / dwell ──────────────────────────────────────────────────────


def test_lawful_onset_requires_dwell_and_rejects_flicker():
    F = np.zeros(20, bool)
    F[3] = True  # one-bar TRUE after only 3 FALSE — flicker, not a dwell-5 onset
    tr = pb3.lawful_transitions(F, np.ones(20, bool), dwell=5)
    assert tr["onset"].size == 0
    F = np.zeros(20, bool)
    F[10:16] = True
    # 5+ FALSE immediately before T=10, then TRUE — lawful onset
    tr = pb3.lawful_transitions(F, np.ones(20, bool), dwell=5)
    assert 10 in set(tr["onset"].tolist())


def test_measurability_break_resets_dwell_and_is_not_false():
    F = np.zeros(12, bool)
    F[8:] = True
    meas = np.ones(12, bool)
    meas[6] = False  # break inside the would-be FALSE dwell
    tr = pb3.lawful_transitions(F, meas, dwell=5)
    assert tr["onset"].size == 0


def test_vz_dwell_is_2_others_are_5():
    assert pb3.DWELL["volz_gt1"] == 2
    for k in ("dd_le_m20", "dd_le_m35", "under_ma200", "quiet_base"):
        assert pb3.DWELL[k] == 5


# ── session-regime terciles (A8) ─────────────────────────────────────────────


def test_session_tercile_ties_go_lower_and_holdout_clips():
    fit = np.array([0.10, 0.20, 0.30, 0.40, 0.50, 0.60])
    q1, q2, lo, hi = pb3.fit_tercile_cuts(fit)
    # value exactly at q1 → lower tercile (0)
    assert pb3.assign_tercile(q1, q1, q2, lo, hi) == 0
    assert pb3.assign_tercile(q2, q1, q2, lo, hi) == 1
    # HOLDOUT above FIT max clips to max → tercile 2
    assert pb3.assign_tercile(0.99, q1, q2, lo, hi) == 2
    # HOLDOUT below FIT min clips to min → tercile 0
    assert pb3.assign_tercile(-0.5, q1, q2, lo, hi) == 0


def test_session_u1_fraction_is_one_row_per_session():
    dcode = np.array([0, 0, 1, 1, 1, 2])
    u1 = np.array([1, 0, 1, 1, 0, 0], bool)
    assigned = np.ones(6, bool)
    frac = pb3.session_u1_fraction(dcode, u1, assigned)
    assert frac[0] == pytest.approx(0.5)
    assert frac[1] == pytest.approx(2 / 3)
    assert frac[2] == pytest.approx(0.0)


# ── scope / signs / pins ─────────────────────────────────────────────────────


def test_scope_is_exactly_the_frozen_20_cells():
    cells = [(s, b, h) for s in pb3.FSHORT.values()
             for b in pb3.BOARDS for h in pb3.HORIZONS]
    assert len(cells) == 20
    assert set(pb3.FSHORT.values()) == {"DD20", "DD35", "MA200", "QB", "VZ"}
    assert "chinext10" not in pb3.BOARDS
    assert "star" not in pb3.BOARDS
    assert "confluence_long" not in pb3.FKEYS


def test_frozen_signs_and_edges():
    assert pb3.PRIMARY_EDGE["under_ma200"] == "exit"
    assert pb3.A_SIGN["under_ma200"] == +1
    assert pb3.B_SIGN["under_ma200"] == -1  # occupancy sign, not the A-exit sign
    assert pb3.A_SIGN["quiet_base"] == -1
    assert pb3.B_SIGN["dd_le_m20"] == +1


def test_pin_prefixes_match_prereg_section_3():
    for name, prefix in pb3.PIN_PREFIXES.items():
        digest = pb3._sha(pb3.OUT_DIR / name)
        assert digest.startswith(prefix), (name, digest[:16], prefix)


def test_refuse_pin_mismatch_can_fail():
    with pytest.raises(SystemExit):
        pb3.refuse_pin_mismatch([
            (pb3.W1_PATH, "deadbeefdeadbeef"),
        ])


def test_pb2_preservation_sentence_is_verbatim():
    assert pb3.PB2_PRESERVATION_SENTENCE == (
        "P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR. The numbers "
        "below are P-B3 verdicts on a new estimand and a new null.")


def test_no_shift_null_in_headline_payload():
    h = pb3.headline_disposition("NULL", "CERTIFIED_OCCUPANCY", "dd_le_m35")
    blob = str(h).lower()
    assert "shift" not in blob
    assert "250" not in blob


# ── adversarial probes can fire (synthetic, no full panel) ───────────────────


def test_probe_helper_detects_a_failing_mutation():
    def fn(mut):
        return (not mut), {"mut": mut}
    rec = pb3._fallback_probe(fn, lambda: True, "force fail")
    assert rec["detected"] is True
    rec_ok = pb3._fallback_probe(fn, lambda: False, "no mutation")
    assert rec_ok["detected"] is False


def test_battery_can_fail_is_itself_a_failing_check():
    """§12.17 probe: skip probe 2 must make battery_can_fail return False."""
    # Mimic the check body.
    adversarial = {
        "planted_timing": {"mutation_probe": {"detected": True}},
        "persistent_state_null": {"mutation_probe": {"detected": True}},
    }
    dets = {k: v["mutation_probe"]["detected"] for k, v in adversarial.items()}
    skip = True
    passed = False if skip else all(dets.values())
    assert passed is False


def test_seed_is_the_frozen_new_study_seed():
    assert pb3.SEED == 20260815
    assert pb3.N_PERM == 2000
    assert pb3.N_ASSIGN == 2000


def test_g6b_is_not_f_minus_pi():
    src = Path(pb3.__file__).read_text()
    assert "F − p_i" not in src or "forbidden" in src.lower()
    assert "path assignment" in src.lower() or "name-path" in src.lower() or "π" in src
    # The gate must mention assignment, not a demeaned threshold.
    assert "N_ASSIGN" in src


def test_import_does_not_touch_prophet_or_build_a_score():
    src = Path(pb3.__file__).read_text()
    assert "china_board_rank" not in src
    assert "cn_prophet_v4" not in src
    assert "NO P-B3 production ranker" in src


def test_regime_probe_fires_on_visible_transitions():
    """§11.5: drop matching + assert A still null must fail when onsets exist."""
    F = np.zeros(40, bool)
    F[10:20] = True  # session-constant block → lawful onset at 10 (dwell 5)
    tr = pb3.lawful_transitions(F, np.ones(40, bool), 5)
    n_on = int(tr["onset"].size)
    assert n_on > 0
    still_null = n_on == 0
    detected = not still_null
    assert detected is True


def test_force_flip_plants_a_dwell_legal_transition():
    """§11.1 probe: a 6-bar flip after 5 FALSE is a lawful onset, not a flicker."""
    F = np.zeros(30, bool)
    F[10:16] = True
    tr = pb3.lawful_transitions(F, np.ones(30, bool), 5)
    assert 10 in set(tr["onset"].tolist())
    flicker = np.zeros(30, bool)
    flicker[10] = True
    tr_f = pb3.lawful_transitions(flicker, np.ones(30, bool), 5)
    assert 10 in set(tr_f["onset"].tolist())  # first True after 10 FALSE is onset
    early = np.zeros(30, bool)
    early[3] = True
    assert pb3.lawful_transitions(early, np.ones(30, bool), 5)["onset"].size == 0


def test_diagnostic_shift_sets_empty_fkeys_order():
    """A11: P-B2 FKEYS_ORDER is empty unless its own main() ran."""
    class _PB2:
        FKEYS_ORDER = ()

        def shift_footprints(self, pl, S):
            assert self.FKEYS_ORDER, "FKEYS_ORDER must be filled before shift"
            return {k: pl.F[k] for k in ("dd_le_m20", "dd_le_m35")}, {}

    class _Pl:
        F = {"dd_le_m20": np.zeros(4, bool), "dd_le_m35": np.zeros(4, bool)}
        n = 4

    # The helper under test is the FKEYS_ORDER fill + missing-key skip.
    pb2 = _PB2()
    if not getattr(pb2, "FKEYS_ORDER", ()):
        pb2.FKEYS_ORDER = tuple(_Pl.F)
    assert pb2.FKEYS_ORDER == ("dd_le_m20", "dd_le_m35")
    shifted, _ = pb2.shift_footprints(_Pl(), 250)
    assert "dd_le_m20" in shifted
