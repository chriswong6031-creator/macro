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
package still costs nothing on a thin runner.

``event_study`` is NOT in that class — it is numpy/pandas-bound — so it is reachable
as an attribute through the PEP 562 ``__getattr__`` at the bottom of this file, which
imports it only when something actually asks for it, and it stays out of ``__all__``
so ``import *`` never drags the scientific stack in behind it.
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
    "EVENT_CLOCK_READ_SCHEMA",
    "EXPECTED_PROJECTION_CONTRACT",
    "NEURALWEB_STATE_SCHEMA",
    "PROPHET_OVERLAY_SCHEMA",
    "QUARANTINE_REASON_CODES",
    "ContractError",
    "UniverseRead",
    "benjamini_yekutieli",
    "build_neuralweb_state",
    "build_prophet_overlay",
    "corporate_actions_asof",
    "coverage_report",
    "earliest_snapshot",
    "latest_snapshot",
    "max_t_adjusted_p_values",
    "membership_asof",
    "price_adjustment_vintage",
    "read_event_projection",
    "resolve_issuer_unavailable",
    "resolve_security_asof",
    "snapshot_dates",
    "validate_bitemporal_event",
    "validate_neuralweb_state",
    "validate_prophet_overlay",
]

#: Modules that carry a numpy/pandas dependency and therefore may not be imported
#: eagerly here (see the module docstring).  They resolve on first attribute access.
_LAZY_MODULES = ("event_study",)


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
