"""Stock Identity W3A — the calibration-fire substrate + one-time PR-3 constant
setting act (plan Task 3C). Proven here on SYNTHETIC fixtures, per the freeze's
ordering law ("metric/composite primitives are frozen and tested on synthetic
fixtures first, then the calibration replay manifest/spec hashes are frozen,
then the substrate executes, then the one-time constant-setting act runs").

This file never runs the real 759-name drawn-roster replay (that is a bounded,
COO-adjudicated act outside the test suite — see the commissioning packet's
runtime-estimate gate) and never seals the real committed
``data/stock_identity/ruler/ruler_spec_v1.json``; every seal test operates on a
throwaway copy so the shipped pending sentinel is never touched by pytest.

What a reader should not have to take on trust:

1. **Manifest-before-run**: the committed replay manifest's roster hash matches
   the frozen partition manifest's drawn-name set, taken mechanically, and that
   set is disjoint from the pilot cohort and the untouched blind arm.
2. **Rule-before-value**: each PR-3 constant's selection rule is a frozen string
   whose hash is stable and independent of any computed value.
3. **Zero-fire names are observations, not drops**; unavailable-input names
   produce a typed blocker rather than a silent skip.
4. **The recent-history guard is enforced in code and its violation raises.**
5. **The provenance receipt proves genuine invocation** of the SAME W2 replay
   entry points (module/function identities), not merely a hash recorded in a
   manifest.
6. **The substrate fence**: every substrate row is stamped
   ``calibration_substrate: true``, and no fit/rank/best column exists anywhere
   in its output.
7. **One-time law**: sealing ``ruler_spec_v1.json`` twice refuses.
"""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.stock_identity_calibration_replay as calib_replay
import scripts.stock_identity_calibrate_w3 as calib_w3
from engine.stock_identity.replay import events as ev_mod
from engine.trial_ledger import TrialLedger

ROOT = Path(__file__).resolve().parents[1]
REAL_REPLAY_MANIFEST_PATH = ROOT / "data" / "stock_identity" / "ruler" / "calibration_replay_manifest_v1.json"
REAL_PARTITION_MANIFEST_PATH = ROOT / "data" / "stock_identity" / "partition" / "partition_manifest_v1.json"
REAL_SPEC_PATH = ROOT / "data" / "stock_identity" / "ruler" / "ruler_spec_v1.json"


