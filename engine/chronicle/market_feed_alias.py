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
# (None = absent from the schema today).
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

DIRECTION_FIELD_CANDIDATES: tuple[str, ...] = (
    "impact_direction", "direction", "impact", "sign", "polarity",
)

_DISCLOSURE_EN: dict[str, str] = {
    "NOT_SERVED": (
        "We don't publish a market feed yet. We track the events and which "
        "tickers they touch — we do not yet publish which way each "
        "event pushed a stock, so that column is blank on purpose."
    ),
    "UNKNOWN": (
        "We can't read the event record right now, so we're not saying "
        "either way — this note updates when the record is back."
    ),
    "PARTIALLY_SERVED": (
        "Part of the market feed is live. Events and tickers are "
        "published; the direction of each event's effect is still blank."
    ),
    "SERVED": (
        "The market feed is live: each event, the tickers it touches, and "
        "which way it pushed them."
    ),
}

_DISCLOSURE_ZH: dict[str, str] = {
    "NOT_SERVED": "我们暂未发布市场事件流。事件与所涉个股已在追踪，但每个事件对个股的方向影响尚未发布，因此该栏目前留空。",
    "UNKNOWN": "目前无法读取事件记录，因此暂不作判断；记录恢复后此处会更新。",
    "PARTIALLY_SERVED": "市场事件流已部分上线：事件与个股已发布，事件影响方向仍为空。",
    "SERVED": "市场事件流已上线：事件、所涉个股，以及影响方向。",
}


def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def market_feed_field_coverage(root: Path | str | None = None) -> dict:
    """Deterministic census of the committed events.jsonl store.

    Unreadable/absent store => every count is None, never 0. Not-knowing must
    not be shaped like emptiness; a sparse worktree omits data/, so a 0 here
    would read as a proven "no events" and would let a future SERVED/
    NOT_SERVED call be made on nothing.
    """
    out = {
        "store_path": str(EVENTS_REL),
        "readable": False,
        "reason": None,
        "events_total": None,
        "events_with_tickers": None,
        "events_with_direction_field": None,
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
        with_direction = sum(
            1 for e in events if any(k in e for k in DIRECTION_FIELD_CANDIDATES)
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
                "coverage_start": dates[0] if dates else None,
                "coverage_end": dates[-1] if dates else None,
            }
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["readable"] = False
        out["reason"] = f"read_failed: {exc.__class__.__name__}"
        for k in (
            "events_total", "events_with_tickers", "events_with_direction_field",
            "coverage_start", "coverage_end", "store_receipt",
        ):
            out[k] = None
        return out


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

        if not coverage["readable"]:
            state = "UNKNOWN"
            flags.add("store_unreadable")
            served_fields: list[str] = []
            missing_fields = list(required)
            proj_out = {
                "declared": projection is not None,
                "name": None,
                "route": None,
                "declared_fields": [],
                "unknown_fields": [],
            }
            if projection is not None:
                proj_out["name"] = projection.get("name")
                proj_out["route"] = projection.get("route")
                decl = list(projection.get("fields") or [])
                proj_out["declared_fields"] = sorted(decl)
                proj_out["unknown_fields"] = sorted(
                    f for f in decl if f not in MARKET_FEED_REQUIRED_FIELDS
                )
            reason = "store_unreadable: cannot determine alias state"
        else:
            schema_backed = sorted(
                f for f, src in MARKET_FEED_FIELD_SOURCES.items() if src is not None
            )
            support = {}
            proj_out = {
                "declared": projection is not None,
                "name": None,
                "route": None,
                "declared_fields": [],
                "unknown_fields": [],
            }
            declared_fields: list[str] = []
            if projection is not None:
                proj_out["name"] = projection.get("name")
                proj_out["route"] = projection.get("route")
                declared_fields = list(projection.get("fields") or [])
                proj_out["declared_fields"] = sorted(declared_fields)
                proj_out["unknown_fields"] = sorted(
                    f for f in declared_fields if f not in MARKET_FEED_REQUIRED_FIELDS
                )
                support = dict(projection.get("support") or {})

            if projection is None:
                state = "NOT_SERVED"
                flags.add("no_declared_projection")
                served_fields = schema_backed
                missing_fields = sorted(set(required) - set(schema_backed))
                reason = "no_declared_projection: only schema-backed fields available"
            else:
                # Schema-backed fields are always available; the projection's
                # job is to supply the non-schema-backed ones (direction/
                # magnitude) with store-measured support.
                served_fields_set = set(schema_backed)
                unsupported_claims: list[str] = []
                for f in declared_fields:
                    if f not in MARKET_FEED_REQUIRED_FIELDS:
                        continue
                    if MARKET_FEED_FIELD_SOURCES.get(f) is not None:
                        served_fields_set.add(f)
                        continue
                    entry = support.get(f) or {}
                    sample_n = entry.get("sample_n") if isinstance(entry, Mapping) else None
                    if isinstance(sample_n, (int, float)) and sample_n and sample_n > 0:
                        served_fields_set.add(f)
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
                elif missing_fields:
                    state = "PARTIALLY_SERVED"
                    flags.add("projection_incomplete")
                    reason = "projection_incomplete: required field(s) neither schema-backed nor supported"
                else:
                    state = "SERVED"
                    reason = "projection_complete: all required fields schema-backed or store-supported"

        disclosure_en = _DISCLOSURE_EN[state]
        disclosure_zh = _DISCLOSURE_ZH[state]

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
            "evidence": {
                "kind": "store",
                "ref": str(EVENTS_REL),
                "as_of": as_of_val,
                "receipt": coverage.get("store_receipt"),
            },
        }
        return receipt
    except Exception as exc:  # noqa: BLE001
        state = "UNKNOWN"
        return {
            "schema": SCHEMA_VERSION,
            "ledger_row": LEDGER_ROW,
            "parent_row": PARENT_ROW,
            "state": state,
            "as_of": as_of or _today(),
            "projection": {"declared": False, "name": None, "route": None, "declared_fields": [], "unknown_fields": []},
            "required_fields": list(MARKET_FEED_REQUIRED_FIELDS),
            "served_fields": [],
            "missing_fields": list(MARKET_FEED_REQUIRED_FIELDS),
            "rejected_proxies": [dict(p) for p in REJECTED_PROXIES],
            "flags": ["resolve_failed"],
            "coverage": {
                "store_path": str(EVENTS_REL), "readable": False,
                "reason": f"resolve_failed: {exc.__class__.__name__}",
                "events_total": None, "events_with_tickers": None,
                "events_with_direction_field": None, "coverage_start": None,
                "coverage_end": None, "store_receipt": None,
            },
            "reason": f"resolve_failed: {exc.__class__.__name__}",
            "disclosure_en": _DISCLOSURE_EN["UNKNOWN"],
            "disclosure_zh": _DISCLOSURE_ZH["UNKNOWN"],
            "evidence": {"kind": "store", "ref": str(EVENTS_REL), "as_of": as_of or _today(), "receipt": None},
        }


def alias_disclosure(receipt: Mapping[str, object], lang: str = "en") -> str:
    """Return the plain-word disclosure string for a receipt's state. Never
    raises: an unknown/missing state degrades to the UNKNOWN copy."""
    try:
        state = receipt.get("state")
        table = _DISCLOSURE_ZH if lang == "zh" else _DISCLOSURE_EN
        return table.get(state, table["UNKNOWN"])
    except Exception:  # noqa: BLE001
        return _DISCLOSURE_ZH["UNKNOWN"] if lang == "zh" else _DISCLOSURE_EN["UNKNOWN"]
