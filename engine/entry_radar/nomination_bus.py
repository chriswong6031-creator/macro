"""engine/entry_radar/nomination_bus.py — candidate enlistment bus.

The single door every lobe nomination walks through.  It does four things and
deliberately nothing else:

1. **Ingest** producer reads, preserving the availability tri-state.  A read is
   never unwrapped into a bare list — ``unavailable`` has to survive the door,
   because downstream retention branches on it (contract §5).
2. **Dedup on identity ``(source_id, ticker, source_asof)``** — and on nothing
   else.  One ticker may carry many nominations from many producers and every
   one is kept: collapsing them is the §16 A1 no-flattening violation.  Only a
   re-read of the SAME producer at the SAME artifact vintage is a duplicate,
   and that one is idempotent rather than additive.
3. **Expire** on ``ttl_until``.  Expiry removes a nomination from the ACTIVE
   set; it never deletes the spooled event (no silent signal deletion, §16).
4. **Disclose correlated families** by ``source_id`` prefix, so a downstream
   reader can see that ``stockdata:entry_signal`` and ``stockdata:setups`` are
   one artifact read twice rather than two independent confirmers (Track C §1.3
   shared-upstream clusters).  Nomination guarantees probing; predictive weight
   must be earned independently per family (§6.1) — the bus makes the
   correlation visible so nobody can double-count by accident.

SPOOL BEFORE CONSUME (contract §5, PR-1 acceptance)
---------------------------------------------------
When a spool is attached, a nomination becomes consumable only after its event
is durably spooled.  A failed spool write leaves the nomination in
``refused_unspooled`` with a line-start annotation, not in the active set.  The
ephemeral producers (hot_tape, flow_pulse fastpath) have no artifact vintage to
replay, so an unspooled nomination is a fact that will never be reconstructible
— admitting on it would put an ungradeable episode into the forward ledger.

A bus constructed with ``spool=None`` runs undurable and says so via
``durable``; that mode is for unit tests of the funnel, never for the lane.

NO SCORING HAPPENS HERE.  The bus counts nothing, weights nothing, and ranks
nothing.  Five nominations is not "stronger" than one.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from engine.entry_radar.contracts import (
    Nomination,
    ProducerRead,
    iso,
    utcnow,
)
from engine.entry_radar.spool import NominationSpool

log = logging.getLogger(__name__)


class NominationBus:
    """Ingestion + dedup/provenance for `mastermind.entry_probe_nomination.v1`."""

    def __init__(self, *, spool: NominationSpool | None = None) -> None:
        self._spool = spool
        self._by_identity: dict[tuple[str, str, str], Nomination] = {}
        self._reads: dict[str, ProducerRead] = {}
        self.refused_unspooled: list[Nomination] = []
        self.duplicates_dropped: int = 0
        self.spool_keys: list[str] = []

    # -- properties -------------------------------------------------------
    @property
    def durable(self) -> bool:
        """False when no spool is attached — the funnel-unit-test mode."""
        return self._spool is not None

    @property
    def reads(self) -> dict[str, ProducerRead]:
        """Per-producer availability, keyed by ``source_id``.  Includes outages."""
        return dict(self._reads)

    # -- ingestion --------------------------------------------------------
    def ingest_read(self, read: ProducerRead, *, now: datetime | None = None) -> int:
        """Ingest one producer read.  Returns the count of newly-active nominations."""
        return self.ingest_reads([read], now=now)

    def ingest_reads(self, reads: Sequence[ProducerRead], *,
                     now: datetime | None = None, pass_id: str = "") -> int:
        """Ingest a whole pass: spool first, then admit what the spool accepted."""
        stamp = now or utcnow()
        fresh: list[Nomination] = []
        for read in reads:
            prior = self._reads.get(read.source_id)
            # An unavailable read must never overwrite a usable one from the same
            # pass — the outage is recorded, but the facts we DID get stand.
            if prior is None or prior.status == "unavailable" or read.usable:
                self._reads[read.source_id] = read
            for nom in read.nominations:
                if nom.identity in self._by_identity:
                    self.duplicates_dropped += 1
                    continue
                fresh.append(nom)

        if not fresh:
            # Still spool: a pass whose producers were all unavailable is a fact.
            if self._spool is not None:
                key = self._spool.append((), producers=list(reads), now=stamp, pass_id=pass_id)
                if key:
                    self.spool_keys.append(key)
            return 0

        if self._spool is not None:
            key = self._spool.append(fresh, producers=list(reads), now=stamp, pass_id=pass_id)
            if not key:
                print("::warning title=entry-radar-bus::spool refused "
                      f"{len(fresh)} nomination event(s) — NOT admitted (spool-before-consume; "
                      "an unspooled ephemeral nomination is unreconstructible)", flush=True)
                self.refused_unspooled.extend(fresh)
                return 0
            self.spool_keys.append(key)

        for nom in fresh:
            self._by_identity[nom.identity] = nom
        return len(fresh)

    def ingest(self, nominations: Iterable[Nomination], *, source_id: str,
               status: str = "ok", source_asof: datetime | None = None,
               now: datetime | None = None) -> int:
        """Convenience door for a producer that hands over bare nominations."""
        noms = tuple(nominations)
        read = ProducerRead(source_id=source_id, status=status, nominations=noms,
                            source_asof=source_asof, observed_at=now or utcnow())
        return self.ingest_read(read, now=now)

    # -- reading ----------------------------------------------------------
    def active(self, *, now: datetime | None = None) -> list[Nomination]:
        """Every unexpired nomination, in ingestion-stable order."""
        stamp = now or utcnow()
        return [n for n in self._by_identity.values() if not n.expired(now=stamp)]

    def expired(self, *, now: datetime | None = None) -> list[Nomination]:
        """Every TTL-expired nomination.  Still here — expiry is not deletion."""
        stamp = now or utcnow()
        return [n for n in self._by_identity.values() if n.expired(now=stamp)]

    def by_ticker(self, *, now: datetime | None = None) -> dict[str, list[Nomination]]:
        """``ticker -> [every active nomination]``.  Never a count, never a badge."""
        out: dict[str, list[Nomination]] = defaultdict(list)
        for nom in self.active(now=now):
            out[nom.ticker].append(nom)
        return dict(out)

    def for_ticker(self, ticker: str, *, now: datetime | None = None) -> list[Nomination]:
        key = str(ticker or "").strip().upper()
        return [n for n in self.active(now=now) if n.ticker == key]

    def correlated_groups(self, *, now: datetime | None = None) -> dict[str, list[str]]:
        """``upstream-artifact prefix -> [source_id]`` for the active set.

        A group of size > 1 is a correlated family: those producers share an
        upstream artifact and are not independent confirmation of anything.
        """
        out: dict[str, set[str]] = defaultdict(set)
        for nom in self.active(now=now):
            out[nom.source_prefix].add(nom.source_id)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def availability(self) -> dict[str, Any]:
        """The per-producer availability block for the published artifact."""
        reads = list(self._reads.values())
        return {
            "producers": [r.to_dict() for r in sorted(reads, key=lambda r: r.source_id)],
            "n_ok": sum(1 for r in reads if r.status == "ok"),
            "n_stale": sum(1 for r in reads if r.status == "stale"),
            "n_unavailable": sum(1 for r in reads if r.status == "unavailable"),
            "unavailable_sources": sorted(r.source_id for r in reads
                                          if r.status == "unavailable"),
            "stale_sources": sorted(r.source_id for r in reads if r.status == "stale"),
        }

    def summary(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or utcnow()
        active = self.active(now=stamp)
        return {
            "observed_at": iso(stamp),
            "durable": self.durable,
            "n_active": len(active),
            "n_expired": len(self.expired(now=stamp)),
            "n_tickers": len({n.ticker for n in active}),
            "duplicates_dropped": self.duplicates_dropped,
            "refused_unspooled": len(self.refused_unspooled),
            "spool_keys": list(self.spool_keys),
            "correlated_groups": self.correlated_groups(now=stamp),
            "availability": self.availability(),
        }
