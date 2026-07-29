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


def _context(scored: dict, story: dict, source_tier: int) -> dict:
    source_count = max(
        int(story.get("source_count", 0) or 0),
        int(story.get("sources_15m", 0) or 0),
        1,
    )
    if str(scored.get("corroboration_class") or "") == "direct-quote":
        evidence = "Primary source"
    elif source_count >= 2:
        evidence = "Multiple reports"
    else:
        evidence = "Single report"

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


def _draft(text: object, event_id: str, source_url: str) -> dict | None:
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

    draft = _draft(draft_text, event_id, source_url)
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
        "context": _context(scored, story, source_tier),
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


def _merge_packets(old: dict | None, new: dict) -> dict:
    if not isinstance(old, dict):
        return dict(new)

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

    drafts: dict[str, dict] = {}
    for row in list(old.get("drafts") or []) + list(new.get("drafts") or []):
        if isinstance(row, dict) and row.get("id"):
            drafts[str(row["id"])] = row
    merged["drafts"] = list(drafts.values())[-6:]
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
    if any(d.get("status") == "review" for d in merged["drafts"]):
        merged["stance"] = "Review the draft"
    elif confirmed:
        merged["stance"] = "Read the evidence"
    else:
        merged["stance"] = "Watch for confirmation"
    return merged


def _public_packet(packet: dict) -> dict:
    return {key: value for key, value in packet.items() if not key.startswith("_")}


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

    def upsert(self, packets: Iterable[dict], *, now: datetime) -> int:
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
                merged = _merge_packets(old, packet)
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
                 max_items: int = 80) -> dict:
        cutoff = _iso(_utc(now) - timedelta(hours=max(1.0, active_h)))
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
                stories.append(_public_packet(packet))
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

    store = IntelligenceStore(db_target)
    try:
        store.upsert(packets, now=now)
        store.prune(
            now=now,
            retention_h=float(cfg.get("retention_h", 72.0)),
            max_stories=int(cfg.get("max_stories", 1500)),
        )
        payload = store.snapshot(
            now=now,
            active_h=float(cfg.get("active_h", 48.0)),
            max_items=int(cfg.get("snapshot_max_items", 80)),
        )
    finally:
        store.close()
    _atomic_json(sink_target, payload)
    return payload
