"""Persistent, evidence-first story packets for the real-time Intelligence Desk.

The press fastlane is an arrival rail. This module turns those arrivals into a
durable newsroom view:

    filtered item -> story packet -> cross-tick merge -> live/intelligence.json

It deliberately does not publish to X. Drafts are review candidates, every
source remains attached, and a score never appears in the public artifact.
SQLite state is host-local and gitignored; the exported JSON is an atomic,
display-tier snapshot served through the registered-user live boundary.

Import closure is stdlib-only so the 75-second daemon and the thin marketing CI
lane can always import it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


PACKET_SCHEMA = "intelligence.story_packet/v1"
DESK_SCHEMA = "intelligence.desk/v1"

DEFAULT_DB_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/state/intelligence/intelligence.db",
    "data/marketing/press/intelligence.db",
)
DEFAULT_SNAPSHOT_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/public/live/intelligence.json",
    "data/marketing/press/intelligence.json",
)

# V2 honesty defaults. Every one is overridable from
# config/press_sources.yml -> wire.intelligence; the code defaults exist so a
# config-less checkout (and every existing test) behaves exactly as before.
DEFAULT_MARKET_STALE_MIN = 30.0
DEFAULT_TIMELINE_MAX = 12
DEFAULT_PACE_CFG: dict[str, float] = {
    "rising_recent_min": 20.0,
    "rising_sources_60m": 2.0,
    "cooling_h": 6.0,
}
# A story is "New" only while it is both single-sourced and this young.
_NEW_STORY_MAX_MIN = 60.0
# How far ahead of the tick clock an evidence stamp may sit and still count as
# evidence for the pace recompute. See `_recompute_pace`.
_FUTURE_STAMP_TOLERANCE = timedelta(minutes=5)

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EVENT_LANES = {
    "macro_print": "macro",
    "policy": "policy",
    "geopolitical": "policy",
    "company_news": "companies",
    "earnings": "companies",
    "none": "markets",
}
_LANE_LABELS = {
    "markets": ("Markets", "市场"),
    "macro": ("Macro", "宏观"),
    "policy": ("Policy", "政策"),
    "companies": ("Companies", "公司"),
}
_WHY = {
    "macro_print": (
        "A fresh macro input that can change the rate and growth narrative.",
        "新的宏观数据可能改变利率与增长叙事。",
    ),
    "policy": (
        "A policy development with potential market or business consequences.",
        "这项政策进展可能影响市场或企业。",
    ),
    "geopolitical": (
        "A geopolitical development where confirmation and market follow-through matter.",
        "地缘事件仍需关注后续确认与市场反应。",
    ),
    "company_news": (
        "A company-specific development that may change the operating narrative.",
        "公司层面的新进展可能改变其经营叙事。",
    ),
    "earnings": (
        "A new company result or outlook update.",
        "新的公司业绩或指引更新。",
    ),
    "none": (
        "A developing market story worth keeping on the desk.",
        "值得持续跟踪的市场动态。",
    ),
}
# The SAME display words news.html already maps for `stage`. A timeline label is
# public copy, so it may never carry the raw slug.
_STAGE_WORDS = {
    "high_impact": ("High impact", "高影响"),
    "confirmed": ("Confirmed", "已确认"),
    "developing": ("Developing", "发展中"),
}


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(dt)


def _clean(value: object, cap: int) -> str:
    return _WS_RE.sub(" ", str(value or "")).strip()[:cap]


def _story_id(scored: dict, story: dict | None) -> str:
    sid = _clean((story or {}).get("story_id"), 96)
    if sid:
        return sid
    basis = "|".join((
        _clean(scored.get("truth_status_id"), 120),
        _clean(scored.get("url"), 500),
        _clean(scored.get("headline"), 300).lower(),
    ))
    return "intel_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]


def _source_key(source: dict) -> str:
    url = str(source.get("url") or "")
    try:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        host = ""
    return (host or str(source.get("name") or "").lower().lstrip("@")
            or str(source.get("event_id") or ""))


def _plain_brief(scored: dict) -> str:
    headline = _clean(scored.get("headline"), 320)
    body = _clean(scored.get("body_snippet"), 520)
    if not body or body.lower() == headline.lower():
        return headline
    return body


def _evidence_word(*, verified: bool, source_count: int) -> str:
    """The `context.evidence` chip for a story with this much backing.

    ONE definition, used at build time AND re-applied by `_merge_packets`: the
    merge recomputes `source_count` and `stage` from the union of evidence, and a
    chip left at whatever the last-arriving item alone could see contradicted
    them. That is not hypothetical on the V2 path — the claim registry aliases
    items the corroboration ledger never paired (a Truth post keys on
    `truth:<status_id>`, a late arrival falls outside the ledger's window), so a
    genuine two-source story served "Confirmed", "2 sources", "X joined
    coverage" and "Single report" on the same card.
    """
    if verified:
        return "Primary source"
    return "Multiple reports" if int(source_count or 0) >= 2 else "Single report"


def _context(scored: dict, story: dict, source_tier: int,
             *, source_count: int = 0) -> dict:
    source_count = max(
        int(source_count or 0),
        int(story.get("source_count", 0) or 0),
        int(story.get("sources_15m", 0) or 0),
        1,
    )
    evidence = _evidence_word(
        verified=str(scored.get("corroboration_class") or "") == "direct-quote",
        source_count=source_count,
    )

    # Build-time pace is a seed only: `IntelligenceStore.snapshot` recomputes it
    # from the story's own evidence timestamps for EVERY served packet, so a
    # story that was "Rising" two days ago is never still served as Rising.
    recent = int(story.get("sources_15m", 0) or 0)
    pace = "Rising" if recent >= 2 else ("New" if story.get("is_new") else "Active")
    source_quality = {
        1: "Primary / top-tier",
        2: "Established press",
        3: "Aggregator",
    }.get(source_tier, "Unrated source")
    return {"evidence": evidence, "pace": pace, "source_quality": source_quality}


def _market_context(
    scored: dict,
    quotes_store: dict | None,
    *,
    now: datetime,
    tape_cfg: dict | None,
) -> dict | None:
    if not isinstance(quotes_store, dict):
        return None
    try:
        from engine.marketing.tape_stamp import compute_stamp  # noqa: PLC0415
        hit = compute_stamp(scored, quotes_store, now=now, cfg=tape_cfg or {})
    except Exception:  # noqa: BLE001
        return None
    if not hit.get("stamp"):
        return None
    return {
        "label": str(hit["stamp"]),
        "symbol": hit.get("symbol"),
        "move_pct": hit.get("move_pct"),
        # This is a session move from the quote store, never a causal
        # "since the headline" claim.
        "basis": "session vs prior close",
        "as_of": _iso(now),
    }


def _draft(text: object, event_id: str, source_url: str, *,
           now: datetime, origin: str = "wire") -> dict | None:
    """One review candidate. `shape` is its CANONICAL slot on the story.

    `_merge_packets` keeps at most one draft per shape, so a re-arriving draft
    whose text drifted (a tape stamp attached late, a recomposed body) REPLACES
    its shape-mate instead of accreting a near-duplicate in the review queue.
    """
    candidate = _clean(text, 700)
    if not candidate:
        return None
    # A structured tape suffix is useful context but source URLs do not belong
    # inside the draft body unless the copywriter explicitly added one.
    candidate = _URL_RE.sub("", candidate).strip()
    if not candidate:
        return None
    fits_x = len(candidate) <= 280
    return {
        "id": "draft_" + hashlib.sha1(
            f"{event_id}|{candidate}".encode("utf-8")
        ).hexdigest()[:16],
        "shape": "wire" if fits_x else "long_post",
        "text": candidate,
        "status": "review" if fits_x else "needs_edit",
        "characters": len(candidate),
        "requires_review": True,
        "source_url": source_url,
        "origin": origin,
        "updated_at": _iso(now),
    }


def build_story_packet(
    scored: dict,
    *,
    story: dict | None,
    now: datetime,
    corr_sources: Iterable[str] = (),
    draft_text: object = "",
    quotes_store: dict | None = None,
    tape_cfg: dict | None = None,
) -> dict:
    """Build one public-safe story packet from a scored, garbage-cleared item.

    `salience` is used only to choose a broad impact band; neither it nor any
    feature component is copied into the returned packet.
    """
    now = _utc(now)
    story = dict(story or {})
    event_id = _clean(scored.get("id"), 160)
    sid = _story_id(scored, story)
    event_class = _clean(scored.get("event_class"), 40) or "none"
    lane = _EVENT_LANES.get(event_class, "markets")
    label_en, label_zh = _LANE_LABELS[lane]
    headline = _clean(scored.get("headline"), 320)
    source_name = _clean(
        scored.get("source_name") or scored.get("source"), 120
    ) or "Unknown source"
    source_url = _clean(scored.get("url"), 900)
    published_at = (
        _clean(scored.get("published_at"), 40)
        or _clean(story.get("first_seen"), 40)
        or _iso(now)
    )

    try:
        from engine import qkernel  # noqa: PLC0415
        source_tier = qkernel.source_tier(
            (urlsplit(source_url).hostname or "") if source_url else "",
            str(scored.get("source") or source_name),
        )
    except Exception:  # noqa: BLE001
        source_tier = 0

    corr_keys = {str(s) for s in corr_sources if str(s)}
    source_count = max(
        len(corr_keys),
        int(story.get("source_count", 0) or 0),
        1,
    )
    verified = str(scored.get("corroboration_class") or "") == "direct-quote"
    confirmed = verified or source_count >= 2
    try:
        high_impact = float(scored.get("salience", 0.0) or 0.0) >= 70.0
    except (TypeError, ValueError):
        high_impact = False
    stage = "high_impact" if confirmed and high_impact else (
        "confirmed" if confirmed else "developing"
    )

    tickers: list[str] = []
    matched = scored.get("matched")
    if isinstance(matched, dict):
        for ticker in matched.get("tickers") or []:
            token = _clean(ticker, 16).upper().lstrip("$")
            if token and token not in tickers:
                tickers.append(token)

    draft = _draft(draft_text, event_id, source_url, now=now)
    routes = ["wire"]
    if confirmed:
        routes.append("analysis")
    if stage == "high_impact":
        routes.append("thread")

    first_seen = _clean(story.get("first_seen"), 40) or published_at
    updated_at = _clean(story.get("last_seen"), 40) or _iso(now)
    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "id": sid,
        "stage": stage,
        # MACHINE field: the admin approve flow routes an approved draft to an
        # account by event_class. It is a coarse categorical lane name, not a
        # score, and the news.html client never renders it.
        "event_class": event_class,
        "lane": lane,
        "lane_label_en": label_en,
        "lane_label_zh": label_zh,
        "headline": headline,
        "brief": _plain_brief(scored),
        "why_it_matters_en": _WHY.get(event_class, _WHY["none"])[0],
        "why_it_matters_zh": _WHY.get(event_class, _WHY["none"])[1],
        "first_seen": first_seen,
        "updated_at": updated_at,
        "source_count": source_count,
        "tickers": tickers[:8],
        "context": _context(scored, story, source_tier,
                            source_count=source_count),
        "evidence": [{
            "event_id": event_id,
            "name": source_name,
            "url": source_url,
            "published_at": published_at,
            "headline": headline,
        }],
        "market": _market_context(
            scored, quotes_store, now=now, tape_cfg=tape_cfg
        ),
        "drafts": [draft] if draft else [],
        "content_routes": routes,
        "stance": (
            "Review the draft" if draft and draft["status"] == "review"
            else "Read the evidence" if confirmed
            else "Watch for confirmation"
        ),
        # Merge hints are broad categorical facts, not public scores.
        "_verified": verified,
        "_impact_band": "high" if high_impact else "normal",
    }
    return packet


def _timeline_event(kind: str, ts: str, *, source_name: str = "",
                    stage: str = "") -> dict:
    """One public, bilingual timeline row. Fixed templates — never a raw slug.

    Source names stay Latin in both languages (a wire's masthead is its name in
    any language); everything around them is house copy.
    """
    name = _clean(source_name, 60)
    if kind == "new_source":
        label_en = f"{name} joined coverage" if name else "A new source joined coverage"
        label_zh = f"新增来源：{name}" if name else "新增来源"
    elif kind == "stage":
        word_en, word_zh = _STAGE_WORDS.get(
            str(stage), _STAGE_WORDS["developing"]
        )
        label_en = f"Stage: {word_en}"
        label_zh = f"阶段：{word_zh}"
    else:
        kind = "first_report"
        label_en = f"First report: {name}" if name else "First report"
        label_zh = f"首次报道：{name}" if name else "首次报道"
    row = {"ts": ts, "kind": kind, "label_en": label_en, "label_zh": label_zh}
    if name and kind in ("first_report", "new_source"):
        row["source_name"] = name
    return row


def _coherent_zh(merged: dict, old: dict, new: dict, field: str) -> None:
    """Keep a zh twin only while its English original is still the served one.

    Incoming wins when present. When the merged EN text moved on without a fresh
    translation, the stale zh is DROPPED: an out-of-date Chinese headline next to
    a newer English one is a worse failure than the honest 英文原文 fallback.
    """
    zh_field = f"{field}_zh"
    current = _clean(merged.get(field), 700)
    for candidate in (new, old):
        zh = _clean(candidate.get(zh_field), 700)
        if zh and _clean(candidate.get(field), 700) == current:
            merged[zh_field] = zh
            return
    merged.pop(zh_field, None)


def _merge_why(merged: dict, old: dict, new: dict) -> None:
    """Resolve `why_it_matters` across a merge. A phrased line outranks a canned one.

    Every packet ``build_story_packet`` produces carries the CANNED per-class
    sentence, so a story phrased on tick 1 would have that phrasing overwritten
    on tick 2 by the very next arrival — the LLM pass is cached per headline and
    deliberately does not pay again. The `_why_phrased` marker (internal, never
    served) is what survives in the stored row and defends the phrasing:

        canned  vs phrased(stored)  -> the stored phrasing stands
        phrased vs canned(stored)   -> the phrasing replaces the canned line
        phrased vs phrased(stored)  -> the incoming phrasing wins

    The zh twin travels WITH its English original: it is taken from whichever
    side supplied the winning line, and when that side has none the canned
    per-class zh sentence is used. That sentence is generically true for the
    event class, which makes it an honest fallback beside a phrased English
    line — a Chinese sentence translated from some OTHER English would not be.
    """
    old_phrased = bool(old.get("_why_phrased"))
    new_phrased = bool(new.get("_why_phrased"))
    old_en = _clean(old.get("why_it_matters_en"), 700)
    new_en = _clean(new.get("why_it_matters_en"), 700)

    if old_phrased and not new_phrased and old_en:
        winner, why_en = old, old_en
    elif new_en:
        winner, why_en = new, new_en
    elif old_en:
        winner, why_en = old, old_en
    else:
        return

    merged["why_it_matters_en"] = why_en
    zh = _clean(winner.get("why_it_matters_zh"), 700)
    if not zh:
        event_class = str(merged.get("event_class") or "none")
        zh = _WHY.get(event_class, _WHY["none"])[1]
    merged["why_it_matters_zh"] = zh
    if old_phrased or new_phrased:
        merged["_why_phrased"] = True
    else:
        merged.pop("_why_phrased", None)


def _merge_packets(old: dict | None, new: dict, *, now: datetime | None = None,
                   timeline_max: int = DEFAULT_TIMELINE_MAX) -> dict:
    stamp = (
        _utc(now) if isinstance(now, datetime)
        else (_parse_iso(new.get("updated_at"))
              or datetime.now(timezone.utc))
    )
    cap = max(1, int(timeline_max or DEFAULT_TIMELINE_MAX))

    if not isinstance(old, dict):
        merged = dict(new)
        rows = [r for r in merged.get("evidence") or [] if isinstance(r, dict)]
        first_name = str(rows[0].get("name") or "") if rows else ""
        # Normalized, never the raw upstream stamp: `first_seen` arrives in
        # whatever offset form its producer used and this is public payload.
        first_ts = _iso(_parse_iso(merged.get("first_seen")) or stamp)
        carried = [
            row for row in (merged.get("timeline") or []) if isinstance(row, dict)
        ]
        merged["timeline"] = (carried or [
            _timeline_event("first_report", first_ts, source_name=first_name)
        ])[:cap]
        return merged

    merged = dict(old)
    merged.update({
        key: value for key, value in new.items()
        if value not in (None, "", [], {})
    })

    old_first = _parse_iso(old.get("first_seen"))
    new_first = _parse_iso(new.get("first_seen"))
    if old_first and new_first:
        merged["first_seen"] = _iso(min(old_first, new_first))
    elif old.get("first_seen"):
        merged["first_seen"] = old["first_seen"]

    evidence: dict[str, dict] = {}
    for row in list(old.get("evidence") or []) + list(new.get("evidence") or []):
        if not isinstance(row, dict):
            continue
        key = str(row.get("event_id") or row.get("url") or _source_key(row))
        if key:
            evidence[key] = row
    merged["evidence"] = sorted(
        evidence.values(),
        key=lambda row: str(row.get("published_at") or ""),
        reverse=True,
    )[:24]

    distinct_sources = {
        _source_key(row) for row in merged["evidence"] if _source_key(row)
    }
    merged["source_count"] = max(
        int(old.get("source_count", 0) or 0),
        int(new.get("source_count", 0) or 0),
        len(distinct_sources),
        1,
    )

    # CANONICAL DRAFTS: one slot per shape. Keying by draft id let tape-stamp
    # drift accrete five near-identical wire drafts on one story and noise the
    # review queue; keying by shape means a drifted redraft replaces its
    # shape-mate. Unknown/future shapes ("analysis", an LLM shape) get their own
    # slot generically — this dict is never a whitelist.
    #
    # Review N8: within a slot, a stored LLM phrasing OUTRANKS an incoming
    # deterministic draft while the story's headline is unchanged — the LLM pass
    # is budget-capped and cache-keyed, so most ticks re-arrive with only the
    # deterministic wire text, and letting that evict the phrased copy silently
    # reverted the story every quiet tick. A moved headline releases the slot:
    # stale phrasing must not outlive the story text it phrased.
    headline_moved = _clean(old.get("headline"), 320) != _clean(
        new.get("headline"), 320)
    drafts: dict[str, dict] = {}
    for row in list(old.get("drafts") or []) + list(new.get("drafts") or []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        slot = str(row.get("shape") or "wire")
        held = drafts.get(slot)
        if (held is not None and not headline_moved
                and str(held.get("origin") or "") == "llm"
                and str(row.get("origin") or "") != "llm"):
            continue
        drafts[slot] = row
    merged["drafts"] = list(drafts.values())[:6]
    # A market stamp is a fresh, threshold-gated session observation. Never
    # carry yesterday's/last-tick's stamp forward when the current quote is
    # quiet or stale.
    merged["market"] = new.get("market")

    verified = bool(old.get("_verified")) or bool(new.get("_verified"))
    high = old.get("_impact_band") == "high" or new.get("_impact_band") == "high"
    confirmed = verified or int(merged["source_count"]) >= 2
    merged["_verified"] = verified
    merged["_impact_band"] = "high" if high else "normal"
    merged["stage"] = "high_impact" if confirmed and high else (
        "confirmed" if confirmed else "developing"
    )
    routes = ["wire"]
    if confirmed:
        routes.append("analysis")
    if merged["stage"] == "high_impact":
        routes.append("thread")
    merged["content_routes"] = routes
    # The evidence chip is part of the same verdict as `stage` and
    # `source_count`, so it is re-derived from the merged totals rather than
    # inherited from the incoming packet, which only ever saw its own item.
    # (`pace` is deliberately NOT touched here — `_served_packet` recomputes it
    # from evidence timestamps at snapshot time.)
    merged_context = dict(merged.get("context") or {})
    merged_context["evidence"] = _evidence_word(
        verified=verified, source_count=int(merged["source_count"])
    )
    merged["context"] = merged_context
    if any(d.get("status") == "review" for d in merged["drafts"]):
        merged["stance"] = "Review the draft"
    elif confirmed:
        merged["stance"] = "Read the evidence"
    else:
        merged["stance"] = "Watch for confirmation"

    # TIMELINE: what changed on this story, in public words. Deterministic —
    # derived from the diff between the stored packet and the merged one, never
    # from a score. Newest first, bounded.
    events: list[dict] = []
    old_stage = str(old.get("stage") or "")
    if old_stage and old_stage != str(merged["stage"]):
        events.append(_timeline_event(
            "stage", _iso(stamp), stage=str(merged["stage"])
        ))
    old_keys = {
        _source_key(row) for row in (old.get("evidence") or [])
        if isinstance(row, dict)
    }
    old_keys.discard("")
    fresh: dict[str, str] = {}
    for row in merged["evidence"]:
        key = _source_key(row)
        if key and key not in old_keys and key not in fresh:
            fresh[key] = str(row.get("name") or "")
    for key in sorted(fresh):
        events.append(_timeline_event(
            "new_source", _iso(stamp), source_name=fresh[key]
        ))
    history = [row for row in (old.get("timeline") or []) if isinstance(row, dict)]
    if not history:
        # A v1 row predates the timeline; seed it from what the story already knows.
        first_rows = [r for r in merged["evidence"] if isinstance(r, dict)]
        history = [_timeline_event(
            "first_report",
            _iso(_parse_iso(merged.get("first_seen")) or stamp),
            source_name=str(first_rows[-1].get("name") or "") if first_rows else "",
        )]
    merged["timeline"] = (events + history)[:cap]

    # zh twins last: they must agree with the EN text the merge just settled on.
    _coherent_zh(merged, old, new, "headline")
    _coherent_zh(merged, old, new, "brief")
    _merge_why(merged, old, new)
    return merged


def _public_packet(packet: dict) -> dict:
    return {key: value for key, value in packet.items() if not key.startswith("_")}


def _pace_cfg(cfg: object) -> dict[str, float]:
    out = dict(DEFAULT_PACE_CFG)
    if isinstance(cfg, dict):
        for key in list(out):
            try:
                out[key] = float(cfg.get(key, out[key]))
            except (TypeError, ValueError):
                continue
    return out


def _recompute_pace(packet: dict, *, now: datetime, pace_cfg: dict) -> str:
    """The story's pace AS OF NOW, from its own evidence timestamps.

    A packet's pace was frozen at build time, so a story that stopped moving two
    days ago kept serving "Rising" forever. The desk states what is true when the
    reader loads it, which is also the only way `Cooling` can ever be said.
    """
    rows = [row for row in packet.get("evidence") or [] if isinstance(row, dict)]
    stamps = [
        ts for ts in (_parse_iso(row.get("published_at")) for row in rows)
        if ts is not None
        # A FUTURE STAMP WOULD FREEZE THIS STORY AT "Rising" FOREVER. `_age_min`
        # floors at 0, so one clock-skewed or embargo-dated publisher pins
        # `newest_age` at 0: the Rising test always passes and the Cooling test
        # (`newest_age >= cooling_h * 60`) can never pass again, for the whole 72h
        # the row is retained. Snapshot-time honesty is the entire point of this
        # function, so a stamp the clock says has not happened yet is not evidence
        # about how fast the story is moving. The tolerance absorbs ordinary
        # host/publisher clock drift rather than treating it as a fault.
        and ts <= now + _FUTURE_STAMP_TOLERANCE
    ]
    if not stamps:
        fallback = (_parse_iso(packet.get("updated_at"))
                    or _parse_iso(packet.get("first_seen")))
        if fallback is None:
            return str((packet.get("context") or {}).get("pace") or "Active")
        stamps = [fallback]

    def _age_min(ts: datetime) -> float:
        return max(0.0, (now - ts).total_seconds() / 60.0)

    newest_age = min(_age_min(ts) for ts in stamps)
    within_60m = sum(1 for ts in stamps if _age_min(ts) <= 60.0)
    first = _parse_iso(packet.get("first_seen")) or max(stamps)
    story_age = _age_min(first)

    if max(len(rows), 1) <= 1 and story_age < _NEW_STORY_MAX_MIN:
        return "New"
    if (newest_age <= pace_cfg["rising_recent_min"]
            and within_60m >= pace_cfg["rising_sources_60m"]):
        return "Rising"
    if newest_age >= pace_cfg["cooling_h"] * 60.0:
        return "Cooling"
    return "Active"


def _served_packet(packet: dict, *, now: datetime, pace_cfg: dict,
                   market_stale_min: float) -> dict:
    """The public view of a stored packet, recomputed at SERVE time."""
    served = _public_packet(packet)
    context = dict(served.get("context") or {})
    context["pace"] = _recompute_pace(packet, now=now, pace_cfg=pace_cfg)
    served["context"] = context

    market = served.get("market")
    if isinstance(market, dict):
        as_of = _parse_iso(market.get("as_of"))
        # An unstamped block cannot be proven fresh, so it is served as null too:
        # a market chip is a claim about RIGHT NOW or it is nothing.
        if as_of is None or (now - as_of) > timedelta(
            minutes=max(0.0, market_stale_min)
        ):
            served["market"] = None
    return served


class IntelligenceStore:
    """Small SQLite story store with bounded retention and atomic JSON export."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=5.0)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS stories (
                story_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                packet_json TEXT NOT NULL
            )
            """
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS stories_updated_idx ON stories(updated_at DESC)"
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def upsert(self, packets: Iterable[dict], *, now: datetime,
               timeline_max: int = DEFAULT_TIMELINE_MAX) -> int:
        count = 0
        with self.db:
            for packet in packets:
                if not isinstance(packet, dict) or packet.get("schema") != PACKET_SCHEMA:
                    continue
                sid = str(packet.get("id") or "")
                if not sid:
                    continue
                row = self.db.execute(
                    "SELECT packet_json FROM stories WHERE story_id = ?", (sid,)
                ).fetchone()
                old = None
                if row:
                    try:
                        old = json.loads(row[0])
                    except (TypeError, ValueError):
                        old = None
                merged = _merge_packets(
                    old, packet, now=now, timeline_max=timeline_max
                )
                merged["updated_at"] = _iso(now)
                self.db.execute(
                    """
                    INSERT INTO stories(story_id, first_seen, updated_at, packet_json)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(story_id) DO UPDATE SET
                        first_seen=excluded.first_seen,
                        updated_at=excluded.updated_at,
                        packet_json=excluded.packet_json
                    """,
                    (
                        sid,
                        str(merged.get("first_seen") or _iso(now)),
                        _iso(now),
                        json.dumps(merged, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                count += 1
        return count

    def prune(self, *, now: datetime, retention_h: float = 72.0,
              max_stories: int = 1500) -> None:
        cutoff = _iso(_utc(now) - timedelta(hours=max(1.0, retention_h)))
        with self.db:
            self.db.execute("DELETE FROM stories WHERE updated_at < ?", (cutoff,))
            self.db.execute(
                """
                DELETE FROM stories WHERE story_id IN (
                    SELECT story_id FROM stories
                    ORDER BY updated_at DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (max(1, max_stories),),
            )

    def snapshot(self, *, now: datetime, active_h: float = 48.0,
                 max_items: int = 80, pace_cfg: dict | None = None,
                 market_stale_min: float = DEFAULT_MARKET_STALE_MIN) -> dict:
        now = _utc(now)
        pace = _pace_cfg(pace_cfg)
        cutoff = _iso(now - timedelta(hours=max(1.0, active_h)))
        rows = self.db.execute(
            """
            SELECT packet_json FROM stories
            WHERE updated_at >= ?
            ORDER BY updated_at DESC
            """,
            (cutoff,),
        ).fetchall()
        stories: list[dict] = []
        for row in rows:
            try:
                packet = json.loads(row[0])
            except (TypeError, ValueError):
                continue
            if isinstance(packet, dict):
                stories.append(_served_packet(
                    packet, now=now, pace_cfg=pace,
                    market_stale_min=market_stale_min,
                ))
        # Stage priority first; within each stage the latest story leads.
        ordered: list[dict] = []
        for stage in ("high_impact", "confirmed", "developing"):
            group = [p for p in stories if p.get("stage") == stage]
            ordered.extend(sorted(
                group, key=lambda p: str(p.get("updated_at") or ""), reverse=True
            ))
        known_stages = {"high_impact", "confirmed", "developing"}
        ordered.extend(sorted(
            (p for p in stories if p.get("stage") not in known_stages),
            key=lambda p: str(p.get("updated_at") or ""),
            reverse=True,
        ))
        stories = ordered[:max(1, max_items)]

        source_keys: set[str] = set()
        confirmed = 0
        draft_ready = 0
        for packet in stories:
            if packet.get("stage") in ("confirmed", "high_impact"):
                confirmed += 1
            if any(
                isinstance(d, dict) and d.get("status") == "review"
                for d in packet.get("drafts") or []
            ):
                draft_ready += 1
            for source in packet.get("evidence") or []:
                if isinstance(source, dict):
                    key = _source_key(source)
                    if key:
                        source_keys.add(key)

        newest = max(
            (_parse_iso(p.get("updated_at")) for p in stories),
            default=None,
            key=lambda value: value or datetime.min.replace(tzinfo=timezone.utc),
        )
        state = "quiet"
        if newest and (_utc(now) - newest) <= timedelta(minutes=15):
            state = "live"
        return {
            "schema": DESK_SCHEMA,
            "updated_at": _iso(now),
            "health": {
                "state": state,
                "active_stories": len(stories),
                "confirmed": confirmed,
                "draft_ready": draft_ready,
                "sources_online": len(source_keys),
            },
            "stories": stories,
        }


