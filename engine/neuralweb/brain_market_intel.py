"""engine.neuralweb.brain_market_intel — Mastermind retrieval: live events + research.

CLASSIFICATION: read-only retrieval helpers for the Mastermind brain gateway.
This module holds the FUNCTIONS and their Anthropic tool schemas only; the
gateway owns dispatch, the tool allowlist, and tier gating. Nothing here is
imported by the nightly or calls an LLM.

TIER: display/context — READ-ONLY. Never computes a signal, score, rank, size,
or gate. Every function is a pure read over artifacts other lanes publish.

TWO EXCEPTIONS, both belonging to mode="report" (W4) and to nothing else: it
reads the R2-backed corpus (so a cold process may pay ONE download through the
shared reader in research_vault.corpus) and it debits the hourly view ledger
(one small JSON file per user per hour, via research_vault.view_ratelimit). No
other path here touches a socket or writes a byte.

PUBLIC API
----------
get_market_events(root, window_h=12.0, limit=5, symbol=None) -> dict
    Fresh market events, merged from the intraday press wire (wires.v1) and
    topped up from the nightly news digests when the wire is thin. The wire pool
    is permuted by the desk's ranked-wire sidecar when a fresh one is published
    (W2 — see the _WIRE_RANK_BASENAME block); recency otherwise.

search_research(root, query, limit=5, mode="search", report_id="",
                user_ctx=None) -> dict
    mode="search"   — deterministic keyword search over the committed
                      research-vault catalog (third-party institutional
                      summaries — never the desk's own signals).
    mode="clusters" — street-convergence view of the SAME catalog: which themes
                      N>=3 fresh notes from >=2 institutions are all writing
                      about. A retrieval summary, never consensus-as-authority.
    mode="report"   — ONE report by id: catalog metadata + the PUBLIC excerpt +
                      a capped slice of the stored body. PRO-only (operator
                      ruling 2026-07-31) and metered — see the FUNCTION 2c block
                      for the rights reasoning and the caps.

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

# --- ranked-wire sidecar (W2) ---------------------------------------------- #
# The public rail carries NO salience, by the news desk's ruling: internal
# ranking numbers never ride a user-fetchable payload (their leak law, 2026-07-30,
# Intelligence Desk V2 lane). So the desk's ordering arrives out-of-band, on a
# NON-public STATE path, as a list of ids in best-first order:
#
#   {"schema": "wire_rank.v1", "updated_at": "<ISO>", "ids": ["<id>", ...]}
#
# Ordering by POSITION, with deliberately no numbers at all: there is no score to
# leak, nothing to quote back, and nothing an LLM could re-present as a desk
# probability. The effect here is a permutation of the wire pool and NOTHING else
# — EVENT_FIELDS is unchanged, so no sidecar value can reach the model's context.
# This module never writes the file.
_WIRE_RANK_BASENAME = "wire_rank.json"
_VPS_STATE_DIR = "/var/lib/macro-live/state"
# Older than this and the ranking is ignored: a wire window turns over in
# minutes, so a stale ordering is worse than honest recency (it would pin an hour-
# old lead story to the top of a fresh tape).
_WIRE_RANK_MAX_AGE_MIN = 45.0


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


def _wire_rank_candidates(root: Path) -> list[Path]:
    """Ordered candidate paths for the ranked-wire sidecar (highest first).

    Mirrors the wires ladder but on the STATE dir, not the PUBLIC live dir —
    that separation is the whole point of the sidecar (see the block comment
    above). MACRO_LIVE_STATE_DIR is the deployed override
    (app/deploy/live-setup.sh:80, scripts/vps_live_orchestrator.py:459).
    """
    candidates: list[Path] = []
    env_dir = os.environ.get("MACRO_LIVE_STATE_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / _WIRE_RANK_BASENAME)
    state = Path(_VPS_STATE_DIR)
    try:
        if state.is_dir():
            candidates.append(state / _WIRE_RANK_BASENAME)
    except OSError:
        pass  # unreadable mount point — skip the rung, never raise
    # Dev sink: the same gitignored directory the fastlane daemon writes wires to.
    candidates.append(root / "data" / "marketing" / "press" / _WIRE_RANK_BASENAME)
    return candidates


def _resolve_wire_rank_path(root: Path) -> Path | None:
    """First sidecar candidate whose FILE exists, else None.

    File-exists (not dir-exists), same as _resolve_wires_path: on a dev box the
    state dir can exist and be empty while the dev sink holds the real file.
    """
    for cand in _wire_rank_candidates(root):
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def _wire_rank_order(root: Path, now: datetime) -> dict[str, int] | None:
    """{wire item id: position} from a FRESH sidecar, else None.

    None — meaning "fall back to the honest recency order" — for every degraded
    case: no file, corrupt JSON, no `ids` list, an unparseable `updated_at`, or a
    stamp older than _WIRE_RANK_MAX_AGE_MIN.

    An unparseable/absent stamp is treated as unusable rather than fresh: a
    ranking whose age cannot be established cannot be shown to be current, and
    assuming freshness is how a dead daemon's last ordering outlives it. A
    FUTURE stamp is clock skew, not staleness, so it passes (the same rule
    _recency_factor applies to research dates).

    The schema string is checked loosely, matching _wire_items: a reader that
    hard-failed on a rename would go dark on a schema bump, and every field
    access here is already defensive.
    """
    path = _resolve_wire_rank_path(root)
    if path is None:
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    stamp = _parse_ts(payload.get("updated_at"))
    if stamp is None:
        return None
    age_min = (now - stamp).total_seconds() / 60.0
    if age_min > _WIRE_RANK_MAX_AGE_MIN:
        return None
    ids = payload.get("ids")
    if not isinstance(ids, list):
        return None
    order: dict[str, int] = {}
    for pos, raw in enumerate(ids):
        if not isinstance(raw, str):
            continue
        key = raw.strip()
        if key and key not in order:  # first position wins on a duplicated id
            order[key] = pos
    return order or None


def _apply_wire_rank(
    pool: list[tuple[float, datetime, dict, list, str | None]],
    order: dict[str, int] | None,
) -> list[tuple[float, datetime, dict, list, str | None]]:
    """Reorder the wire pool by sidecar position; unranked items keep their order.

    Stable-sorted on position with a +inf default, so items the sidecar does not
    name retain the salience/recency order `_rank` gave them and land AFTER every
    ranked one. Nothing about the events themselves changes — this is a
    permutation, which is why no output field had to be added.
    """
    if not order:
        return pool
    return sorted(pool, key=lambda row: order.get(row[4] or "", float("inf")))


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


def _collect_wire_events(root: Path, cutoff: datetime) -> list[tuple[float, datetime, dict, list, str | None]]:
    """Read the live wire and project its in-window items.

    Returns (salience_sort_value, ts, event, tickers, item_id) rows. The ticker
    list and the id ride ALONGSIDE the projected event rather than inside it:
    neither is an output field (EVENT_FIELDS), but symbol matching needs the
    tickers and the ranked sidecar needs the id, so both are carried out-of-band
    and dropped before the return.

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
    out: list[tuple[float, datetime, dict, list, str | None]] = []
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
            _first_text(item, "id"),
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


