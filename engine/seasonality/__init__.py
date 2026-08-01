"""Clean-room seasonality intelligence primitives.

This package is intentionally separate from :mod:`engine.factor_seasonality`.
The existing module is a display-only Ken French factor climate.  This package
owns the point-in-time contracts and selection-aware statistics for the future
calendar, catalyst, and regime clocks used by biopharma seasonality.
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
from .multiplicity import (
    benjamini_yekutieli,
    max_t_adjusted_p_values,
)

__all__ = [
    "BIOTEMPORAL_EVENT_SCHEMA",
    "NEURALWEB_STATE_SCHEMA",
    "PROPHET_OVERLAY_SCHEMA",
    "ContractError",
    "benjamini_yekutieli",
    "build_neuralweb_state",
    "build_prophet_overlay",
    "max_t_adjusted_p_values",
    "validate_bitemporal_event",
    "validate_neuralweb_state",
    "validate_prophet_overlay",
]