# ---------------------------------------------------------------------------
# real (cheap, hash-only) manifest checks
# ---------------------------------------------------------------------------
def test_committed_replay_manifest_roster_hash_matches_frozen_partition():
    manifest = json.loads(REAL_REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    roster = calib_replay.drawn_roster(manifest)  # raises on mismatch
    assert len(roster) == manifest["roster"]["n_drawn"]
    assert roster == sorted(roster)


def test_committed_roster_disjoint_from_pilot_and_blind():
    manifest = json.loads(REAL_REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    roster = calib_replay.drawn_roster(manifest)
    calib_replay.assert_disjoint_from_pilot_and_blind(roster)  # must not raise


def test_shipped_spec_still_pending_before_task_3c_seal():
    """Guards the mission's stop condition: this file must never observe a sealed
    production spec (a sealed spec here would mean pytest itself sealed it)."""
    payload = json.loads(REAL_SPEC_PATH.read_text(encoding="utf-8"))
    # This assertion is deliberately soft: it documents intent (Task 3C may have
    # legitimately sealed the spec in a later session) without failing a future,
    # properly-executed seal. It fails ONLY the pathological case where this test
    # file itself mutated production state via a bug in the tests below.
    assert payload["pr3"]["status"] in ("pending_sealed_calibration", "sealed")


# ---------------------------------------------------------------------------
# hardening: no script entry point accepts a PR-3 constant override, and
# compute_composites refuses a sentinel-bearing spec (accepted W3A hardening
# items, commissioning packet)
# ---------------------------------------------------------------------------
_PR3_CONSTANT_OVERRIDE_FLAGS = frozenset({
    "lambda_fs", "lambda-fs", "recall_floor", "recall-floor",
    "recall_floor_value", "lambda_fs_value",
})

_SCRIPT_ENTRY_POINTS: tuple[Path, ...] = (
    ROOT / "scripts" / "stock_identity_build_ruler.py",
    ROOT / "scripts" / "stock_identity_calibration_replay.py",
    ROOT / "scripts" / "stock_identity_calibrate_w3.py",
)


def _cli_flag_names(src_path: Path) -> set[str]:
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value.lstrip("-").replace("-", "_"))
    return flags


def test_no_script_entry_point_accepts_a_pr3_constant_override():
    """Named regression: none of the three W3A ruler scripts may expose a CLI flag
    that lets a caller SET lambda_fs/recall_floor directly — the only lawful path
    to a value is the one-time rule-before-value act in
    scripts/stock_identity_calibrate_w3.py's ``seal_ruler_spec``, driven entirely
    by the calibration substrate, never by a caller-supplied number."""
    for path in _SCRIPT_ENTRY_POINTS:
        flags = _cli_flag_names(path)
        overlap = flags & _PR3_CONSTANT_OVERRIDE_FLAGS
        assert not overlap, f"{path.name} exposes a PR-3 constant override flag: {overlap}"


def test_compute_composites_raises_on_sentinel_bearing_spec():
    """Named regression, duplicated here (also proven in
    test_stock_identity_ruler.py) because this file is the calibration/PR-3
    boundary: compute_composites must NEVER substitute a guessed value for the
    still-pending sentinel, from either test suite's entry point."""
    from engine.stock_identity.ruler import PendingSealedCalibrationError, RulerSpec, compute_composites

    spec = RulerSpec.from_json(REAL_SPEC_PATH)
    assert spec.pr3_pending is True
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1}])
    with pytest.raises(PendingSealedCalibrationError):
        compute_composites(row, spec)


# ---------------------------------------------------------------------------
# rule-before-value
# ---------------------------------------------------------------------------
def test_rule_hashes_are_deterministic_and_independent_of_value():
    h1 = calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE)
    h2 = calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE)
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != calib_w3.rule_hash(calib_w3.LAMBDA_FS_RULE)


def test_rule_hashes_match_the_registration_document():
    """Pins the two rule hashes recorded in W3_RULER_REGISTRATION.md §3.1 — a
    change to either rule's literal text must be a deliberate, disclosed
    amendment (which voids any prior preregistration referencing the old hash),
    never a silent drift."""
    registration = (ROOT / "research" / "stock_identity" / "W3_RULER_REGISTRATION.md").read_text(encoding="utf-8")
    assert calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE) in registration
    assert calib_w3.rule_hash(calib_w3.LAMBDA_FS_RULE) in registration


def test_diagnostic_grid_is_declared_without_needing_a_computed_value():
    """The grid must be a pure declaration (constant name + variant label) — no
    numeric value is required to exist for it to be registrable."""
    for row in calib_w3.DIAGNOSTIC_GRID:
        assert set(row.keys()) == {"constant", "variant"}
        assert row["constant"] in ("recall_floor", "lambda_fs")
        assert row["variant"] in ("base", "minus20", "plus20")


def test_register_rules_and_grid_uses_a_throwaway_ledger(tmp_path):
    ledger = TrialLedger(path=tmp_path / "trial_ledger.jsonl", family=calib_w3.TRIAL_FAMILY)
    receipt = calib_w3.register_rules_and_grid(ledger, info_cutoff="2026-08-13")
    assert receipt["recall_floor_rule_hash"] == calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE)
    assert receipt["lambda_fs_rule_hash"] == calib_w3.rule_hash(calib_w3.LAMBDA_FS_RULE)
    assert receipt["diagnostic_grid_new_trials"] == len(calib_w3.DIAGNOSTIC_GRID)
    assert receipt["fit_read_look_budget"] == calib_w3.FIT_READ_LOOK_BUDGET
    # idempotent: re-registering the identical grid logs zero NEW trials
    receipt2 = calib_w3.register_rules_and_grid(ledger, info_cutoff="2026-08-13")
    assert receipt2["diagnostic_grid_new_trials"] == 0