def _collect_nightly_events(root: Path, cutoff: datetime) -> list[tuple[float, datetime, dict, list, str | None]]:
    """Project in-window items from the nightly news digests.

    Same row shape as _collect_wire_events so one `_rank`/`_absorb` serves both.
    The trailing id is always None here: the ranked sidecar covers the WIRE pool
    only — the desk ranks the intraday tape, not last night's digest.

    SALIENCE NOTE: these are the NEWS desk's own scores (`importance_score`,
    `quality`, `rank_score` — all roughly 0..100), not press-lane salience. They
    are emitted because they are facts the desk computed, but nightly items are
    never sorted against wire items by them (see get_market_events).
    """
    out: list[tuple[float, datetime, dict, list, str | None]] = []
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
                None,
            ))
    return out


def _rank(
    pool: list[tuple[float, datetime, dict, list, str | None]],
) -> list[tuple[float, datetime, dict, list, str | None]]:
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
    salience desc then ts desc, then permuted by the ranked-wire sidecar when a
    fresh one exists), then nightly top-ups (ranked the same way).
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
        # The desk's own ordering, when a fresh non-public sidecar publishes one;
        # otherwise the recency order above stands (see _wire_rank_order).
        wire_pool = _apply_wire_rank(wire_pool, _wire_rank_order(root, reference))
    except Exception:  # noqa: BLE001 — retrieval must not take the turn down
        wire_pool = []

    matches = _symbol_matcher(symbol) if isinstance(symbol, str) and symbol.strip() else None

    # Dedupe as we select, wire copy winning: it carries the desk's composed text,
    # its corroboration chip, and any zh twin we already paid for.
    seen: set[str] = set()
    selected: list[tuple[dict, bool]] = []  # (event, is_symbol_match)

    def _absorb(pool: list[tuple[float, datetime, dict, list, str | None]]) -> None:
        for _sal, _ts, event, tickers, _iid in pool:
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


