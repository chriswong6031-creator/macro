"""engine.neuralweb.brain_market_intel — Mastermind retrieval: live events + research.

CLASSIFICATION: read-only retrieval helpers for the Mastermind brain gateway.
This module holds the FUNCTIONS and their Anthropic tool schemas only; the
gateway owns dispatch, the tool allowlist, and tier gating. Nothing here is
imported by the nightly, writes a file, opens a socket, or calls an LLM.

TIER: display/context — READ-ONLY. Never computes a signal, score, rank, size,
or gate. Both functions are pure reads over artifacts other lanes publish.

PUBLIC API
----------
get_market_events(root, window_h=12.0, limit=5, symbol=None) -> dict
    Fresh market events, merged from the intraday press wire (wires.v1) and
    topped up from the nightly news digests when the wire is thin.

search_research(root, query, limit=5) -> dict
    Deterministic keyword search over the committed research-vault catalog
    (third-party institutional summaries — never the desk's own signals).

EVENTS_TOOL_SCHEMA / RESEARCH_TOOL_SCHEMA
    Anthropic tool definitions, shaped like brain_gateway._brain_tool_schemas().

EPISTEMICS LAW (TI-R5) — WHY THE OUTPUT IS A WHITELIST
------------------------------------------------------
get_market_events returns FACTS ONLY: a timestamp, the headline the desk
composed, the source, the desk-computed salience where one exists, and the
corroboration chip. It must NEVER emit a predicted effect, a beneficiary or
casualty list, a "shelter" mapping, or an invented probability — the
shock→beneficiary map is a standing house KILL (TI-R5, research/DO_NOT_REBUILD.md
§1: "laundered directional escalation on nulled continuation claims"), and an
LLM may not originate a signal or escalation (A7).

The law is honored MECHANICALLY, not by good intentions: every output item is
built by ``_project_event`` from the literal key set ``EVENT_FIELDS``. There is
no ``{**item}`` spread anywhere on the output path, so a field an upstream lane
adds later — even one literally named ``beneficiaries`` — cannot reach the model
without someone editing ``EVENT_FIELDS`` and tripping
tests/test_brain_market_intel.py.

FAIL-SOFT is the whole contract: a missing artifact, corrupt JSON, an
unexpected container shape, or an unparseable timestamp degrades to fewer
events (or none) with an honest ``note``. Neither function raises.

CLOCK
-----
Both functions take a keyword-only ``now`` for tests. The house has twice shipped
a scheduled CI red by aging fixtures against the wall clock instead of the
caller's instant (see scripts/marketing_fastlane_daemon._merge_wires_window), so
the suite freezes ``now`` and derives every fixture timestamp from it. No clock
reading is hashed or persisted here — these functions write nothing.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Output contract (TI-R5 whitelist)
# --------------------------------------------------------------------------- #
# The EXACT key set an event item may carry. `headline_zh` is the one optional
# member (emitted only when the upstream actually carries a translation — never
# an English string passed off as translated, which is the same honest-disclosure
# rule the news.html wire rail follows with its 英文原文 marker).
EVENT_FIELDS: tuple[str, ...] = (
    "ts",
    "headline",
    "headline_zh",
    "source",
    "salience",
    "corroboration",
    "source_kind",
)
# Required members: everything except the optional translation.
EVENT_FIELDS_REQUIRED: tuple[str, ...] = tuple(f for f in EVENT_FIELDS if f != "headline_zh")

# Bounds, mirrored in the tool schemas' descriptions so the model and the code
# cannot drift apart.
_WINDOW_MIN_H, _WINDOW_MAX_H, _WINDOW_DEFAULT_H = 1.0, 48.0, 12.0
_EVENTS_LIMIT_MIN, _EVENTS_LIMIT_MAX, _EVENTS_LIMIT_DEFAULT = 1, 10, 5
_RESEARCH_LIMIT_MIN, _RESEARCH_LIMIT_MAX, _RESEARCH_LIMIT_DEFAULT = 1, 8, 5

# Salience sentinel for items that carry none. Real desk salience is 0..100, so a
# negative floor sorts unscored items AFTER scored ones without ever inventing a
# number for them — the emitted `salience` stays None.
_NO_SALIENCE = -1.0

# Research scoring weights (deterministic; no embeddings, no network).
_W_TITLE, _W_SUMMARY, _W_INSTITUTION, _W_TOP_PICK = 3.0, 1.5, 2.0, 1.0
_RECENCY_HALF_LIFE_DAYS = 45.0
_RECENCY_FLOOR = 0.35
_SUMMARY_POINTS_KEPT = 4
_SUMMARY_POINT_MAX_CHARS = 220


# --------------------------------------------------------------------------- #
# Small fail-soft helpers
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    """Parse `path` as JSON, or return None. Never raises.

    Missing file, unreadable file, and invalid JSON collapse to the same answer
    on purpose: every caller here treats "no usable artifact" identically, and a
    retrieval tool that raised would take the whole chat turn down with it.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 — any read/parse failure degrades to None
        return None


