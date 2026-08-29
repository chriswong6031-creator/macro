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
import os
import sys
import tempfile
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


def _pending_variant_of_real_spec_path(tmp_path: Path, name: str = "ruler_spec_v1.json") -> Path:
    """SI-W3A-RULER-V1 post-seal test repair: PR-3 sealed for real
    (SI-SEALED-CAL-P1, recall_floor=0.05, lambda_fs=0.000279297) on
    ``data/stock_identity/ruler/ruler_spec_v1.json`` on 2026-08-29, so this
    file's own pre-seal invariants (pending sentinel present, one-time seal
    law, hash re-pin, dry-run cleanliness) can no longer be exercised against
    the REAL committed file -- a straight copy of it now refuses immediately
    (``seal_ruler_spec`` raises "already sealed" on first call). Materialize a
    byte-identical COPY of the real spec in ``tmp_path`` with ONLY the ``pr3``
    block reset to its pre-seal ``pending_sealed_calibration`` state (verified
    against git rev 0b7442209a35, the commit immediately preceding the seal)
    so every pre-seal behavior stays live and mutation-killable, without ever
    touching the real committed file."""
    payload = json.loads(REAL_SPEC_PATH.read_text(encoding="utf-8"))
    payload["pr3"] = {
        "status": "pending_sealed_calibration",
        "recall_floor": None,
        "lambda_fs": None,
        "receipt": None,
        "note": (
            "The PR-3 ruler-composite constant family (lambda_fs, recall floor, "
            "any declared composite constants) is set exactly once by Task 3C "
            "from SI-SEALED-CAL-P1 under rule-before-value discipline. Until "
            "that one-time act runs, this block carries the explicit pending "
            "sentinel above -- never a guessed number. Fixture-only constants "
            "used to test the metric/composite MATH on synthetic data live only "
            "in test code and are never written here."
        ),
    }
    out_path = tmp_path / name
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return out_path


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


def test_compute_composites_raises_on_sentinel_bearing_spec(tmp_path):
    """Named regression, duplicated here (also proven in
    test_stock_identity_ruler.py) because this file is the calibration/PR-3
    boundary: compute_composites must NEVER substitute a guessed value for the
    still-pending sentinel, from either test suite's entry point.

    Pending-state branch: exercised against a restored fixture copy of the
    real spec, since PR-3's ONE-TIME SEAL (SI-SEALED-CAL-P1) means the real
    committed file is no longer pending and can no longer demonstrate this
    refusal itself -- see the sealed-state companion test below."""
    from engine.stock_identity.ruler import PendingSealedCalibrationError, RulerSpec, compute_composites

    spec = RulerSpec.from_json(_pending_variant_of_real_spec_path(tmp_path))
    assert spec.pr3_pending is True
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1}])
    with pytest.raises(PendingSealedCalibrationError):
        compute_composites(row, spec)


def test_compute_composites_succeeds_on_the_real_sealed_spec():
    """Sealed-state branch of the above: the real committed spec is sealed
    (SI-SEALED-CAL-P1, recall_floor=0.05, lambda_fs=0.000279297) so
    compute_composites must now actually compute on it instead of refusing."""
    from engine.stock_identity.ruler import RulerSpec, compute_composites

    spec = RulerSpec.from_json(REAL_SPEC_PATH)
    assert spec.pr3_pending is False
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
                          "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline",
                          "grain": "daily"}])
    out = compute_composites(row, spec)
    assert out.loc[0, "c_loc_r"] == pytest.approx(0.5 * 0.8 - spec.lambda_fs * 0.1)
    assert pd.notna(out.loc[0, "c_loc_d"])


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


def test_compute_lambda_fs_is_median_product_over_p75_false_start_rate():
    """Ruling 1(b): lambda_fs = median(recall_at_tier * zone_precision) /
    P75(false_start_rate), over the lawful (n_episodes>0) population, with NO
    rounding grid."""
    cells = pd.DataFrame({
        "n_episodes": [5, 5, 5, 5],
        "n_fires": [10, 10, 10, 0],
        "recall_at_tier": [0.1, 0.2, 0.3, np.nan],
        "zone_precision": [0.5, 0.6, 0.7, np.nan],
        "false_start_rate": [0.05, 0.10, 0.20, np.nan],
    })
    lam = calib_w3.compute_lambda_fs(cells)
    product = [0.1 * 0.5, 0.2 * 0.6, 0.3 * 0.7]
    fsr = [0.05, 0.10, 0.20]
    expected = float(np.median(product)) / float(np.percentile(fsr, 75, method="linear"))
    assert lam == pytest.approx(expected)


def test_compute_lambda_fs_rounds_nothing():
    """Ruling 1(b): the prior 'rounded to the nearest 0.25' step is GONE --
    lambda_fs is the exact quotient, deliberately NOT a multiple of 0.25."""
    cells = pd.DataFrame({
        "n_episodes": [3],
        "recall_at_tier": [0.4],
        "zone_precision": [0.5],
        "false_start_rate": [0.3],
    })
    lam = calib_w3.compute_lambda_fs(cells)
    expected_exact = (0.4 * 0.5) / 0.3  # ~0.6667, not a 0.25-grid value
    assert lam == pytest.approx(expected_exact)
    assert lam != pytest.approx(round(expected_exact / 0.25) * 0.25)


def test_compute_recall_floor_raises_on_no_eligible_cells():
    cells = pd.DataFrame({"n_episodes": [0, 0], "n_fires": [0, 0],
                           "recall_at_tier": [np.nan, np.nan], "false_start_rate": [np.nan, np.nan]})
    with pytest.raises(ValueError):
        calib_w3.compute_recall_floor(cells)


def test_compute_lambda_fs_raises_typed_blocked_degenerate_on_all_nan_population():
    """Ruling 1(b) fail-closed path: an all-NaN numerator AND denominator over
    the lawful population raises the typed BlockedDegenerateCalibrationError,
    never a bare ValueError -- and the error's receipt names the reason."""
    cells = pd.DataFrame({"n_episodes": [1], "n_fires": [0],
                           "recall_at_tier": [np.nan], "zone_precision": [np.nan],
                           "false_start_rate": [np.nan]})
    with pytest.raises(calib_w3.BlockedDegenerateCalibrationError) as excinfo:
        calib_w3.compute_lambda_fs(cells)
    assert not np.isfinite(excinfo.value.numerator)
    assert not np.isfinite(excinfo.value.denominator)
    receipt = excinfo.value.to_receipt()
    assert receipt["status"] == "BLOCKED_DEGENERATE_CALIBRATION"


def test_compute_lambda_fs_raises_typed_blocked_degenerate_on_zero_denominator():
    """Injecting a false_start_rate distribution whose P75 is exactly zero
    (denominator == 0, not merely NaN) must ALSO raise the typed blocker --
    the fail-closed gate requires STRICTLY greater than zero, not merely
    defined."""
    cells = pd.DataFrame({
        "n_episodes": [3, 3, 3],
        "recall_at_tier": [0.2, 0.3, 0.4],
        "zone_precision": [0.5, 0.5, 0.5],
        "false_start_rate": [0.0, 0.0, 0.0],
    })
    with pytest.raises(calib_w3.BlockedDegenerateCalibrationError) as excinfo:
        calib_w3.compute_lambda_fs(cells)
    assert excinfo.value.denominator == pytest.approx(0.0)


