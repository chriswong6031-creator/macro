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
from .prophet_bridge import (
    OVERLAY_SET_SCHEMA,
    build_overlays_for_plans,
)

__all__ = [
    "BIOTEMPORAL_EVENT_SCHEMA",
    "EVENT_CLOCK_READ_SCHEMA",
    "EXPECTED_PROJECTION_CONTRACT",
    "NEURALWEB_STATE_SCHEMA",
    "OVERLAY_SET_SCHEMA",
    "PROPHET_OVERLAY_SCHEMA",
    "QUARANTINE_REASON_CODES",
    "ContractError",
    "benjamini_yekutieli",
    "build_neuralweb_state",
    "build_overlays_for_plans",
    "build_prophet_overlay",
    "max_t_adjusted_p_values",
    "read_event_projection",
    "resolve_issuer_unavailable",
    "validate_bitemporal_event",
    "validate_neuralweb_state",
    "validate_prophet_overlay",
]
