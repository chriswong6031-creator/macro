"""engine.press.research_triage — W2R research triage & tiering (XG-W8 / D14 §5b).

~150 institutional reports enter the research vault every day.  This module
decides which of them deserve an article, and prints the reasoning for ALL of
them.

    W-SCORE  deterministic, engine-owned, six components, every threshold a
             config key (config/press.yml `research_triage`).  NO LLM ANYWHERE
             in this file — the model never originates a score (DO_NOT_REBUILD:
             "LLM-originated signals, scores, or escalations — FORBIDDEN").

ONE SCORING BRAIN, TWO CONSUMERS (X Growth charter §6 reconciliation ruling:
"Media W2R's W-score reuses IS-W2 components rather than growing a parallel
scorer").  Everything below that already existed is IMPORTED, never re-written:

    engine.marketing.garbage_gate      P0 pre-drop (promo / paywall stub /
                                       non-story / source blocklist)
    engine.marketing.story_spine       cluster identity — normalize_text,
                                       shingles, MinHash near-dup, and
                                       `independence_key` for "how many
                                       INDEPENDENT institutions are on this
                                       theme".  Not one line of clustering is
                                       reimplemented here.
    engine.marketing.signal_features   tokenize() for topical overlap and
                                       headline_shape() for the attention term.
    engine.press.validators            recent_own_posts + window_jaccard for
                                       the 30-day self-similarity novelty term.

The only NEW code is the vault-report ADAPTER (a catalog item is not a wire
item) and the six-component blend.

THE SIX COMPONENTS (masterplan §5b, in the order they are declared):

    institution_tier      who published it.  A prior on the desk, never a
                          measurement of THIS report — an unlisted institution
                          scores the neutral, not zero.
    cluster_density       how many INDEPENDENT institutions are on this theme
                          inside the trailing window.  The masterplan's
                          "importance" proxy.
    relevance             report tickers/themes against live movers, hot
                          chronicle threads and the watchlist.  Each context
                          source is independently null-safe: absent contributes
                          EXACTLY 0 and never renormalizes the others, so a
                          corpus with no context at all is rank-neutral.
    extraction_quality    structure/depth of our OWN vault `summary_points`.
                          A thin extraction cannot feed a good article, and this
                          is the one component measured on the material the
                          writer will actually see.
    attention_potential   headline-grade deltas — RANKING INPUT ONLY.  The §5
                          validator suite still bans unearned urgency framing in
                          the OUTPUT; this decides reading order, never voice.
                          Deliberately the smallest weight in the default set.
    novelty               inverse 30-day self-similarity against our own
                          published estate.  Catches the desk rewriting itself.

NULLS ARE PRINTED, NOT HIDDEN (house epistemics law).  Every component returns a
named `state` for every report — "observed", "unranked", "no-extraction",
"no-peers", "exact-only", "absent" — and every report in the ranking window gets
a ledger row every day, including the ones that were dropped as garbage and the
ones that were merely skipped.  A day with no row for a report is a bug.

THE LLM VETO PASS LIVES NEXT DOOR (engine/press/research_veto.py) and can only
DEMOTE.  `apply_vetoes` below is the ONLY place a veto touches a number, and it
is clamped so the arithmetic cannot raise a score even with a hostile config.

NO NETWORK.  This module reads committed artifacts and nothing else — the
fact-anchor law's "no free web browsing" line starts here, not at the writer.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

SCHEMA = "press.research_triage.v1"
SCORING_VERSION = "w2r.1"

COMPONENT_NAMES: tuple[str, ...] = (
    "institution_tier",
    "cluster_density",
    "relevance",
    "extraction_quality",
    "attention_potential",
    "novelty",
)

#: Ranking tiers, best first.  `none` is the honest name for "ranked, printed,
#: not selected" — a report with no tier still carries its score to the ledger.
TIERS: tuple[str, ...] = ("flagship", "desk_note", "none")

#: Every status a ledger row may carry.
#:
#:   selected         picked for a tier
#:   skipped          ranked, printed, below the volume line
#:   ranked           scored but not yet tiered (transient, inside rank())
#:   garbage_dropped  the P0 gate said no
#:   gate_error       the P0 gate RAISED — fail-closed, see _score_one
#:   skipped_input    never enterable: unusable row shape, or outside the window
STATUSES: tuple[str, ...] = ("selected", "skipped", "ranked", "garbage_dropped",
                             "gate_error", "skipped_input")

#: The only statuses that may reach the LLM veto head.
#:
#: FAIL-CLOSED (review M8).  `garbage_dropped` was the sole exclusion, so a
#: report whose gate RAISED sailed into the head.  The XG-W5 contract is that
#: the scoring brain never has to rank a horoscope AND that garbage never costs
#: a token; an exception is precisely the case where we do not know which it is,
#: and not knowing is not a reason to spend.
VETO_ELIGIBLE_STATUSES: frozenset[str] = frozenset({"ranked", "selected", "skipped"})

#: Statuses excluded from the ranking.  They carry scores; they carry no rank.
UNRANKED_STATUSES: frozenset[str] = frozenset({"garbage_dropped", "gate_error",
                                               "skipped_input"})


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULTS — every one of these is a config key under config/press.yml
# `research_triage`.  The XG-W5 contract-test pattern applies: a
# config/module drift is a test failure, not a silent re-tune.
#
# EVERY WEIGHT BELOW IS A HYPOTHESIS awaiting main-loop ratification (charter §8
# and the constitution's §20 closing instruction: suggested weights are to be
# calibrated, never treated as fixed truth).  The rationale for each sits beside
# it so a ratification review argues with a stated reason rather than a number.
# ─────────────────────────────────────────────────────────────────────────────

_WEIGHT_DEFAULTS: dict[str, float] = {
    # The hardest constraint on OUTPUT quality, and the only component measured
    # on the material the writer will actually be handed.  A four-point,
    # number-carrying extraction can become a piece; a one-line stub cannot,
    # however important the underlying report is.
    "extraction_quality": 0.24,
    # The differentiator against a bare summarizer: coverage that lands on what
    # our engine and our readers are already looking at.  Second only to
    # extraction because a perfectly relevant report we cannot write from is
    # still an article we cannot ship.
    "relevance": 0.22,
    # The masterplan's importance proxy.  Discounted below relevance for two
    # honest reasons: without the optional near-dup backend it degrades to a
    # floor (see `cluster_density`), and a crowded theme is also a crowded SERP.
    "cluster_density": 0.18,
    # A real prior on whether a desk's read is worth a piece — but a prior on
    # the NAME, not a measurement of this report, so it never dominates.
    "institution_tier": 0.16,
    # Protects against the engine rewriting itself.  Low because on a cold
    # estate (today) it is a neutral constant for every candidate.
    "novelty": 0.12,
    # DELIBERATELY THE SMALLEST.  This is the component most able to drag the
    # brand toward the sensationalism the §5 validators exist to ban.  It earns
    # a tie-break, not a ranking.
    "attention_potential": 0.08,
}

_INSTITUTION_DEFAULTS: dict[str, Any] = {
    # Value per tier.  `unranked` is the NEUTRAL, not zero: an institution we
    # have not classified has not been measured, and punishing it would make the
    # register's incompleteness look like a judgement.
    "tier_values": {"tier_1": 1.0, "tier_2": 0.7, "tier_3": 0.45, "unranked": 0.5},
    # Operator/Fable-editable register.  Ships with a small seeded default and
    # nothing else — an absent name lands on `unranked`, which costs it nothing.
    "tiers": {"tier_1": (), "tier_2": (), "tier_3": ()},
}

_CLUSTER_DEFAULTS: dict[str, Any] = {
    # Independent institutions on one theme for a full-marks density score.
    # Same squash shape as signal_features.corroboration_velocity: a
    # single-institution theme scores 0, which is also what "no corroboration"
    # means about it.
    "institutions_full": 4,
    # Trailing window the clustering runs over.
    "window_days": 7,
    # Hard cap on how many reports enter one clustering pass — the spine is
    # O(live stories) per construction and this runs on a shared runner.
    "max_items": 600,
}

_RELEVANCE_DEFAULTS: dict[str, Any] = {
    "w_ticker": 0.55,
    "w_topic": 0.45,
    # Topical overlap saturates here: matching three of our live context tokens
    # is as relevant as matching thirty.
    "topic_overlap_full": 3,
    # Trailing windows for the two first-party context sources.
    "chronicle_window_days": 7,
    "watchlist_window_days": 7,
    # THE CIRCULARITY FIX, and it is not optional.  The vault ingest writes one
    # `research_vault` chronicle event per report, so 236 of the 242 chronicle
    # events in a live 7-day window ARE the reports being triaged.  Without this
    # exclusion "relevance vs hot chronicle threads" compares the corpus against
    # itself: every report matched, the term saturated at its maximum for all
    # 280 candidates, and a component with a 0.22 weight became a constant.
    # Mirrors `desks.brief.exclude_sources`, which draws the same desk boundary
    # for the same reason.
    "exclude_chronicle_sources": ("research_vault",),
    # Movers pulled from the committed heatmap.
    "movers_n": 8,
    "movers_min_abs": 3.0,
}

_EXTRACTION_DEFAULTS: dict[str, Any] = {
    "points_full": 4,          # summary_points for full structural marks
    "words_full": 30,          # mean words per point for full depth marks
    "w_points": 0.40,
    "w_depth": 0.35,
    "w_numeric": 0.25,         # share of points carrying a figure
    # `needs_metadata: true` in the catalog means our own extraction knows it is
    # incomplete.  Multiplicative, not a drop: the report may still be the best
    # thing on the wire, it just cannot carry a piece on its own today.
    "needs_metadata_factor": 0.5,
}

_ATTENTION_DEFAULTS: dict[str, Any] = {
    # signal_features.headline_shape is REUSED wholesale for the shape half.
    "w_shape": 0.80,
    "w_top_pick": 0.20,
    # Passed straight through to signal_features.headline_shape; the vault's
    # titles are long-form report titles, so the bands differ from wire copy.
    "headline_shape": {"short_max_chars": 40, "long_min_chars": 130},
}

_NOVELTY_DEFAULTS: dict[str, Any] = {
    "window_days": 30,
    "shingle_n": 5,
    # COMPARABILITY FLOOR (review M4).  With six hand-written evergreen posts in
    # the estate, every institutional report scored a clean 1.0 and the detail
    # block said `observed` — a measured-looking maximum that only meant "we
    # have almost nothing to compare against".  Below this many peers the
    # component reports its null instead of a number.  This is a floor on the
    # CORPUS, not on the metric: it clears once the research desk publishes.
    "min_peers": 8,
    # Neutral, NOT a measurement: with nothing published there is nothing to
    # repeat, and calling that "maximally novel" would be a number pretending to
    # be evidence.  Same shape as signal_features' cold-start neutral.
    "neutral": 0.5,
    # A cap on how many of our own posts one report is compared against.
    "max_peers": 60,
}

_VETO_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # How far down the ranking the model is allowed to read.  The masterplan
    # prices FULL 150/day coverage at about $5/mo; the default covers the head
    # that can actually become an article, and raising it is a config edit with
    # a documented price.
    "head_size": 40,
    "batch_size": 20,
    # THE ONLY NUMBER A VETO CAN TOUCH.  Clamped into [0, 1] by apply_vetoes, so
    # even a hostile config edit cannot turn a demotion into a promotion.
    "demote_factor": 0.35,
    "model_key": "press_research_veto",
    # The DeepSeek rung's model id.  Named separately because an Anthropic model
    # id is not a DeepSeek one, and passing only `opus_model` left a
    # DeepSeek-only host running llm_auth's `deepseek-v4-pro` default — a tier up
    # from the cheapest-that-can-answer this lane is priced on (review M12).
    "deepseek_model": "deepseek-v4-flash",
    "max_tokens": 1200,
}

_VOLUME_DEFAULTS: dict[str, Any] = {
    # COLD-START DEFAULT (masterplan §5b + §0 W1 gate: publish volume is a
    # GSC-evidence-gated knob, "never a day-one 1,500/mo — a cold domain at that
    # cadence is the scaled-content-abuse profile Google deindexes").
    #
    # The RAMP IS CONFIG, NOT CODE: `stage` selects a row from `stages` below,
    # and each row states the evidence that opens it.  Moving the operation from
    # cold_start to warm is an edit to this one key plus the evidence.
    "stage": "cold_start",
    "stages": {
        "cold_start": {"flagship_per_day": 1, "desk_notes_per_day": 0},
        "warm": {"flagship_per_day": 2, "desk_notes_per_day": 4},
        "target": {"flagship_per_day": 3, "desk_notes_per_day": 12},
    },
}

_LEDGER_DEFAULTS: dict[str, Any] = {
    "path": "data/press/research_triage.jsonl",
    # The ranking window — reports published within this many days of the run
    # are ranked AND printed.  Matches desks.research_desk.window_days so the
    # ledger covers exactly the pool the planner draws from.
    "window_days": 21,
    # ONE ROW PER REPORT IS THE LAW, so this is NOT a row cap (review M6).  It
    # is sized to the real inflow — the masterplan's ~150 reports/day over a
    # 21-day window is ~3,150, and 4,000 leaves headroom.  Above it rows are
    # still written, just WITHOUT `component_detail`: a thinner row is a
    # survivable loss, a missing row is the hidden null the ledger exists to
    # prevent.  Either way it is announced.
    "max_detailed_rows_per_run": 4000,
    # `compact_ledger` drops rows older than this on the scheduled run.  At
    # ~300 rows/day a year is ~110k rows; 120 days is the window a
    # weight-ratification review would actually read.
    "retention_days": 120,
}


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers (mirrors of the XG-W5 idiom so the two files read alike)
# ─────────────────────────────────────────────────────────────────────────────


#: OPERATOR LEVERS — config keys whose VALUE is deliberately not pinned by the
#: config-contract test (review M9).
#:
#: The rest of the block is contract-tested value-for-value against the module
#: defaults, which is what stops a silent re-tune.  These four are the knobs the
#: charter says an operator turns, and a test that pins their values makes
#: "config, not code" false: flipping the volume stage, widening the veto head,
#: or classifying an institution would turn CI red.  The test asserts they EXIST
#: and have the right TYPE; it does not assert what they say.
OPERATOR_LEVER_KEYS: tuple[str, ...] = (
    "volume.stage",
    "veto.head_size",
    "veto.enabled",
    "institution.tiers",
)


def _get(cfg: dict | None, key: str, defaults: dict[str, Any]) -> Any:
    if isinstance(cfg, dict) and key in cfg and cfg[key] is not None:
        return cfg[key]
    return defaults[key]


def _clamp01(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(0.0, min(1.0, v))


def _annotate(level: str, title: str, message: str) -> None:
    """GitHub annotation.  Bare print, line start, flushed (house law).

    A logger would prefix the line and GitHub would silently drop it — the call
    reviews as an alarm and produces nothing in the Actions summary.
    """
    print(f"::{level} title={title}::{message}", flush=True)


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _slug(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")


_DIGIT_RE = re.compile(r"\d")


def triage_config(cfg: dict | None) -> dict:
    """The `research_triage` block of config/press.yml ({} when absent)."""
    block = (cfg or {}).get("research_triage") if isinstance(cfg, dict) else None
    return block if isinstance(block, dict) else {}


# ─────────────────────────────────────────────────────────────────────────────
# The adapter — a vault catalog item is not a wire item
# ─────────────────────────────────────────────────────────────────────────────


def report_text(item: dict) -> str:
    """Title + summary points, markdown stripped.  The one text view."""
    from engine.press.desk_planner import _strip_md  # noqa: PLC0415

    parts = [str(item.get("title") or "")]
    parts.extend(_strip_md(str(p)) for p in (item.get("summary_points") or []))
    return " ".join(p for p in parts if p).strip()


def as_signal_item(item: dict) -> dict:
    """Adapt a vault catalog row into the shape the XG-W5 modules already read.

    A THIN ADAPTER, deliberately: the garbage gate, the story spine and the
    headline-shape feature all consume `{id, headline, body_snippet, source,
    url, source_tier}`.  Handing them that shape is what lets W2R reuse the
    scoring brain instead of growing a parallel one.

    `source` carries the INSTITUTION, because that is what
    story_spine.independence_key falls back to when an item has no x handle and
    no URL — which is exactly the identity we want counted for cluster density
    ("how many independent institutions are on this theme").
    """
    from engine.press.desk_planner import _strip_md  # noqa: PLC0415

    points = [_strip_md(str(p)) for p in (item.get("summary_points") or [])]
    return {
        "id": str(item.get("id") or ""),
        "headline": str(item.get("title") or ""),
        "body_snippet": " ".join(points),
        "source": _slug(item.get("institution")) or "unknown_institution",
        # No URL by construction: the vault never republishes the source
        # document, and a report has no public third-party URL we would link.
        "url": None,
        "source_tier": "research",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Component 1 — institution_tier
# ─────────────────────────────────────────────────────────────────────────────


def institution_tier(item: dict, *, cfg: dict | None = None) -> tuple[float, dict]:
    """Per-institution prior.  UNLISTED IS NEUTRAL, never zero.

    The register is an operator/Fable lever (same posture as the garbage gate's
    source blocklist): a builder's opinion about which banks matter is not
    evidence, so the shipped default classifies nobody and every institution
    lands on the neutral until somebody rules on it.
    """
    values = dict(_INSTITUTION_DEFAULTS["tier_values"])
    raw_values = _get(cfg, "tier_values", _INSTITUTION_DEFAULTS)
    if isinstance(raw_values, dict):
        for key, value in raw_values.items():
            try:
                values[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

    tiers = _get(cfg, "tiers", _INSTITUTION_DEFAULTS)
    tiers = tiers if isinstance(tiers, dict) else {}
    name = _slug(item.get("institution"))
    if not name:
        return float(values.get("unranked", 0.5)), {
            "state": "no-institution",
            "institution": "",
            "note": "catalog row carries no institution — neutral, NOT a measurement",
        }

    for tier in sorted(tiers):
        members = {_slug(m) for m in (tiers.get(tier) or ())}
        if name in members:
            return _clamp01(values.get(str(tier), values.get("unranked", 0.5))), {
                "state": "observed",
                "institution": name,
                "tier": str(tier),
            }
    return _clamp01(values.get("unranked", 0.5)), {
        "state": "unranked",
        "institution": name,
        "note": "institution not in the tier register — neutral, NOT a measurement",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Component 2 — cluster_density (story_spine REUSED, nothing reimplemented)
# ─────────────────────────────────────────────────────────────────────────────


def build_spine(items: Iterable[dict], *, cfg: dict | None = None,
                spine_cfg: dict | None = None):
    """Cluster the window's reports with engine.marketing.story_spine.

    Returns ``(spine, {report_id: story_view})``.  The spine is constructed over
    an EPHEMERAL in-memory state dict — this makes zero repo writes and shares no
    state with the press daemon's own spine.

    The 15m/60m source windows in a story view are meaningless for daily
    research reports and are NOT read; `source_count` (distinct
    ``independence_key``s over the whole story record, window-free) is the only
    field consumed.
    """
    from engine.marketing.story_spine import StorySpine  # noqa: PLC0415

    spine = StorySpine({}, cfg=spine_cfg or {})
    views: dict[str, dict] = {}
    ordered = list(items)
    for it in ordered:
        signal_item = as_signal_item(it)
        when = _as_date(it.get("published_at")) or date.today()
        now = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
        spine.assign(signal_item, now=now)

    # Second pass: a story's source count is only complete once every member has
    # been absorbed, so the VIEW is taken after the whole window is clustered.
    # (`assign` on an already-seen exact key is idempotent for identity — it
    # re-absorbs the same independence key, which `_absorb` skips.)
    for it in ordered:
        signal_item = as_signal_item(it)
        view = spine.assign(signal_item, now=datetime.now(tz=timezone.utc))
        views[str(it.get("id") or "")] = view
    return spine, views


def cluster_density(story_view: dict | None, *, near_dup_enabled: bool = True,
                    cfg: dict | None = None,
                    absent_reason: str = "no-story") -> tuple[float, dict]:
    """Independent institutions on one theme, squashed to [0, 1].

    HONEST DEGRADATION.  ``story_spine``'s near-dup pass needs the optional
    ``datasketch`` wheel.  Without it, story identity collapses to the exact key
    (a normalized-headline hash), so two banks writing the same theme in
    different words land in different stories and the count reads 1.  That is
    reported as ``state="exact-only"`` with the value declared a FLOOR — it is
    not dressed up as a measured absence of clustering, and it is not replaced
    by an invented neutral either.
    """
    full = max(2, int(_get(cfg, "institutions_full", _CLUSTER_DEFAULTS)))
    if not isinstance(story_view, dict):
        # THE ABSENCE HAS THREE DIFFERENT CAUSES (review M7) and they are not
        # interchangeable: `outside-cluster-window` means the report is older
        # than the clustering window and was never a candidate for a cluster;
        # `cluster-truncated` means it lost a slot to `cluster.max_items`, which
        # is OUR cap and a tuning problem; `no-story` means the spine itself was
        # unavailable.  One label for all three read as "measured alone".
        return 0.0, {"state": absent_reason, "institutions": 0,
                     "institutions_full": full,
                     "note": "not clustered this run — 0 is an ABSENCE, not a "
                             "measured lack of corroboration"}

    count = int(story_view.get("source_count", 0) or 0)
    value = _clamp01((count - 1) / (full - 1))
    if near_dup_enabled:
        state = "observed" if count > 1 else "measured-alone"
    else:
        state = "exact-only"
    detail = {
        "state": state,
        "institutions": count,
        "institutions_full": full,
        "story_id": str(story_view.get("story_id") or ""),
        "members": int(story_view.get("member_count", 0) or 0),
    }
    if state == "measured-alone":
        detail["note"] = ("clustered and genuinely alone on its theme — this 0 IS "
                          "a measurement, unlike the absent states")
    if not near_dup_enabled:
        detail["note"] = ("near-dup pass unavailable (datasketch absent) — identity is "
                          "exact-key only, so this count is a FLOOR, not a measurement")
    return value, detail


# ─────────────────────────────────────────────────────────────────────────────
# Component 3 — relevance (every context source independently null-safe)
# ─────────────────────────────────────────────────────────────────────────────


def build_context(root=None, *, as_of: date | None = None,
                  cfg: dict | None = None) -> dict:
    """Assemble the live-relevance context.  Every source fails soft to empty.

    THREE FIRST-PARTY SOURCES, no network and no new ingestion:

        movers      the committed S&P heatmap, via engine.marketing.movers_source
                    (imported, not re-read).
        chronicle   recent chronicle events' tickers + themes — the "hot
                    chronicle threads" the masterplan names.
        watchlist   recent watchlist alert assets.

    An absent source yields an EMPTY set and its own named state.  Because the
    relevance blend adds sub-scores rather than averaging over the sources that
    happen to exist, an absent source contributes exactly 0 to every report and
    therefore cannot re-order the ranking (the tone_extremity rule, XG-W5).
    """
    from engine.press.desk_planner import repo_root  # noqa: PLC0415

    repo = repo_root(root)
    ref = as_of or date.today()
    states: dict[str, dict] = {}
    tickers: set[str] = set()
    topics: set[str] = set()

    # -- movers -------------------------------------------------------------
    try:
        from engine.marketing import movers_source  # noqa: PLC0415

        data = movers_source.load_movers(repo)
        if data:
            picks = movers_source.top_movers(
                data, tf="1D",
                n=int(_get(cfg, "movers_n", _RELEVANCE_DEFAULTS)),
                min_abs=float(_get(cfg, "movers_min_abs", _RELEVANCE_DEFAULTS)),
            )
            found = {str(m.get("ticker") or "").upper()
                     for side in ("gainers", "losers")
                     for m in (picks.get(side) or []) if m.get("ticker")}
            tickers |= found
            states["movers"] = {"state": "observed", "tickers": len(found)}
        else:
            states["movers"] = {"state": "absent", "note": "no committed heatmap"}
    except Exception as exc:  # noqa: BLE001 — a missing source costs its own term
        states["movers"] = {"state": "absent", "note": f"{type(exc).__name__}"}

    # -- chronicle ----------------------------------------------------------
    window = int(_get(cfg, "chronicle_window_days", _RELEVANCE_DEFAULTS))
    lo = (ref - timedelta(days=window)).isoformat()
    hi = ref.isoformat()
    try:
        from engine.press.desk_planner import _chronicle_events  # noqa: PLC0415
        from engine.marketing.signal_features import tokenize  # noqa: PLC0415

        excluded = {str(s) for s in _get(cfg, "exclude_chronicle_sources",
                                         _RELEVANCE_DEFAULTS)}
        rows = 0
        for ev in _chronicle_events(root):
            when = str(ev.get("date") or "")
            if not when or not (lo <= when <= hi):
                continue
            if str(ev.get("source") or "") in excluded:
                continue
            rows += 1
            tickers |= {str(t).upper() for t in (ev.get("tickers") or []) if t}
            for theme in (ev.get("themes") or []):
                topics |= set(tokenize(theme))
            topics |= set(tokenize(ev.get("title")))
        states["chronicle"] = ({"state": "observed", "events": rows} if rows
                               else {"state": "absent",
                                     "note": f"no chronicle events in {window}d"})
    except Exception as exc:  # noqa: BLE001
        states["chronicle"] = {"state": "absent", "note": f"{type(exc).__name__}"}

    # -- watchlist ----------------------------------------------------------
    wwindow = int(_get(cfg, "watchlist_window_days", _RELEVANCE_DEFAULTS))
    wlo = (ref - timedelta(days=wwindow)).isoformat()
    path = repo / "data" / "alerts" / "watchlist_alerts.jsonl"
    try:
        found_w: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                when = str(row.get("as_of") or row.get("ts") or "")[:10]
                if not when or not (wlo <= when <= hi):
                    continue
                asset = str(row.get("asset") or "").upper()
                if asset:
                    found_w.add(asset.split("-", 1)[0])
        tickers |= found_w
        states["watchlist"] = ({"state": "observed", "assets": len(found_w)} if found_w
                               else {"state": "absent",
                                     "note": f"no watchlist alerts in {wwindow}d"})
    except Exception as exc:  # noqa: BLE001
        states["watchlist"] = {"state": "absent", "note": f"{type(exc).__name__}"}

    return {"tickers": tickers, "topics": topics, "states": states}


def relevance(item: dict, context: dict | None, *,
              cfg: dict | None = None) -> tuple[float, dict]:
    """Report tickers/themes against the live first-party context."""
    from engine.marketing.signal_features import tokenize  # noqa: PLC0415

    w_ticker = float(_get(cfg, "w_ticker", _RELEVANCE_DEFAULTS))
    w_topic = float(_get(cfg, "w_topic", _RELEVANCE_DEFAULTS))
    overlap_full = max(1, int(_get(cfg, "topic_overlap_full", _RELEVANCE_DEFAULTS)))

    ctx = context if isinstance(context, dict) else {}
    ctx_tickers = {str(t).upper() for t in (ctx.get("tickers") or set())}
    ctx_topics = {str(t) for t in (ctx.get("topics") or set())}
    if not ctx_tickers and not ctx_topics:
        return 0.0, {
            "state": "no-context",
            "note": ("no live context source available — 0 contribution for EVERY "
                     "report, so the ranking is untouched"),
            "sources": dict(ctx.get("states") or {}),
        }

    report_topics = set(tokenize(item.get("title")))
    for tag in (item.get("tags") or []):
        report_topics |= set(tokenize(tag))
    topic_hits = sorted(report_topics & ctx_topics)
    topic_score = _clamp01(len(topic_hits) / overlap_full)

    report_tickers = {str(t).upper() for t in (item.get("tickers") or []) if t}
    if not report_tickers:
        # NULL IS NOT ZERO (review M3, house stats law).  Every one of the 280
        # live catalog rows carries `tickers: []` — the vault extractor does not
        # populate the field — so the 0.55 ticker half was a STRUCTURAL zero for
        # the whole corpus while the detail block said `observed`.  That is a
        # measurement claim about an absent input: it silently capped relevance
        # at 0.45 and made the component look weaker than it is.
        #
        # An unmeasurable half RENORMALIZES rather than scoring zero: the topic
        # half carries the whole component, exactly as it would if the ticker
        # weight had never been declared.  Same rule as the tone feature's
        # absent-join rule in XG-W5 — an absent input must not move a score.
        return _clamp01(topic_score), {
            "state": "no-report-tickers",
            "note": ("this report carries no tickers, so the ticker half is "
                     "unmeasurable and the topic half is renormalized to carry "
                     "the component — NOT a zero ticker score"),
            "renormalized": True,
            "w_topic_effective": 1.0,
            "topic_hits": topic_hits[:6],
            "sources": dict(ctx.get("states") or {}),
        }

    ticker_hits = sorted(report_tickers & ctx_tickers)
    ticker_score = 1.0 if ticker_hits else 0.0

    value = _clamp01(w_ticker * ticker_score + w_topic * topic_score)
    return value, {
        "state": "observed",
        "report_tickers": len(report_tickers),
        "ticker_hits": ticker_hits[:6],
        "topic_hits": topic_hits[:6],
        "renormalized": False,
        "sources": dict(ctx.get("states") or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Component 4 — extraction_quality
# ─────────────────────────────────────────────────────────────────────────────


def extraction_quality(item: dict, *, cfg: dict | None = None) -> tuple[float, dict]:
    """Structure and depth of OUR OWN vault summary.  Thin in, thin out.

    This is the only component computed on the material the writer is actually
    handed, which is why it carries the largest default weight: a report we
    cannot extract properly cannot become a piece that passes the §5 suite,
    however important the underlying research is.
    """
    from engine.press.desk_planner import _strip_md  # noqa: PLC0415

    points = [_strip_md(str(p)) for p in (item.get("summary_points") or [])]
    points = [p for p in points if p.strip()]
    if not points:
        return 0.0, {"state": "no-extraction", "points": 0,
                     "note": "no summary_points — this report cannot feed an article"}

    points_full = max(1, int(_get(cfg, "points_full", _EXTRACTION_DEFAULTS)))
    words_full = max(1, int(_get(cfg, "words_full", _EXTRACTION_DEFAULTS)))
    w_points = float(_get(cfg, "w_points", _EXTRACTION_DEFAULTS))
    w_depth = float(_get(cfg, "w_depth", _EXTRACTION_DEFAULTS))
    w_numeric = float(_get(cfg, "w_numeric", _EXTRACTION_DEFAULTS))
    total_w = (w_points + w_depth + w_numeric) or 1.0

    mean_words = sum(len(p.split()) for p in points) / len(points)
    numeric_share = sum(1 for p in points if _DIGIT_RE.search(p)) / len(points)

    value = (
        w_points * _clamp01(len(points) / points_full)
        + w_depth * _clamp01(mean_words / words_full)
        + w_numeric * _clamp01(numeric_share)
    ) / total_w

    detail = {
        "state": "observed",
        "points": len(points),
        "mean_words": round(mean_words, 2),
        "numeric_share": round(numeric_share, 3),
        "pages": item.get("pages"),
    }
    if item.get("needs_metadata"):
        factor = _clamp01(_get(cfg, "needs_metadata_factor", _EXTRACTION_DEFAULTS))
        value *= factor
        detail["needs_metadata"] = True
        detail["needs_metadata_factor"] = factor
    return _clamp01(value), detail


# ─────────────────────────────────────────────────────────────────────────────
# Component 5 — attention_potential (RANKING INPUT ONLY)
# ─────────────────────────────────────────────────────────────────────────────


def attention_potential(item: dict, *, cfg: dict | None = None) -> tuple[float, dict]:
    """Headline-grade shape, reusing signal_features.headline_shape verbatim.

    READ THE CONTRACT BEFORE MOVING THIS WEIGHT UP.  It orders a reading list.
    It never reaches the writer, never becomes a framing instruction, and the §5
    validator suite (ai_tells, cheese_test, banned/advice lexicons) still fails
    any draft that dresses a report in unearned urgency.  Ranking on attention
    while writing without it is the whole design: it is how the desk competes
    for the same attention without becoming the thing it is competing with.
    """
    from engine.marketing.signal_features import headline_shape  # noqa: PLC0415

    w_shape = float(_get(cfg, "w_shape", _ATTENTION_DEFAULTS))
    w_top = float(_get(cfg, "w_top_pick", _ATTENTION_DEFAULTS))
    total_w = (w_shape + w_top) or 1.0

    shape_cfg = _get(cfg, "headline_shape", _ATTENTION_DEFAULTS)
    shape_cfg = shape_cfg if isinstance(shape_cfg, dict) else {}
    signal_item = as_signal_item(item)
    matched = {"tickers": [t for t in (item.get("tickers") or []) if t]}
    shape_value, shape_detail = headline_shape(signal_item, matched=matched,
                                               cfg=shape_cfg)

    top_pick = bool(item.get("top_pick"))
    value = (w_shape * shape_value + w_top * (1.0 if top_pick else 0.0)) / total_w
    return _clamp01(value), {
        "state": "observed",
        "shape": round(float(shape_value), 4),
        "top_pick": top_pick,
        "numbers": shape_detail.get("numbers"),
        "entities": shape_detail.get("entities"),
        "length_band": shape_detail.get("length_band"),
        "contract": "ranking input only — never a framing instruction to the writer",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Component 6 — novelty (validators' own self-similarity machinery, reused)
# ─────────────────────────────────────────────────────────────────────────────


def load_peers(root=None, *, as_of: date | None = None,
               cfg: dict | None = None) -> list[dict]:
    """Our own recently published estate — the novelty comparison corpus."""
    from engine.press import validators as _v  # noqa: PLC0415

    window = int(_get(cfg, "window_days", _NOVELTY_DEFAULTS))
    max_peers = max(1, int(_get(cfg, "max_peers", _NOVELTY_DEFAULTS)))
    try:
        peers = _v.recent_own_posts(root, as_of=as_of, window_days=window)
    except Exception as exc:  # noqa: BLE001
        log.warning("research_triage: peer load failed: %s", exc)
        return []
    return peers[:max_peers]


def novelty(item: dict, peers: list[dict] | None, *,
            cfg: dict | None = None) -> tuple[float, dict]:
    """1 - (worst windowed shingle overlap against our own recent posts).

    REUSES engine.press.validators.window_jaccard — the SAME length-invariant
    metric the §5 self-similarity radar gates drafts with, so a report that
    would produce a near-duplicate piece is demoted BEFORE the writer spends a
    token on it rather than quarantined afterwards.
    """
    neutral = float(_get(cfg, "neutral", _NOVELTY_DEFAULTS))
    window = int(_get(cfg, "window_days", _NOVELTY_DEFAULTS))
    min_peers = max(0, int(_get(cfg, "min_peers", _NOVELTY_DEFAULTS)))
    if not peers:
        return _clamp01(neutral), {
            "state": "no-peers",
            "window_days": window,
            "note": ("no published estate in the window — neutral value, NOT a "
                     "measurement of novelty"),
        }
    if len(peers) < min_peers:
        # COMPARABILITY FLOOR (review M4).  "Zero overlap against six evergreen
        # blog posts" and "this report is novel" are different claims, and the
        # first was being printed with `state: observed` and a value of exactly
        # 1.0 for all 280 candidates.  A maximum that only reflects an empty
        # comparison corpus is a number pretending to be evidence.
        return _clamp01(neutral), {
            "state": "peer-corpus-too-thin",
            "peers": len(peers),
            "min_peers": min_peers,
            "window_days": window,
            "note": ("fewer than min_peers comparable posts — neutral value, NOT "
                     "a measurement. Zero overlap against a nearly empty estate "
                     "is not evidence of novelty."),
        }

    from engine.press.validators import window_jaccard, words  # noqa: PLC0415

    n = max(1, int(_get(cfg, "shingle_n", _NOVELTY_DEFAULTS)))
    tokens = words(report_text(item))
    if not tokens:
        return _clamp01(neutral), {"state": "no-text", "window_days": window}

    worst, worst_slug = 0.0, ""
    for peer in peers:
        j = window_jaccard(tokens, words(str(peer.get("text") or "")), n)
        if j > worst:
            worst, worst_slug = j, str(peer.get("slug") or "")
    return _clamp01(1.0 - worst), {
        "state": "observed",
        "max_jaccard": round(worst, 4),
        "closest": worst_slug,
        "peers": len(peers),
        "window_days": window,
    }


# ─────────────────────────────────────────────────────────────────────────────
# The W-score
# ─────────────────────────────────────────────────────────────────────────────


def weights(cfg: dict | None = None) -> dict[str, float]:
    """Merged component weights (config overrides the defaults key by key)."""
    merged = dict(_WEIGHT_DEFAULTS)
    raw = (cfg or {}).get("weights") if isinstance(cfg, dict) else None
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in merged:
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
    return merged


def w_score(values: dict[str, float], *, cfg: dict | None = None) -> tuple[float, dict]:
    """Weighted blend of the six components.  Every term is inspectable.

    THIS IS AN ORDERING NUMBER AND NOTHING ELSE.  It is never compared against a
    publish floor, never surfaced to a reader, and never reaches the writer's
    prompt.  It decides which reports the desk reads first.
    """
    w = weights(cfg)
    contributions: dict[str, float] = {}
    total = 0.0
    for name in COMPONENT_NAMES:
        contribution = w.get(name, 0.0) * _clamp01(values.get(name, 0.0))
        contributions[name] = round(contribution, 6)
        total += contribution
    return round(_clamp01(total), 6), {"weights": w, "contributions": contributions}


# ─────────────────────────────────────────────────────────────────────────────
# Tiering + the cold-start volume ramp
# ─────────────────────────────────────────────────────────────────────────────


def volume(cfg: dict | None = None) -> dict:
    """Resolved publish volume for the current ramp stage.

    THE RAMP IS CONFIG, NOT CODE.  `stage` names a row in `stages`; the row
    supplies flagship/desk-note counts.  An unknown stage falls back to
    cold_start and says so loudly rather than inventing a cadence.
    """
    stages = dict(_VOLUME_DEFAULTS["stages"])
    raw_stages = _get(cfg, "stages", _VOLUME_DEFAULTS)
    if isinstance(raw_stages, dict):
        for key, row in raw_stages.items():
            if isinstance(row, dict):
                stages[str(key)] = row

    stage = str(_get(cfg, "stage", _VOLUME_DEFAULTS))
    row = stages.get(stage)
    if not isinstance(row, dict):
        _annotate("warning", "research_triage_stage",
                  f"research_triage.volume.stage={stage!r} is not a declared stage "
                  f"({sorted(stages)}) — falling back to cold_start")
        stage = "cold_start"
        row = stages.get("cold_start") or _VOLUME_DEFAULTS["stages"]["cold_start"]

    def _n(key: str) -> int:
        try:
            return max(0, int(row.get(key, 0) or 0))
        except (TypeError, ValueError):
            return 0

    return {"stage": stage,
            "flagship_per_day": _n("flagship_per_day"),
            "desk_notes_per_day": _n("desk_notes_per_day")}


def assign_tiers(rows: list[dict], *, cfg: dict | None = None) -> list[dict]:
    """Stamp `rank` and `tier` on ranked rows, in place.  Returns the rows.

    Garbage-dropped rows never receive a tier: they are printed with their
    components and excluded from the ranking, which is the difference between
    "we looked and said no" and "we did not look".
    """
    vol = volume((cfg or {}).get("volume") if isinstance(cfg, dict) else None)
    flagship_n = vol["flagship_per_day"]
    note_n = vol["desk_notes_per_day"]

    rank = 0
    for row in rows:
        if row.get("status") in UNRANKED_STATUSES:
            row["rank"] = None
            row["tier"] = "none"
            continue
        rank += 1
        row["rank"] = rank
        if rank <= flagship_n:
            row["tier"] = "flagship"
            row["status"] = "selected"
        elif rank <= flagship_n + note_n:
            row["tier"] = "desk_note"
            row["status"] = "selected"
        else:
            row["tier"] = "none"
            row["status"] = "skipped"
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# The ranking pass
# ─────────────────────────────────────────────────────────────────────────────


def _sort_key(row: dict):
    """Deterministic order: score DESC, publication date DESC, id ASC."""
    pub = _as_date(row.get("published_at")) or date.min
    return (-float(row.get("w_score") or 0.0), -pub.toordinal(), str(row.get("report_id")))


def rank(items: Iterable[dict], *, as_of=None, root=None, cfg: dict | None = None,
         context: dict | None = None, peers: list[dict] | None = None,
         satire_blocklist: Iterable[str] | None = None) -> dict:
    """Score and rank every vault report in the window.  Deterministic, offline.

    `cfg` is the FULL config/press.yml mapping; the `research_triage` block is
    read out of it here so callers never have to know the nesting.

    Returns::

        {"as_of", "scoring_version", "schema", "weights", "volume",
         "rows": [...],            every report, ranked, garbage rows included
         "context_states": {...},  which relevance sources were live
         "downgrades": [...]}      story-spine optional-dependency notices

    NEVER RAISES on a single bad report: a row that cannot be scored is printed
    with a named error state rather than silently dropped.
    """
    tcfg = triage_config(cfg)
    run_date = _as_date(as_of) or date.today()

    ledger_cfg = tcfg.get("ledger") if isinstance(tcfg.get("ledger"), dict) else {}
    window = int(_get(ledger_cfg, "window_days", _LEDGER_DEFAULTS))
    lo = run_date - timedelta(days=window)
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── INTAKE, RECONCILED (review M1) ───────────────────────────────────────
    # The first version dropped four classes of input with a bare `continue`:
    # a non-mapping row, a row with no id, a row whose `published_at` would not
    # parse, and a row outside the window.  "Every report's score prints to the
    # ledger" was therefore true only of the reports that survived a filter
    # nobody could see the output of — a broken vault field would have silently
    # shrunk the denominator with no trace anywhere.  Every input now produces a
    # row, and the run reconciles inputs against rows before it returns.
    pool: list[dict] = []
    excluded: list[dict] = []
    inputs = 0
    for index, it in enumerate(items or []):
        inputs += 1
        if not isinstance(it, dict):
            excluded.append(_skipped_input_row(
                {}, as_of=run_date, ts=ts, reason="not-a-mapping",
                fallback_id=f"_unscorable_{index}",
                note=f"input #{index} is a {type(it).__name__}, not a catalog row"))
            continue
        rid = str(it.get("id") or "").strip()
        if not rid:
            excluded.append(_skipped_input_row(
                it, as_of=run_date, ts=ts, reason="no-report-id",
                fallback_id=f"_unidentified_{index}",
                note="catalog row carries no id — it cannot be deduped, linked "
                     "or covered, so it cannot be triaged"))
            continue
        pub = _as_date(it.get("published_at"))
        if pub is None:
            excluded.append(_skipped_input_row(
                it, as_of=run_date, ts=ts, reason="unparseable-published-at",
                note=f"published_at={it.get('published_at')!r} does not parse — "
                     "a report that cannot be dated cannot be point-in-time"))
            continue
        # `as_of` is a hard right edge, exactly as in desk_planner: a report
        # published after the run date cannot be triaged by that run.
        if pub > run_date:
            excluded.append(_skipped_input_row(
                it, as_of=run_date, ts=ts, reason="published-after-run-date",
                note="postdates the run — a hard right edge, not a judgement"))
            continue
        if pub < lo:
            excluded.append(_skipped_input_row(
                it, as_of=run_date, ts=ts, reason="outside-ledger-window",
                note=f"older than ledger.window_days={window}"))
            continue
        pool.append(it)

    # ── clustering slice (review M7) ─────────────────────────────────────────
    # RECENCY-ORDERED before the cap.  Catalog order is ingest order, so
    # `[:max_items]` used to hand the spine whatever happened to be first in the
    # file — on an over-cap day the newest reports, which are the ones a cluster
    # is actually about, could be the ones excluded.
    cluster_cfg = tcfg.get("cluster") if isinstance(tcfg.get("cluster"), dict) else {}
    max_items = max(1, int(_get(cluster_cfg, "max_items", _CLUSTER_DEFAULTS)))
    cluster_window = int(_get(cluster_cfg, "window_days", _CLUSTER_DEFAULTS))
    cluster_lo = run_date - timedelta(days=cluster_window)
    in_window = [it for it in pool
                 if (_as_date(it.get("published_at")) or date.min) >= cluster_lo]
    in_window.sort(key=lambda it: (
        -((_as_date(it.get("published_at")) or date.min).toordinal()),
        str(it.get("id") or ""),
    ))
    cluster_pool = in_window[:max_items]
    cluster_truncated = max(0, len(in_window) - len(cluster_pool))
    clustered_ids = {str(it.get("id") or "") for it in cluster_pool}
    if cluster_truncated:
        _annotate("warning", "research_triage_cluster_truncated",
                  f"cluster.max_items={max_items} excluded {cluster_truncated} "
                  "in-window report(s) from the clustering pass — their density "
                  "rows say `cluster-truncated`, not `measured-alone`. Raise the "
                  "cap or narrow cluster.window_days.")

    spine_cfg = tcfg.get("story_spine") if isinstance(tcfg.get("story_spine"), dict) else {}
    spine_failed = False
    try:
        spine, views = build_spine(cluster_pool, spine_cfg=spine_cfg)
        near_dup = bool(spine.near_dup_enabled)
        downgrades = list(spine.downgrades)
    except Exception as exc:  # noqa: BLE001 — clustering must never stop triage
        _annotate("warning", "research_triage_cluster",
                  f"story-spine clustering failed ({type(exc).__name__}: {exc}) — "
                  "cluster_density reports no-story for every report this run")
        views, near_dup, downgrades = {}, False, [f"clustering failed: {exc}"]
        spine_failed = True

    if context is None:
        context = build_context(root, as_of=run_date,
                                cfg=tcfg.get("relevance") if isinstance(
                                    tcfg.get("relevance"), dict) else None)
    if peers is None:
        peers = load_peers(root, as_of=run_date,
                           cfg=tcfg.get("novelty") if isinstance(
                               tcfg.get("novelty"), dict) else None)

    gate_cfg = tcfg.get("garbage_gate") if isinstance(tcfg.get("garbage_gate"), dict) else {}

    rows: list[dict] = []
    for it in pool:
        rid = str(it.get("id") or "")
        if spine_failed:
            absent = "no-story"
        elif rid in clustered_ids:
            absent = "no-story"          # in the pass; a missing view is a bug
        elif rid in {str(x.get("id") or "") for x in in_window}:
            absent = "cluster-truncated"
        else:
            absent = "outside-cluster-window"
        rows.append(_score_one(it, as_of=run_date, ts=ts, tcfg=tcfg,
                               gate_cfg=gate_cfg, views=views, near_dup=near_dup,
                               context=context, peers=peers,
                               satire_blocklist=satire_blocklist,
                               cluster_absent_reason=absent))
    rows.extend(excluded)

    live = [r for r in rows if r["status"] not in UNRANKED_STATUSES]
    dropped = [r for r in rows if r["status"] in UNRANKED_STATUSES]
    live.sort(key=_sort_key)
    dropped.sort(key=_sort_key)
    ordered = assign_tiers(live, cfg=tcfg) + dropped

    # THE DENOMINATOR IS RECONCILED, LOUDLY.  "One row per input" is the law the
    # ledger rests on; an off-by-anything means a report vanished, so it is an
    # annotation rather than a comment nobody reads.
    if len(ordered) != inputs:
        _annotate("warning", "research_triage_reconcile",
                  f"triage saw {inputs} input row(s) and produced {len(ordered)} "
                  f"ledger row(s) — they must match. Difference: "
                  f"{inputs - len(ordered)}. A missing row is a report whose "
                  "score was never printed.")

    return {
        "schema": SCHEMA,
        "scoring_version": SCORING_VERSION,
        "as_of": run_date.isoformat(),
        "weights": weights(tcfg),
        "volume": volume(tcfg.get("volume") if isinstance(tcfg.get("volume"), dict) else None),
        "rows": ordered,
        "context_states": dict((context or {}).get("states") or {}),
        "peers": len(peers or []),
        "near_dup_enabled": near_dup,
        "downgrades": downgrades,
        "inputs": inputs,
        "reconciled": len(ordered) == inputs,
        "cluster_truncated": cluster_truncated,
        "effective_contributions": effective_contributions(ordered, cfg=tcfg),
    }


def _skipped_input_row(item: dict, *, as_of: date, ts: str, reason: str,
                       note: str, fallback_id: str = "") -> dict:
    """A ledger row for an input that could never enter the ranking.

    It carries the same shape as a scored row so a consumer never has to branch,
    with every component in an explicit `not-scored` state.  That is the
    difference between "we looked and could not use it" and silence.
    """
    rid = str((item or {}).get("id") or "").strip() or fallback_id
    return {
        "schema": SCHEMA,
        "scoring_version": SCORING_VERSION,
        "as_of": as_of.isoformat(),
        "ts": ts,
        "report_id": rid,
        "title": str((item or {}).get("title") or ""),
        "institution": str((item or {}).get("institution") or ""),
        "published_at": str((item or {}).get("published_at") or "")[:10],
        "status": "skipped_input",
        "skip_reason": reason,
        "drop_reason": None,
        "drop_detail": note,
        "tier": "none",
        "rank": None,
        "w_score": None,
        "w_score_pre_veto": None,
        "components": {},
        "contributions": {},
        "component_detail": {name: {"state": "not-scored", "reason": reason}
                             for name in COMPONENT_NAMES},
        "veto": None,
    }


def effective_contributions(rows: list[dict], *, cfg: dict | None = None) -> dict:
    """What the blend is ACTUALLY ordering on this run (review M2).

    A declared weight is not an operative one.  A component that is constant
    across the corpus contributes nothing to the ORDER however large its weight,
    and on the shipped config three of six are constant today — so the printed
    weight vector, read alone, describes a ranking that is not happening.

    Returns per-component standard deviation of the CONTRIBUTION (weight x
    value, i.e. the term that actually moves the total) plus the Pearson
    correlation of each component's contribution with the final score, and names
    the dominant one.  Pure arithmetic over the rows already computed; no
    numpy, no second pass over the corpus.
    """
    scored = [r for r in rows if isinstance(r.get("w_score"), (int, float))
              and r.get("components")]
    out: dict[str, Any] = {"n": len(scored), "components": {}, "dominant": None}
    if len(scored) < 2:
        out["note"] = "fewer than two scored rows — no dispersion to report"
        return out

    w = weights(cfg)
    scores = [float(r["w_score"]) for r in scored]
    mean_s = sum(scores) / len(scores)
    var_s = sum((x - mean_s) ** 2 for x in scores) / len(scores)
    sd_s = math.sqrt(var_s)

    best_name, best_r = None, -2.0
    for name in COMPONENT_NAMES:
        contrib = [w.get(name, 0.0) * float((r.get("components") or {}).get(name, 0.0))
                   for r in scored]
        mean_c = sum(contrib) / len(contrib)
        var_c = sum((x - mean_c) ** 2 for x in contrib) / len(contrib)
        sd_c = math.sqrt(var_c)
        # TOLERANCE, NOT EQUALITY. A component that is the identical float on
        # every row still accumulates ~1e-17 of variance through the sum, so
        # `sd_c == 0` reported `novelty` (a flat 0.5 under its comparability
        # floor) as if it were ordering something. A term that moves the total
        # by less than a picopoint is inert in every sense a reader cares about.
        inert = sd_c < 1e-12
        if not inert and sd_s > 0:
            cov = sum((c - mean_c) * (s - mean_s)
                      for c, s in zip(contrib, scores)) / len(contrib)
            corr = cov / (sd_c * sd_s)
        else:
            corr = None
        out["components"][name] = {
            "declared_weight": round(w.get(name, 0.0), 6),
            "value_sd": round(math.sqrt(
                sum((float((r.get("components") or {}).get(name, 0.0)) -
                     sum(float((q.get("components") or {}).get(name, 0.0))
                         for q in scored) / len(scored)) ** 2
                    for r in scored) / len(scored)), 6),
            "contribution_sd": round(sd_c, 6),
            "corr_with_score": None if corr is None else round(corr, 4),
            # A component that never varies cannot order anything, whatever its
            # declared weight says.
            "orders_nothing": inert,
        }
        if corr is not None and corr > best_r:
            best_name, best_r = name, corr

    out["score_sd"] = round(sd_s, 6)
    if best_name is not None:
        out["dominant"] = {"component": best_name, "corr_with_score": round(best_r, 4)}
    out["inert"] = sorted(n for n, d in out["components"].items() if d["orders_nothing"])
    return out


def _score_one(item: dict, *, as_of: date, ts: str, tcfg: dict, gate_cfg: dict,
               views: dict, near_dup: bool, context: dict | None,
               peers: list[dict] | None, satire_blocklist,
               cluster_absent_reason: str = "no-story") -> dict:
    """One report's full row.  Every failure becomes a named state, never a drop."""
    from engine.marketing import garbage_gate  # noqa: PLC0415

    rid = str(item.get("id") or "")
    signal_item = as_signal_item(item)

    # P0 garbage gate FIRST — the XG-W5 contract is that nothing garbage ever
    # reaches an LLM.  It is honoured here: a gated report is excluded from the
    # ranking and therefore from the veto head, so it costs zero tokens.  Its
    # deterministic components are still computed and printed, because a dropped
    # row with no numbers on it is exactly the hidden null the house law forbids.
    #
    # AN EXCEPTION FAILS CLOSED (review M8).  The first version logged and left
    # `verdict = None`, which RANKED the report and put it in the veto head —
    # the one case where we do not know whether it is garbage was the case that
    # got the benefit of the doubt AND cost tokens.  A gate we cannot run is a
    # gate that said no.
    verdict = None
    gate_error = ""
    try:
        verdict = garbage_gate.check(signal_item, cfg=gate_cfg,
                                     satire_blocklist=satire_blocklist)
    except Exception as exc:  # noqa: BLE001
        gate_error = f"{type(exc).__name__}: {exc}"
        log.warning("research_triage: garbage gate raised for %s: %s", rid, exc)
        # This module runs inside a GitHub Actions step, so the alarm has to be
        # an annotation at line start, not only a log line (house law).
        _annotate("warning", "research_triage_gate_error",
                  f"{rid}: P0 garbage gate raised ({gate_error}) — report held OUT "
                  "of the ranking and the veto head (fail-closed). Its scores are "
                  "still printed to the ledger.")

    values: dict[str, float] = {}
    detail: dict[str, dict] = {}
    try:
        values["institution_tier"], detail["institution_tier"] = institution_tier(
            item, cfg=tcfg.get("institution"))
        values["cluster_density"], detail["cluster_density"] = cluster_density(
            views.get(rid), near_dup_enabled=near_dup, cfg=tcfg.get("cluster"),
            absent_reason=cluster_absent_reason)
        values["relevance"], detail["relevance"] = relevance(
            item, context, cfg=tcfg.get("relevance"))
        values["extraction_quality"], detail["extraction_quality"] = extraction_quality(
            item, cfg=tcfg.get("extraction"))
        values["attention_potential"], detail["attention_potential"] = attention_potential(
            item, cfg=tcfg.get("attention"))
        values["novelty"], detail["novelty"] = novelty(
            item, peers, cfg=tcfg.get("novelty"))
    except Exception as exc:  # noqa: BLE001
        _annotate("warning", "research_triage_score",
                  f"{rid}: component computation failed ({type(exc).__name__}: {exc}) "
                  "— row printed with an error state, not dropped")
        for name in COMPONENT_NAMES:
            values.setdefault(name, 0.0)
            detail.setdefault(name, {"state": "error", "error": f"{type(exc).__name__}"})

    score, score_detail = w_score(values, cfg=tcfg)
    return {
        "schema": SCHEMA,
        "scoring_version": SCORING_VERSION,
        "as_of": as_of.isoformat(),
        "ts": ts,
        "report_id": rid,
        "title": str(item.get("title") or ""),
        "institution": str(item.get("institution") or ""),
        "published_at": str(item.get("published_at") or "")[:10],
        "status": ("gate_error" if gate_error
                   else "garbage_dropped" if verdict else "ranked"),
        "drop_reason": ("gate_error" if gate_error
                        else (verdict or {}).get("reason") if verdict else None),
        "drop_detail": (gate_error if gate_error
                        else (verdict or {}).get("detail") if verdict else None),
        "tier": "none",
        "rank": None,
        "w_score": score,
        "w_score_pre_veto": score,
        "components": {k: round(float(v), 6) for k, v in values.items()},
        "contributions": score_detail["contributions"],
        "component_detail": detail,
        "veto": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# The veto application — THE ONLY PLACE AN LLM VERDICT TOUCHES A NUMBER
# ─────────────────────────────────────────────────────────────────────────────

#: The complete set of demotion reasons a veto may carry (masterplan §5b:
#: "may DEMOTE (thin/paywalled/duplicate) — never promote").  An unrecognised
#: reason is DISCARDED rather than trusted: a model that answers off-contract
#: has not earned a rank change in either direction.
VETO_REASONS: frozenset[str] = frozenset({"thin", "paywalled", "duplicate"})


def apply_vetoes(result: dict, vetoes: dict | None, *,
                 cfg: dict | None = None) -> dict:
    """Apply demote-only vetoes to a ranked result.  Returns a NEW result dict.

    `cfg` is the `research_triage` BLOCK (the same shape `rank` reads), not the
    whole press config.

    DEMOTE-ONLY BY CONSTRUCTION, three independent locks — any one of them alone
    would be enough, and they are all here because "the LLM cannot promote" is
    the property the whole veto design rests on:

      1. `factor` is clamped into [0, 1] before it is used, so a config typo
         (2.0, -1, "lots") cannot become a multiplier above one.
      2. The new score is `min(old * factor, old)`, so even a factor of exactly
         1.0 leaves the score unchanged rather than moving it.
      3. Only reasons in `VETO_REASONS` are honoured, and only for report ids
         that were actually in the ranked set.  A veto for an id the model
         invented is discarded.

    HONEST LIMIT ON "CAN ONLY MOVE DOWN".  A demotion lowers ONE row's score and
    touches no other, so a demoted row can only lose ground to rows that were
    not demoted.  It does NOT follow that no row ever gains a rank NUMBER: when
    a row above you is demoted past you, your rank improves from 4 to 3 without
    your score changing.  That is arithmetic, not promotion — nothing the model
    said raised your score — but it IS a report reaching a tier it would not
    have reached, so any row whose rank improved because something above it was
    demoted is stamped with `promoted_by_demotion` naming the ids that moved.
    A tier that was won this way should be visible, not inferred.
    """
    vcfg = (cfg or {}).get("veto") if isinstance(cfg, dict) else None
    factor = _clamp01(_get(vcfg, "demote_factor", _VETO_DEFAULTS))

    rows = [dict(r) for r in (result.get("rows") or [])]
    known = {str(r.get("report_id")) for r in rows}
    ranks_before = {str(r.get("report_id")): r.get("rank") for r in rows}
    applied = 0
    demoted_ids: list[str] = []

    for row in rows:
        entry = (vetoes or {}).get(str(row.get("report_id")))
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("reason") or "")
        if reason not in VETO_REASONS:
            log.warning("research_triage: veto for %s carries unknown reason %r — ignored",
                        row.get("report_id"), reason)
            continue
        before = float(row.get("w_score") or 0.0)
        after = min(before * factor, before)
        row["w_score_pre_veto"] = before
        row["w_score"] = round(after, 6)
        row["veto"] = {
            "demoted": True,
            "reason": reason,
            "factor": factor,
            "model": str(entry.get("model") or ""),
            "provider": str(entry.get("provider") or ""),
        }
        demoted_ids.append(str(row.get("report_id")))
        applied += 1

    unknown = sorted(set((vetoes or {})) - known)
    if unknown:
        log.warning("research_triage: %d veto(es) named unranked report ids — discarded: %s",
                    len(unknown), ", ".join(unknown[:5]))

    live = [r for r in rows if r.get("status") not in UNRANKED_STATUSES]
    dropped = [r for r in rows if r.get("status") in UNRANKED_STATUSES]
    live.sort(key=_sort_key)
    ordered = assign_tiers(live, cfg=(cfg or {})) + dropped

    # TRACE THE ROWS THAT GAINED GROUND (see the docstring's honest limit).
    # No score rose; some ranks did, because rows above them fell. A tier won
    # that way is a real editorial consequence of an LLM verdict and belongs in
    # the audit trail rather than being reconstructible only by diffing runs.
    for row in ordered:
        rid = str(row.get("report_id"))
        before, after = ranks_before.get(rid), row.get("rank")
        if rid in demoted_ids or before is None or after is None:
            continue
        if after < before:
            row["promoted_by_demotion"] = {
                "rank_before": before,
                "rank_after": after,
                "because_demoted": sorted(demoted_ids),
                "note": ("this row's SCORE did not change — it moved up because "
                         "rows above it were demoted"),
            }

    out = dict(result)
    out["rows"] = ordered
    out["vetoes_applied"] = applied
    out["demoted_ids"] = sorted(demoted_ids)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Shortlist — what the planner consumes
