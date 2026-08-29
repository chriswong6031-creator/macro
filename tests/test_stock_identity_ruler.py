"""Stock Identity W3A — the localization ruler contract (Tasks 1-3).

What a reader should not have to take on trust:

1. The ruler spec ships exactly two graded composites (``c_loc_r``, ``c_loc_d``) and its
   PR-3 constant family (``lambda_fs``, ``recall_floor``) carries the explicit
   ``pending_sealed_calibration`` sentinel until Task 3C runs — never a guessed number.
2. ``compute_fire_metrics`` builds one measurement row per attributed (event, episode)
   hit, never a best-expert row; censored episodes carry no anchor metrics but still
   count in the unconditional block.
3. The two composites are exact, declared formulas over already-aggregated cell metrics;
   ``compute_composites`` REFUSES while the spec's PR-3 fields are still pending.
4. No output column or module source carries ranking/outcome-audition vocabulary
   (``best_expert``, ``expert_rank``, ``winner``, ``route``, ``prophet_score``), and every
   serialized authority axis is false.

Fixture-only constants (``lambda_fs=0.5`` etc. below) are chosen for arithmetic
legibility and carry no prior on the production value later set by Task 3C from
``SI-SEALED-CAL-P1``; they are never serialized to ``ruler_spec_v1.json`` and are not
readable by any script path.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity.ruler import (
    FIRE_METRIC_COLUMNS,
    SUPPORT_COVERAGE_COLUMNS,
    UNCONDITIONAL_BLOCK_COLUMNS,
    FAMILY_ELIGIBLE_STATE,
    FAMILY_EPISODE_AVAILABILITY_COLUMNS,
    FORBIDDEN_OUTPUT_TOKENS,
    MissingRankStratumColumnsError,
    PendingSealedCalibrationError,
    RulerSpec,
    UnconditionalBlockUniverseError,
    aggregate_cell_metrics,
    build_family_episode_availability,
    build_support_coverage,
    compute_composites,
    compute_fire_metrics,
    compute_unconditional_block,
    validate_ruler_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data" / "stock_identity" / "ruler" / "ruler_spec_v1.json"
RULER_SRC = ROOT / "engine" / "stock_identity" / "ruler.py"
RULER_NULLS_SRC = ROOT / "engine" / "stock_identity" / "ruler_nulls.py"


def _pending_variant_of_shipped_spec_path(tmp_path: Path) -> Path:
    """SI-W3A-RULER-V1 post-seal test repair: PR-3 sealed for real
    (SI-SEALED-CAL-P1, recall_floor=0.05, lambda_fs=0.000279297) on the shipped
    ``ruler_spec_v1.json``, so the pre-seal invariants below (pending sentinel
    present, ``compute_composites`` refusal) can no longer be exercised against
    the real committed file. Materialize a byte-identical COPY of the shipped
    spec in ``tmp_path`` with ONLY the ``pr3`` block reset to its pre-seal
    ``pending_sealed_calibration`` state (verified against git rev
    0b7442209a35, the commit immediately preceding the seal) so every pre-seal
    behavior stays live and mutation-killable."""
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
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
    out_path = tmp_path / "ruler_spec_v1_pending_variant.json"
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# fixture-only spec (never serialized; arithmetic legibility only)
# ---------------------------------------------------------------------------
def _fixture_spec(**overrides) -> RulerSpec:
    base = dict(
        schema="stock_identity.ruler_spec.v1",
        version="v1",
        atr_basis="wilder_atr14_at_prior_confirmed_close",
        p_pre_sessions=5,
        useful_zone_window_sessions=15,
        useful_zone_delta_atr=0.75,
        false_start_atr_threshold=3.75,
        episode_type_anchor={
            "reset_decline": "durable_low",
            "reclaim": "recapture_bar",
            "failed_breakdown": "breakdown_low",
        },
        grain_classes=("daily", "weekly"),
        graded_composites=("c_loc_r", "c_loc_d"),
        c_loc_d_rank_population="episode_type_x_grain",
        recall_floor=0.3,
        lambda_fs=0.5,
        pr3_status="fixture_only",
        pr3_receipt=None,
        authority={
            "can_rank": False, "can_size": False, "can_gate": False,
            "can_originate_signal": False, "can_escalate": False,
        },
    )
    base.update(overrides)
    return RulerSpec(**base)


# ---------------------------------------------------------------------------
# Task 1: contract tests
# ---------------------------------------------------------------------------
def test_ruler_spec_has_only_two_graded_composites():
    spec = RulerSpec.from_json(SPEC_PATH)
    assert spec.graded_composites == ("c_loc_r", "c_loc_d")


def test_shipped_spec_freezes_c_loc_d_rank_population_as_episode_type_x_grain():
    """M5: the rank-normalization stratum is frozen in the shipped spec, not left
    implicit in code alone (this is a non-PR-3 structural field — it must be
    present even while pr3 stays pending)."""
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert payload["c_loc_d_rank_population"] == "episode_type_x_grain"


def test_ruler_spec_reads_c_loc_d_rank_population_from_json():
    """M5-residual: the field must actually be READ by RulerSpec.from_json (the
    prior implementation left it present in the JSON but never parsed it), so
    RulerSpec.c_loc_d_rank_population reflects the shipped file's value."""
    spec = RulerSpec.from_json(SPEC_PATH)
    assert spec.c_loc_d_rank_population == "episode_type_x_grain"


def test_c_loc_d_rank_population_is_carried_in_canonical_dict():
    spec = _fixture_spec()
    assert spec.to_canonical_dict()["c_loc_d_rank_population"] == "episode_type_x_grain"


def test_c_loc_d_rank_population_change_changes_the_spec_hash():
    """M5-residual: because the field is now carried in to_canonical_dict(), it
    must be covered by spec_hash() — a spec differing ONLY in this field must
    hash differently."""
    a = _fixture_spec(c_loc_d_rank_population="episode_type_x_grain")
    b = _fixture_spec(c_loc_d_rank_population="something_else")
    assert a.spec_hash() != b.spec_hash()


def test_ruler_spec_hash_is_stable():
    spec = RulerSpec.from_json(SPEC_PATH)
    assert len(spec.spec_hash()) == 64
    assert spec.spec_hash() == RulerSpec.from_json(SPEC_PATH).spec_hash()


def test_shipped_spec_carries_sealed_pr3_values_with_complete_receipt():
    """Sealed-state branch (PR-3's ONE-TIME SEAL, SI-SEALED-CAL-P1, executed
    2026-08-29): the committed JSON now carries the receipted values, never a
    guessed number and never the pre-seal pending sentinel. The receipt's
    ``ruler_implementation_sha256`` pins MUST match the CURRENT bytes of
    ``ruler.py``/``ruler_nulls.py`` -- this doubles as a live guard on the
    freeze's voiding clause: any future edit to either implementation file
    would desync this assertion from the receipt."""
    spec = RulerSpec.from_json(SPEC_PATH)
    assert spec.pr3_pending is False
    assert spec.recall_floor == pytest.approx(0.05)
    assert spec.lambda_fs == pytest.approx(0.00027929738756017066)

    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert payload["pr3"]["status"] == "sealed"

    receipt = payload["pr3"]["receipt"]
    for field in (
        "recall_floor", "lambda_fs", "computed_at", "n_names_drawn",
        "spec_hash_before_seal", "spec_hash_after_seal",
        "ruler_implementation_sha256", "trial_ledger_family",
        "trial_ledger_effective_n", "roster_sha256", "replay_manifest_hash",
        "substrate_provenance_hash", "w2_family_registry_hash",
        "recent_history_guard_cutoff", "fit_read_look_budget",
    ):
        assert field in receipt, f"seal receipt missing required field {field!r}"

    impl_hashes = receipt["ruler_implementation_sha256"]
    assert hashlib.sha256(RULER_SRC.read_bytes()).hexdigest() == impl_hashes["ruler_py"]
    assert (
        hashlib.sha256(RULER_NULLS_SRC.read_bytes()).hexdigest()
        == impl_hashes["ruler_nulls_py"]
    )


