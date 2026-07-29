"""engine.prophet_live — Prophet Live P0: provisional-close arming + intraday states.

Two speeds, one engine (research/PROPHET_LIVE_INTRADAY_SIGNALS_MASTERPLAN_BY_FABLE.md):
the nightly build arms a per-name trigger pack by probing the SAME close-only
admission gate with candidate provisional closes; a light */5 lane re-runs the
comparison against a delayed live price. No second signal engine exists.

Modules
-------
``interval``     the published interval contract — stdlib only, ONE reader.
``armed_pack``   nightly arming pass (pandas + engine.signal_gate). Heavy.
``live_states``  the intraday state machine — pure stdlib, no pandas, no I/O.
``r2io``         shared R2 object helpers (boto3, lazily imported).

IMPORT DISCIPLINE — this ``__init__`` pulls NOTHING. The */5 evaluator installs
``requests pyyaml boto3`` and no pandas, so a package-level re-export of
``armed_pack`` would make ``from engine.prophet_live import live_states`` raise
ModuleNotFoundError on that lane. Import the submodule you need by name.
"""
from __future__ import annotations

__all__: list[str] = []