def test_compute_lambda_fs_raises_typed_blocked_degenerate_on_zero_numerator():
    """A numerator (median product) of exactly zero must ALSO raise the typed
    blocker -- zero is not > 0."""
    cells = pd.DataFrame({
        "n_episodes": [3, 3, 3],
        "recall_at_tier": [0.0, 0.0, 0.0],
        "zone_precision": [0.5, 0.5, 0.5],
        "false_start_rate": [0.1, 0.2, 0.3],
    })
    with pytest.raises(calib_w3.BlockedDegenerateCalibrationError) as excinfo:
        calib_w3.compute_lambda_fs(cells)
    assert excinfo.value.numerator == pytest.approx(0.0)


def test_compute_lambda_fs_never_applies_epsilon_clipping_or_fallback():
    """AST-level test (Ruling 1(b)): the rule path carries no epsilon,
    clipping, cap, alternate-quantile, or fallback-constant vocabulary that
    could rescue a degenerate numerator/denominator instead of refusing.

    The REAL guard against a rescue shape is the behavioral trio directly
    above this test
    (``test_compute_lambda_fs_raises_typed_blocked_degenerate_on_all_nan_population``,
    ``..._on_zero_denominator``, ``..._on_zero_numerator``) -- each feeds
    ``compute_lambda_fs`` a genuinely degenerate input and asserts the typed
    refusal fires; a rescue shape anywhere in the numerator/denominator path,
    however it were spelled, would make one of those three fail closed
    instead of raising. This test is a SECOND, static line of defense: an AST
    scan (not a plain-string grep) of ``compute_lambda_fs``'s own assignment
    statements that fails on any ``max``/``min``/``np.maximum``/
    ``np.minimum``/``np.clip`` call feeding an assignment to ``numerator`` or
    ``denominator`` -- including a rescue call wrapped around the RAW
    expression before it is ever bound to one of those names (e.g.
    ``numerator = max(product.median(), 0.01)``), a shape a plain
    ``"max(numerator"``-token grep cannot see because the rescued expression
    is not itself named ``numerator`` at the call site. Mutation-proven: a
    prior plain-string-token version of this test passed unchanged under
    exactly that shape."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "compute_lambda_fs"
    )

    rescue_call_names = {"max", "min"}
    rescue_attr_names = {"maximum", "minimum", "clip"}

    def _is_rescue_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id in rescue_call_names:
            return True
        if isinstance(callee, ast.Attribute) and callee.attr in rescue_attr_names:
            return True
        return False

    violations = []
    for stmt in ast.walk(func):
        if not isinstance(stmt, ast.Assign):
            continue
        targets = {t.id for t in stmt.targets if isinstance(t, ast.Name)}
        if not (targets & {"numerator", "denominator"}):
            continue
        for sub in ast.walk(stmt.value):
            if _is_rescue_call(sub):
                violations.append((sorted(targets), ast.dump(sub)))
    assert not violations, (
        "forbidden rescue call (max/min/np.maximum/np.minimum/np.clip) found "
        f"feeding an assignment to numerator/denominator: {violations}"
    )

    # eps/fallback vocabulary is never a legitimate identifier this function
    # would use for any other purpose -- a plain-string scan over the CODE
    # (never the docstring, which names the prohibition in prose) still
    # catches it cheaply.
    start = src.index("def compute_lambda_fs(")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    doc_end = body.index('"""', body.index('"""') + 3) + 3
    code = body[doc_end:]
    banned_code_shapes = ["eps =", "eps=", "+ eps", "or 0.01", "fallback"]
    for token in banned_code_shapes:
        assert token not in code, f"forbidden rescue shape {token!r} found in compute_lambda_fs's code"


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


def test_assert_bars_within_guard_raises_on_violation():
    """Bars-side, defense-in-depth check (freeze review finding B3) — the
    function formerly named ``assert_recent_history_guard``."""
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    with pytest.raises(calib_replay.RecentHistoryGuardViolation):
        calib_replay.assert_bars_within_guard({"AAA": bars}, cutoff)


def test_assert_bars_within_guard_passes_when_truncated():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    truncated = calib_replay.truncate_to_guard({"AAA": bars}, cutoff)
    calib_replay.assert_bars_within_guard(truncated, cutoff)  # must not raise
    assert truncated["AAA"].index.max() <= cutoff


# ---------------------------------------------------------------------------
# B3: the REAL guard runs on the substrate's own OUTPUTS (events/episodes), not
# merely on self-truncated input bars.
# ---------------------------------------------------------------------------
def test_assert_recent_history_guard_raises_on_event_beyond_cutoff():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    events = pd.DataFrame({
        "event_id": ["E1"], "family_key": ["fam.x"], "symbol": ["AAA"],
        "signal_known_ts": [bars.index[-1]],  # WELL beyond cutoff
    })
    with pytest.raises(calib_replay.RecentHistoryGuardViolation):
        calib_replay.assert_recent_history_guard(events, pd.DataFrame(), cutoff)


def test_assert_recent_history_guard_raises_on_episode_end_date_beyond_cutoff():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    episodes = pd.DataFrame({
        "symbol": ["AAA"], "start_date": [bars.index[-200]], "end_date": [bars.index[-1]],
    })
    with pytest.raises(calib_replay.RecentHistoryGuardViolation):
        calib_replay.assert_recent_history_guard(pd.DataFrame(), episodes, cutoff)


def test_assert_recent_history_guard_passes_when_outputs_respect_cutoff():
    bars = _synthetic_bars(n=400)
    cutoff = bars.index[-127]
    events = pd.DataFrame({
        "event_id": ["E1"], "family_key": ["fam.x"], "symbol": ["AAA"],
        "signal_known_ts": [bars.index[-200]],
    })
    episodes = pd.DataFrame({
        "symbol": ["AAA"], "start_date": [bars.index[-250]], "end_date": [bars.index[-200]],
    })
    calib_replay.assert_recent_history_guard(events, episodes, cutoff)  # must not raise


def test_run_substrate_drops_or_censors_outputs_beyond_the_recent_history_cutoff(
    synthetic_partition, fake_w2_machinery,
):
    """Even if a reused W2 fire function ignores the truncated bars it was handed
    and fires beyond the cutoff (the real-data case this test names), the
    substrate's own OUTPUT must never carry a date beyond the cutoff — proved
    here by forcing the fake fire function's date arbitrarily far in the future
    relative to a short, tight bars window."""
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    cutoff = pd.Timestamp(result.provenance["recent_history_guard_cutoff"])
    if not result.events.empty:
        assert (pd.to_datetime(result.events["signal_known_ts"]) <= cutoff).all()
    if result.episodes is not None and not result.episodes.empty and "end_date" in result.episodes.columns:
        ends = pd.to_datetime(result.episodes["end_date"], errors="coerce").dropna()
        assert (ends <= cutoff).all()


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
    # n=550 (not the default 350): long enough that the recent-history guard's
    # 126-session cutoff (asof=2021-06-01, well beyond this whole bars span)
    # lands safely AFTER the durable-low date (2019-11-18) baked into
    # _episode_bars's fixed 130-flat/100-decline layout, so the reset_decline
    # episode below still resolves under B3's real truncation instead of coming
    # back censored.
    bars_cache = {"SYN_A": _episode_bars("2019-01-01", 550),
                  "SYN_B": _episode_bars("2019-01-01", 550),
                  "SYN_ZERO": _episode_bars("2019-01-01", 550)}

    def fake_load(sym, plane_id, asof):
        if sym == "SYN_MISSING":
            raise FileNotFoundError(f"{sym} not present on plane {plane_id}")
        return bars_cache[sym].loc[bars_cache[sym].index <= asof]

    def fake_fire_fns(sym, plane_id, hashes, registry, ledgers):
        def one_fire(df):
            if sym == "SYN_ZERO":
                return []
            # Two fires inside the reset_decline episode's attribution window
            # (episode start 2019-07-02, durable low/end 2019-11-18; verified
            # against the frozen W1 episode constants): one near the durable
            # low (in-zone, no false start) and one early in the window while
            # price is still near the flat 100 level, far from the ~70
            # anchor -- this second fire's price_dist/ATR trips false_start
            # (Ruling 1(b)'s compute_lambda_fs is FAIL-CLOSED on an all-zero
            # false_start_rate population; a single-fire-per-symbol synthetic
            # fixture with no false start anywhere is a genuinely degenerate
            # calibration population under the new rule, so the fixture needs
            # a real false start to exercise the ordinary happy-path plumbing
            # tests that assume a computed, non-degenerate lambda_fs).
            return [
                _fake_event(sym, "fam.synthetic", pd.Timestamp("2019-11-15")),
                _fake_event(sym, "fam.synthetic", pd.Timestamp("2019-07-08")),
            ]

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


# ---------------------------------------------------------------------------
# MINOR (delta-review third pass): run_substrate reads its recent-history
# guard cutoff from the FROZEN si_constants_v1.json calibration_history_cutoff
# (the same source calibrate_w3.py already reads), not a re-derivation from
# whatever symbol set/calendar this particular run happens to have bars loaded
# for. recent_history_cutoff() is kept only as a cheap cross-check that warns
# (line-start ::warning) on disagreement.
# ---------------------------------------------------------------------------
def _fake_constants_path_with_cutoff(tmp_path, cutoff_str, name="si_constants_v1.json"):
    """A fake si_constants_v1.json carrying the REAL committed file's full
    payload (so unrelated reads -- P_pre, the episode constants -- keep
    working) with only calibration_history_cutoff overridden."""
    real_constants = json.loads(calib_replay.CONSTANTS_PATH.read_text(encoding="utf-8"))
    path = tmp_path / name
    path.write_text(
        json.dumps({**real_constants, "calibration_history_cutoff": cutoff_str}),
        encoding="utf-8",
    )
    return path


def test_frozen_calibration_history_cutoff_reads_the_real_committed_constant_calib_replay():
    """Parity check: calib_replay's own frozen_calibration_history_cutoff must
    read the SAME committed si_constants_v1.json field as calib_w3's -- both
    are now the SAME single frozen source of truth."""
    cutoff = calib_replay.frozen_calibration_history_cutoff()
    assert cutoff == pd.Timestamp("2026-02-11")
    assert cutoff == calib_w3.frozen_calibration_history_cutoff()


def test_run_substrate_reads_cutoff_from_frozen_constants_not_recomputed(
    monkeypatch, tmp_path, synthetic_partition, fake_w2_machinery,
):
    """The substrate's recorded recent_history_guard_cutoff must come from the
    FROZEN constant, not a re-derivation from this run's own combined bars
    calendar -- proved by pointing the frozen constant at a deliberately
    different (but still valid) date than what recent_history_cutoff() would
    derive from this fixture's synthetic calendar, and checking the
    substrate's recorded cutoff follows the frozen value, not the derived
    one."""
    replay_manifest, roster = synthetic_partition
    frozen_cutoff_str = "2020-01-02"
    monkeypatch.setattr(
        calib_replay, "CONSTANTS_PATH", _fake_constants_path_with_cutoff(tmp_path, frozen_cutoff_str),
    )
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    assert result.provenance["recent_history_guard_cutoff"] == frozen_cutoff_str


def test_run_substrate_warns_but_does_not_raise_on_cutoff_disagreement(
    monkeypatch, tmp_path, capsys, synthetic_partition, fake_w2_machinery,
):
    """MINOR: a real disagreement between the frozen constant and what this
    run's own combined bars calendar would derive must surface as a
    line-start GitHub warning (never through a logger -- house law, a
    prefixing format makes GitHub silently drop it) IMMEDIATELY, rather than
    only being discovered after a multi-hour replay completes and
    calibrate_w3.py's second barrier catches it -- and it must never raise;
    the frozen value still wins."""
    replay_manifest, roster = synthetic_partition
    frozen_cutoff_str = "2020-01-02"  # far from the derived cutoff for this fixture
    monkeypatch.setattr(
        calib_replay, "CONSTANTS_PATH", _fake_constants_path_with_cutoff(tmp_path, frozen_cutoff_str),
    )
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])  # must not raise
    out = capsys.readouterr().out
    assert out.startswith("::warning") or "\n::warning" in out
    assert "si-w3a-substrate-cutoff-disagreement" in out
    assert result.provenance["recent_history_guard_cutoff"] == frozen_cutoff_str


def test_run_substrate_does_not_warn_when_frozen_and_derived_cutoff_agree(
    monkeypatch, tmp_path, capsys, synthetic_partition, fake_w2_machinery,
):
    """The cross-check must not spuriously warn when the frozen constant and
    the run's own derived cutoff genuinely agree."""
    replay_manifest, roster = synthetic_partition
    partition = calib_replay._partition_manifest()
    asof = pd.Timestamp(partition["asof"])
    raw_bars = {
        sym: fake_w2_machinery[sym].loc[fake_w2_machinery[sym].index <= asof]
        for sym in ("SYN_A", "SYN_B")
    }
    full_calendar = pd.DatetimeIndex(sorted({d for df in raw_bars.values() for d in df.index}))
    expected_cutoff = calib_replay.recent_history_cutoff(asof, full_calendar, guard_sessions=126)
    monkeypatch.setattr(
        calib_replay, "CONSTANTS_PATH",
        _fake_constants_path_with_cutoff(tmp_path, str(expected_cutoff.date())),
    )
    calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    out = capsys.readouterr().out
    assert "::warning" not in out