def test_pending_variant_spec_carries_pending_sentinel(tmp_path):
    """Preserves the pre-seal invariant (pending sentinel present, values None)
    that the shipped file itself can no longer exhibit now that it is sealed --
    exercised here against a fixture copy of the shipped spec with the PR-3
    block restored to its pre-seal state, so the behavior stays
    mutation-killable."""
    spec = RulerSpec.from_json(_pending_variant_of_shipped_spec_path(tmp_path))
    assert spec.pr3_pending is True
    assert spec.recall_floor is None
    assert spec.lambda_fs is None

    # sanity: the restore never touched the real shipped file
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert payload["pr3"]["status"] == "sealed"


def test_shipped_spec_authority_all_false():
    spec = RulerSpec.from_json(SPEC_PATH)
    assert spec.authority == {
        "can_rank": False, "can_size": False, "can_gate": False,
        "can_originate_signal": False, "can_escalate": False,
    }


def test_fixture_spec_is_never_confused_with_shipped_spec(tmp_path):
    """Fixture-only constants must not equal whatever the shipped file carries,
    and the restored pre-seal fixture copy (used to keep the pending-state
    invariants mutation-killable now that the real file is sealed) must not be
    confused with either the fixture or the real sealed shipped spec."""
    fixture = _fixture_spec()
    shipped = RulerSpec.from_json(SPEC_PATH)
    pending_variant = RulerSpec.from_json(_pending_variant_of_shipped_spec_path(tmp_path))

    assert fixture.pr3_status != shipped.pr3_status
    assert shipped.pr3_pending is False  # sealed, SI-SEALED-CAL-P1
    assert pending_variant.pr3_pending is True
    assert pending_variant.pr3_status != shipped.pr3_status
    assert fixture.recall_floor != shipped.recall_floor
    assert fixture.lambda_fs != shipped.lambda_fs


def test_validate_ruler_inputs_raises_on_missing_columns():
    with pytest.raises(ValueError):
        validate_ruler_inputs(pd.DataFrame({"a": [1]}), pd.DataFrame(), pd.DataFrame())


# ---------------------------------------------------------------------------
# shared fixture builders (episodes/events/attribution) for Tasks 2-3
# ---------------------------------------------------------------------------
def _bars(symbol: str, start: str, n: int, base: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    # a smooth decline then recovery so ATR stays well-defined and positive
    if n % 2 == 0:
        down = base - np.linspace(0, 20, n // 2)
        up = down[-1] + np.linspace(0, 10, n - n // 2)
        close = np.concatenate([down, up])
    else:
        down = base - np.linspace(0, 20, n // 2 + 1)
        up = down[-1] + np.linspace(0, 10, n - n // 2 - 1)
        close = np.concatenate([down, up])
    close = close[:n]
    high = close + 1.0
    low = close - 1.0
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close,
         "volume": np.full(n, 1_000_000.0)},
        index=idx,
    )


def _episode_row(
    symbol="AAA", episode_type="reset_decline", tier=1, start_date="2020-01-06",
    anchor_date="2020-03-02", end_date="2020-03-09", resolution="durable_low",
    censored=False, reference_price=100.0, anchor_price=80.0, a0_leg=2.0,
    a0_anchor=2.0, terminated_reason=None,
) -> dict:
    return {
        "symbol": symbol, "price_plane_id": "stock_identity_ohlcv_v1",
        "episode_type": episode_type, "tier": tier,
        "start_date": pd.Timestamp(start_date),
        "anchor_date": pd.Timestamp(anchor_date) if anchor_date else pd.NaT,
        "end_date": pd.Timestamp(end_date) if end_date else pd.NaT,
        "resolution": resolution, "censored": censored,
        "depth_pct": 0.2, "depth_atr": 10.0, "duration_sessions": 40,
        "a0_leg": a0_leg, "a0_anchor": a0_anchor,
        "atr_basis": "wilder_atr14_at_prior_confirmed_close",
        "resolution_known_date": pd.Timestamp(end_date) if end_date else pd.NaT,
        "terminated_reason": terminated_reason,
        "reference_price": reference_price,
        "anchor_price": anchor_price if not censored else None,
    }


def _event_row(event_id, symbol="AAA", family_key="fam.x", known_ts="2020-02-10",
                grain="1D") -> dict:
    ts = pd.Timestamp(known_ts)
    return {
        "event_id": event_id, "family_key": family_key, "symbol": symbol,
        "signal_ts": ts, "signal_known_ts": ts, "grain": grain,
    }


def _attribution_row(event_id, symbol, episode_index, episode_type, episode_tier,
                      episode_start_date, episode_end_date, episode_resolution,
                      episode_censored, attributed, known_ts, family_key="fam.x") -> dict:
    return {
        "event_id": event_id, "family_key": family_key, "symbol": symbol,
        "signal_known_ts": pd.Timestamp(known_ts),
        "episode_index": episode_index, "episode_type": episode_type,
        "episode_tier": episode_tier, "episode_start_date": episode_start_date,
        "episode_end_date": episode_end_date, "episode_resolution": episode_resolution,
        "episode_censored": episode_censored, "attributed": attributed,
        "p_pre_sessions": 5,
    }


def _three_episode_fixture():
    """Reset (resolved), reclaim-like (resolved) and censored episodes for one symbol,
    plus events before/inside/outside attribution windows."""
    episodes = pd.DataFrame([
        _episode_row(
            symbol="AAA", episode_type="reset_decline", tier=1,
            start_date="2020-01-06", anchor_date="2020-03-02", end_date="2020-03-09",
            resolution="durable_low", censored=False,
            reference_price=100.0, anchor_price=80.0, a0_leg=2.0, a0_anchor=2.0,
        ),
        _episode_row(
            symbol="AAA", episode_type="reclaim", tier=2,
            start_date="2020-04-01", anchor_date="2020-05-01", end_date="2020-06-01",
            resolution="held", censored=False,
            reference_price=90.0, anchor_price=95.0, a0_leg=1.5, a0_anchor=1.5,
        ),
        _episode_row(
            symbol="AAA", episode_type="reset_decline", tier=1,
            start_date="2020-07-01", anchor_date=None, end_date="2020-09-01",
            resolution="censored", censored=True,
            reference_price=100.0, anchor_price=None, a0_leg=2.0, a0_anchor=None,
            terminated_reason="tape_truncated",
        ),
    ])
    ep0, ep1, ep2 = episodes.iloc[0], episodes.iloc[1], episodes.iloc[2]

    events = pd.DataFrame([
        _event_row("E_ANTICIPATE", known_ts="2020-02-25"),   # before anchor -> lead_lag<0
        _event_row("E_AFTER", known_ts="2020-03-05"),        # after anchor -> lead_lag>0
        _event_row("E_OUTSIDE", known_ts="2019-01-01"),      # outside every episode window
        _event_row("E_CENSORED", known_ts="2020-08-01"),     # inside the censored episode
    ])

    attribution = pd.DataFrame([
        _attribution_row(
            "E_ANTICIPATE", "AAA", 0, "reset_decline", 1, ep0["start_date"], ep0["end_date"],
            "durable_low", False, True, "2020-02-25",
        ),
        _attribution_row(
            "E_AFTER", "AAA", 0, "reset_decline", 1, ep0["start_date"], ep0["end_date"],
            "durable_low", False, True, "2020-03-05",
        ),
        _attribution_row(
            "E_OUTSIDE", "AAA", None, None, None, None, None, None, None, False, "2019-01-01",
        ),
        _attribution_row(
            "E_CENSORED", "AAA", 2, "reset_decline", 1, ep2["start_date"], pd.NaT,
            "censored", True, True, "2020-08-01",
        ),
    ])

    bars = {"AAA": _bars("AAA", "2019-06-01", 400)}
    return events, attribution, episodes, bars


# ---------------------------------------------------------------------------
# Task 2: per-fire metrics + unconditional block
# ---------------------------------------------------------------------------
def test_censored_episode_has_no_anchor_metrics_but_counts_unconditional():
    events, attribution, episodes, bars = _three_episode_fixture()
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)

    row = out.loc[out["episode_id"].str.contains("reset_decline") & out["signal_known_ts"].eq(pd.Timestamp("2020-08-01"))]
    assert len(row) == 1
    row = row.iloc[0]
    assert pd.isna(row["lead_lag"])
    assert pd.isna(row["atr_dist"])
    assert pd.isna(row["price_dist"])
    assert pd.isna(row["mae_after"])
    assert pd.isna(row["capture"])

    unconditional = compute_unconditional_block(events, attribution, episodes)
    aaa = unconditional.loc[unconditional["symbol"] == "AAA"].iloc[0]
    assert aaa["fires_per_name_year"] > 0
    assert aaa["total_fires"] == 4
    # E_OUTSIDE is retained (unattributed), not dropped
    assert aaa["attributed_fires"] == 3


def test_lead_lag_sign_convention_anticipate_is_negative():
    events, attribution, episodes, bars = _three_episode_fixture()
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)
    anticipate = out.loc[out["event_id"] == "E_ANTICIPATE"].iloc[0]
    after = out.loc[out["event_id"] == "E_AFTER"].iloc[0]
    assert anticipate["lead_lag"] < 0
    assert after["lead_lag"] > 0


def test_out_of_episode_fire_is_retained_for_unconditional_block_only():
    events, attribution, episodes, bars = _three_episode_fixture()
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)
    # E_OUTSIDE never attributes to an episode -> no per-fire metric row
    assert "E_OUTSIDE" not in set(out["event_id"])
    unconditional = compute_unconditional_block(events, attribution, episodes)
    aaa = unconditional.loc[unconditional["symbol"] == "AAA"].iloc[0]
    assert aaa["total_fires"] == 4
    assert aaa["episode_attribution_rate"] == pytest.approx(3 / 4)