def _first_usable_path(candidates: Iterable[str], *, root: Path) -> Path | None:
    for raw in candidates:
        path = Path(str(raw))
        if not path.is_absolute():
            path = root / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, probe = tempfile.mkstemp(prefix=".intel-write-", dir=path.parent)
            os.close(fd)
            os.unlink(probe)
            return path
        except OSError:
            continue
    return None


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _quarantine_db(path: Path, *, now: datetime, exc: BaseException) -> None:
    """Move a broken store aside so the next open can create a fresh one.

    A corrupt (or locked-beyond-retry) SQLite file used to freeze the desk
    FOREVER behind a daemon whose logs looked healthy: every tick raised, the
    error was logged, and the snapshot stayed at whatever it last was. Renaming
    keeps the evidence on disk for a postmortem while the desk keeps running —
    the store is host-local derived state, rebuilt from the next few ticks.
    """
    stamp = _utc(now).strftime("%Y%m%dT%H%M%SZ")
    aside = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        if path.exists():
            path.replace(aside)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
    # WAL/SHM siblings belong to the quarantined file; leaving them next to a
    # fresh database is how a "healed" store corrupts itself again on open.
    for suffix in ("-wal", "-shm"):
        side = path.with_name(path.name + suffix)
        try:
            if side.exists():
                side.replace(aside.with_name(aside.name + suffix))
        except OSError:
            try:
                side.unlink()
            except OSError:
                pass
    print(
        f"::warning title=intelligence-db-quarantined::{type(exc).__name__}: "
        f"{exc} — moved {path.name} aside as {aside.name} and recreated the store",
        flush=True,
    )