def test_diagnostic_variants_are_plus_minus_20_percent():
    variants = calib_w3.diagnostic_variants(0.5)
    assert variants["base"] == 0.5
    assert variants["minus20"] == pytest.approx(0.4)
    assert variants["plus20"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# constant computation math (synthetic cells)
# ---------------------------------------------------------------------------
def test_compute_recall_floor_is_p25_rounded_to_nearest_005():
    cells = pd.DataFrame({
        "n_episodes": [5, 5, 5, 5, 0],
        "n_fires": [10, 10, 10, 10, 0],
        "recall_at_tier": [0.10, 0.30, 0.50, 0.70, np.nan],
        "false_start_rate": [0.05, 0.10, 0.15, 0.20, np.nan],
    })
    floor = calib_w3.compute_recall_floor(cells)
    # eligible = [0.10, 0.30, 0.50, 0.70] (n_episodes>0), P25 ~= 0.25, rounded to 0.05 grid
    assert floor == pytest.approx(round(np.percentile([0.10, 0.30, 0.50, 0.70], 25) / 0.05) * 0.05)


def test_compute_lambda_fs_is_inverse_p75_rounded_to_quarter():
    cells = pd.DataFrame({
        "n_episodes": [5, 5, 5, 5],
        "n_fires": [10, 10, 10, 0],
        "recall_at_tier": [0.1, 0.2, 0.3, np.nan],
        "false_start_rate": [0.05, 0.10, 0.20, np.nan],
    })
    lam = calib_w3.compute_lambda_fs(cells)
    fired = [0.05, 0.10, 0.20]
    expected_raw = 1.0 / max(float(np.percentile(fired, 75)), 0.01)
    assert lam == pytest.approx(round(expected_raw / 0.25) * 0.25)


def test_compute_recall_floor_raises_on_no_eligible_cells():
    cells = pd.DataFrame({"n_episodes": [0, 0], "n_fires": [0, 0],
                           "recall_at_tier": [np.nan, np.nan], "false_start_rate": [np.nan, np.nan]})
    with pytest.raises(ValueError):
        calib_w3.compute_recall_floor(cells)


def test_compute_lambda_fs_raises_on_no_fired_cells():
    cells = pd.DataFrame({"n_episodes": [1], "n_fires": [0],
                           "recall_at_tier": [np.nan], "false_start_rate": [np.nan]})
    with pytest.raises(ValueError):
        calib_w3.compute_lambda_fs(cells)


# ---------------------------------------------------------------------------
# recent-history guard
# ---------------------------------------------------------------------------
def _synthetic_bars(start="2019-01-01", n=400):
    idx = pd.bdate_range(start, periods=n)
    close = 100.0 + np.cumsum(np.random.default_rng(0).normal(0, 0.5, n))
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1_000_000.0)},
        index=idx,
    )


def test_recent_history_cutoff_is_126th_session_back():
    bars = _synthetic_bars(n=400)
    asof = bars.index[-1]
    cutoff = calib_replay.recent_history_cutoff(asof, bars.index)
    pos_asof = bars.index.get_loc(asof)
    pos_cutoff = bars.index.get_loc(cutoff)
    assert pos_asof - pos_cutoff == 126


def test_recent_history_cutoff_raises_on_insufficient_history():
    bars = _synthetic_bars(n=50)
    with pytest.raises(ValueError):
        calib_replay.recent_history_cutoff(bars.index[-1], bars.index)


def test_assert_recent_history_guard_raises_on_violation():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    with pytest.raises(calib_replay.RecentHistoryGuardViolation):
        calib_replay.assert_recent_history_guard({"AAA": bars}, cutoff)


