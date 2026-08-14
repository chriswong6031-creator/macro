"""engine/entry_radar/contracts.py — frozen record shapes for the Radar funnel.

Three objects live here and nothing else:

  ``Nomination``     `mastermind.entry_probe_nomination.v1` — the enlistment record
                     a producer emits.  Field list FROZEN at contract §6.1.
  ``ProbeRecord``    one name in the Probe Set.  Field list frozen below.
  ``ProducerRead``   the availability tri-state wrapper every adapter returns.

Everything is validated at construction: a malformed nomination raises
``NominationError`` at the bus door rather than becoming a silently-wrong row in
a durable spool.

THE FROZEN NOMINATION FIELD LIST (contract §6.1) is exactly thirteen names.  It
is not extensible in PR-1 — a producer needing to say something the list cannot
express says it in ``reason_code``/``evidence_ref``, or the contract is amended
under §18.  ``NOMINATION_FIELDS`` is asserted against the dataclass in
``tests/test_entry_radar_w1.py`` so the freeze is mechanical, not editorial.

NO SCORES.  ``ProbeRecord`` has no score, rank, points, `candidate` boolean, or
bullish field, because admission is a coverage decision and not an opinion
(package docstring).  ``PROBE_RECORD_FIELDS`` plus ``BANNED_RECORD_TOKENS``
make that testable.  Note the asymmetry: a *nomination* may carry
``source_rank`` / ``source_value`` — those are the PRODUCER's own numbers,
preserved verbatim as provenance.  Preserving a producer's rank is honesty;
promoting it onto the probe record would be Radar adopting an opinion it did
not earn.

MEMBERSHIP-EXPANSION LAUNDERING GUARD (contract §6).  A basket-level fact must
never launder into a single-name fact.  The lock is bidirectional and lives in
``Nomination._validate``: a ``reason_code`` under the
``membership_expansion.`` prefix REQUIRES ``source_family ==
"membership_expansion"``, and that family REQUIRES that prefix.  Neither half
alone is enough — the family without the prefix lets a basket fact wear a
single-name reason, and the prefix without the family lets it wear a
single-name family.

POINT-IN-TIME (contract §5).  ``observed_at >= source_asof`` is enforced at
construction: a nomination may never be consumed before the producer artifact
that justifies it existed.  That is the "nomination postdate test" row of the
§5 leakage matrix, made structural.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

NOMINATION_SCHEMA = "mastermind.entry_probe_nomination.v1"
PROBE_SET_SCHEMA = "mastermind.entry_probe_set.v1"

#: Display/research tier.  Stamped on every published Radar artifact (contract §2).
AUTHORITY_BLOCK: dict[str, bool] = {
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_escalate": False,
}

#: FROZEN — contract §6.1.  Order is the contract's order.
NOMINATION_FIELDS: tuple[str, ...] = (
    "ticker",
    "source_id",
    "source_family",
    "reason_code",
    "reason_text",
    "observed_at",
    "source_asof",
    "source_rank",
    "source_value",
    "source_horizon",
    "ttl_until",
    "evidence_ref",
    "data_quality",
)

#: FROZEN — contract §6.  ``membership_expansion`` is its own family precisely
#: so a basket-level fact cannot borrow a single-name one.
SOURCE_FAMILIES: frozenset[str] = frozenset({
    "market_price",
    "theme_sector",
    "fund_etf_flow",
    "smart_money",
    "options",
    "off_exchange",
    "news_catalyst",
    "fundamental",
    "special_situation",
    "operator",
    "membership_expansion",
})

MEMBERSHIP_EXPANSION_FAMILY = "membership_expansion"
MEMBERSHIP_EXPANSION_PREFIX = "membership_expansion."

#: Availability of a producer READ (contract §5 — "missing is not negative").
SOURCE_STATUSES: frozenset[str] = frozenset({"ok", "stale", "unavailable"})

#: Availability of an INPUT READING (contract §5 vocabulary).  Carried here so
#: PR-2/PR-3 detector states use one enumeration rather than minting a second.
AVAILABILITY_STATES: frozenset[str] = frozenset({
    "confirmed", "provisional", "stale", "unavailable",
})

#: Layer-A classification (contract §6).  ``unclassified`` is the FAIL-CLOSED
#: landing: a name we cannot classify is separately classified and kept
#: visible, never silently dropped and never silently admitted as an operating
#: company.
ELIGIBILITY_STATES: frozenset[str] = frozenset({
    "operating_equity", "adr", "wrapper_excluded", "unclassified",
})

DATA_QUALITY_STATES: frozenset[str] = frozenset({"ok", "degraded", "unknown"})

ADMISSION_LAYERS: tuple[str, ...] = ("A", "B", "C", "D")

#: FROZEN.  The Probe Set record's complete field set — see the no-scores law.
PROBE_RECORD_FIELDS: tuple[str, ...] = (
    "ticker",
    "admission_layers",
    "admission_reasons",
    "eligibility",
    "history_age_sessions",
    "first_admitted_at",
    "last_refreshed_at",
    "freshness",
    "data_quality",
    "nominations",
)

#: Substrings that may never appear in a Probe Set record key.  The guard exists
#: because the failure mode is gradual: one "hotness_points" field added for a
#: debug view, and admission has quietly become an opinion.
BANNED_RECORD_TOKENS: tuple[str, ...] = (
    "score", "rank", "points", "bullish", "bull_", "candidate",
    "conviction", "weight", "grade", "signal_strength",
)

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


class NominationError(ValueError):
    """A nomination that violates the frozen contract.  Raised at construction."""


def utcnow() -> datetime:
    """Tz-aware UTC now — the single clock this package reads."""
    return datetime.now(timezone.utc)


def iso(ts: datetime | None) -> str | None:
    """Serialise a tz-aware datetime as ``...Z`` (the house live-plane form)."""
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_ts(raw: Any) -> datetime | None:
    """Parse an ISO timestamp (``Z`` or offset) to tz-aware UTC.  None on failure."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        txt = str(raw).strip()
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        got = datetime.fromisoformat(txt)
        return got if got.tzinfo else got.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _require_aware(name: str, ts: Any) -> datetime:
    got = parse_ts(ts)
    if got is None:
        raise NominationError(f"{name} is required and must be an ISO timestamp (got {ts!r})")
    return got.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Nomination:
    """`mastermind.entry_probe_nomination.v1` — FROZEN field list (contract §6.1).

    ``observed_at`` is the bus INGESTION clock; ``source_asof`` is the producer
    artifact's OWN asof.  They are different questions and both are required —
    the pair is what makes a nomination replayable and what makes the §5
    postdate test possible.
    """

    ticker: str
    source_id: str
    source_family: str
    reason_code: str
    reason_text: str
    observed_at: datetime
    source_asof: datetime
    source_rank: int | None = None
    source_value: float | None = None
    source_horizon: str | None = None
    ttl_until: datetime | None = None
    evidence_ref: str | None = None
    data_quality: str = "ok"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", str(self.ticker or "").strip().upper())
        object.__setattr__(self, "observed_at", _require_aware("observed_at", self.observed_at))
        object.__setattr__(self, "source_asof", _require_aware("source_asof", self.source_asof))
        if self.ttl_until is not None:
            object.__setattr__(self, "ttl_until", _require_aware("ttl_until", self.ttl_until))
        self._validate()

    def _validate(self) -> None:
        if not _TICKER_RE.match(self.ticker):
            raise NominationError(f"ticker {self.ticker!r} is not a plausible US symbol")
        if not str(self.source_id or "").strip():
            raise NominationError("source_id is required — a nomination with no producer "
                                  "has no provenance and cannot be graded later")
        if self.source_family not in SOURCE_FAMILIES:
            raise NominationError(f"source_family {self.source_family!r} is not one of "
                                  f"{sorted(SOURCE_FAMILIES)}")
        if not str(self.reason_code or "").strip():
            raise NominationError("reason_code is required")
        if not str(self.reason_text or "").strip():
            raise NominationError("reason_text is required — the operator-readable why")
        if self.data_quality not in DATA_QUALITY_STATES:
            raise NominationError(f"data_quality {self.data_quality!r} not in "
                                  f"{sorted(DATA_QUALITY_STATES)}")

        # --- membership-expansion laundering guard (bidirectional, contract §6) ---
        is_basket_family = self.source_family == MEMBERSHIP_EXPANSION_FAMILY
        has_basket_prefix = self.reason_code.startswith(MEMBERSHIP_EXPANSION_PREFIX)
        if is_basket_family and not has_basket_prefix:
            raise NominationError(
                f"{self.source_family} nomination for {self.ticker} carries reason_code "
                f"{self.reason_code!r}; a basket-level fact must declare itself with the "
                f"{MEMBERSHIP_EXPANSION_PREFIX!r} reason prefix")
        if has_basket_prefix and not is_basket_family:
            raise NominationError(
                f"reason_code {self.reason_code!r} is basket-level but source_family is "
                f"{self.source_family!r}; a basket-level fact must never launder into a "
                f"single-name family")

        # --- point-in-time (contract §5 nomination postdate test) ---
        if self.observed_at < self.source_asof:
            raise NominationError(
                f"nomination for {self.ticker} observed_at {iso(self.observed_at)} predates "
                f"source_asof {iso(self.source_asof)} — a nomination may not be consumed "
                f"before the artifact that justifies it existed")

    # -- identity ---------------------------------------------------------
    @property
    def identity(self) -> tuple[str, str, str]:
        """Dedup identity: ``(source_id, ticker, source_asof)``.

        Deliberately NOT ``(ticker,)``.  One ticker may carry many nominations
        and every one is kept; only a re-read of the SAME producer at the SAME
        artifact vintage is a duplicate.
        """
        return (self.source_id, self.ticker, iso(self.source_asof) or "")

    @property
    def source_prefix(self) -> str:
        """The upstream-artifact group, for correlated-family disclosure.

        Convention: ``source_id`` is ``<upstream_artifact>:<producer>`` — so
        ``stockdata:entry_signal`` and ``stockdata:setups`` disclose that they
        are one artifact read twice, not two independent confirmers (Track C
        §1.3 shared-upstream clusters).
        """
        return self.source_id.split(":", 1)[0]

    def expired(self, *, now: datetime | None = None) -> bool:
        """True once ``ttl_until`` has passed.  A nomination with no TTL never expires."""
        if self.ttl_until is None:
            return False
        return (now or utcnow()) >= self.ttl_until

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form.  Key order and key set are exactly ``NOMINATION_FIELDS``."""
        out: dict[str, Any] = {}
        for name in NOMINATION_FIELDS:
            val = getattr(self, name)
            out[name] = iso(val) if isinstance(val, datetime) else val
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Nomination:
        unknown = set(raw) - set(NOMINATION_FIELDS)
        if unknown:
            raise NominationError(f"unknown nomination field(s) {sorted(unknown)} — the v1 "
                                  f"field list is frozen at {list(NOMINATION_FIELDS)}")
        return cls(**{k: raw[k] for k in NOMINATION_FIELDS if k in raw})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ProducerRead:
    """One adapter's read of one artifact — the availability tri-state.

    ``status="unavailable"`` with an empty ``nominations`` list is NOT the same
    fact as ``status="ok"`` with an empty list.  The first says *we could not
    look*; the second says *we looked and there was nothing*.  Collapsing them
    is the §5 "missing is not negative" violation, and downstream
    (``universe.assemble_probe_set``) branches on exactly this distinction.
    """

    source_id: str
    status: str
    nominations: tuple[Nomination, ...] = ()
    source_asof: datetime | None = None
    observed_at: datetime | None = None
    age_seconds: float | None = None
    stale_after_seconds: float | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status not in SOURCE_STATUSES:
            raise NominationError(f"source status {self.status!r} not in {sorted(SOURCE_STATUSES)}")
        if self.status == "unavailable" and self.nominations:
            raise NominationError(f"{self.source_id}: an unavailable read cannot carry "
                                  f"nominations — it did not happen")

    @property
    def usable(self) -> bool:
        """``ok`` or ``stale``.  A stale read still carries real, aged facts."""
        return self.status in ("ok", "stale")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "source_asof": iso(self.source_asof),
            "observed_at": iso(self.observed_at),
            "age_seconds": self.age_seconds,
            "stale_after_seconds": self.stale_after_seconds,
            "n_nominations": len(self.nominations),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AdmissionReason:
    """Why one name is in the Probe Set, per admitting producer.

    Carries the producer's identity and the read's availability so a name
    retained across an outage is visibly retained-because-stale rather than
    silently present (contract §5).
    """

    layer: str
    source_id: str
    reason_code: str
    reason_text: str
    source_status: str = "ok"
    source_asof: datetime | None = None
    observed_at: datetime | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    retained_stale: bool = False

    def __post_init__(self) -> None:
        if self.layer not in ADMISSION_LAYERS:
            raise NominationError(f"admission layer {self.layer!r} not in {ADMISSION_LAYERS}")
        if self.source_status not in SOURCE_STATUSES:
            raise NominationError(f"source status {self.source_status!r} not in "
                                  f"{sorted(SOURCE_STATUSES)}")

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["source_asof"] = iso(self.source_asof)
        out["observed_at"] = iso(self.observed_at)
        return out


@dataclass(frozen=True, slots=True)
class ProbeRecord:
    """One name in the Probe Set.

    ``nominations`` holds the FULL v1 records, never a count and never a
    collapsed badge list — the §16 A1 no-flattening law.  Two nominations for
    one ticker from two families stay two records with two provenances.
    """

    ticker: str
    admission_layers: tuple[str, ...]
    admission_reasons: tuple[AdmissionReason, ...]
    eligibility: str
    history_age_sessions: int | None = None
    first_admitted_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    freshness: dict[str, Any] = field(default_factory=dict)
    data_quality: str = "ok"
    nominations: tuple[Nomination, ...] = ()

    def __post_init__(self) -> None:
        if self.eligibility not in ELIGIBILITY_STATES:
            raise NominationError(f"eligibility {self.eligibility!r} not in "
                                  f"{sorted(ELIGIBILITY_STATES)}")
        bad = [layer for layer in self.admission_layers if layer not in ADMISSION_LAYERS]
        if bad:
            raise NominationError(f"admission layers {bad} not in {ADMISSION_LAYERS}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form.  Key set is exactly ``PROBE_RECORD_FIELDS`` — no scores."""
        return {
            "ticker": self.ticker,
            "admission_layers": list(self.admission_layers),
            "admission_reasons": [r.to_dict() for r in self.admission_reasons],
            "eligibility": self.eligibility,
            "history_age_sessions": self.history_age_sessions,
            "first_admitted_at": iso(self.first_admitted_at),
            "last_refreshed_at": iso(self.last_refreshed_at),
            "freshness": dict(self.freshness),
            "data_quality": self.data_quality,
            "nominations": [n.to_dict() for n in self.nominations],
        }


def assert_no_score_fields(record: dict[str, Any]) -> None:
    """Raise if a serialised probe record grew a score-shaped key.

    Scoped to the record's OWN keys: the ``nominations`` subtree legitimately
    carries ``source_rank``/``source_value`` (the producer's numbers, preserved
    as provenance — see the module docstring's asymmetry note).
    """
    for key in record:
        low = key.lower()
        for token in BANNED_RECORD_TOKENS:
            if token in low:
                raise NominationError(
                    f"probe record field {key!r} looks like a score/rank field; admission "
                    f"is a coverage decision, not an opinion (contract §9)")
    extra = set(record) - set(PROBE_RECORD_FIELDS)
    if extra:
        raise NominationError(f"probe record carries unfrozen field(s) {sorted(extra)}")


def nomination_dataclass_fields() -> tuple[str, ...]:
    """The dataclass's own field order — asserted equal to ``NOMINATION_FIELDS``."""
    return tuple(f.name for f in fields(Nomination))