def test_unconditional_block_reports_explicit_no_coverage_for_zero_total():
    """M10: a (family, symbol) pair in the caller's universe with NO events at all
    must appear as an EXPLICIT row (total_fires=0, fires_per_name_year=0.0,
    episode_attribution_rate=NaN, no_coverage=True) — never silently omitted. The
    prior implementation asserted the pair was simply absent (``out.empty``),
    which certified the silent-omission defect rather than catching it."""
    events = pd.DataFrame([_event_row("Z1", symbol="ZZZ")])
    events = events.iloc[0:0]  # zero rows for family/symbol pair under test
    attribution = pd.DataFrame(columns=[
        "event_id", "family_key", "symbol", "signal_known_ts", "episode_index",
        "episode_type", "episode_tier", "episode_start_date", "episode_end_date",
        "episode_resolution", "episode_censored", "attributed", "p_pre_sessions",
    ])
    episodes = pd.DataFrame(columns=["symbol", "episode_type", "tier", "start_date", "end_date"])
    out = compute_unconditional_block(events, attribution, episodes, universe=[("fam.x", "ZZZ")])
    assert len(out) == 1
    row = out.iloc[0]
    assert row["family_key"] == "fam.x"
    assert row["symbol"] == "ZZZ"
    assert row["total_fires"] == 0
    assert row["attributed_fires"] == 0
    assert row["fires_per_name_year"] == pytest.approx(0.0)
    assert pd.isna(row["episode_attribution_rate"])
    assert bool(row["no_coverage"]) is True


def test_unconditional_block_universe_none_falls_back_to_observed_pairs_only():
    """Legacy call shape (no ``universe``) still works and never fabricates
    no_coverage rows for pairs it never heard of."""
    events, attribution, episodes, bars = _three_episode_fixture()
    out = compute_unconditional_block(events, attribution, episodes)
    assert not out["no_coverage"].any()


def test_unconditional_block_universe_covers_observed_and_uncovered_pairs():
    events, attribution, episodes, bars = _three_episode_fixture()
    out = compute_unconditional_block(
        events, attribution, episodes, universe=[("fam.x", "AAA"), ("fam.x", "BBB")]
    )
    aaa = out.loc[out["symbol"] == "AAA"].iloc[0]
    bbb = out.loc[out["symbol"] == "BBB"].iloc[0]
    assert bool(aaa["no_coverage"]) is False
    assert aaa["total_fires"] == 4
    assert bool(bbb["no_coverage"]) is True
    assert bbb["total_fires"] == 0
    assert pd.isna(bbb["episode_attribution_rate"])


def test_no_ranking_or_authority_columns_in_fire_metrics_output():
    events, attribution, episodes, bars = _three_episode_fixture()
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)
    cols_lower = {str(c).lower() for c in out.columns}
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in cols_lower


def test_ruler_module_source_carries_no_ranking_vocabulary():
    tree = ast.parse(RULER_SRC.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name.lower())
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        if isinstance(node, ast.arg):
            names.add(node.arg.lower())
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in names, f"{token!r} appears as an identifier in ruler.py"


def test_fire_metric_columns_are_closed():
    events, attribution, episodes, bars = _three_episode_fixture()
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)
    assert list(out.columns) == list(FIRE_METRIC_COLUMNS)


def test_unconditional_block_columns_are_closed():
    events, attribution, episodes, bars = _three_episode_fixture()
    out = compute_unconditional_block(events, attribution, episodes)
    assert list(out.columns) == list(UNCONDITIONAL_BLOCK_COLUMNS)


def test_support_coverage_frame_has_no_realized_metric_columns():
    events, attribution, episodes, bars = _three_episode_fixture()
    out = build_support_coverage(events, attribution, episodes, bars, feature_symbols={"AAA"})
    assert list(out.columns) == list(SUPPORT_COVERAGE_COLUMNS)
    forbidden = {
        "c_loc_r", "c_loc_d", "lead_lag", "price_dist", "atr_dist", "mae_after",
        "capture", "recall_at_tier", "zone_precision", "false_start",
        "false_start_rate", "relative_order", "consistency",
    }
    assert forbidden.isdisjoint(out.columns)
    # E_OUTSIDE (unattributed, and predates any bars for AAA) is retained
    outside = out.loc[out["event_id"] == "E_OUTSIDE"].iloc[0]
    assert bool(outside["attributed"]) is False
    assert pd.isna(outside["episode_id"])
    # the censored episode's fire is retained and flagged
    censored_row = out.loc[out["event_id"] == "E_CENSORED"].iloc[0]
    assert censored_row["availability_state"] == "CENSORED"
    assert bool(censored_row["attributed"]) is True


