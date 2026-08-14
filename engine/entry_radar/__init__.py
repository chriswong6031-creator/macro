"""engine/entry_radar — Live Entry Radar: probe universe + candidate enlistment bus.

DISPLAY / RESEARCH TIER.  Authority block on every published artifact:
``can_rank / can_size / can_gate / can_originate_signal / can_escalate = false``
(DRL convention, `research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` §2).
Nothing in the pick chain imports this package; this package imports nothing
from Prophet, from the entry gate, or from any scoring consumer.

WHAT RADAR IS
-------------
Radar is the **WHEN** organ.  It asks one question — *is an unusually attractive
early entry forming right now, before full confirmation?* — and it asks it
separately from *is this worth owning?* (Prophet / Own-It) and from *has enough
confluence arrived?* (`engine/entry_signal.py`).  Those three questions stay
separate permanently (contract §1).

WHAT THIS PACKAGE (PR-1) IS
---------------------------
The **funnel** and the **bus**, nothing else:

  ``contracts.py``       frozen record shapes — `mastermind.entry_probe_nomination.v1`,
                         the Probe Set record, the authority block, availability states
  ``universe.py``        funnel Layers A (broad eligibility + wrapper classifier),
                         B (core/index/liquid/operator), C (dynamic hot), D (lobe
                         nominations), and Probe Set assembly
  ``nomination_bus.py``  ingestion, dedup identity, TTL expiry, correlated-family
                         disclosure
  ``producers/``         one adapter per artifact-based producer (Track C census)
  ``spool.py``           the durable prospective nomination spool

NO DETECTOR CODE LIVES HERE.  No StochRSI, no MACD, no oscillator math of any
kind — those are PR-2 (G0) and PR-3 (C1–C5).  This package computes admission,
and admission is a *coverage* decision.

ADMISSION IS NOT BULLISHNESS
----------------------------
The single most important law in this package.  A name is in the Probe Set
because something asked us to *look at it*, never because anything thinks it
will go up.  Consequently the Probe Set record carries **no score, no rank, no
points, no `candidate` boolean, no bullish field of any kind** — enforced by
`contracts.PROBE_RECORD_FIELDS` and by
`tests/test_entry_radar_w1.py::test_probe_record_carries_no_score_field`.
Hotness admits; it never scores (contract §9).  Five lobe badges are not +25.

NO FLATTENING (contract §16 / §18 A1.2)
---------------------------------------
Nothing downstream of Radar may be forced to reconstruct a distinction Radar
dissolved.  One ticker carrying six nominations keeps six nomination records
with six provenances — they are never collapsed into a count, a boolean, or a
"lobe score".  A basket-level fact never launders into a single-name fact: it
carries its own `membership_expansion` family and its own reason-code prefix,
and `contracts` refuses the mislabelling in both directions.

MISSING IS NOT NEGATIVE (contract §5)
-------------------------------------
A producer that could not be read is `unavailable` with an age.  It is never an
empty list, and an empty list is never a negative observation.  See
`universe.assemble_probe_set` for the retention rule this implies.

BOUNDARY WITH THE ADJACENT PER-NAME ORGANS (contract §2)
--------------------------------------------------------
`engine/washout_turn.py` is a **weekly** washout-turn watch organ and
`engine/mtf_upturn.py` is the TS-R3 multi-timeframe upturn organ; both are
display-tier per-name organs at a *different grain* (weekly / multi-week) and a
*different product* (watch vocabulary) than Radar's 1D-live episode ledger and
ranking.  `engine/ignition_radar.py` is market/basket-grain breadth — name
collision only.  `engine/setups.py` and `engine/stock_personality.py` are
downstream consumers: they may read Radar output later; **Radar never writes
into their scoring**, and Radar never imports them.

Radar likewise does not absorb Stock Identity, Prophet, or Intelligence-Hub
scoring.  Per-name outcome statistics never enter any Radar score, rank, gate,
or calibration feature, and ticker identity is never a model feature
(contract §18 A2.5.1–2) — the ticker key is memory and continuity, never a
strategy key.

WRITE DISCIPLINE (contract §7.3)
--------------------------------
PR-1 production code writes **no** ``data/`` path.  The Probe Set artifact goes
to the live-dir ladder (``$MACRO_LIVE_DIR`` → ``/var/lib/macro-live/public/live``
→ ``site/live``) by atomic rename; the nomination spool goes to R2 (or a local
fallback directory in tests).  The nightly reconciler of PR-5 is the only
durable ``data/`` writer, gated by
``engine/ledger_lane.py::nightly_advance_enabled()``.
"""
from __future__ import annotations

from engine.entry_radar.contracts import (
    AUTHORITY_BLOCK,
    AVAILABILITY_STATES,
    ELIGIBILITY_STATES,
    NOMINATION_FIELDS,
    NOMINATION_SCHEMA,
    PROBE_RECORD_FIELDS,
    PROBE_SET_SCHEMA,
    SOURCE_FAMILIES,
    SOURCE_STATUSES,
    AdmissionReason,
    Nomination,
    NominationError,
    ProbeRecord,
    ProducerRead,
)

__all__ = [
    "AUTHORITY_BLOCK",
    "AVAILABILITY_STATES",
    "ELIGIBILITY_STATES",
    "NOMINATION_FIELDS",
    "NOMINATION_SCHEMA",
    "PROBE_RECORD_FIELDS",
    "PROBE_SET_SCHEMA",
    "SOURCE_FAMILIES",
    "SOURCE_STATUSES",
    "AdmissionReason",
    "Nomination",
    "NominationError",
    "ProbeRecord",
    "ProducerRead",
]