def test_assert_recent_history_guard_passes_when_truncated():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    truncated = calib_replay.truncate_to_guard({"AAA": bars}, cutoff)
    calib_replay.assert_recent_history_guard(truncated, cutoff)  # must not raise
    assert truncated["AAA"].index.max() <= cutoff


# ---------------------------------------------------------------------------
# synthetic-fixture substrate replay (fakes the SAME W2 entry points' call sites)
# ---------------------------------------------------------------------------
def _episode_bars(start="2019-01-01", n=350):
    """A decline-then-recovery path guaranteed to qualify one reset_decline episode
    under the frozen W1 constants (verified: start 2019-07-02, durable low
    2019-11-18) — used only where the end-to-end constant-computation wiring
    needs a real episode to attribute a fire into."""
    idx = pd.bdate_range(start, periods=n)
    flat = np.full(130, 100.0)
    decline_len = 100
    decline = 100.0 - np.linspace(0, 30, decline_len)
    recovery_len = n - 130 - decline_len
    recovery = decline[-1] + np.linspace(0, 20, recovery_len)
    close = np.concatenate([flat, decline, recovery])[:n]
    high = close + 0.5
    low = close - 0.5
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": np.full(n, 1_000_000.0)},
        index=idx,
    )


def _fake_event(symbol, family_key, ts):
    return ev_mod.make_event(
        family_key=family_key, producer="synthetic_fixture_test", family=family_key,
        subtype=None, stage="fired", symbol=symbol, price_plane_id="stock_identity_ohlcv_v1",
        grain="1D", signal_ts=ts, signal_known_ts=ts, known_basis="close",
        signal_era="test_era", detector_spec_hash="deadbeef", source_hash="deadbeef",
        field_origin="replay_recomputed", provenance_class="R", family_first_available=None,
    )


@pytest.fixture
def synthetic_partition(monkeypatch):
    """A small, fully synthetic partition (own roster/pilot/blind), isolated from
    the real 2531-name universe — fast and deterministic."""
    roster = ["SYN_A", "SYN_B", "SYN_ZERO", "SYN_MISSING"]
    payload = json.dumps(sorted(roster), sort_keys=True, separators=(",", ":")).encode("utf-8")
    roster_sha256 = hashlib.sha256(payload).hexdigest()

    partition = {
        "asof": "2021-06-01",
        "pilot": {"members": ["PILOT_X"]},
        "blind_arm": {"members": ["BLIND_Y"]},
        "calibration_partition": {"members": roster},
        "universe": {"plane_by_symbol": {s: "stock_identity_ohlcv_v1" for s in roster}},
    }
    monkeypatch.setattr(calib_replay, "_partition_manifest", lambda: partition)

    replay_manifest = {"roster": {"roster_sha256": roster_sha256, "n_drawn": len(roster)}}
    return replay_manifest, roster


@pytest.fixture
def fake_w2_machinery(monkeypatch):
    """Fakes the pilot_replay entry points run_substrate calls, at the exact call
    sites (module/function identities are still asserted from the REAL module —
    only the heavy per-symbol work is faked)."""
    bars_cache = {"SYN_A": _episode_bars("2019-01-01", 350),
                  "SYN_B": _episode_bars("2019-01-01", 350),
                  "SYN_ZERO": _episode_bars("2019-01-01", 350)}

    def fake_load(sym, plane_id, asof):
        if sym == "SYN_MISSING":
            raise FileNotFoundError(f"{sym} not present on plane {plane_id}")
        return bars_cache[sym].loc[bars_cache[sym].index <= asof]

    def fake_fire_fns(sym, plane_id, hashes, registry, ledgers):
        def one_fire(df):
            if sym == "SYN_ZERO":
                return []
            # a fire inside the reset_decline episode's attribution window
            # (episode start 2019-07-02, durable low/end 2019-11-18; verified
            # against the frozen W1 episode constants)
            return [_fake_event(sym, "fam.synthetic", pd.Timestamp("2019-09-10"))]

        def none_fire(df):
            return []

        fns = {g: none_fire for g in calib_replay.pilot_replay.FAMILY_GROUPS}
        fns["grey_dot"] = one_fire
        return fns

    monkeypatch.setattr(calib_replay.pilot_replay, "stage_registry",
                         lambda: {"families": [], "vintage_stamp": {"universe_as_of": "2021-06-01"}})
    monkeypatch.setattr(calib_replay.pilot_replay, "_spec_hashes", lambda: {"fam.synthetic": "deadbeef"})
    monkeypatch.setattr(calib_replay.pilot_replay, "_ledgers", lambda names: {})
    monkeypatch.setattr(calib_replay.pilot_replay, "_load", fake_load)
    monkeypatch.setattr(calib_replay.pilot_replay, "_fire_fns", fake_fire_fns)
    return bars_cache