# --------------------------------------------------------------------------- #
# FUNCTION 2b — street clusters (W2): what is the street all writing about?
# --------------------------------------------------------------------------- #
# WHAT THE CATALOG ACTUALLY GIVES US (recon, 2026-07-30, 374 items, ~7d window):
# `institution` is filled 374/374 across 28 distinct houses, and `side` splits
# sell 319 / independent 55. `desk`, `tags` and `tickers` are filled 0/374 —
# DEAD FIELDS. So convergence is read off text + institution, and nothing here
# touches tags/tickers: a theme keyed on an always-empty field would return zero
# clusters forever and read as "the street agrees on nothing". Deterministic and
# offline throughout — no embeddings, no LLM, no network.
#
# WHY THEMES ARE ANCHORED ON TERMS, AND ON THE TITLE (measured, not assumed)
# -------------------------------------------------------------------------
# The obvious build — bag-of-words over title+summary, greedy document
# clustering, join on Jaccard>=0.3 or >=2 shared tokens — was implemented first
# and MEASURED against the real catalog. It fabricates convergence:
#
#   * Top cluster: 51 reports / 14 houses labelled "hike fed rate", whose members
#     were "US EQUITIES COLOR PRESSER PRESSURE", "In Credit 27 07 2026" and
#     "Chile MPC Keeps Policy Rate at 4.5" — nothing in common.
#   * Second: 22 reports / 8 houses labelled "global policy data", members
#     "Qualcomm First Take", "CBRE 2Q26", "Pi gev 3q26".
#
# The cause is structural, not a tuning miss. Half this catalog is MULTI-TOPIC
# daily briefings ("GS MORNING 1 Oil Tracker, 2 USDJPY Topside, 3 Korea Update,
# 4 ..."), whose token bags span the whole macro universe. Each one is a hub that
# chains unrelated notes into one blob, and tightening the distinctiveness of the
# shared tokens (swept at 2/4/6/8% document frequency) never separates them.
# Reporting that as "14 houses are converging" would be a manufactured consensus
# claim — the exact laundered-escalation failure TI-R5 exists to stop.
#
# So a theme is a TERM plus the notes whose OWN TITLE names it. A title is the
# note's declaration of its subject; a mention buried in an omnibus briefing's
# bullets is not. That makes the emitted claim literally checkable — "11 notes
# from 6 houses have 'oil' in the title" — instead of an unfalsifiable grouping.
# Adding the summariser's bolded bullet headers as a second membership signal was
# tried too and rejected: recall rose but "geopolitical" then swept in "Ford
# Motor July 29", because an omnibus note's headers span everything its bullets
# do. Measured output of the shipped version: credit 10 reports/8 houses,
# europe 12/6, oil 11/6, iran 6/6, china 19/5, earnings 11/5 — every member's
# title genuinely names its theme.
#
# A term must start with a LETTER and run >=3 chars. That one rule drops the
# measurement noise this catalog is full of ("152bps", "2q26", "500") while
# keeping subject words that carry a digit ("mag7").
_CLUSTER_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")

# Grammar words, report FURNITURE, and calendar words — the vocabulary of a
# note's packaging rather than its subject. Frozen and hand-checked against the
# real titles: "JPM GLOBAL MARKET INTELLIGENCE" and "DB Research Europe" are
# recurring PUBLICATION SERIES names, so market/global/research/intelligence must
# not become themes. "The street is focused on: market" is also exactly the vague
# glance-tier copy the design doctrine bans.
_CLUSTER_STOPWORDS: frozenset[str] = frozenset({
    # grammar / connective
    "and", "the", "for", "with", "from", "that", "this", "will", "has", "have",
    "are", "but", "not", "its", "was", "were", "been", "into", "over", "more",
    "less", "than", "per", "all", "any", "out", "our", "their", "they", "them",
    "what", "when", "where", "which", "while", "also", "may", "can", "could",
    "would", "should", "still", "after", "before", "amid", "amidst", "versus",
    "vs", "about", "above", "below", "between", "both", "each", "other",
    "others", "some", "such", "only", "own", "same", "too", "very", "just",
    "now", "one", "two", "three", "new", "near", "next", "last", "most",
    "much", "many", "due", "despite", "since", "until", "again", "off", "via",
    "without", "within", "across", "against", "along", "among", "around",
    "because", "being", "does", "doing", "done", "during", "further",
    "however", "itself", "made", "make", "making", "need", "needs", "once",
    "said", "says", "see", "seen", "set", "sets", "show", "shows", "thus",
    "toward", "towards", "use", "used", "using", "whether", "though",
    "although", "either", "neither", "yet", "already", "onto", "under", "upon",
    "here", "there", "then", "who", "whom", "how", "why",
    # report furniture / recurring publication-series words
    "report", "reports", "update", "updates", "note", "notes", "weekly",
    "monthly", "daily", "quarterly", "preview", "review", "first", "second",
    "third", "take", "takes", "group", "inc", "corp", "ltd", "plc", "llc",
    "research", "comment", "comments", "commentary", "color", "colour",
    "morning", "afternoon", "evening", "midday", "overnight", "summary",
    "brief", "briefing", "briefings", "desk", "recap", "wrap", "edition",
    "deck", "chart", "charts", "table", "exhibit", "appendix", "page", "pages",
    "key", "focus", "thoughts", "views", "view", "read", "reading", "insight",
    "insights", "idea", "ideas", "call", "calls", "week", "month", "year",
    "quarter", "today", "yesterday", "session", "meeting", "market", "markets",
    "global", "macro", "equity", "equities", "intelligence", "intell",
    "strategy", "strategies", "thematic", "think", "point", "talk", "tracker",
    "navigator", "kickstart", "analyst", "economics", "outlook",
    # calendar
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "monday",
    "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
})