# ---------------------------------------------------------------------------
# MINOR (delta-review third pass): the substrate provenance receipt names the
# eligible (tier<=2) episode population and its censored share, computed from
# the substrate's own episode catalog -- answerable at 759-name scale directly
# from the receipt, before any PR-3 constant is even read.
# ---------------------------------------------------------------------------
def test_run_substrate_provenance_carries_eligible_episode_fields(synthetic_partition, fake_w2_machinery):
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_A", "SYN_B"])
    prov = result.provenance
    for key in ("n_eligible_episodes", "n_eligible_censored", "censored_share_of_eligible"):
        assert key in prov
    assert isinstance(prov["n_eligible_episodes"], int)
    assert isinstance(prov["n_eligible_censored"], int)
    assert prov["n_eligible_censored"] <= prov["n_eligible_episodes"]
    if prov["n_eligible_episodes"]:
        assert prov["censored_share_of_eligible"] == pytest.approx(
            prov["n_eligible_censored"] / prov["n_eligible_episodes"]
        )
    else:
        assert prov["censored_share_of_eligible"] is None
    # sanity: the fields are actually derived from the substrate's OWN episode
    # catalog (tier<=2), not a placeholder constant.
    if result.episodes is not None and not result.episodes.empty and "tier" in result.episodes.columns:
        eligible = result.episodes.loc[pd.to_numeric(result.episodes["tier"], errors="coerce") <= 2]
        assert prov["n_eligible_episodes"] == len(eligible)


