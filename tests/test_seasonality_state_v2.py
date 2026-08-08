"""W5 — ``neuralweb.biopharma_seasonality_state.v2``: the multi-clock state.

The tests that carry weight here are the ones about a MIGRATION that has not
happened yet, because the defect this schema exists to prevent is a future one:

* ``TestFrozenV1Semantic`` pins that ``forecast`` cannot exist on a v2 state at
  all.  ``v1.forecast.p`` is a historical positive-year share, and the failure
  mode is a later session fitting a model and writing its output into a field
  that is already there, already plumbed, and already called ``p``.  Every
  downstream reader would keep reading, and nothing in the payload would record
  that the meaning changed.  Deprecating the name is not enough — the name is
  ABSENT, so the test is "does writing it raise".
* ``TestCalibratedEstimate`` pins that the replacement slot cannot be filled
  loosely.  A calibrated estimate without a calibration version, a model
  version, AND a data cutoff cannot be audited, reproduced, or checked for
  leakage, so a payload carrying two of the three is refused rather than
  accepted-with-a-flag.
* ``TestDualReadEquivalence`` feeds a v1 file and a v2 file carrying the SAME
  underlying numbers and asserts the attached candidate block is byte-equal.
  That is the whole claim of the migration — a rename, not a reinterpretation —
  and it is the one claim a reader cannot verify by eye.
* ``TestNoFusion`` searches the emitted block for any number that is the
  product or the sum of a seasonality number and another engine's number.
  Seasonality computes no combined weight, discount, or fused score; a fused
  number is how a display-tier context block becomes an authority it never
  earned.
* ``TestMeasuredNotAsserted`` pins that the contradiction and overlap slots
  cannot go quiet.  v1 carried both as a free-text ``hooks`` blob attached
  AFTER validation, so the two facts the lobe most needed to be honest about
  were the two the contract never checked.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.seasonality import contracts, state as season_state  # noqa: E402
from scripts import build_seasonality_shadow_state as emitter  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "seasonality"
_NOW = datetime(2026, 8, 2, 4, 0, 0, tzinfo=timezone.utc)

_SHA = "sha256:" + "a" * 64
_SHB = "sha256:" + "b" * 64


# ---------------------------------------------------------------------------
# Builders — ONE pair of payloads carrying identical numbers under both schemas
# ---------------------------------------------------------------------------

#: The numbers both schemas describe.  Written once so "the same underlying
#: numbers" is enforced by construction rather than by two literals matching.
_NUMBERS = {
    "p": 0.72,
    "p_baseline": 0.61,
    "edge": 0.11,
    "ci90": [0.55, 0.86],
    "n_years": 18,
    "live_n": 3,
    "start_doy": 284,
    "end_doy": 344,
    "occurrence_end_date": "2026-12-10",
    "phase": "pre_window",
    "asof": "2026-07-03",
    "available_at": "2026-07-03T00:00:00Z",
    "expires_at": "2026-07-07T00:00:00Z",
    "flags": ["forward_sample_thin"],
}


def _evidence(**overrides) -> dict:
    return {
        "n_independent": _NUMBERS["n_years"],
        "n_issuers": 1,
        "n_date_clusters": _NUMBERS["n_years"],
        "live_n": _NUMBERS["live_n"],
        "q_by": None,
        "p_max_t": None,
        "spa_p": None,
        **overrides,
    }


def _provenance() -> dict:
    return {
        "model_version": "seasonality-calendar-v1",
        "pattern_spec_hash": _SHA,
        "data_snapshot": _SHB,
    }


def _v1_state(ticker: str = "FIXTURE_BUY", *, abstain: bool = False) -> dict:
    return contracts.build_neuralweb_state(
        artifact_id="data-neuralweb-biopharma-seasonality-state",
        entity={"type": "issuer", "id": f"ticker:{ticker}", "ticker": ticker},
        asof=_NUMBERS["asof"],
        available_at=_NUMBERS["available_at"],
        expires_at=_NUMBERS["expires_at"],
        clock={
            "type": "calendar",
            "phase": _NUMBERS["phase"],
            "start_doy": _NUMBERS["start_doy"],
            "end_doy": _NUMBERS["end_doy"],
            "occurrence_end_date": _NUMBERS["occurrence_end_date"],
        },
        forecast={
            "target": "default_window_return_gt_0",
            "horizon_td": 160,
            "p": _NUMBERS["p"],
            "p_baseline": _NUMBERS["p_baseline"],
            "edge": _NUMBERS["edge"],
            "ci90": list(_NUMBERS["ci90"]),
            "baseline_basis": "same_length_all_starts_mean",
        },
        evidence=_evidence(),
        uncertainty={"abstain": abstain, "flags": list(_NUMBERS["flags"])},
        provenance=_provenance(),
    )


def _v2_state(
    ticker: str = "FIXTURE_BUY",
    *,
    abstain: bool = False,
    calibrated_estimate: dict | None = None,
) -> dict:
    """The SAME numbers as :func:`_v1_state`, under the v2 names."""
    return contracts.build_neuralweb_state_v2(
        artifact_id="data-neuralweb-biopharma-seasonality-state",
        entity={"type": "issuer", "id": f"ticker:{ticker}", "ticker": ticker},
        asof=_NUMBERS["asof"],
        available_at=_NUMBERS["available_at"],
        expires_at=_NUMBERS["expires_at"],
        clocks=[
            {
                "type": "calendar",
                "phase": _NUMBERS["phase"],
                "window": {
                    "start_doy": _NUMBERS["start_doy"],
                    "end_doy": _NUMBERS["end_doy"],
                    "occurrence_end_date": _NUMBERS["occurrence_end_date"],
                },
                "evidence": {"n_years": _NUMBERS["n_years"]},
            }
        ],
        historical_up_share={
            "target": "default_window_return_gt_0",
            "horizon_td": 160,
            "p": _NUMBERS["p"],
            "p_baseline": _NUMBERS["p_baseline"],
            "edge": _NUMBERS["edge"],
            "ci90": list(_NUMBERS["ci90"]),
            # The Wilson interval bounds the SHARE, not the next outcome.
            "ci90_kind": "parameter_ci",
            "n_years": _NUMBERS["n_years"],
            "basis": "same_length_all_starts_mean",
        },
        calibrated_estimate=calibrated_estimate,
        contradiction=season_state.measure_contradiction(calendar_phase=_NUMBERS["phase"]),
        overlap=season_state.measure_overlap(None, ticker),
        evidence=_evidence(),
        uncertainty={"abstain": abstain, "flags": list(_NUMBERS["flags"])},
        provenance=_provenance(),
    )


def _full_estimate(**overrides) -> dict:
    return {
        "kind": "probability",
        "value": 0.66,
        "baseline": 0.61,
        "edge": 0.05,
        "calibration_version": "isotonic-2026-08",
        "model_version": "seasonality-calibrated-v1",
        "data_cutoff": "2026-06-30",
        **overrides,
    }


# ---------------------------------------------------------------------------
# 1. The v1 semantic is frozen — there is nowhere to write a calibrated p
# ---------------------------------------------------------------------------


class TestFrozenV1Semantic:
    def test_v2_has_no_forecast_key_at_all(self):
        assert "forecast" not in _v2_state()

    def test_writing_a_forecast_onto_a_v2_state_is_refused(self):
        """The migration hazard, made structural rather than advisory."""
        state = _v2_state()
        state["forecast"] = {"p": 0.91}
        with pytest.raises(contracts.ContractError, match="forecast"):
            contracts.validate_neuralweb_state_v2(state)

    @pytest.mark.parametrize(
        "key", ["score", "combined_score", "weight", "combined_weight", "discount", "rank"]
    )
    def test_fused_score_vocabulary_is_refused(self, key):
        state = _v2_state()
        state[key] = 0.5
        with pytest.raises(contracts.ContractError):
            contracts.validate_neuralweb_state_v2(state)

    @pytest.mark.parametrize(
        "key", ["model_version", "calibration_version", "data_cutoff", "calibrated"]
    )
    def test_historical_up_share_cannot_wear_model_provenance(self, key):
        """A realized frequency has no model and no cutoff.

        A payload that gives it one is describing a fitted estimate under the
        honest object's name — the same smuggle as writing into ``forecast.p``,
        one level down.
        """
        state = _v2_state()
        state["historical_up_share"][key] = "whatever"
        with pytest.raises(contracts.ContractError, match=key):
            contracts.validate_neuralweb_state_v2(state)

    def test_edge_must_still_equal_p_minus_baseline(self):
        state = _v2_state()
        state["historical_up_share"]["edge"] = 0.30
        with pytest.raises(contracts.ContractError, match="edge"):
            contracts.validate_neuralweb_state_v2(state)

    def test_ci90_must_contain_p(self):
        state = _v2_state()
        state["historical_up_share"]["ci90"] = [0.10, 0.40]  # excludes p=0.72
        with pytest.raises(contracts.ContractError, match="ci90"):
            contracts.validate_neuralweb_state_v2(state)


# ---------------------------------------------------------------------------
# 2. calibrated_estimate — null now, and impossible to fill loosely later
# ---------------------------------------------------------------------------


class TestCalibratedEstimate:
    def test_null_is_valid_and_is_what_the_emitter_produces(self, tmp_path):
        assert _v2_state()["calibrated_estimate"] is None
        assert season_state.CALIBRATED_ESTIMATE is None
        states = _emit(tmp_path)
        assert states, "the emitter produced no states to check"
        for symbol, state in states.items():
            assert state["calibrated_estimate"] is None, symbol

    def test_the_key_may_not_simply_be_omitted(self):
        """Absent reads as an oversight; explicit null reads as a statement."""
        state = _v2_state()
        del state["calibrated_estimate"]
        with pytest.raises(contracts.ContractError, match="calibrated_estimate"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_fully_provenanced_estimate_is_accepted(self):
        contracts.validate_neuralweb_state_v2(
            _v2_state(calibrated_estimate=_full_estimate())
        )

    @pytest.mark.parametrize(
        "missing", ["calibration_version", "model_version", "data_cutoff"]
    )
    def test_each_provenance_field_is_required(self, missing):
        """Two of three is refused. Each alone is uninterpretable."""
        estimate = _full_estimate()
        del estimate[missing]
        with pytest.raises(contracts.ContractError, match=missing):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    @pytest.mark.parametrize(
        "blank", ["", "   ", None]
    )
    def test_a_blank_provenance_field_does_not_count_as_present(self, blank):
        estimate = _full_estimate(calibration_version=blank)
        with pytest.raises(contracts.ContractError, match="calibration_version"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    def test_kind_is_a_closed_vocabulary(self):
        with pytest.raises(contracts.ContractError, match="kind"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=_full_estimate(kind="probability_ish"))
            )

    def test_a_probability_kind_must_carry_a_probability(self):
        with pytest.raises(contracts.ContractError, match="value"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=_full_estimate(value=1.4))
            )


class TestUncertaintyKind:
    """An interval that does not say WHICH interval it is is the defect."""

    def test_an_interval_requires_uncertainty_kind(self):
        estimate = _full_estimate(ci90=[0.55, 0.80])
        with pytest.raises(contracts.ContractError, match="uncertainty_kind"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    @pytest.mark.parametrize(
        "kind", ["parameter_ci", "predictive_interval", "outcome_quantiles"]
    )
    def test_each_named_kind_is_accepted(self, kind):
        estimate = _full_estimate(ci90=[0.55, 0.80], uncertainty_kind=kind)
        contracts.validate_neuralweb_state_v2(
            _v2_state(calibrated_estimate=estimate)
        )

    def test_the_generic_label_interval_is_forbidden_as_a_kind(self):
        estimate = _full_estimate(ci90=[0.55, 0.80], uncertainty_kind="interval")
        with pytest.raises(contracts.ContractError, match="uncertainty_kind"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    @pytest.mark.parametrize("label", ["interval", "ci", "band", "range", "uncertainty"])
    def test_the_generic_label_is_forbidden_as_a_field_name(self, label):
        """A parameter CI and a predictive interval plot identically.

        A payload that says only "interval" has already lost the distinction,
        so the word cannot appear as the field carrying the numbers either.
        """
        estimate = _full_estimate(**{label: [0.55, 0.80]})
        with pytest.raises(contracts.ContractError, match=label):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    def test_a_quantiles_kind_carries_an_interval_by_construction(self):
        estimate = {
            "kind": "quantiles",
            "quantiles": {"q05": -0.08, "q50": 0.01, "q95": 0.11},
            "calibration_version": "isotonic-2026-08",
            "model_version": "seasonality-calibrated-v1",
            "data_cutoff": "2026-06-30",
        }
        with pytest.raises(contracts.ContractError, match="uncertainty_kind"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )
        estimate["uncertainty_kind"] = "outcome_quantiles"
        contracts.validate_neuralweb_state_v2(
            _v2_state(calibrated_estimate=estimate)
        )

    @pytest.mark.parametrize(
        "smuggled",
        [
            {"ci95": [0.4, 0.8]},
            {"ci99": [0.4, 0.8]},
            {"confidence_interval": [0.4, 0.8]},
            {"credible_interval": [0.4, 0.8]},
            {"lower": 0.4, "upper": 0.8},
            {"p05": 0.4, "p95": 0.8},
            {"stderr": 0.01},
            {"sigma": 0.01},
            {"hdi": [0.4, 0.8]},
            {"error_bars": [0.4, 0.8]},
        ],
    )
    def test_an_interval_cannot_arrive_under_a_name_nothing_checks(self, smuggled):
        """The requirement is triggered by CONTENT, not by one hardcoded key.

        Requiring ``uncertainty_kind`` only when the key is literally spelled
        ``ci90`` is not a law about intervals, it is a law about one string:
        ``ci95``, ``credible_interval``, ``lower``/``upper``, ``p05``/``p95``
        and ``stderr`` are all the same object under names the check never looks
        for.  The vocabulary is CLOSED instead, so an unrecognised key is
        refused by name rather than tested against a list of words someone
        thought of in advance.
        """
        with pytest.raises(contracts.ContractError, match="unknown key"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=_full_estimate(**smuggled))
            )

    def test_the_closed_vocabulary_still_accepts_every_legitimate_field(self):
        contracts.validate_neuralweb_state_v2(
            _v2_state(
                calibrated_estimate={
                    "kind": "probability",
                    "value": 0.66,
                    "baseline": 0.61,
                    "edge": 0.05,
                    "ci90": [0.55, 0.80],
                    "uncertainty_kind": "parameter_ci",
                    "calibration_version": "isotonic-2026-08",
                    "model_version": "seasonality-calibrated-v1",
                    "data_cutoff": "2026-06-30",
                }
            )
        )

    def test_an_interval_that_excludes_its_own_estimate_is_refused(self):
        """v1's ``_validate_forecast`` enforced containment; v2 must not lose it.

        An interval that does not contain the number it is an interval FOR is
        not a wider read — it is two numbers from different objects printed side
        by side, and it plots as an ordinary error bar.
        """
        estimate = _full_estimate(
            value=0.99, ci90=[0.1, 0.2], uncertainty_kind="parameter_ci"
        )
        with pytest.raises(contracts.ContractError, match="ci90 must contain"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    @pytest.mark.parametrize("ci", [[-5.0, 7.0], [0.5, 1.4], [-0.2, 0.9]])
    def test_a_probability_interval_must_lie_in_zero_one(self, ci):
        estimate = _full_estimate(
            value=0.66, ci90=ci, uncertainty_kind="parameter_ci"
        )
        with pytest.raises(contracts.ContractError, match=r"ci90\[[01]\]"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    def test_an_expectation_interval_may_leave_zero_one_but_must_contain_the_value(self):
        contracts.validate_neuralweb_state_v2(
            _v2_state(
                calibrated_estimate=_full_estimate(
                    kind="expectation",
                    value=-0.03,
                    ci90=[-0.20, 0.14],
                    uncertainty_kind="predictive_interval",
                )
            )
        )
        with pytest.raises(contracts.ContractError, match="ci90 must contain"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(
                    calibrated_estimate=_full_estimate(
                        kind="expectation",
                        value=-0.90,
                        ci90=[-0.20, 0.14],
                        uncertainty_kind="predictive_interval",
                    )
                )
            )

    @pytest.mark.parametrize(
        "quantiles",
        [
            {"q05": 0.9, "q95": 0.1},              # crossed
            {"q05": 0.1, "q50": 0.9, "q95": 0.5},  # median above the upper tail
        ],
    )
    def test_non_monotone_quantiles_are_refused(self, quantiles):
        """A swapped pair is not a wide distribution; it plots as an ordinary fan."""
        estimate = {
            "kind": "quantiles",
            "quantiles": quantiles,
            "uncertainty_kind": "outcome_quantiles",
            "calibration_version": "isotonic-2026-08",
            "model_version": "seasonality-calibrated-v1",
            "data_cutoff": "2026-06-30",
        }
        with pytest.raises(contracts.ContractError, match="non-monotone"):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )

    @pytest.mark.parametrize(
        "label",
        [
            "median", "low", "q", "q0", "q00", "p05",
            # Ambiguous rather than more precise: q100 reads as both the 100th
            # percentile and the 10.0th, and a label whose level is a guess
            # cannot order anything.
            "q100", "q995",
        ],
    )
    def test_a_quantile_label_that_cannot_be_ORDERED_is_refused(self, label):
        """Ordering is what makes monotonicity checkable at all."""
        estimate = {
            "kind": "quantiles",
            "quantiles": {label: 0.1, "q95": 0.9},
            "uncertainty_kind": "outcome_quantiles",
            "calibration_version": "isotonic-2026-08",
            "model_version": "seasonality-calibrated-v1",
            "data_cutoff": "2026-06-30",
        }
        with pytest.raises(contracts.ContractError):
            contracts.validate_neuralweb_state_v2(
                _v2_state(calibrated_estimate=estimate)
            )


class TestHistoricalShareIntervalsNameThemselves:
    """The one interval that actually SHIPS is not exempt from the same law.

    ``calibrated_estimate`` is null everywhere the emitter produces, so the
    ``uncertainty_kind`` law guarded a field nothing writes — while
    ``historical_up_share`` shipped a Wilson ``ci90`` AND a quantile map with
    neither labelled.  They are different objects: the ci90 bounds the realized
    SHARE, the quantiles describe one future window's RETURN.
    """

    def test_the_emitter_labels_both_of_its_intervals(self, tmp_path):
        for symbol, state in _emit(tmp_path).items():
            share = state["historical_up_share"]
            assert share["ci90_kind"] == "parameter_ci", symbol
            assert share["quantiles_kind"] == "outcome_quantiles", symbol

    def test_an_unlabelled_ci90_is_refused(self):
        state = _v2_state()
        del state["historical_up_share"]["ci90_kind"]
        with pytest.raises(contracts.ContractError, match="ci90_kind"):
            contracts.validate_neuralweb_state_v2(state)

    def test_the_ci90_may_not_be_relabelled_as_a_predictive_interval(self):
        """A Wilson interval on a realized share bounds the FREQUENCY."""
        state = _v2_state()
        state["historical_up_share"]["ci90_kind"] = "predictive_interval"
        with pytest.raises(contracts.ContractError, match="ci90_kind"):
            contracts.validate_neuralweb_state_v2(state)

    def test_unlabelled_quantiles_are_refused(self):
        state = _v2_state()
        state["historical_up_share"]["quantiles"] = {"q05": -0.04, "q95": 0.11}
        with pytest.raises(contracts.ContractError, match="quantiles_kind"):
            contracts.validate_neuralweb_state_v2(state)

    def test_the_share_quantiles_must_be_monotone_too(self):
        state = _v2_state()
        state["historical_up_share"]["quantiles"] = {"q05": 0.11, "q95": -0.04}
        state["historical_up_share"]["quantiles_kind"] = "outcome_quantiles"
        with pytest.raises(contracts.ContractError, match="non-monotone"):
            contracts.validate_neuralweb_state_v2(state)

    @pytest.mark.parametrize("label", ["interval", "ci", "band", "range", "uncertainty"])
    def test_a_generic_label_is_forbidden_on_the_share_as_well(self, label):
        state = _v2_state()
        state["historical_up_share"][label] = [0.55, 0.86]
        with pytest.raises(contracts.ContractError, match=label):
            contracts.validate_neuralweb_state_v2(state)


class TestV1ChecksThatMustNotBeLostInTheRename:
    """A rename that quietly drops a check is a loosening wearing a migration's name."""

    @pytest.mark.parametrize("bad", [-5, 0, 1.5, True, "160", None])
    def test_horizon_td_is_still_a_positive_integer(self, bad):
        """v1's ``_validate_forecast`` refused this; v2 must not accept it.

        The migration is advertised as 'the same arithmetic on the numbers that
        carried over'.  ``horizon_td`` carried over and stopped being checked.
        """
        state = _v2_state()
        state["historical_up_share"]["horizon_td"] = bad
        with pytest.raises(contracts.ContractError, match="horizon_td"):
            contracts.validate_neuralweb_state_v2(state)

    def test_horizon_td_may_not_simply_be_omitted(self):
        state = _v2_state()
        del state["historical_up_share"]["horizon_td"]
        with pytest.raises(contracts.ContractError, match="horizon_td"):
            contracts.validate_neuralweb_state_v2(state)

    def test_target_is_still_required(self):
        state = _v2_state()
        del state["historical_up_share"]["target"]
        with pytest.raises(contracts.ContractError, match="target"):
            contracts.validate_neuralweb_state_v2(state)

    def test_every_field_v1_validated_is_still_validated(self):
        """Enumerated so a future rename cannot drop one silently."""
        import inspect  # noqa: PLC0415

        v1_source = inspect.getsource(contracts._validate_forecast)
        v2_source = inspect.getsource(contracts._validate_historical_up_share)
        for field in ("target", "horizon_td", "p", "p_baseline", "edge", "ci90"):
            assert field in v1_source, f"the v1 baseline no longer checks {field}"
            assert field in v2_source, (
                f"{field} was validated by v1 and is unchecked in v2 — the rename "
                "loosened the contract"
            )