# A term in more than a quarter of the window's notes is the week's WEATHER, not
# a theme worth naming: it has no discriminating power and its "N houses wrote
# about it" reads as convergence when it is just vocabulary.
_CLUSTER_DF_CEILING = 0.25
# Two terms whose supporting note sets overlap this much are one theme said two
# ways ("oil"/"crude"); merging on the DOCUMENT sets rather than on token
# similarity is what keeps an omnibus note from chaining themes together.
_CLUSTER_MERGE_JACCARD = 0.5
_CLUSTER_THEME_TERMS = 3         # words in the emitted theme label
_CLUSTER_REPORTS_SHOWN = 3       # newest N reports listed per theme
_CLUSTER_SCAN_CAP = 800          # bounds the walk on a runaway catalog

_CLUSTERS_SCHEMA = "brain.research_clusters.v1"
_CLUSTERS_NOTE = (
    "Convergence is a retrieval summary of what the street is writing about — "
    "not a view, not consensus-as-authority."
)

_MODE_SEARCH, _MODE_CLUSTERS, _MODE_REPORT = "search", "clusters", "report"


def _is_mode(mode, wanted: str) -> bool:
    """True only for an explicit request for `wanted`; anything else searches.

    Lenient on the way in (case, whitespace, a non-string the model invented) and
    strict about the DEFAULT: an unrecognised mode runs the search it always did
    rather than erroring, because the gateway hands model arguments straight
    through and a typo must not cost the user his answer.
    """
    return isinstance(mode, str) and mode.strip().lower() == wanted


def _is_clusters_mode(mode) -> bool:
    """True only for an explicit clusters request (see :func:`_is_mode`)."""
    return _is_mode(mode, _MODE_CLUSTERS)


def _is_report_mode(mode) -> bool:
    """True only for an explicit report request (see :func:`_is_mode`)."""
    return _is_mode(mode, _MODE_REPORT)


def _cluster_tokens(item: dict) -> frozenset[str]:
    """The note's OWN declared subject: filtered tokens of its title.

    Title only — see the block comment above for the measured reason. Markdown
    needs no stripping pass: a token regex anchored on a letter run drops
    asterisks, colons and dashes by itself.
    """
    text = str(item.get("title") or "").lower()
    return frozenset(
        t for t in _CLUSTER_TOKEN_RE.findall(text) if t not in _CLUSTER_STOPWORDS
    )


def _cluster_sort_key(item: dict) -> tuple:
    """Newest-first ordering key, total and stable.

    A note with no readable date sorts LAST rather than first, and `id` closes
    the order so a catalog rebuild cannot reshuffle the output.
    """
    ts = _parse_ts(item.get("published_at"))
    return (ts is None, -ts.timestamp() if ts is not None else 0.0,
            str(item.get("id") or ""))


def _research_clusters(
    items: list[dict],
    *,
    now: datetime,
    min_reports: int = 3,
    min_institutions: int = 2,
    max_clusters: int = 5,
) -> dict:
    """Themes several houses are writing about at once. Deterministic; never raises.

    A theme is a subject TERM plus every note whose title names it. Terms whose
    supporting note sets overlap by >=_CLUSTER_MERGE_JACCARD are folded together
    so one subject said two ways lands once, and the label keeps up to
    _CLUSTER_THEME_TERMS of them.

    A theme is only REPORTED when >=min_reports notes from >=min_institutions
    distinct houses carry it. One house publishing three notes on its own idea is
    not the street converging — it is one desk repeating itself, and the
    institution count is the only thing that separates the two.

    Empty is an honest answer: `clusters: []` means nothing cleared the bar, not
    that the read failed.
    """
    rows: list[tuple[tuple, dict, frozenset[str]]] = []
    for item in items:
        tokens = _cluster_tokens(item)
        if tokens:
            rows.append((_cluster_sort_key(item), item, tokens))
    # Sort BEFORE the cap: `items` arrives in whatever order the catalog builder
    # wrote it, which is not guaranteed to be chronological, so capping the raw
    # list could silently drop the NEWEST notes on a large vintage. Newest-first
    # then truncate keeps the cap a bound on cost, not a bias in what is read.
    rows.sort(key=lambda row: row[0])
    del rows[_CLUSTER_SCAN_CAP:]
    scanned = len(rows)

    # term -> the set of note indices whose title carries it
    support: dict[str, set[int]] = {}
    for index, (_key, _item, tokens) in enumerate(rows):
        for token in tokens:
            support.setdefault(token, set()).add(index)

    floor = max(1, int(min_reports))
    # The ambient ceiling can never fall BELOW the admission floor: on a small
    # catalog a quarter of the notes is fewer than min_reports, so a scaled-only
    # ceiling would classify every shared term as ambient and report nothing —
    # silently, and only on small inputs. max() keeps the floor always reachable
    # and needs no magic minimum-N cliff.
    ceiling = max(scanned * _CLUSTER_DF_CEILING, float(floor))
    candidates = sorted(
        ((len(docs), term) for term, docs in support.items()
         if floor <= len(docs) <= ceiling),
        # Commonest term first, alphabetical among equals: a total order, so the
        # same catalog always folds into the same themes.
        key=lambda row: (-row[0], row[1]),
    )

    themes: list[dict] = []
    for _count, term in candidates:
        docs = support[term]
        for theme in themes:
            union = len(docs | theme["docs"])
            if union and len(docs & theme["docs"]) / union >= _CLUSTER_MERGE_JACCARD:
                theme["terms"].append(term)
                theme["docs"] |= docs
                break
        else:
            themes.append({"terms": [term], "docs": set(docs)})

    reported: list[tuple[tuple, dict]] = []
    for theme in themes:
        members = [rows[i][1] for i in sorted(theme["docs"])]
        institutions = sorted({
            inst for inst in (_first_text(m, "institution") for m in members) if inst
        })
        if len(members) < min_reports or len(institutions) < min_institutions:
            continue
        reported.append(_cluster_projection(theme["terms"], members, institutions))

    # n_institutions desc, n_reports desc, newest first, theme — a total order.
    reported.sort(key=lambda row: row[0])
    return {
        "schema": _CLUSTERS_SCHEMA,
        "asof": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count_scanned": scanned,
        "clusters": [payload for _key, payload in reported[:max(1, int(max_clusters))]],
        "note": _CLUSTERS_NOTE,
    }


