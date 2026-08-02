"""engine.marketing.press_lane — pure, testable tick body for the press wire lane.

Processes a batch of press FeedItems (from press_providers.poll_all + the wire RSS
lane) through the full pipeline:

    satire blocklist -> relevance score -> corroboration gate -> flagship top-K/floor
    -> summarize-with-citation -> emit kind="breaking" outbox item (scheduled_at="immediate")

Reuses the existing display-tier machinery:
    breaking_relevance.score_item      deterministic salience / event_class / tickers
    breaking_summary.build_breaking_payload   LLM summarize-with-citation + card
    press_corroboration.corroboration_decision   the §3 gate

XG-W2 moved this lane onto the CANONICAL outbox path — outbox.make_item() ->
outbox.validate_item() -> outbox.enqueue() — so it inherits the id-dedup,
text-dedup, same-account near-dup and cross-account near-dup guards it used to
bypass by writing its own data/marketing/outbox/<id>.json (a shape nothing read:
the publisher folds items.jsonl). It still rides the SAME #3478 breaking dispatch
rail (scheduled_at="immediate" -> publisher._is_immediate -> Buffer
customScheduled). The earnings fast lane moved in the same wave and by the same
route, so the two shapes stay identical.

Two XG-W2 gates run BEFORE any LLM spend: the account is resolved per item by
wire_routing (no module-level account constant), and the one-conversation-one-
owner story lock refuses a claim another account already took.

Public API:
    run_press_tick(items, *, root, now, cfg, press_cfg, state, dry_run=False,
                   spool=False, llm_override=None) -> dict
        {emitted:[...], skipped:[...], digest:[...], blocked:[...]}

State (daemon-local, gitignored — data/marketing/press/; the Actions lane
commits the same dict to data/marketing/press_wire/cursors.json):
    state["flagship_counter"]  = {"day": "YYYY-MM-DD", "count": N}
        the PRIMARY desk's row, kept for the committed-cursors contract
    state["wire_day_counts"]   = {"day": "YYYY-MM-DD", "counts": {account: N}}
        W4d: the per-desk daily wire budget ledger. Each desk draws its own
        stricter-of(top-K, ramp cap) budget instead of sharing one counter that
        was named for one account while bounding all of them.
    state["wire_headroom"]     = {"day": ..., "spilled": {"a->b": N},
                                  "exhausted": N}
        W4d: the COUNTED drops. `exhausted` is items that cleared every quality
        gate and were dropped only because no live wire desk had budget left.
        Persisted, not local — a silent `continue` is how twelve nights of
        mover posts disappeared. `spilled` counts ROUTING DECISIONS, not
        emissions: an item can be handed to another desk here and still be
        refused downstream by the story lock or the queue, which is why the
        budget itself is charged at the emission, never here.
    state["transient_refusals"] = {emission_key: consecutive_env_refusals}
    (the seen-ledger + provider cursors live in the same state file, owned by the
     daemon; this module only reads/advances the counters above, the
     corroboration window and the transient-refusal retry tally.)
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# The house language law is CALLED, never forked: copywriter.banned_language is the
# one function validate_copy runs at generation time and the publisher runs at post
# time, and it is what this lane's last gate (see _emit_outbox_item) runs before an
# item can enter the queue. Imported at module level exactly as
# scripts/marketing_publisher.py imports it — copywriter's own import closure is
# stdlib + pyyaml, so the thin marketing-engine CI lane stays green.
from engine.marketing.copywriter import banned_language as _banned_language

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_OUTBOX_DIR = Path("data/marketing/outbox")
_MEDIA_DIR = _OUTBOX_DIR / "media"

# XG-W2: the account is RESOLVED per item by engine/marketing/wire_routing.py
# from the `wire_routing:` config map, not pinned to a module constant. The old
# `_ACCOUNT = "flagship"` hardcode meant the wire lane could address exactly one
# of the seven live Buffer channels — including never the account whose entire
# job is the wire (mastermind_news). This constant survives ONLY as the fallback
# wire_routing itself falls back to, so a config-less checkout behaves as before.
_FALLBACK_ACCOUNT = "flagship"

# Breaking sorts ahead of the ladder. The publisher orders candidates by
# (priority, scheduled_at, id) with a default of 5, so 1 is "first in the run".
# The pre-XG-W2 raw writer wrote the string "high" here, which make_item rejects
# (priority must be an int) and which no consumer ever compared against anything.
_BREAKING_PRIORITY = 1

#: Cashtags in post copy — the SAME shape scripts/marketing_publisher.py's
#: `_CASHTAG_RE` uses, because this gate exists to answer that gate's question
#: one step earlier: "will the publisher call this a ticker post?"
_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z])?\b")

#: Card hosting census for one tick — read by the daemon/dry-run report so the
#: press lane's picture coverage is a number, not an anecdote. `unhosted_refused`
#: is the subset that cost a post (a cashtag item with no hosted card cannot ship
#: at all: bare it would be quarantined by the publisher and text-only it would
#: violate the every-ticker-post-carries-a-chart law).
_MEDIA_HOST_TALLY: dict[str, int] = {
    "cards": 0, "hosted": 0, "unhosted": 0, "unhosted_refused": 0,
}


def media_host_stats() -> dict:
    """A COPY of this process's card-hosting census."""
    return dict(_MEDIA_HOST_TALLY)


def reset_media_host_stats() -> None:
    """Zero the card-hosting census (tests + the dry-run report)."""
    for k in _MEDIA_HOST_TALLY:
        _MEDIA_HOST_TALLY[k] = 0


#: Refusal reasons that are a property of the ENVIRONMENT, not of the copy.
#:
#: A TRANSIENT REFUSAL MUST NOT ENTER A PERMANENT LEDGER (adversarial review,
#: 2026-07-31). Everything else `_emit_outbox_item` can refuse — invalid item,
#: banned language, a duplicate, a near-dup, a cap — is decided by the generated
#: TEXT and gives the same answer on every retry, which is why the caller marks
#: those seen. ``media_unhosted`` is not in that class: it fires when the Chrome
#: raster loses a race, when the R2 upload blips, when boto3 or the R2_* creds
#: are missing on the host. One flaky raster on a breaking cashtag story used to
#: bury that story for the whole life of the seen ledger, and the LLM spend that
#: produced its copy bought nothing.
_TRANSIENT_REFUSALS: frozenset[str] = frozenset({"media_unhosted"})

#: Consecutive transient refusals of the SAME story before the lane alarms. A
#: retry loop that never surfaces is the other half of the same fault: a host
#: that is genuinely down (no creds, no boto3) would otherwise re-render, re-pay
#: and re-refuse the same item every tick in silence. Three ticks is the press
#: daemon's ~15 minutes — long enough to ride out a raster blip, short enough
#: that a real outage lands in the Actions summary the same hour.
_TRANSIENT_RETRY_ALARM_AT = 3

#: Cap on the per-story retry tally carried in daemon state. Bounded like every
#: other ledger here: the counter exists to spot a stuck story, not to be a
#: history. Oldest entries (insertion order) are dropped first.
_TRANSIENT_TALLY_CAP = 500


#: Wire emissions allowed PER WIRE DESK PER DAY. A VOLUME CAP, not a quality
#: gate — which item may go out is decided by `flagship_salience_floor`, the
#: market-nexus test, the corroboration gate and the garbage gate, and none of
#: those moved when this number did (W4d, 2026-08-02).
#:
#: WAS 3, AND 3 WAS NOT MEASURED. It is now, by replaying the real backlog —
#: 438 live items polled from the six `breaking.sources` RSS feeds plus the two
#: free Truth mirrors on 2026-08-02 — through this function in hourly ticks with
#: the daemon's own clocks:
#:
#:   day        candidates  above-floor (cash-session clock)  emitted at K=3
#:   2026-07-30      20            2                                2
#:   2026-07-31      22            2                                2
#:   2026-08-01      96            2                                0
#:   2026-08-02      43            6                                1
#:
#: TWO THINGS THAT REPLAY SAYS, AND BOTH BELONG HERE. First, on most days the
#: binding constraint is SUPPLY, not this counter: ~45% of the daily ingest is a
#: mirror duplicate and nearly all of the rest scores under the 30.0 floor, so
#: the lane emits 1-2/day with `flagship_top_k_reached` never once firing.
#: Raising this number does not manufacture volume and must not be sold as
#: though it does. Second, it DOES bind on the busy days — 2026-08-02 cleared 6
#: above the floor off a PARTIAL day's 43 candidates, so K=3 would have dropped
#: half of them, and it would have dropped them into a `continue` whose count
#: nothing persisted.
#:
#: WHY 10. Bounded from above by flagship's own ramp cap: `sentinel.ramp.
#: account_overrides.flagship.max_posts_per_account_per_day` is 20, and the wire
#: must not be able to consume a desk's whole day — the nightly ladder and the
#: publish-time lanes draw from the same 20. Half is the operator-legible split.
#: Bounded from below by the measured supply: 10 covers the highest observed
#: above-floor day (6) with headroom, and covers a full weekday extrapolated
#: from 2026-08-02's 14% above-floor rate on ~95 candidates (~13) at ~75%.
#: It is >3x the masterplan §8.0 per-account acceptance floor.
#:
#: PER DESK, NOT PER NETWORK (this is the fix to the XG-W2 TODO at step 5). The
#: pre-W4d counter was global while being named for one account, so the moment
#: mastermind_news armed it would have shared flagship's 3/day and the wire desk
#: would have starved the flagship rather than adding to it.
_DEFAULT_FLAGSHIP_TOP_K = 10
_DEFAULT_FLAGSHIP_FLOOR = 70.0
_DEFAULT_CORROBORATION_WINDOW_S = 1800

# B4a rail: the news.html live-wire rail floor is LOWER than the X post floor —
# the rail shows everything above this (incl. digest-class items), X gets top-K.
_DEFAULT_RAIL_FLOOR = 40.0
_DEFAULT_RAIL_MAX_ITEMS = 50

#: `policy` ONLY, and the exclusions are each a measured decision rather than a
#: judgement call — every one of these was scored before the set was written:
#:
#:   geopolitical  "Israel and Iran agree to ceasefire after two weeks of
#:                 strikes" scores 36.0 and matches NO ticker, sector or macro
#:                 key. It is also one of the most market-moving headlines a
#:                 wire can carry. Requiring a nexus here blocks exactly the
#:                 story this lane should be fastest on, so geopolitical is out:
#:                 war, ceasefires and sanctions are market events as a class.
#:   company_news  about a company by construction (43.5 / 36.0 in the live
#:                 sample, both with tickers) — and a company whose name the
#:                 ticker universe happens not to carry must still ship.
#:   macro_print   a print IS the market event ("Real GDP increased at an
#:                 annual rate of 1.5 percent" -> 52.5, macro_keys=['gdp']).
#:
#: That leaves `policy`, the one class that holds domestic political content
#: which can be loud and mean nothing for a tape.
_NEXUS_REQUIRED_CLASSES: frozenset[str] = frozenset({"policy"})


def _no_market_nexus(scored: dict) -> bool:
    """True when a politics-scored item demonstrates no connection to markets.

    `matched` is breaking_relevance's own output — the tickers, sectors and
    macro keys it found in the headline. An item in a class that scores on the
    speaker rather than the content, which matched NONE of the three, is
    political content that happens to be loud. Anything else passes.
    """
    if str(scored.get("event_class") or "") not in _NEXUS_REQUIRED_CLASSES:
        return False
    m = scored.get("matched") or {}
    return not (m.get("tickers") or m.get("sectors") or m.get("macro_keys"))

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _day_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d")


# XG-W5 removed this lane's own `_is_satire`. The rule now lives ONCE, in
# engine/marketing/garbage_gate.py, reached through `_garbage_check` below —
# the list itself still lives ONCE too, in config/press_sources.yml
# `satire_blocklist`, and is handed in by the caller. Keeping a delegating
# wrapper here would have left a second name for one rule with no caller.


def _garbage_check(item: dict, *, gate_cfg: dict, blocklist_lower: set[str]) -> dict | None:
    """XG-W5 P0 garbage gate — runs BEFORE features and before any LLM spend.

    Fail-open by design: a gate that cannot evaluate must not silently delete the
    wire. Any unexpected failure logs a start-of-line warning and passes the item
    through to the existing corroboration/floor/sentinel gates, which are the
    real publication guards.
    """
    from engine.marketing import garbage_gate as _gg  # noqa: PLC0415

    try:
        return _gg.check(item, cfg=gate_cfg, satire_blocklist=blocklist_lower)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=garbage-gate-failed::{item.get('id', '')}: "
              f"{type(exc).__name__}: {exc} — item passed through", flush=True)
        return None


_DEFAULT_CORPUS_ROW_WINDOW_H = 24