# ---------------------------------------------------------------------------
# 3. Clocks — a list, one per type, never empty
# ---------------------------------------------------------------------------


class TestClocks:
    def test_clocks_is_a_list(self):
        clocks = _v2_state()["clocks"]
        assert isinstance(clocks, list) and len(clocks) == 1
        assert clocks[0]["type"] == "calendar"

    def test_an_empty_clock_list_is_refused(self):
        state = _v2_state()
        state["clocks"] = []
        with pytest.raises(contracts.ContractError, match="clocks"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_duplicate_clock_type_is_refused(self):
        """Uniqueness is what makes 'the calendar clock' a deterministic read."""
        state = _v2_state()
        state["clocks"] = state["clocks"] + [dict(state["clocks"][0])]
        with pytest.raises(contracts.ContractError, match="twice"):
            contracts.validate_neuralweb_state_v2(state)

    def test_several_distinct_clock_types_are_accepted(self):
        state = _v2_state()
        state["clocks"] = state["clocks"] + [
            {"type": "regime", "phase": "expansion", "window": {}, "evidence": {}}
        ]
        validated = contracts.validate_neuralweb_state_v2(state)
        assert [c["type"] for c in validated["clocks"]] == ["calendar", "regime"]

    def test_the_projection_still_reads_the_calendar_clock(self):
        state = _v2_state()
        state["clocks"] = [
            {"type": "regime", "phase": "expansion", "window": {}, "evidence": {}}
        ] + state["clocks"]
        block = contracts.seasonality_state_projection(state)["block"]
        assert block["phase"] == _NUMBERS["phase"]
        assert block["start_doy"] == _NUMBERS["start_doy"]

    def test_an_unknown_clock_type_is_refused(self):
        state = _v2_state()
        state["clocks"][0]["type"] = "astrological"
        with pytest.raises(contracts.ContractError, match="type"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_state_with_no_calendar_clock_is_refused(self):
        """``historical_up_share`` IS a calendar-window statistic.

        A state publishing that share while declaring no calendar clock is a
        number about a period it never names — and it is not merely untidy: the
        projection falls back to an empty window, emits a ``p`` with a NULL
        start/end/occurrence_end_date, and ``register_rows`` then dies inside
        ``date.fromisoformat(None)``.  A CONTRACT-VALID payload would take the
        whole nightly out before the state file is written.
        """
        state = _v2_state()
        state["clocks"] = [
            {"type": "event", "phase": "pdufa_pending", "window": {}, "evidence": {}}
        ]
        with pytest.raises(contracts.ContractError, match="calendar"):
            contracts.validate_neuralweb_state_v2(state)

    @pytest.mark.parametrize(
        "window",
        [
            {},
            {"start_doy": 284, "end_doy": 344},                       # no end date
            {"start_doy": 284, "occurrence_end_date": "2026-12-10"},  # no end_doy
            {"start_doy": 344, "end_doy": 284, "occurrence_end_date": "2026-12-10"},
            {"start_doy": 0, "end_doy": 344, "occurrence_end_date": "2026-12-10"},
            {"start_doy": 284, "end_doy": 344, "occurrence_end_date": "not-a-date"},
            {"start_doy": 284, "end_doy": 344, "occurrence_end_date": None},
        ],
    )
    def test_a_calendar_clock_must_carry_the_window_every_reader_projects(
        self, window
    ):
        state = _v2_state()
        state["clocks"][0]["window"] = window
        with pytest.raises(contracts.ContractError):
            contracts.validate_neuralweb_state_v2(state)

    def test_the_emitter_never_produces_a_null_windowed_ledger_row(self, tmp_path):
        """End to end: what the contract refuses, the ledger writer never sees."""
        states = _emit(tmp_path)
        rows = season_state.register_rows(states, set(), date(2026, 8, 2))
        assert rows, "the emitter registered nothing to check"
        for row in rows:
            assert row["occurrence_end_date"]
            assert isinstance(row["start_doy"], int)
            date.fromisoformat(row["occurrence_end_date"])


# ---------------------------------------------------------------------------
# 3b. Point-in-time and the TTL — the two clocks a consumer trusts blindly
# ---------------------------------------------------------------------------


class TestPointInTimeAndTTL:
    def test_expires_at_must_be_later_than_available_at(self):
        """The check the whole expiry mechanism rests on.

        Both readers drop a state whose ``expires_at`` has passed.  A state
        born with ``expires_at`` BEFORE ``available_at`` therefore validates and
        is then dropped as 'expired' on every read for the rest of time — the
        lobe goes dark and every gap note says the context expired by design.
        """
        state = _v2_state()
        state["expires_at"] = "2026-07-02T00:00:00Z"  # before available_at
        with pytest.raises(contracts.ContractError, match="expires_at"):
            contracts.validate_neuralweb_state_v2(state)

    def test_an_equal_expiry_is_a_state_that_is_born_dead(self):
        state = _v2_state()
        state["expires_at"] = state["available_at"]
        with pytest.raises(contracts.ContractError, match="expires_at"):
            contracts.validate_neuralweb_state_v2(state)

    def test_the_emitter_stamps_the_declared_ttl(self):
        assert season_state.TTL_HOURS == 48
        state = _v2_state()
        span = datetime.fromisoformat(
            state["expires_at"].replace("Z", "+00:00")
        ) - datetime.fromisoformat(state["available_at"].replace("Z", "+00:00"))
        assert span.total_seconds() > 0

    def test_an_asof_after_available_at_is_a_look_ahead_and_is_refused(self):
        """A state cannot be folded from data that had not arrived yet.

        ``asof`` is the vintage of the DATA; ``available_at`` is when the state
        came into existence.  v1 left this unchecked and the only defence was
        producer-side, which a hand-built or third-party state walks straight
        past — arriving with ``as_of: 2099-12-31`` on a block the model reads
        as today's.
        """
        state = _v2_state()
        state["asof"] = "2099-12-31"
        with pytest.raises(contracts.ContractError, match="asof"):
            contracts.validate_neuralweb_state_v2(state)

    @pytest.mark.parametrize("bad", ["not-a-date", "", None, "07/03/2026"])
    def test_an_unparseable_asof_is_refused_rather_than_passed_through(self, bad):
        state = _v2_state()
        state["asof"] = bad
        with pytest.raises(contracts.ContractError, match="asof"):
            contracts.validate_neuralweb_state_v2(state)

    def test_an_asof_on_the_build_day_itself_is_fine(self):
        state = _v2_state()
        state["asof"] = state["available_at"][:10]
        contracts.validate_neuralweb_state_v2(state)

    def test_the_two_independence_counts_may_not_disagree(self):
        """One count, written twice — so it cannot depend on which key is read.

        The projection resolves ``n_years`` from ``historical_up_share`` for v2
        and from ``evidence.n_independent`` for v1.  Left uncrosschecked, a
        producer writing different numbers hands the consumer block one count
        and the forward ledger another, with nothing recording the split.
        """
        state = _v2_state()
        state["historical_up_share"]["n_years"] = 4
        with pytest.raises(contracts.ContractError, match="n_independent"):
            contracts.validate_neuralweb_state_v2(state)

    def test_the_projected_n_years_is_the_same_number_in_both_places(self):
        state = _v2_state()
        projection = contracts.seasonality_state_projection(state)
        assert projection["block"]["n_years"] == state["evidence"]["n_independent"]
        assert projection["ledger"]["n_years"] == state["evidence"]["n_independent"]

    def test_the_emitter_writes_one_number_into_both(self, tmp_path):
        for symbol, state in _emit(tmp_path).items():
            assert (
                state["historical_up_share"]["n_years"]
                == state["evidence"]["n_independent"]
            ), symbol


# ---------------------------------------------------------------------------
# 4. The authority ceiling did not move with the schema bump
# ---------------------------------------------------------------------------


class TestAuthority:
    def test_ceiling_is_all_false(self):
        authority = _v2_state()["authority"]
        assert authority["may_explain"] is True
        assert authority["may_flag_attention"] is True
        for key in (
            "may_deescalate",
            "may_rank",
            "may_gate",
            "may_size",
            "may_originate",
            "may_rewrite_geometry",
            "may_boost_confidence",
        ):
            assert authority[key] is False, key

    @pytest.mark.parametrize(
        "key",
        ["may_rank", "may_gate", "may_size", "may_originate", "may_deescalate"],
    )
    def test_raising_the_ceiling_is_refused(self, key):
        """A schema bump is not an authority grant."""
        state = _v2_state()
        state["authority"][key] = True
        with pytest.raises(contracts.ContractError, match=key):
            contracts.validate_neuralweb_state_v2(state)


# ---------------------------------------------------------------------------
# 5. Contradiction and overlap — measured, or explicitly unavailable
# ---------------------------------------------------------------------------


class TestMeasuredNotAsserted:
    def test_contradiction_is_false_and_names_the_missing_owner(self):
        contradiction = _v2_state()["contradiction"]
        assert contradiction["present"] is False
        assert contradiction["reason_code"] == "event_timing_probability_absent"
        # The missing artifact is NAMED, and named from the reader that declares
        # the expectation rather than from a literal that can drift away from it.
        assert season_state.EVENT_TIMING_OWNER_CONTRACT in contradiction["detail"]
        assert season_state.EVENT_TIMING_OWNER in contradiction["detail"]
        assert set(contradiction["between"]) == {"calendar_clock", "event_clock"}

    def test_the_detail_says_unmeasured_rather_than_implying_agreement(self):
        detail = _v2_state()["contradiction"]["detail"].lower()
        assert "not a measured absence" in detail

    def test_a_silent_contradiction_is_refused(self):
        """``present: false`` with no reason is the failure this slot replaces."""
        state = _v2_state()
        state["contradiction"] = {"present": False, "between": [], "detail": "none"}
        with pytest.raises(contracts.ContractError, match="reason_code"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_claimed_contradiction_must_name_two_legs(self):
        state = _v2_state()
        state["contradiction"] = {
            "present": True,
            "between": ["calendar_clock"],
            "detail": "asserted",
            "measured_by": "some/artifact.json",
        }
        with pytest.raises(contracts.ContractError, match="two legs"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_claimed_contradiction_must_name_what_measured_it(self):
        """The one positive claim in the payload cannot be the one with no receipt.

        ``overlap`` always carries ``measured_by``.  A contradiction asserting
        that two clocks DISAGREE is a stronger statement still, and its second
        leg is an event-timing probability whose producer contract has not
        landed — so 'the calendar disagrees with X' has to name an artifact
        somebody can open.
        """
        state = _v2_state()
        state["contradiction"] = {
            "present": True,
            "between": ["calendar_clock", "astrology"],
            "detail": "the stars say otherwise",
        }
        with pytest.raises(contracts.ContractError, match="measured_by"):
            contracts.validate_neuralweb_state_v2(state)
        state["contradiction"]["measured_by"] = "data/neuralweb/event_clock.json"
        contracts.validate_neuralweb_state_v2(state)

    def test_an_unratified_event_payload_still_does_not_fabricate_one(self):
        """Given bytes, the reader refuses the dialect wholesale — it does not guess."""
        measured = season_state.measure_contradiction(
            calendar_phase="in_window",
            event_timing_probability={"p_adverse": 0.4},
        )
        assert measured["present"] is False
        assert measured["reason_code"] == "event_timing_contract_not_ratified"
        assert season_state.EVENT_TIMING_OWNER_CONTRACT in measured["detail"]

    def test_overlap_is_unmeasured_and_redundancy_is_null_not_zero(self):
        overlap = _v2_state()["overlap"]
        assert overlap["measured"] is False
        assert overlap["redundancy"] is None
        assert overlap["reason_code"] == "spine_artifact_unavailable"
        assert overlap["measured_by"] == season_state.SPINE_ARTIFACT_PATH

    def test_an_unmeasured_overlap_may_not_claim_zero_redundancy(self):
        state = _v2_state()
        state["overlap"] = {**state["overlap"], "redundancy": 0.0}
        with pytest.raises(contracts.ContractError, match="not zero redundancy"):
            contracts.validate_neuralweb_state_v2(state)

    def test_a_measured_overlap_must_carry_a_number(self):
        state = _v2_state()
        state["overlap"] = {
            "measured": True,
            "measured_against": ["track_record"],
            "redundancy": None,
            "measured_by": season_state.SPINE_ARTIFACT_PATH,
        }
        with pytest.raises(contracts.ContractError, match="redundancy"):
            contracts.validate_neuralweb_state_v2(state)


class TestOverlapReadsTheSpine:
    """Overlap is DELEGATED to covariance_spine — never a second measurement."""

    @staticmethod
    def _spine(lobes: dict) -> dict:
        return {"schema": season_state.SPINE_SCHEMA, "blocks": {"lobes": lobes}}

    def test_the_real_committed_spine_does_not_carry_the_seasonality_lobe(self):
        """Measured, not assumed: today's honest answer is 'absent from the spine'."""
        repo = Path(__file__).resolve().parent.parent
        spine = season_state.load_spine(repo)
        if spine is None:
            pytest.skip("covariance spine artifact not present in this checkout")
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False
        assert overlap["reason_code"] == "lobe_absent_from_spine"
        # It still reports WHAT it would have been measured against.
        assert isinstance(overlap["measured_against"], list)

    def test_a_wrong_schema_artifact_is_not_read(self):
        assert season_state.load_spine(Path("/nonexistent-root-for-a-test")) is None

    def test_a_below_floor_lobe_is_unmeasured_with_its_own_reason(self):
        spine = self._spine(
            {"coverage": {"measurable": ["track_record"], "unmeasurable": {"seasonality": 7}}}
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False
        assert overlap["reason_code"] == "lobe_below_spine_measurement_floor"
        assert "7" in overlap["detail"]

    @staticmethod
    def _pair(a: str, b: str, corr: float) -> dict:
        """A pair in the PRODUCER's dialect, not a convenient one.

        ``engine/neuralweb/covariance_spine.py`` writes
        ``{"a", "b", "corr", "n_shared_weeks", "jaccard"}``.  A fixture that
        invents ``{"pair": [...]}`` here would green-light a reader that finds
        no pair on the real artifact — and a reader that finds no pair is one
        line away from publishing a fabricated ``redundancy: 0.0``.  So the
        fixture is built from the producer's own keys.
        """
        return {"a": a, "b": b, "corr": corr, "n_shared_weeks": 52, "jaccard": 0.4}

    def test_the_pair_fixture_matches_the_producers_own_key_shape(self):
        """The fixture dialect above is the one covariance_spine actually emits."""
        source = (
            Path(__file__).resolve().parent.parent
            / "engine" / "neuralweb" / "covariance_spine.py"
        ).read_text(encoding="utf-8")
        emitted = source.split("all_pairs.append(", 1)[1][:220]
        for key in ('"a"', '"b"', '"corr"'):
            assert key in emitted, (
                "covariance_spine no longer emits this pair key — measure_overlap "
                "reads it by name and would silently find no pair"
            )
        assert '"pair"' not in emitted and '"engines"' not in emitted

    def test_a_measurable_lobe_reports_the_spines_own_strongest_pairing(self):
        """The code path that starts returning a NUMBER the day the lobe fires."""
        spine = self._spine(
            {
                "coverage": {
                    "measurable": ["seasonality", "track_record", "us_board"],
                    "unmeasurable": {},
                },
                "highest_overlap_pairs": [
                    self._pair("seasonality", "track_record", -0.42),
                    self._pair("seasonality", "us_board", 0.31),
                    self._pair("track_record", "us_board", 0.95),
                ],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is True
        # Magnitude, and only over pairs the seasonality lobe is IN: the 0.95
        # pair belongs to two other lobes and is none of this lobe's business.
        assert overlap["redundancy"] == pytest.approx(0.42)
        assert overlap["measured_against"] == ["track_record", "us_board"]
        contracts.validate_neuralweb_state_v2(
            {**_v2_state(), "overlap": overlap}
        )

    def test_measured_against_names_only_the_peers_it_was_correlated_with(self):
        """Naming a lobe the number was never computed over is a false receipt."""
        spine = self._spine(
            {
                "coverage": {
                    "measurable": ["seasonality", "track_record", "us_board", "flows"],
                    "unmeasurable": {},
                },
                "highest_overlap_pairs": [self._pair("seasonality", "flows", 0.55)],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is True
        assert overlap["redundancy"] == pytest.approx(0.55)
        assert overlap["measured_against"] == ["flows"]
        assert "track_record" not in overlap["detail"]

    def test_a_measurable_lobe_with_no_published_pair_is_unmeasured_not_zero(self):
        """The finding this whole slot exists to prevent, one level down.

        ``highest_overlap_pairs`` is the spine's GLOBAL top-5 and the artifact
        carries no correlation matrix, so a lobe that clears the measurement
        floor but sits outside that top-5 has NO published correlation.  Calling
        that ``measured: true, redundancy: 0.0`` is a positive claim of total
        independence against peers it was never correlated with — and
        ``measured: true`` is exactly what the cortex prompt teaches the model
        to read as genuinely measured.
        """
        spine = self._spine(
            {
                "coverage": {
                    "measurable": ["seasonality", "track_record", "us_board"],
                    "unmeasurable": {},
                },
                "highest_overlap_pairs": [self._pair("track_record", "us_board", 0.95)],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False
        assert overlap["redundancy"] is None
        assert overlap["reason_code"] == "lobe_in_index_but_no_pair_published"
        assert "not zero" in overlap["detail"]
        contracts.validate_neuralweb_state_v2({**_v2_state(), "overlap": overlap})

    def test_the_only_measurable_lobe_has_no_peers_and_says_so(self):
        spine = self._spine(
            {
                "coverage": {"measurable": ["seasonality"], "unmeasurable": {}},
                "highest_overlap_pairs": [],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False
        assert overlap["redundancy"] is None
        assert overlap["reason_code"] == "lobe_in_index_but_no_pair_published"

    def test_a_pair_in_an_invented_dialect_is_not_read_as_a_measurement(self):
        """A key shape no producer writes must not become a fabricated zero."""
        spine = self._spine(
            {
                "coverage": {
                    "measurable": ["seasonality", "track_record"],
                    "unmeasurable": {},
                },
                "highest_overlap_pairs": [
                    {"pair": ["seasonality", "track_record"], "corr": 0.88},
                    {"engines": ["seasonality", "track_record"], "correlation": 0.88},
                ],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False, (
            "an unrecognised pair dialect was read as a measurement"
        )
        assert overlap["redundancy"] is None

    def test_a_pair_with_no_usable_corr_is_not_counted_as_a_measurement(self):
        spine = self._spine(
            {
                "coverage": {
                    "measurable": ["seasonality", "track_record"],
                    "unmeasurable": {},
                },
                "highest_overlap_pairs": [
                    {"a": "seasonality", "b": "track_record", "corr": None},
                ],
            }
        )
        overlap = season_state.measure_overlap(spine, "MRNA")
        assert overlap["measured"] is False
        assert overlap["redundancy"] is None


# ---------------------------------------------------------------------------
# 6. Dual read — v1 and v2 project to the SAME consumer block
# ---------------------------------------------------------------------------


def _seasonality_file(root: Path, states: dict[str, dict]) -> Path:
    (root / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
    path = root / "data" / "neuralweb" / "biopharma_seasonality_state.json"
    path.write_text(
        json.dumps(
            {
                "schema": season_state.STATE_FILE_SCHEMA,
                "as_of": _NUMBERS["asof"],
                "universe": {"source": "site/seasonalitydata/index.json"},
                "states": states,
                "gaps": [],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestDualReadEquivalence:
    def test_the_two_schemas_project_to_an_identical_block(self):
        v1 = contracts.seasonality_state_projection(_v1_state())
        v2 = contracts.seasonality_state_projection(_v2_state())
        assert v1["block"] == v2["block"], (
            "the migration reinterpreted a number instead of renaming it"
        )
        assert v1["abstain"] == v2["abstain"]
        assert v1["expires_at"] == v2["expires_at"]

    def test_the_ledger_projection_is_identical_too(self):
        """One ledger row schema across the state migration, or the 28 existing
        rows stop being comparable with everything appended after them."""
        assert (
            contracts.seasonality_state_projection(_v1_state())["ledger"]
            == contracts.seasonality_state_projection(_v2_state())["ledger"]
        )

    def test_the_block_carries_exactly_the_declared_keys(self):
        block = contracts.seasonality_state_projection(_v2_state())["block"]
        assert tuple(block) == contracts.SEASONALITY_BLOCK_KEYS

    @pytest.mark.parametrize("builder", [_v1_state, _v2_state])
    def test_the_projection_carries_the_FULL_flag_list_never_a_filtered_one(
        self, builder
    ):
        """The flags ARE the honesty of this block.

        ``state._flags`` can emit six at once, every one of them de-escalating.
        A projection that trimmed the list would read as a cleaner finding than
        the lobe actually has — a stale, thin-panel, unclear-null state showing
        one caveat instead of four — and the trim would be invisible to any
        fixture carrying a single flag.  So this asserts SET EQUALITY against
        the state's own list, with more flags than a truncation would keep.
        """
        many = [
            "raw_null_not_cleared",
            "neutral_null_not_cleared",
            "stability_fragile",
            "forward_sample_thin",
            "thin_years",
            "artifact_stale",
        ]
        state = builder()
        state["uncertainty"]["flags"] = list(many)
        state = contracts.validate_seasonality_state(state)
        block = contracts.seasonality_state_projection(state)["block"]
        assert block["flags"] == many, "the projection reordered or trimmed the flags"

    def test_every_flag_the_producer_can_emit_survives_to_the_consumer_block(
        self, tmp_path
    ):
        """The full list, end to end — emitter, bridge, and cortex row.

        A truncation anywhere on this path is a de-escalation the payload never
        records, which is the one direction this lobe is forbidden to drift in.
        """
        from engine.neuralweb.mastermind_context import _load_seasonality_map  # noqa: PLC0415

        many = ["raw_null_not_cleared", "thin_years", "artifact_stale"]
        state = _v2_state()
        state["uncertainty"]["flags"] = list(many)
        _seasonality_file(tmp_path, {"FIXTURE_BUY": state})

        notes: list[str] = []
        mapped = _load_seasonality_map(
            tmp_path, notes, now=datetime(2026, 7, 5, tzinfo=timezone.utc)
        )
        assert mapped["FIXTURE_BUY"]["flags"] == many, notes

        from engine.neuralweb.cortex import _tool_read_seasonality_state  # noqa: PLC0415

        row = _tool_read_seasonality_state(
            tmp_path, {}, datetime(2026, 7, 5, tzinfo=timezone.utc)
        )["states"][0]
        assert row["flags"] == many

    def test_p_is_the_historical_share_in_both(self):
        for state in (_v1_state(), _v2_state()):
            assert contracts.seasonality_state_projection(state)["block"]["p"] == (
                _NUMBERS["p"]
            )

    def test_a_calibrated_estimate_is_never_projected_into_the_block(self):
        """Surfacing a calibrated number is a promotion, not a read."""
        state = _v2_state(calibrated_estimate=_full_estimate(value=0.99))
        block = contracts.seasonality_state_projection(state)["block"]
        assert block["p"] == _NUMBERS["p"] != 0.99
        assert 0.99 not in block.values()

    def test_an_unknown_schema_is_refused_rather_than_sniffed(self):
        state = _v2_state()
        state["schema"] = "neuralweb.biopharma_seasonality_state.v3"
        with pytest.raises(contracts.ContractError):
            contracts.validate_seasonality_state(state)
        with pytest.raises(contracts.ContractError):
            contracts.seasonality_state_projection(state)

    @pytest.mark.parametrize("builder", [_v1_state, _v2_state])
    def test_both_schemas_pass_the_dispatching_validator(self, builder):
        contracts.validate_seasonality_state(builder())

    def test_the_candidate_bridge_attaches_the_same_block_from_either_file(
        self, tmp_path
    ):
        """END TO END: a v1 file and a v2 file through the real consumer.

        This is the acceptance gate the schema migration lives or dies on — the
        projection agreeing in isolation is necessary but not sufficient, since
        the consumer could still read a field the projection does not own.
        """
        from tests.test_mastermind_context import _build_minimal_tree  # noqa: PLC0415
        from engine.neuralweb.mastermind_context import build_context  # noqa: PLC0415

        blocks = {}
        for label, state in (("v1", _v1_state()), ("v2", _v2_state())):
            root = tmp_path / label
            root.mkdir()
            _build_minimal_tree(root)
            _seasonality_file(root, {"FIXTURE_BUY": state})
            payload = build_context(
                root=root, now=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
            )
            blocks[label] = payload["candidate_context"]["FIXTURE_BUY"]["seasonality"]

        assert blocks["v1"] == blocks["v2"], blocks
        assert blocks["v2"]["p"] == _NUMBERS["p"]
        assert blocks["v2"]["allowed_behavior"] == "annotate_only"


# ---------------------------------------------------------------------------
# 7. No fusion — seasonality computes no combined weight, discount, or score
# ---------------------------------------------------------------------------


class TestNoFusion:
    #: Numbers owned by OTHER engines, of the kind a fused score would blend in.
    _FOREIGN = {
        "spine_redundancy": 0.42,
        "factor_corr": -0.17,
        "hazard_p": 0.30,
        "options_skew": 1.25,
    }

    def test_no_block_number_is_a_product_or_sum_with_another_engines_number(self):
        """Search, rather than assert: a fused field would not announce itself.

        Every numeric field in the emitted block is checked against every
        product and sum of a seasonality number with a foreign engine's number.
        A hit does not prove fusion, but a fused field cannot hide from it.
        """
        block = contracts.seasonality_state_projection(_v2_state())["block"]
        own = [
            value
            for value in (_NUMBERS["p"], _NUMBERS["p_baseline"], _NUMBERS["edge"])
        ]
        forbidden: list[tuple[str, float]] = []
        for own_value in own:
            for name, foreign in self._FOREIGN.items():
                forbidden.append((f"{own_value}*{name}", own_value * foreign))
                forbidden.append((f"{own_value}+{name}", own_value + foreign))
                forbidden.append((f"{own_value}-{name}", own_value - foreign))

        numeric = {
            key: float(value)
            for key, value in block.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        assert numeric, "the block carried no numbers to check"
        for key, value in numeric.items():
            for label, combined in forbidden:
                assert abs(value - combined) > 1e-9, (
                    f"block[{key}] == {value} matches {label} — seasonality "
                    "computed a fused number"
                )

    def test_edge_is_the_only_derived_number_and_it_is_wholly_internal(self):
        block = contracts.seasonality_state_projection(_v2_state())["block"]
        assert block["edge"] == pytest.approx(block["p"] - block["p_baseline"])

    def test_overlap_redundancy_never_reaches_the_block(self):
        """The spine's number is CONTEXT about the lobe, not an input to it."""
        spine = {
            "schema": season_state.SPINE_SCHEMA,
            "blocks": {
                "lobes": {
                    "coverage": {"measurable": ["seasonality", "track_record"], "unmeasurable": {}},
                    "highest_overlap_pairs": [
                        {"a": "seasonality", "b": "track_record", "corr": 0.42}
                    ],
                }
            },
        }
        with_spine = {**_v2_state(), "overlap": season_state.measure_overlap(spine, "X")}
        without = _v2_state()
        assert with_spine["overlap"]["redundancy"] == pytest.approx(0.42)
        assert (
            contracts.seasonality_state_projection(with_spine)["block"]
            == contracts.seasonality_state_projection(without)["block"]
        ), "a redundancy measurement moved a consumer-facing number"


# ---------------------------------------------------------------------------
# 8. Forward-ledger grading — append-only, replay-safe
# ---------------------------------------------------------------------------


def _write_universe(root: Path, symbols: list[str], *, as_of: str) -> None:
    base = root / "site" / "seasonalitydata"
    (base / "entities").mkdir(parents=True, exist_ok=True)
    entity = json.loads((_FIXTURES / "SPY.entity.json").read_text(encoding="utf-8"))
    entries = []
    for symbol in symbols:
        entries.append(
            {
                "symbol": symbol,
                "name": symbol,
                "group": "equity",
                "sector": season_state.BIOPHARMA_SECTOR,
            }
        )
        (base / "entities" / f"{symbol}.json").write_text(
            json.dumps(entity), encoding="utf-8"
        )
    (base / "index.json").write_text(
        json.dumps(
            {
                "schema": "biopharma_seasonality.index.v1",
                "as_of": as_of,
                "default_symbol": "SPY",
                "n_entities": len(entries),
                "entities": entries,
            }
        ),
        encoding="utf-8",
    )


def _emit(root: Path, *, now: datetime = _NOW) -> dict[str, dict]:
    _write_universe(root, ["SPY"], as_of="2026-07-31")
    emitter.build(root=root, now=now)
    payload = json.loads(
        (root / emitter.STATE_PATH).read_text(encoding="utf-8")
    )
    return payload["states"]


def _seed_register(root: Path, **overrides) -> dict:
    row = {
        "row_type": "register",
        "schema": season_state.LEDGER_SCHEMA,
        "key": "SPY:2025:284-344",
        "symbol": "SPY",
        "registered_asof": "2025-01-02",
        "start_doy": 284,
        "end_doy": 344,
        "occurrence_end_date": "2025-12-10",
        "p": 0.72,
        "p_baseline": 0.61,
        "n_years": 18,
        "pattern_spec_hash": _SHA,
        "model_version": "seasonality-calendar-v1",
        "tier": "shadow",
        **overrides,
    }
    ledger = root / emitter.LEDGER_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def _prices(root: Path, symbol: str, rows: list[tuple[date, float]]) -> None:
    store = root / "data" / "yahoo"
    store.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"close": [value for _, value in rows]},
        index=pd.to_datetime([day for day, _ in rows]),
    ).to_parquet(store / f"{symbol}.parquet")


def _ledger_rows(root: Path) -> list[dict]:
    text = (root / emitter.LEDGER_PATH).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class TestForwardLedgerGrading:
    def test_a_matured_occurrence_is_graded_once_and_replay_adds_nothing(self, tmp_path):
        """The acceptance line: replaying the SAME inputs appends no duplicate.

        A forward ledger that re-grades on every run inflates its own sample
        and turns one outcome into N — which is exactly the shape that makes a
        track record look better than it is.
        """
        _write_universe(tmp_path, ["SPY"], as_of="2026-07-31")
        _seed_register(tmp_path)
        _prices(
            tmp_path,
            "SPY",
            [
                (date(2025, 10, 10), 100.0),
                (date(2025, 10, 11), 101.0),
                (date(2025, 12, 9), 109.0),
                (date(2025, 12, 10), 110.0),
                (date(2026, 7, 30), 150.0),
            ],
        )
        first = emitter.build(root=tmp_path, now=_NOW)
        assert first["n_graded"] == 1
        after_first = (tmp_path / emitter.LEDGER_PATH).read_bytes()

        grades = [r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade"]
        assert len(grades) == 1
        assert grades[0]["grade_status"] == "graded"
        assert grades[0]["key"] == "SPY:2025:284-344"
        assert grades[0]["outcome_up"] is True

        # Replay, byte-for-byte identical inputs.
        second = emitter.build(root=tmp_path, now=_NOW)
        assert second["n_graded"] == 0
        assert (tmp_path / emitter.LEDGER_PATH).read_bytes() == after_first, (
            "a replay rewrote or duplicated the ledger"
        )
        assert len([r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade"]) == 1

    def test_prior_bytes_are_never_rewritten_reordered_or_re_dated(self, tmp_path):
        _write_universe(tmp_path, ["SPY"], as_of="2026-07-31")
        _seed_register(tmp_path)
        prior = (tmp_path / emitter.LEDGER_PATH).read_bytes()
        _prices(
            tmp_path,
            "SPY",
            [(date(2025, 10, 11), 100.0), (date(2025, 12, 10), 110.0), (date(2026, 7, 30), 150.0)],
        )
        emitter.build(root=tmp_path, now=_NOW)
        assert (tmp_path / emitter.LEDGER_PATH).read_bytes().startswith(prior)

    def test_matured_without_prices_stays_pending_inside_thirty_days(self, tmp_path):
        """Pending is not a grade. Nothing here ever invents a price."""
        _write_universe(tmp_path, ["SPY"], as_of="2026-01-05")
        _seed_register(tmp_path)  # window closed 2025-12-10, 26 days earlier
        _prices(tmp_path, "SPY", [(date(2025, 6, 2), 90.0)])
        summary = emitter.build(
            root=tmp_path, now=datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc)
        )
        assert summary["n_graded"] == 0
        assert not [r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade"]

    def test_it_closes_out_as_ungradable_only_after_thirty_days(self, tmp_path):
        _write_universe(tmp_path, ["SPY"], as_of="2026-01-15")
        _seed_register(tmp_path)  # 36 days after the 2025-12-10 close
        _prices(tmp_path, "SPY", [(date(2025, 6, 2), 90.0)])
        summary = emitter.build(
            root=tmp_path, now=datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
        )
        assert summary["n_graded"] == 1
        grade = next(r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade")
        assert grade["grade_status"] == "ungradable_missing_prices"
        assert grade["realized_log_return"] is None and grade["outcome_up"] is None

        # And a close-out is final: it is never revisited on a later night.
        assert emitter.build(
            root=tmp_path, now=datetime(2026, 2, 1, 4, 0, tzinfo=timezone.utc)
        )["n_graded"] == 0

    def test_a_symbol_that_LEFT_the_store_is_still_closed_out(self, tmp_path):
        """The close-out's own reason for existing, and it was unreachable.

        ``ungradable_missing_prices`` is documented as "the honest reading for a
        symbol that left the store" — but the emitter only called ``grade_rows``
        when at least one price frame loaded, and a symbol that left the store
        loads no frame.  So the one case the branch was written for was the one
        case that skipped it: the row sat PENDING forever, inflating the pending
        count and never entering ``live_n``.  It worked only when some unrelated
        symbol happened to be present.
        """
        _write_universe(tmp_path, ["SPY"], as_of="2026-01-15")
        _seed_register(tmp_path, key="ZZZ:2025:284-344", symbol="ZZZ")
        # The store EXISTS; ZZZ is simply no longer in it.
        (tmp_path / "data" / "yahoo").mkdir(parents=True, exist_ok=True)
        summary = emitter.build(
            root=tmp_path, now=datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
        )
        assert summary["n_graded"] == 1, (
            "36 days past maturity with the symbol gone from the store and nothing "
            "was closed out"
        )
        grade = next(r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade")
        assert grade["symbol"] == "ZZZ"
        assert grade["grade_status"] == "ungradable_missing_prices"

    def test_that_close_out_does_not_depend_on_an_unrelated_symbol_being_present(
        self, tmp_path
    ):
        """Same input, minus the coincidence — the answer must not change."""
        _write_universe(tmp_path, ["SPY"], as_of="2026-01-15")
        _seed_register(tmp_path, key="ZZZ:2025:284-344", symbol="ZZZ")
        _seed_register(tmp_path, key="SPY:2025:284-344", symbol="SPY")
        _prices(tmp_path, "SPY", [(date(2025, 10, 10), 100.0), (date(2025, 12, 10), 150.0)])
        with_company = emitter.build(
            root=tmp_path, now=datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
        )
        statuses = {
            r["symbol"]: r["grade_status"]
            for r in _ledger_rows(tmp_path)
            if r["row_type"] == "grade"
        }
        assert with_company["n_graded"] == 2
        assert statuses["ZZZ"] == "ungradable_missing_prices"
        assert statuses["SPY"] == "graded"

    def test_an_absent_price_STORE_closes_nothing_out(self, tmp_path):
        """An infra outage is not evidence that a symbol left the store.

        ``None`` (no store) and ``{}`` (store present, symbol gone) are
        different answers and must stay different: closing rows out during an
        outage would write permanent ungradable verdicts over a temporary
        absence.
        """
        _write_universe(tmp_path, ["SPY"], as_of="2026-01-15")
        _seed_register(tmp_path, key="ZZZ:2025:284-344", symbol="ZZZ")
        assert not (tmp_path / "data" / "yahoo").exists()
        summary = emitter.build(
            root=tmp_path, now=datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
        )
        assert summary["n_graded"] == 0
        assert not [r for r in _ledger_rows(tmp_path) if r["row_type"] == "grade"]
        payload = json.loads((tmp_path / emitter.STATE_PATH).read_text(encoding="utf-8"))
        assert any(
            g.get("reason_code") == "price_store_absent" for g in payload["gaps"]
        ), payload["gaps"]

    def test_an_unclosed_window_is_never_graded(self, tmp_path):
        _write_universe(tmp_path, ["SPY"], as_of="2026-07-31")
        _seed_register(tmp_path, key="SPY:2026:284-344", occurrence_end_date="2026-12-10")
        _prices(tmp_path, "SPY", [(date(2026, 7, 30), 150.0)])
        assert emitter.build(root=tmp_path, now=_NOW)["n_graded"] == 0

    def test_only_graded_rows_count_toward_the_forward_sample(self, tmp_path):
        rows = [
            {"row_type": "grade", "symbol": "SPY", "grade_status": "graded"},
            {"row_type": "grade", "symbol": "SPY", "grade_status": "ungradable_missing_prices"},
            {"row_type": "register", "symbol": "SPY"},
        ]
        assert season_state.live_n_by_symbol(rows) == {"SPY": 1}

    def test_the_row_schema_did_not_move_with_the_state_schema(self, tmp_path):
        """The 28 committed rows must stay comparable with everything after."""
        states = _emit(tmp_path)
        assert states["SPY"]["schema"] == contracts.NEURALWEB_STATE_V2_SCHEMA
        register = next(
            r for r in _ledger_rows(tmp_path) if r["row_type"] == "register"
        )
        assert register["schema"] == season_state.LEDGER_SCHEMA == (
            "seasonality.nw_forward_ledger.v1"
        )
        assert set(register) == {
            "row_type", "schema", "key", "symbol", "registered_asof", "start_doy",
            "end_doy", "occurrence_end_date", "p", "p_baseline", "n_years",
            "pattern_spec_hash", "model_version", "tier",
        }

    def test_the_envelope_declares_the_schema_the_states_inside_actually_are(
        self, tmp_path
    ):
        """The envelope label is a DISPATCH key, so a mislabel misroutes silently.

        The file top-level says ``state_schema`` so "a consumer can dispatch
        without opening a state".  Nothing checked that the label matched the
        states, so an envelope reading v1 over a map of v2 states would send a
        dispatch-on-envelope reader down the wrong branch with no error
        anywhere.
        """
        states = _emit(tmp_path)
        payload = json.loads(
            (tmp_path / emitter.STATE_PATH).read_text(encoding="utf-8")
        )
        assert payload["state_schema"] == season_state.EMITTED_STATE_SCHEMA
        assert payload["state_schema"] == contracts.NEURALWEB_STATE_V2_SCHEMA
        assert states, "the emitter produced no states to check the label against"
        for symbol, state in states.items():
            assert state["schema"] == payload["state_schema"], (
                f"{symbol} is a {state['schema']} state under a "
                f"{payload['state_schema']} envelope"
            )


# ---------------------------------------------------------------------------
# 9. The cortex read tool
# ---------------------------------------------------------------------------


#: Inside the fixtures' own 2026-07-03 -> 2026-07-07 validity. The fixture
#: states carry a REAL expiry, so every read has to be told which instant it is
#: reading at — a suite that read at wall clock would pass today and go silently
#: empty forever after 2026-07-07.
_LIVE = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)


class TestCortexReadTool:
    @staticmethod
    def _read(
        root: Path, params: dict | None = None, *, now: datetime | str | None = _LIVE
    ) -> dict:
        from engine.neuralweb.cortex import _tool_read_seasonality_state  # noqa: PLC0415

        return _tool_read_seasonality_state(root, params or {}, now)

    def test_it_is_registered_in_the_whitelist_and_the_schemas(self):
        from engine.neuralweb.cortex import _READ_TOOLS, _tool_schemas  # noqa: PLC0415

        assert "read_seasonality_state" in _READ_TOOLS
        schema = next(
            s for s in _tool_schemas() if s["name"] == "read_seasonality_state"
        )
        assert schema["input_schema"]["required"] == []
        assert "ticker" in schema["input_schema"]["properties"]

    def test_the_dispatcher_routes_it(self, tmp_path):
        """Registered in three places, or the tool is invisible at runtime.

        A read tool that is in ``_tool_schemas`` but not in the A7 whitelist is
        offered to the model and then refused when it calls it, which reads as
        a model failure rather than as a wiring hole.
        """
        from engine.neuralweb.cortex import _ALLOWED_TOOLS, dispatch_tool  # noqa: PLC0415

        assert "read_seasonality_state" in _ALLOWED_TOOLS
        census: dict = {}
        out = dispatch_tool(
            "read_seasonality_state", {}, tmp_path, "2026-08-02", {}, census
        )
        assert "error" not in out
        assert out["is_context_only"] is True
        assert census["read_seasonality_state"] == 1

    def test_the_prompt_states_the_historical_share_ceiling(self):
        """Naming the tool is not enough — the model must be told what p IS.

        ``p`` is a historical positive-year share.  A prompt that lists the tool
        without saying so invites the model to narrate it as a probability, and
        the payload gives it no reason not to: the field is called ``p`` and it
        sits in [0, 1] like every calibrated number the cortex reads.
        """
        from engine.neuralweb.cortex import _SYSTEM_PROMPT  # noqa: PLC0415

        assert "SEASONALITY CEILING" in _SYSTEM_PROMPT
        ceiling = _SYSTEM_PROMPT.split("SEASONALITY CEILING", 1)[1][:700].lower()
        assert "historical" in ceiling
        assert "never a forecast" in ceiling
        assert "p_baseline" in ceiling
        assert "unmeasured, not zero" in ceiling

    def test_absent_artifact_is_a_structured_gap_not_a_raise(self, tmp_path):
        out = self._read(tmp_path)
        assert out["is_context_only"] is True
        assert out["gaps"] and "absent" in out["gaps"][0]
        assert "states" not in out

    def test_unreadable_artifact_is_a_structured_gap(self, tmp_path):
        (tmp_path / "data" / "neuralweb").mkdir(parents=True)
        (tmp_path / "data" / "neuralweb" / "biopharma_seasonality_state.json").write_text(
            "{not json", encoding="utf-8"
        )
        out = self._read(tmp_path)
        assert out["is_context_only"] is True
        assert out["gaps"] and "unreadable" in out["gaps"][0]

    @pytest.mark.parametrize("builder", [_v1_state, _v2_state])
    def test_it_reads_both_schemas_and_returns_the_same_row(self, tmp_path, builder):
        _seasonality_file(tmp_path, {"FIXTURE_BUY": builder()})
        out = self._read(tmp_path)
        assert out["n_returned"] == 1
        row = out["states"][0]
        assert row["symbol"] == "FIXTURE_BUY"
        assert row["p"] == _NUMBERS["p"]
        assert row["phase"] == _NUMBERS["phase"]

    def test_a_contract_violating_state_is_counted_never_rendered(self, tmp_path):
        broken = _v2_state()
        broken["authority"]["may_rank"] = True
        _seasonality_file(tmp_path, {"FIXTURE_BUY": broken})
        out = self._read(tmp_path)
        assert out["n_returned"] == 0
        assert any("failed the context contract" in gap for gap in out["gaps"])

    def test_the_ticker_param_narrows_the_read(self, tmp_path):
        _seasonality_file(
            tmp_path,
            {"AAA": _v2_state("AAA"), "BBB": _v2_state("BBB")},
        )
        out = self._read(tmp_path, {"ticker": "bbb"})
        assert [row["symbol"] for row in out["states"]] == ["BBB"]

    def test_output_is_bounded(self, tmp_path):
        """A LITERAL ceiling, not whatever the constant currently says.

        Asserting ``n_returned == _SEASONALITY_ROW_CAP`` only proves the loop
        honours the constant — raising the constant to 4000 keeps that assertion
        green while turning the read into the context bomb the cap exists to
        prevent.  So the numbers below are written out.
        """
        from engine.neuralweb.cortex import _SEASONALITY_ROW_CAP  # noqa: PLC0415

        assert _SEASONALITY_ROW_CAP <= 40, (
            "the seasonality read-tool cap was raised past the bound this tool "
            "was justified by — an unbounded read is a context bomb"
        )
        _seasonality_file(
            tmp_path,
            {f"T{i:03d}": _v2_state(f"T{i:03d}") for i in range(_SEASONALITY_ROW_CAP + 12)},
        )
        out = self._read(tmp_path)
        assert out["n_returned"] == _SEASONALITY_ROW_CAP
        assert len(out["states"]) <= 40
        assert len(out["gaps"]) <= 40
        # The whole payload, not just the row count: a row that grew would blow
        # the budget at a legal row count.
        assert len(json.dumps(out)) < 120_000, "the bounded read is no longer small"

    def test_states_beyond_the_cap_are_counted_not_silently_dropped(self, tmp_path):
        """A cut-off that leaves no trace makes the counts describe a prefix."""
        from engine.neuralweb.cortex import _SEASONALITY_ROW_CAP  # noqa: PLC0415

        n_extra = 12
        _seasonality_file(
            tmp_path,
            {
                f"T{i:03d}": _v2_state(f"T{i:03d}")
                for i in range(_SEASONALITY_ROW_CAP + n_extra)
            },
        )
        out = self._read(tmp_path)
        assert any(
            f"{n_extra} further state(s) not returned" in gap for gap in out["gaps"]
        ), out["gaps"]

    def test_an_expired_state_is_dropped_and_counted(self, tmp_path):
        """The 48h TTL, enforced at BOTH readers of this one artifact.

        ``mastermind_context._load_seasonality_map`` already drops expired
        states.  A tool that served them would put the two readers of one
        artifact into disagreement about what is current — with the permissive
        one wired to the chat model, citing arbitrarily stale calendar context
        as though it were today's.
        """
        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state()})
        out = self._read(tmp_path, now=datetime(2030, 1, 1, tzinfo=timezone.utc))
        assert out["n_returned"] == 0
        assert out["states"] == []
        assert any("expired state(s) skipped" in gap for gap in out["gaps"]), out["gaps"]

    def test_an_unparseable_reference_time_does_not_switch_the_ttl_off(self, tmp_path):
        """A bad clock must fall back to wall clock, never to 'no expiry check'."""
        from engine.neuralweb.cortex import _seasonality_reference_time  # noqa: PLC0415

        reference = _seasonality_reference_time("not-a-timestamp")
        assert reference.tzinfo is not None
        assert reference.year >= 2026
        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state()})
        out = self._read(tmp_path, now="not-a-timestamp")
        assert out["n_returned"] == 0, "an unparseable now silently disabled the TTL"

    def test_the_dispatcher_hands_the_tool_the_runs_own_clock(self, tmp_path):
        """One run judges every state against one clock, not wall time."""
        from engine.neuralweb.cortex import dispatch_tool  # noqa: PLC0415

        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state()})
        live = dispatch_tool(
            "read_seasonality_state", {}, tmp_path, "2026-07-05", {}, {}
        )
        dead = dispatch_tool(
            "read_seasonality_state", {}, tmp_path, "2026-08-05", {}, {}
        )
        assert live["n_returned"] == 1
        assert dead["n_returned"] == 0, (
            "the dispatcher's as-of is not reaching the expiry check"
        )

    def test_an_abstaining_state_is_dropped_and_counted(self, tmp_path):
        """``abstain`` is the lobe declining to speak — at BOTH readers.

        The sibling consumer and ``state.register_rows`` both treat abstention
        that way.  Serving the row anyway puts a full ``p`` in front of the
        model on a sample the lobe itself refused to publish.
        """
        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state(abstain=True)})
        out = self._read(tmp_path)
        assert out["n_returned"] == 0
        assert out["states"] == []
        assert any("abstaining state(s) skipped" in gap for gap in out["gaps"]), out["gaps"]

    def test_the_prompt_tells_the_model_what_the_withheld_states_mean(self):
        """A count in ``gaps`` the model was never taught to read is noise."""
        from engine.neuralweb.cortex import _SYSTEM_PROMPT  # noqa: PLC0415

        ceiling = _SYSTEM_PROMPT.split("SEASONALITY CEILING", 1)[1][:1200].lower()
        assert "abstain" in ceiling
        assert "expire" in ceiling or "ttl" in ceiling

    def test_a_structured_note_is_never_the_entry_the_gap_cap_drops(self, tmp_path):
        """Notes say what is MISSING; producer gaps are the expendable tail."""
        from engine.neuralweb.cortex import _SEASONALITY_GAP_CAP  # noqa: PLC0415

        path = _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state(abstain=True)})
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["gaps"] = [
            {"symbol": f"G{i:03d}", "reason_code": "noise", "detail": "filler"}
            for i in range(_SEASONALITY_GAP_CAP + 25)
        ]
        path.write_text(json.dumps(payload), encoding="utf-8")
        out = self._read(tmp_path)
        assert len(out["gaps"]) == _SEASONALITY_GAP_CAP
        assert any("abstaining state(s) skipped" in gap for gap in out["gaps"])

    def test_it_returns_no_recommendation_rank_or_score(self, tmp_path):
        """The authority ceiling, checked at the tool boundary."""
        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state()})
        out = self._read(tmp_path)
        blob = json.dumps(out).lower()
        for banned in (
            '"score"', '"rank"', '"recommendation"', '"action"', '"buy"',
            '"sell"', '"conviction"', '"target_price"', '"weight"',
        ):
            assert banned not in blob, f"the seasonality read tool emitted {banned}"
        assert out["is_context_only"] is True and out["display_only"] is True

    def test_it_never_surfaces_a_calibrated_estimate(self, tmp_path):
        _seasonality_file(
            tmp_path,
            {"FIXTURE_BUY": _v2_state(calibrated_estimate=_full_estimate(value=0.99))},
        )
        out = self._read(tmp_path)
        assert "calibrated_estimate" not in json.dumps(out)
        assert out["states"][0]["p"] == _NUMBERS["p"]

    def test_it_carries_the_measurement_reason_codes(self, tmp_path):
        _seasonality_file(tmp_path, {"FIXTURE_BUY": _v2_state()})
        row = self._read(tmp_path)["states"][0]
        assert row["contradiction"]["present"] is False
        assert row["contradiction"]["reason_code"]
        assert row["overlap"]["measured"] is False
        assert row["overlap"]["redundancy"] is None