def test_run_substrate_eligible_episode_fields_are_zero_on_no_episodes(
    synthetic_partition, fake_w2_machinery,
):
    """A roster that produces NO episodes at all (here, every name unavailable
    -- SYN_MISSING alone) must report zero eligible counts and a None share,
    never raise."""
    replay_manifest, roster = synthetic_partition
    result = calib_replay.run_substrate(replay_manifest, sample=["SYN_MISSING"])
    assert result.episodes is None or result.episodes.empty
    prov = result.provenance
    assert prov["n_eligible_episodes"] == 0
    assert prov["n_eligible_censored"] == 0
    assert prov["censored_share_of_eligible"] is None


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
    """A tmp copy of the real spec with the PR-3 block reset to pending.

    Post-seal repair: the real committed ``ruler_spec_v1.json`` is now sealed
    (SI-SEALED-CAL-P1), so a straight byte copy of it would already be sealed
    too -- ``seal_ruler_spec``'s one-time law would then refuse on the FIRST
    call every test below makes, not just the deliberate second one. Restoring
    the pre-seal pending state here (never touching the real file) is what
    keeps the one-time-seal tests exercising the actual pending-to-sealed
    transition rather than an already-sealed-to-refused no-op.
    """
    dest = _pending_variant_of_real_spec_path(tmp_path)
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
# M8: the real seal writes a full receipt into BOTH ruler_spec_v1.json AND
# W3_RULER_REGISTRATION.md
# ---------------------------------------------------------------------------
@pytest.fixture
def throwaway_registration(tmp_path, monkeypatch):
    dest = tmp_path / "W3_RULER_REGISTRATION.md"
    dest.write_text("# fixture registration doc\n", encoding="utf-8")
    monkeypatch.setattr(calib_w3, "REGISTRATION_PATH", dest)
    return dest


def _fixture_seal_inputs(tmp_path):
    from engine.stock_identity.ruler import RulerSpec

    base_spec = RulerSpec.from_json(REAL_SPEC_PATH)
    manifest = json.loads(REAL_REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    roster = ["FIX_A", "FIX_B"]
    provenance = {
        "spec_hashes_asserted_at_run": {"fam.fixture": "deadbeef"},
        "recent_history_guard_cutoff": "2020-06-01",
    }
    provenance_path = tmp_path / "provenance_receipt.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    registration_receipt = {
        "recall_floor_rule_hash": calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE),
        "lambda_fs_rule_hash": calib_w3.rule_hash(calib_w3.LAMBDA_FS_RULE),
        "diagnostic_grid_effective_n": 6,
        "fit_read_look_budget": 3,
    }
    return dict(
        recall_floor=0.35, lambda_fs=0.75, base_spec=base_spec, roster=roster,
        manifest=manifest, provenance=provenance, provenance_path=provenance_path,
        cutoff=pd.Timestamp("2020-06-01"), registration_receipt=registration_receipt,
    )


def test_build_seal_receipt_carries_every_m8_field(tmp_path):
    receipt = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    for key in (
        "recall_floor", "lambda_fs", "roster_sha256", "replay_manifest_hash",
        "w2_family_registry_hash", "substrate_provenance_hash",
        "ruler_implementation_sha256", "spec_hash_before_seal", "spec_hash_after_seal",
        "computed_at",
    ):
        assert key in receipt, f"missing M8 receipt field: {key}"
    assert receipt["recall_floor"]["value"] == pytest.approx(0.35)
    assert receipt["lambda_fs"]["value"] == pytest.approx(0.75)
    assert len(receipt["replay_manifest_hash"]) == 64
    assert len(receipt["w2_family_registry_hash"]) == 64
    assert len(receipt["substrate_provenance_hash"]) == 64
    assert len(receipt["spec_hash_before_seal"]) == 64
    assert len(receipt["spec_hash_after_seal"]) == 64
    assert receipt["spec_hash_before_seal"] != receipt["spec_hash_after_seal"]


def test_build_seal_receipt_carries_ruler_implementation_hashes(tmp_path, monkeypatch):
    """PRE-ACT CONDITION 2 (SI-W3A-RULER-V1 pre-seal fix pass): the receipt's
    ``ruler_implementation_sha256`` block records the exact sha256 of
    ``engine/stock_identity/ruler.py`` and ``ruler_nulls.py`` bytes at seal
    time, so a post-value implementation change is detectable from the
    receipt alone (the freeze's voiding clause). Proven by pointing the
    module-level implementation paths at a throwaway fixture copy and showing
    the recorded hash changes -- and ONLY the changed file's hash changes --
    when one fixture's bytes change."""
    ruler_copy = tmp_path / "ruler_fixture.py"
    nulls_copy = tmp_path / "ruler_nulls_fixture.py"
    ruler_copy.write_bytes(b"# ruler fixture v1\n")
    nulls_copy.write_bytes(b"# ruler nulls fixture v1\n")
    monkeypatch.setattr(calib_w3, "RULER_IMPLEMENTATION_PATH", ruler_copy)
    monkeypatch.setattr(calib_w3, "RULER_NULLS_IMPLEMENTATION_PATH", nulls_copy)

    receipt_before = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    block_before = receipt_before["ruler_implementation_sha256"]
    assert set(block_before) == {"ruler_py", "ruler_nulls_py"}
    assert block_before["ruler_py"] == hashlib.sha256(ruler_copy.read_bytes()).hexdigest()
    assert block_before["ruler_nulls_py"] == hashlib.sha256(nulls_copy.read_bytes()).hexdigest()

    # change ONE file's bytes -- only ITS recorded hash may move
    ruler_copy.write_bytes(b"# ruler fixture v2 -- implementation changed\n")
    receipt_after = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    block_after = receipt_after["ruler_implementation_sha256"]
    assert block_after["ruler_py"] != block_before["ruler_py"]
    assert block_after["ruler_py"] == hashlib.sha256(ruler_copy.read_bytes()).hexdigest()
    assert block_after["ruler_nulls_py"] == block_before["ruler_nulls_py"]