def _corpus_gate(state: dict, *, now: datetime, window_h: float):
    """Return `(should_row, note)` — a per-item corpus-row dedupe window.

    REVIEW F-1, the blocker. The lane's `seen` ledger only advances when an item
    EMITS or is refused by the outbox. Every other outcome — garbage-dropped,
    digest, below-floor, over top-K, story-locked — leaves the item unseen, so
    the next tick re-ingests it, re-scores it and writes ANOTHER corpus row. At
    a 120-second cadence that is 30 rows per item per hour, forever: the
    reviewer's 6-hour replay of three stale RSS items produced 560 rows over 23
    distinct ids, and a "200-item" labeling batch came back with 22 distinct
    items, two of them ninety times over.

    The corpus is a labeling and evaluation sample, so its unit must be the
    ITEM, not the tick. This gate keys on item id and admits each item once per
    rolling window. It is deliberately separate from `seen`: `seen` governs
    EMISSION (and must keep letting a below-floor item be reconsidered when its
    corroboration grows), while this governs SAMPLING.

    The window is a config key. The state lives in the same daemon-local
    gitignored dict as everything else here.
    """
    ledger: dict = state.setdefault("corpus_rowed", {})
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=window_h)
    for key in [k for k, ts in list(ledger.items())
                if (_parse_ts(ts) or cutoff) < cutoff]:
        del ledger[key]

    stamp = now.astimezone(timezone.utc).isoformat()

    def _should_row(item_id: str) -> bool:
        key = str(item_id or "")
        if not key or key in ledger:
            return False
        ledger[key] = stamp
        return True

    return _should_row


def _parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scoring_provenance(scored: dict) -> dict:
    """Compact `_components` for the outbox item's provenance block."""
    components = scored.get("_components") or {}
    story = components.get("story") or {}
    return {
        "version": components.get("scoring_version", ""),
        "rank_score": scored.get("rank_score"),
        "features": components.get("features") or {},
        "story_id": story.get("story_id", ""),
        "source_count": story.get("source_count", 0),
    }


def _corpus_row(scored: dict, *, outcome: str, now_iso: str) -> dict:
    """One golden-set corpus row for an ingested item (host-local sink).

    The labeling batch and the eval harness both read this shape. It carries the
    label-relevant surface (headline/source/url/time), the deterministic score
    and the full `_components`, and the pipeline OUTCOME so a labeler can see
    what the engine did with it. Written by the daemon to the GITIGNORED
    data/marketing/press/ tree — never a repo write.
    """
    components = scored.get("_components") or {}
    salience_block = components.get("salience") or {}
    # Review F-8(b): the UNCONTAMINATED baseline. Once demotion arms, `salience`
    # is partly the new scorer's output, so the harness's "incumbent ordering"
    # control would be a blend of control and treatment. `salience_base` is the
    # pre-demotion number and is what the eval ranks the baseline on.
    salience_base = salience_block.get("pre_demotion", scored.get("salience"))
    return {
        "schema": "press_corpus.v1",
        "item_id": str(scored.get("id", "")),
        "ingested_at": now_iso,
        "published_at": str(scored.get("published_at", "")),
        "headline": str(scored.get("headline", "")),
        "body_snippet": str(scored.get("body_snippet", ""))[:400],
        "url": str(scored.get("url", "")),
        "source": str(scored.get("source", "")),
        "source_name": str(scored.get("source_name", "")),
        "source_tier": str(scored.get("source_tier", "")),
        "event_class": str(scored.get("event_class", "none")),
        "salience": scored.get("salience"),
        "salience_base": salience_base,
        "rank_score": scored.get("rank_score"),
        "story_id": (components.get("story") or {}).get("story_id", ""),
        "outcome": outcome,
        "_components": components,
    }


def _emission_key(item: dict) -> str:
    """Mirror-collapsed identity for EMISSION dedupe (M1).

    The same Truth post seen via two mirrors (trumpstruth + cnn_truth_backfill)
    carries two distinct FeedItem `id`s (each embeds its mirror source key) but a
    single `truth_status_id`. Deduping emission on `id` alone therefore double-
    emits the same post. When a truth_status_id is present the emission identity
    collapses to `truth:{id}`; otherwise it is the plain item id. This key (not the
    raw id) is what the seen-ledger records for mirror items, so a later tick from
    EITHER mirror is recognised as already-emitted.
    """
    tsid = str(item.get("truth_status_id", "")).strip()
    if tsid:
        return f"truth:{tsid}"
    return str(item.get("id", ""))


def _strip_trailing_source_clause(summary: str, source_name: str) -> str:
    """Remove a trailing '-- {source_name}' clause from a summary (m3).

    The deterministic fallback builds '{headline} -- {source_name}'; when the body
    attribution is supplied by the corroboration decision we must not leave the
    mirror name in the body. Only strips the EXACT trailing source clause (any
    dash variant, longest first) so a dash inside the headline itself is kept.
    The em/en-dash variants stay in the list because a summary of an OLDER vintage
    (or an LLM that ignored its prompt) can still arrive carrying one.
    """
    text = str(summary).rstrip()
    src = str(source_name).strip()
    if not src:
        return text
    for dash in (" -- ", " — ", " – ", " - ", "--", "—", "–", "-"):
        suffix = f"{dash}{src}"
        if text.endswith(suffix):
            return text[: -len(suffix)].rstrip()
    return text


def _corroboration_key(item: dict) -> str:
    """A coarse claim key for counting independent corroborating sources.

    For mirror items it is the Truth status id (the same post seen via two
    mirrors is the SAME claim, not two).

    For hearsay/x_relay items corroboration keys on ENTITY + event_class, NOT raw
    headline text (M3): two handles wording the same claim differently
    ("Trump told reporters new China tariffs" vs "Trump: China tariffs to rise")
    share matched entity `tariffs` and event_class `policy`, so they land on the
    same claim key and corroborate. A verbatim-headline key never matched such a
    pair — the ≥2-source instant path was dead. `item` must be a SCORED item
    (carrying `matched` + `event_class` from score_item); an unscored item falls
    back to a headline stub so the function never raises.
    """
    tsid = str(item.get("truth_status_id", "")).strip()
    if tsid:
        return f"truth:{tsid}"

    event_class = str(item.get("event_class", "none"))
    entity = _primary_entity(item)
    if entity:
        return f"claim:{event_class}:{entity}"

    # No named entity/ticker to anchor on → fall back to a normalized headline
    # stub (unscored item, or a claim with no matched entity). This path never
    # corroborates a differently-worded pair, which is the conservative default.
    head = re.sub(r"[^a-z0-9 ]", "", str(item.get("headline", "")).lower())
    head = re.sub(r"\s+", " ", head).strip()
    return f"head:{head[:80]}"


def _primary_entity(item: dict) -> str:
    """The single strongest matched entity anchoring a claim, or "".

    Deterministic precedence ticker > macro_key > sector so two items about the
    same claim resolve to the SAME anchor even when one also matched a weaker
    signal. Reads score_item's `matched` dict; returns "" when nothing matched.
    """
    matched = item.get("matched")
    if not isinstance(matched, dict):
        return ""
    for field in ("tickers", "macro_keys", "sectors"):
        vals = matched.get(field) or []
        if vals:
            return f"{field[:3]}:{sorted(str(v) for v in vals)[0]}"
    return ""


# ── Intelligence Desk claim registry (V2 §3) ────────────────────────────────
# The story spine is the PRIMARY cross-source matcher, but its two matching
# backends are optional: MinHash near-dup needs `datasketch` and the semantic
# pass needs a local encoder artifact. On a bare host NEITHER exists, so nothing
# cross-source ever matched and every arrival opened its own desk story — an
# arrival log wearing an intelligence UI. This registry is the deterministic
# FLOOR under that: the lane already computes an entity+event_class claim anchor
# that matches two differently-worded reports of one claim, so the desk uses it
# for story identity too. Lives here (post-scoring, where `matched` exists), not
# in intelligence_desk (stdlib-only) and not in the spine (assigns pre-scoring).
_INTEL_CLAIM_TTL_H = 24.0
_INTEL_JACCARD_MIN = 0.15
# Inside `tight_window_min` the wording bar LOWERS to this — it is never
# bypassed. A bare "overlap >= jaccard_min OR inside the window" merged two
# genuinely different same-ticker stories that arrived 10 minutes apart and then
# presented the false merge as confirmed/multi-source evidence (review N1).
_INTEL_TIGHT_JACCARD_MIN = 0.05
_INTEL_TIGHT_WINDOW_MIN = 45.0
#: Prefix of the day-bucketed fallback id. Load-bearing: it is what tells a
#: registered `story_id` apart from a spine-assigned one (see
#: `_intel_registered_spine_sid`).
_INTEL_STUB_PREFIX = "intel_"
# STATE BUDGET (load-bearing, not a round number). This registry lives in the
# tick state dict, and the GitHub Actions deployment of this lane
# (scripts/marketing_press_wire.py) COMMITS that dict to a tracked cursors.json
# under a 256 KB ceiling — a 24h TTL over ~24 anchors per 30-minute window is
# ~1k entries/day, so an unbounded registry with a token LIST per entry would
# have blown that file. Entries are capped, and tokens are stored as ONE
# space-joined string (indent=2 puts a list item on its own line).
_INTEL_CLAIM_MAX_ENTRIES = 400
_INTEL_TOKEN_CAP = 12
# Words that carry no claim identity. Without them a Jaccard over two unrelated
# headlines about the same ticker clears 0.15 on "the/and/for" alone, and the
# registry would merge two genuinely different stories.
_INTEL_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "after",
    "says", "said", "will", "has", "have", "its", "his", "her", "their", "are",
    "was", "were", "but", "not", "you", "who", "how", "why", "new", "amid",
    "than", "then", "out", "off", "per", "via", "may", "can", "all", "one",
    "two", "more", "most", "now", "here", "什么", "报道",
})


def _intel_claim_key(scored: dict) -> str:
    """The registry anchor for a scored item, or "" when it cannot be anchored.

    Deliberately ENTITY-anchored (`claim:{event_class}:{primary_entity}`), the
    same anchor `_corroboration_key` uses for its M3 pair-matching. The two other
    shapes `_corroboration_key` can return are excluded on purpose:

      * `truth:<status_id>` is a per-POST identity — after mirror collapse it is
        unique to one item, so registering it could never merge two sources. A
        Truth post that matched an entity still participates through the anchor
        below, which is exactly the Trump-wire ↔ Reuters merge we want.
      * `head:<normalized headline>` is the no-anchor fallback. An unanchored
        claim has nothing to alias ON, and registering headline stubs would make
        the registry a second, weaker near-dup matcher.
    """
    entity = _primary_entity(scored)
    if not entity:
        return ""
    return f"claim:{str(scored.get('event_class', 'none'))}:{entity}"


def _intel_tokens(headline: object) -> set[str]:
    """Normalized content tokens of a headline, for the overlap sanity check.

    Truncated to the same alphabetical prefix the registry stores, so the two
    sides of the Jaccard are always the same shape — a comparison where only one
    side is capped silently depresses the overlap on long headlines.
    """
    words = re.sub(r"[^a-z0-9 ]", " ", str(headline or "").lower()).split()
    keep = {w for w in words if len(w) >= 3 and w not in _INTEL_STOPWORDS}
    return set(sorted(keep)[:_INTEL_TOKEN_CAP])


def _intel_jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _intel_day_stub_id(scored: dict, *, now: datetime) -> str:
    """A story id for an item the spine could not place, stable within a UTC day.

    The v1 fallback hashed `truth_status_id|url|headline`, so the SAME story seen
    at two urls (or re-served with a drifted headline) opened two desk rows and
    the desk could never merge them. Day-bucketing the normalized headline keeps
    one id per (day, wording) — a floor, not a matcher.
    """
    head = re.sub(r"[^a-z0-9 ]", " ", str(scored.get("headline", "")).lower())
    head = re.sub(r"\s+", " ", head).strip()[:120]
    day = now.astimezone(timezone.utc).strftime("%Y%m%d")
    return _INTEL_STUB_PREFIX + hashlib.sha1(
        f"{day}|{head}".encode("utf-8")).hexdigest()[:20]


def _prune_intel_claims(registry: dict, *, now: datetime, ttl_h: float) -> None:
    """Same TTL discipline as the corroboration ledger; also bounded by count."""
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=max(1.0, ttl_h))
    for key in list(registry):
        entry = registry.get(key)
        first = _parse_ts(entry.get("first_ts")) if isinstance(entry, dict) else None
        if first is None or first < cutoff:
            del registry[key]
    if len(registry) > _INTEL_CLAIM_MAX_ENTRIES:
        # Persisted daemon state: keep the newest claims, drop the oldest tail.
        ordered = sorted(
            registry.items(),
            key=lambda kv: str((kv[1] or {}).get("first_ts") or ""),
            reverse=True,
        )
        for key, _ in ordered[_INTEL_CLAIM_MAX_ENTRIES:]:
            del registry[key]


def _intel_registered_spine_sid(entry: object) -> str:
    """The SPINE sid a registry entry was registered with, or "" when none.

    Read off `story_id` rather than stored a second time, and that is exact by
    construction: `_resolve_intel_story_id` registers ``own``, which is either
    the incoming spine sid or a day stub, and a day stub is the only value that
    carries `_INTEL_STUB_PREFIX` (spine ids are ``st-<sha1>``). Duplicating the
    value into its own key costs ~17 KB at the 400-entry cap and puts the state
    budget over the 100 KB line that `cursors.json` is measured against —
    `test_the_claim_registry_stays_inside_its_state_budget` pins both that
    ceiling and the `story_id == spine_sid` invariant this reader depends on.
    """
    if not isinstance(entry, dict):
        return ""
    sid = str(entry.get("story_id") or "")
    return "" if sid.startswith(_INTEL_STUB_PREFIX) else sid


