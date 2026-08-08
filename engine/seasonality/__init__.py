"""Clean-room seasonality intelligence primitives.

This package is intentionally separate from :mod:`engine.factor_seasonality`.
The existing module is a display-only Ken French factor climate.  This package
owns the point-in-time contracts and selection-aware statistics for the
calendar, catalyst, and regime clocks used by biopharma seasonality.

Only the pure-stdlib modules are re-exported here, and that is DELIBERATE:
``contracts`` and ``multiplicity`` are advertised as usable by ingestion jobs and
thin CI runners with no pandas/numpy installed, and eagerly importing
``panel``/``calendar``/``scanner`` from this file would silently make
``import engine.seasonality`` require the scientific stack.  Import those three
by module path (``from engine.seasonality import panel``) instead of adding them
below.

``universe`` is re-exported here because it keeps the same bargain: its module
scope is pure stdlib and it defers ``pandas``/``yaml`` into the functions that
actually read a parquet snapshot or the ownership registry, so importing this
package still costs nothing on a thin runner.  ``screener`` keeps it too: it is
pure stdlib end to end and reaches ``universe`` only through an injected
resolver, so it reads no store itself.

``event_study`` is NOT in that class — it is numpy/pandas-bound — so it is reachable
as an attribute through the PEP 562 ``__getattr__`` at the bottom of this file, which
imports it only when something actually asks for it, and it stays out of ``__all__``
so ``import *`` never drags the scientific stack in behind it.

The ``screener`` re-export is DELIBERATELY partial.  ``build_research_result_set``
is the gated entry point: it is the only function that takes a consumer identity
and runs ``assert_consumer_permitted``, so a Prophet/Neural Web path asking for
this research-tier artifact is refused BY NAME.  The ordering, row-building, and
cohort primitives underneath it take no identity at all, and publishing them at
package level made "import the package, call ``order_rows``" a supported way
around the only gate this artifact has.  They stay reachable — ``from
engine.seasonality import screener`` — because that is a deliberate act by a
caller who has read the module, not a package-level convenience.

``screener`` also defines ``UNCERTAINTY_SEMANTICS``, ``UncertaintySemanticsError``,
and ``assert_uncertainty_semantics``, and none of the three is re-exported here.
The first two names are already published by this package from ``model``, and
``screener``'s error is a different class — a ``ScreenerError``, not a
``SeasonalityModelError`` — so re-exporting it would silently rebind a name that
callers already catch around ``forecast``.  Exporting the validator by itself
would be worse: it raises the class this package does NOT publish, so the obvious
``except UncertaintySemanticsError`` wrapped around it would never fire.  All
three stay available as ``screener.<name>``, where the validator and the
exception it raises come from the same module.
"""

from .contracts import (
    BIOTEMPORAL_EVENT_SCHEMA,
    NEURALWEB_STATE_SCHEMA,
    NEURALWEB_STATE_V2_SCHEMA,
    PROPHET_OVERLAY_SCHEMA,
    SEASONALITY_BLOCK_KEYS,
    ContractError,
    build_neuralweb_state,
    build_neuralweb_state_v2,
    build_prophet_overlay,
    seasonality_state_projection,
    validate_bitemporal_event,
    validate_neuralweb_state,
    validate_neuralweb_state_v2,
    validate_prophet_overlay,
    validate_seasonality_state,
)
from .event_clock import (
    EVENT_CLOCK_READ_SCHEMA,
    EXPECTED_PROJECTION_CONTRACT,
    QUARANTINE_REASON_CODES,
    read_event_projection,
    resolve_issuer_unavailable,
)
from .model import (
    BUILD_FLOORS,
    MODEL_SCHEMA,
    MODEL_VERSION,
    OwnerProbabilityFeatureError,
    UNCERTAINTY_SEMANTICS,
    UncertaintySemanticsError,
    classify_feature,
    forecast,
    make_uncertainty,
    require_lawful_features,
    screen_features,
)
from .multiplicity import (
    benjamini_yekutieli,
    max_t_adjusted_p_values,
)
from .program_watch import (
    WATCH_SCHEMA,
    evaluate_program_watch,
    read_ledger_counts,
)
from .prophet_bridge import (
    OVERLAY_SET_SCHEMA,
    build_overlays_for_plans,
)
from .regime import (
    AUTHORIZED_AXES,
    DISPLAY_ONLY_AXES,
    RegimeFeatureError,
    conditional_estimate_or_context,
    interaction_eligibility,
    read_regime_context,
)
from .screener import (
    ESTIMATE_CALIBRATED,
    ESTIMATE_DESCRIPTIVE,
    ESTIMATE_TYPES,
    IS_CALIBRATED_SCREENER,
    NOT_CALIBRATED_REASON,
    PERMITTED_CONSUMERS,
    RESEARCH_BROWSER_SCHEMA,
    RESEARCH_ROW_SCHEMA,
    SORTABLE_COLUMNS,
    DeterminismError,
    LookaheadError,
    MachineAuthorityRefused,
    MixedEstimateAxisError,
    ResearchRow,
    ScreenerError,
    SortKeyError,
    TierDeclarationError,
    UniverseDisclosure,
    assert_consumer_permitted,
    assert_research_tier_intact,
    build_result_set as build_research_result_set,
    program_multiplicity,
    resolve_universe,
)
from .universe import (
    UNRESOLVED_BLOCKER,
    UniverseRead,
    corporate_actions_asof,
    coverage_report,
    earliest_snapshot,
    latest_snapshot,
    membership_asof,
    price_adjustment_vintage,
    resolve_security_asof,
    snapshot_dates,
)