def _cluster_projection(terms: list[str], members: list[dict],
                        institutions: list[str]) -> tuple[tuple, dict]:
    """(sort_key, output theme). Literal fields only — no score, no confidence.

    `window_days` is the theme's OWN span, oldest to newest report: "6 houses
    inside 1.7 days" and "6 houses across a fortnight" are different facts about
    convergence, and the catalog's rolling window cannot express either.
    """
    theme = " ".join(terms[:_CLUSTER_THEME_TERMS])
    stamps = [s for s in (_parse_ts(m.get("published_at")) for m in members)
              if s is not None]
    window_days = (round((max(stamps) - min(stamps)).total_seconds() / 86400.0, 1)
                   if len(stamps) > 1 else 0.0)
    newest = max(str(m.get("published_at") or "") for m in members)
    shown = sorted(members, key=_cluster_sort_key)[:_CLUSTER_REPORTS_SHOWN]
    payload = {
        "theme": theme,
        "n_reports": len(members),
        "n_institutions": len(institutions),
        "institutions": institutions,
        "window_days": window_days,
        "top_pick_count": sum(1 for m in members if m.get("top_pick")),
        "reports": [{
            "id": m.get("id"),
            "title": m.get("title"),
            "institution": m.get("institution"),
            "published_at": m.get("published_at"),
        } for m in shown],
    }
    sort_key = (-len(institutions), -len(members), _neg_str_key(newest), theme)
    return sort_key, payload


# --------------------------------------------------------------------------- #
# FUNCTION 2c — full-report escalation (W4): ONE report, its fuller content
# --------------------------------------------------------------------------- #
# OPERATOR RULING (2026-07-31): the vault's full-report escalation is APPROVED
# for PRO members in chat. What that does and does not license:
#
#   * The material is a THIRD PARTY's copyrighted research. engine/research_vault/
#     excerpt.py frames its own caps as "the entire risk surface … an OPERATOR
#     decision, never a builder default"; the same rule governs here. The chat
#     exposure cap is _REPORT_BODY_MAX_CHARS (12,000 chars) — thesis plus core
#     argument, deliberately far under the 60,000 the corpus stores. Raising it is
#     an operator decision, not a tuning knob.
#   * The rights line rides in the payload `note` — the chat equivalent of the
#     watermark app/research.py stamps into a downloaded PDF. It is addressed to
#     the model because the model is what renders the answer: attribute, quote
#     sparingly, synthesize, never reproduce pages.
#   * TIER is the GATEWAY's job (Pro-only for this mode; insider keeps search and
#     clusters). This function still fails CLOSED on a missing `user_ctx`: a call
#     with no identity cannot be metered, and an unmeterable serve of third-party
#     research is exactly what the cap exists to prevent.
#
# The three content layers, cheapest first — a layer that is unavailable is
# DISCLOSED, never faked:
#   1. catalog metadata (committed, public);
#   2. the PUBLIC excerpt (data/research_vault/excerpts.json — already rendered
#      outside the paywall on site/research/<slug>.html, so it costs no new
#      exposure and is the honest fallback when the corpus is unreachable);
#   3. the stored body, via research_vault.corpus.get_document → R2. This is the
#      only paid layer, so it is the only one that debits the hourly view cap.
_EXCERPTS_REL = ("data", "research_vault", "excerpts.json")

_REPORT_SCHEMA = "brain.research_report.v1"
REPORT_BODY_MAX_CHARS = 12_000
# Named so the model can tell the user where the rest of the report lives. The
# budget COVERS this marker (the _truncate idiom) — a "12,000 + marker" result
# would break any caller sizing a context window off the documented number.
_REPORT_TRUNCATION_MARKER = "…full report continues — available in the Research Vault"
# The catalog clamps summary_points at 8; all of them are kept for a single
# report (the point of the escalation is depth), each clamped to the same
# per-point budget the search results use so the payload stays bounded.
_REPORT_SUMMARY_POINTS_KEPT = 8

