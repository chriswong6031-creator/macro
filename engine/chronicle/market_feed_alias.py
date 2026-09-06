"""engine.chronicle.market_feed_alias — MO-DELTA-001 alias resolver.

Ledger row MO-DELTA-001 (research/market_intelligence_productization/
MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:49) asks whether
MO-PAID-017's substrate (real_producer: engine/chronicle/spine.py, the same
substrate this row shares) confirms or refutes serving an UNCONFIRMED
"Market-Feed"-branded surface. The Market-Feed definition this module tests
against, quoted from the F00B crosswalk (research/market_intelligence_
productization/MARKET_ONTOLOGY_F00B_CURRENT_CAPABILITY_CROSSWALK_2026-08-28.csv
:84): "Market Feed (stock-impacting events with ticker impact/direction)".

Three independent probes measured at the commit that introduced this module:

1. Naming. No "Market Feed" / "Market-Feed" string exists in templates/,
   scripts/, engine/, docs/. The single case-insensitive hit is unrelated:
   engine/ipo_hk.py:115 ("...grey market) but those keyless primary-market
   feeds...").
2. Contract. engine/chronicle/schema.py:21-24 fixes the public-safe allowlist
   EVENT_FIELDS = (id, ts, date, source, source_ref, kind, title, facts,
   tickers, themes, horizon_hint, weight_hint, links). There is no impact/
   direction/confidence field, and schema.py:1-8 states the allowlist IS the
   gate ("no field outside this list may ever appear on an emitted event").
   Measured on the committed store data/chronicle/events.jsonl (macro-main
   snapshot, mtime 2026-08-22 22:32): 7,643 events, key census returns
   exactly the 13 schema keys on all 7,643 rows, 5,958 (78.0%) carry a
   non-empty tickers, 0 carry any direction-bearing field; date span
   2013-05-21 -> 2026-08-22; kinds earnings 5,922 / report 1,651 /
   signal_close 36 / state_flip 18 / print 16.
3. Surface. `grep -rln chronicle templates/` returns nothing. The spine's
   only consumers are non-rendered: engine/neuralweb/mastermind_context.py
   :1707 _summarize_chronicle (-> site/neuralwebdata/mastermind_context.json,
   a Brain context blob, not a page), engine/neuralweb/brain_gateway.py:1468
   (imports earnings_calls.latest_for_ticker only), and the press/marketing
   lanes. engine/chronicle/__init__.py:26-27 names context_pack.pack() "the
   one symbol every consumer binds"; its return (context_pack.py:125-146) is
   {lines[{text,source_ref,site_url,source_url,receipt}], narratives,
   coverage, budget_used} -- a text-line context contract, not a per-ticker
   impact feed.

As of the commit that introduced this module the answer is NOT_SERVED; this
module recomputes that answer from the live store rather than asserting it.

No LLM, no scoring, no ranking here -- deterministic set/count arithmetic
only (house epistemics law, mirrored from engine/chronicle/__init__.py:6-8).
Every public function takes ``root`` per the package's test-injection
convention (context_pack.py:125-134) and never raises (the pack() M11
fail-soft convention, context_pack.py:143-146): every failure degrades into
the typed receipt instead of propagating.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = "chronicle.market_feed_alias.v1"
LEDGER_ROW = "MO-DELTA-001"
PARENT_ROW = "MO-PAID-017"
ALIAS_STATES: tuple[str, ...] = ("SERVED", "PARTIALLY_SERVED", "NOT_SERVED", "UNKNOWN")

MARKET_FEED_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_id", "event_time", "tickers", "impact_direction", "impact_magnitude",
)

# logical Market-Feed field -> chronicle.event.v1 field that already serves it
# (None = absent from the schema today; granted only when the live store
# census measures a matching candidate key — see DIRECTION_/MAGNITUDE_
# FIELD_CANDIDATES below).
MARKET_FEED_FIELD_SOURCES: dict[str, str | None] = {
    "event_id": "id",
    "event_time": "date",
    "tickers": "tickers",
    "impact_direction": None,
    "impact_magnitude": None,
}

# Fields a future reader might mistake for direction/magnitude, and why they
# are refused. Load-bearing: this is what stops a later session from silently
# promoting weight_hint into a magnitude (LLM-origination / epistemics law).
REJECTED_PROXIES: tuple[dict[str, str], ...] = (
    {
        "field": "weight_hint",
        "reason": "context-pack salience weight, not a per-ticker impact magnitude; promoting it would originate a score",
    },
    {
        "field": "horizon_hint",
        "reason": "deterministic kind->horizon mapping (schema.py HORIZON_BY_KIND), carries no direction",
    },
    {
        "field": "themes",
        "reason": "free-text tags, not a signed impact",
    },
)

EVENTS_REL = Path("data") / "chronicle" / "events.jsonl"  # mirrors spine.EVENTS_REL (spine.py:49)

# Explicit direction keys only. Generic "impact" / "sign" were dropped: a free-
# text value like "grey market feeds" must never count as a signed direction.
DIRECTION_FIELD_CANDIDATES: tuple[str, ...] = (
    "impact_direction", "direction", "polarity",
)

# Explicit magnitude keys only — weight_hint / horizon_hint / themes stay in
# REJECTED_PROXIES and are never counted as magnitude support.
MAGNITUDE_FIELD_CANDIDATES: tuple[str, ...] = (
    "impact_magnitude", "magnitude", "impact_size", "abs_impact",
)

# Closed domain for direction values (case-insensitive strings + numeric sign).
_DIRECTION_ENUM: frozenset[str] = frozenset({
    "up", "down", "positive", "negative", "+1", "-1", "1",
})

# SERVED requires real coverage, not a single stray row in a multi-thousand
# event store. Absolute floor + share of ticker-bearing events.
SERVED_MIN_CO_OCCURRENCE = 2
SERVED_MIN_SHARE_OF_TICKER_EVENTS = 0.10

# Cause-keyed disclosures (Front-End Clarity Law). PARTIALLY_SERVED has three
# distinct causes; state-alone copy falsely claimed a live published feed.
_DISCLOSURE_EN: dict[tuple[str, str | None], str] = {
    ("NOT_SERVED", None): (
        "We don't publish a market feed yet. We track the events and which "
        "tickers they touch — we do not yet publish which way each "
        "event pushed a stock, so that column is blank on purpose."
    ),
    ("UNKNOWN", None): (
        "We can't read the event record right now, so we're not saying "
        "either way — this note updates when the record is back."
    ),
    ("PARTIALLY_SERVED", "no_declared_projection"): (
        "We don't publish a market feed yet. We've started recording which "
        "way some events pushed a stock, but nothing is published until "
        "that page is live."
    ),
    ("PARTIALLY_SERVED", "claim_unsupported_by_store"): (
        "We don't publish a market feed yet — we don't yet measure which "
        "way each event pushed a stock."
    ),
    ("PARTIALLY_SERVED", "projection_incomplete"): (
        "We don't publish a full market feed yet. Some fields are ready; "
        "direction or size for each event is still incomplete."
    ),
    ("PARTIALLY_SERVED", "below_coverage_threshold"): (
        "We don't publish a market feed yet. Direction and size data covers "
        "only a thin slice of events, so the feed stays unpublished until "
        "coverage is solid."
    ),
    ("SERVED", None): (
        "The market feed is live: each event, the tickers it touches, "
        "which way it pushed them, and how large that move was."
    ),
}

_DISCLOSURE_ZH: dict[tuple[str, str | None], str] = {
    ("NOT_SERVED", None): (
        "我们暂未发布市场事件流。事件与所涉个股已在追踪，但每个事件对个股的"
        "方向影响尚未发布，因此该栏目前留空。"
    ),
    ("UNKNOWN", None): "目前无法读取事件记录，因此暂不作判断；记录恢复后此处会更新。",
    ("PARTIALLY_SERVED", "no_declared_projection"): (
        "我们暂未发布市场事件流。部分事件的方向影响已开始记录，但相关页面上线前不会发布。"
    ),
    ("PARTIALLY_SERVED", "claim_unsupported_by_store"): (
        "我们暂未发布市场事件流——每个事件对个股的方向影响尚未测量。"
    ),
    ("PARTIALLY_SERVED", "projection_incomplete"): (
        "我们暂未完整发布市场事件流。部分字段已就绪，但每个事件的方向或幅度仍不完整。"
    ),
    ("PARTIALLY_SERVED", "below_coverage_threshold"): (
        "我们暂未发布市场事件流。方向与幅度数据仅覆盖少量事件，覆盖达标前不会发布。"
    ),
    ("SERVED", None): "市场事件流已上线：事件、所涉个股、影响方向与影响幅度。",
}


def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _support_for_receipt(support: Mapping[str, object] | None) -> dict:
    """Deterministic copy of the caller's support claim for audit/debug."""
    if not support:
        return {}
    out: dict = {}
    for key in sorted(support):
        value = support[key]
        if isinstance(value, Mapping):
            out[key] = {sk: value[sk] for sk in sorted(value)}
        else:
            out[key] = value
    return out


