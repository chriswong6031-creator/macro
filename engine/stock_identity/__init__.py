"""Stock Identity — Identity Atlas v0 (W1 / PR-1).

Descriptive, measurement-first behavioral layer registered by
``research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md`` under the frozen
contract ``research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md``.

What lives here
---------------
``plane``       universe enumeration + per-symbol normalized OHLCV loader (§1)
``partition``   blind evaluation arm + sealed calibration partition draws (§3/§4)
``fingerprint`` the frozen v0 behavioral-fingerprint enumeration (§5)
``state``       the eight-state bars-only tagger (§6)
``episodes``    the expert-independent path-anchored episode catalog (§7)
``census``      the coverage census + calendar clusters (§8)
``dossier``     per-name operator-readable markdown + chart (§14 PR-1 row)
``authority``   the all-false authority block every artifact carries

Standing laws this package is written against
---------------------------------------------
* **Zero authority.** Every artifact produced here ships
  ``authority = {can_rank, can_size, can_gate, can_originate_signal,
  can_escalate}`` all false. Nothing here ranks, sizes, gates, originates a
  signal, or escalates anything.
* **No expert-fit content in W1** (masterplan §16.9). No expert identifier, fit
  metric, ordering, or "best" field exists in any schema, column, artifact or
  identifier this package produces. The episode catalog is built with no expert
  event anywhere in its construction (G-3).
* **Causal by construction.** Every fingerprint and state value at a date is a
  function of that date's trailing data only — truncation-invariance is
  test-enforced. Episode *resolution* labels use future data by design and are a
  research-time labeling instrument only (masterplan §7.2); they never ship live.
* **Plane law.** Only the TR-adjusted deep planes are read (``data/stocks``,
  ``data/baskets/ohlcv``, and the program-owned ``data/stock_identity/ohlcv``);
  ``price_plane_id`` is recorded on every row. A feature family structurally
  unavailable on a plane is excluded from the metric block rather than masked
  (masterplan §4 law vi) — this is why the gap family is diagnostic-only here.
* **Vocabulary.** The object is a *behavioral fingerprint* / *identity*; the
  prior repo sense of the other word is a different thing and is not used.
  "Identity episode" is always qualified in prose.

Import discipline: this package imports no gate-chain, signal, or ranking module
(the G-8 protected set), and never imports from ``scripts/``. It exports nothing
heavy at import time — submodules are imported explicitly by callers.
"""
from __future__ import annotations

__all__ = ["AUTHORITY_BLOCK", "authority_block", "SPEC_VERSION"]

SPEC_VERSION = "v0"

# Re-exported here because every submodule and every artifact needs it; this is a
# plain dict of five false booleans, not a heavy import.
from engine.stock_identity.authority import (  # noqa: E402
    AUTHORITY_BLOCK,
    authority_block,
)
