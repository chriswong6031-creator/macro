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

The ``screener`` re-export is DELIBERATELY partial.  ``build_research_result_set``
is the gated entry point: it is the only function that takes a consumer identity
and runs ``assert_consumer_permitted``, so a Prophet/Neural Web path asking for
this research-tier artifact is refused BY NAME.  The ordering, row-building, and
cohort primitives underneath it take no identity at all, and publishing them at
package level made "import the package, call ``order_rows``" a supported way
around the only gate this artifact has.  They stay reachable — ``from
engine.seasonality import screener`` — because that is a deliberate act by a
caller who has read the module, not a package-level convenience.
"""

from .contracts import (
    BIOTEMPORAL_EVENT_SCHEMA,
    NEURALWEB_STATE_SCHEMA,
    PROPHET_OVERLAY_SCHEMA,
    ContractError,
    build_neuralweb_state,
    build_prophet_overlay,
    validate_bitemporal_event,
    validate_neuralweb_state,
    validate_prophet_overlay,
)
from .event_clock import (
    EVENT_CLOCK_READ_SCHEMA,
    EXPECTED_PROJECTION_CONTRACT,
    QUARANTINE_REASON_CODES,
    read_event_projection,
    resolve_issuer_unavailable,
)
from .multiplicity import (
    benjamini_yekutieli,
    max_t_adjusted_p_values,
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
    UNCERTAINTY_SEMANTICS,
    DeterminismError,
    LookaheadError,
    MachineAuthorityRefused,
    MixedEstimateAxisError,
    ResearchRow,
    ScreenerError,
    SortKeyError,
    TierDeclarationError,
    UncertaintySemanticsError,
    UniverseDisclosure,
    assert_consumer_permitted,
    assert_research_tier_intact,
    assert_uncertainty_semantics,
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
    "UNRESOLVED_BLOCKER",
    "BIOTEMPORAL_EVENT_SCHEMA",
    "ESTIMATE_CALIBRATED",
    "ESTIMATE_DESCRIPTIVE",
    "ESTIMATE_TYPES",
    "EVENT_CLOCK_READ_SCHEMA",
    "EXPECTED_PROJECTION_CONTRACT",
    "IS_CALIBRATED_SCREENER",
    "NEURALWEB_STATE_SCHEMA",
    "NOT_CALIBRATED_REASON",
    "PERMITTED_CONSUMERS",
    "PROPHET_OVERLAY_SCHEMA",
    "QUARANTINE_REASON_CODES",
    "RESEARCH_BROWSER_SCHEMA",
    "RESEARCH_ROW_SCHEMA",
    "SORTABLE_COLUMNS",
    "UNCERTAINTY_SEMANTICS",
    "ContractError",
    "DeterminismError",
    "LookaheadError",
    "MachineAuthorityRefused",
    "MixedEstimateAxisError",
    "ResearchRow",
    "ScreenerError",
    "SortKeyError",
    "TierDeclarationError",
    "UncertaintySemanticsError",
    "UniverseDisclosure",
    "UniverseRead",
    "assert_consumer_permitted",
    "assert_research_tier_intact",
    "assert_uncertainty_semantics",
    "benjamini_yekutieli",
    "build_neuralweb_state",
    "build_prophet_overlay",
    "build_research_result_set",
    "corporate_actions_asof",
    "coverage_report",
    "earliest_snapshot",
    "latest_snapshot",
    "max_t_adjusted_p_values",
    "membership_asof",
    "price_adjustment_vintage",
    "program_multiplicity",
    "read_event_projection",
    "resolve_issuer_unavailable",
    "resolve_security_asof",
    "resolve_universe",
    "snapshot_dates",
    "validate_bitemporal_event",
    "validate_neuralweb_state",
    "validate_prophet_overlay",
]
