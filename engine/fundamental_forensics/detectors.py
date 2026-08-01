"""Deterministic, evidence-linked forensic detectors for annual statement vintages."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Iterable

from .models import (
    Finding,
    FindingInput,
    FindingState,
    NormalizedObservation,
    StatementVintage,
    decimal_text,
    stable_id,
)
from .normalize import DetectorSpec, ForensicsRegistry


MIN_PERIOD_GAP_DAYS = 300
MAX_PERIOD_GAP_DAYS = 430


def _decimal(observation: NormalizedObservation) -> Decimal:
    return Decimal(observation.value)


def _growth(current: Decimal, prior: Decimal) -> Decimal | None:
    if prior == 0:
        return None
    return (current - prior) / abs(prior) * Decimal("100")


def _periods_are_consecutive(vintages: tuple[StatementVintage, ...]) -> bool:
    if len(vintages) < 2:
        return False
    ends = [date.fromisoformat(item.period_end) for item in vintages]
    return all(
        MIN_PERIOD_GAP_DAYS <= (later - earlier).days <= MAX_PERIOD_GAP_DAYS
        for earlier, later in zip(ends, ends[1:])
    )


def _observation(
    vintage: StatementVintage,
    metric: str,
    observations: dict[str, NormalizedObservation],
) -> NormalizedObservation | None:
    observation_id = vintage.metrics().get(metric)
    return observations.get(observation_id) if observation_id else None


def _collect_inputs(
    pairs: Iterable[tuple[StatementVintage, str]],
    observations: dict[str, NormalizedObservation],
) -> tuple[tuple[FindingInput, ...], tuple[str, ...], list[NormalizedObservation]]:
    inputs: list[FindingInput] = []
    missing: list[str] = []
    source_observations: list[NormalizedObservation] = []
    for vintage, metric in pairs:
        item = _observation(vintage, metric, observations)
        if item is None:
            missing.append(f"{metric}@{vintage.period_end}")
            continue
        inputs.append(
            FindingInput(
                metric=metric,
                period_end=vintage.period_end,
                value=item.value,
                observation_id=item.observation_id,
                fact_ids=item.fact_ids,
            )
        )
        source_observations.append(item)
    inputs.sort(key=lambda item: (item.period_end, item.metric, item.observation_id))
    return tuple(inputs), tuple(sorted(missing)), source_observations


def _finding(
    spec: DetectorSpec,
    registry: ForensicsRegistry,
    *,
    entity_cik: str,
    state: FindingState,
    period_ends: tuple[str, ...],
    inputs: tuple[FindingInput, ...],
    source_observations: list[NormalizedObservation],
    missing_inputs: tuple[str, ...] = (),
    derived_values: dict[str, Decimal | str] | None = None,
    computed_at: datetime,
    limitations: tuple[str, ...] = (),
) -> Finding:
    evidence_observation_ids = tuple(sorted(item.observation_id for item in source_observations))
    evidence_fact_ids = tuple(
        sorted({fact_id for item in source_observations for fact_id in item.fact_ids})
    )
    all_source_ready = bool(source_observations) and all(
        item.source_event_at is not None for item in source_observations
    )
    source_ready_at = (
        max(item.source_event_at for item in source_observations if item.source_event_at)
        if all_source_ready
        else None
    )
    recorded_ready_at = (
        max(item.recorded_at for item in source_observations) if source_observations else None
    )
    derived = tuple(
        sorted(
            (key, decimal_text(value))
            for key, value in (derived_values or {}).items()
        )
    )
    finding_id = stable_id(
        "finding",
        spec.detector_id,
        registry.detector_pack_version,
        entity_cik,
        state.value,
        period_ends,
        evidence_observation_ids,
        missing_inputs,
        derived,
    )
    return Finding(
        finding_id=finding_id,
        detector_id=spec.detector_id,
        detector_version=registry.detector_pack_version,
        detector_rule_available_at=registry.detector_pack_available_at,
        entity_cik=entity_cik,
        state=state,
        applicability="insufficient_evidence" if state is FindingState.NOT_EVALUABLE else "applicable",
        formula=spec.formula,
        thresholds=spec.thresholds,
        derived_values=derived,
        period_ends=period_ends,
        inputs=inputs,
        missing_inputs=tuple(sorted(missing_inputs)),
        evidence_observation_ids=evidence_observation_ids,
        evidence_fact_ids=evidence_fact_ids,
        source_ready_at=source_ready_at,
        recorded_ready_at=recorded_ready_at,
        computed_at=computed_at,
        limitations=tuple(sorted(limitations)),
    )


def _not_evaluable(
    spec: DetectorSpec,
    registry: ForensicsRegistry,
    *,
    entity_cik: str,
    period_ends: tuple[str, ...],
    inputs: tuple[FindingInput, ...],
    source_observations: list[NormalizedObservation],
    missing_inputs: tuple[str, ...],
    computed_at: datetime,
    limitations: tuple[str, ...] = (),
) -> Finding:
    return _finding(
        spec,
        registry,
        entity_cik=entity_cik,
        state=FindingState.NOT_EVALUABLE,
        period_ends=period_ends,
        inputs=inputs,
        source_observations=source_observations,
        missing_inputs=missing_inputs,
        computed_at=computed_at,
        limitations=limitations,
    )


def _two_period_detector(
    spec: DetectorSpec,
    registry: ForensicsRegistry,
    selected: tuple[StatementVintage, ...],
    observations: dict[str, NormalizedObservation],
    *,
    metrics: tuple[str, ...],
    computed_at: datetime,
    compute: Callable[[dict[tuple[str, str], Decimal]], tuple[bool | None, dict[str, Decimal], tuple[str, ...], tuple[str, ...]]],
    entity_cik: str,
) -> Finding:
    if len(selected) < 2:
        return _not_evaluable(
            spec, registry, entity_cik=entity_cik, period_ends=tuple(v.period_end for v in selected),
            inputs=(), source_observations=[], missing_inputs=("two_consecutive_annual_periods",),
            computed_at=computed_at,
        )
    pair = selected[-2:]
    period_ends = tuple(item.period_end for item in pair)
    pairs = tuple((vintage, metric) for vintage in pair for metric in metrics)
    inputs, missing, source_items = _collect_inputs(pairs, observations)
    if not _periods_are_consecutive(pair):
        missing = tuple(sorted(set(missing) | {"consecutive_annual_periods"}))
    if missing:
        return _not_evaluable(
            spec, registry, entity_cik=entity_cik, period_ends=period_ends, inputs=inputs,
            source_observations=source_items, missing_inputs=missing, computed_at=computed_at,
        )
    values = {
        (item.period_end, item.metric): Decimal(item.value)
        for item in inputs
    }
    triggered, derived, failures, limitations = compute(values)
    if triggered is None:
        return _not_evaluable(
            spec, registry, entity_cik=entity_cik, period_ends=period_ends, inputs=inputs,
            source_observations=source_items, missing_inputs=failures, computed_at=computed_at,
            limitations=limitations,
        )
    return _finding(
        spec,
        registry,
        entity_cik=entity_cik,
        state=FindingState.TRIGGERED if triggered else FindingState.CLEAR,
        period_ends=period_ends,
        inputs=inputs,
        source_observations=source_items,
        derived_values=derived,
        computed_at=computed_at,
        limitations=limitations,
    )


def _margin_compute(spec: DetectorSpec, periods: tuple[str, str]):
    thresholds = spec.threshold_map()
    minimum_growth = Decimal(thresholds["min_revenue_growth_pp"])

    def compute(values):
        prior, current = periods
        prior_revenue, current_revenue = values[(prior, "revenue")], values[(current, "revenue")]
        if prior_revenue == 0 or current_revenue == 0:
            return None, {}, ("nonzero_revenue_required",), ()
        revenue_growth = _growth(current_revenue, prior_revenue)
        gross_margin_prior = values[(prior, "gross_profit")] / prior_revenue * Decimal("100")
        gross_margin_current = values[(current, "gross_profit")] / current_revenue * Decimal("100")
        fired = revenue_growth >= minimum_growth and gross_margin_current < gross_margin_prior
        return fired, {
            "revenue_growth_pp": revenue_growth,
            "gross_margin_prior_pp": gross_margin_prior,
            "gross_margin_current_pp": gross_margin_current,
            "gross_margin_change_pp": gross_margin_current - gross_margin_prior,
        }, (), ()

    return compute


def _working_capital_compute(spec: DetectorSpec, periods: tuple[str, str], metric: str, threshold_key: str):
    gap_threshold = Decimal(spec.threshold_map()[threshold_key])

    def compute(values):
        prior, current = periods
        prior_revenue, current_revenue = values[(prior, "revenue")], values[(current, "revenue")]
        prior_metric, current_metric = values[(prior, metric)], values[(current, metric)]
        if prior_revenue == 0 or prior_metric == 0 or current_revenue <= 0:
            return None, {}, ("positive_revenue_and_nonzero_prior_balance_required",), ()
        revenue_growth = _growth(current_revenue, prior_revenue)
        metric_growth = _growth(current_metric, prior_metric)
        growth_gap = metric_growth - revenue_growth
        return growth_gap > gap_threshold, {
            "revenue_growth_pp": revenue_growth,
            f"{metric}_growth_pp": metric_growth,
            "growth_gap_pp": growth_gap,
        }, (), ()

    return compute


def _capital_intensity_compute(spec: DetectorSpec, periods: tuple[str, str]):
    gap_threshold = Decimal(spec.threshold_map()["growth_gap_pp"])

    def compute(values):
        prior, current = periods
        prior_revenue, current_revenue = values[(prior, "revenue")], values[(current, "revenue")]
        prior_capex, current_capex = values[(prior, "capital_expenditures")], values[(current, "capital_expenditures")]
        prior_oi, current_oi = values[(prior, "operating_income")], values[(current, "operating_income")]
        if prior_revenue == 0 or prior_capex == 0 or current_capex <= 0:
            return None, {}, ("nonzero_revenue_and_positive_capex_required",), ()
        revenue_growth = _growth(current_revenue, prior_revenue)
        capex_growth = _growth(current_capex, prior_capex)
        capex_revenue_gap = capex_growth - revenue_growth
        derived = {
            "revenue_growth_pp": revenue_growth,
            "capital_expenditures_growth_pp": capex_growth,
            "capex_revenue_growth_gap_pp": capex_revenue_gap,
        }
        if current_oi <= 0:
            return capex_revenue_gap > gap_threshold, derived, (), (
                "nonpositive_operating_income_revenue_only_branch",
            )
        if prior_oi == 0:
            return None, {}, ("nonzero_prior_operating_income_required",), ()
        operating_income_growth = _growth(current_oi, prior_oi)
        capex_oi_gap = capex_growth - operating_income_growth
        derived.update({
            "operating_income_growth_pp": operating_income_growth,
            "capex_operating_income_growth_gap_pp": capex_oi_gap,
        })
        fired = capex_revenue_gap > gap_threshold and capex_oi_gap > gap_threshold
        return fired, derived, (), ()

    return compute


def _accruals_detector(
    spec: DetectorSpec,
    registry: ForensicsRegistry,
    selected: tuple[StatementVintage, ...],
    observations: dict[str, NormalizedObservation],
    *,
    computed_at: datetime,
    entity_cik: str,
) -> Finding:
    if len(selected) < 3:
        return _not_evaluable(
            spec, registry, entity_cik=entity_cik, period_ends=tuple(v.period_end for v in selected),
            inputs=(), source_observations=[], missing_inputs=("three_consecutive_annual_periods",),
            computed_at=computed_at,
        )
    window = selected[-3:]
    period_ends = tuple(item.period_end for item in window)
    pairs = tuple(
        (vintage, metric)
        for vintage in window
        for metric in ("net_income", "operating_cash_flow", "assets")
    )
    inputs, missing, source_items = _collect_inputs(pairs, observations)
    if not _periods_are_consecutive(window):
        missing = tuple(sorted(set(missing) | {"consecutive_annual_periods"}))
    if missing:
        return _not_evaluable(
            spec, registry, entity_cik=entity_cik, period_ends=period_ends, inputs=inputs,
            source_observations=source_items, missing_inputs=missing, computed_at=computed_at,
        )
    values = {(item.period_end, item.metric): Decimal(item.value) for item in inputs}
    ratios: list[Decimal] = []
    for period_end in period_ends:
        assets = values[(period_end, "assets")]
        if assets <= 0:
            return _not_evaluable(
                spec, registry, entity_cik=entity_cik, period_ends=period_ends, inputs=inputs,
                source_observations=source_items, missing_inputs=("positive_assets_required",),
                computed_at=computed_at,
            )
        ratios.append(
            (values[(period_end, "net_income")] - values[(period_end, "operating_cash_flow")])
            / assets
        )
    change = ratios[-1] - ratios[0]
    threshold = Decimal(spec.threshold_map()["min_three_period_increase"])
    fired = change >= threshold and ratios[-1] > ratios[0]
    derived = {f"accrual_ratio_{period}": ratio for period, ratio in zip(period_ends, ratios)}
    derived["accrual_ratio_change"] = change
    return _finding(
        spec,
        registry,
        entity_cik=entity_cik,
        state=FindingState.TRIGGERED if fired else FindingState.CLEAR,
        period_ends=period_ends,
        inputs=inputs,
        source_observations=source_items,
        derived_values=derived,
        computed_at=computed_at,
    )


def evaluate_detectors(
    normalized_observations: tuple[NormalizedObservation, ...],
    selected_vintages: tuple[StatementVintage, ...],
    registry: ForensicsRegistry,
    *,
    computed_at: datetime,
    detector_rules_eligible: bool = True,
    entity_cik: str,
) -> tuple[Finding, ...]:
    """Evaluate every registered detector; absence always becomes an explicit state."""
    observations = {item.observation_id: item for item in normalized_observations}
    selected = tuple(sorted(selected_vintages, key=lambda item: item.period_end))
    results: list[Finding] = []
    for spec in registry.detectors:
        if not detector_rules_eligible:
            results.append(
                _not_evaluable(
                    spec,
                    registry,
                    entity_cik=entity_cik,
                    period_ends=tuple(item.period_end for item in selected),
                    inputs=(),
                    source_observations=[],
                    missing_inputs=("detector_rule_unavailable_at_as_of",),
                    computed_at=computed_at,
                )
            )
            continue
        if spec.detector_id == "accruals_trending_up":
            results.append(
                _accruals_detector(
                    spec, registry, selected, observations, computed_at=computed_at,
                    entity_cik=entity_cik,
                )
            )
            continue
        pair_periods = (
            tuple(item.period_end for item in selected[-2:])
            if len(selected) >= 2 else ("", "")
        )
        if spec.detector_id == "margin_compression_despite_revenue_growth":
            metrics = ("revenue", "gross_profit")
            compute = _margin_compute(spec, pair_periods)
        elif spec.detector_id == "receivables_stretch":
            metrics = ("revenue", "accounts_receivable")
            compute = _working_capital_compute(
                spec, pair_periods, "accounts_receivable", "growth_gap_pp"
            )
        elif spec.detector_id == "inventory_build":
            metrics = ("revenue", "inventory")
            compute = _working_capital_compute(spec, pair_periods, "inventory", "growth_gap_pp")
        elif spec.detector_id == "capital_intensity_rising":
            metrics = ("revenue", "capital_expenditures", "operating_income")
            compute = _capital_intensity_compute(spec, pair_periods)
        else:
            raise ValueError(f"unknown detector in registry: {spec.detector_id}")
        results.append(
            _two_period_detector(
                spec,
                registry,
                selected,
                observations,
                metrics=metrics,
                computed_at=computed_at,
                compute=compute,
                entity_cik=entity_cik,
            )
        )
    return tuple(sorted(results, key=lambda item: item.detector_id))