def test_core_spec_hash_excludes_the_receipt_itself(tmp_path):
    """The before/after hashes must never depend on the receipt's own contents
    (a value can't legally hash itself) -- two receipts differing only in an
    unrelated field must still project to the SAME core hash."""
    from engine.stock_identity.ruler import RulerSpec

    base_spec = RulerSpec.from_json(REAL_SPEC_PATH)
    h1 = calib_w3.core_spec_hash(base_spec, recall_floor=0.35, lambda_fs=0.75, status="sealed")
    h2 = calib_w3.core_spec_hash(base_spec, recall_floor=0.35, lambda_fs=0.75, status="sealed")
    assert h1 == h2  # deterministic, independent of any receipt object identity


def test_format_seal_receipt_markdown_contains_every_hash(tmp_path):
    receipt = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    block = calib_w3.format_seal_receipt_markdown(receipt)
    assert receipt["replay_manifest_hash"] in block
    assert receipt["w2_family_registry_hash"] in block
    assert receipt["substrate_provenance_hash"] in block
    assert receipt["ruler_implementation_sha256"]["ruler_py"] in block
    assert receipt["ruler_implementation_sha256"]["ruler_nulls_py"] in block
    assert receipt["spec_hash_before_seal"] in block
    assert receipt["spec_hash_after_seal"] in block
    assert "0.35" in block
    assert "0.75" in block


def test_append_seal_receipt_to_registration_writes_the_throwaway_file(
    tmp_path, throwaway_registration,
):
    receipt = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    before = throwaway_registration.read_text(encoding="utf-8")
    calib_w3.append_seal_receipt_to_registration(receipt)
    after = throwaway_registration.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert receipt["spec_hash_after_seal"] in after
    # the REAL, committed registration doc is untouched
    assert REAL_REGISTRATION_PATH.read_text(encoding="utf-8") == REGISTRATION_DOC_SNAPSHOT


REAL_REGISTRATION_PATH = ROOT / "research" / "stock_identity" / "W3_RULER_REGISTRATION.md"
REGISTRATION_DOC_SNAPSHOT = REAL_REGISTRATION_PATH.read_text(encoding="utf-8")


def test_seal_and_append_end_to_end_never_touches_real_registration_doc(
    throwaway_spec, throwaway_registration, tmp_path,
):
    """The real (fixture-value) seal path -- seal_ruler_spec +
    append_seal_receipt_to_registration -- writes into the THROWAWAY spec and
    THROWAWAY registration doc only; the real committed
    W3_RULER_REGISTRATION.md is byte-identical before and after."""
    receipt = calib_w3.build_seal_receipt(**_fixture_seal_inputs(tmp_path))
    calib_w3.seal_ruler_spec(0.35, 0.75, receipt=receipt)
    calib_w3.append_seal_receipt_to_registration(receipt)

    assert "0.35" in throwaway_registration.read_text(encoding="utf-8")
    assert REAL_REGISTRATION_PATH.read_text(encoding="utf-8") == REGISTRATION_DOC_SNAPSHOT


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
    # Ruling 2: an explicit family_registry entry for "fam.synthetic" -- the
    # real committed registry has no such family, and
    # compute_constants_from_substrate's default (load_family_registry()) would
    # type every cell UNESTIMABLE for it. Sol CONFIRMATION-1 point 5 also
    # requires a present provenance_class (R/B, never omitted). Sol
    # REQUEST_REPAIR (Slack C0BSBM78V1N, 2026-08-29): a NULL
    # family_first_available can no longer type ELIGIBLE at all (however
    # receipted its spec_hash), which would make every cell UNESTIMABLE here
    # and raise inside compute_recall_floor/compute_lambda_fs -- this test is
    # about the end-to-end constant-computation WIRING, not the null-bound
    # availability law, so a BOUNDED entry (predating this synthetic
    # substrate's fixture bars, which start 2019-01-01) keeps the fixture
    # genuinely unrestricted via the unchanged bounded path.
    fixture_registry = [{
        "family_key": "fam.synthetic", "family_first_available": "1900-01-01",
        "provenance_class": "R",
    }]
    recall_floor, lambda_fs, cells = calib_w3.compute_constants_from_substrate(
        result.events, result.attribution, result.episodes, result.bars_by_symbol, base_spec,
        family_registry=fixture_registry,
    )
    assert isinstance(recall_floor, float)
    assert isinstance(lambda_fs, float)
    assert not cells.empty


# ---------------------------------------------------------------------------
# B1: --sample without --estimate-only refuses (never falls through to a real,
# partial-roster write)
# ---------------------------------------------------------------------------
def test_sample_without_estimate_only_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibration_replay.py",
        "--manifest", str(tmp_path / "does_not_exist.json"),
        "--sample", "5",
    ])
    with pytest.raises(calib_replay.SampledSubstrateWriteRefused):
        calib_replay.main()


def test_sample_with_estimate_only_does_not_hit_the_refusal_gate(monkeypatch, tmp_path):
    """Proves the refusal is specifically about --sample WITHOUT --estimate-only
    -- a nonexistent manifest still fails, but with a DIFFERENT exception, proving
    the refusal check itself did not fire."""
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibration_replay.py",
        "--manifest", str(tmp_path / "does_not_exist.json"),
        "--sample", "5", "--estimate-only",
    ])
    with pytest.raises(FileNotFoundError):
        calib_replay.main()


def test_no_sample_without_estimate_only_does_not_hit_the_refusal_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibration_replay.py",
        "--manifest", str(tmp_path / "does_not_exist.json"),
    ])
    with pytest.raises(FileNotFoundError):
        calib_replay.main()


# ---------------------------------------------------------------------------
# B1: partial-substrate refusal by the constant-setting act itself
# ---------------------------------------------------------------------------
def test_assert_full_roster_coverage_refuses_on_roster_hash_mismatch():
    manifest = {"roster": {"roster_sha256": "cafebabe"}}
    provenance = {"roster_sha256": "deadbeef", "n_names_attempted": 3}
    with pytest.raises(calib_w3.PartialSubstrateError):
        calib_w3.assert_full_roster_coverage(provenance, ["A", "B", "C"], manifest)


def test_assert_full_roster_coverage_refuses_on_partial_n_attempted():
    manifest = {"roster": {"roster_sha256": "cafebabe"}}
    provenance = {"roster_sha256": "cafebabe", "n_names_attempted": 2}
    with pytest.raises(calib_w3.PartialSubstrateError):
        calib_w3.assert_full_roster_coverage(provenance, ["A", "B", "C"], manifest)


def test_assert_full_roster_coverage_passes_on_full_match():
    manifest = {"roster": {"roster_sha256": "cafebabe"}}
    provenance = {"roster_sha256": "cafebabe", "n_names_attempted": 3}
    calib_w3.assert_full_roster_coverage(provenance, ["A", "B", "C"], manifest)  # must not raise