# ─────────────────────────────────────────────────────────────────────────────


def shortlist(result: dict, tier: str = "flagship") -> list[str]:
    """Report ids selected for `tier`, best first.

    This is the planner's whole intake contract: an ORDER, not a decision.  The
    planner still applies its own dedupe, point-in-time and lexicon rules, and
    still drops a report it cannot legally write about.
    """
    return [str(r.get("report_id")) for r in (result.get("rows") or [])
            if r.get("tier") == tier and r.get("status") == "selected"]


def ranked_order(result: dict) -> list[str]:
    """Every non-garbage report id in ranked order (the full fallback order)."""
    return [str(r.get("report_id")) for r in (result.get("rows") or [])
            if r.get("status") not in UNRANKED_STATUSES]


# ─────────────────────────────────────────────────────────────────────────────
# The ledger — nulls printed, every day, for every report in the window
# ─────────────────────────────────────────────────────────────────────────────


def ledger_path(cfg: dict | None, root=None) -> Path:
    from engine.press.desk_planner import repo_root  # noqa: PLC0415

    tcfg = triage_config(cfg)
    lcfg = tcfg.get("ledger") if isinstance(tcfg.get("ledger"), dict) else {}
    return repo_root(root) / str(_get(lcfg, "path", _LEDGER_DEFAULTS))