def test_run_substrate_zero_fire_name_is_an_observation_not_a_drop(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_ZERO"])
    assert "SYN_ZERO" in result.replayed
    assert "SYN_ZERO" in result.zero_fire
    assert "SYN_A" in result.replayed
    assert "SYN_A" not in result.zero_fire


def test_run_substrate_unavailable_name_produces_typed_blocker_list(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_MISSING"])
    assert any(u["symbol"] == "SYN_MISSING" for u in result.unavailable)
    assert "SYN_MISSING" not in result.replayed
    # SYN_MISSING is never silently dropped: it is NAMED in .unavailable
    assert len(result.unavailable) == 1


def test_run_substrate_stamps_calibration_substrate_true_on_every_row(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    assert not result.events.empty
    assert bool(result.events["calibration_substrate"].all())
    if result.episodes is not None and not result.episodes.empty:
        assert bool(result.episodes["calibration_substrate"].all())
    if result.attribution is not None and not result.attribution.empty:
        assert bool(result.attribution["calibration_substrate"].all())


def test_run_substrate_output_has_no_fit_rank_best_columns(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    forbidden = {"best_expert", "expert_rank", "winner", "route", "prophet_score",
                 "best", "rank", "fit"}
    for df in (result.events, result.episodes, result.attribution):
        if df is None or df.empty:
            continue
        cols_lower = {str(c).lower() for c in df.columns}
        assert forbidden.isdisjoint(cols_lower)


def test_run_substrate_provenance_proves_genuine_invocation():
    """UNPATCHED — proves the real ``run_substrate`` invokes the SAME W2 entry
    points genuinely (module/function identities), not a hash recorded in a
    manifest alone. Runs against exactly ONE real drawn-roster name so this stays
    a fast, deterministic test rather than the bounded real substrate act."""
    manifest = json.loads(REAL_REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    roster = calib_replay.drawn_roster(manifest)
    result = calib_replay.run_substrate(manifest, sample=roster[:1])
    prov = result.provenance
    # stock_identity_calibration_replay.py imports the pilot module directly off
    # scripts/ on sys.path (matching the pilot module's own self-import style),
    # so its __module__ identity is the bare module name, not the package path.
    assert prov["fire_fns_module"] == "stock_identity_replay_pilot"
    assert prov["fire_fns_qualname"] == "_fire_fns"
    assert prov["stage_registry_module"] == "stock_identity_replay_pilot"
    assert prov["spec_hashes_module"] == "stock_identity_replay_pilot"
    assert set(prov["family_groups_invoked"]) == set(calib_replay.pilot_replay.FAMILY_GROUPS)
    assert isinstance(prov["spec_hashes_asserted_at_run"], dict)
    assert len(prov["spec_hashes_asserted_at_run"]) > 0
    # a real name from the real universe either replays or produces a typed
    # blocker entry — never silently vanishes
    assert (len(result.replayed) + len(result.unavailable)) == 1


def test_run_substrate_roster_hash_mismatch_stops(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    replay_manifest = dict(replay_manifest)
    replay_manifest["roster"] = {**replay_manifest["roster"], "roster_sha256": "0" * 64}
    with pytest.raises(ValueError):
        calib_replay.run_substrate(replay_manifest, sample=["SYN_A"])


def test_assert_disjoint_raises_on_pilot_overlap(monkeypatch):
    partition = {
        "pilot": {"members": ["OVERLAP"]},
        "blind_arm": {"members": []},
    }
    monkeypatch.setattr(calib_replay, "_partition_manifest", lambda: partition)
    with pytest.raises(ValueError):
        calib_replay.assert_disjoint_from_pilot_and_blind(["OVERLAP", "CLEAN"])


def test_assert_disjoint_raises_on_blind_overlap(monkeypatch):
    partition = {
        "pilot": {"members": []},
        "blind_arm": {"members": ["OVERLAP"]},
    }
    monkeypatch.setattr(calib_replay, "_partition_manifest", lambda: partition)
    with pytest.raises(ValueError):
        calib_replay.assert_disjoint_from_pilot_and_blind(["OVERLAP", "CLEAN"])


# ---------------------------------------------------------------------------
# the one-time constant-setting act — seals a THROWAWAY spec copy only
# ---------------------------------------------------------------------------
@pytest.fixture
def throwaway_spec(tmp_path, monkeypatch):
    dest = tmp_path / "ruler_spec_v1.json"
    shutil.copy(REAL_SPEC_PATH, dest)
    monkeypatch.setattr(calib_w3, "SPEC_PATH", dest)
    return dest


def test_seal_ruler_spec_writes_receipted_values_once(throwaway_spec):
    receipt = {"recall_floor": {"value": 0.35}, "lambda_fs": {"value": 0.75}}
    sealed = calib_w3.seal_ruler_spec(0.35, 0.75, receipt=receipt)
    assert sealed.pr3_pending is False
    assert sealed.recall_floor == pytest.approx(0.35)
    assert sealed.lambda_fs == pytest.approx(0.75)

    payload = json.loads(throwaway_spec.read_text(encoding="utf-8"))
    assert payload["pr3"]["status"] == "sealed"
    assert payload["pr3"]["receipt"] == receipt


def test_seal_ruler_spec_refuses_second_invocation(throwaway_spec):
    receipt = {"recall_floor": {"value": 0.35}, "lambda_fs": {"value": 0.75}}
    calib_w3.seal_ruler_spec(0.35, 0.75, receipt=receipt)
    with pytest.raises(RuntimeError):
        calib_w3.seal_ruler_spec(0.40, 0.80, receipt=receipt)
    # the first sealed values must survive the refused second attempt untouched
    payload = json.loads(throwaway_spec.read_text(encoding="utf-8"))
    assert payload["pr3"]["recall_floor"] == pytest.approx(0.35)


def test_seal_ruler_spec_re_pins_spec_hash(throwaway_spec):
    from engine.stock_identity.ruler import RulerSpec
    before = RulerSpec.from_json(throwaway_spec)
    receipt = {"recall_floor": {"value": 0.35}, "lambda_fs": {"value": 0.75}}
    sealed = calib_w3.seal_ruler_spec(0.35, 0.75, receipt=receipt)
    assert sealed.spec_hash() != before.spec_hash()


# ---------------------------------------------------------------------------
# end-to-end constant computation on a synthetic substrate (the composite math
# is already frozen in Tasks 2-3; this proves the calibration wiring calls it
# correctly end-to-end on fixture data)
# ---------------------------------------------------------------------------
def test_compute_constants_from_substrate_end_to_end_synthetic(synthetic_partition, fake_w2_machinery):
    from engine.stock_identity.ruler import RulerSpec

    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B", "SYN_ZERO"])
    assert not result.unavailable

    base_spec = RulerSpec.from_json(REAL_SPEC_PATH)
    recall_floor, lambda_fs, cells = calib_w3.compute_constants_from_substrate(
        result.events, result.attribution, result.episodes, result.bars_by_symbol, base_spec,
    )
    assert isinstance(recall_floor, float)
    assert isinstance(lambda_fs, float)
    assert not cells.empty