def _resolve_intel_story_id(scored: dict, *, spine_sid: str, registry: dict,
                            now: datetime, jaccard_min: float,
                            tight_jaccard_min: float,
                            tight_window_min: float) -> str:
    """The desk story id this item belongs to (V2 §3 resolution).

        no anchor        -> the spine's id, else a day-bucketed headline stub
        anchor hit (TTL) -> alias to the registered story WHEN the wording
                            overlaps: Jaccard >= jaccard_min, relaxed to
                            >= tight_jaccard_min inside tight_window_min.
                            Otherwise keep own id, because two different
                            stories can share a ticker
        spine primacy    -> when BOTH arrivals carry a real spine sid and the
                            two differ, never alias, whatever the wording says
        anchor miss      -> register this story under the anchor
    """
    own = str(spine_sid or "") or _intel_day_stub_id(scored, now=now)
    key = _intel_claim_key(scored)
    if not key:
        return own
    tokens = _intel_tokens(scored.get("headline"))
    entry = registry.get(key)
    if isinstance(entry, dict) and entry.get("story_id"):
        # SPINE PRIMACY (review N1). The registry is the deterministic floor
        # UNDER a missing spine, never an override of a working one: when the
        # spine placed these two arrivals in DIFFERENT stories it used a better
        # matcher than an entity anchor plus a token overlap, and undoing that
        # here would merge on the weaker signal. Only a real sid counts on each
        # side — a day stub means the spine said nothing about that arrival.
        registered = _intel_registered_spine_sid(entry)
        incoming = str(spine_sid or "")
        if registered and incoming and registered != incoming:
            return own
        # Pruning already dropped anything past the TTL, so a hit is in-window.
        first = _parse_ts(entry.get("first_ts"))
        tight = (
            first is not None
            and (now.astimezone(timezone.utc) - first)
            <= timedelta(minutes=max(0.0, tight_window_min))
        )
        # The tight window LOWERS the bar; it never bypasses it. `min` keeps
        # that true even if the two keys are configured the wrong way round —
        # "arrived close together" may relax the wording test, never tighten it.
        bar = min(jaccard_min, tight_jaccard_min) if tight else jaccard_min
        overlap = _intel_jaccard(tokens, _intel_stored_tokens(entry.get("tokens")))
        if overlap >= bar:
            return str(entry["story_id"])
        return own
    registry[key] = {
        "story_id": own,
        "first_ts": now.astimezone(timezone.utc).isoformat(),
        "tokens": " ".join(sorted(tokens)),
    }
    return own


def _intel_stored_tokens(value: object) -> set[str]:
    """Read a stored token set. Tolerates the list form an older state file has."""
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, (list, tuple, set)):
        return {str(v) for v in value}
    return set()


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO stamp to aware UTC, or None. Never raises."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _independent_source(item: dict) -> str:
    """Identity used to count INDEPENDENT sources for corroboration.

    Review F-14: ONE implementation, in engine/marketing/story_spine.py. This
    lane's corroboration counter and the story spine's source counter were two
    copies of the same rule, so a fix to either drifted from the other; they now
    share a key space by construction, which is also what makes the spine's
    match-weighted count a valid input to the corroboration feature (F-6).
    Fail-soft to the historical form: a corroboration counter that raises would
    stop the wire.
    """
    try:
        from engine.marketing.story_spine import independence_key  # noqa: PLC0415

        return independence_key(item)
    except Exception:  # noqa: BLE001
        return str(item.get("x_handle") or item.get("source") or "")


def _resolve_top_k(breaking_cfg: dict | None, wire_cfg: dict | None) -> int:
    """Daily wire budget per desk, from config, with the measured code default.

    Precedence, highest first:

        cfg["breaking"]["flagship_top_k_per_day"]        (config/marketing.yml)
        press_cfg["wire"]["flagship_top_k_per_day"]      (config/press_sources.yml)
        _DEFAULT_FLAGSHIP_TOP_K

    TWO HOMES ON PURPOSE, AND THIS IS THE ORDER THAT MAKES THEM SAFE. The knob
    has always lived under press_sources' `wire:` block, next to the salience
    floor it is repeatedly confused with. Everything else that decides whether a
    breaking item may go out — the salience threshold, the LLM lane, the garbage
    gate, the sources themselves — lives in marketing.yml `breaking:`, which is
    also where the desk roster and the routing table are. Adding the marketing.yml
    key at HIGHER precedence lets the volume decision sit beside the desks it
    governs without silently disowning a press_sources value an operator already
    tuned: absent the new key, the old one still wins, and a checkout that sets
    neither gets the measured default rather than the historical 3.

    Junk in either place is IGNORED with a start-of-line annotation rather than
    coerced — a mistyped cap that silently reads as 0 is a dark lane, and this
    lane has been dark for reasons exactly that dull before.
    """
    for block, home in ((breaking_cfg, "breaking"), (wire_cfg, "wire")):
        if not isinstance(block, dict) or "flagship_top_k_per_day" not in block:
            continue
        raw = block.get("flagship_top_k_per_day")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            # BARE, line-start, flushed — a logger prefix makes GitHub drop it.
            print(f"::warning title=press-lane-top-k-invalid::"
                  f"{home}.flagship_top_k_per_day={raw!r} is not an integer — "
                  f"ignoring it and falling through to the next source "
                  f"(default {_DEFAULT_FLAGSHIP_TOP_K})", flush=True)
            continue
        if value < 0:
            print(f"::warning title=press-lane-top-k-invalid::"
                  f"{home}.flagship_top_k_per_day={value} is negative — ignoring "
                  f"it (use 0 to stop the lane deliberately)", flush=True)
            continue
        return value
    return _DEFAULT_FLAGSHIP_TOP_K


def _ramp_post_caps(cfg: dict | None, now: datetime, root: Path) -> dict[str, int]:
    """``{account: max_posts_per_account_per_day}`` from the sentinel ramp.

    The wire's per-desk budget is the STRICTER of its own top-K and this, so a
    cold desk cannot be handed a warmed desk's volume just because the wire is
    the lane doing the handing. Press items are ``scheduled_at="immediate"`` and
    an immediate item is exempt from the per-account daily cap downstream
    (standing operator ruling, "breaking has no limits"), so this is the ONLY
    place the ramp reaches them — and it reaches them as a CEILING, never as a
    licence: an account absent from the map, or holding an unlimited cap, keeps
    the plain top-K.

    Never raises and never blocks: a ramp that cannot be resolved returns {} and
    every desk falls back to the plain top-K, which is the pre-W4d behaviour.
    """
    try:
        from engine.marketing.sentinel import resolve_ramp  # noqa: PLC0415

        report = resolve_ramp(cfg if isinstance(cfg, dict) else {},
                              _day_key(now), root=root, announce=False)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=press-lane-ramp-unavailable::"
              f"{type(exc).__name__}: {exc} — wire desks fall back to the plain "
              f"top-K budget", flush=True)
        return {}
    caps: dict[str, int] = {}
    for acct, row in (report.get("accounts") or {}).items():
        raw = (row.get("caps") or {}).get("max_posts_per_account_per_day")
        if raw is None:          # config -1/"unlimited" — no ceiling to apply
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            caps[str(acct)] = value
    return caps


#: (from, to) spill pairs already announced in THIS process. The daemon ticks
#: every ~90s and a busy news day spills repeatedly; one line per pair is the
#: operator's signal, 300 identical lines are noise that buries it.
_WARNED_SPILL: set[tuple[str, str]] = set()


def reset_spill_warnings() -> None:
    """Clear the once-per-process spill announcement set (tests)."""
    _WARNED_SPILL.clear()


def _pick_spill_account(routed: str, *, pool: list[str], budgets: dict[str, int],
                        counts: dict[str, int]) -> str:
    """A live wire desk with headroom, or "" when the whole pool is spent.

    Chooses the desk with the MOST remaining headroom so a busy day spreads
    across the network instead of filling one desk and then the next — a
    20-post/day flagship firehose is a worse product than a distributed wire,
    which is the whole point of W4d. Ties break on account id so the choice is
    reproducible run to run.

    `pool` is wire_routing.spill_pool's answer, so a dark desk cannot appear
    here: there is one liveness read in this lane and this is not a second one.
    """
    best = ""
    best_room = 0
    for acct in pool:
        if acct == routed:
            continue
        room = int(budgets.get(acct, 0)) - int(counts.get(acct, 0))
        if room > best_room:
            best, best_room = acct, room
    return best


def _spill_pool(cfg: dict, root: Path) -> list[str]:
    """Live wire-owning desks (wire_routing.spill_pool), fail-soft to none.

    An empty pool is a valid answer and means "no spill target" — the routed
    desk's own budget then bounds the lane exactly as it did before W4d.
    """
    try:
        from engine.marketing.wire_routing import spill_pool  # noqa: PLC0415

        return spill_pool(cfg, root=root)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=wire-spill-unavailable::{type(exc).__name__}: "
              f"{exc} — surplus wire items have no spill target this tick",
              flush=True)
        return []


def _route_account(scored: dict, *, cfg: dict, root: Path) -> str:
    """The account that owns this wire item (XG-W2 per-account wire routing).

    Fail-soft to the historical flagship: a routing lookup must never be able to
    stop a breaking item from emitting at all.
    """
    try:
        from engine.marketing.wire_routing import route  # noqa: PLC0415

        return route(scored.get("event_class", "none"), cfg=cfg, root=root)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=wire-routing-failed::falling back to "
              f"{_FALLBACK_ACCOUNT}: {exc}", flush=True)
        return _FALLBACK_ACCOUNT


def _story_key_for(scored: dict, corroboration_key: str) -> str:
    """The one-owner lock identity for a press item.

    The lane's own ``_corroboration_key`` is the primary input: it is already the
    engine's answer to "is this the same claim?", including the mirror collapse
    (one Truth status id across two mirrors) and the M3 entity+event_class key
    that made two differently-worded relays of one claim resolve together. The
    normalized-headline hash is only the last-resort fallback inside
    ``story_lock.story_key``.
    """
    try:
        from engine.marketing.story_lock import story_key  # noqa: PLC0415

        return story_key(
            cluster_key=corroboration_key,
            event_id=scored.get("id"),
            headline=scored.get("headline"),
        )
    except Exception:  # noqa: BLE001
        return ""