def test_main_refuses_when_substrate_provenance_missing(tmp_path):
    """main() checks provenance coverage BEFORE reading any parquet — a
    substrate-dir with the parquet files but no provenance_receipt.json (which
    a --sample write would never legitimately produce anyway, per B1's CLI
    refusal, but this proves the setter's OWN independent check) refuses."""
    substrate_dir = tmp_path / "substrate_no_provenance"
    substrate_dir.mkdir()
    import pandas as pd
    pd.DataFrame({
        "event_id": ["E1"], "family_key": ["fam.x"], "symbol": ["A"],
        "signal_known_ts": [pd.Timestamp("2020-01-01")],
    }).to_parquet(substrate_dir / "calibration_events_v1.parquet")
    pd.DataFrame({"symbol": ["A"]}).to_parquet(substrate_dir / "calibration_episodes_v1.parquet")

    monkeypatch_argv = [
        "stock_identity_calibrate_w3.py", "--substrate-dir", str(substrate_dir),
    ]
    old_argv = sys.argv
    sys.argv = monkeypatch_argv
    try:
        with pytest.raises(calib_w3.PartialSubstrateError):
            calib_w3.main()
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# B1: dry-run masks every derived PR-3 constant value
# ---------------------------------------------------------------------------
def test_build_dry_run_report_masks_constant_values():
    report = calib_w3.build_dry_run_report(
        roster=["A", "B"],
        events=pd.DataFrame({"signal_known_ts": [pd.Timestamp("2020-01-01")]}),
        episodes=pd.DataFrame({"symbol": ["A"]}),
        cells=pd.DataFrame({"x": [1]}),
        cutoff=pd.Timestamp("2020-06-01"),
    )
    assert report["recall_floor_value"] == "MASKED_DRY_RUN"
    assert report["lambda_fs_value"] == "MASKED_DRY_RUN"
    assert isinstance(report["recall_floor_value"], str)
    assert isinstance(report["lambda_fs_value"], str)
    # no key in the report ever holds a bare float -- every numeric field is a
    # COUNT (roster_n/n_events/n_episodes/n_cells), never a computed constant
    numeric_keys = {k for k, v in report.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert numeric_keys <= {"roster_n", "n_events", "n_episodes", "n_cells"}


def test_main_source_never_puts_bare_recall_floor_or_lambda_fs_into_the_dry_run_report():
    """Named regression pinning the exact defect this repair closes: the OLD
    implementation printed the full receipt (containing the real numeric
    values) unconditionally, BEFORE checking ``args.dry_run``. Source-level
    check: the dry-run branch must build its report via build_dry_run_report
    (which has no parameter a real value could flow through), never inline a
    dict literal referencing the local recall_floor/lambda_fs values."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    start = src.index("if args.dry_run:")
    end = src.index("ledger = TrialLedger(")
    branch = src[start:end]
    assert "build_dry_run_report(" in branch
    assert '"recall_floor_value": recall_floor' not in branch
    assert '"lambda_fs_value": lambda_fs' not in branch


def test_register_rules_and_grid_is_never_called_in_the_dry_run_branch():
    """M9/B1: dry-run must not write to the shared data/trial_ledger.jsonl."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    start = src.index("if args.dry_run:")
    end = src.index("ledger = TrialLedger(")
    branch = src[start:end]
    assert "register_rules_and_grid(" not in branch
    assert "TrialLedger(" not in branch
    assert "seal_ruler_spec(" not in branch


# ---------------------------------------------------------------------------
# B4: rule-review disclosure
# ---------------------------------------------------------------------------
def test_rule_review_status_is_declared_pending_sol_rule_review():
    assert calib_w3.RULE_REVIEW_STATUS == "declared_pending_sol_rule_review"


def test_rule_hashes_match_the_currently_committed_registration_values():
    """Ruling 1 (SI-W3A-RULER-V1 PR-3 seal law) REPLACES both rules' exact
    forms (recall_floor gains the max(...,0.05) preregistered substantive
    floor; lambda_fs's formula is now median(recall_at_tier*zone_precision) /
    P75(false_start_rate), fail-closed, no rounding grid) -- a genuine
    rule-FORM change, so both hashes changed again and are re-recorded in
    W3_RULER_REGISTRATION.md §3.1 with every PRIOR hash (including the two
    pre-Ruling-1 population-wording-only re-pins) retained alongside the new
    one. recall_floor's hash then moved a FOURTH time (pre-seal fix pass,
    item 5) -- a TEXT-ONLY clarification naming the quantize_to_nearest_0.05
    tie convention (Python's round(), banker's rounding/round-half-to-even);
    the math is unchanged, round() was always the implementation.
    lambda_fs's hash is untouched by that item."""
    assert calib_w3.rule_hash(calib_w3.LAMBDA_FS_RULE) == (
        "8b149a753f5034c737eb0cc0c72d081e56e2d9431dd4adc01ac0cea8cc4ae366"
    )
    assert calib_w3.rule_hash(calib_w3.RECALL_FLOOR_RULE) == (
        "71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf"
    )


def test_register_rules_and_grid_echoes_rule_review_status(tmp_path):
    ledger = TrialLedger(path=tmp_path / "trial_ledger.jsonl", family=calib_w3.TRIAL_FAMILY)
    receipt = calib_w3.register_rules_and_grid(ledger, info_cutoff="2026-08-13")
    assert receipt["rule_review_status"] == "declared_pending_sol_rule_review"


def test_sealed_receipt_carries_rule_review_status(throwaway_spec):
    """The real (non-dry-run) receipt's per-constant blocks must carry the
    disclosure status too -- a reader of a sealed receipt must be able to see
    that the rule form was pending Sol review at seal time without cross-
    referencing source."""
    receipt = {
        "recall_floor": {"value": 0.35, "status": calib_w3.RULE_REVIEW_STATUS},
        "lambda_fs": {"value": 0.75, "status": calib_w3.RULE_REVIEW_STATUS},
    }
    sealed = calib_w3.seal_ruler_spec(0.35, 0.75, receipt=receipt)
    payload = json.loads(throwaway_spec.read_text(encoding="utf-8"))
    assert payload["pr3"]["receipt"]["recall_floor"]["status"] == "declared_pending_sol_rule_review"
    assert payload["pr3"]["receipt"]["lambda_fs"]["status"] == "declared_pending_sol_rule_review"


def test_real_sealed_receipt_status_field_predates_the_rule_form_ruling():
    """The REAL shipped receipt (data/stock_identity/ruler/ruler_spec_v1.json,
    sealed by SI-SEALED-CAL-P1) still carries ``status:
    declared_pending_sol_rule_review`` on both PR-3 constant blocks -- this is
    a labeling artifact, not evidence the rule form is unreviewed: Sol's
    rule-form ruling (Ruling 1, W3_RULER_REGISTRATION.md §6.11) landed BEFORE
    this seal and the sealed ``rule``/``rule_hash`` fields are exactly Sol's
    ruled forms (Ruling 1(a) for recall_floor, Ruling 1(b) for lambda_fs; the
    hashes below match §3.1's re-pinned values and
    test_rule_hashes_match_the_currently_committed_registration_values above).
    ``RULE_REVIEW_STATUS`` is a single module-level constant the seal path
    never re-derives per constant, so the sealed receipt still carries the
    pre-ruling wording even though the ruling has, in fact, already happened.
    This test pins that reading rather than letting a future reader infer from
    the string alone that Sol never ruled -- see the registration doc's §5.1
    caveat for the same note in the human-facing record. Do NOT edit the
    sealed receipt to fix this string -- the freeze's voiding clause covers
    it; only the test/doc read of it may change."""
    payload = json.loads(REAL_SPEC_PATH.read_text(encoding="utf-8"))
    receipt = payload["pr3"]["receipt"]
    assert receipt["recall_floor"]["status"] == "declared_pending_sol_rule_review"
    assert receipt["lambda_fs"]["status"] == "declared_pending_sol_rule_review"
    assert receipt["recall_floor"]["rule_hash"] == (
        "71fbf3ff74e344ea7713f07e3615c4be8ce3e4c7a691af60e44eb151320a04cf"
    )
    assert receipt["lambda_fs"]["rule_hash"] == (
        "8b149a753f5034c737eb0cc0c72d081e56e2d9431dd4adc01ac0cea8cc4ae366"
    )


# ---------------------------------------------------------------------------
# B1: a real, wired dry-run leaves the tracked tree byte-clean and writes
# nothing to data/trial_ledger.jsonl
# ---------------------------------------------------------------------------
@pytest.fixture
def dry_run_substrate(tmp_path, monkeypatch, fake_w2_machinery, throwaway_spec):
    # A small, fully-available roster (no SYN_MISSING) so run_substrate with the
    # FULL roster (sample=None) never produces an unavailable-name blocker --
    # B1's assert_full_roster_coverage refuses on anything less than the full
    # drawn roster, so this fixture must actually cover it.
    roster = ["SYN_A", "SYN_B"]
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
    monkeypatch.setattr(calib_w3, "_partition_manifest", lambda: partition)

    replay_manifest = {"roster": {"roster_sha256": roster_sha256, "n_drawn": len(roster)}}
    manifest_path = tmp_path / "calibration_replay_manifest_v1.json"
    manifest_path.write_text(json.dumps(replay_manifest), encoding="utf-8")
    monkeypatch.setattr(calib_w3, "REPLAY_MANIFEST_PATH", manifest_path)

    def fake_load_symbol(sym, plane_id, root):
        return fake_w2_machinery[sym]
    monkeypatch.setattr("engine.stock_identity.plane.load_symbol", fake_load_symbol)

    # Minor repair (delta-review third pass): run_substrate now reads its
    # cutoff from the FROZEN si_constants_v1.json (calib_replay.CONSTANTS_PATH)
    # rather than deriving it -- point that at a fake file carrying exactly the
    # cutoff this synthetic partition's own combined bars calendar derives, so
    # (a) run_substrate's frozen-vs-derived cross-check never disagrees and
    # prints a stray ::warning into a test's captured stdout, and (b) the
    # substrate's own guard truncation still exercises this fixture's short,
    # tight bars window exactly as it did before this repair.
    asof = pd.Timestamp(partition["asof"])
    full_calendar = pd.DatetimeIndex(sorted({
        d for sym in roster for d in fake_w2_machinery[sym].loc[fake_w2_machinery[sym].index <= asof].index
    }))
    expected_cutoff = calib_replay.recent_history_cutoff(asof, full_calendar, guard_sessions=126)
    fake_constants_path = tmp_path / "si_constants_v1.json"
    # run_substrate also reads P_pre and the episode constants (X/Y/N/k/z/M/m/
    # D1/D2/S_reclaim) off this SAME CONSTANTS_PATH (unrelated to the cutoff
    # repair) -- start from the REAL committed file's full payload and override
    # only calibration_history_cutoff, so those unrelated reads keep working
    # once CONSTANTS_PATH is redirected here.
    real_constants = json.loads(calib_replay.CONSTANTS_PATH.read_text(encoding="utf-8"))
    fake_constants_path.write_text(
        json.dumps({**real_constants, "calibration_history_cutoff": str(expected_cutoff.date())}),
        encoding="utf-8",
    )
    monkeypatch.setattr(calib_replay, "CONSTANTS_PATH", fake_constants_path)

    # the FULL drawn roster (not a sample) -- assert_full_roster_coverage (B1)
    # would otherwise correctly refuse a partial-roster substrate here too.
    result = calib_replay.run_substrate(replay_manifest, sample=None)
    assert not result.unavailable
    substrate_dir = tmp_path / "substrate"
    calib_replay.write_substrate(result, substrate_dir)

    # B3-minor: the second barrier (calib_w3) also checks the substrate's
    # recorded cutoff against a FROZEN constants file (never a recomputation)
    # -- the SAME fake file above already carries exactly the cutoff this
    # synthetic substrate now records, so it doubles as calib_w3's frozen
    # source too.
    assert result.provenance["recent_history_guard_cutoff"] == str(expected_cutoff.date())
    monkeypatch.setattr(calib_w3, "CALIBRATION_CONSTANTS_PATH", fake_constants_path)

    # Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law): aggregate_cell_metrics'
    # recall-denominator eligibility now needs a W2 family registry entry for
    # "fam.synthetic" (the synthetic fixture family) -- the REAL committed
    # family_registry.json carries no such family, which would type every
    # cell UNESTIMABLE and make compute_recall_floor/compute_lambda_fs raise.
    # Point FAMILY_REGISTRY_PATH at a fixture file carrying a BOUNDED entry
    # for it, same pattern as the other monkeypatched module paths above.
    # Sol CONFIRMATION-1 point 5 also requires a present provenance_class
    # (R/B). Sol REQUEST_REPAIR (Slack C0BSBM78V1N, 2026-08-29): a NULL
    # family_first_available can no longer type ELIGIBLE at all -- this
    # fixture is about the CLI's end-to-end wiring, not the null-bound
    # availability law, so a bound predating the fixture bars (2019-01-01)
    # keeps it genuinely unrestricted via the unchanged bounded path.
    fake_family_registry_path = tmp_path / "family_registry.json"
    fake_family_registry_path.write_text(
        json.dumps({"families": [{
            "family_key": "fam.synthetic", "family_first_available": "1900-01-01",
            "provenance_class": "R",
        }]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(calib_w3, "FAMILY_REGISTRY_PATH", fake_family_registry_path)

    return substrate_dir


def test_dry_run_leaves_tracked_tree_byte_clean_and_writes_no_ledger_entry(
    monkeypatch, tmp_path, dry_run_substrate,
):
    import subprocess

    ledger_path = ROOT / "data" / "trial_ledger.jsonl"
    ledger_before = ledger_path.read_bytes() if ledger_path.exists() else None
    git_before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout

    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibrate_w3.py",
        "--substrate-dir", str(dry_run_substrate), "--dry-run",
    ])
    rc = calib_w3.main()
    assert rc == 0

    git_after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert git_after == git_before

    ledger_after = ledger_path.read_bytes() if ledger_path.exists() else None
    assert ledger_after == ledger_before

    # the throwaway spec (standing in for ruler_spec_v1.json, from the
    # dry_run_substrate fixture's throwaway_spec dependency) is untouched too --
    # dry-run must never call seal_ruler_spec.
    from engine.stock_identity.ruler import RulerSpec
    assert RulerSpec.from_json(calib_w3.SPEC_PATH).pr3_pending is True


# ---------------------------------------------------------------------------
# MINORS: scratch fallback is never another session's private scratchpad path
# ---------------------------------------------------------------------------
def test_scratch_fallback_default_is_not_hardcoded_to_any_session_scratchpad():
    """Named regression: a prior revision of this module hardcoded a specific
    session's UUID-scoped working-directory path as the SCRATCH fallback
    default -- another session's (or a later run's) private, non-durable
    directory. The fallback must be a generic, non-session-specific location
    (the OS temp root), honoring STOCK_IDENTITY_CALIBRATION_SCRATCH as the
    lawful override."""
    import re
    src = Path(calib_replay.__file__).read_text(encoding="utf-8")
    assert "tempfile.gettempdir()" in src
    # no UUID (session-identifying) literal appears anywhere in the source
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    assert not uuid_pattern.search(src)
    # the actual default resolves under the OS temp root, not a fixed absolute
    # path baked in at authoring time
    default = calib_replay.SCRATCH
    assert str(default).startswith(tempfile.gettempdir()) or "STOCK_IDENTITY_CALIBRATION_SCRATCH" in os.environ


def test_dry_run_output_report_has_no_numeric_constant_values(monkeypatch, capsys, dry_run_substrate):
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibrate_w3.py",
        "--substrate-dir", str(dry_run_substrate), "--dry-run",
    ])
    rc = calib_w3.main()
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["status"] == "DRY_RUN_OK"
    assert report["recall_floor_value"] == "MASKED_DRY_RUN"
    assert report["lambda_fs_value"] == "MASKED_DRY_RUN"


