"""engine/entry_radar/producers/baskets.py — the basket drawer producers.

Two adapters, and the boundary BETWEEN them is the point of this module:

  ``read_group_pulse``       ``site/basketdata/pulse.json``             membership_expansion
  ``read_linked_outsiders``  ``site/basketdata/linked_outsiders.json``  special_situation

THE LAUNDERING BOUNDARY (contract §6)
--------------------------------------
"A basket-level fact must never launder into a single-name fact."  These two
artifacts sit on opposite sides of that line, and getting them right is the
whole reason they share a module:

* **``pulse.json`` is BASKET-LEVEL.**  ``<basket>.direction.leader.ticker`` is
  the answer to *which member led this basket* — a statement about the BASKET,
  which happens to name a member.  It is not a statement about that company.
  So it carries ``source_family="membership_expansion"`` and a
  ``membership_expansion.*`` reason code, and ``contracts.Nomination`` enforces
  both halves.  Downstream can therefore never mistake "led its basket" for
  "something happened to this company".

* **``linked_outsiders.json`` is SINGLE-NAME.**  An outsider row is a specific
  8-K in which a specific basket member disclosed a material agreement with a
  specific counterparty (``linked_members[] = {member, relationship, filed_at,
  accession, form, item}``).  The basket is how we FOUND it; the fact itself is
  a filing about that company.  So it carries
  ``source_family="special_situation"`` with a plain (non-prefixed) reason code
  — Track C's "filing-linked, not price-correlated; genuine catalyst-adjacent"
  read.

Discovery route and fact grain are different questions.  Answering the first
when asked the second is exactly the laundering the contract forbids, and
answering the second when the fact IS basket-level is the same error mirrored.

ARTIFACT SHAPES (verified from writer code; the worktree is sparse)
--------------------------------------------------------------------
Both files are ``{basket_id: <record>}`` at the root with **no root-level
asof** — each basket record carries its own ``as_of`` / ``generated_at``
(``engine/group_pulse.py``:992-1005, ``engine/group_linked_outsiders.py``
:867-880).  So the adapters derive artifact vintage as the NEWEST per-basket
``as_of``, and a basket whose own stamp is missing degrades quality rather than
inheriting a sibling's freshness.

  pulse:            ``<b>.direction.{leader{ticker,kind}, strongest{ticker,ret},
                    weakest{ticker,ret}}``
  linked_outsiders: ``<b>.outsiders[] = {ticker, name, linked_members[], edge_n,
                    last_filed_at, state, move_spy_adj, active}``
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import Nomination, NominationError, ProducerRead, parse_ts, utcnow
from engine.entry_radar.producers.base import (
    clamp_asof,
    grade_staleness,
    read_json,
    stale_after,
    unavailable,
)

log = logging.getLogger(__name__)

PULSE_SOURCE_ID = "basketdata:pulse"
LINKED_OUTSIDERS_SOURCE_ID = "basketdata:linked_outsiders"

#: ``direction`` sub-key → (reason suffix, phrasing).  Each is a DISTINCT
#: basket-level fact; they are never merged into one "basket signal".
_PULSE_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("leader", "basket_leader", "led {basket} on activity"),
    ("strongest", "basket_strongest", "was the strongest member of {basket}"),
    ("weakest", "basket_weakest", "was the weakest member of {basket}"),
)


def _basket_records(payload: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    return {str(k): v for k, v in payload.items() if isinstance(v, Mapping)}


def _newest_asof(records: Mapping[str, Mapping[str, Any]]) -> tuple[datetime | None, str]:
    """Newest per-basket ``as_of``; ``degraded`` when any basket lacks one."""
    newest: datetime | None = None
    quality = "ok"
    for rec in records.values():
        got = parse_ts(rec.get("as_of") or rec.get("generated_at"))
        if got is None:
            quality = "degraded"
            continue
        newest = got if newest is None else max(newest, got)
    if newest is None:
        quality = "unknown"
    return newest, quality


def read_group_pulse(path: Path, *, now: datetime | None = None,
                     cfg: Mapping[str, Any] | None = None) -> ProducerRead:
    """``site/basketdata/pulse.json`` → BASKET-LEVEL membership_expansion nominations.

    Every nomination here says "this basket did something and this member is how
    it showed up" — never "this company did something".  The family and the
    reason-code prefix both say so, and ``contracts`` refuses the pairing if
    either is dropped.
    """
    stamp = now or utcnow()
    payload, reason = read_json(path)
    if payload is None:
        return unavailable(PULSE_SOURCE_ID, reason, now=stamp)

    records = _basket_records(payload)
    if not records:
        return unavailable(PULSE_SOURCE_ID,
                           f"{path} carried no basket records — treated as an outage",
                           now=stamp)

    asof, quality = _newest_asof(records)
    status, age = grade_staleness(asof, now=stamp,
                                  stale_after_minutes=stale_after(cfg, PULSE_SOURCE_ID))
    ttl = stamp + timedelta(minutes=max(1.0, stale_after(cfg, PULSE_SOURCE_ID)))
    noms: list[Nomination] = []

    for basket_id, rec in records.items():
        direction = rec.get("direction")
        if not isinstance(direction, Mapping):
            continue
        basket_asof = parse_ts(rec.get("as_of") or rec.get("generated_at")) or asof or stamp
        row_quality = "ok" if parse_ts(rec.get("as_of")) else "degraded"
        for slot, suffix, phrasing in _PULSE_SLOTS:
            block = direction.get(slot)
            if not isinstance(block, Mapping):
                continue
            sym = str(block.get("ticker") or "").strip().upper()
            if not sym:
                continue
            value = block.get("ret")
            try:
                value = float(value) if value is not None else None
            except (TypeError, ValueError):
                value = None
            safe_asof, clamped = clamp_asof(basket_asof, stamp)
            row_q = row_quality if quality != "unknown" else "degraded"
            try:
                noms.append(Nomination(
                    ticker=sym, source_id=PULSE_SOURCE_ID,
                    source_family="membership_expansion",
                    reason_code=f"membership_expansion.{suffix}",
                    reason_text=f"{sym} " + phrasing.format(basket=basket_id) +
                                " — a fact about the basket, not about the company",
                    observed_at=stamp, source_asof=safe_asof or stamp,
                    source_value=value, source_horizon="nightly", ttl_until=ttl,
                    evidence_ref=f"pulse.json#{basket_id}/direction/{slot}",
                    data_quality="degraded" if clamped else row_q,
                ))
            except NominationError as exc:
                log.warning("entry_radar.producers.baskets: pulse row dropped (%s)", exc)

    return ProducerRead(source_id=PULSE_SOURCE_ID, status=status, nominations=tuple(noms),
                        source_asof=asof, observed_at=stamp, age_seconds=age,
                        stale_after_seconds=stale_after(cfg, PULSE_SOURCE_ID) * 60.0,
                        detail=f"{len(noms)} basket-level nomination(s) across "
                               f"{len(records)} basket(s); vintage={quality}")


def read_linked_outsiders(path: Path, *, now: datetime | None = None,
                          cfg: Mapping[str, Any] | None = None) -> ProducerRead:
    """``site/basketdata/linked_outsiders.json`` → SINGLE-NAME special_situation.

    An outsider is a company outside the basket that a MEMBER named in a
    material 8-K.  The filing is about that company, so the nomination is
    single-name — with the discovering basket and the filing accession kept in
    ``evidence_ref`` so the discovery route stays inspectable.
    """
    stamp = now or utcnow()
    payload, reason = read_json(path)
    if payload is None:
        return unavailable(LINKED_OUTSIDERS_SOURCE_ID, reason, now=stamp)

    records = _basket_records(payload)
    if not records:
        return unavailable(LINKED_OUTSIDERS_SOURCE_ID,
                           f"{path} carried no basket records — treated as an outage",
                           now=stamp)

    asof, quality = _newest_asof(records)
    stale_min = stale_after(cfg, LINKED_OUTSIDERS_SOURCE_ID)
    status, age = grade_staleness(asof, now=stamp, stale_after_minutes=stale_min)
    ttl = stamp + timedelta(minutes=max(1.0, stale_min))
    noms: list[Nomination] = []

    for basket_id, rec in records.items():
        basket_asof = parse_ts(rec.get("as_of") or rec.get("generated_at")) or asof or stamp
        for row in rec.get("outsiders") or ():
            if not isinstance(row, Mapping):
                continue
            sym = str(row.get("ticker") or "").strip().upper()
            if not sym:
                continue
            links = [ln for ln in (row.get("linked_members") or ()) if isinstance(ln, Mapping)]
            members = ", ".join(sorted({str(ln.get("member") or "") for ln in links} - {""}))
            accession = next((str(ln.get("accession") or "") for ln in links
                              if ln.get("accession")), "")
            relationship = next((str(ln.get("relationship") or "") for ln in links
                                 if ln.get("relationship")), "")
            edge_n = row.get("edge_n")
            try:
                edge_n = int(edge_n) if edge_n is not None else None
            except (TypeError, ValueError):
                edge_n = None
            text = (f"{sym} was named as a counterparty in a material 8-K filed by "
                    f"{members or 'a ' + basket_id + ' member'}")
            if relationship:
                text += f" ({relationship})"
            # source_asof is the ARTIFACT VINTAGE, never the filing timestamp.
            # A filing date is when the event happened; the vintage is when this
            # producer last looked.  Using the filing date made the §5 postdate
            # check trivially satisfiable (a months-old 8-K always precedes now)
            # and hid a stale artifact behind a fresh-looking event.  The filing
            # date rides in evidence_ref/source_horizon where it belongs.
            filed = parse_ts(row.get("last_filed_at"))
            safe_asof, clamped = clamp_asof(basket_asof, stamp)
            try:
                noms.append(Nomination(
                    ticker=sym, source_id=LINKED_OUTSIDERS_SOURCE_ID,
                    source_family="special_situation",
                    reason_code="filing.linked_counterparty",
                    reason_text=text,
                    observed_at=stamp,
                    source_asof=safe_asof or stamp,
                    source_value=float(edge_n) if edge_n is not None else None,
                    source_horizon=("event" if filed is None
                                    else f"event@{filed.date().isoformat()}"),
                    ttl_until=ttl,
                    evidence_ref=(f"linked_outsiders.json#{basket_id}/{sym}"
                                  + (f"?accession={accession}" if accession else "")
                                  + (f"&filed={filed.date().isoformat()}" if filed else "")),
                    data_quality="degraded" if (clamped or filed is None) else "ok",
                ))
            except NominationError as exc:
                log.warning("entry_radar.producers.baskets: outsider row dropped (%s)", exc)

    return ProducerRead(source_id=LINKED_OUTSIDERS_SOURCE_ID, status=status,
                        nominations=tuple(noms), source_asof=asof, observed_at=stamp,
                        age_seconds=age, stale_after_seconds=stale_min * 60.0,
                        detail=f"{len(noms)} filing-linked counterparty nomination(s) "
                               f"across {len(records)} basket(s); vintage={quality}")