def _store_cycle(db_target: Path, packets: list[dict], *, now: datetime,
                 cfg: dict) -> dict:
    """One full store tick: merge, prune, snapshot. Always closes the store."""
    store = IntelligenceStore(db_target)
    try:
        store.upsert(
            packets, now=now,
            timeline_max=int(cfg.get("timeline_max", DEFAULT_TIMELINE_MAX)),
        )
        store.prune(
            now=now,
            retention_h=float(cfg.get("retention_h", 72.0)),
            max_stories=int(cfg.get("max_stories", 1500)),
        )
        return store.snapshot(
            now=now,
            active_h=float(cfg.get("active_h", 48.0)),
            max_items=int(cfg.get("snapshot_max_items", 80)),
            pace_cfg=cfg.get("pace"),
            market_stale_min=float(
                cfg.get("market_stale_min", DEFAULT_MARKET_STALE_MIN)
            ),
        )
    finally:
        try:
            store.close()
        except sqlite3.Error:
            pass


def update_intelligence_desk(
    packets: Iterable[dict],
    *,
    root: Path | str,
    now: datetime,
    cfg: dict | None = None,
    db_path: Path | str | None = None,
    snapshot_path: Path | str | None = None,
) -> dict:
    """Merge a tick and publish a new desk snapshot. Returns the payload.

    Explicit paths are the test/development seam. Production chooses the first
    writable path from the configured candidates, with the gitignored repo path
    as its last fallback.
    """
    root = Path(root)
    cfg = cfg or {}
    db_candidates = cfg.get("db_paths") or DEFAULT_DB_PATHS
    sink_candidates = cfg.get("snapshot_paths") or DEFAULT_SNAPSHOT_PATHS
    db_target = Path(db_path) if db_path is not None else _first_usable_path(
        db_candidates, root=root
    )
    sink_target = (
        Path(snapshot_path) if snapshot_path is not None
        else _first_usable_path(sink_candidates, root=root)
    )
    if db_target is None or sink_target is None:
        raise OSError("no writable Intelligence Desk database/snapshot path")

    # Materialised ONCE: the self-heal retry below re-reads this list, and a
    # generator would hand the second attempt an empty tick.
    batch = [p for p in packets]
    try:
        payload = _store_cycle(db_target, batch, now=now, cfg=cfg)
    except sqlite3.DatabaseError as exc:
        _quarantine_db(db_target, now=now, exc=exc)
        # Exactly ONE retry. A second failure is not a corrupt file — it is a
        # broken host (read-only mount, full disk) — and it must reach the
        # daemon's log rather than be swallowed into a silently empty desk.
        payload = _store_cycle(db_target, batch, now=now, cfg=cfg)
    _atomic_json(sink_target, payload)
    return payload