# ---------------------------------------------------------------------------
# B3-minor: the second barrier compares against the frozen W1
# calibration_history_cutoff constant, never a recomputation from whatever
# (possibly narrower) symbol set this script happens to have bars loaded for.
# ---------------------------------------------------------------------------
def test_frozen_calibration_history_cutoff_reads_the_real_committed_constant():
    """Sanity check against the real, committed si_constants_v1.json (no
    monkeypatch) -- pins that the frozen source of truth is actually wired to
    the committed W1 file, not merely to a test double."""
    cutoff = calib_w3.frozen_calibration_history_cutoff()
    assert cutoff == pd.Timestamp("2026-02-11")


def test_main_refuses_when_recorded_cutoff_disagrees_with_frozen_constant(
    monkeypatch, dry_run_substrate,
):
    """B3-minor discriminating test: the substrate's own recorded cutoff must
    agree with the frozen W1 calibration_history_cutoff constant -- a real
    disagreement (here, a deliberately wrong frozen constant) must still be
    caught, exactly as a disagreement with a recomputed cutoff used to be."""
    wrong_constants_path = dry_run_substrate.parent / "si_constants_wrong.json"
    wrong_constants_path.write_text(
        json.dumps({"calibration_history_cutoff": "1999-01-01"}), encoding="utf-8",
    )
    monkeypatch.setattr(calib_w3, "CALIBRATION_CONSTANTS_PATH", wrong_constants_path)
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibrate_w3.py",
        "--substrate-dir", str(dry_run_substrate), "--dry-run",
    ])
    with pytest.raises(calib_replay.RecentHistoryGuardViolation):
        calib_w3.main()