def _story_lock_check(account: str, key: str, *, root: Path, now: datetime,
                      cfg: dict):
    """Run the cross-account one-owner lock against the outbox queue.

    Returns a LockVerdict, or None when the lock could not run (import or read
    failure) — the caller treats None as "no verdict, proceed", because a lock
    that cannot read its state must not become a silent publication stopper.
    """
    if not key:
        return None
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415
        from engine.marketing import story_lock as _sl  # noqa: PLC0415

        return _sl.check(account, key, _ob.read_items_all(root), now=now, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=story-lock-unavailable::{key}: {exc}", flush=True)
        return None


def _clamp_for_x(headline: str, body: str, *, attribution: str = "",
                 tape_stamp: str = "") -> dict:
    """The platform clamp (M1), IMPORTED from the module that owns the budgets.

    ``wire_format`` is a stdlib-only sibling, so this is the same lazy-import
    idiom ``_emit_outbox_item`` uses for ``outbox``: a checkout where it cannot
    be imported is broken, and hiding that behind a fallback would let an
    over-cap post reach the queue.
    """
    from engine.marketing.wire_format import clamp_for_x  # noqa: PLC0415

    return clamp_for_x(headline, body, attribution=attribution,
                       tape_stamp=tape_stamp)


def _host_card_media(
    entry: dict,
    svg: str,
    *,
    item_id: str,
    as_of: str,
    root: Path,
) -> bool:
    """Raster the press card and publish the PNG; stamp the media entry. -> hosted?

    THE DEFECT THIS CLOSES (2026-07-31). This lane rendered a breaking card into
    `payload["card_svg"]`, wrote the raw SVG to `data/marketing/outbox/media/` and
    stopped there. Nothing in press_lane.py or breaking_summary.py ever called
    `rasterize_svg` or `media_publish.publish_card`, so every press item shipped a
    media[] entry with no `media_url` — and Buffer/X can only attach a HOSTED
    image (`_media_paths_for` skips non-http paths). The card was rendered,
    committed and unreachable: every press post went out text-only, and a press
    item carrying a cashtag was permanently unpostable (the publisher quarantines
    a bare cashtag post — "YOU WILL NOT SHIP THESE TEXT ONLY"). The publish
    workflow has pip-installed boto3 since 159537bcfe for exactly this call.

    ONE SEAM: `media_publish.publish_card` is the same function the hot-tape lane
    goes through (`hot_tape_radar.resolve_chart`), so the posted PNG is a raster
    of the SAME SVG the admin preview shows — the 2026-07-26 drift incident's
    rule. The hot-tape card contract is copied exactly: `media_url`,
    `media_png_path` and `media_render` land on the media entry.

    FAIL-SOFT BY CONSTRUCTION: `publish_card` never raises, and the try/except is
    the second belt — a missing Chrome, absent R2 credentials or a boto3-less
    checkout must degrade the PICTURE, never take down the wire lane. A False
    return puts the caller back on exactly the pre-fix behaviour (local SVG only)
    for a cashtag-free item.

    `chart_id` is the FEED item id and `as_of` the item's own as_of, so the
    sidecar key scripts/marketing_media_backfill.py writes
    (``<as_of>/<chart_id>``) matches what the publisher looks up — an upload that
    fails tonight is recoverable tomorrow instead of lost.
    """
    try:
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415

        published = publish_card(svg, chart_id=item_id, as_of=as_of, root=root) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=press-lane-card-publish-failed::{item_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return False

    url = str(published.get("media_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        # A PNG may still have been written locally — keep the pointer so the
        # backfill can upload it later without re-rastering.
        if published.get("media_png_path"):
            entry["media_png_path"] = published["media_png_path"]
        return False

    entry["media_url"] = url
    if published.get("media_png_path"):
        entry["media_png_path"] = published["media_png_path"]
    if published.get("media_render"):
        entry["media_render"] = published["media_render"]
    return True


def _emit_outbox_item(
    root: Path,
    item_id: str,
    account: str,
    headline: str,
    body: str,
    svg: str,
    provenance: dict,
    now: datetime,
    *,
    story_key: str,
    cta_suppress: bool,
    dry_run: bool,
    cfg: dict | None = None,
    spool: bool = False,
    refusal: dict | None = None,
    text_override: str | None = None,
) -> dict[str, Any] | None:
    """Build a CANONICAL outbox item (kind='breaking') and enqueue it.

    XG-W2 replaced the hand-rolled ``data/marketing/outbox/<id>.json`` writer this
    used to be. That writer produced a shape no reader consumed (the publisher
    folds ``items.jsonl`` and nothing else), so every press emission bypassed
    ``make_item``/``validate_item`` AND the id-dedup, text-dedup, same-account
    near-dup and cross-account near-dup guards that live in ``enqueue``. The lane
    now goes through the front door.

    Returns the item dict, or None when validation, the language gate, the card
    host, or the queue refused it (the caller records a skip). ``dry_run`` builds
    and validates but writes nothing — the media SVG, its PNG raster and the R2
    upload included, which is why a dry run cannot report the media_unhosted
    verdict a live run can. ``refusal``, when supplied, is filled with
    {"reason": ...} so the caller's skip census names the gate that fired instead
    of a generic refusal.

    ``text_override`` is the PLATFORM-CLAMPED post text (M1). The item still
    carries the full headline/body fields for the rail and the admin preview, but
    ``text`` — the string the publisher validates and posts — is the clamped one.
    Absent, the text is composed from the pair exactly as before.
    """
    from engine.marketing import outbox as _ob  # noqa: PLC0415

    media_rel = f"data/marketing/outbox/media/{item_id}.svg"
    as_of = now.astimezone(timezone.utc).strftime("%Y-%m-%d")

    # Media keeps its historical filename (the FEED item id) so nothing that
    # already points at data/marketing/outbox/media/<feed id>.svg moves; only the
    # ITEM id becomes canonical (ob-<as_of>-<hash>, derived from the copy).
    media = (
        [{"kind": "chart_svg", "path": media_rel, "chart_id": item_id}]
        if svg else []
    )

    # The text the publisher will actually screen (the M1 clamp's, when present).
    _post_text = (text_override if text_override is not None
                  else _ob.compose_text(headline, body))

    # ── CARD RASTER + HOST ───────────────────────────────────────────────────
    # Runs BEFORE the value gate so `has_media` is the truth (a card nobody can
    # fetch is not media) and before make_item so the media_url rides on the item
    # the queue stores. Skipped on dry_run: a dry run writes nothing, and this
    # step is a Chrome raster plus an R2 upload.
    if media and not dry_run:
        _MEDIA_HOST_TALLY["cards"] += 1
        if _host_card_media(media[0], svg, item_id=item_id, as_of=as_of, root=root):
            _MEDIA_HOST_TALLY["hosted"] += 1
        else:
            _MEDIA_HOST_TALLY["unhosted"] += 1
            _cashtags = sorted(set(_CASHTAG_RE.findall(_post_text)))
            if _cashtags:
                # A CASHTAG POST WITHOUT A PICTURE DOES NOT SHIP (operator
                # 2026-07-30). Enqueuing it would burn a queue slot on an item
                # the publisher quarantines as a bare cashtag post, so refuse it
                # here where the caller's skip census can name the reason.
                _MEDIA_HOST_TALLY["unhosted_refused"] += 1
                print("::warning title=press-lane-card-unhosted::"
                      f"{item_id}: card could not be hosted (no media_url) and the "
                      f"copy names {' '.join(_cashtags)} — not enqueued", flush=True)
                if refusal is not None:
                    refusal["reason"] = "media_unhosted"
                    refusal["violations"] = list(_cashtags)
                return None
            # No cashtag: the post is prose the publisher ships text-only, so
            # drop the unreachable media entry rather than hand the queue a
            # pointer to a picture that will never resolve.
            print("::warning title=press-lane-card-unhosted::"
                  f"{item_id}: card could not be hosted (no media_url) — posting "
                  "text-only (no cashtag in the copy)", flush=True)
            media = []

    _source: dict = {
        "lane": "press",
        "feed_item_id": item_id,
        "story_key": story_key,
        **provenance,
    }
    # GIFT-GRIP-PROOF VERDICT (XG-W3, charter §0) — every emission carries it.
    # `source_headline` is the UPSTREAM wire headline, so the informational-
    # surplus test (§7.2: "We rewrote the headline is not an answer") actually
    # has something to compare against on this lane — the one lane where
    # restating the source is the live failure mode.
    _would_block = _ob.stamp_value_gate(
        _source,
        headline=headline,
        body=body,
        kind="breaking",
        has_media=bool(media),
        source_headline=str(provenance.get("source_headline") or ""),
        citation=str(provenance.get("url") or ""),
        cfg=cfg,
    )
    if _would_block:
        _verdict = _source.get("value_gate") or {}
        # SAY WHICH IT IS (2026-07-30). One line served both modes, so an armed
        # refusal announced itself in the conditional voice — "would abstain …
        # enforce=True" is what a dropped post looked like in the nightly log,
        # and a reader scanning for trouble sees a rehearsal. A post that does
        # not ship is a ::warning, not a ::notice.
        _enforced = _ob._value_gate_enforced(cfg, "breaking")
        _why = ",".join(_verdict.get("reasons") or [])
        if _enforced:
            print("::warning title=press-lane-value-gate::"
                  f"{item_id}: ABSTAINED, not posted ({_why})", flush=True)
        elif not _ob.value_gate_kind_is_measured(cfg, "breaking"):
            # The kind is outside the armed set: the verdict is EVIDENCE being
            # collected, not a judgment being applied. Say so, or the next
            # reader arms it on a corpus that never contained this kind.
            print("::notice title=press-lane-value-gate::"
                  f"{item_id}: abstains on an UNMEASURED kind (breaking) — "
                  f"recorded, post ships ({_why})", flush=True)
        else:
            print("::notice title=press-lane-value-gate::"
                  f"{item_id}: would abstain ({_why}) — shadow mode, post ships",
                  flush=True)
        if _enforced:
            return None

    try:
        item = _ob.make_item(
            account=account,
            kind="breaking",
            text=_post_text,
            as_of=as_of,
            media=media,
            scheduled_at="immediate",
            priority=_BREAKING_PRIORITY,
            provenance="press_lane",
            source=_source,
            now=now,
        )
    except ValueError as exc:
        print(f"::warning title=press-lane-item-invalid::{item_id}: {exc}", flush=True)
        return None

    # Fields the canonical schema has no slot for but the breaking rail reads.
    # Additive: validate_item does not reject extra keys, and each is load-bearing
    # downstream — `immediate` is the legacy share-now marker, `cta_suppress`
    # steers the card footer, and headline/body keep the two halves separately
    # readable (the rail and the admin preview want them apart).
    item["immediate"] = True
    item["cta_suppress"] = bool(cta_suppress)
    item["headline"] = headline
    item["body"] = body

    errors = _ob.validate_item(item)
    if errors:
        print(f"::warning title=press-lane-item-invalid::{item_id}: {errors[0]}",
              flush=True)
        if refusal is not None:
            refusal["reason"] = "item_invalid"
        return None

    # ── LAST GATE: house language law (doctrine v3 §9a) ───────────────────────
    # The SAME screen the publisher runs on every due item, run here at the lane's
    # single enqueue choke point. Two things this catches that nothing upstream
    # can: a source headline that arrives carrying an em dash (the headline is
    # copied verbatim into the post text), and any FUTURE vintage of this lane
    # that composes a body some new way. Without it the item enqueues, sits in the
    # queue, and is quarantined at post time — a burnt LLM call, a burnt queue
    # slot, and a verdict nobody reads until the publisher log. Screening BEFORE
    # the dry_run return is deliberate: a dry run must report the same verdict a
    # live run would, and a doomed item must not write its media SVG.
    # BOTH the posted text and the full pair: the M1 clamp can trim a sentence
    # out of `text`, and headline/body still ship to the rail and the admin
    # preview. A token that survives on either surface is a token that shipped.
    _lang = _banned_language(item.get("text", ""))
    _full = _ob.compose_text(headline, body)
    if not _lang and _full != item.get("text", ""):
        _lang = _banned_language(_full)
    if _lang:
        print("::warning title=press-lane-banned-language::"
              f"{item_id}: refused by the house language law: "
              f"{', '.join(_lang[:4])}", flush=True)
        if refusal is not None:
            refusal["reason"] = "banned_language"
            refusal["violations"] = list(_lang)
        return None

    if dry_run:
        return item

    if svg:
        media_path = root / _MEDIA_DIR / f"{item_id}.svg"
        media_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=media_path.parent, suffix=".svg.tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(svg)
            os.replace(tmp_path, media_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    result = _ob.enqueue(item, root, cfg=cfg, spool=spool)
    if result != "queued":
        print(f"::warning title=press-lane-not-queued::{item_id} refused by the "
              f"outbox: {result}", flush=True)
        return None
    return item


_RECENT_OPENERS_KEEP = 3   # per-account no-repeat window depth (only [-1] gates)


def _corroboration_chip(n_sources: int, corr_class: str) -> str:
    """Honest corroboration chip for the rail (§6: never present hearsay as fact).

    A user-facing surface must not present a single-source relay as confirmed:
        direct-quote (mirror-verified own post) -> "verified"
        >=2 independent sources                 -> "N sources"
        single-source hearsay                   -> "reports"
    """
    if corr_class == "direct-quote":
        return "verified"
    if n_sources >= 2:
        return f"{n_sources} sources"
    return "reports"


# m2: plain-word class labels (EN + ZH) so the B4b rail client renders a human
# label and NEVER the raw event_class slug. `class` still carries the slug for
# machine use; label_en/label_zh are the display strings. Any class not listed
# falls back to the "none" -> Wire/快讯 entry (never a bare slug leak).
_CLASS_LABELS: dict[str, tuple[str, str]] = {
    "macro_print": ("Macro", "宏观"),
    "policy": ("Washington", "政策"),
    "geopolitical": ("Geopolitics", "地缘"),
    "company_news": ("Companies", "公司"),
    "earnings": ("Companies", "公司"),
    "none": ("Wire", "快讯"),
}
_CLASS_LABEL_FALLBACK: tuple[str, str] = _CLASS_LABELS["none"]


def _class_labels(event_class: str) -> tuple[str, str]:
    """(label_en, label_zh) for an event_class slug; Wire/快讯 for anything unlisted."""
    return _CLASS_LABELS.get(str(event_class), _CLASS_LABEL_FALLBACK)


def _rail_order_value(scored_item: dict, *, rank_ordering: bool) -> float:
    """The value this tick ordered by, for the INTERNAL `_rail_order` return map.

    Mirrors run_press_tick's own sort so a map folded across ticks stays coherent
    with the lane's ordering: rank_score when the ranker is armed (dark by
    default), else salience. Ties keep their recency position downstream, which
    is exactly what a stable sort gives.

    NEVER a payload field. The one consumer is the VPS daemon's non-public
    wire_rank sidecar, whose only expression of rank is ELEMENT ORDER — no number
    from here reaches wires.json or any served surface. Lives OUTSIDE the rail
    builder on purpose: that function's source is scanned by
    tests/test_marketing_scoring_brain.py::TestNoScoreIsUserFacing.
    """
    def _num(key: str) -> float:
        try:
            return float(scored_item.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return _num("rank_score") if rank_ordering else _num("salience")


def _build_rail_item(
    scored: dict,
    now: datetime,
    emitted_bodies: dict[str, dict],
    *,
    corr: dict,
    now_iso: str,
    window_s: int,
    quotes_store: dict | None,
    tape_cfg: dict,
    wire_voice_enabled: bool,
) -> dict:
    """Build one wires.v1 rail item for a scored press item.

    An item that emitted to X reuses its fully-composed body (opener + summary +
    attribution + tape). A rail-only item (digest-class or below the X post floor)
    gets a DETERMINISTIC display text — headline + attribution + tape — so this
    builder makes no LLM call of its own.

    BOTH paths end the text with " · {tape_stamp}" when a stamp exists, and the
    stamp also ships as its own field. The news.html rail therefore strips that
    tail for display and re-renders the stamp from the structured field, which is
    the only way it can carry its window in words and be translated.
    """
    iid = str(scored.get("id", ""))
    corr_class = str(scored.get("corroboration_class", "hearsay"))
    register = "markets"
    if wire_voice_enabled:
        try:
            from engine.marketing.wire_voice import derive_register  # noqa: PLC0415
            register = derive_register(scored)
        except Exception:  # noqa: BLE001
            register = str(scored.get("event_class", "none"))

    # Independent-source count for the chip.
    ck = _corroboration_key(scored)
    n_sources = len(corr.get(ck, {}).get("sources", []))

    hit = emitted_bodies.get(iid)
    if hit is not None:
        text_en = hit["text"]
        tape_stamp = hit.get("tape_stamp", "")
        attribution = hit.get("attribution", "")
        register = hit.get("register", register)
    else:
        # Deterministic rail-only text. Attribution comes from the corroboration
        # decision so the rail never presents hearsay as fact.
        from engine.marketing.press_corroboration import (  # noqa: PLC0415
            corroboration_decision,
        )
        window_ok = _within_window(
            corr.get(ck, {}).get("first_ts", now_iso), now, window_s
        )
        decision = corroboration_decision(
            scored, corroborated_sources=n_sources, window_ok=window_ok
        )
        attribution = decision.get("attribution", "")
        headline = str(scored.get("headline", "")).strip()
        tape_stamp = ""
        if wire_voice_enabled and quotes_store is not None:
            try:
                from engine.marketing.tape_stamp import stamp_clause  # noqa: PLC0415
                tape_stamp = stamp_clause(scored, quotes_store, now=now, cfg=tape_cfg)
            except Exception:  # noqa: BLE001
                tape_stamp = ""
        text_en = headline
        if attribution:
            # B1: double hyphen, never an em dash. The rail text and the X post
            # text are ONE string on the emitted path (the rail reuses the
            # composed body), so the two joins must agree or the rail would
            # display a form the publisher's language gate rejects.
            text_en = f"{text_en} -- {attribution}"
        if tape_stamp:
            text_en = f"{text_en} · {tape_stamp}"

    event_class = str(scored.get("event_class", "none"))
    label_en, label_zh = _class_labels(event_class)
    item: dict = {
        "id": iid,
        "ts": str(scored.get("published_at", "")) or now_iso,
        # `class` = machine slug; label_en/label_zh = plain-word display (m2). The
        # B4b client renders the labels and never needs the slug.
        "class": event_class,
        "label_en": label_en,
        "label_zh": label_zh,
        "register": register,
        # m2: spec field name is `en` (was text_en).
        "en": text_en,
        "attribution": attribution,
        "corroboration": _corroboration_chip(n_sources, corr_class),
        # ADDITIVE (Mastermind brain coordination, 2026-07-29): the plain
        # publisher name, a display-tier fact the page may ignore. The internal
        # ranking number was requested alongside it and DECLINED — wires.json
        # is served to registered users, and TestNoScoreIsUserFacing scans this
        # very function to keep every such number out of it; the brain's reader
        # falls back to recency ordering by design. The sanctioned ranked view
        # is the non-public wire_rank sidecar, never this payload.
        "source_name": str(
            scored.get("source_name") or scored.get("source") or "")[:120],
    }
    if tape_stamp:
        item["tape_stamp"] = tape_stamp
    return item


def _apply_wire_voice(
    scored: dict,
    base_summary: str,
    attribution: str,
    *,
    account: str,
    recent_openers: dict,
    quotes_store: dict | None,
    fmt: str,
    voice_cfg: dict,
    format_cfg: dict,
    tape_cfg: dict,
    now: datetime,
) -> tuple[str, str, str, str, str, bool]:
    """Run the B2-COPY voice pass over one item's summary.

    `fmt` is the already-picked format ("flash"|"wire_deep") from the caller — the
    picker runs BEFORE the summarizer so the wire_deep two-paragraph instruction
    can steer the LLM prompt (the picker is deterministic code either way).

    Returns (body, register, opener, wire_format, tape_stamp, applied). `applied`
    is False when the composed post fails the length budget after the voice pass —
    the caller then keeps the plain B1 body. The AI-tell check is applied to the
    LLM summary text; a hit strips the offending prose to the deterministic
    headline, never posting the AI-tell'd summary.

    Mutates recent_openers[account] in place (records the chosen opener), so the
    daemon persists the no-repeat window across ticks.
    """
    from engine.marketing import wire_format as wf  # noqa: PLC0415
    from engine.marketing import wire_voice as wv  # noqa: PLC0415

    # 1. AI-tell guard on the summary prose. A hit means the LLM summary reads as
    #    generated — drop it to the deterministic headline so we never ship a tell.
    summary_text = str(base_summary or "")
    if summary_text and wv.ai_tell_hits(summary_text):
        summary_text = str(scored.get("headline", "")).strip()

    # 3. Opener rotation with a per-account no-repeat window.
    acct_recent = recent_openers.setdefault(account, [])
    opener, register = wv.select_opener(
        scored, account=account, recent_openers=acct_recent, cfg=voice_cfg
    )

    # 4. Tape stamp — threshold-gated; missing/stale/quiet => "".
    tape = ""
    if quotes_store is not None:
        from engine.marketing.tape_stamp import stamp_clause  # noqa: PLC0415
        tape = stamp_clause(scored, quotes_store, now=now, cfg=tape_cfg)

    # 5. Compose + length-budget validate.
    post = wv.compose_post(
        opener=opener, summary=summary_text, attribution=attribution,
        tape_stamp=tape,
    )
    violations = wf.validate_length(post, fmt, cfg=format_cfg)
    if violations:
        # A wire_deep post UNDER the 400-char minimum is just a long flash — the
        # source did not fill two paragraphs. Downgrade to flash rather than
        # decline, so the voice (opener + tape) still ships. (An OVER-budget deep
        # is a real overshoot and is not downgraded — it falls through below.)
        if fmt == "wire_deep" and all("< min" in v for v in violations):
            fmt = "flash"
            violations = wf.validate_length(post, fmt, cfg=format_cfg)
        if violations:
            # Retry once WITHOUT the opener (the cheapest length to shed); if still
            # over budget, the voice pass declines and the caller keeps the plain
            # body — we never ship an over-budget post.
            post_no_opener = wv.compose_post(
                opener="", summary=summary_text, attribution=attribution,
                tape_stamp=tape,
            )
            if not wf.validate_length(post_no_opener, fmt, cfg=format_cfg):
                opener = ""
                post = post_no_opener
            else:
                return base_summary, register, "", fmt, "", False

    # Record the chosen opener into the account's no-repeat window (newest last).
    acct_recent.append(opener)
    del acct_recent[:-_RECENT_OPENERS_KEEP]

    return post, register, opener, fmt, tape, True


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_press_tick
# ─────────────────────────────────────────────────────────────────────────────

def run_press_tick(
    items: list[dict],
    *,
    root: Path | str,
    now: datetime,
    cfg: dict,
    press_cfg: dict,
    state: dict[str, Any],
    seen_ids: set[str] | None = None,
    dry_run: bool = False,
    prime: bool = False,
    spool: bool = False,
    llm_override: Any = None,
) -> dict[str, list[dict]]:
    """Run one press-lane tick over a batch of FeedItems.

    Args:
        items:      FeedItems from press_providers.poll_all + wire RSS poll_all.
        root:       repo root (outbox output dirs).
        now:        current UTC datetime (injectable for tests).
        cfg:        full marketing.yml dict (for breaking.llm gating + relevance cfg).
        press_cfg:  parsed press_sources.yml dict (satire list, wire caps).
        state:      daemon-local mutable state (flagship counter, corroboration
                    seen, transient-refusal retry tally).
        seen_ids:   ids already emitted (dedupe). When None, no cross-tick dedupe
                    (the daemon passes its persisted seen-set).
        dry_run:    compute everything, write nothing.
        spool:      True routes the emission to the GITIGNORED daemon-local
                    outbox spool (outbox._host_items_path) instead of the
                    git-TRACKED items.jsonl. The VPS daemon sets it so a press
                    tick cannot dirty the checkout its 3-minute `git pull`
                    depends on. Read-side guards are unaffected — they read the
                    union of both files.
        prime:      COLD-START (m2). On the very first run — no cursor/seen state —
                    the batch is a full history snapshot, not real-time news;
                    emitting it would flood. When True the tick runs the full
                    pipeline (so the seen-ledger primes and provider cursors, which
                    the provider fetch already advanced to newest, stay advanced)
                    but emits NOTHING and logs a start-of-line "[press] primed".
                    The daemon sets this on true cold-start only.
        llm_override: test seam forwarded to build_breaking_payload.

    Returns {emitted, skipped, digest, blocked, rail, _rail_order, intelligence,
    corpus, _seen}. Underscore keys are INTERNAL and must never be served.

    `corpus` (XG-W5) is one row per item the lane SAW — ingested items with their
    full `_components`, gate-dropped items with their reason. The lane only
    RETURNS them; the daemon persists them to the gitignored host-local corpus
    the golden-set exporter and the precision@20 harness read. A dry run
    therefore computes the rows and writes nothing, like every other side effect
    on this path.
    """
    from engine.marketing.breaking_relevance import score_item
    from engine.marketing.breaking_summary import build_breaking_payload
    from engine.marketing.press_corroboration import corroboration_decision

    root = Path(root)
    # PER-TICK card census. Zeroed here so the number this tick returns is this
    # tick's, not a process-lifetime running total the daemon would misread.
    reset_media_host_stats()
    breaking_cfg = cfg.get("breaking", {}) if isinstance(cfg, dict) else {}
    wire_cfg = (press_cfg or {}).get("wire", {}) if isinstance(press_cfg, dict) else {}
    top_k = _resolve_top_k(breaking_cfg, wire_cfg)
    floor = float(wire_cfg.get("flagship_salience_floor", _DEFAULT_FLAGSHIP_FLOOR))
    window_s = int(wire_cfg.get("corroboration_window_s", _DEFAULT_CORROBORATION_WINDOW_S))
    rail_floor = float(wire_cfg.get("rail_salience_floor", _DEFAULT_RAIL_FLOOR))
    rail_max = int(wire_cfg.get("rail_max_items", _DEFAULT_RAIL_MAX_ITEMS))

    # B2-COPY wire-voice config lives under press_sources.yml `wire.voice`,
    # `wire.format`, `wire.tape` (all optional — absent => deterministic defaults,
    # so a B1-shaped config is a clean no-op enhancement). Loaded once per tick.
    voice_cfg = wire_cfg.get("voice", {}) if isinstance(wire_cfg, dict) else {}
    format_cfg = wire_cfg.get("format", {}) if isinstance(wire_cfg, dict) else {}
    tape_cfg = wire_cfg.get("tape", {}) if isinstance(wire_cfg, dict) else {}
    wire_voice_enabled = bool(voice_cfg.get("enabled", True))

    # Live-quote store for tape stamps — read ONCE (fail-soft: None => no stamps).
    quotes_store = None
    if bool(tape_cfg.get("enabled", True)):
        try:
            from engine.marketing.tape_stamp import load_quotes  # noqa: PLC0415
            quotes_store = load_quotes(tape_cfg.get("quote_store_paths"), root=root)
        except Exception:  # noqa: BLE001
            quotes_store = None

    # Per-account opener no-repeat window (persisted in daemon-local state so it
    # survives across ticks). recent[account] = [last openers], newest last.
    recent_openers_state = state.setdefault("recent_openers", {})

    blocklist_lower = {s.lower() for s in ((press_cfg or {}).get("satire_blocklist") or [])}
    seen = set(seen_ids or set())

    # ── PER-DESK daily wire budgets (W4d) ────────────────────────────────────
    # `flagship_counter` is KEPT and still advanced for the routing default: the
    # Actions lane commits it in cursors.json, and three tests in
    # tests/test_marketing_press_wire.py assert it survives the state-ceiling
    # trim. It is now a VIEW of the primary desk's row in `wire_day_counts`,
    # not the network-wide budget it used to be — the old shape was a single
    # counter named for one account while bounding all of them, which is the
    # defect the XG-W2 TODO at step 5 recorded and W4d closes.
    day = _day_key(now)
    counter = state.setdefault("flagship_counter", {"day": day, "count": 0})
    if counter.get("day") != day:
        counter["day"] = day
        counter["count"] = 0

    wire_counts_state = state.setdefault("wire_day_counts", {"day": day, "counts": {}})
    if wire_counts_state.get("day") != day:
        wire_counts_state["day"] = day
        wire_counts_state["counts"] = {}
    day_counts: dict = wire_counts_state.setdefault("counts", {})

    # The live wire desks and their budgets, resolved ONCE per tick. Budget =
    # stricter-of(top-K, the desk's ramp cap) — see _ramp_post_caps.
    spill_targets = _spill_pool(cfg, root) if top_k > 0 else []
    ramp_caps = _ramp_post_caps(cfg, now, root) if top_k > 0 else {}
    primary_desk = _FALLBACK_ACCOUNT
    try:
        from engine.marketing.wire_routing import default_account  # noqa: PLC0415
        primary_desk = default_account(cfg)
    except Exception:  # noqa: BLE001
        pass

    def _budget(acct: str) -> int:
        """This desk's wire budget for today."""
        cap = ramp_caps.get(acct)
        return top_k if cap is None else min(top_k, cap)

    # HEADROOM CENSUS — a NAMED, PERSISTED counter, not a local dict that dies
    # with the tick. save_cursors (scripts/marketing_press_wire.py) writes every
    # non-underscore state key to the COMMITTED cursors.json, so a day that
    # dropped surplus wire items leaves evidence in the repo rather than in a
    # log line nobody folds. This is the same defect class as the mover bug that
    # hid twelve nights of lost posts: a silent `continue` is not a decision, it
    # is a leak.
    census = state.setdefault("wire_headroom", {"day": day, "spilled": {},
                                                "exhausted": 0})
    if census.get("day") != day:
        census["day"] = day
        census["spilled"] = {}
        census["exhausted"] = 0
    census.setdefault("spilled", {})
    census.setdefault("exhausted", 0)
    exhausted_before = int(census.get("exhausted") or 0)

    # Transient-refusal retry tally: emission_key -> CONSECUTIVE refusals whose
    # reason is environmental (see _TRANSIENT_REFUSALS). Lives in daemon state
    # rather than in `seen` on purpose — `seen` is the "never again" ledger and
    # these items are explicitly coming back next tick. Cleared the moment the
    # story emits or is settled by a copy-property refusal.
    transient_tries: dict = state.setdefault("transient_refusals", {})

    # Corroboration window ledger: claim_key -> {sources:list, first_ts:iso}.
    # Prune entries older than the window so the state file cannot grow unbounded
    # (a claim past its corroboration window can never gain a within-window peer).
    corr = state.setdefault("corroboration", {})
    for ck in [k for k, e in corr.items()
               if not _within_window(e.get("first_ts"), now, window_s)]:
        del corr[ck]

    emitted: list[dict] = []
    skipped: list[dict] = []
    digest: list[dict] = []
    blocked: list[dict] = []
    rail: list[dict] = []   # B4a: rail-eligible items (lower floor, incl. digest)
    emitted_bodies: dict[str, dict] = {}   # id -> composed text for rail reuse
    intelligence: list[dict] = []  # evidence-first story packets for the live desk

    # ── XG-W5 scoring brain (IS-W2) ───────────────────────────────────────────
    # L0 story spine + L1 feature stores live in the SAME daemon-local state dict
    # the corroboration window and the flagship counter already use — gitignored
    # data/marketing/press/state.json on the VPS. Zero repo writes intraday; the
    # nightly stays the sole advancer of every tracked ledger.
    scoring_cfg = breaking_cfg.get("scoring", {}) if isinstance(breaking_cfg, dict) else {}
    if not isinstance(scoring_cfg, dict):
        scoring_cfg = {}
    gate_cfg = breaking_cfg.get("garbage_gate", {}) if isinstance(breaking_cfg, dict) else {}
    if not isinstance(gate_cfg, dict):
        gate_cfg = {}

    # Review F-1: one corpus row per ITEM per rolling window, not one per tick.
    should_row = _corpus_gate(
        state, now=now,
        window_h=float(scoring_cfg.get("corpus_row_window_h",
                                       _DEFAULT_CORPUS_ROW_WINDOW_H)),
    )

    spine = None
    corpus = None
    authority = None
    tone_lookup: dict = {}
    if bool(scoring_cfg.get("enabled", True)):
        try:
            from engine.marketing.signal_features import (  # noqa: PLC0415
                AuthorityStore, SignalCorpus, load_tone_lookup,
            )
            from engine.marketing.story_spine import StorySpine, load_encoder  # noqa: PLC0415

            spine = StorySpine(
                state.setdefault("story_spine", {}),
                cfg=scoring_cfg.get("story_spine", {}),
                # Semantic pass: OFF unless a LOCAL model artifact exists. Never a
                # runtime download on any render/nightly/daemon path.
                encoder=load_encoder(scoring_cfg.get("semantic", {}), root=root),
            )
            corpus = SignalCorpus(state.setdefault("signal_corpus", {}),
                                  cfg=scoring_cfg.get("corpus", {}))
            authority = AuthorityStore(state.setdefault("source_authority", {}),
                                       cfg=scoring_cfg.get("authority", {}))
            tone_lookup = load_tone_lookup(root, cfg=scoring_cfg.get("tone", {}))
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=scoring-brain-unavailable::"
                  f"{type(exc).__name__}: {exc} — falling back to salience-only",
                  flush=True)
            spine = corpus = authority = None

    # 1. GARBAGE GATE (XG-W5 P0 drop) + dedupe.
    # The gate runs FIRST — before the story spine, before any feature, before
    # any LLM spend — because the cheapest way to rank a horoscope is to never
    # rank it. It REUSES the existing satire blocklist (one list, one rule) and
    # adds source blocklist / promo-spam / paywalled-stub / non-story detectors.
    # Every drop is recorded in `blocked` with its reason, the historical P0
    # shape, so the daemon's existing logging and the admin ledger are unchanged.
    #
    # Dedupe on the MIRROR-COLLAPSED emission key (M1): the same Truth post seen
    # via two mirrors shares one truth_status_id, so the second mirror is a
    # dedupe skip, not a second emission. Also collapse within a single tick so a
    # trumpstruth + cnn_truth_backfill pair arriving together emits once.
    ingest: list[dict] = []
    seen_this_tick: set[str] = set()
    gate_drops: dict[str, int] = {}
    gate_rows: list[dict] = []
    for it in items:
        iid = str(it.get("id", ""))
        drop = _garbage_check(it, gate_cfg=gate_cfg, blocklist_lower=blocklist_lower)
        if drop is not None:
            reason = str(drop.get("reason", "garbage"))
            gate_drops[reason] = gate_drops.get(reason, 0) + 1
            blocked.append({"id": iid, "reason": reason,
                            "detail": str(drop.get("detail", "")),
                            "headline": str(it.get("headline", ""))[:120]})
            if should_row(iid):
                gate_rows.append(_corpus_row(
                    dict(it), outcome=f"blocked:{reason}",
                    now_iso=now.astimezone(timezone.utc).isoformat(),
                ))
            continue
        ekey = _emission_key(it)
        if ekey and (ekey in seen or ekey in seen_this_tick):
            skipped.append({"id": iid, "reason": "dedupe"})
            continue
        if ekey:
            seen_this_tick.add(ekey)
        ingest.append(it)
    if gate_drops:
        print("::notice title=press-garbage-gate::" + ", ".join(
            f"{reason}={count}" for reason, count in sorted(gate_drops.items())
        ), flush=True)

    # 2. Score everything (deterministic relevance) and register corroboration.
    #
    # ORDER MATTERS TWICE HERE:
    #  (a) the corpus observes EVERY ingested item BEFORE any of them is scored,
    #      so this tick's own arrivals are visible to the burst detector (a burst
    #      you can only see next tick is not a burst detector). `novelty` then
    #      excludes the item's own contribution from its own IDF, which is what
    #      keeps a 3-item cold-start corpus from calling everything novel.
    #  (b) the story spine assigns BEFORE scoring, because corroboration_velocity
    #      is a property of the story, not of the item.
    now_iso = now.astimezone(timezone.utc).isoformat()
    stories: dict[str, dict] = {}
    if corpus is not None or spine is not None or authority is not None:
        for it in ingest:
            iid = str(it.get("id", ""))
            if spine is not None:
                stories[iid] = spine.assign(it, now=now)
            if authority is not None:
                authority.observe(it, now=now)
            if corpus is not None:
                corpus.observe(it, now=now)
        # REFRESH the views after the whole batch is absorbed. `assign` returns
        # the story as it stood at that moment, so the FIRST item of a two-source
        # burst arriving in one tick would otherwise score source_count=1 while
        # the second scored 2 — the same story, two different corroboration
        # velocities, decided by list order. Re-deriving every view once the
        # batch is in makes the feature a property of the story, as intended.
        if spine is not None:
            for iid, view in list(stories.items()):
                sid = str(view.get("story_id", ""))
                if not sid:
                    continue
                refreshed = spine.view(sid, now=now)
                refreshed["match"] = view.get("match", "")
                refreshed["is_new"] = view.get("is_new", False)
                stories[iid] = refreshed

    scored: list[dict] = []
    for it in ingest:
        iid = str(it.get("id", ""))
        s = score_item(
            it, now=now, cfg=breaking_cfg, root=root,
            # L1 CONTEXT — the production call site. Without it score_item still
            # emits `_components`, with every feature reporting its own null
            # state; with it the six deterministic features are live.
            context={
                "story": stories.get(iid),
                "corpus": corpus,
                "authority": authority,
                "tone_lookup": tone_lookup,
            },
        )
        # Register this source against its claim key for corroboration counting.
        ck = _corroboration_key(s)
        entry = corr.setdefault(ck, {"sources": [], "first_ts": now_iso})
        src = _independent_source(s)
        if src and src not in entry["sources"]:
            entry["sources"].append(src)
        scored.append(s)

    # Bound the persisted state (TTL + hard caps) every tick, so a busy news week
    # cannot grow data/marketing/press/state.json without limit.
    try:
        if spine is not None:
            spine.prune(now)
        if corpus is not None:
            corpus.prune(now)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=scoring-brain-prune::{type(exc).__name__}: {exc}",
              flush=True)

    # 3. ORDER the queue.
    #
    # ══ GATE ORDERING (charter §0 / masterplan IS-W2) ═════════════════════════
    # A SCORE MAY REORDER AND DEPRIORITIZE. IT MAY NEVER PUBLISH.
    #
    # This sort is the ONLY thing rank_score does in this lane. Everything that
    # decides whether an item may go out runs AFTER it and never reads it:
    #   step 4  corroboration_decision(...)      -> digest/attributed/instant
    #   step 5  salience < floor / top-K counter -> salience, never rank_score
    #   step 5c story_lock.check(...)            -> one-conversation-one-owner
    #   step 6+ build_breaking_payload -> outbox.stamp_value_gate ->
    #           outbox.make_item/validate_item -> outbox.enqueue (id-dedup,
    #           7-day text-dedup, same-account + cross-account near-dup,
    #           sentinel caps, cadence resolver)
    # Reordering changes WHICH surviving item takes a scarce slot; it cannot
    # create a slot, cannot clear a gate, and cannot raise salience (the L1
    # demotion multiplier in breaking_relevance is clamped at 1.0). No score is
    # ever written to a user-facing surface — the news.html rail item built below
    # copies named display fields only, never `_components` or `rank_score`.
    #
    # rank_ordering ships DARK (default false). Arming it is one config flip,
    # and the masterplan gates that flip on the golden set: the scorer's
    # precision@20 must beat salience-only ordering before it displaces it.
    # ══════════════════════════════════════════════════════════════════════════
    rank_ordering = bool(scoring_cfg.get("rank_ordering", False))
    if rank_ordering:
        scored.sort(key=lambda x: (float(x.get("rank_score", 0.0) or 0.0),
                                   float(x.get("salience", 0.0) or 0.0)),
                    reverse=True)
    else:
        scored.sort(key=lambda x: x.get("salience", 0.0), reverse=True)

    # COLD-START (m2): on the very first run the batch is a full history snapshot
    # (mirror archives, twitterapi.io last_tweets with no prior cursor), NOT
    # real-time news — emitting it would flood. "Prime, don't post": record every
    # item's emission key so the NEXT tick dedupes the history away, keep the
    # advanced provider cursors + registered corroboration window, emit nothing.
    if prime:
        for s in scored:
            seen.add(_emission_key(s))
        print(f"[press] primed | {len(scored)} items seen, 0 emitted (cold start)",
              flush=True)
        return {
            "emitted": [],
            "skipped": [{"id": str(s.get("id", "")), "reason": "primed"} for s in scored],
            "digest": [],
            "blocked": blocked,
            "rail": [],
            "_rail_order": {},
            "intelligence": [],
            # A primed batch is a history snapshot — exactly the corpus a first
            # labeling batch wants, so the rows ship even though nothing emitted.
            "corpus": list(gate_rows) + [
                _corpus_row(s, outcome="primed", now_iso=now_iso) for s in scored
                if should_row(str(s.get("id", "")))
            ],
            "_seen": sorted(seen),
        }

    for s in scored:
        iid = str(s.get("id", ""))
        ck = _corroboration_key(s)
        entry = corr.get(ck, {"sources": [], "first_ts": now_iso})
        n_sources = len(entry.get("sources", []))
        window_ok = _within_window(entry.get("first_ts"), now, window_s)

        # 4. Corroboration gate.
        decision = corroboration_decision(
            s, corroborated_sources=n_sources, window_ok=window_ok
        )
        if decision["gate"] == "digest":
            digest.append({"id": iid, "reason": decision["reason"],
                           "salience": s.get("salience"), "headline": s.get("headline")})
            continue

        # 5. Wire admission: salience floor, market nexus, per-desk daily budget.
        #
        # ⚠ THESE COUNTERS ARE THE END-TO-END VOLUME BOUND ON THE WIRE RAIL.
        # Trace the composition honestly: press items are emitted with
        # scheduled_at="immediate", and an immediate item is EXEMPT from the
        # per-account daily cap, the tier ramp, the global 10-minute floor
        # (operator 2026-07-27, "breaking has no limits") and — by
        # cadence_resolver.exempt_immediate, which defaults true for the same
        # reason — from the XG-W2 cadence resolver as well. Nothing downstream
        # bounds how many of these go out in a day. So `wire.flagship_top_k_per_day`
        # here, plus the earnings lane's own per-event key space (one item per
        # ticker+quarter, deduped by the seen ledger), are the ONLY end-to-end
        # limits on the immediate rail.
        #
        # This is documented, not "fixed": the exemption is a standing operator
        # ruling, and adding a second competing cap here would quietly overrule
        # it. If the immediate rail ever needs bounding, the lever that exists is
        # cadence_resolver.exempt_immediate: false — one config flip, already
        # tested — not a new knob.
        #
        # CLOSED (W4d, was TODO(xg-w2-review)): the budget is now PER ROUTED
        # DESK, not one counter named for one account while bounding all of
        # them. Under the old shape, arming mastermind_news would have made the
        # wire desk share flagship's 3/day — the desk whose entire job is the
        # wire would have SUBTRACTED from the flagship rather than adding to the
        # network. Each desk now draws its own budget, stricter-of(top-K, its
        # ramp cap), and surplus spills across desks instead of being dropped.
        if s.get("salience", 0.0) < floor:
            skipped.append({"id": iid, "reason": "below_flagship_floor",
                            "salience": s.get("salience")})
            continue
        if _no_market_nexus(s):
            # A MARKETS ACCOUNT DOES NOT RELAY POLITICS FOR ITS OWN SAKE.
            #
            # Lowering flagship_salience_floor 70 -> 30 on 2026-07-31 was right —
            # at 70 only `macro_print + official` could ever clear (55 + 15,
            # exactly), so the wire was a BEA-print relay and company news,
            # tariffs and every other class were excluded by arithmetic. But the
            # floor is a proxy for "worth posting", not for "about markets", and
            # dropping it admitted the whole `policy` class on salience alone.
            #
            # That class holds both of these, and they score the same:
            #   "Trump announces 50% tariff on Chinese semiconductors"  -> tariffs
            #   "how much Money and Prestige the Supreme Court has lost" -> nothing
            #
            # The first is the reason this lane exists. The second is a political
            # grievance with no market nexus, and the dry run on 2026-07-31 booked
            # it to the FLAGSHIP account. The separating signal was already
            # computed and thrown away: `matched`. The tariff item matches
            # macro_keys=['tariffs']; the grievance matches no ticker, no sector
            # and no macro key at all.
            #
            # Scoped to the two classes the floor change opened. company_news and
            # macro_print are untouched — they are about markets by construction,
            # and a company story whose name the universe happens not to carry
            # must still ship.
            skipped.append({"id": iid, "reason": "no_market_nexus",
                            "salience": s.get("salience"),
                            "event_class": s.get("event_class")})
            continue
        # 5b. ROUTE (XG-W2). Which account owns this wire class? Config, not a
        #     module constant — see engine/marketing/wire_routing.py.
        #
        # ROUTING NOW PRECEDES THE BUDGET CHECK (W4d) and that order is the
        # feature: you cannot charge a desk's budget before you know which desk
        # owns the item. The old order charged one global counter and then asked
        # who it belonged to.
        account = _route_account(s, cfg=cfg, root=root)

        # 5b-ii. PER-DESK BUDGET + CROSS-DESK SPILL.
        #
        # THE SURPLUS MOVES ACROSS THE NETWORK, NOT ONTO THE FLAGSHIP. Piling a
        # busy day's whole wire onto one desk is a worse product than a
        # distributed one, and the operator ruling that opened this budget said
        # so explicitly. `_spill_pool` is wire_routing's DECLARED wire-desk
        # roster resolved through the same liveness read `route` uses, so a dark
        # desk can never be selected and a persona desk is never eligible (§4:
        # wire accounts relay, they do not take stances).
        #
        # A spill is announced ONCE per (from, to) pair per process — the daemon
        # ticks every ~90s and would otherwise bury the Actions summary in
        # identical lines.
        if int(day_counts.get(account, 0)) >= _budget(account):
            spill = _pick_spill_account(account, pool=spill_targets,
                                        budgets={a: _budget(a) for a in spill_targets},
                                        counts=day_counts)
            if not spill:
                # COUNTED, NOT SILENT. The census below is persisted to the
                # committed cursors.json; the reason string is unchanged so the
                # existing skip taxonomy and its test keep meaning what they did.
                census["exhausted"] = int(census.get("exhausted") or 0) + 1
                skipped.append({
                    "id": iid, "reason": "flagship_top_k_reached",
                    "salience": s.get("salience"), "account": account,
                    "detail": "every live wire desk has spent its daily budget: "
                              + ", ".join(f"{a}={day_counts.get(a, 0)}/{_budget(a)}"
                                          for a in (spill_targets or [account])),
                })
                continue
            pair = (account, spill)
            if pair not in _WARNED_SPILL:
                _WARNED_SPILL.add(pair)
                # BARE, line-start, flushed (house law): routed through a logger
                # this module's format prefixes the line and GitHub drops the
                # annotation silently. A desk publishing another desk's routed
                # class is exactly what must not be silent.
                print(f"::notice title=press-lane-wire-spill::{account!r} has "
                      f"spent its daily wire budget ({_budget(account)}) — "
                      f"surplus is routing to {spill!r} "
                      f"({day_counts.get(spill, 0)}/{_budget(spill)} used). "
                      f"Raise breaking.flagship_top_k_per_day, or point more "
                      f"wire_routing.classes at the desk that should own them.",
                      flush=True)
            census["spilled"][f"{account}->{spill}"] = int(
                census["spilled"].get(f"{account}->{spill}", 0)) + 1
            account = spill

        # 5c. ONE CONVERSATION, ONE OWNER (charter §2 amendment 6). The story key
        #     reuses the lane's OWN claim identity (_corroboration_key), so the
        #     lock inherits the M3 collapse that makes two differently-worded
        #     relays of one claim the same story. A second account drawing it
        #     inside the window is refused here, before any LLM spend.
        skey = _story_key_for(s, ck)
        verdict = _story_lock_check(account, skey, root=root, now=now, cfg=cfg)
        if verdict is not None and not verdict.allowed:
            skipped.append({"id": iid, "reason": "story_locked",
                            "story_key": skey, "owner": verdict.owner,
                            "account": account})
            continue

        # 6. Pick the wire FORMAT first (deterministic — code, never the LLM), so
        #    the wire_deep two-paragraph instruction can steer the summarizer. The
        #    picked format is passed into the voice pass so it is not re-derived.
        chosen_format = "flash"
        wire_llm: dict | None = None
        if wire_voice_enabled:
            try:
                from engine.marketing import wire_format as _wf  # noqa: PLC0415
                chosen_format = _wf.pick_format(s, cfg=format_cfg)["format"]
                # wire config forwarded to the LLM summarizer: tier keys (from
                # voice_cfg) + the picked format so the prompt matches the budget.
                wire_llm = dict(voice_cfg)
                wire_llm["_format"] = chosen_format
            except Exception:  # noqa: BLE001
                chosen_format = "flash"
                wire_llm = None

        # Summarize-with-citation + build the outbox-shaped payload.
        payload = build_breaking_payload(
            s, cfg, root=root, _llm_override=llm_override, wire=wire_llm
        )

        headline = payload.get("headline", "")
        summary = payload.get("summary", "")
        # Body attribution comes from the corroboration DECISION, never from the
        # mirror name (m3). For a direct-quote the decision says "on Truth Social";
        # the mirror ("via trumpstruth.org") belongs to provenance/ledger, not the
        # post body. The deterministic fallback summary ends "— {source_name}",
        # which for a mirror item names the mirror — strip that clause and replace
        # it with the decision attribution. The LLM summary (mode="llm") carries no
        # trailing source line (its prompt forbids one), so the attribution is
        # appended. Either way the body attributes the ORIGINAL surface, and the
        # mirror is named only in provenance.
        attribution = decision.get("attribution", "")
        mode = payload.get("mode", "deterministic")
        source_name = str(s.get("source_name", s.get("source", "")))
        # The summary WITHOUT the trailing "— {source_name}" fallback clause — the
        # attribution is (re)applied by the corroboration decision, and the wire
        # voice pass composes opener + attribution + tape from these parts.
        base_summary = _strip_trailing_source_clause(summary, source_name)

        # ── B2-COPY wire voice pass ────────────────────────────────────────────
        # Opener rotation (deterministic + per-account no-repeat), deterministic
        # format pick, tape stamp (threshold-gated), AI-tell rejection, length
        # budget. Any failure in this layer falls back to the plain B1 body — the
        # voice pass NEVER blocks an item that would otherwise post.
        register = s.get("event_class", "none")
        wire_format = "flash"
        opener = ""
        tape_stamp = ""
        voice_applied = False
        if wire_voice_enabled:
            try:
                body, register, opener, wire_format, tape_stamp, voice_applied = (
                    _apply_wire_voice(
                        s, base_summary, attribution,
                        account=account,
                        recent_openers=recent_openers_state,
                        quotes_store=quotes_store,
                        fmt=chosen_format,
                        voice_cfg=voice_cfg, format_cfg=format_cfg, tape_cfg=tape_cfg,
                        now=now,
                    )
                )
            except Exception:  # noqa: BLE001
                voice_applied = False

        if not voice_applied:
            # Plain B1 body (attribution appended, no opener/tape). Double hyphen:
            # same join as compose_post, same reason (the publisher quarantines
            # U+2014, and this is the path a disarmed voice pass lands on).
            if attribution:
                body = f"{base_summary} -- {attribution}"
            else:
                body = base_summary

        provenance = {
            **payload.get("provenance", {}),
            "corroboration_class": s.get("corroboration_class", "hearsay"),
            "corroboration_gate": decision["gate"],
            "corroborated_sources": n_sources,
            "salience": s.get("salience"),
            "event_class": s.get("event_class"),
            # The mirror/relay surface is recorded HERE (provenance/ledger), never
            # in the post body (m3): e.g. "via trumpstruth.org".
            "via_source": source_name,
            # B2-COPY voice metadata (feedback-loop + rail payload inputs).
            "register": register,
            "wire_format": wire_format,
            "opener": opener,
            "tape_stamp": tape_stamp,
            # XG-W5: the scoring brain's breakdown travels with the emission so a
            # re-weighting is auditable from the outbox alone. COMPACT on purpose
            # (values + rank + story id, not the verbose per-feature detail) —
            # items.jsonl is read on every publisher pass. MARKETING-INTERNAL:
            # provenance never reaches a post body or a user-facing surface.
            "scoring": _scoring_provenance(s),
        }

        # ── M1 platform clamp ─────────────────────────────────────────────────
        # The post text is headline + blank line + body, and the X cap is 280.
        # wire_deep's budget is 400-700, so every deep item was composed, queued,
        # and then quarantined by validate_postable — the format never posted
        # once. The clamp decides what X gets; `body` (full length) is what the
        # rail keeps, which is why this is computed here and not inside the
        # voice pass.
        _clamp = _clamp_for_x(headline, body, attribution=attribution,
                              tape_stamp=tape_stamp)
        if not _clamp["text"]:
            print("::warning title=press-lane-over-x-budget::"
                  f"{iid}: {_clamp['reason']}; rail keeps the full item",
                  flush=True)
            seen.add(_emission_key(s))
            skipped.append({"id": iid, "reason": "over_x_budget",
                            "account": account, "detail": _clamp["reason"]})
            # RAIL-ONLY, AT FULL LENGTH. The item did not post, but it was
            # composed, and news.html is the retention surface with no character
            # cap. Recording the composed body here is what "the rail keeps the
            # full item" means; without it the rail would fall back to the bare
            # headline line and the work would be thrown away twice.
            emitted_bodies[iid] = {"text": body, "register": register,
                                   "tape_stamp": tape_stamp,
                                   "attribution": attribution}
            continue
        if _clamp["clamped"]:
            print("::notice title=press-lane-x-clamp::"
                  f"{iid}: {_clamp['reason']}", flush=True)
            provenance["x_clamp"] = _clamp["reason"]

        _refusal: dict = {}
        out_item = _emit_outbox_item(
            root, iid, account, headline, body, payload.get("card_svg", ""),
            provenance, now,
            story_key=skey,
            cta_suppress=bool(s.get("cta_suppress", False)),
            dry_run=dry_run,
            cfg=cfg,
            spool=spool,
            refusal=_refusal,
            text_override=_clamp["text"],
        )
        if out_item is None:
            _reason = str(_refusal.get("reason") or "outbox_refused")
            _ekey = _emission_key(s)
            if _reason in _TRANSIENT_REFUSALS:
                # NOT RECORDED AS SEEN. The invariant below holds only for
                # refusals decided by the COPY; this one is decided by the
                # environment (a lost Chrome raster, an R2 blip, absent creds),
                # and marking it seen turned a five-second outage into a
                # permanent kill of a breaking story. It comes back next tick.
                #
                # The retry is COUNTED so it cannot be silent: a host that is
                # genuinely down would otherwise re-render, re-pay and re-refuse
                # the same item every tick with nothing in the summary.
                _tries = int(transient_tries.get(_ekey, 0) or 0) + 1
                transient_tries[_ekey] = _tries
                if _tries >= _TRANSIENT_RETRY_ALARM_AT and \
                        _tries % _TRANSIENT_RETRY_ALARM_AT == 0:
                    # BARE print, line-start, flushed — never through the logger
                    # (this module's format prefixes the line and GitHub then
                    # drops the annotation silently).
                    print(f"::warning title=press-lane-transient-refusal-stuck::"
                          f"{iid}: refused {_tries} ticks in a row with "
                          f"{_reason!r} — this is an ENVIRONMENT fault, not the "
                          f"copy, and every attempt paid for a raster and an LLM "
                          f"call. Check the card host (boto3 installed, R2_* set) "
                          f"rather than the story.", flush=True)
                # Bound the tally: it is a stuck-story detector, not a history.
                if len(transient_tries) > _TRANSIENT_TALLY_CAP:
                    for _stale in list(transient_tries)[:-_TRANSIENT_TALLY_CAP]:
                        transient_tries.pop(_stale, None)
            else:
                # RECORDED AS SEEN, deliberately. The canonical path refused it
                # (invalid, banned language, duplicate, cross-account near-dup,
                # or over cap), and the LLM summarize-with-citation call above
                # has ALREADY been paid for. The refusal cannot be evaluated any
                # earlier — every guard that produced it keys on the generated
                # TEXT — so leaving the item unseen means re-generating and
                # re-refusing the same story on every tick, forever, burning
                # billed spend on an outcome we already know. EVERY REASON THAT
                # REACHES THIS BRANCH IS A STABLE PROPERTY OF THE COPY, so a
                # retry cannot change the answer; the transient class above is
                # the exception the old blanket comment wrongly claimed did not
                # exist. The seen ledger is size-capped and rolls (daemon
                # _PRESS_SEEN_CAP), so this is a suppression with a horizon, not
                # a permanent kill.
                seen.add(_ekey)
                transient_tries.pop(_ekey, None)   # settled: the streak is over
            _skip_row = {"id": iid, "reason": _reason, "account": account}
            if _refusal.get("violations"):
                _skip_row["violations"] = list(_refusal["violations"])[:4]
            skipped.append(_skip_row)
            continue
        transient_tries.pop(_emission_key(s), None)   # it shipped; streak over
        # Charge the desk that actually took the item — the SPILL target when one
        # was chosen, never the class's nominal owner. Charging the pre-spill
        # account would leave the receiving desk's budget uncharged and let one
        # busy day empty the whole pool through a single exhausted route.
        day_counts[account] = int(day_counts.get(account, 0)) + 1
        # `flagship_counter` is the primary desk's row, kept for the committed
        # cursors.json contract (see the per-desk budget block above).
        if account == primary_desk:
            counter["count"] = int(counter["count"]) + 1
        # Record the MIRROR-COLLAPSED key so a later tick from EITHER mirror is a
        # dedupe skip. (There is no per-item outbox FILENAME any more — XG-W2
        # moved this lane onto items.jsonl/the daemon spool — but the feed id
        # still names the media SVG and rides on the item as source.feed_item_id.)
        seen.add(_emission_key(s))
        emitted.append(out_item)
        # An emitted item is rail-eligible with its FULLY-composed body (opener +
        # summary + attribution + tape). Record the composed text keyed by id so
        # the rail builder reuses it rather than re-running the LLM.
        emitted_bodies[iid] = {"text": body, "register": register,
                               "tape_stamp": tape_stamp, "attribution": attribution}

    # ── B4a rail ───────────────────────────────────────────────────────────────
    # The rail shows EVERYTHING above a LOWER floor (incl. digest-class items X
    # never posts) — the news.html retention surface. Items that emitted to X reuse
    # their composed body; rail-only items (digest/below-post-floor) get a
    # deterministic display text (headline + attribution + tape). Ranked by
    # salience, capped.
    #
    # NOTE: this builder itself makes no LLM call, but the rail is no longer
    # cost-free end to end — the daemon's B4c zh pass translates each NEW item
    # once before publishing (scripts/marketing_fastlane_daemon.py::_attach_zh,
    # capped per tick and disarmable via wire.zh_enabled).
    rail_seen: set[str] = set()
    # INTERNAL, never a payload: {rail id -> this tick's ordering value}. Returned
    # under the underscore key `_rail_order` for the daemon's non-public
    # wire_rank sidecar. Built HERE and not inside the rail builder so the item
    # dicts stay numberless (TestNoScoreIsUserFacing scans that builder).
    rail_order: dict[str, float] = {}
    for s in scored:
        try:
            if float(s.get("salience", 0.0)) < rail_floor:
                continue
        except (TypeError, ValueError):
            continue
        rail_item = _build_rail_item(
            s, now, emitted_bodies, corr=corr, now_iso=now_iso,
            window_s=window_s, quotes_store=quotes_store, tape_cfg=tape_cfg,
            wire_voice_enabled=wire_voice_enabled,
        )
        rkey = rail_item["id"]
        if rkey in rail_seen:
            continue
        rail_seen.add(rkey)
        rail.append(rail_item)
        rail_order[rkey] = _rail_order_value(s, rank_ordering=rank_ordering)
        if len(rail) >= rail_max:
            break

    # ── Intelligence Desk story packets ─────────────────────────────────────
    # The wire is an arrival log; the desk is the durable story layer. Every
    # garbage-cleared item above the lower intelligence floor becomes an
    # evidence-bearing packet, even when X publishing is disabled, the item is
    # digest-only, or the daily X slot is already taken. No score or feature
    # component is copied into the public packet.
    intelligence_cfg = (
        wire_cfg.get("intelligence", {}) if isinstance(wire_cfg, dict) else {}
    )
    if not isinstance(intelligence_cfg, dict):
        # `intelligence:` present with an empty body parses as None, and every
        # read below would raise AttributeError past the (TypeError, ValueError)
        # guards — i.e. a blank config key would stop the whole wire tick.
        intelligence_cfg = {}
    try:
        intelligence_floor = float(intelligence_cfg.get("salience_floor", 30.0))
    except (TypeError, ValueError):
        intelligence_floor = 30.0
    try:
        intelligence_max = int(intelligence_cfg.get("max_packets_per_tick", 100))
    except (TypeError, ValueError):
        intelligence_max = 100
    rail_by_id = {
        str(item.get("id") or ""): item for item in rail if isinstance(item, dict)
    }
    # V2 §3 claim registry: claim_key -> {story_id, first_ts, tokens}. Persisted
    # in the SAME daemon-local state dict the corroboration window uses, pruned on
    # the same TTL discipline. Never a repo write.
    claims_cfg = (
        intelligence_cfg.get("claims", {})
        if isinstance(intelligence_cfg.get("claims"), dict) else {}
    )

    def _claims_num(key: str, default: float) -> float:
        try:
            return float(claims_cfg.get(key, default))
        except (TypeError, ValueError):
            return default

    claim_ttl_h = _claims_num("ttl_h", _INTEL_CLAIM_TTL_H)
    claim_jaccard = _claims_num("jaccard_min", _INTEL_JACCARD_MIN)
    claim_tight_jaccard = _claims_num("tight_jaccard_min",
                                      _INTEL_TIGHT_JACCARD_MIN)
    claim_tight_min = _claims_num("tight_window_min", _INTEL_TIGHT_WINDOW_MIN)
    intel_claims = state.setdefault("intel_claims", {})
    if not isinstance(intel_claims, dict):
        intel_claims = state["intel_claims"] = {}
    try:
        _prune_intel_claims(intel_claims, now=now, ttl_h=claim_ttl_h)
    except Exception:  # noqa: BLE001 — a registry fault never stops the desk
        intel_claims = state["intel_claims"] = {}
    try:
        from engine.marketing.intelligence_desk import (  # noqa: PLC0415
            build_story_packet,
        )
        for s in scored:
            try:
                if float(s.get("salience", 0.0) or 0.0) < intelligence_floor:
                    continue
            except (TypeError, ValueError):
                continue
            iid = str(s.get("id") or "")
            corr_entry = corr.get(_corroboration_key(s), {})
            rail_item = rail_by_id.get(iid, {})
            draft_text = (
                (emitted_bodies.get(iid) or {}).get("text")
                or rail_item.get("en")
                or ""
            )
            # Story identity: the spine's view when it has one, then the claim
            # registry's alias. The packet's `id` IS the resolved story id, so
            # IntelligenceStore.upsert merges evidence across sources by
            # construction — no second merge layer inside the desk.
            spine_view = stories.get(iid)
            resolved_sid = _resolve_intel_story_id(
                s,
                spine_sid=str((spine_view or {}).get("story_id") or ""),
                registry=intel_claims,
                now=now,
                jaccard_min=claim_jaccard,
                tight_jaccard_min=claim_tight_jaccard,
                tight_window_min=claim_tight_min,
            )
            story_view = dict(spine_view or {})
            story_view["story_id"] = resolved_sid
            intelligence.append(build_story_packet(
                s,
                story=story_view,
                now=now,
                corr_sources=corr_entry.get("sources") or [],
                draft_text=draft_text,
                quotes_store=quotes_store,
                tape_cfg=tape_cfg,
            ))
            if intelligence_max > 0 and len(intelligence) >= intelligence_max:
                break
    except Exception as exc:  # noqa: BLE001
        # A desk export must never stop the speed rail or an eligible post.
        print(
            f"::warning title=intelligence-packets-unavailable::"
            f"{type(exc).__name__}: {exc} — wire tick continued",
            flush=True,
        )

    # ── XG-W5 golden-set corpus rows ──────────────────────────────────────────
    # EVERY item that reached this lane gets a row: the ingested ones with their
    # full `_components`, the garbage-gated ones with their drop reason. The
    # daemon appends these to the GITIGNORED host-local corpus that the labeling
    # exporter and the eval harness read (engine/marketing/golden_set.py). Never
    # a repo write, never user-facing.
    outcomes: dict[str, str] = {}
    for row in digest:
        outcomes[str(row.get("id", ""))] = "digest"
    for row in skipped:
        outcomes[str(row.get("id", ""))] = f"skipped:{row.get('reason', '')}"
    for out_item in emitted:
        feed_id = str((out_item.get("source") or {}).get("feed_item_id", ""))
        if feed_id:
            outcomes[feed_id] = "emitted"
    corpus_rows = list(gate_rows) + [
        _corpus_row(s, outcome=outcomes.get(str(s.get("id", "")), "scored"),
                    now_iso=now_iso)
        for s in scored
        if should_row(str(s.get("id", "")))
    ]

    # ── W4d headroom alarm ────────────────────────────────────────────────────
    # A day that DROPPED admissible wire items for want of a desk is a volume
    # decision the operator never made, and it used to happen through a bare
    # `continue`. The running day total is persisted (state -> cursors.json); one
    # line-start warning per TICK that dropped anything puts the same number in
    # the Actions summary. Bare print, flushed: through a logger GitHub silently
    # drops it, which is how five earlier annotations shipped dead.
    #
    # SILENT AT top_k=0, AND ONLY THERE. Zero is a deliberate stop, not a
    # shortage, and a lane an operator switched off must not shout on all 288 of
    # the day's runs — that is how a real alarm gets tuned out. The census still
    # COUNTS the drops, so the evidence survives in cursors.json either way.
    _dropped_this_tick = int(census.get("exhausted") or 0) - exhausted_before
    if _dropped_this_tick > 0 and top_k > 0:
        print(f"::warning title=press-lane-wire-headroom::{_dropped_this_tick} "
              f"wire item(s) cleared every quality gate and were dropped for want "
              f"of desk headroom (day total {census['exhausted']}). Budgets: "
              + ", ".join(f"{a}={day_counts.get(a, 0)}/{_budget(a)}"
                          for a in (spill_targets or [primary_desk]))
              + ". Raise breaking.flagship_top_k_per_day, or arm another wire desk "
                "in desk_network and point wire_routing.classes at it.", flush=True)

    return {
        "emitted": emitted,
        "skipped": skipped,
        "digest": digest,
        "blocked": blocked,
        "rail": rail,   # B4a: rail-eligible items for the wires.json sink
        # INTERNAL (underscore = never served): {rail id -> ordering value} for
        # exactly the rail items above. The VPS daemon folds this into its
        # host-local state and expresses it as ELEMENT ORDER in the non-public
        # wire_rank sidecar; the Actions lane discards it. Never write this into
        # wires.json or any other user-facing payload.
        "_rail_order": rail_order,
        "intelligence": intelligence,
        # XG-W5: labeling/eval corpus for this tick (host-local sink; see daemon).
        "corpus": corpus_rows,
        # Card-hosting census for this process: {cards, hosted, unhosted,
        # unhosted_refused}. A tally nobody reads is half a fix — the lane shipped
        # every card unhostable for weeks precisely because no number said so.
        "media_host": media_host_stats(),
        # The full seen-set AFTER this tick, including MIRROR-COLLAPSED emission
        # keys (M1). The daemon persists this verbatim so cross-tick dedupe works
        # for mirror pairs — recording out_item["id"] alone would miss the collapse.
        "_seen": sorted(seen),
    }


def _within_window(first_ts: str | None, now: datetime, window_s: int) -> bool:
    """True when `now` is within window_s of first_ts (both UTC)."""
    if not first_ts:
        return True
    try:
        first = datetime.fromisoformat(str(first_ts).replace("Z", "+00:00"))
    except ValueError:
        return True
    delta = (now.astimezone(timezone.utc) - first.astimezone(timezone.utc)).total_seconds()
    return 0 <= delta <= window_s