#: Per-report keys whose value is identical for every row of a run.  They are
#: hoisted into the run header and stripped from the rows (review M6): at 280
#: rows/day the relevance `sources` block alone repeated a ~200-byte context
#: dict 280 times for no information gain.
_RUN_LEVEL_KEYS: tuple[str, ...] = ("schema", "scoring_version", "as_of", "ts")

RUN_SCHEMA = "press.research_triage.run.v1"


def run_header(result: dict, *, cfg: dict | None = None,
               veto_report: dict | None = None) -> dict:
    """The once-per-run row: everything that is constant across the day's rows.

    Written as the FIRST line of a run's append block.  Readers that only want
    scores skip it on `schema`; readers that want to know what the run knew —
    which context sources were live, which weights applied, what the blend was
    actually ordering on — get it once instead of 280 times.
    """
    return {
        "schema": RUN_SCHEMA,
        "scoring_version": result.get("scoring_version", SCORING_VERSION),
        "as_of": result.get("as_of"),
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weights": result.get("weights"),
        "volume": result.get("volume"),
        "context_states": result.get("context_states"),
        "near_dup_enabled": result.get("near_dup_enabled"),
        "peers": result.get("peers"),
        "inputs": result.get("inputs"),
        "rows": len(result.get("rows") or []),
        "reconciled": result.get("reconciled"),
        "cluster_truncated": result.get("cluster_truncated"),
        "downgrades": list(result.get("downgrades") or []),
        # WHAT THE BLEND ACTUALLY ORDERED ON (review M2). The declared weights
        # above describe an intent; this describes the run.
        "effective_contributions": result.get("effective_contributions"),
        "veto": {k: v for k, v in (veto_report or {}).items() if k != "vetoes"},
    }