def test_main_never_recomputes_cutoff_from_episodes_only_symbol_set():
    """Named regression: the second barrier must not call
    scripts.stock_identity_calibration_replay.recent_history_cutoff (the prior
    implementation's symbol-set-dependent recomputation) anywhere in its own
    source -- the harmonized check reads only frozen_calibration_history_cutoff
    (si_constants_v1.json)."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    assert "recent_history_cutoff(" not in src
    assert "frozen_calibration_history_cutoff()" in src


# ---------------------------------------------------------------------------
# M8-minor: the receipt-inclusive hash is named/asserted distinctly from the
# receipt-exclusive spec_hash_after_seal
# ---------------------------------------------------------------------------
def test_main_prints_sealed_spec_receipt_hash_not_sealed_spec_hash():
    """Named regression pinning the M8-minor rename: the OLD field name
    'sealed_spec_hash' must never appear in source, and the new name must."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    assert '"sealed_spec_hash"' not in src
    assert '"sealed_spec_receipt_hash"' in src


def test_registration_append_failure_prints_recovery_message_and_reraises(
    monkeypatch, tmp_path, dry_run_substrate, throwaway_spec,
):
    """M8-minor, end-to-end: on a registration-append failure AFTER a
    successful seal, the real (non-dry-run) main() must (1) leave the seal
    durably committed to the throwaway ruler_spec_v1.json (never attempt to
    unseal), (2) print a recovery message naming that durable receipt, and (3)
    still propagate the append failure to the caller."""
    from engine.trial_ledger import TrialLedger as RealTrialLedger

    monkeypatch.setattr(
        calib_w3, "TrialLedger",
        lambda family: RealTrialLedger(path=tmp_path / "throwaway_trial_ledger.jsonl", family=family),
    )

    def _boom(receipt):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(calib_w3, "append_seal_receipt_to_registration", _boom)
    monkeypatch.setattr(sys, "argv", [
        "stock_identity_calibrate_w3.py",
        "--substrate-dir", str(dry_run_substrate),
    ])

    import io
    import contextlib

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        with pytest.raises(OSError):
            calib_w3.main()

    stdout = captured.getvalue()
    assert "::warning" in stdout
    assert "ruler_spec_v1.json" in stdout
    assert "pr3.receipt" in stdout
    assert "do NOT attempt to unseal" in stdout

    from engine.stock_identity.ruler import RulerSpec
    assert RulerSpec.from_json(calib_w3.SPEC_PATH).pr3_pending is False


# ---------------------------------------------------------------------------
# DOC ITEM: the dry-run computation-succeeded proof is an explicit raise, not a
# bare `assert` (which python -O strips)
# ---------------------------------------------------------------------------
def test_dry_run_computation_proof_is_not_a_bare_assert():
    """Named regression: a bare `assert isinstance(...)` is stripped entirely
    under `python -O`, silently removing the proof that the dry-run computation
    actually succeeded. The dry-run branch must use an explicit
    if/raise instead."""
    src = Path(calib_w3.__file__).read_text(encoding="utf-8")
    start = src.index("if args.dry_run:")
    end = src.index("ledger = TrialLedger(")
    branch = src[start:end]
    assert "assert isinstance(recall_floor, float)" not in branch
    assert "raise TypeError(" in branch
