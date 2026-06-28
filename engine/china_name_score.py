"""Back-compat shim — the per-name POTENTIAL score is now market-aware and lives in
engine/name_score.py. China keeps calling ``potential_score(rec, regime_stress=...)``
(market defaults to "CN", edge_mult=1, so behaviour is unchanged); the general engine
adds the per-market validated-edge blend for US/CA/INTL. See engine/name_score.py and
[[china-name-potential-score]].
"""
from __future__ import annotations

from engine.name_score import (  # noqa: F401  — re-exported for existing call sites
    _BANDS,
    _band,
    potential_score,
)
