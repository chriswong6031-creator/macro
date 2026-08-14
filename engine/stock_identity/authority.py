"""The all-false authority block carried by every Identity Atlas artifact.

Masterplan §12.2 / registration §"Hard exclusion": the Identity Atlas is
descriptive. Nothing it produces may rank, size, gate, originate a signal, or
escalate. That is not a convention here — it is a field written into every JSON
artifact and every parquet's sidecar manifest, so a downstream reader that
forgets the law still sees it stamped on the data.

The five keys and their ``false`` values are frozen. A future promotion would be
a separate, separately-gated construction with its own registration; it would not
edit this file's defaults.
"""
from __future__ import annotations

from typing import Any

AUTHORITY_KEYS: tuple[str, ...] = (
    "can_rank",
    "can_size",
    "can_gate",
    "can_originate_signal",
    "can_escalate",
)

#: The literal block. Callers must copy, never mutate.
AUTHORITY_BLOCK: dict[str, bool] = {k: False for k in AUTHORITY_KEYS}


def authority_block() -> dict[str, bool]:
    """A fresh all-false authority block (a copy, so a caller cannot poison it)."""
    return {k: False for k in AUTHORITY_KEYS}


def stamp_authority(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach the authority block to a JSON-bound payload, in place, and return it."""
    payload["authority"] = authority_block()
    return payload


def is_zero_authority(payload: Any) -> bool:
    """True iff ``payload`` carries a complete, all-false authority block."""
    if not isinstance(payload, dict):
        return False
    block = payload.get("authority")
    if not isinstance(block, dict):
        return False
    if set(block) != set(AUTHORITY_KEYS):
        return False
    return all(block[k] is False for k in AUTHORITY_KEYS)
