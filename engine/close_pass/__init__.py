"""engine.close_pass — the evening provisional US board (W-L1a).

The nightly stays the sole writer of record. This package answers one narrower
question from the day's closes alone, hours earlier: *given today's closes, who
would tonight's admission gate admit, and in what close-derived order?*

Nothing here writes ``data/``, advances a ledger, or claims authority. The
payload is display-tier and stamped ``provisional: true``.
"""
from __future__ import annotations

from engine.close_pass.board import (  # noqa: F401
    CLOSE_DERIVED_LEGS,
    LANE,
    NIGHTLY_EXPECTED_BY_UTC,
    OMITTED_LEGS,
    SCHEMA,
    WEIGHT_COVERED,
    board_state,
    build_board,
    close_legs,
    valid_until,
)
from engine.close_pass.reconcile import (  # noqa: F401
    RECEIPT_SCHEMA,
    board_state_payload,
    confirmation_receipt,
)

# `board_state` (board.py — the PROVISIONAL side) and `board_state_payload`
# (reconcile.py — the CONFIRMED side) are deliberately distinct names: they are
# two projections of two different documents, and a shared name here would
# silently rebind one of them on import order.
__all__ = [
    "CLOSE_DERIVED_LEGS", "LANE", "NIGHTLY_EXPECTED_BY_UTC", "OMITTED_LEGS",
    "SCHEMA", "WEIGHT_COVERED", "RECEIPT_SCHEMA", "board_state",
    "board_state_payload", "build_board", "close_legs", "confirmation_receipt",
    "valid_until",
]