def test_availability_state_values_are_taxonomy_tokens_or_resolved():
    """MINORS: every availability_state value is drawn from the closed freeze §7
    taxonomy, except the one deliberate non-problem state ``"resolved"``."""
    from engine.stock_identity.ruler import AVAILABILITY_TAXONOMY_TOKENS

    events, attribution, episodes, bars = _three_episode_fixture()
    out = build_support_coverage(events, attribution, episodes, bars, feature_symbols={"AAA"})
    allowed = set(AVAILABILITY_TAXONOMY_TOKENS) | {"resolved"}
    assert set(out["availability_state"]) <= allowed
    # E_OUTSIDE fires but attributes to nothing -> a real, measured non-attribution
    outside = out.loc[out["event_id"] == "E_OUTSIDE"].iloc[0]
    assert outside["availability_state"] == "MEASURED_ZERO"
    # missing-bars (no bars frame at all for the symbol) -> NO_COVERAGE
    no_bars_events = pd.DataFrame([_event_row("E_NOBARS", symbol="NOBARS")])
    no_bars_attribution = pd.DataFrame([_attribution_row(
        "E_NOBARS", "NOBARS", None, None, None, None, None, None, None, False, "2020-02-10",
    )])
    no_bars_episodes = pd.DataFrame(columns=list(episodes.columns))
    out2 = build_support_coverage(no_bars_events, no_bars_attribution, no_bars_episodes, {}, feature_symbols=set())
    assert out2.iloc[0]["availability_state"] == "NO_COVERAGE"


# ---------------------------------------------------------------------------
# Task 3: composites
# ---------------------------------------------------------------------------
def test_c_loc_r_exact_formula():
    spec = _fixture_spec()
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1}])
    out = compute_composites(row, spec)
    assert out.loc[0, "c_loc_r"] == pytest.approx(0.5 * 0.8 - spec.lambda_fs * 0.1)


def test_c_loc_d_refuses_rows_below_recall_floor():
    spec = _fixture_spec(recall_floor=0.4)
    row = pd.DataFrame([
        {"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
         "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline", "grain": "daily"},
        {"recall_at_tier": 0.1, "zone_precision": 0.8, "false_start_rate": 0.1,
         "atr_dist_median_in_zone": 0.2, "episode_type": "reset_decline", "grain": "daily"},
    ])
    out = compute_composites(row, spec)
    assert pd.notna(out.loc[0, "c_loc_d"])
    assert pd.isna(out.loc[1, "c_loc_d"])


def test_compute_composites_refuses_while_pr3_is_pending(tmp_path):
    """Pending-state branch, exercised against the restored fixture copy since
    the real shipped spec is now sealed (SI-SEALED-CAL-P1) and can no longer
    demonstrate this refusal itself -- see the sealed-state companion test
    below."""
    spec = RulerSpec.from_json(_pending_variant_of_shipped_spec_path(tmp_path))
    assert spec.pr3_pending is True
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1}])
    with pytest.raises(PendingSealedCalibrationError):
        compute_composites(row, spec)


def test_compute_composites_succeeds_on_sealed_shipped_spec():
    """Sealed-state branch of the above: PR-3's ONE-TIME SEAL (SI-SEALED-CAL-P1,
    recall_floor=0.05, lambda_fs=0.000279297) means the real shipped spec is no
    longer pending -- compute_composites must now actually compute on it
    instead of refusing."""
    spec = RulerSpec.from_json(SPEC_PATH)
    assert spec.pr3_pending is False
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
                          "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline",
                          "grain": "daily"}])
    out = compute_composites(row, spec)
    assert out.loc[0, "c_loc_r"] == pytest.approx(0.5 * 0.8 - spec.lambda_fs * 0.1)
    assert pd.notna(out.loc[0, "c_loc_d"])


def test_compute_composites_output_columns_closed_to_two_graded():
    spec = _fixture_spec()
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
                          "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline",
                          "grain": "daily"}])
    out = compute_composites(row, spec)
    assert set(spec.graded_composites) <= set(out.columns)
    assert "c_loc_r" in out.columns and "c_loc_d" in out.columns


# ---------------------------------------------------------------------------
# M5-residual: missing stratum columns REFUSE rather than silently falling back
# to a global rank
# ---------------------------------------------------------------------------
def test_compute_composites_raises_on_missing_stratum_columns():
    spec = _fixture_spec()
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
                          "atr_dist_median_in_zone": 0.3}])  # no episode_type/grain
    with pytest.raises(MissingRankStratumColumnsError):
        compute_composites(row, spec)


def test_compute_composites_raises_on_unsupported_rank_population():
    spec = _fixture_spec(c_loc_d_rank_population="some_other_stratum")
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1,
                          "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline",
                          "grain": "daily"}])
    with pytest.raises(ValueError):
        compute_composites(row, spec)


# ---------------------------------------------------------------------------
# M1: NaN recall_at_tier fails the recall-floor gate (fail-closed)
# ---------------------------------------------------------------------------
def test_c_loc_d_gated_nan_on_undefined_recall_at_tier():
    spec = _fixture_spec(recall_floor=0.4)
    row = pd.DataFrame([
        {"recall_at_tier": np.nan, "zone_precision": 0.8, "false_start_rate": 0.1,
         "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline", "grain": "daily"},
        {"recall_at_tier": 0.9, "zone_precision": 0.8, "false_start_rate": 0.1,
         "atr_dist_median_in_zone": 0.2, "episode_type": "reset_decline", "grain": "daily"},
    ])
    out = compute_composites(row, spec)
    assert pd.isna(out.loc[0, "c_loc_d"])
    assert out.loc[0, "c_loc_d_gate_reason"] == "recall_at_tier_nan"
    assert pd.notna(out.loc[1, "c_loc_d"])
    assert pd.isna(out.loc[1, "c_loc_d_gate_reason"])


def test_c_loc_d_gate_reason_distinguishes_below_floor_from_nan():
    spec = _fixture_spec(recall_floor=0.4)
    row = pd.DataFrame([
        {"recall_at_tier": 0.1, "zone_precision": 0.8, "false_start_rate": 0.1,
         "atr_dist_median_in_zone": 0.3, "episode_type": "reset_decline", "grain": "daily"},
    ])
    out = compute_composites(row, spec)
    assert out.loc[0, "c_loc_d_gate_reason"] == "below_recall_floor"


# ---------------------------------------------------------------------------
# M5: C-LOC-D rank population is stratified by (episode_type, grain)
# ---------------------------------------------------------------------------
def test_c_loc_d_ranks_within_episode_type_grain_stratum_only():
    spec = _fixture_spec(recall_floor=0.0)
    stratum_a = pd.DataFrame([
        {"recall_at_tier": 0.9, "zone_precision": 0.9, "false_start_rate": 0.0,
         "atr_dist_median_in_zone": 0.1, "episode_type": "reset_decline", "grain": "daily"},
        {"recall_at_tier": 0.9, "zone_precision": 0.9, "false_start_rate": 0.0,
         "atr_dist_median_in_zone": 0.5, "episode_type": "reset_decline", "grain": "daily"},
    ])
    out_a_alone = compute_composites(stratum_a, spec)

    stratum_b = pd.DataFrame([
        {"recall_at_tier": 0.9, "zone_precision": 0.9, "false_start_rate": 0.0,
         "atr_dist_median_in_zone": 0.01, "episode_type": "reclaim", "grain": "weekly"},
        {"recall_at_tier": 0.9, "zone_precision": 0.9, "false_start_rate": 0.0,
         "atr_dist_median_in_zone": 0.02, "episode_type": "reclaim", "grain": "weekly"},
    ])
    combined = pd.concat([stratum_a, stratum_b], ignore_index=True)
    out_combined = compute_composites(combined, spec)

    # stratum_a's own two rows' c_loc_d must be unaffected by stratum_b's presence,
    # even though stratum_b's atr_dist_median_in_zone values are all much smaller
    # (which WOULD change a global rank).
    a_rows = out_combined.loc[out_combined["episode_type"] == "reset_decline"].reset_index(drop=True)
    assert a_rows["c_loc_d"].tolist() == pytest.approx(out_a_alone["c_loc_d"].tolist())


