"""Back-compat shim — the per-name POTENTIAL-score grader is now market-aware and lives
in engine/name_score_grader.py. China keeps calling ``append_name_calls(calls, asof=...)``
and ``grade()`` (market defaults to "CN", and CN keeps its legacy ledger path). See
engine/name_score_grader.py and [[china-name-potential-score]].
"""
from __future__ import annotations

from lib import config  # noqa: F401  — re-exported so existing tests/callers can patch config.data_dir
from engine.name_score_grader import (  # noqa: F401  — re-exported for existing call sites
    append_name_calls,
    grade,
)