# The EXACT key set the `report` object may carry — the _project_event discipline
# (see the module's EPISTEMICS LAW). No score, no confidence, no desk read: this
# is somebody ELSE's note, and the tool's job is to hand it over attributed, not
# to grade it.
REPORT_FIELDS: tuple[str, ...] = (
    "id", "title", "institution", "side", "published_at",
    "summary_points", "excerpt_paragraphs", "body_text", "body_truncated",
)

_REPORT_NOTE = (
    "Third-party institutional research served under the vault's Pro access — "
    "attribute every claim to {institution}, quote sparingly, synthesize in your "
    "own words; never reproduce pages verbatim. Not for redistribution."
)
_REPORT_NOTE_FALLBACK_INSTITUTION = "the publishing institution"
_REPORT_EXCERPT_ONLY = (
    " The full text is not reachable right now, so this is the report's PUBLIC "
    "opening excerpt only — say plainly that you are reading the opening pages, "
    "not the whole note."
)
# The OTHER reason a body comes back empty, and the note above is a false promise
# for it: the corpus measured this PDF as image-only (text_layer 'none'), so there
# is no fuller text to become reachable later — no retry, no repair pass, nothing.
# 'unavailable' and '' keep the excerpt-only note, which is equally true of them:
# our extraction did not run (a HOST fault, healed by ingest._reextract_bodies).
_REPORT_SCAN_ONLY = (
    " This report is a scanned/image-only PDF — the vault holds no machine-readable "
    "text for it, so the public excerpt and summary above are all the text there "
    "is. Say that plainly; do not imply a temporary failure."
)

# view_ratelimit.allow() keys a SECOND ledger on sha256(ip)[:16], and maps an
# empty/'unknown' ip to the literal bucket 'noip' — every chat user would then
# share one hourly counter and one Pro member's reading would deny everybody
# else's. So chat passes a per-user synthetic marker instead: the hash is
# hex-only and unique per user, which puts the ip ledger in lockstep with the
# user ledger (effective cap = the plain hourly limit, RESEARCH_VIEW_HOURLY).
# The gateway's `ip_hint` is deliberately NOT used as that key — an office NAT
# would collide unrelated Pro members into one bucket, which is the same bug.
_BRAIN_VIEW_IP_PREFIX = "brain:"

_REPORT_ERR_PRO = (
    "The full-report reader is a Pro capability and this call carried no "
    "signed-in Pro identity — explain the gate plainly and answer from the vault "
    "summaries instead. Never describe a report you have not read."
)
_REPORT_ERR_NOT_FOUND = (
    "No report with that id is in the vault catalog. Re-run search_research "
    "(mode='search' or mode='clusters') and use an id from those results — never "
    "guess an id, and never invent what a report says."
)
_REPORT_ERR_VAULT = (
    "The research vault catalog could not be read, so this report could not be "
    "looked up. Say so plainly rather than describing a note you have not read."
)
_REPORT_ERR_LIMIT = (
    "This account has reached its hourly full-report limit. Tell the user "
    "plainly, answer from the summaries already retrieved, and note that the cap "
    "resets at the top of the hour."
)


def _excerpt_paragraphs(root: Path, doc_id: str) -> list[str]:
    """The committed PUBLIC excerpt paragraphs for `doc_id` ([] when absent).

    Reads data/research_vault/excerpts.json ({"schema":1,"excerpts":{id:[…]}}),
    the same snapshot the SEO research pages render outside the paywall. Coverage
    is partial (a scanned PDF with no text layer has no excerpt), so [] is a
    normal answer, not a failure. Never raises.
    """
    payload = _read_json(root.joinpath(*_EXCERPTS_REL))
    if not isinstance(payload, dict):
        return []
    bucket = payload.get("excerpts")
    if not isinstance(bucket, dict):
        return []
    paras = bucket.get(doc_id)
    if not isinstance(paras, list):
        return []
    return [p.strip() for p in paras if isinstance(p, str) and p.strip()]


def _load_corpus_document(doc_id: str):
    """research_vault.corpus.get_document(doc_id), or None. Never raises.

    Imported lazily and called through the MODULE (not a from-import) so the
    attribute resolves at call time — the corpus reader is the seam tests replace,
    and an engine module that cannot be imported at all must degrade to the
    excerpt rather than take the chat turn down.
    """
    try:
        from engine.research_vault import corpus as corpus_mod  # noqa: PLC0415
        return corpus_mod.get_document(doc_id)
    except Exception:  # noqa: BLE001 — no corpus → excerpt-only, disclosed
        return None


def _charge_report_view(user_id: str, now: datetime) -> tuple[bool, dict]:
    """Debit ONE hourly view for this user. Returns (allowed, {remaining, limit}).

    Called exactly once per served BODY and never for the excerpt-only fallback —
    the excerpt is already public, and metering a public read would deny a member
    material he can see on the website.

    Fails OPEN on an unusable limiter (import/IO error), mirroring
    view_ratelimit's own documented rule: a broken ledger must not lock a paying
    subscriber out of what he bought.
    """
    try:
        from engine.research_vault import view_ratelimit  # noqa: PLC0415
        return view_ratelimit.allow(
            user_id, _BRAIN_VIEW_IP_PREFIX + user_id, now=now)
    except Exception:  # noqa: BLE001 — fail-open, same as the ledger itself
        return True, {}


