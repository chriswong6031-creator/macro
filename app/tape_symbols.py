"""Dependency-free symbol contract for the six-instrument macro tape."""

from __future__ import annotations

# ORDER mirrors the dashboard strip and drives the Yahoo upstream subscription.
TAPE_SYMBOLS: tuple[str, ...] = (
    "ES=F",
    "NQ=F",
    "YM=F",
    "RTY=F",
    "^TNX",
    "DX-Y.NYB",
)