def ledger_rows(result: dict, *, cfg: dict | None = None) -> list[dict]:
    """The per-report rows this run would append.  ONE PER INPUT, ALWAYS.

    COMPACTED (review M6).  Two changes from the first version:

      * The run-level keys and the relevance context block are hoisted into
        `run_header`, so a row stops carrying four constants and a ~200-byte
        state dict that were identical across the whole day.
      * `ledger.max_detailed_rows_per_run` no longer DROPS rows.  One row per
        report is the law the ledger exists to keep, so above the threshold rows
        are written WITHOUT `component_detail` instead — a thinner row is a
        survivable loss, a missing row is the hidden null. The strip is
        announced either way.
    """
    tcfg = triage_config(cfg)
    lcfg = tcfg.get("ledger") if isinstance(tcfg.get("ledger"), dict) else {}
    cap = max(1, int(_get(lcfg, "max_detailed_rows_per_run", _LEDGER_DEFAULTS)))
    rows = list(result.get("rows") or [])

    strip_detail_from = cap if len(rows) > cap else len(rows)
    if strip_detail_from < len(rows):
        _annotate("notice", "research_triage_ledger_thin",
                  f"triage produced {len(rows)} rows and "
                  f"ledger.max_detailed_rows_per_run is {cap} — "
                  f"{len(rows) - strip_detail_from} row(s) are written WITHOUT "
                  "component_detail. Every report still has a row; only the "
                  "per-component explanation is dropped.")

    out: list[dict] = []
    for index, row in enumerate(rows):
        compact = {k: v for k, v in row.items() if k not in _RUN_LEVEL_KEYS}
        compact["as_of"] = row.get("as_of")      # the row's own join key stays
        detail = compact.get("component_detail")
        if index >= strip_detail_from:
            compact.pop("component_detail", None)
            compact["detail_stripped"] = True
        elif isinstance(detail, dict):
            # The relevance `sources` map is the run's context state, identical
            # on every row and already in the header.
            trimmed = dict(detail)
            rel = trimmed.get("relevance")
            if isinstance(rel, dict) and "sources" in rel:
                rel = {k: v for k, v in rel.items() if k != "sources"}
                trimmed["relevance"] = rel
            compact["component_detail"] = trimmed
        out.append(compact)
    return out