# ---------------------------------------------------------------------------
# Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law) fixture helper: a minimal W2
# family-registry entry conferring UNRESTRICTED lawful availability
# (family_first_available=None -- "no known start boundary", the SAME
# convention family_registry.json's own committed entries use). Sol
# CONFIRMATION-1 (point 5) additionally requires a present ``provenance_class``
# field (R or B -- never P, never omitted) for a null-bound family to type
# ELIGIBLE rather than UNESTIMABLE; every "unrestricted" fixture entry now
# carries ``"provenance_class": "R"`` and a synthetic-but-truthy ``spec_hash``
# (point 3(a)'s structural receipt check) by default. No embedded ``data/``
# path in the fixture ``producer`` string, so point 3(b)'s producer-store
# check is vacuous for every fixture family, exactly like the real
# bar-derived engine families (grey_dot_macro, tier_cascade, the naive
# comparators, ...).
# ---------------------------------------------------------------------------
def _unrestricted_registry(*family_keys: str, provenance_class: str = "R") -> list[dict]:
    return [
        {
            "family_key": fk,
            "family_first_available": None,
            "provenance_class": provenance_class,
            "spec_hash": f"fixture-spec-hash::{fk}",
            "producer": "fixture synthetic producer (no data/ store dependency)",
        }
        for fk in family_keys
    ]


# ---------------------------------------------------------------------------
# B2 + M7: aggregate_cell_metrics recall denominator / flooding normalization
# ---------------------------------------------------------------------------
def _two_symbol_recall_fixture():
    """AAA fires and recalls; BBB has a tier-eligible episode of the SAME type but
    receives no fire at all from fam.x — a coverage gap the OLD fire-conditional
    denominator could never see."""
    events_aaa, attribution_aaa, episodes_aaa, bars = _three_episode_fixture()
    bbb_episode = _episode_row(
        symbol="BBB", episode_type="reset_decline", tier=1,
        start_date="2020-01-06", anchor_date="2020-03-02", end_date="2020-03-09",
        resolution="durable_low", censored=False,
        reference_price=100.0, anchor_price=80.0, a0_leg=2.0, a0_anchor=2.0,
    )
    episodes = pd.concat([episodes_aaa, pd.DataFrame([bbb_episode])], ignore_index=True)
    # fam.x also fires (and attributes) on BBB in a DIFFERENT episode_type so BBB
    # is in fam.x's symbol-coverage universe, but never fires into BBB's
    # reset_decline episode above.
    bbb_reclaim = _episode_row(
        symbol="BBB", episode_type="reclaim", tier=2,
        start_date="2020-04-01", anchor_date="2020-05-01", end_date="2020-06-01",
        resolution="held", censored=False,
        reference_price=90.0, anchor_price=95.0, a0_leg=1.5, a0_anchor=1.5,
    )
    episodes = pd.concat([episodes, pd.DataFrame([bbb_reclaim])], ignore_index=True)
    bbb_event = _event_row("E_BBB_RECLAIM", symbol="BBB", known_ts="2020-05-05")
    bbb_attr = _attribution_row(
        "E_BBB_RECLAIM", "BBB", 3, "reclaim", 2, bbb_reclaim["start_date"], bbb_reclaim["end_date"],
        "held", False, True, "2020-05-05",
    )
    events = pd.concat([events_aaa, pd.DataFrame([bbb_event])], ignore_index=True)
    attribution = pd.concat([attribution_aaa, pd.DataFrame([bbb_attr])], ignore_index=True)
    bars = dict(bars)
    bars["BBB"] = _bars("BBB", "2019-06-01", 400)
    return events, attribution, episodes, bars