def _slice_report_body(body) -> tuple[str, bool]:
    """(body within the cap, was_truncated). Cut at a word boundary, marked.

    The marker is INSIDE the budget, so the returned text never exceeds
    :data:`REPORT_BODY_MAX_CHARS` — and the model is told where the rest lives
    instead of being handed a sentence that stops mid-word with no explanation.
    """
    text = str(body or "")
    if len(text) <= REPORT_BODY_MAX_CHARS:
        return text, False
    room = max(0, REPORT_BODY_MAX_CHARS - len(_REPORT_TRUNCATION_MARKER) - 2)
    cut = text[:room].rsplit(" ", 1)[0].rstrip() if room else ""
    return f"{cut}\n\n{_REPORT_TRUNCATION_MARKER}", True


def _meta_field(item: dict, document, key: str) -> str:
    """Catalog value for `key`, else the corpus row's, else ''.

    Catalog first because it is the PUBLIC, editorially-cleaned record (titles are
    repaired there — see research_vault.title); the corpus row is the fallback for
    a catalog field that happens to be blank.
    """
    return (_first_text(item, key)
            or (_first_text(document, key) if isinstance(document, dict) else None)
            or "")


def _project_report(
    *,
    report_id: str,
    title: str,
    institution: str,
    side: str,
    published_at: str,
    summary_points: list[str],
    excerpt_paragraphs: list[str],
    body_text: str,
    body_truncated: bool,
) -> dict:
    """Build the report object from the whitelisted fields only (REPORT_FIELDS).

    Keyword-only and fully literal, exactly like :func:`_project_event`: no dict
    spread, no passthrough of the catalog item or the corpus row, so nothing an
    upstream lane adds later can reach the model's context by accident.
    """
    return {
        "id": report_id,
        "title": title,
        "institution": institution,
        "side": side,
        "published_at": published_at,
        "summary_points": summary_points,
        "excerpt_paragraphs": excerpt_paragraphs,
        "body_text": body_text,
        "body_truncated": body_truncated,
    }


def _report_error(code: str, note: str, **extra) -> dict:
    """One honest error envelope. The model explains the gate; it never invents."""
    return {"schema": _REPORT_SCHEMA, "error": code, "note": note, **extra}


def _research_report(root: Path, report_id, *, user_ctx, now: datetime) -> dict:
    """One report's fuller content for a PRO member. Never raises.

    Order is deliberate and each step is its own gate:
      1. identity — no `user_ctx`/user_id → pro_required (fail CLOSED; an
         unmeterable serve of third-party research is the thing being prevented);
      2. EXISTENCE in the committed catalog — an id the catalog does not carry
         never reaches the corpus, so a hallucinated id cannot probe the store;
      3. public layers — catalog metadata + the committed excerpt;
      4. the corpus body, and ONLY if one comes back, one debit of the hourly cap;
      5. the cap slice + the rights note.
    """
    uid = str((user_ctx or {}).get("user_id") or "").strip()
    if not uid:
        return _report_error("pro_required", _REPORT_ERR_PRO)

    rid = str(report_id or "").strip()

    try:
        items = _catalog_items(root)
    except Exception:  # noqa: BLE001
        items = None
    if items is None:
        return _report_error("vault_unavailable", _REPORT_ERR_VAULT, report_id=rid)

    item = None
    if rid:
        for candidate in items:
            if str(candidate.get("id") or "") == rid:
                item = candidate
                break
    if item is None:
        return _report_error("report_not_found", _REPORT_ERR_NOT_FOUND, report_id=rid)

    points = item.get("summary_points")
    points = [p for p in points if isinstance(p, str)] if isinstance(points, list) else []
    paragraphs = _excerpt_paragraphs(root, rid)

    document = _load_corpus_document(rid)
    body_raw = str((document or {}).get("body") or "")

    quota: dict | None = None
    if body_raw.strip():
        allowed, info = _charge_report_view(uid, now)
        if not allowed:
            return _report_error(
                "view_limit_reached", _REPORT_ERR_LIMIT,
                report_id=rid, remaining=0, limit=(info or {}).get("limit"))
        quota = {"remaining": (info or {}).get("remaining"),
                 "limit": (info or {}).get("limit")}
        body_text, truncated = _slice_report_body(body_raw)
    else:
        body_text, truncated = "", False

    institution = _meta_field(item, document, "institution")
    note = _REPORT_NOTE.format(
        institution=institution or _REPORT_NOTE_FALLBACK_INSTITUTION)
    if quota is None:
        # No body was served. WHY there is none decides which sentence is honest:
        # a measured 'none' is a scan (nothing more will ever exist), everything
        # else — no corpus row at all, an unmeasured row, a host-fault
        # 'unavailable' — is a shortfall that a later run may close.
        layer = str((document or {}).get("text_layer") or "") \
            if isinstance(document, dict) else ""
        note += _REPORT_SCAN_ONLY if layer == "none" else _REPORT_EXCERPT_ONLY

    return {
        "schema": _REPORT_SCHEMA,
        "asof": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "report": _project_report(
            report_id=rid,
            title=_meta_field(item, document, "title"),
            institution=institution,
            side=_meta_field(item, document, "side"),
            published_at=_meta_field(item, document, "published_at"),
            summary_points=[_truncate(p) for p in points[:_REPORT_SUMMARY_POINTS_KEPT]],
            excerpt_paragraphs=paragraphs,
            body_text=body_text,
            body_truncated=truncated,
        ),
        "quota": quota,
        "note": note,
    }


