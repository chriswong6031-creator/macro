"""engine/levels_ledger.py — the sealed pre-open Ledger for the levels board.

Voltick Gamma-Levels program, WP-C3. Each trading morning, before the bell, the day's named
levels for every board are written to one canonical file and sealed with a SHA-256 hash,
published immediately. After the close the same grader behind the Track Record (WP-C1) scores
that day. The hash proves the file has not changed by a single byte since it was sealed: the
map came first, and anyone can check with `shasum -a 256`.

This module is the PURE core: canonicalization + hashing + the sealed-board projection. No
I/O, no clock — the driver (scripts/seal_levels_ledger.py) computes the boards, stamps the
sealed_at time, writes the file, and appends to the public manifest.

DISPLAY-TIER: a record of where the positioning map sat before each session — a measurement,
never a forecast, never a reason to trade. Positioning, not prophecy.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "levels_ledger.v1"
INDEX_SCHEMA = "levels_ledger.index/v1"

# The named levels that are sealed and later graded (the "prediction" written before the open).
_SEAL_ROLES = ("anchor", "call_wall", "put_wall", "flip", "cluster", "counter")


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic JSON bytes for hashing: sorted keys, no whitespace, UTF-8.

    Re-serializing the same logical object always yields identical bytes, so re-hashing a
    downloaded file reproduces the published hash exactly.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal_board(levels_payload: dict) -> dict | None:
    """Project a ``levels.v1`` board down to the sealed prediction for one root.

    Keeps only what will be graded: root, session date, spot, regime, the expected-move band
    inputs, and the located named levels (role → strike + sticky). Deterministic ordering
    (nodes sorted by role then strike) so the canonical bytes are stable.
    """
    if not levels_payload or not isinstance(levels_payload.get("nodes"), list):
        return None
    root = levels_payload.get("root")
    session_date = levels_payload.get("asof") or levels_payload.get("session_date")
    if not root or not session_date:
        return None
    nodes = []
    for nd in levels_payload["nodes"]:
        if not isinstance(nd, dict):
            continue
        if nd.get("role") not in _SEAL_ROLES:
            continue
        strike = nd.get("strike")
        if strike is None:
            continue
        nodes.append({
            "role": nd.get("role"),
            "strike": round(float(strike), 4),
            "sticky": (bool(nd["sticky"]) if nd.get("sticky") is not None else None),
        })
    nodes.sort(key=lambda n: (n["role"], n["strike"]))
    regime = levels_payload.get("regime") or {}
    return {
        "root": root,
        "session_date": session_date,
        "spot": (round(float(levels_payload["spot"]), 4)
                 if levels_payload.get("spot") is not None else None),
        "regime": (regime.get("label") if isinstance(regime, dict) else None),
        "nodes": nodes,
    }


def build_ledger_file(session_date: str, sealed_boards: list[dict], sealed_at: str | None = None) -> dict:
    """Assemble the canonical per-session sealed file (before hashing).

    sealed_boards: list of seal_board() outputs. sealed_at: an ISO timestamp stamped by the
    driver (this module keeps no clock). Boards are sorted by root for byte-stability.
    """
    boards = sorted((b for b in sealed_boards if b), key=lambda b: b["root"])
    return {
        "schema": SCHEMA,
        "session_date": session_date,
        "sealed_at": sealed_at,
        "n_boards": len(boards),
        "boards": boards,
    }


def seal(session_date: str, sealed_boards: list[dict], sealed_at: str | None = None) -> tuple[dict, str]:
    """Return (canonical file dict, sha256 hex of its canonical bytes)."""
    f = build_ledger_file(session_date, sealed_boards, sealed_at=sealed_at)
    return f, sha256_hex(canonical_bytes(f))


def verify(ledger_file: dict, expected_sha256: str) -> bool:
    """Re-hash a sealed file and compare — the public integrity check."""
    return sha256_hex(canonical_bytes(ledger_file)) == expected_sha256


def index_entry(ledger_file: dict, sha256: str) -> dict:
    """One row of the public manifest (levels_ledger/index.json)."""
    return {
        "session_date": ledger_file.get("session_date"),
        "sealed_at": ledger_file.get("sealed_at"),
        "n_boards": ledger_file.get("n_boards"),
        "roots": sorted(b["root"] for b in ledger_file.get("boards", [])),
        "sha256": sha256,
    }