def _empty_projection(*, declared: bool = False) -> dict:
    return {
        "declared": declared,
        "name": None,
        "route": None,
        "declared_fields": [],
        "unknown_fields": [],
        "support": {},
    }


def _projection_out(projection: Mapping[str, object] | None) -> dict:
    proj_out = _empty_projection(declared=projection is not None)
    if projection is None:
        return proj_out
    proj_out["name"] = projection.get("name")
    proj_out["route"] = projection.get("route")
    declared_fields = list(projection.get("fields") or [])
    proj_out["declared_fields"] = sorted(declared_fields)
    proj_out["unknown_fields"] = sorted(
        f for f in declared_fields if f not in MARKET_FEED_REQUIRED_FIELDS
    )
    # ``support`` is kept in the receipt for audit/debugging but plays no
    # part in the grant decision (caller sample_n is never trusted).
    proj_out["support"] = _support_for_receipt(
        projection.get("support") if isinstance(projection.get("support"), Mapping) else {}
    )
    return proj_out


def _is_valid_direction(value: object) -> bool:
    """Closed domain: enum strings or a nonzero numeric sign. Never free text."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _DIRECTION_ENUM
    return False


def _is_valid_magnitude(value: object) -> bool:
    """Magnitude must be a real number (bool is excluded — bool subclasses int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _event_has_valid_direction(event: Mapping[str, object]) -> bool:
    return any(
        _is_valid_direction(event.get(k)) for k in DIRECTION_FIELD_CANDIDATES
    )


def _event_has_valid_magnitude(event: Mapping[str, object]) -> bool:
    return any(
        _is_valid_magnitude(event.get(k)) for k in MAGNITUDE_FIELD_CANDIDATES
    )


def _positive_count(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _meets_served_coverage(coverage: Mapping[str, object]) -> bool:
    """SERVED requires co-occurrence on >= N events AND >= share of ticker events."""
    co = coverage.get("events_with_direction_and_magnitude")
    tickers = coverage.get("events_with_tickers")
    if not _positive_count(co) or co < SERVED_MIN_CO_OCCURRENCE:
        return False
    if not isinstance(tickers, (int, float)) or isinstance(tickers, bool) or tickers <= 0:
        return False
    return (float(co) / float(tickers)) >= SERVED_MIN_SHARE_OF_TICKER_EVENTS


def _disclosure_cause(state: str, flags: set[str] | frozenset[str]) -> str | None:
    """Map receipt flags to the disclosure cause key for PARTIALLY_SERVED."""
    if state != "PARTIALLY_SERVED":
        return None
    for key in (
        "below_coverage_threshold",
        "claim_unsupported_by_store",
        "no_declared_projection",
        "projection_incomplete",
    ):
        if key in flags:
            return key
    return "projection_incomplete"


def _lookup_disclosure(state: str, cause: str | None, lang: str) -> str:
    table = _DISCLOSURE_ZH if lang == "zh" else _DISCLOSURE_EN
    if (state, cause) in table:
        return table[(state, cause)]
    if (state, None) in table:
        return table[(state, None)]
    return table[("UNKNOWN", None)]


def market_feed_field_coverage(root: Path | str | None = None) -> dict:
    """Deterministic census of the committed events.jsonl store.

    Unreadable/absent store => every count is None, never 0. Not-knowing must
    not be shaped like emptiness; a sparse worktree omits data/, so a 0 here
    would read as a proven "no events" and would let a future SERVED/
    NOT_SERVED call be made on nothing.

    Direction/magnitude counts require a closed value domain — key presence or
    free-text values do not count. events_with_direction_and_magnitude is
    restricted to ticker-bearing events so it is a true subset of
    events_with_tickers: the SERVED coverage ratio divides one by the
    other, and a numerator drawn from the whole store (including tickerless
    events) let the ratio exceed 1.0 and let SERVED fire with zero actual
    stock impact (MAJOR-1, PR #6897 review).
    """
    out = {
        "store_path": str(EVENTS_REL),
        "readable": False,
        "reason": None,
        "events_total": None,
        "events_with_tickers": None,
        "events_with_direction_field": None,
        "events_with_magnitude_field": None,
        "events_with_direction_and_magnitude": None,
        "coverage_start": None,
        "coverage_end": None,
        "store_receipt": None,
    }
    try:
        repo = _repo_root(root)
        path = repo / EVENTS_REL
        if not path.exists():
            out["reason"] = "store_absent"
            return out
        raw = path.read_bytes()
        out["store_receipt"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        events: list[dict] = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        total = len(events)
        with_tickers = sum(1 for e in events if e.get("tickers"))
        with_direction = sum(1 for e in events if _event_has_valid_direction(e))
        with_magnitude = sum(1 for e in events if _event_has_valid_magnitude(e))
        with_direction_and_magnitude = sum(
            1
            for e in events
            if e.get("tickers")
            and _event_has_valid_direction(e)
            and _event_has_valid_magnitude(e)
        )
        dates = sorted(
            d for e in events if (d := e.get("date"))
        )
        out.update(
            {
                "readable": True,
                "reason": None,
                "events_total": total,
                "events_with_tickers": with_tickers,
                "events_with_direction_field": with_direction,
                "events_with_magnitude_field": with_magnitude,
                "events_with_direction_and_magnitude": with_direction_and_magnitude,
                "coverage_start": dates[0] if dates else None,
                "coverage_end": dates[-1] if dates else None,
            }
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["readable"] = False
        out["reason"] = f"read_failed: {exc.__class__.__name__}"
        for k in (
            "events_total", "events_with_tickers",
            "events_with_direction_field", "events_with_magnitude_field",
            "events_with_direction_and_magnitude",
            "coverage_start", "coverage_end", "store_receipt",
        ):
            out[k] = None
        return out


def _build_store_evidence(*, coverage: Mapping[str, object], as_of: str) -> dict:
    """Honest store pointer — not an unregistered K1 EvidenceRef.

    Emitting ``evidence_foundation.reference.v1`` with owner_store
    ``chronicle.market_feed_alias`` fails ``lib.evidence_foundation.validate_reference``
    because that owner is not in contracts/evidence_foundation/vocabulary.v1.json
    (contracts/ is outside this module's owned paths). Shipping an invalid K1
    shape is refused; full semantic K1 requires a separate vocabulary
    registration PR. Until then the receipt points at the store with an
    explicit ``k1_registration: not_registered`` marker.
    """
    reason = coverage.get("reason")
    missingness_reason = None
    if not coverage.get("readable"):
        if isinstance(reason, str) and reason.startswith("read_failed"):
            missingness_reason = "source_unreadable"
        else:
            missingness_reason = "source_missing"
    return {
        "kind": "store",
        "ref": str(EVENTS_REL),
        "as_of": as_of,
        "receipt": coverage.get("store_receipt"),
        "k1_registration": "not_registered",
        "missingness_reason": missingness_reason,
    }


def resolve_market_feed_alias(
    root: Path | str | None = None,
    *,
    projection: Mapping[str, object] | None = None,
    as_of: str | None = None,
) -> dict:
    """Recompute whether a Market-Feed surface is SERVED, PARTIALLY_SERVED,
    NOT_SERVED, or UNKNOWN. Never raises; failures degrade into the receipt.
    """
    try:
        as_of_val = as_of or _today()
        coverage = market_feed_field_coverage(root)

        flags: set[str] = set()
        required = list(MARKET_FEED_REQUIRED_FIELDS)
        proj_out = _projection_out(projection)
        declared_fields = list(proj_out["declared_fields"])

        if proj_out["unknown_fields"]:
            flags.add("unknown_declared_fields")

        if not coverage["readable"]:
            state = "UNKNOWN"
            flags.add("store_unreadable")
            # Not-knowing: do not shape missingness like a measured absence of
            # every required field — nothing was measured.
            served_fields: list[str] = []
            missing_fields: list[str] = []
            reason = "store_unreadable: cannot determine alias state"
        else:
            schema_backed = sorted(
                f for f, src in MARKET_FEED_FIELD_SOURCES.items() if src is not None
            )
            store_has_direction = _positive_count(
                coverage.get("events_with_direction_field")
            )
            store_has_magnitude = _positive_count(
                coverage.get("events_with_magnitude_field")
            )
            store_has_direction_and_magnitude = _positive_count(
                coverage.get("events_with_direction_and_magnitude")
            )
            store_meets_served_coverage = _meets_served_coverage(coverage)

            if projection is None or not declared_fields:
                served_fields = schema_backed
                missing_fields = sorted(set(required) - set(schema_backed))
                if store_has_direction or store_has_magnitude:
                    # Store-side progress without a declared surface.
                    state = "PARTIALLY_SERVED"
                    flags.add("no_declared_projection")
                    if store_has_direction:
                        flags.add("store_has_direction_data_no_declared_projection")
                    if store_has_magnitude:
                        flags.add("store_has_magnitude_data_no_declared_projection")
                    reason = (
                        "store_has_impact_data_no_declared_projection: the store "
                        "carries direction/magnitude-bearing field(s) but no "
                        "projection has declared a surface that serves them"
                    )
                else:
                    state = "NOT_SERVED"
                    flags.add("no_declared_projection")
                    reason = "no_declared_projection: only schema-backed fields available"
            else:
                # Schema-backed fields are always available; the projection's
                # job is to supply the non-schema-backed ones (direction/
                # magnitude) with store-measured support.
                # A caller-supplied projection['support'][field]['sample_n'] is
                # NEVER trusted as evidence of store support -- that would let
                # any caller (including an LLM-originated one) grant SERVED by
                # simply asserting a number. The only evidence this module
                # accepts is its OWN store census (market_feed_field_coverage
                # above). ``support`` is kept in the receipt for audit/
                # debugging but plays no part in the grant decision.
                served_fields_set = set(schema_backed)
                unsupported_claims: list[str] = []
                below_threshold_claims: list[str] = []
                for f in declared_fields:
                    if f not in MARKET_FEED_REQUIRED_FIELDS:
                        continue
                    if MARKET_FEED_FIELD_SOURCES.get(f) is not None:
                        served_fields_set.add(f)
                        continue
                    if f in ("impact_direction", "impact_magnitude"):
                        if store_meets_served_coverage:
                            served_fields_set.add(f)
                        elif store_has_direction_and_magnitude:
                            below_threshold_claims.append(f)
                        else:
                            unsupported_claims.append(f)
                    else:
                        unsupported_claims.append(f)

                served_fields = sorted(served_fields_set & set(required))
                missing_fields = sorted(set(required) - served_fields_set)

                if unsupported_claims:
                    state = "PARTIALLY_SERVED"
                    flags.add("claim_unsupported_by_store")
                    if missing_fields:
                        flags.add("projection_incomplete")
                    reason = "claim_unsupported_by_store: declared field(s) lack store support"
                elif below_threshold_claims:
                    state = "PARTIALLY_SERVED"
                    flags.add("below_coverage_threshold")
                    if missing_fields:
                        flags.add("projection_incomplete")
                    reason = (
                        "below_coverage_threshold: co-occurrence exists but is "
                        f"below SERVED_MIN_CO_OCCURRENCE={SERVED_MIN_CO_OCCURRENCE} "
                        f"or share {SERVED_MIN_SHARE_OF_TICKER_EVENTS}"
                    )
                elif missing_fields:
                    state = "PARTIALLY_SERVED"
                    flags.add("projection_incomplete")
                    reason = "projection_incomplete: required field(s) neither schema-backed nor supported"
                else:
                    state = "SERVED"
                    reason = "projection_complete: all required fields schema-backed or store-supported"

        cause = _disclosure_cause(state, flags)
        disclosure_en = _lookup_disclosure(state, cause, "en")
        disclosure_zh = _lookup_disclosure(state, cause, "zh")

        receipt = {
            "schema": SCHEMA_VERSION,
            "ledger_row": LEDGER_ROW,
            "parent_row": PARENT_ROW,
            "state": state,
            "as_of": as_of_val,
            "projection": proj_out,
            "required_fields": list(required),
            "served_fields": sorted(served_fields),
            "missing_fields": sorted(missing_fields),
            "rejected_proxies": [dict(p) for p in REJECTED_PROXIES],
            "flags": sorted(flags),
            "coverage": coverage,
            "reason": reason,
            "disclosure_en": disclosure_en,
            "disclosure_zh": disclosure_zh,
            "evidence": _build_store_evidence(coverage=coverage, as_of=as_of_val),
        }
        return receipt
    except Exception as exc:  # noqa: BLE001
        state = "UNKNOWN"
        fallback_as_of = as_of or _today()
        fallback_coverage = {
            "store_path": str(EVENTS_REL), "readable": False,
            "reason": f"resolve_failed: {exc.__class__.__name__}",
            "events_total": None, "events_with_tickers": None,
            "events_with_direction_field": None,
            "events_with_magnitude_field": None,
            "events_with_direction_and_magnitude": None,
            "coverage_start": None,
            "coverage_end": None, "store_receipt": None,
        }
        return {
            "schema": SCHEMA_VERSION,
            "ledger_row": LEDGER_ROW,
            "parent_row": PARENT_ROW,
            "state": state,
            "as_of": fallback_as_of,
            "projection": _empty_projection(declared=False),
            "required_fields": list(MARKET_FEED_REQUIRED_FIELDS),
            "served_fields": [],
            "missing_fields": [],
            "rejected_proxies": [dict(p) for p in REJECTED_PROXIES],
            "flags": ["resolve_failed"],
            "coverage": fallback_coverage,
            "reason": f"resolve_failed: {exc.__class__.__name__}",
            "disclosure_en": _lookup_disclosure("UNKNOWN", None, "en"),
            "disclosure_zh": _lookup_disclosure("UNKNOWN", None, "zh"),
            "evidence": _build_store_evidence(
                coverage=fallback_coverage, as_of=fallback_as_of
            ),
        }


def alias_disclosure(receipt: Mapping[str, object], lang: str = "en") -> str:
    """Return the plain-word disclosure string for a receipt. Never raises:
    an unknown/missing state degrades to the UNKNOWN copy."""
    try:
        state = str(receipt.get("state") or "UNKNOWN")
        flags_raw = receipt.get("flags") or []
        flags = set(flags_raw) if isinstance(flags_raw, (list, tuple, set)) else set()
        cause = _disclosure_cause(state, flags)
        return _lookup_disclosure(state, cause, lang)
    except Exception:  # noqa: BLE001
        return _lookup_disclosure("UNKNOWN", None, "zh" if lang == "zh" else "en")