def append_ledger(path: Path, rows: list[dict], *,
                  header: dict | None = None) -> int:
    """Append-only, idempotent per (as_of, report_id).  Returns rows written.

    A re-run on the same day rewrites nothing: the pairs already on file are
    skipped, so the operator can dispatch the lane twice without doubling a
    day's scores.  The run header (when given) is written once, ahead of the
    rows, and only if the run actually has fresh rows to write.
    """
    if not rows:
        return 0
    seen: set[tuple[str, str]] = set()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and obj.get("schema") != RUN_SCHEMA:
                        seen.add((str(obj.get("as_of")), str(obj.get("report_id"))))
        except OSError as exc:
            log.warning("research_triage: ledger unreadable (%s) — appending anyway", exc)

    fresh = [r for r in rows
             if (str(r.get("as_of")), str(r.get("report_id"))) not in seen]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        if header:
            fh.write(json.dumps(header, ensure_ascii=False, default=str) + "\n")
        for row in fresh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    clear_ledger_cache()
    return len(fresh)


#: Parsed-ledger cache, keyed by (path, mtime_ns, size).  The planner calls
#: `recorded_vetoes` once per research desk — two full file reads per press run
#: for a file that cannot change mid-run (review M6).  A stat is cheap; a
#: re-parse of a 100k-row ledger inside a planning loop is not.  The key
#: includes mtime AND size so an external append invalidates it immediately.
_LEDGER_CACHE: dict[tuple[str, int, int], list[dict]] = {}


