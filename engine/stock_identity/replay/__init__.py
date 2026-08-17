"""Stock Identity — Expert Replay + Provenance Pinning (W2 / PR-2).

Registered by ``research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md`` under the
frozen contract ``research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md``
(§5 expert library, §7.3 attribution clause, §9.4 leakage, §14 PR-2 row).

What this subpackage is
-----------------------
It reconstructs and preserves **entry-event families with their provenance**. It
produces an event history per family, the typed edges between events, and the join
from events to the W1 identity-episode catalog. Nothing else.

What it is NOT — and this is a law, not a preference
----------------------------------------------------
**W2 publishes no ruler metric.** No lead/lag, no distance-to-anchor, no MAE, no
capture, no recall, no precision, no composite, no fit, no rank, no "best". Those are
PR-3's object and their absence here is test-enforced (``tests/test_stock_identity_
replay.py::TestNoRulerContent``). The only aggregates W2 publishes are **inventory
counts** (events per family x name x era x provenance) and **join-coverage counts**.
There is no per-name expert selection, no routing authority, and no outcome audition
(``DNR:KILL-OUTCOME-AUDITION``) anywhere in this subpackage.

The import firewall (registration §2 — scoped, test-enforced)
--------------------------------------------------------------
W1's firewall over ``engine/stock_identity/**`` remains **TOTAL for the identity
layer** (``plane/partition/fingerprint/state/episodes/hygiene/census/dossier`` — the
episode catalog stays expert-free, G-3). This subpackage holds the ONLY exemption: it
may import, **read-only**, exactly these producers so a family is recomputed by *the
engine's own function* rather than re-implemented (re-implementation is the silent-fork
hazard — archaeology §4.2):

``engine.signal_quality`` · ``engine.confluence_tiers`` · ``engine.washout_turn`` ·
``engine.canon`` · ``engine.us_early_turn``

Never imported anywhere in this package: ``engine.signal_gate`` (authority, not event
math), ``engine.prophet_*``, ``engine.entry_radar.*``, ``engine.stock_personality``,
``engine.oracle.*``, Terminal internals, and anything under ``scripts/``. Imports
mutate nothing, so the G-8 clean-diff obligation is untouched.

Provenance laws carried on every row
------------------------------------
* ``known_ts`` law (G-4 / masterplan §9.4): ``signal_known_ts`` is the **completion
  timestamp of the bar that fires the event** — the daily close for a 1D event, the
  completing session's close for a 2D/3D bucket, the completed W-FRI close for a weekly
  organ. Completed bars only; provisional-bar readings are prohibited. ``known_basis``
  records which rule applied, per row.
* ``family_first_available`` / ``family_era``: structural absence is never read as
  negative evidence. A family born on a date has no history before it and ships **zero
  rows** rather than a backfill.
* ``spec_postdates_history``: a locked-spec backcast (Class B) is stamped on every row
  and may never be cited as evidence that the family *as it then existed* localized
  anything.
* ``scored_authority`` is a **recorded fact** about what the emitter's own authority was
  at the time — never a grant, and nothing here grants authority to anything.
* Every artifact carries the five-key all-false authority block.

Module map (registration §8)
----------------------------
``grid``            bucket grids + the known-ts maps each producer's own convention implies
``events``          event schema, deterministic ids, typed edges, the R1 vintage stamp
``registry``        the family registry — keys minted from producer receipts, never invented
``grey_dot``        ``grey_dot_macro`` (dual as-recorded / as-restated) + the ``grey_dot_terminal`` twin
``confirmed_buy``   ledger extraction from ``track_record.parquet`` + the deeper recompute
``tiers``           ``tier_cascade_t1..t4`` onsets via ``tier_stream()``
``washout_turn``    the weekly organ: ledger union earlier truncated-frame recompute
``reclaim_waiver``  re-derived ONLY over the committed nightly state artifact's own era
``bottom_watch``    the locked-spec C5 port (Radar contract §3.4)
``starter``         the union-admission signature + the licensing-context PIT investigation
``sea``             the SEA event store join (keep-FIRST honored)
``naive``           the three frozen reference comparators
``leak``            the leak fixtures every family must pass before its events ship
``attribution``     event -> identity episode, under W1's frozen ``P_pre``
"""
from __future__ import annotations

__all__ = ["SPEC_VERSION", "ALLOWED_PRODUCER_IMPORTS", "FORBIDDEN_PRODUCER_IMPORTS"]

SPEC_VERSION = "v0"

#: The scoped allowlist of registration §2. The firewall test reads THIS tuple, so the
#: law and the code cannot drift apart.
ALLOWED_PRODUCER_IMPORTS: tuple[str, ...] = (
    "engine.signal_quality",
    "engine.confluence_tiers",
    "engine.washout_turn",
    "engine.canon",
    "engine.us_early_turn",
)

#: Never imported anywhere in ``engine/stock_identity/**``, replay included.
FORBIDDEN_PRODUCER_IMPORTS: tuple[str, ...] = (
    "engine.signal_gate",
    "engine.entry_signal",
    "engine.mtf_upturn",
    "engine.stock_personality",
    "engine.oracle.personality_context",
)