def search_research(
    root: Path,
    query: str = "",
    limit: int = _RESEARCH_LIMIT_DEFAULT,
    *,
    mode: str | None = None,
    report_id: str = "",
    user_ctx: dict | None = None,
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

    mode="clusters" answers a different question over the same catalog — which
    themes several houses are all writing about right now — and returns the
    brain.research_clusters.v1 envelope instead of `results`. `query` and `limit`
    are not read in that mode (see the clusters block above).

    mode="report" reads ONE report named by `report_id` and returns the
    brain.research_report.v1 envelope: catalog metadata, the public excerpt, and
    a capped slice of the stored body. It is PRO-only and METERED — `user_ctx`
    ({"user_id": …}) must be present or the call fails closed with pro_required
    (the gateway owns the tier decision; this is the fail-safe under it).
    `query` and `limit` are not read in that mode.

    Any other mode value, including a typo, searches.
    """
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    # --- report mode (W4) --------------------------------------------------- #
    # First, because it reads neither `query` nor `limit`: a Pro member asking for
    # one note's argument is not searching. The whole body is wrapped so a corpus
    # or ledger surprise degrades to an honest error instead of killing the turn.
    if _is_report_mode(mode):
        try:
            return _research_report(root, report_id, user_ctx=user_ctx,
                                    now=reference)
        except Exception:  # noqa: BLE001 — retrieval must not take the turn down
            return _report_error("vault_unavailable", _REPORT_ERR_VAULT,
                                 report_id=str(report_id or ""))

    cap = _clamp_int(limit, _RESEARCH_LIMIT_MIN, _RESEARCH_LIMIT_MAX, _RESEARCH_LIMIT_DEFAULT)
    note = (
        "institutional research summaries — third-party views, "
        "not the desk's own signals"
    )

    # --- clusters mode ----------------------------------------------------- #
    # Same tool, same catalog, same tier gate (the gateway gates by NAME, so this
    # mode inherits the Insider/Pro fence without touching it). The query is not
    # read here: convergence is a property of the whole window, and filtering it
    # by search terms would answer "who agrees with my premise" instead.
    if _is_clusters_mode(mode):
        try:
            items = _catalog_items(root)
        except Exception:  # noqa: BLE001
            items = None
        if items is None:
            return {"schema": "brain.research_clusters.v1",
                    "asof": reference.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "count_scanned": 0, "clusters": [],
                    "note": "research vault unavailable"}
        try:
            return _research_clusters(items, now=reference)
        except Exception:  # noqa: BLE001 — retrieval must not take the turn down
            return {"schema": "brain.research_clusters.v1",
                    "asof": reference.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "count_scanned": 0, "clusters": [],
                    "note": "street clusters unavailable"}

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
        "own read, and say plainly when a note disagrees with the engine. "
        "Set mode='clusters' instead of searching when the user asks what the "
        "street is FOCUSED on, where the desks are converging or crowding, or "
        "what everyone is writing about this week: that returns the themes "
        "several houses hit at once, with the report counts and house names. "
        "Convergence is what was WRITTEN, not evidence the view is right — many "
        "desks agreeing is a crowding fact, so name the houses and say so. "
        "Set mode='report' with report_id to open ONE note in depth once a "
        "search or clusters result has named it — when the user asks what a "
        "specific report actually argues, or you need its reasoning rather than "
        "its headline. That returns the fuller text for PRO members and is "
        "metered hourly, so call it for the one report that matters, not for "
        "every hit; attribute it to its institution, quote sparingly, and "
        "synthesize in your own words rather than reproducing pages."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search terms — theme, ticker, or institution (needs at "
                    "least 2 words, e.g. 'hedge fund momentum', 'NVDA capex'). "
                    "Ignored when mode='clusters' or mode='report'; pass '' there."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (1..8, default 5)",
            },
            "mode": {
                "type": "string",
                "enum": [_MODE_SEARCH, _MODE_CLUSTERS, _MODE_REPORT],
                "description": (
                    "'search' (default) ranks individual notes against the "
                    "query; 'clusters' ignores the query and returns the themes "
                    "3+ notes from 2+ institutions share right now; 'report' "
                    "ignores the query and opens the single note named by "
                    "report_id."
                ),
            },
            "report_id": {
                "type": "string",
                "description": (
                    "The id of ONE report to open in depth, used with "
                    "mode='report'. Ids come from search or clusters results — "
                    "never invent or guess one. A Pro capability: on a "
                    "non-Pro account the call returns the gate, which you "
                    "explain instead of describing a report you have not read."
                ),
            },
        },
        "required": ["query"],
    },
}