def read_ledger(root=None, cfg: dict | None = None,
                *, use_cache: bool = True) -> list[dict]:
    """Every ledger row ([] when the ledger does not exist yet).

    Cached per (path, mtime, size).  Pass ``use_cache=False`` from a writer that
    has just appended and wants the file as it now is.
    """
    path = ledger_path(cfg, root)
    try:
        if not path.exists():
            return []
        stat = path.stat()
        key = (str(path), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError as exc:
        log.warning("research_triage: ledger stat failed: %s", exc)
        return []
    if use_cache and key in _LEDGER_CACHE:
        return _LEDGER_CACHE[key]

    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError as exc:
        log.warning("research_triage: ledger read failed: %s", exc)
        return []
    if use_cache:
        # One entry is enough: the cache exists to collapse repeated reads of
        # ONE file inside ONE run, not to hold a history of versions.
        _LEDGER_CACHE.clear()
        _LEDGER_CACHE[key] = out
    return out


def clear_ledger_cache() -> None:
    """Drop the parsed-ledger cache (tests, and any writer that wants a re-read)."""
    _LEDGER_CACHE.clear()


def recorded_vetoes(root=None, cfg: dict | None = None, *,
                    as_of=None, window_days: int = 7) -> dict[str, dict]:
    """Demotions the nightly veto pass recorded and has NOT since cleared.

    THE PLANNER'S ONLY VIEW OF THE LLM.  The planner itself never calls a model:
    it recomputes the deterministic W-score (pure, offline, cheap) and reads the
    veto verdicts from the ledger the nightly wrote.  An absent ledger yields
    {} and the planner runs on the deterministic score alone — which is exactly
    the right degradation, because the veto can only ever have LOWERED a rank.

    A LATER VERDICT CLEARS AN EARLIER ONE.  Rows are walked oldest-first and the
    LAST verdict inside the window wins, so a report demoted on Monday and left
    alone on Tuesday is no longer demoted on Tuesday.  The first version only
    ever collected demotions, so a `thin` verdict on a stub that the vault later
    re-extracted properly would have suppressed that report for the whole
    window — a demote-only mechanism must still be able to stop demoting.
    """
    ref = _as_date(as_of) or date.today()
    lo = (ref - timedelta(days=max(0, int(window_days)))).isoformat()
    hi = ref.isoformat()

    latest: dict[str, tuple[str, dict | None]] = {}
    for row in read_ledger(root, cfg):
        if row.get("schema") == RUN_SCHEMA:
            continue
        when = str(row.get("as_of") or "")
        if not when or not (lo <= when <= hi):
            continue
        rid = str(row.get("report_id") or "")
        if not rid:
            continue
        # A row that never reached the veto head carries no verdict either way
        # and must not clear a real one from a run that did read it.
        if row.get("status") not in VETO_ELIGIBLE_STATUSES:
            continue
        veto = row.get("veto")
        veto = veto if isinstance(veto, dict) and veto.get("demoted") else None
        prior = latest.get(rid)
        if prior is None or when >= prior[0]:
            latest[rid] = (when, veto)

    return {rid: veto for rid, (_when, veto) in latest.items() if veto}


def compact_ledger(path: Path, *, retention_days: int, as_of=None) -> dict:
    """Drop rows older than `retention_days`.  Returns {"before", "after", "dropped"}.

    Rewrites through a temp file and one atomic replace, so an interrupted
    compaction leaves the ledger exactly as it was rather than half a file.
    """
    if not path.exists():
        return {"before": 0, "after": 0, "dropped": 0}
    ref = _as_date(as_of) or date.today()
    cutoff = (ref - timedelta(days=max(0, int(retention_days)))).isoformat()

    kept: list[str] = []
    before = 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                before += 1
                try:
                    obj = json.loads(line)
                except ValueError:
                    kept.append(line.rstrip("\n"))   # keep what we cannot date
                    continue
                when = str((obj or {}).get("as_of") or "")
                if not when or when >= cutoff:
                    kept.append(line.rstrip("\n"))
    except OSError as exc:
        log.warning("research_triage: compaction read failed: %s", exc)
        return {"before": before, "after": before, "dropped": 0}

    dropped = before - len(kept)
    if dropped <= 0:
        return {"before": before, "after": before, "dropped": 0}
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("research_triage: compaction write failed: %s", exc)
        tmp.unlink(missing_ok=True)
        return {"before": before, "after": before, "dropped": 0}
    clear_ledger_cache()
    _annotate("notice", "research_triage_compaction",
              f"triage ledger compacted: {before} -> {len(kept)} row(s) "
              f"({dropped} older than {retention_days} days dropped)")
    return {"before": before, "after": len(kept), "dropped": dropped}


__all__ = [
    "SCHEMA", "RUN_SCHEMA", "SCORING_VERSION", "COMPONENT_NAMES", "TIERS",
    "STATUSES", "VETO_ELIGIBLE_STATUSES", "UNRANKED_STATUSES", "VETO_REASONS",
    "OPERATOR_LEVER_KEYS",
    "triage_config", "as_signal_item", "report_text",
    "institution_tier", "cluster_density", "relevance", "extraction_quality",
    "attention_potential", "novelty",
    "build_spine", "build_context", "load_peers",
    "weights", "w_score", "volume", "assign_tiers",
    "rank", "apply_vetoes", "shortlist", "ranked_order",
    "ledger_path", "ledger_rows", "run_header", "append_ledger", "read_ledger",
    "clear_ledger_cache", "compact_ledger", "recorded_vetoes",
    "effective_contributions",
]