__all__ = [
    "AUTHORIZED_AXES",
    "BIOTEMPORAL_EVENT_SCHEMA",
    "BUILD_FLOORS",
    "ContractError",
    "DISPLAY_ONLY_AXES",
    "DeterminismError",
    "ESTIMATE_CALIBRATED",
    "ESTIMATE_DESCRIPTIVE",
    "ESTIMATE_TYPES",
    "EVENT_CLOCK_READ_SCHEMA",
    "EXPECTED_PROJECTION_CONTRACT",
    "IS_CALIBRATED_SCREENER",
    "LookaheadError",
    "MODEL_SCHEMA",
    "MODEL_VERSION",
    "MachineAuthorityRefused",
    "MixedEstimateAxisError",
    "NEURALWEB_STATE_SCHEMA",
    "NEURALWEB_STATE_V2_SCHEMA",
    "NOT_CALIBRATED_REASON",
    "OVERLAY_SET_SCHEMA",
    "OwnerProbabilityFeatureError",
    "PERMITTED_CONSUMERS",
    "PROPHET_OVERLAY_SCHEMA",
    "QUARANTINE_REASON_CODES",
    "RESEARCH_BROWSER_SCHEMA",
    "RESEARCH_ROW_SCHEMA",
    "RegimeFeatureError",
    "ResearchRow",
    "SEASONALITY_BLOCK_KEYS",
    "SORTABLE_COLUMNS",
    "ScreenerError",
    "SortKeyError",
    "TierDeclarationError",
    "UNCERTAINTY_SEMANTICS",
    "UNRESOLVED_BLOCKER",
    "UncertaintySemanticsError",
    "UniverseDisclosure",
    "UniverseRead",
    "WATCH_SCHEMA",
    "assert_consumer_permitted",
    "assert_research_tier_intact",
    "benjamini_yekutieli",
    "build_neuralweb_state",
    "build_neuralweb_state_v2",
    "build_overlays_for_plans",
    "build_prophet_overlay",
    "build_research_result_set",
    "classify_feature",
    "conditional_estimate_or_context",
    "corporate_actions_asof",
    "coverage_report",
    "earliest_snapshot",
    "evaluate_program_watch",
    "forecast",
    "interaction_eligibility",
    "latest_snapshot",
    "make_uncertainty",
    "max_t_adjusted_p_values",
    "membership_asof",
    "price_adjustment_vintage",
    "program_multiplicity",
    "read_event_projection",
    "read_ledger_counts",
    "read_regime_context",
    "require_lawful_features",
    "resolve_issuer_unavailable",
    "resolve_security_asof",
    "resolve_universe",
    "screen_features",
    "seasonality_state_projection",
    "snapshot_dates",
    "validate_bitemporal_event",
    "validate_neuralweb_state",
    "validate_neuralweb_state_v2",
    "validate_prophet_overlay",
    "validate_seasonality_state",
]

#: Modules that carry a numpy/pandas dependency and therefore may not be imported
#: eagerly here (see the module docstring).  They resolve on first attribute access.
_LAZY_MODULES = ("calibration", "event_study")


def __getattr__(name: str):
    """Resolve the heavy submodules on demand — PEP 562.

    ``from engine.seasonality import event_study`` already works as a submodule
    import; this exists so ``engine.seasonality.event_study`` also resolves after a
    bare ``import engine.seasonality``, without making the package itself require
    the scientific stack that the thin ingestion runners deliberately do not have.
    """
    if name in _LAZY_MODULES:
        import importlib

        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