def _parse_ts(raw) -> datetime | None:
    """Parse an ISO-8601-ish timestamp to an aware UTC datetime, else None.

    Handles the three forms the real artifacts use: "…Z" (wires.v1 updated_at
    and press published_at), "…+00:00" (site/news/*.json seendate), and a naive
    stamp (assumed UTC, matching every other reader in the repo). Anything else
    returns None and the caller SKIPS the item — an event with no trustworthy
    timestamp cannot be placed inside a freshness window, and guessing one would
    be inventing a fact.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp_int(raw, low: int, high: int, default: int) -> int:
    """Coerce `raw` to an int inside [low, high]; unusable input → `default`."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _clamp_float(raw, low: float, high: float, default: float) -> float:
    """Coerce `raw` to a float inside [low, high]; unusable input → `default`."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _first_text(item: dict, *keys: str) -> str | None:
    """First non-blank string value among `keys`, else None (no empty strings).

    None rather than "" because the two are different claims to the model:
    None reads as "we do not know the source", "" reads as "the source is blank".
    """
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _float_or_none(raw) -> float | None:
    """Coerce to float, or None. Used for desk scores that may be absent/null."""
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# FUNCTION 1 — live market events
# --------------------------------------------------------------------------- #
# Path ladder for the intraday wire, mirroring the precedents:
#   scripts/notify_turn_events.py:93          MACRO_LIVE_DIR overrides site/live
#   scripts/marketing_fastlane_daemon.py:555  VPS public live dir, dev-path fallback
# The daemon (a WRITER) picks the first candidate whose PARENT dir exists. A
# READER must not: on a dev box /var/lib/macro-live/public/live may exist and be
# empty while the dev sink under data/marketing/press/ holds the real window, so
# the first candidate whose FILE exists wins. A present-but-empty live dir
# therefore falls through instead of blanking the read.
_WIRES_BASENAME = "wires.json"
_VPS_LIVE_DIR = "/var/lib/macro-live/public/live"


def _wires_candidates(root: Path) -> list[Path]:
    """Ordered candidate paths for the wires.v1 payload (highest precedence first)."""
    candidates: list[Path] = []
    env_dir = os.environ.get("MACRO_LIVE_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / _WIRES_BASENAME)
    vps = Path(_VPS_LIVE_DIR)
    try:
        if vps.is_dir():
            candidates.append(vps / _WIRES_BASENAME)
    except OSError:
        pass  # unreadable mount point — skip the rung, never raise
    candidates.append(root / "site" / "live" / _WIRES_BASENAME)
    # Final rung: the daemon's gitignored dev sink (data/marketing/press/wires.json).
    candidates.append(root / "data" / "marketing" / "press" / _WIRES_BASENAME)
    return candidates


def _resolve_wires_path(root: Path) -> Path | None:
    """First candidate on the ladder whose file exists, else None."""
    for cand in _wires_candidates(root):
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def _wire_items(payload) -> list[dict]:
    """Extract the item list from a wires.v1 payload, defensively.

    Two shapes are accepted because both exist in the wild: the published
    payload is {"schema": "wires.v1", "updated_at": …, "items": [...]}, and an
    ad-hoc/dev file may be a bare top-level list. The schema string is NOT
    required to match — a reader that hard-failed on a schema bump would go dark
    on a rename, and every field access below is already defensive.
    """
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _dedupe_key(headline: str | None) -> str:
    """Normalised headline key for cross-source dedupe.

    Both wire text tails are stripped first. press_lane composes rail text as
    "<headline> -- <attribution> · <tape_stamp>", so the wire copy of a story and
    its nightly-digest twin share no prefix-free substring unless those tails
    come off — without this the merge would show the same story twice.
    """
    text = (headline or "").split(" -- ")[0].split(" · ")[0]
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _project_event(
    *,
    ts: datetime,
    headline: str,
    headline_zh: str | None,
    source: str | None,
    salience: float | None,
    corroboration: str | None,
    source_kind: str,
) -> dict:
    """Build ONE output event from the whitelisted fields only (TI-R5).

    Keyword-only and fully literal by design: there is no dict spread and no
    passthrough of the upstream item, so a field added upstream can never leak
    into the model's context. See this module's EPISTEMICS LAW docstring.
    """
    event = {
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": headline,
        "source": source,
        "salience": salience,
        "corroboration": corroboration,
        "source_kind": source_kind,
    }
    if headline_zh:
        event["headline_zh"] = headline_zh
    return event


def _collect_wire_events(root: Path, cutoff: datetime) -> list[tuple[float, datetime, dict, list]]:
    """Read the live wire and project its in-window items.

    Returns (salience_sort_value, ts, event, tickers) rows. The ticker list rides
    ALONGSIDE the projected event rather than inside it: `tickers` is not an
    output field (EVENT_FIELDS), but symbol matching needs it, so it is carried
    out-of-band and dropped before the return.

    SHAPE NOTE: the published rail item carries id/ts/class/label_en/label_zh/
    register/en/attribution/corroboration (+ optional zh, tape_stamp) — it does
    NOT carry `salience`, `source_name`, or `tickers`; those live on the scored
    upstream item inside the daemon. Every one of them is therefore read
    optionally: a wire with no salience simply ranks by recency.
    """
    path = _resolve_wires_path(root)
    if path is None:
        return []
    items = _wire_items(_read_json(path))
    out: list[tuple[float, datetime, dict, list]] = []
    for item in items:
        ts = _parse_ts(item.get("ts") or item.get("published_at"))
        if ts is None or ts < cutoff:
            continue  # unparseable or out of window
        headline = _first_text(item, "en", "headline", "text", "title")
        if not headline:
            continue  # nothing to show; a bodiless item is not an event
        salience = _float_or_none(item.get("salience"))
        # `corroboration` is the honest display chip ("verified" / "3 sources" /
        # "reports"); `corroboration_class` is the machine slug on the scored
        # item. Prefer the chip, fall back to the slug, else None.
        corroboration = _first_text(item, "corroboration", "corroboration_class")
        out.append((
            salience if salience is not None else _NO_SALIENCE,
            ts,
            _project_event(
                ts=ts,
                headline=headline,
                headline_zh=_first_text(item, "zh", "headline_zh", "title_zh"),
                # label_en is a desk CLASS ("Washington", "Companies"), never a
                # source, so it is deliberately not a fallback here. attribution
                # is the corroboration decision's source claim, which is.
                source=_first_text(item, "source_name", "domain", "source", "attribution"),
                salience=salience,
                corroboration=corroboration,
                source_kind="live_wire",
            ),
            item.get("tickers") if isinstance(item.get("tickers"), list) else [],
        ))
    return out


# Nightly digest containers. WHITELISTED rather than "every list-valued key":
# site/news/*.json also carry a `rejected` list (headlines the desk filtered
# OUT) that must never be presented as news.
_NIGHTLY_FILES = ("macro.json", "financial.json")
_NIGHTLY_LIST_KEYS = ("headlines", "market", "items")
_NIGHTLY_DICT_KEYS = ("by_ticker", "sectors", "mag7", "baskets")


def _nightly_candidate_items(payload) -> list[dict]:
    """Flatten a site/news/*.json payload into a flat list of headline dicts.

    macro.json keeps its items under `headlines`; financial.json keeps the broad
    tape under `market` plus dict-of-list buckets (`by_ticker`, `sectors`,
    `mag7`, `baskets`). Both are read; `rejected` never is.
    """
    if not isinstance(payload, dict):
        return [it for it in payload if isinstance(it, dict)] if isinstance(payload, list) else []
    items: list[dict] = []
    for key in _NIGHTLY_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(it for it in value if isinstance(it, dict))
    for key in _NIGHTLY_DICT_KEYS:
        bucket = payload.get(key)
        if not isinstance(bucket, dict):
            continue
        for value in bucket.values():
            if isinstance(value, list):
                items.extend(it for it in value if isinstance(it, dict))
    return items


def _collect_nightly_events(root: Path, cutoff: datetime) -> list[tuple[float, datetime, dict, list]]:
    """Project in-window items from the nightly news digests.

    SALIENCE NOTE: these are the NEWS desk's own scores (`importance_score`,
    `quality`, `rank_score` — all roughly 0..100), not press-lane salience. They
    are emitted because they are facts the desk computed, but nightly items are
    never sorted against wire items by them (see get_market_events).
    """
    out: list[tuple[float, datetime, dict, list]] = []
    for name in _NIGHTLY_FILES:
        payload = _read_json(root / "site" / "news" / name)
        if payload is None:
            continue
        for item in _nightly_candidate_items(payload):
            ts = _parse_ts(item.get("seendate") or item.get("published_at") or item.get("ts"))
            if ts is None or ts < cutoff:
                continue
            headline = _first_text(item, "title", "headline", "en")
            if not headline:
                continue
            salience = _float_or_none(
                item.get("importance_score")
                if item.get("importance_score") is not None
                else item.get("quality")
                if item.get("quality") is not None
                else item.get("rank_score")
            )
            out.append((
                salience if salience is not None else _NO_SALIENCE,
                ts,
                _project_event(
                    ts=ts,
                    headline=headline,
                    headline_zh=_first_text(item, "title_zh", "headline_zh", "zh"),
                    source=_first_text(item, "source_name", "domain", "source"),
                    salience=salience,
                    # The nightly digest carries no corroboration decision. None,
                    # never a manufactured "reports" chip.
                    corroboration=None,
                    source_kind="nightly",
                ),
                item.get("tickers") if isinstance(item.get("tickers"), list) else [],
            ))
    return out


def _rank(pool: list[tuple[float, datetime, dict, list]]) -> list[tuple[float, datetime, dict, list]]:
    """Sort one source pool by salience desc, then timestamp desc."""
    return sorted(pool, key=lambda row: (-row[0], -row[1].timestamp()))


def _symbol_matcher(symbol: str):
    """Return a predicate: does this item's text or ticker list mention `symbol`?

    Word-boundary matching so "C" does not hit "CPI" and "BA" does not hit
    "BABA". re.escape keeps exchange-qualified forms (600036.SH, BRK.B) literal.
    """
    needle = symbol.strip()
    pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])", re.IGNORECASE)

    def matches(item: dict, tickers) -> bool:
        if isinstance(tickers, (list, tuple)):
            for tick in tickers:
                if isinstance(tick, str) and tick.strip().upper() == needle.upper():
                    return True
        for key in ("headline", "headline_zh"):
            text = item.get(key)
            if isinstance(text, str) and pattern.search(text):
                return True
        return False

    return matches


def get_market_events(
    root: Path,
    window_h: float = _WINDOW_DEFAULT_H,
    limit: int = _EVENTS_LIMIT_DEFAULT,
    symbol: str | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """Fresh market events — FACTS ONLY (timestamps, headlines, source, salience).

    Sources, tried in order and merged (deduped by id-normalised headline):
      1. The intraday press wire (wires.v1) resolved off the MACRO_LIVE_DIR →
         VPS live dir → site/live → data/marketing/press ladder.
      2. The nightly news digests (site/news/macro.json, site/news/financial.json),
         used ONLY to top up when the wire yields fewer than `limit`.

    Ordering is SOURCE-MAJOR: wire events first (ranked among themselves by
    salience desc then ts desc), then nightly top-ups (ranked the same way).
    The two pools are never sorted against each other, because their scores are
    not the same quantity — press salience and the news desk's importance/quality
    scores share a 0..100 range and nothing else, so a cross-pool comparison
    would be a fabricated ranking. Source-major ordering is also exactly what
    "nightly only tops up" means.

    `symbol` PREFERS matching items (ticker list or word-boundary text hit) and
    then backfills with general items to reach `limit` — a quiet ticker returns
    the broad tape rather than an empty answer.

    EPISTEMICS (TI-R5): the returned events carry only the keys in EVENT_FIELDS.
    No predicted effect, no beneficiary/casualty list, no invented probability —
    not even if an upstream lane starts publishing them. See the module docstring.

    Returns {"asof", "window_h", "events", "note"}. Never raises; a dead artifact
    degrades to fewer events and an honest note.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    window = _clamp_float(window_h, _WINDOW_MIN_H, _WINDOW_MAX_H, _WINDOW_DEFAULT_H)
    cap = _clamp_int(limit, _EVENTS_LIMIT_MIN, _EVENTS_LIMIT_MAX, _EVENTS_LIMIT_DEFAULT)
    cutoff = reference - timedelta(hours=window)

    try:
        wire_pool = _rank(_collect_wire_events(root, cutoff))
    except Exception:  # noqa: BLE001 — retrieval must not take the turn down
        wire_pool = []

    matches = _symbol_matcher(symbol) if isinstance(symbol, str) and symbol.strip() else None

    # Dedupe as we select, wire copy winning: it carries the desk's composed text,
    # its corroboration chip, and any zh twin we already paid for.
    seen: set[str] = set()
    selected: list[tuple[dict, bool]] = []  # (event, is_symbol_match)

    def _absorb(pool: list[tuple[float, datetime, dict, list]]) -> None:
        for _sal, _ts, event, tickers in pool:
            key = _dedupe_key(event.get("headline"))
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            selected.append((event, bool(matches(event, tickers)) if matches else False))

    _absorb(wire_pool)

    # Nightly is a TOP-UP only: read it when the wire could not fill the cap.
    # `symbol` widens what "fill" means — a ticker-specific ask wants the ticker's
    # own items, so top up whenever the wire's MATCHING set is short, even if the
    # wire filled the cap with general items.
    filled = sum(1 for _e, hit in selected if hit) if matches else len(selected)
    if filled < cap:
        try:
            _absorb(_rank(_collect_nightly_events(root, cutoff)))
        except Exception:  # noqa: BLE001
            pass

    if matches is not None:
        # Symbol-matching items keep their pool order and come first; general
        # items backfill to `cap`, so a quiet ticker returns the broad tape
        # instead of an empty answer.
        events = [e for e, hit in selected if hit] + [e for e, hit in selected if not hit]
    else:
        events = [e for e, _hit in selected]

    events = events[:cap]

    if not events:
        note = "no fresh events in window"
    elif any(e.get("source_kind") == "live_wire" for e in events):
        note = "live wire"
    else:
        note = "nightly digest only"

    return {
        "asof": reference.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_h": window,
        "events": events,
        "note": note,
    }


# --------------------------------------------------------------------------- #
# FUNCTION 2 — research-vault search
# --------------------------------------------------------------------------- #
_CATALOG_REL = ("data", "research_vault", "catalog.json")

# Alnum word tokens, ≥2 chars. Applied to the lowercased query and to the
# lowercased haystack so both sides tokenise identically.
_WORD_RE = re.compile(r"[a-z0-9]{2,}")
# A raw whitespace token containing a dot or a digit is kept AS-IS as well:
# splitting on non-alnum would shred exchange-qualified tickers (600036.SH →
# "600036" + "sh") and lose the qualified form the catalog may carry verbatim.
_QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z0-9]$")


def _tokenize(query: str) -> tuple[str, ...]:
    """Query → ordered, de-duplicated lowercase match tokens.

    De-duplicated because the score counts DISTINCT token hits per field: a
    query that repeats a word must not buy that word a double weight.
    """
    text = str(query or "")
    tokens: list[str] = []
    for raw in text.split():
        stripped = raw.strip().strip(",;:!?\"'()[]")
        if ("." in stripped or any(ch.isdigit() for ch in stripped)) and _QUALIFIED_RE.match(stripped):
            lowered = stripped.lower()
            if len(lowered) >= 2 and lowered not in tokens:
                tokens.append(lowered)
    for word in _WORD_RE.findall(text.lower()):
        if word not in tokens:
            tokens.append(word)
    return tuple(tokens)


def _hits(tokens: tuple[str, ...], haystack: str) -> int:
    """Count DISTINCT tokens appearing as words in `haystack` (already lowercased)."""
    if not haystack:
        return 0
    words = set(_WORD_RE.findall(haystack))
    count = 0
    for token in tokens:
        # A qualified token ("600036.sh") survives tokenisation of the haystack
        # only as fragments, so fall back to a substring test for those.
        if token in words or ("." in token and token in haystack):
            count += 1
    return count


def _recency_factor(published_at, now: datetime) -> float:
    """max(0.35, 1 - age_days/45); an unparseable/absent date takes the floor.

    The floor, not 1.0: an item whose date we cannot read has not earned a
    freshness premium, and giving it one would let undated rows crowd out dated
    ones on every query.
    """
    ts = _parse_ts(published_at)
    if ts is None:
        return _RECENCY_FLOOR
    age_days = (now - ts).total_seconds() / 86400.0
    if age_days < 0:
        age_days = 0.0  # a future stamp is clock skew, not extra freshness
    return max(_RECENCY_FLOOR, 1.0 - age_days / _RECENCY_HALF_LIFE_DAYS)


def _truncate(text: str) -> str:
    """Clamp one summary point to _SUMMARY_POINT_MAX_CHARS, ellipsis included.

    The budget covers the ellipsis, so the returned string is never longer than
    the documented cap — a "220 + 1" result would break any caller sizing a
    context window off this number.
    """
    clean = " ".join(str(text or "").split())
    if len(clean) <= _SUMMARY_POINT_MAX_CHARS:
        return clean
    return clean[: _SUMMARY_POINT_MAX_CHARS - 1] + "…"


def _catalog_items(root: Path) -> list[dict] | None:
    """Read research_vault.catalog.v1 items, or None when unavailable.

    None (not []) distinguishes "vault missing/corrupt" — which the caller
    reports honestly — from "vault present, nothing matched".
    """
    payload = _read_json(root.joinpath(*_CATALOG_REL))
    if payload is None:
        return None
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return None
    return [it for it in items if isinstance(it, dict)]


def search_research(
    root: Path,
    query: str,
    limit: int = _RESEARCH_LIMIT_DEFAULT,
    *,
    now: datetime | None = None,
) -> dict:
    """Keyword-search the research vault — THIRD-PARTY views, not the desk's own.

    Deterministic and offline: no embeddings, no network, no LLM. Per item,
        score = (3.0 × distinct title hits)
              + (1.5 × distinct summary hits)
              + (2.0 × distinct institution word hits)
              + (1.0 if top_pick)
        score × max(0.35, 1 - age_days/45)

    The top_pick bonus only applies to an item that already matched something —
    it is a tiebreak among relevant research, not a free pass into every result
    set. `tags`/`tickers` are empty across the committed catalog today, so they
    are deliberately not scored; title, summary_points, and institution are.

    A query of fewer than 2 tokens returns no results ("query too short"): one
    bare word against 346 institutional notes ranks essentially by recency and
    would read as a search that worked. A missing or corrupt catalog returns
    "research vault unavailable". Never raises.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    cap = _clamp_int(limit, _RESEARCH_LIMIT_MIN, _RESEARCH_LIMIT_MAX, _RESEARCH_LIMIT_DEFAULT)
    note = (
        "institutional research summaries — third-party views, "
        "not the desk's own signals"
    )
    tokens = _tokenize(query)
    if len(tokens) < 2:
        return {"query": str(query or ""), "results": [], "count_scanned": 0,
                "note": "query too short"}

    try:
        items = _catalog_items(root)
    except Exception:  # noqa: BLE001
        items = None
    if items is None:
        return {"query": str(query or ""), "results": [], "count_scanned": 0,
                "note": "research vault unavailable"}

    scored: list[tuple[float, str, str, dict]] = []
    for item in items:
        title = str(item.get("title") or "")
        points = item.get("summary_points")
        points = [str(p) for p in points if isinstance(p, str)] if isinstance(points, list) else []
        institution = str(item.get("institution") or "")

        title_hits = _hits(tokens, title.lower())
        summary_hits = _hits(tokens, " ".join(points).lower())
        institution_hits = _hits(tokens, institution.lower())
        if not (title_hits or summary_hits or institution_hits):
            continue  # no textual relevance — top_pick alone never admits an item

        raw = (
            _W_TITLE * title_hits
            + _W_SUMMARY * summary_hits
            + _W_INSTITUTION * institution_hits
            + (_W_TOP_PICK if item.get("top_pick") else 0.0)
        )
        published_at = item.get("published_at")
        score = raw * _recency_factor(published_at, reference)
        if score <= 0:
            continue
        # Tie-break on published_at then id so the ordering is stable across runs
        # (a catalog rebuild reorders `items`, and an unstable top-5 would make
        # the tool look like it changed its mind).
        scored.append((score, str(published_at or ""), str(item.get("id") or ""), item))

    # Score descending; among ties the NEWEST note first, then id for a total
    # order. `_neg_str_key` inverts the ISO date because Python cannot negate a
    # str — a plain ascending sort would surface the oldest tied note.
    scored.sort(key=lambda row: (-row[0], _neg_str_key(row[1]), row[2]))

    results = []
    for _score, _pub, _iid, item in scored[:cap]:
        points = item.get("summary_points")
        points = [p for p in points if isinstance(p, str)] if isinstance(points, list) else []
        results.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "institution": item.get("institution"),
            "side": item.get("side"),
            "published_at": item.get("published_at"),
            "summary_points": [_truncate(p) for p in points[:_SUMMARY_POINTS_KEPT]],
            "top_pick": bool(item.get("top_pick")),
        })

    return {
        "query": str(query or ""),
        "results": results,
        "count_scanned": len(items),
        "note": note,
    }


def _neg_str_key(text: str) -> tuple:
    """Descending sort key for an ISO date string used as a tie-break.

    Python cannot negate a str, so invert each codepoint. Only ever applied to
    ISO-8601 stamps, where lexical order IS chronological order.
    """
    return tuple(-ord(ch) for ch in text)


# --------------------------------------------------------------------------- #
# Anthropic tool schemas (shape mirrors brain_gateway._brain_tool_schemas)
# --------------------------------------------------------------------------- #
EVENTS_TOOL_SCHEMA: dict = {
    "name": "get_market_events",
    "description": (
        "Read the desk's fresh market-events feed: the intraday press wire, "
        "topped up from the nightly news digests when the wire is thin. Call for "
        "any question about today's or current news, catalysts, 'why is the "
        "market moving', 'what happened', breaking developments, or what is "
        "driving a ticker right now. Returns FACTS ONLY — timestamp, headline "
        "(EN and ZH where translated), source, desk-computed salience, and a "
        "corroboration chip ('verified', 'N sources', 'reports'). It returns no "
        "predicted effects and no beneficiary or casualty lists; draw any market "
        "read yourself from the engine's own signal tools, and never present a "
        "single-source 'reports' item as confirmed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "window_h": {
                "type": "number",
                "description": "Look-back window in hours (1..48, default 12)",
            },
            "limit": {
                "type": "integer",
                "description": "Max events to return (1..10, default 5)",
            },
            "symbol": {
                "type": "string",
                "description": (
                    "Prefer events mentioning this ticker (e.g. 'NVDA'); general "
                    "events backfill to the limit. Optional."
                ),
            },
        },
        "required": [],
    },
}

RESEARCH_TOOL_SCHEMA: dict = {
    "name": "search_research",
    "description": (
        "Search the research vault of institutional sell-side and buy-side notes "
        "by keyword. Call when the user asks what analysts, institutions, banks, "
        "or the street think, wants research on a theme or ticker, or asks for a "
        "second opinion beside the desk's own signals. Returns third-party "
        "institutional research summaries — attribute every view to its "
        "institution ('Goldman Sachs writes…'), never present one as the desk's "
        "own read, and say plainly when a note disagrees with the engine."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search terms — theme, ticker, or institution (needs at "
                    "least 2 words, e.g. 'hedge fund momentum', 'NVDA capex')"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (1..8, default 5)",
            },
        },
        "required": ["query"],
    },
}