def test_recall_denominator_counts_eligible_episodes_regardless_of_fire():
    events, attribution, episodes, bars = _two_symbol_recall_fixture()
    spec = _fixture_spec()
    fire_metrics = compute_fire_metrics(events, attribution, episodes, bars, spec)
    registry = _unrestricted_registry("fam.x")
    cells = aggregate_cell_metrics(
        fire_metrics, episodes, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    cell = cells.loc[
        (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
    ].iloc[0]
    # AAA's resolved reset_decline episode fired in-zone; AAA's OWN censored
    # reset_decline episode and BBB's reset_decline episode of the SAME type
    # never fired at all but are both tier-eligible. Ruling 2 (SI-W3A-RULER-V1
    # PR-3 seal law): BBB enters fam.x's recall denominator via LAWFUL
    # AVAILABILITY (an unrestricted family_registry entry + bars_by_symbol
    # coverage for BBB), never via events/fired-on coverage -> denominator = 3
    # eligible episodes (AAA's two + BBB's one), only AAA's resolved one is
    # recalled -> 1/3.
    assert cell["recall_at_tier"] == pytest.approx(1 / 3)


def test_old_fire_conditional_recall_denominator_would_have_been_wrong():
    """Named regression: a fired-on-only denominator would have reported
    recall_at_tier == 1.0 for the same fixture (only AAA's resolved episode
    ever fired) — this test fails under that behavior, both under the OLD
    events-derived universe and the new availability-based one."""
    events, attribution, episodes, bars = _two_symbol_recall_fixture()
    spec = _fixture_spec()
    fire_metrics = compute_fire_metrics(events, attribution, episodes, bars, spec)
    registry = _unrestricted_registry("fam.x")
    cells = aggregate_cell_metrics(
        fire_metrics, episodes, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    cell = cells.loc[
        (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
    ].iloc[0]
    assert cell["recall_at_tier"] != pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law): the recall-denominator eligibility
# universe is built from OUTCOME-INDEPENDENT provenance/coverage (W2 family
# registry + input bars), never from events/fired-on coverage. Sol's three
# required regressions: (a) an available symbol with eligible episodes and
# ZERO fires grows the denominator and cannot improve recall; (b) a genuinely
# not-yet-available symbol never enters the denominator; (c) missing
# eligibility evidence never falls through to fired-on coverage.
# ---------------------------------------------------------------------------
def test_recall_denominator_grows_from_available_zero_fire_symbol_ruling2_regression_a():
    """Regression (a): CCC never appears in ``events`` AT ALL (not even an
    unattributed fire) but is still ELIGIBLE via family_registry + bars, which
    GROWS the denominator and cannot improve recall -- eligibility no longer
    derives from events in any form."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    episodes_aaa_only = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    episodes_with_ccc = pd.concat([
        episodes_aaa_only,
        pd.DataFrame([_episode_row(symbol="CCC", episode_type="reset_decline", start_date="2020-02-01")]),
    ], ignore_index=True)
    # CCC has NO row anywhere in events -- fam.x never fired on it, attributed
    # or not.
    events = pd.DataFrame([
        {"event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
         "signal_known_ts": pd.Timestamp("2020-01-10"), "grain": "1D"},
    ])
    spec = _fixture_spec()
    bars = {"AAA": _bars("AAA", "2019-06-01", 400), "CCC": _bars("CCC", "2019-06-01", 400)}
    registry = _unrestricted_registry("fam.x")

    cells_aaa_only = aggregate_cell_metrics(
        fm, episodes_aaa_only, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    cells_with_ccc = aggregate_cell_metrics(
        fm, episodes_with_ccc, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    recall_aaa_only = cells_aaa_only.loc[
        (cells_aaa_only["family_key"] == "fam.x") & (cells_aaa_only["episode_type"] == "reset_decline")
    ].iloc[0]["recall_at_tier"]
    cell_with_ccc = cells_with_ccc.loc[
        (cells_with_ccc["family_key"] == "fam.x") & (cells_with_ccc["episode_type"] == "reset_decline")
    ].iloc[0]
    # AAA alone: 1 eligible episode, 1 recalled -> 1.0. Adding CCC (zero fires,
    # but lawfully available) grows the denominator to 2 -> 0.5, strictly LOWER,
    # never higher.
    assert recall_aaa_only == pytest.approx(1.0)
    assert cell_with_ccc["recall_at_tier"] == pytest.approx(0.5)
    assert cell_with_ccc["recall_at_tier"] < recall_aaa_only


def test_recall_denominator_excludes_not_yet_available_symbol_ruling2_regression_b():
    """Regression (b): a symbol whose family only became available AFTER the
    tier-eligible episode's entire window must NEVER enter the denominator,
    even though bars cover it fully."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    # DDD's episode resolves entirely in 2018 -- well before fam.x's registered
    # family_first_available of 2019-01-01. AAA's episode (default window,
    # ending 2020-03-09) postdates that boundary and must stay eligible.
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
        _episode_row(
            symbol="DDD", episode_type="reset_decline", start_date="2018-01-01",
            anchor_date="2018-02-01", end_date="2018-03-09",
        ),
    ])
    events = pd.DataFrame([
        {"event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
         "signal_known_ts": pd.Timestamp("2020-01-10"), "grain": "1D"},
    ])
    spec = _fixture_spec()
    bars = {"AAA": _bars("AAA", "2019-06-01", 400), "DDD": _bars("DDD", "2017-06-01", 400)}
    registry = [{
        "family_key": "fam.x", "family_first_available": "2019-01-01",
        "provenance_class": "R", "spec_hash": "fixture-spec-hash::fam.x",
    }]

    cells = aggregate_cell_metrics(
        fm, episodes, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    cell = cells.loc[
        (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
    ].iloc[0]
    # DDD's episode window entirely predates fam.x's family_first_available, so
    # it is NOT_YET_AVAILABLE -- excluded. Denominator is AAA's 1 episode only,
    # recalled -> 1.0, never diluted by an episode the family could not have
    # fired on.
    assert cell["recall_at_tier"] == pytest.approx(1.0)

    availability = build_family_episode_availability(
        episodes, ["fam.x"], family_registry=registry, bars_by_symbol=bars,
    )
    ddd_state = availability.loc[availability["symbol"] == "DDD", "availability_state"].iloc[0]
    assert ddd_state == "NOT_YET_AVAILABLE"


def test_recall_denominator_missing_eligibility_evidence_never_falls_through_to_fired_on_ruling2_regression_c():
    """Regression (c): with NO family_registry and NO bars_by_symbol supplied,
    lawful availability cannot be established at all -- recall_at_tier must be
    undefined (NaN, availability_state UNESTIMABLE), NEVER silently computed
    off the old fired-on (events-derived) coverage universe, even though AAA
    plainly fired and would have produced a defined value under that discarded
    read."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    events = pd.DataFrame([
        {"event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
         "signal_known_ts": pd.Timestamp("2020-01-10"), "grain": "1D"},
    ])
    spec = _fixture_spec()
    # No family_registry, no bars_by_symbol -- both default to None.
    cells = aggregate_cell_metrics(fm, episodes, spec, events)
    cell = cells.loc[
        (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
    ].iloc[0]
    assert pd.isna(cell["recall_at_tier"])

    availability = build_family_episode_availability(episodes, ["fam.x"])
    assert (availability["availability_state"] == "UNESTIMABLE").all()


def test_family_symbol_universe_empty_when_events_is_empty():
    """``events`` is no longer read for eligibility at all (Ruling 2) -- an
    empty ``events`` frame has NO effect on recall_at_tier one way or the
    other; with no family_registry/bars_by_symbol supplied (both default
    None), recall_at_tier is undefined (NaN, UNESTIMABLE), never a fabricated
    value or a raise."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    spec = _fixture_spec()
    empty_events = pd.DataFrame(columns=["event_id", "family_key", "symbol", "signal_known_ts", "grain"])
    cells = aggregate_cell_metrics(fm, episodes, spec, empty_events)
    cell = cells.loc[
        (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
    ].iloc[0]
    assert pd.isna(cell["recall_at_tier"])


# ---------------------------------------------------------------------------
# Sol CONFIRMATION-1 (SI-W3A-RULER-V1) — the availability-eligibility closed
# law narrowing Ruling 2: (1) a non-null family_first_available remains a hard
# lower bound (unchanged, already covered above); (2) a Class-P family is
# historically unavailable REGARDLESS of a null date; (3) an R/B family with a
# NULL first-available is eligible only where the SAME W2 replay/source
# machinery can establish, outcome-independently, that it was lawfully
# reconstructible (receipted spec, existing declared producer input, price-
# plane coverage, resolvable identity); (4) where source-specific availability
# cannot be established, the existing typed unavailable/unestimable state is
# returned, NEVER an eligibility inferred from the family having fired or from
# the null itself; (5) a missing registry entry or missing availability field
# (including a missing provenance_class) stays UNESTIMABLE. Sol's five
# required regressions below.
# ---------------------------------------------------------------------------
def test_class_p_family_never_eligible_regardless_of_null_date_confirmation1_regression_a():
    """Regression (a): a Class-P (prospective-only) family with a NULL
    family_first_available -- the exact shape CLASS_P_FAMILIES ships in the
    real registry -- must type STRUCTURAL_ABSENCE, never ELIGIBLE, even with
    full bars coverage. "Regardless of a null date" is the literal law: a
    Class-P family with a SET bound must also stay STRUCTURAL_ABSENCE (the
    real registry's own amber_early carries both provenance_class="P" and a
    non-null family_first_available)."""
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    bars = {"AAA": _bars("AAA", "2019-06-01", 400)}
    null_bound_registry = [{
        "family_key": "fam.p", "family_first_available": None,
        "provenance_class": "P", "producer": "prospective-only by charter",
    }]
    availability = build_family_episode_availability(
        episodes, ["fam.p"], family_registry=null_bound_registry, bars_by_symbol=bars,
    )
    assert (availability["availability_state"] == "STRUCTURAL_ABSENCE").all()
    assert (availability["availability_state"] != FAMILY_ELIGIBLE_STATE).all()

    set_bound_registry = [{
        "family_key": "fam.p", "family_first_available": "2026-08-11",
        "provenance_class": "P", "producer": "washout-promoted EARLY marker",
    }]
    availability_bound = build_family_episode_availability(
        episodes, ["fam.p"], family_registry=set_bound_registry, bars_by_symbol=bars,
    )
    assert (availability_bound["availability_state"] == "STRUCTURAL_ABSENCE").all()


def test_rb_null_bound_family_eligible_with_lawful_source_input_coverage_confirmation1_regression_b():
    """Regression (b): an R family with NULL family_first_available -- a
    receipted spec_hash, an EXISTING declared producer input store, full bars
    coverage, and a resolvable identity -- becomes ELIGIBLE. The producer
    string embeds a real committed-store path (the same convention
    confirmed_buy/rebuy/sea_event_classes use in the shipped registry); this
    test creates that path under a throwaway repo_root so the positive
    "input exists" branch is genuinely exercised, not merely vacuous."""
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    bars = {"AAA": _bars("AAA", "2019-06-01", 400)}
    registry = [{
        "family_key": "fam.rb", "family_first_available": None,
        "provenance_class": "R", "spec_hash": "fixture-spec-hash::fam.rb",
        "producer": "engine.fixture:analyze -> data/fixture_store/ledger.parquet",
    }]

    def _availability(repo_root):
        return build_family_episode_availability(
            episodes, ["fam.rb"], family_registry=registry, bars_by_symbol=bars,
            repo_root=repo_root,
        )

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "data" / "fixture_store").mkdir(parents=True)
        (tmp_root / "data" / "fixture_store" / "ledger.parquet").write_bytes(b"x")
        availability = _availability(tmp_root)
    assert (availability["availability_state"] == FAMILY_ELIGIBLE_STATE).all()


def test_rb_null_bound_family_missing_source_coverage_types_unavailable_confirmation1_regression_c():
    """Regression (c): an R family with NULL family_first_available whose
    declared producer input store is ABSENT from disk types SOURCE_FAILED
    (never ELIGIBLE, never a silent fired-on fallback) -- and separately, the
    SAME family with no receipted spec_hash at all types UNESTIMABLE (point
    3(a)'s structural receipt check)."""
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    bars = {"AAA": _bars("AAA", "2019-06-01", 400)}

    missing_store_registry = [{
        "family_key": "fam.rb", "family_first_available": None,
        "provenance_class": "R", "spec_hash": "fixture-spec-hash::fam.rb",
        "producer": "engine.fixture:analyze -> data/does_not_exist/ledger.parquet",
    }]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        availability = build_family_episode_availability(
            episodes, ["fam.rb"], family_registry=missing_store_registry, bars_by_symbol=bars,
            repo_root=Path(tmp),
        )
    assert (availability["availability_state"] == "SOURCE_FAILED").all()

    no_spec_hash_registry = [{
        "family_key": "fam.rb", "family_first_available": None,
        "provenance_class": "R", "spec_hash": None,
        "producer": "engine.fixture:pure_function",
    }]
    availability_no_spec = build_family_episode_availability(
        episodes, ["fam.rb"], family_registry=no_spec_hash_registry, bars_by_symbol=bars,
    )
    assert (availability_no_spec["availability_state"] == "UNESTIMABLE").all()


def test_zero_fire_eligible_episode_still_grows_denominator_under_narrowed_law_confirmation1_regression_d():
    """Regression (d): adding a zero-fire-but-eligible episode still GROWS the
    recall denominator under the narrowed CONFIRMATION-1 predicate (not just
    under the pre-CONFIRMATION-1 Ruling 2 shape already covered by regression
    (a) above) -- an R family, null-bound, spec-receipted, no declared
    producer-store dependency."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    episodes_aaa_only = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    episodes_with_ccc = pd.concat([
        episodes_aaa_only,
        pd.DataFrame([_episode_row(symbol="CCC", episode_type="reset_decline", start_date="2020-02-01")]),
    ], ignore_index=True)
    events = pd.DataFrame([
        {"event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
         "signal_known_ts": pd.Timestamp("2020-01-10"), "grain": "1D"},
    ])
    spec = _fixture_spec()
    bars = {"AAA": _bars("AAA", "2019-06-01", 400), "CCC": _bars("CCC", "2019-06-01", 400)}
    registry = _unrestricted_registry("fam.x")

    cells_aaa_only = aggregate_cell_metrics(
        fm, episodes_aaa_only, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    cells_with_ccc = aggregate_cell_metrics(
        fm, episodes_with_ccc, spec, events, family_registry=registry, bars_by_symbol=bars,
    )
    recall_aaa_only = cells_aaa_only.loc[
        (cells_aaa_only["family_key"] == "fam.x") & (cells_aaa_only["episode_type"] == "reset_decline")
    ].iloc[0]["recall_at_tier"]
    cell_with_ccc = cells_with_ccc.loc[
        (cells_with_ccc["family_key"] == "fam.x") & (cells_with_ccc["episode_type"] == "reset_decline")
    ].iloc[0]
    assert recall_aaa_only == pytest.approx(1.0)
    assert cell_with_ccc["recall_at_tier"] == pytest.approx(0.5)
    assert cell_with_ccc["recall_at_tier"] < recall_aaa_only


def test_no_fired_on_fallback_under_any_missing_evidence_path_confirmation1_regression_e():
    """Regression (e): AAA plainly FIRED (fam.x has a real fire on it), but
    under FOUR distinct missing-evidence paths the episode is never silently
    read as eligible via that fire -- recall_at_tier stays undefined (NaN) in
    every case: (i) missing family_registry entirely (pre-existing Ruling 2(c)
    coverage, re-asserted here); (ii) registry entry missing provenance_class
    (NEW under CONFIRMATION-1 point 5); (iii) null-bound R family missing
    spec_hash (point 3(a)); (iv) null-bound R family with a declared but
    absent producer store (point 3(b), typed SOURCE_FAILED rather than
    UNESTIMABLE, but STILL never ELIGIBLE and never fired-on)."""
    fm = pd.DataFrame([{
        "event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
        "episode_id": "AAA::reset_decline::2020-01-01",
        "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
        "signal_known_ts": pd.Timestamp("2020-01-10"),
        "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
        "mae_basis": "low", "capture": 0.5, "false_start": False,
    }])
    episodes = pd.DataFrame([
        _episode_row(symbol="AAA", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    events = pd.DataFrame([
        {"event_id": "E1", "family_key": "fam.x", "symbol": "AAA",
         "signal_known_ts": pd.Timestamp("2020-01-10"), "grain": "1D"},
    ])
    spec = _fixture_spec()
    bars = {"AAA": _bars("AAA", "2019-06-01", 400)}

    def _recall(registry):
        cells = aggregate_cell_metrics(
            fm, episodes, spec, events, family_registry=registry, bars_by_symbol=bars,
        )
        cell = cells.loc[
            (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
        ].iloc[0]
        return cell["recall_at_tier"]

    # (i) no registry supplied at all.
    assert pd.isna(_recall(None))
    # (ii) registry entry present, but no provenance_class key.
    assert pd.isna(_recall([{"family_key": "fam.x", "family_first_available": None}]))
    # (iii) R class, null bound, no spec_hash.
    assert pd.isna(_recall([{
        "family_key": "fam.x", "family_first_available": None,
        "provenance_class": "R", "spec_hash": None,
    }]))
    # (iv) R class, null bound, spec_hash present, but the declared producer
    # store does not exist -- SOURCE_FAILED, still never ELIGIBLE/fired-on.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cells = aggregate_cell_metrics(
            fm, episodes, spec, events,
            family_registry=[{
                "family_key": "fam.x", "family_first_available": None,
                "provenance_class": "R", "spec_hash": "h",
                "producer": "engine.fixture -> data/does_not_exist/ledger.parquet",
            }],
            bars_by_symbol=bars, repo_root=Path(tmp),
        )
        cell = cells.loc[
            (cells["family_key"] == "fam.x") & (cells["episode_type"] == "reset_decline")
        ].iloc[0]
        assert pd.isna(cell["recall_at_tier"])


def test_identity_unresolved_symbol_never_eligible_under_null_bound():
    """Point 3(d): a null-bound R/B family on a ticker-identity-hygiene-
    blocked symbol (the real, committed COMPUTE_BLOCKLIST -- 'ABX', a verified
    recycled symbol per engine/stock_identity/hygiene.py) types
    IDENTITY_UNRESOLVED, never ELIGIBLE, even with full bars coverage and a
    receipted spec. Uses the REAL repo_root (default) since COMPUTE_BLOCKLIST
    is a module-level constant, not config-file-driven."""
    episodes = pd.DataFrame([
        _episode_row(symbol="ABX", episode_type="reset_decline", start_date="2020-01-01"),
    ])
    bars = {"ABX": _bars("ABX", "2019-06-01", 400)}
    registry = _unrestricted_registry("fam.x")
    availability = build_family_episode_availability(
        episodes, ["fam.x"], family_registry=registry, bars_by_symbol=bars,
    )
    assert (availability["availability_state"] == "IDENTITY_UNRESOLVED").all()


# ---------------------------------------------------------------------------
# M10-minor: compute_unconditional_block raises rather than silently dropping an
# observed pair absent from a caller-supplied universe
# ---------------------------------------------------------------------------
def test_unconditional_block_raises_when_universe_omits_an_observed_pair():
    events, attribution, episodes, bars = _three_episode_fixture()
    with pytest.raises(UnconditionalBlockUniverseError):
        # events/attribution observe (fam.x, AAA); universe omits it entirely.
        compute_unconditional_block(events, attribution, episodes, universe=[("fam.other", "ZZZ")])


def test_flooding_is_invariant_to_cell_size_at_equal_density():
    """Two cells with the same fires-per-eligible-episode-session density but
    different absolute sizes must report the SAME flooding value (M7). Ruling
    2 (SI-W3A-RULER-V1 PR-3 seal law): a family's eligible-episode universe is
    now availability-based (family registry + bars), not events-derived, and
    is NOT scoped to "symbols this family happens to have fired on" — within
    ONE combined ``episodes``/``bars_by_symbol`` call every lawfully-available
    family sees every tier-eligible episode in that catalog, regardless of
    symbol. To keep the two families' eligible-episode POPULATIONS genuinely
    different sizes (the property this invariance test needs), each family is
    computed via its OWN call with only its own symbol's episodes/bars in
    scope — modeling two families whose lawful universes are legitimately
    different in size, which is what the M7 invariant is actually about."""
    small = pd.DataFrame([
        {"event_id": f"S{i}", "family_key": "fam.small", "symbol": "SMALLSYM",
         "episode_id": f"SMALLSYM::reset_decline::2020-0{(i % 3) + 1}-01",
         "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
         "signal_known_ts": pd.Timestamp("2020-01-10") + pd.Timedelta(days=i),
         "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
         "mae_basis": "low", "capture": 0.5, "false_start": False}
        for i in range(4)
    ])
    large = pd.DataFrame([
        {"event_id": f"L{i}", "family_key": "fam.large", "symbol": "LARGESYM",
         "episode_id": f"LARGESYM::reset_decline::2020-0{(i % 6) + 1}-01",
         "episode_type": "reset_decline", "episode_tier": 1, "grain": "daily",
         "signal_known_ts": pd.Timestamp("2020-01-10") + pd.Timedelta(days=i),
         "lead_lag": 0.0, "price_dist": 0.0, "atr_dist": 0.1, "mae_after": 0.0,
         "mae_basis": "low", "capture": 0.5, "false_start": False}
        for i in range(8)
    ])
    fm = pd.concat([small, large], ignore_index=True)
    # small: 3 eligible episodes, 4 fires -> density 4/3. large: 6 eligible
    # episodes, 8 fires -> density 8/6 == 4/3. Equal density, different size.
    small_eps = pd.DataFrame([
        _episode_row(symbol="SMALLSYM", episode_type="reset_decline", start_date=f"2020-0{k}-01")
        for k in range(1, 4)
    ])
    large_eps = pd.DataFrame([
        _episode_row(symbol="LARGESYM", episode_type="reset_decline", start_date=f"2020-0{k}-01")
        for k in range(1, 7)
    ])
    spec = _fixture_spec()
    small_events = pd.DataFrame({
        "event_id": small["event_id"], "family_key": small["family_key"], "symbol": small["symbol"],
        "signal_known_ts": small["signal_known_ts"], "grain": small["grain"],
    })
    large_events = pd.DataFrame({
        "event_id": large["event_id"], "family_key": large["family_key"], "symbol": large["symbol"],
        "signal_known_ts": large["signal_known_ts"], "grain": large["grain"],
    })
    small_bars = {"SMALLSYM": _bars("SMALLSYM", "2019-06-01", 400)}
    large_bars = {"LARGESYM": _bars("LARGESYM", "2019-06-01", 400)}

    small_cells = aggregate_cell_metrics(
        small, small_eps, spec, small_events,
        family_registry=_unrestricted_registry("fam.small"), bars_by_symbol=small_bars,
    )
    large_cells = aggregate_cell_metrics(
        large, large_eps, spec, large_events,
        family_registry=_unrestricted_registry("fam.large"), bars_by_symbol=large_bars,
    )
    small_cell = small_cells.loc[small_cells["family_key"] == "fam.small"].iloc[0]
    large_cell = large_cells.loc[large_cells["family_key"] == "fam.large"].iloc[0]
    assert small_cell["flooding"] == pytest.approx(large_cell["flooding"])
    assert small_cell["flooding"] == pytest.approx((4 / 3) / spec.useful_zone_window_sessions)


# ---------------------------------------------------------------------------
# M6: mae_after is strictly forward-from-fire and records its basis
# ---------------------------------------------------------------------------
def test_mae_after_never_uses_pre_fire_bars_for_a_lagging_fire():
    idx = pd.bdate_range("2020-01-01", periods=60)
    close = np.full(60, 100.0)
    # a severe dip strictly BEFORE the fire's known_ts -- must NEVER affect mae_after
    close[10:15] = 50.0
    # a moderate dip strictly AFTER known_ts -- the only bars mae_after may see
    close[35:40] = 90.0
    bars = pd.DataFrame(
        {"open": close, "high": close + 1.0, "low": close - 1.0, "close": close,
         "volume": np.full(60, 1_000_000.0)},
        index=idx,
    )
    known_ts = idx[30]
    anchor_date = idx[5]  # anchor sits WELL before known_ts -> a lagging fire
    episode = _episode_row(
        symbol="LAG", episode_type="reset_decline", tier=1,
        start_date=idx[0].isoformat(), anchor_date=anchor_date.isoformat(),
        end_date=idx[45].isoformat(), resolution="durable_low", censored=False,
        reference_price=100.0, anchor_price=100.0, a0_leg=2.0, a0_anchor=2.0,
    )
    episodes = pd.DataFrame([episode])
    events = pd.DataFrame([_event_row("E_LAG", symbol="LAG", known_ts=known_ts.isoformat())])
    attribution = pd.DataFrame([_attribution_row(
        "E_LAG", "LAG", 0, "reset_decline", 1, episode["start_date"], episode["end_date"],
        "durable_low", False, True, known_ts.isoformat(),
    )])
    spec = _fixture_spec()  # useful_zone_window_sessions == 15
    out = compute_fire_metrics(events, attribution, episodes, {"LAG": bars}, spec)
    row = out.iloc[0]
    assert row["mae_basis"] == "low"
    # forward window is idx[31:46] -> catches the 35:40 dip (low=89), never the
    # pre-fire 10:15 dip (low=49, which would give mae_after=25.5 if the bug
    # were still present).
    assert row["mae_after"] == pytest.approx((100.0 - 89.0) / 2.0)


def test_mae_after_falls_back_to_close_when_low_column_absent():
    idx = pd.bdate_range("2020-01-01", periods=30)
    close = np.full(30, 100.0)
    close[15:18] = 92.0
    bars = pd.DataFrame({"open": close, "high": close, "close": close,
                          "volume": np.full(30, 1_000_000.0)}, index=idx)
    known_ts = idx[10]
    episode = _episode_row(
        symbol="NOLOW", episode_type="reset_decline", tier=1,
        start_date=idx[0].isoformat(), anchor_date=idx[2].isoformat(),
        end_date=idx[25].isoformat(), resolution="durable_low", censored=False,
        reference_price=100.0, anchor_price=100.0, a0_leg=2.0, a0_anchor=2.0,
    )
    episodes = pd.DataFrame([episode])
    events = pd.DataFrame([_event_row("E_NL", symbol="NOLOW", known_ts=known_ts.isoformat())])
    attribution = pd.DataFrame([_attribution_row(
        "E_NL", "NOLOW", 0, "reset_decline", 1, episode["start_date"], episode["end_date"],
        "durable_low", False, True, known_ts.isoformat(),
    )])
    spec = _fixture_spec()
    out = compute_fire_metrics(events, attribution, episodes, {"NOLOW": bars}, spec)
    row = out.iloc[0]
    assert row["mae_basis"] == "close"
    assert row["mae_after"] == pytest.approx((100.0 - 92.0) / 2.0)
