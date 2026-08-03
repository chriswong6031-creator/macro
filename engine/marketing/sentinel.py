"""engine.marketing.sentinel — Sentinel (trust_office) W1 plan-level gate.

De-escalate only: drop/quarantine/downgrade items; never originate or upgrade
content. Fully deterministic — no LLM anywhere in this module.

Public API:
    gate_plan(plan, cfg, *, receipts_age_days, graded_window, exceptions)
        -> (annotated_plan, report)   # no disk I/O; may PRINT ::warning
                                      # annotations for ramp config defects
    run_gate(root, *, plan, cfg, ...) -> report        # loads, gates, writes
    resolve_ramp(cfg, as_of, *, root, announce) -> ramp report (tiers + caps)
    resolve_ramp_tier(created, as_of, *, graduate_after_days,
                      weeks_1_2_days, weeks_3_4_days) -> tier name
    resolve_ramp_boundaries(ramp_cfg, *, announce) -> (weeks_1_2, weeks_3_4) days
    receipts_context(root, cfg=None) -> (age_days, graded_window)
    load_exceptions(root) -> {item_id: row}
    publish_enabled() -> bool                          # global kill-switch
    is_reply_item(item) -> bool                        # kind OR type (XG-W4)
    reply_send_cap(cfg, account_id, *, mode) -> int    # reply-desk rail cap
    mark_all_unverified(plan) -> None                  # crash-path stamp
    error_report(as_of=..., exc=...) -> dict           # fail-closed report shape
    write_report(root, report) -> Path
    reason_class(reason) -> "policy" | "overflow"

Reason classes: every quarantine reason is either
  * "overflow" — a capacity trim (daily/media/cashtag/slot caps). The content
    plan deliberately over-generates; the gate keeping the postable N is
    expected every night and needs no human attention.
  * "policy"   — a real ban-risk or content flag (lexicon, near-dup, shared
    media, disclosure, links, cherry-pick, stale receipts, disabled account).
    These are what the operator reviews.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
_CONTENT_PLAN_REL = Path("data") / "marketing" / "content_plan.json"
_SENTINEL_REPORT_REL = Path("data") / "marketing" / "sentinel_report.json"
_EXCEPTIONS_REL = Path("data") / "marketing" / "sentinel_exceptions.jsonl"
_CONFIG_REL = Path("config") / "marketing.yml"
_PROPHET_INDEX_REL = Path("site") / "prophet" / "index.json"

# ---------------------------------------------------------------------------
# Kill-switch
# ---------------------------------------------------------------------------

def publish_enabled() -> bool:
    """Global kill-switch.

    Returns True only if env MARKETING_PUBLISH_ENABLED is in
    {"1", "true", "yes"} (case-insensitive). Default False.
    The D02 actuator must check this per item before publishing.
    """
    val = os.environ.get("MARKETING_PUBLISH_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Reply identification + the reply-send cap (XG-W4)
# ---------------------------------------------------------------------------

def is_reply_item(item: dict) -> bool:
    """True when an item is a reply, whichever schema it arrived in.

    THE BUG THIS FIXES (charter §5, assigned to XG-W4): the cap counter below
    read ``item["type"] == "reply"`` only. Content-plan items key on ``type``,
    but outbox and reply-queue items key on ``kind``, so the gate could not see
    a reply arriving in the other schema.

    HONEST STATUS: this makes the counter CAPABLE, not yet exercised. No
    producer in the tree sets ``kind``/``type`` to "reply" today — the reply
    desk runs its own store and its own cap (``reply_send_cap`` +
    ``reply_queue.may_send``), and the content-plan producer that would feed
    THIS counter lands with the rest of the reply pipeline in XG-W6. Until then
    ``reply_cap_daily`` still counts zero in production; the difference is that
    it now counts correctly the moment something arrives, instead of being
    structurally unable to.
    """
    for field in ("kind", "type"):
        if str(item.get(field) or "").strip().lower() == "reply":
            return True
    return False


def reply_send_cap(cfg: dict, account_id: str, *, mode: str) -> int:
    """Effective per-account daily reply-SEND cap for the reply desk.

    Two rails, two authorities. ``max_replies_per_account_per_day`` (base +
    ramp) governs engine-originated reply items travelling the content-plan and
    outbox rail, and ``gate_plan`` still enforces it there. The REPLY DESK is a
    different rail: its own store, its own critics, and a human-supervised
    desktop session as the only sender. Its cap is the mode dial, per the
    charter's explicit ruling that reply caps "open per the mode dial only,
    never by a builder config edit".

    * M0 returns 0 unconditionally. This is the standing 0-cap (D08: "default to
      0 indefinitely unless the operator explicitly opens it"), and no config
      key can move it.
    * M1+ returns the configured per-account target, clamped to
      ``REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY``. The clamp is one-directional:
      config may lower the cap, never raise it past the ceiling.
    """
    if str(mode or "").strip().upper() == "M0":
        return 0

    rd = (cfg or {}).get("reply_desk") or {}
    # The whole-desk kill switch binds the cap too, so a disabled desk cannot be
    # left with a live per-account allowance. Truthiness, not `is False`, so a
    # hand-edited `enabled: 0` disables. Absent means enabled.
    if "enabled" in rd and not rd["enabled"]:
        return 0

    caps = rd.get("daily_caps") or {}
    per_account = caps.get("accounts") or {}
    raw = per_account.get(account_id, caps.get(
        "per_account_target", _DEFAULT_REPLY_TARGET_PER_ACCOUNT_PER_DAY))
    if raw is None:
        # An explicit null is an operator SILENCING one account, not a request
        # for the default. Falling through to 18 would be the opposite of the
        # instruction.
        return 0
    try:
        target = int(raw)
    except (TypeError, ValueError):
        print(
            f"::warning title=reply-cap-unparseable::reply_desk daily cap {raw!r} for "
            f"{account_id!r} is not an integer — falling back to 0 (no sends)",
            flush=True,
        )
        return 0

    if target < 0:
        target = 0
    if target > REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY:
        print(
            f"::warning title=reply-cap-clamped::reply_desk daily cap {target} for "
            f"{account_id!r} exceeds the hard ceiling "
            f"{REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY} — clamped",
            flush=True,
        )
        target = REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY
    return target


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1

# Conservative in-code defaults (all knobs are also in config/marketing.yml sentinel:)
# Base = weeks_1_2 tier: these are the missing-key fallbacks, so they assume a
# brand-new account.
#
# RAMP LAW (enforced 2026-07-27; the old "D02 raises caps by ramp tier" premise
# died when the base caps went unlimited on 2026-07-24): an account that has not
# GRADUATED is governed by the STRICTER of (this base block, its age tier's row in
# sentinel.ramp) — numeric caps take the minimum with -1/unlimited as the loosest
# value, links_allowed is a logical AND, min_minutes_between_posts takes the
# maximum. A ramp row can therefore only ever tighten a cold account, never loosen
# a warm one; a graduated account (age >= ramp.graduate_after_days) uses the base
# block untouched, which is what preserves the operator's unlimited-cadence
# ruling for warmed accounts. See resolve_ramp().
# A drift-guard test asserts these match config/marketing.yml sentinel:.
_DEFAULT_NEAR_DUP_JACCARD = 0.50              # "substantially similar" policy bar
_DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY = 2    # weeks_1_2 floor
_DEFAULT_MIN_MINUTES_BETWEEN_POSTS = 45        # NOT enforced at plan tier (slots have
                                               # no timestamps); contract value the D02
                                               # actuator must read from sentinel config.
                                               # 45-min ladder re-spec (2026-07-27):
                                               # was 120, now matches config default 45.
_DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY = 1  # weeks_1_2 floor
_DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY = 0
_DEFAULT_MAX_RECEIPT_AGE_DAYS = 7
_DEFAULT_LINKS_ALLOWED = False                 # forbidden until week 5 (D08 R2)
_DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY = 1   # weeks_1_2 floor (D08 R4)
_DEFAULT_MAX_CASHTAGS_PER_POST = 3             # per-post breadth cap (D08 R3)
_DEFAULT_MAX_NEW_FOLLOWS_PER_ACCOUNT_PER_DAY = 0   # follow churn = fastest ban trigger (D08 R7)
# Whether a `type: signal` post (a directional call) must carry a not-financial-
# advice / "historical, not a guarantee" / do-your-own-research anchor before it
# clears the gate. Code default True is the safe missing-key fallback; the operator
# may disable it via config/marketing.yml sentinel.require_signal_disclosure. This
# is DISTINCT from the FTC / network-affiliation disclosure regime (Agentic Media
# rev-3, #3490) — flipping it never touches the advice-lexicon guard below, which
# always bans reckless phrasing ("guaranteed", "can't lose", "to the moon", …).
_DEFAULT_REQUIRE_SIGNAL_DISCLOSURE = True

# ── Post-time gates (ported from #3928, adapted 2026-07-29) ──────────────────
# These three knobs govern gates that run at PUBLISH time, not plan time, over
# the same-day posted history of one account. They are deliberately lane-blind:
# the nightly plan, the wire lanes, the press bridge and an operator "post now"
# all land in one account's day, and only the last gate before the network sees
# all of them at once. See the "Post-time gates" section below for the
# functions, and scripts/marketing_publisher.py for the call sites.
#
# Per-account TEMPLATE-FRAME similarity. Two posts by one account on one day
# whose skeletons (tickers and numbers blanked) score at or above this are the
# same post wearing two tickers. Measured over the live outbox on 2026-07-29:
# 124 same-(account, day) pairs among approved/posted items, exactly ONE at or
# over 0.60 — flagship's "$PLTR into the week" / "$MSFT into the week" pair from
# 2026-07-25, at 0.778, which is precisely the defect. The next-highest pair
# scores 0.500, so 0.60 sits in a real gap rather than on a slope.
_DEFAULT_FRAME_SIMILARITY = 0.60
# Per-account daily cap on the no-ticker, no-chart kinds. Kelly's ENTIRE
# 2026-07-28 output was four macro/education posts, each a different way to say
# "I post my results", so after the operator's review she shipped nothing. One a
# day per desk: they are seasoning, not a meal.
#
# THE PLAN SIDE HONOURS THE SAME NUMBER. content_studio.apply_reuse_budget reads
# this key too (see filler_budget_for) and trims the emitted day down to it, so
# this cap is a cross-lane BACKSTOP rather than a publish-time scythe through
# work the allocator planned. Without that, arming this at 1 would have
# quarantined 6 of flagship's 6 planned filler posts every night (measured on
# the 2026-07-28/29 plans) with nothing upstream saying so.
_DEFAULT_MAX_FILLER_PER_ACCOUNT_PER_DAY = 1
#: The kinds the filler cap covers: no ticker, no chart, no per-name evidence.
FILLER_KINDS: frozenset[str] = frozenset({"macro", "event", "education"})
# The substance floor: an ORIGINATED post names a cashtag and states a quantity.
#
# SHIPS DARK (false here and in config/marketing.yml). Arming it drops the
# no-ticker kinds outright — macro/event/education and the planner's ticker-free
# watchlist slot cannot name a cashtag by construction — which is a product
# ruling about whether those lanes exist at all, not a bug fix. So the gate is
# built, tested and CALLED every sweep, but only counts and annotates what it
# WOULD refuse until the operator flips the key. That is the same land-dark
# shape cadence_resolver.enabled uses, and for the same reason: reading one
# cycle of the verdict is the precondition for the arming decision.
_DEFAULT_REQUIRE_TICKER_AND_NUMBER = False
_CASHTAG_IN_TEXT_RE = re.compile(r"\$[A-Z]{1,5}\b")
# Deliberately looser than copywriter._NUMBER_RE, which skips bare 1-2 digit
# integers so "T1" and "3 weeks" do not read as invented prices. Here ANY digit
# counts: the question is "does this post state a quantity at all", not "is
# every quantity whitelisted".
_SUBSTANCE_NUMBER_RE = re.compile(r"\d")

# ── Reply desk send cap (XG-W4) ──────────────────────────────────────────────
# A SEPARATE rail from _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY above: that key
# governs engine-originated reply items on the content-plan/outbox rail, while
# these govern the reply desk's own store and its desktop sender. See
# reply_send_cap() for why the two do not merge.
#
# The hard ceiling comes from the growth doctrine (charter §3): 15-20/day is the
# quality bar, 30 is the wall. It is a CODE constant, not a config key, precisely
# because the charter says reply caps open per the mode dial "never by a builder
# config edit" — a config typo must not be able to raise it.
REPLY_HARD_CEILING_PER_ACCOUNT_PER_DAY = 30
#: Target used when the dial is open but no per-account target is configured.
_DEFAULT_REPLY_TARGET_PER_ACCOUNT_PER_DAY = 18

# ── Age ramp (D08 §3) ────────────────────────────────────────────────────────
# Tier names are the config/marketing.yml sentinel.ramp keys. "graduated" is not
# a config row: it means "old enough that the ramp no longer applies", and such an
# account is governed by the base block alone.
_TIER_WEEKS_1_2 = "weeks_1_2"
_TIER_WEEKS_3_4 = "weeks_3_4"
_TIER_WEEK_5_PLUS = "week_5_plus"
_TIER_GRADUATED = "graduated"
_RAMP_TIER_ORDER: tuple[str, ...] = (_TIER_WEEKS_1_2, _TIER_WEEKS_3_4, _TIER_WEEK_5_PLUS)

# Tier boundaries in days of account age (as_of - created), half-open on the left:
# on the DEFAULT schedule age 13 is still weeks_1_2 and age 14 is weeks_3_4.
#
# These are CODE DEFAULTS ONLY as of 2026-08-03 — `sentinel.ramp.weeks_1_2_days`
# and `sentinel.ramp.weeks_3_4_days` override them (resolve_ramp_boundaries). The
# ramp is a PLATFORM-RISK throttle (a days-old account must not post like a
# spambot), not a content-quality gate, so how fast a new desk walks it is an
# operator lever and belongs in config. It was hardcoded here, which is why
# "speed up the ramp" was a code change: a desk created six days ago sat on the
# week-1 tier with theme_list banned until day 28, and kelly's only at-bat of her
# entire life was a theme_list her tier forbade.
#
# An absent, junk, or incoherent config resolves back to exactly these numbers,
# so a config that never mentions the keys behaves byte-identically to before.
_RAMP_WEEKS_1_2_MAX_DAYS = 14
_RAMP_WEEKS_3_4_MAX_DAYS = 28
_DEFAULT_GRADUATE_AFTER_DAYS = 56

# Caps whose -1 means "unlimited" (loosest possible value in a stricter-of merge).
_RAMP_UNLIMITED_CAPS: tuple[str, ...] = (
    "max_posts_per_account_per_day",
    "max_media_posts_per_account_per_day",
)
# Plain non-negative integer caps: stricter = smaller.
_RAMP_BOUNDED_CAPS: tuple[str, ...] = (
    "max_same_cashtag_per_account_per_day",
    "max_replies_per_account_per_day",
    "max_new_follows_per_account_per_day",
    "max_cashtags_per_post",
)
# Boolean permissions: stricter = logical AND.
_RAMP_BOOL_KNOBS: tuple[str, ...] = ("links_allowed", "theme_list_allowed")
# Waits: stricter = the LONGER wait.
_RAMP_MAX_WINS_KNOBS: tuple[str, ...] = ("min_minutes_between_posts",)

# theme_list default: allowed. Readable from the base sentinel: block AND from a
# tier row (the merge is a logical AND, so either can turn the format off). The
# True default keeps every config that never mentions it byte-identical.
_DEFAULT_THEME_LIST_ALLOWED = True

# Financial-advice lexicon — defense-in-depth at the plan layer.
# Some overlap with copywriter._BANNED_VOCAB is intentional (different layers).

# Mirrors the copywriter disclosure check (validate_copy §6) — keep the anchor
# SET in sync, but sentinel matches single-word tokens with \b word boundaries
# where copywriter substring-matches. That asymmetry is deliberate: copywriter's
# substring match accepts "grade" inside "upgraded"; the plan-level gate must not.
_DISCLOSURE_PHRASES_MULTI: tuple[str, ...] = (
    "size appropriately",
    "not financial advice",
    "not a guarantee",
    "do your own",
    "position sizing",
    "track it",
    "what would change",
)
_DISCLOSURE_PATTERNS_SINGLE: tuple[re.Pattern, ...] = tuple(
    re.compile(r"\b" + word + r"\b", re.IGNORECASE)
    for word in ("historical", "publicly", "grade", "receipt")
)

_DEFAULT_LEXICON_PHRASES: list[str] = [
    "you should buy",
    "you should sell",
    "get in now",
    "get in before",
    "guaranteed",
    "can't lose",
    "cannot lose",
    "sure thing",
    "easy money",
    "risk-free",
    "risk free",
    "free money",
    "no-brainer",
    "back up the truck",
    "load up",
    "all-in",
    "to the moon",
    "price target guaranteed",
]

_DEFAULT_LEXICON_PATTERNS: list[str] = [
    r"\b(will|going to|gonna)\s+(hit|reach|touch|double|triple|10x)\b",
    r"\bcan'?t\s+(go|drop|fall)\b",
]

# Item types considered "receipt" for stale-receipts logic
_RECEIPT_TYPES: frozenset[str] = frozenset({"receipt"})

# Reasons the operator exception queue can NEVER override.
_ALWAYS_ENFORCED: frozenset[str] = frozenset({"account_disabled", "stale_receipts_ledger"})

# Capacity-trim reason heads (everything else is a policy flag).
_OVERFLOW_REASON_HEADS: frozenset[str] = frozenset({
    "cadence_cap_daily",
    "reply_cap_daily",
    "media_cap_daily",
    "cashtag_cap",
    "slot_collision",
})


def reason_class(reason: str) -> str:
    """Classify a quarantine reason: "overflow" (capacity trim) or "policy" (real flag)."""
    head = reason.split(":", 1)[0]
    return "overflow" if head in _OVERFLOW_REASON_HEADS else "policy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# Recognized publish-time slot families — each is its own per-day cap bucket.
_SLOT_PUBLISH_FAMILIES: frozenset[str] = frozenset({"MOVER", "THEME", "CONF"})


def _slot_day_bucket(slot: str) -> str:
    """The per-day cap bucket for a slot label.

    A nightly plan slot is ``D<n>-<AM|PM|EOD>`` — day n is its own bucket (``D3``),
    so a 2-a-day cap applies within each day, not across the 7-day plan (the bug
    that quarantined ~85 of 111 items). A publish-time slot (``MOVER-01`` /
    ``THEME-02`` / ``CONF-01``) buckets by its family. Anything else — an absent
    or unrecognized slot label — shares a single ``""`` bucket per account (so a
    plan with ad-hoc, undated slots still caps per account, plan-wide).
    """
    if not slot:
        return ""
    prefix = slot.split("-", 1)[0]
    if len(prefix) >= 2 and prefix[0] == "D" and prefix[1:].isdigit():
        return prefix  # D1..D7 — the day
    if prefix in _SLOT_PUBLISH_FAMILIES:
        return prefix
    return ""


def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory (same pattern as governor)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_sentinel_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def write_report(root: Path | str | None, report: dict) -> Path:
    """Atomically write the sentinel report to its canonical path. Returns the path."""
    path = _repo_root(root) / _SENTINEL_REPORT_REL
    _write_json_atomic(path, report)
    return path


def _token_set(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", text.lower()))


def _jaccard_sets(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _item_text(item: dict) -> str:
    headline = str(item.get("headline") or "")
    body = str(item.get("body") or "")
    return f"{headline} {body}"


def _cfg_sentinel(cfg: dict) -> dict:
    """Extract the sentinel config block, falling back to an empty dict."""
    return (cfg.get("sentinel") or {}) if isinstance(cfg, dict) else {}


def _get(block: dict, key: str, default: Any) -> Any:
    v = block.get(key)
    return v if v is not None else default


def _cap(block: dict, key: str, default: int) -> int:
    """Read a non-negative integer cap knob (bad values fall back to default)."""
    try:
        return max(0, int(_get(block, key, default)))
    except (TypeError, ValueError):
        return default


def _cap_unlimited(block: dict, key: str, default: int) -> int | None:
    """Like _cap, but ``-1`` (or the string ``"unlimited"``) means NO limit —
    returns None, which the cadence-cap checks read as "do not bound".

    Used for the caps the autonomous-posting policy lifts: daily posts and daily
    media (operator 2026-07-24 — unlimited volume, paced instead by the post-time
    10-minute floor + the 2-week link gate). ``null`` is NOT the sentinel: _get
    collapses a present-null back to the default, so unlimited must be an explicit
    ``-1``. A missing key still falls back to the (bounded, safe) default.
    """
    raw = _get(block, key, default)
    if isinstance(raw, str) and raw.strip().lower() == "unlimited":
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return None if val < 0 else val


def _flag(block: dict, key: str, default: bool) -> bool:
    """Read a boolean policy knob STRICTLY.

    A quoted ``"false"`` in YAML must never silently enable a policy — the same
    parse outbox.sentinel_contract uses, because links_allowed guards D08 R2.
    """
    v = _get(block, key, default)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


# ─────────────────────────────────────────────────────────────────────────────
# Post-time gates (ported from #3928)
#
# WHY THESE ARE NOT IN gate_plan. gate_plan screens ONE nightly plan. The defects
# below are properties of an ACCOUNT'S DAY, and an account's day is assembled
# from lanes that never share a plan: the nightly content plan, the wire/breaking
# lanes, the press bridge, publish-time movers, and an operator "post now" click.
# The publisher's loop is the only place all of them are visible at once, which is
# the same reasoning that put the banned-language and headline-shape gates there
# (a queued item from an older vintage walks around every generation-time check).
#
# Everything here is a PURE function over text the caller already has. The
# publisher owns the state read; this module stays free of an outbox import so
# minimal-env CI keeps importing it.
# ─────────────────────────────────────────────────────────────────────────────

# A cashtag with or without its "$", so "$TEL close to going" and "TEL closed
# above 41" blank to the same frame.
_SKELETON_TICKER_RE = re.compile(r"\$?[A-Z]{2,5}\b")
_SKELETON_NUMBER_RE = re.compile(r"[\d.,%$-]+")


def skeleton(text: str) -> str:
    """The copy with every ticker and number blanked. What is left is the frame.

    THE DEFECT THIS MEASURES. On 2026-07-28 the founder desk shipped "$TEL close
    to going", "$CBOE close to going" and "$FDS close to going" in one day, two
    of them sharing the byte-identical tail "Almost there. Haven't touched it.
    Watching live." Every same-account dedup gate in the tree missed it, and
    always would: they compare TOKEN sets, the tickers and prices differ, so
    three renders of ONE template read as three different posts (token Jaccard
    measured 0.3-0.4). Blank the tickers and the numbers and the template is
    what remains.
    """
    out = _SKELETON_TICKER_RE.sub("X", text or "")
    return _SKELETON_NUMBER_RE.sub("N", out)


def skeleton_tokens(text: str) -> frozenset[str]:
    """Token set of :func:`skeleton` — the comparable form the gate caches."""
    return _token_set(skeleton(text))


def skeleton_similarity(a: str, b: str) -> float:
    """Token Jaccard over the two skeletons. 1.0 = the same template."""
    return _jaccard_sets(skeleton_tokens(a), skeleton_tokens(b))


def frame_similarity_threshold(cfg: dict) -> float:
    """``sentinel.frame_similarity`` (bad values fall back to the code default)."""
    try:
        return float(_get(_cfg_sentinel(cfg), "frame_similarity",
                          _DEFAULT_FRAME_SIMILARITY))
    except (TypeError, ValueError):
        return _DEFAULT_FRAME_SIMILARITY


def frame_repeat_of(
    tokens: frozenset[str],
    prior: "list[tuple[str, frozenset[str]]] | tuple[tuple[str, frozenset[str]], ...]",
    *,
    threshold: float = _DEFAULT_FRAME_SIMILARITY,
) -> "tuple[str, float] | None":
    """First (prior_id, score) whose frame matches ``tokens``, else None.

    ``prior`` is (id, skeleton_tokens) for the SAME account's SAME day. Both
    scopings are deliberate: two desks may legitimately share a house frame (they
    are different voices to different audiences), and one desk reusing a frame
    next week is cadence, not spam.
    """
    for prev_id, prev_tokens in prior or ():
        score = _jaccard_sets(tokens, prev_tokens)
        if score >= threshold:
            return (str(prev_id), score)
    return None


def is_filler_kind(kind: Any) -> bool:
    """Is this one of the no-ticker, no-chart kinds the filler cap covers?"""
    return str(kind or "").strip().lower() in FILLER_KINDS


def max_filler_per_account_per_day(cfg: dict) -> int | None:
    """``sentinel.max_filler_per_account_per_day``; None means unlimited (-1)."""
    return _cap_unlimited(_cfg_sentinel(cfg), "max_filler_per_account_per_day",
                          _DEFAULT_MAX_FILLER_PER_ACCOUNT_PER_DAY)


def require_ticker_and_number(cfg: dict) -> bool:
    """Is the substance floor ARMED? (``sentinel.require_ticker_and_number``)

    False (the shipped default) does not mean "do not evaluate": the publisher
    still computes :func:`substance_gap` for every originated post and annotates
    what arming would refuse. See _DEFAULT_REQUIRE_TICKER_AND_NUMBER.
    """
    return _flag(_cfg_sentinel(cfg), "require_ticker_and_number",
                 _DEFAULT_REQUIRE_TICKER_AND_NUMBER)


def substance_gap(text: str, *, ticker: str = "") -> str | None:
    """Which half of the substance floor a post fails: "ticker", "number", None.

    THE BAR (operator 2026-07-28): "a post must name a ticker, state a dated fact
    with its numbers, and then say something that FOLLOWS from that fact." This
    covers the first two clauses. ``ticker`` is whatever the caller already
    resolved (outbox items carry it on ``source.ticker``, content-plan items on
    ``cashtag``/``ticker``); the copy's own cashtag is the fallback, so a lane
    that stamps no ticker field is still judged on what the reader sees.
    """
    body = text or ""
    has_tag = bool(str(ticker or "").strip()) or bool(_CASHTAG_IN_TEXT_RE.search(body))
    if not has_tag:
        return "ticker"
    if not _SUBSTANCE_NUMBER_RE.search(body):
        return "number"
    return None


def _parse_iso_date(raw: Any) -> "date | None":
    """``YYYY-MM-DD`` (or the date half of an ISO timestamp) → date, else None."""
    s = str(raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _ramp_days(raw: Any, default: int) -> int:
    """One tier-boundary knob → int, DEFENSIVELY.

    Missing, ``None``, junk, a float string, a bool — all resolve to the code
    default. This block is an operator lever for how fast a new desk walks the
    ramp; it must never become a load-bearing dependency that can break the gate.
    ``bool`` is rejected explicitly because ``int(True) == 1`` would otherwise
    read a stray ``weeks_1_2_days: true`` as a one-day tier.
    """
    if isinstance(raw, bool):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _coherent_boundaries(weeks_1_2_days: Any, weeks_3_4_days: Any, *,
                         announce: bool = False) -> "tuple[int, int]":
    """Validate the two tier boundaries; fall back to BOTH defaults if incoherent.

    The ladder is only meaningful while ``0 < weeks_1_2_days < weeks_3_4_days``.
    Anything else (a negative, a zero, an inverted pair, an equal pair that
    deletes weeks_3_4 entirely) is a config typo, and half-applying it would hand
    a brand-new account a tier it has not earned — so BOTH values revert to the
    shipped defaults together rather than one of them being silently repaired.
    """
    w12 = _ramp_days(weeks_1_2_days, _RAMP_WEEKS_1_2_MAX_DAYS)
    w34 = _ramp_days(weeks_3_4_days, _RAMP_WEEKS_3_4_MAX_DAYS)
    if not (0 < w12 < w34):
        if announce:
            _ramp_boundaries_annotation(weeks_1_2_days, weeks_3_4_days)
        return _RAMP_WEEKS_1_2_MAX_DAYS, _RAMP_WEEKS_3_4_MAX_DAYS
    return w12, w34


def resolve_ramp_boundaries(ramp_cfg: Any, *,
                            announce: bool = True) -> "tuple[int, int]":
    """``(weeks_1_2_days, weeks_3_4_days)`` from a ``sentinel.ramp`` block.

    Both keys are optional; absent ⇒ the shipped 14/28 schedule, which is what
    keeps every config written before 2026-08-03 behaving byte-identically.
    """
    block = ramp_cfg if isinstance(ramp_cfg, dict) else {}
    return _coherent_boundaries(block.get("weeks_1_2_days"),
                                block.get("weeks_3_4_days"), announce=announce)


def effective_graduate_after_days(
    raw: Any,
    *,
    weeks_3_4_days: int = _RAMP_WEEKS_3_4_MAX_DAYS,
) -> int:
    """``graduate_after_days``, CLAMPED to at least the weeks_3_4 boundary.

    Below that boundary the knob is inert rather than strict: the ``age <
    weeks_1_2_days`` and ``age < weeks_3_4_days`` branches fire first, so a
    configured 20 under the default 14/28 schedule would never graduate anyone at
    20 — it would only delete the week_5_plus window while accounts kept ramping
    to 28 anyway. Clamping makes the number mean what it says at every value it
    can take; the resolved value is printed in the gate report so a clamped
    config is visible rather than silently reinterpreted.

    The clamp floor is the CONFIGURED boundary, not the module constant: on the
    2026-08-03 fast schedule (5/10) a ``graduate_after_days: 21`` is a real
    21-day graduation, where the old code silently clamped it up to 28.
    """
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return max(int(weeks_3_4_days), _DEFAULT_GRADUATE_AFTER_DAYS)
    return max(int(weeks_3_4_days), val)


def resolve_ramp_tier(
    created: Any,
    as_of: Any,
    *,
    graduate_after_days: int = _DEFAULT_GRADUATE_AFTER_DAYS,
    weeks_1_2_days: int = _RAMP_WEEKS_1_2_MAX_DAYS,
    weeks_3_4_days: int = _RAMP_WEEKS_3_4_MAX_DAYS,
) -> str:
    """The D08 ramp tier for an account, from account age in days.

    Age is ``as_of - created`` where BOTH come from the plan inputs — never a
    wall clock. Re-gating the same plan must always produce the same verdict, so
    a gate that reads ``datetime.now()`` here would be a determinism bug, not a
    convenience.

        age <  weeks_1_2_days        -> weeks_1_2
        age <  weeks_3_4_days        -> weeks_3_4
        age <  graduate_after_days   -> week_5_plus
        age >= graduate_after_days   -> graduated  (base caps only)

    The two boundaries default to the shipped 14/28 and are overridden by
    ``sentinel.ramp.weeks_1_2_days`` / ``weeks_3_4_days`` (resolve_ramp threads
    them through). An incoherent pair reverts to the defaults — see
    _coherent_boundaries; the config-level call is the one that annotates.

    ``graduate_after_days`` is clamped to >= ``weeks_3_4_days`` (see
    effective_graduate_after_days) because below that it is inert.

    FAILS CLOSED to weeks_1_2 (the strictest tier) when either date is missing or
    unparseable, and when ``created`` is in the future relative to ``as_of``
    (corrupt data must not read as an aged account).
    """
    w12, w34 = _coherent_boundaries(weeks_1_2_days, weeks_3_4_days)
    c = _parse_iso_date(created)
    a = _parse_iso_date(as_of)
    if c is None or a is None:
        return _TIER_WEEKS_1_2
    age = (a - c).days
    if age < 0:
        return _TIER_WEEKS_1_2
    if age < w12:
        return _TIER_WEEKS_1_2
    if age < w34:
        return _TIER_WEEKS_3_4
    if age < effective_graduate_after_days(graduate_after_days,
                                           weeks_3_4_days=w34):
        return _TIER_WEEK_5_PLUS
    return _TIER_GRADUATED


def _base_caps(sc: dict) -> dict[str, Any]:
    """The base (non-ramped) cap contract, resolved from the sentinel: block.

    ``None`` in an unlimited-capable cap means NO limit (config ``-1``).
    """
    return {
        "max_posts_per_account_per_day": _cap_unlimited(
            sc, "max_posts_per_account_per_day", _DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY),
        "max_media_posts_per_account_per_day": _cap_unlimited(
            sc, "max_media_posts_per_account_per_day",
            _DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY),
        "max_same_cashtag_per_account_per_day": _cap(
            sc, "max_same_cashtag_per_account_per_day",
            _DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY),
        "max_replies_per_account_per_day": _cap(
            sc, "max_replies_per_account_per_day", _DEFAULT_MAX_REPLIES_PER_ACCOUNT_PER_DAY),
        "max_new_follows_per_account_per_day": _cap(
            sc, "max_new_follows_per_account_per_day",
            _DEFAULT_MAX_NEW_FOLLOWS_PER_ACCOUNT_PER_DAY),
        "max_cashtags_per_post": _cap(
            sc, "max_cashtags_per_post", _DEFAULT_MAX_CASHTAGS_PER_POST),
        "min_minutes_between_posts": _cap(
            sc, "min_minutes_between_posts", _DEFAULT_MIN_MINUTES_BETWEEN_POSTS),
        "links_allowed": _flag(sc, "links_allowed", _DEFAULT_LINKS_ALLOWED),
        # Config-readable like every other base knob (the tier rows AND this can
        # each turn the format off; the merge is a logical AND). Default True, so
        # a config that never mentions it behaves exactly as before.
        "theme_list_allowed": _flag(sc, "theme_list_allowed", _DEFAULT_THEME_LIST_ALLOWED),
    }


def _tier_int(tier_row: dict, tier_name: str, key: str,
              *, announce: bool = True) -> "tuple[bool, int | None]":
    """Read one numeric knob out of a ramp tier row.

    Returns ``(parsed_ok, value)`` where ``value is None`` means "unlimited"
    (``-1`` or the string ``"unlimited"``). ``parsed_ok`` False means the value is
    junk — a typo, or a present-``null`` — and the CALLER MUST IGNORE IT rather
    than substitute a fallback: substituting is what made a one-word typo either
    quarantine 100% of a plan or silently loosen a cap, depending on which merge
    branch happened to read it.
    """
    raw = tier_row.get(key)
    if isinstance(raw, str) and raw.strip().lower() == "unlimited":
        return True, None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        if announce:
            _tier_value_annotation(tier_name, key, raw)
        return False, None
    return True, (None if val < 0 else val)


def _stricter_caps(base: dict[str, Any], tier_row: dict, *,
                   tier_name: str = "", announce: bool = True) -> dict[str, Any]:
    """Merge one ramp tier row onto the base caps, KEEPING THE STRICTER of each.

    * unlimited-capable numeric caps → minimum, with ``None`` (unlimited) as the
      loosest value: base ``-1`` + tier ``2`` ⇒ ``2``.
    * bounded numeric caps → minimum.
    * boolean permissions → logical AND: base ``false`` + tier ``true`` ⇒ ``false``.
    * min_minutes_between_posts → maximum (the longer wait wins).

    Keys absent from the tier row leave the base value untouched, so a partial
    tier row is legal and narrows only what it names. An UNPARSEABLE tier value is
    treated exactly like an absent one — base governs — plus a ``::warning``, so
    the two failure directions a typo used to pick between are now one visible
    behaviour.
    """
    out = dict(base)
    if not isinstance(tier_row, dict):
        return out

    for key in _RAMP_UNLIMITED_CAPS:
        if key not in tier_row:
            continue
        ok, tier_val = _tier_int(tier_row, tier_name, key, announce=announce)
        if not ok or tier_val is None:
            continue        # junk, or the tier says unlimited — neither loosens base
        base_val = base.get(key)
        out[key] = tier_val if base_val is None else min(base_val, tier_val)

    for key in _RAMP_BOUNDED_CAPS:
        if key not in tier_row:
            continue
        ok, tier_val = _tier_int(tier_row, tier_name, key, announce=announce)
        if not ok or tier_val is None:
            continue        # a bounded knob written as -1 places no tier bound
        out[key] = min(int(base.get(key, 0)), tier_val)

    for key in _RAMP_MAX_WINS_KNOBS:
        if key not in tier_row:
            continue
        ok, tier_val = _tier_int(tier_row, tier_name, key, announce=announce)
        if not ok or tier_val is None:
            continue
        out[key] = max(int(base.get(key, 0)), tier_val)

    for key in _RAMP_BOOL_KNOBS:
        if key not in tier_row:
            continue
        out[key] = bool(base.get(key, True)) and _flag(tier_row, key, True)

    return out


# Annotations already emitted by THIS process, keyed by what they are about.
# resolve_ramp is called several times per run (the gate, the per-account cap
# resolver, the publish-time lane), and a config defect does not become more true
# by being printed six times — the Actions summary should carry it once.
_ANNOUNCED: set[str] = set()


def reset_ramp_announcements() -> None:
    """Clear the once-per-process annotation memo. Tests only — a test that
    asserts on an annotation must not be silenced by an earlier test's call."""
    _ANNOUNCED.clear()


def _announce_once(key: str, message: str, log_msg: str, *log_args: Any) -> bool:
    """Emit a GitHub annotation at most once per process. True if it printed.

    A bare ``print`` at line start is LOAD-BEARING: every builder here logs with a
    prefixing format, so ``log.warning("::warning …")`` emits ``WARNING ::warning …``
    and GitHub silently drops it (tests/test_gh_annotation_line_start.py). ``flush``
    matters too — stdout is block-buffered when piped in CI. The human-readable
    ``log.*`` line is separate on purpose and carries no ``::`` prefix.
    """
    if key in _ANNOUNCED:
        return False
    _ANNOUNCED.add(key)
    print(message, flush=True)
    log.warning(log_msg, *log_args)
    return True


def _ramp_annotation(account_id: str) -> None:
    """An ENABLED account with no usable ``created:`` date — fails closed."""
    _announce_once(
        f"created:{account_id}",
        f"::warning title=sentinel-ramp-created-missing::desk_network account "
        f"'{account_id}' is enabled but carries no usable created: date — the D08 "
        f"age ramp fails closed to weeks_1_2 (strictest caps). Set created: "
        f"YYYY-MM-DD in config/marketing.yml to the account's real registration date.",
        "sentinel.resolve_ramp: enabled account %r has no usable created: date — "
        "falling back to the %s tier", account_id, _TIER_WEEKS_1_2,
    )


def _as_of_annotation(as_of: str) -> None:
    """A missing/unparseable plan as_of — the tier of EVERY account fails closed.

    Louder than the per-account case by nature: without a reference date the whole
    network reads as week-1, so a plan that silently lost its as_of would look
    like a correctly-throttled cold network instead of a broken one.
    """
    _announce_once(
        "as_of",
        f"::warning title=sentinel-ramp-as-of-missing::plan as_of {as_of!r} is "
        f"missing or unparseable — the D08 age ramp cannot compute account age and "
        f"fails closed to weeks_1_2 for EVERY account (strictest caps, network-wide). "
        f"Expected YYYY-MM-DD on the plan being gated.",
        "sentinel.resolve_ramp: as_of %r unusable — every account falls back to "
        "the %s tier", as_of, _TIER_WEEKS_1_2,
    )


def _tier_value_annotation(tier_name: str, key: str, raw: Any) -> None:
    """An unparseable value in a ramp tier row — the tier value is IGNORED.

    Both merge branches used to fail silently and in OPPOSITE directions: the
    unlimited-capable branch stored the -1 fallback as a bounded cap (making
    ``count >= -1`` always true, i.e. 100% quarantine), while the bounded branch
    fell back to the looser base. Neither said anything. Now both ignore the
    unparseable value — the base cap governs, which is the same answer as
    "this tier row does not mention this knob" — and say so out loud.
    """
    _announce_once(
        f"tier:{tier_name}:{key}",
        f"::warning title=sentinel-ramp-tier-value-unparseable::sentinel.ramp."
        f"{tier_name}.{key} is {raw!r}, which is not an integer — the tier value is "
        f"IGNORED and the base sentinel: block governs this knob. Fix the value in "
        f"config/marketing.yml (use -1 for unlimited, never null).",
        "sentinel: ramp.%s.%s=%r unparseable — ignoring the tier value",
        tier_name, key, raw,
    )


def _ramp_boundaries_annotation(weeks_1_2_days: Any, weeks_3_4_days: Any) -> None:
    """An incoherent tier-boundary pair — BOTH revert to the 14/28 defaults.

    Silence here would be the worst of the three failure directions: the ramp
    would keep resolving tiers with numbers nobody wrote, and a "we sped the ramp
    up" config edit would read as applied while every desk stayed on the old
    schedule.
    """
    _announce_once(
        "ramp_boundaries",
        f"::warning title=sentinel-ramp-boundaries-incoherent::sentinel.ramp "
        f"weeks_1_2_days={weeks_1_2_days!r} / weeks_3_4_days={weeks_3_4_days!r} "
        f"is not a usable ladder (need 0 < weeks_1_2_days < weeks_3_4_days) — BOTH "
        f"boundaries fall back to the code defaults "
        f"({_RAMP_WEEKS_1_2_MAX_DAYS}/{_RAMP_WEEKS_3_4_MAX_DAYS}). Fix the values "
        f"in config/marketing.yml.",
        "sentinel: ramp boundaries weeks_1_2_days=%r weeks_3_4_days=%r incoherent "
        "— falling back to %d/%d", weeks_1_2_days, weeks_3_4_days,
        _RAMP_WEEKS_1_2_MAX_DAYS, _RAMP_WEEKS_3_4_MAX_DAYS,
    )


def resolve_ramp(
    cfg: dict,
    as_of: Any,
    *,
    root: Path | str | None = None,
    announce: bool = True,
) -> dict[str, Any]:
    """Per-account ramp tier + the effective (stricter-of) caps that govern it.

    THE single tier-resolution seam: gate_plan (plan tier) and
    publish_time_content.generate_slot_items (publish tier) both read caps from
    here so the two lanes can never drift apart on what a cold account may post.

    Returns::

        {"enforced": bool,               # False when sentinel.ramp is absent/empty
         "graduate_after_days": int,
         "weeks_1_2_days": int,          # resolved tier-1 boundary (default 14)
         "weeks_3_4_days": int,          # resolved tier-2 boundary (default 28)
         "as_of": str,
         "base": {...caps...},           # the un-ramped contract
         "fallback": {...caps...},       # caps for an account not in desk_network
         "accounts": {account_id: {"created", "age_days", "tier", "enabled",
                                   "caps": {...}}},
         "missing_created": [account_id, ...],   # ENABLED accounts, annotated
         "as_of_usable": bool}                   # False ⇒ whole network failed closed

    ``enforced`` False (no ramp table) ⇒ every account resolves to the base caps
    and the whole feature is a no-op, which is what keeps configs written before
    2026-07-27 behaving byte-identically.

    NOT PURE: prints ``::warning`` annotations for the four config defects that
    would otherwise degrade the network silently (missing ``created:``, missing
    ``as_of``, an unparseable tier value, an incoherent boundary pair). Each is
    emitted at most ONCE per
    process — see _announce_once. ``announce=False`` silences them for callers
    that only want the numbers (admin reads, repeated cap lookups).
    """
    sc = _cfg_sentinel(cfg)
    base = _base_caps(sc)
    ramp_cfg = sc.get("ramp") if isinstance(sc.get("ramp"), dict) else {}
    tier_rows = {t: ramp_cfg.get(t) for t in _RAMP_TIER_ORDER
                 if isinstance(ramp_cfg.get(t), dict)}
    enforced = bool(tier_rows)
    # The tier ladder's own geometry, config-driven since 2026-08-03. Resolved
    # ONCE here and threaded down, so every account in one report is judged on
    # the same schedule and an incoherent pair is announced once, not per account.
    weeks_1_2_days, weeks_3_4_days = resolve_ramp_boundaries(
        ramp_cfg, announce=announce and enforced)
    graduate_after = effective_graduate_after_days(
        _get(ramp_cfg, "graduate_after_days", _DEFAULT_GRADUATE_AFTER_DAYS),
        weeks_3_4_days=weeks_3_4_days)

    as_of_s = str(as_of or "")
    as_of_d = _parse_iso_date(as_of_s)
    as_of_usable = as_of_d is not None
    # A plan that lost its as_of fails closed for EVERY account, which looks
    # exactly like a correctly-throttled cold network. Say it out loud.
    if enforced and not as_of_usable and announce:
        _as_of_annotation(as_of_s)

    out_accounts: dict[str, dict[str, Any]] = {}
    missing_created: list[str] = []
    # Merge each tier row ONCE (not once per account) so a malformed row cannot
    # emit N identical warnings, and so N accounts on one tier share a resolution.
    merged_tiers = {
        name: _stricter_caps(base, row, tier_name=name, announce=announce)
        for name, row in tier_rows.items()
    }

    from engine.marketing.accounts import effective_accounts as _eff_accounts  # noqa: PLC0415
    for acc in _eff_accounts(cfg if isinstance(cfg, dict) else {}, root):
        acc_id = str(acc.get("id", ""))
        if not acc_id:
            continue
        enabled = bool(acc.get("enabled"))
        created_raw = acc.get("created")
        created = _parse_iso_date(created_raw)
        age_days = (as_of_d - created).days if (created and as_of_d) else None

        if enforced and enabled and created is None:
            missing_created.append(acc_id)
            if announce:
                _ramp_annotation(acc_id)

        tier = (resolve_ramp_tier(created_raw, as_of_s,
                                  graduate_after_days=graduate_after,
                                  weeks_1_2_days=weeks_1_2_days,
                                  weeks_3_4_days=weeks_3_4_days)
                if enforced else _TIER_GRADUATED)
        caps = dict(merged_tiers.get(tier) or base)

        # Per-account override — sentinel.ramp.account_overrides.<id>.<cap>.
        # The tier ladder is age-based and uniform, which is right as a default
        # and wrong for a desk the operator has judged warmed up ahead of its
        # calendar age: on 2026-07-28 every enabled desk was <14 days old, so
        # flagship sat on the same 2-posts/day floor as a desk created that
        # morning. This is the ONLY way to widen one desk without either lying
        # about its `created:` date (which would silently move it through the
        # whole ramp) or loosening the tier for every account at once.
        #
        # LOOSENING here is deliberate and operator-scoped, so unlike
        # _stricter_caps this does NOT take the stricter of the two — an override
        # means what it says. It is announced in the gate report for exactly that
        # reason; an unexplained wide cap should be traceable to a named desk.
        _ov = (ramp_cfg.get("account_overrides") or {}).get(acc_id) or {}
        applied_overrides: dict[str, Any] = {}
        if isinstance(_ov, dict):
            for cap_key in _ov:
                if cap_key not in caps:
                    continue  # unknown knob: ignore rather than invent a cap
                if cap_key in _RAMP_BOOL_KNOBS:
                    # Boolean permission (links_allowed / theme_list_allowed).
                    # These used to fall through _tier_int, where `true` only
                    # worked because int(True) == 1 and a quoted "true" was
                    # discarded as a NUMERIC typo — so the one override the
                    # operator actually reached for on 2026-07-28 (flagship past
                    # the theme_list ramp, 18 sector lists dropped per sweep on
                    # a day semis were routing) was unexpressible. Parsed
                    # strictly; junk is ignored + announced like any tier typo,
                    # never coerced to False (a typo must not silently REVOKE).
                    raw = _ov.get(cap_key)
                    if isinstance(raw, bool):
                        val_b = raw
                    elif isinstance(raw, str) and raw.strip().lower() in (
                            "true", "false", "1", "0", "yes", "no"):
                        val_b = raw.strip().lower() in ("true", "1", "yes")
                    else:
                        if announce:
                            _tier_value_annotation(
                                f"account_overrides.{acc_id}", cap_key, raw)
                        continue
                    caps[cap_key] = val_b
                    applied_overrides[cap_key] = val_b
                    continue
                # Same parse contract as a tier row (-1/"unlimited" → None, junk
                # → ignored + ::warning), so an override typo behaves like a tier
                # typo instead of inventing a third failure mode.
                ok, val = _tier_int(_ov, f"account_overrides.{acc_id}", cap_key,
                                    announce=announce)
                if not ok:
                    continue
                caps[cap_key] = val
                applied_overrides[cap_key] = val

        out_accounts[acc_id] = {
            "created": str(created_raw or "") or None,
            "age_days": age_days,
            "tier": tier,
            "enabled": enabled,
            "caps": dict(caps),
            "overrides": applied_overrides,
        }

    # An account that appears in a plan but NOT in desk_network is a config bug;
    # fail closed to the strictest tier rather than handing it the warm caps.
    fallback = dict(merged_tiers.get(_TIER_WEEKS_1_2) or base)

    return {
        "enforced": enforced,
        "graduate_after_days": graduate_after,
        # The RESOLVED ladder geometry (config, or the code defaults when the
        # config is absent/incoherent) — the same visibility contract as the
        # clamped graduate_after_days above.
        "weeks_1_2_days": weeks_1_2_days,
        "weeks_3_4_days": weeks_3_4_days,
        "as_of": as_of_s,
        "as_of_usable": as_of_usable,
        "base": base,
        "fallback": fallback,
        "accounts": out_accounts,
        "missing_created": missing_created,
    }


def load_exceptions(root: Path | str | None = None) -> dict[str, dict]:
    """Load sentinel_exceptions.jsonl → {item_id: row}. Missing file = empty.

    Rows are operator allow-exceptions: {"item_id": ..., "allow": true, "reason": ...}.
    Later lines win for the same item_id.
    """
    path = _repo_root(root) / _EXCEPTIONS_REL
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            iid = row.get("item_id")
            if iid and row.get("allow"):
                out[str(iid)] = row
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel: failed to load exceptions: %s", exc)
    return out


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mark_all_unverified(plan: dict) -> None:
    """Stamp every queue item in plan with sentinel_ok=False in-place.

    Crash-path helper: called by the governor before writing a raw plan so an
    ungated plan is never written without a clear sentinel_ok=False signal.
    De-escalate-only invariant: only sets False (never upgrades to True).
    """
    for acc in (plan.get("accounts") or []):
        for item in (acc.get("queue") or []):
            if not item.get("sentinel_ok"):
                item["sentinel_ok"] = False


def error_report(*, as_of: str = "", exc: BaseException | str = "") -> dict:
    """The fail-closed report written when the gate itself crashed.

    plan_status "error" tells every consumer (admin, D02 actuator) that the
    plan is UNGATED and must not be published.
    """
    return {
        "schema_version": _SCHEMA_VERSION,
        "produced_by": "sentinel",
        "produced_at": _now_utc(),
        "as_of": as_of,
        "plan_status": "error",
        "publish_enabled": publish_enabled(),
        "auditor_strict": True,
        "counts": {
            "items": 0, "passed": 0, "quarantined": 0,
            "quarantined_policy": 0, "quarantined_overflow": 0,
            "warnings": 0, "exceptions_applied": 0,
        },
        "reasons_histogram": {},
        "quarantined": [],
        "checks": {},
        "notes": [f"sentinel gate raised: {exc}"],
    }


def _has_disclosure(text: str) -> bool:
    """True if text contains any required disclosure anchor.

    Multi-word anchors: substring match (no false-positive superstrings exist).
    Single-word tokens: word-boundary match (guards against "upgraded"→"grade",
    "historically"→"historical", etc.). Mirrors validate_copy §6 — keep the
    anchor set in sync.
    """
    lower = text.lower()
    if any(phrase in lower for phrase in _DISCLOSURE_PHRASES_MULTI):
        return True
    return any(p.search(lower) for p in _DISCLOSURE_PATTERNS_SINGLE)


def receipts_context(root: Path | str | None = None,
                     cfg: dict | None = None) -> tuple[int | None, list[dict] | None]:
    """Derive (receipts_age_days, graded_window) from the Prophet index.

    Single read of site/prophet/index.json.

    receipts_age_days = age in days of the NEWEST _signal_date across plans
    (None when unavailable — the gate then quarantines receipt items only,
    printed honestly in the report).

    graded_window = the full graded outcome set for the same window via
    receipt_source.graded_receipts, as [{"ticker", "outcome"}] (None when
    uncomputable — the gate skips cherry-pick, printed honestly).

    `cfg` IS THE WINDOW THE WORD "WINDOW" REFERS TO (2026-07-31 adversarial
    review). The cherry-pick arm asks "did the desk publish the wins and bury
    the losses INSIDE this window", so the window has to be the same one the
    Content Studio drew its receipts from — otherwise a config change to
    ``copywriter.receipt_max_age_days`` moves the supply and leaves the audit
    grading a different book, and the gate quietly stops being able to see a
    cherry-pick at all. Pass the marketing config the caller already loaded;
    ``None`` reads ``config/marketing.yml`` off *root* rather than falling
    through to the in-code default, because a silent fall-through is the defect.
    """
    r = _repo_root(root)

    if cfg is None:
        try:
            import yaml  # noqa: PLC0415
            with open(r / _CONFIG_REL, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("sentinel.receipts_context: could not load cfg (%s) — "
                        "receipts window falls back to the in-code default", exc)
            cfg = {}
    try:
        idx = json.loads((r / _PROPHET_INDEX_REL).read_text(encoding="utf-8"))
        plans = idx.get("plans") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("sentinel.receipts_context: prophet index unreadable: %s", exc)
        return None, None

    today = datetime.now(timezone.utc).date()
    ages: list[int] = []
    for p in plans:
        sd = str(p.get("_signal_date") or "")[:10]
        if not sd:
            continue
        try:
            days = (today - date.fromisoformat(sd)).days
        except ValueError:
            continue
        # Future-dated signals are corrupt data — skipping them fails closed
        # (a negative age would make the ledger read fresher than reality).
        if days >= 0:
            ages.append(days)
    age_days = min(ages) if ages else None

    graded_window: list[dict] | None = None
    try:
        from engine.marketing.chart_render import load_closes  # noqa: PLC0415
        from engine.marketing.receipt_source import (  # noqa: PLC0415
            graded_receipts, receipt_max_age_days,
        )
        graded = graded_receipts(
            plans,
            closes_loader=lambda t: load_closes(t, r, n=90),
            today=today.isoformat(),
            max_age_days=receipt_max_age_days(cfg),
        )
        graded_window = [{"ticker": g["ticker"], "outcome": g["kind"]} for g in graded]
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "sentinel.receipts_context: graded window uncomputable — cherry-pick will be skipped: %s",
            exc,
        )
    return age_days, graded_window


# ---------------------------------------------------------------------------
# Core gate logic
# ---------------------------------------------------------------------------

def gate_plan(
    plan: dict,
    cfg: dict,
    *,
    receipts_age_days: int | float | None = None,
    graded_window: list[dict] | None = None,
    exceptions: dict[str, dict] | None = None,
    root: str | None = None,
) -> tuple[dict, dict]:
    """The gate: returns (annotated_plan, report).

    No disk I/O and no LLM — deterministic from (plan, cfg, the injected receipts
    context). NOT side-effect-free, though: resolve_ramp may print ``::warning``
    annotations to stdout for ramp config defects (missing created:, missing
    as_of, an unparseable tier value), at most once per process each.

    Mutation only ever de-escalates:
    - items may be quarantined (status → "quarantined", sentinel_ok → False)
    - passing items get sentinel_ok → True annotated
    - item type/headline/body are NEVER modified
    - no new items are originated

    Check sequencing (quarantine-aware — dead items consume no slots):
    1. Content-level checks (lexicon, disclosure, link rule, cashtag breadth)
       — item-intrinsic, order-independent. ALL hits are recorded, not just
       the first (the operator sees the full reason list).
    2. Always-enforced classes (account_disabled, stale-receipts refusal).
    3. Exceptions pass — restores eligible check-violations. Never restores
       an item carrying an always-enforced reason.
    4. Near-dup + shared-media across accounts, over items still alive after
       steps 1–3 (a pair with a dead side is not coordinated posting).
       First-alive-in-plan-order survives. If a near-dup survivor is later
       cap-killed in step 5 the dropped dup stays dropped — deliberate
       conservatism: near-identical content queued the same day is drop-worthy
       regardless (docket: "rewrite-or-drop the later item").
    5. Caps (daily, reply, same-cashtag, slot collision, media) counting ONLY
       still-alive items, in queue order. Check-then-commit: an item that
       fails any cap consumes NO slots at all.
    6. Final exceptions pass for step-4/5 violations (an operator allow may
       exceed a cap — human override by design). Net effect: an item with an
       allow-exception stays quarantined ONLY if it carries an always-enforced
       reason.
    """
    plan = copy.deepcopy(plan)

    sc = _cfg_sentinel(cfg)
    settings = (cfg.get("settings") or {}) if isinstance(cfg, dict) else {}
    strict: bool = bool(_get(settings, "auditor_strict", True))
    exceptions = exceptions or {}

    as_of = plan.get("as_of", "")

    # Disabled account ids from desk_network. An account is "off" for the gate
    # when it is not effective-enabled — which covers the legacy per-account
    # kill-switch (disabled: true), the new liveness model (enabled: false on
    # desks with no real X account yet), AND an operator override that flips one
    # off (data/marketing/account_overrides.json). This is what makes the admin
    # "accounts switched off" cell show the planned desks as OFF rather than "all
    # live"; content_studio already skips generating their queues, so in the
    # normal path there are no items here to quarantine — this stays as a
    # defensive backstop.
    from engine.marketing.accounts import effective_accounts as _eff_accounts
    disabled_accounts: list[str] = [
        str(acc.get("id", ""))
        for acc in _eff_accounts(cfg if isinstance(cfg, dict) else {}, root)
        if not acc.get("enabled")
    ]

    # Flat item list: (account_id, item_dict, account_index, queue_index)
    all_items: list[tuple[str, dict, int, int]] = []
    for ai, acc in enumerate(plan.get("accounts") or []):
        acc_id = str(acc.get("id", ""))
        for qi, item in enumerate(acc.get("queue") or []):
            all_items.append((acc_id, item, ai, qi))

    # --- knobs ---------------------------------------------------------------
    # Age ramp: every ENABLED account resolves a tier from its `created:` date vs
    # THIS plan's as_of, and the caps that govern its items are the stricter of
    # (base block, tier row). A graduated account keeps the base caps untouched.
    # No ramp table in cfg ⇒ enforced False ⇒ base caps everywhere (no-op).
    ramp = resolve_ramp(cfg, as_of, root=root)
    base_caps = ramp["base"]

    def _caps_for(acc_id: str) -> dict[str, Any]:
        entry = ramp["accounts"].get(acc_id)
        return entry["caps"] if entry else ramp["fallback"]

    near_dup_thresh = float(_get(sc, "near_dup_jaccard", _DEFAULT_NEAR_DUP_JACCARD))
    max_receipt_age = _cap(sc, "max_receipt_age_days", _DEFAULT_MAX_RECEIPT_AGE_DAYS)
    lexicon_phrases = list(_get(sc, "lexicon_phrases", _DEFAULT_LEXICON_PHRASES))
    lexicon_patterns = list(_get(sc, "lexicon_patterns", _DEFAULT_LEXICON_PATTERNS))
    require_signal_disclosure = bool(
        _get(sc, "require_signal_disclosure", _DEFAULT_REQUIRE_SIGNAL_DISCLOSURE)
    )

    # Per-item violation accumulator {(ai, qi): list[str]}
    violations: dict[tuple[int, int], list[str]] = defaultdict(list)
    notes: list[str] = []

    if ramp["enforced"] and not ramp["as_of_usable"]:
        notes.append(
            f"ramp: plan as_of {as_of!r} is missing or unparseable — account age "
            f"is uncomputable, so EVERY account fell closed to the "
            f"{_TIER_WEEKS_1_2} tier (network-wide, not a cold-account read)"
        )
    for _no_date in ramp["missing_created"]:
        notes.append(
            f"ramp: enabled account {_no_date} has no created: date — "
            f"fail-closed to the {_TIER_WEEKS_1_2} tier"
        )

    # =========================================================================
    # STEP 1: Content-level checks (item-intrinsic, order-independent)
    # =========================================================================

    # --- financial-advice lexicon: record EVERY hit --------------------------
    phrase_res = [
        (phrase, re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE))
        for phrase in lexicon_phrases
    ]
    pattern_res = [re.compile(p, re.IGNORECASE) for p in lexicon_patterns]
    lexicon_hits = 0

    for _acc_id, item, ai, qi in all_items:
        text = _item_text(item)
        hits = [f"advice_lexicon:{phrase}" for phrase, cre in phrase_res if cre.search(text)]
        for cre in pattern_res:
            m = cre.search(text)
            if m:
                hits.append(f"advice_lexicon:{m.group(0)}")
        if hits:
            violations[(ai, qi)].extend(hits)
            lexicon_hits += len(hits)

    # --- disclosure law (signal items) ---------------------------------------
    # Gated on sentinel.require_signal_disclosure (default True). Operator ruling
    # 2026-07-26 sets it False in config: signal posts are NO LONGER quarantined
    # for a missing not-advice / historical caveat. The advice-lexicon guard above
    # (STEP 1) still bans reckless phrasing regardless of this knob.
    disclosure_hits = 0
    if require_signal_disclosure:
        for _acc_id, item, ai, qi in all_items:
            if item.get("type") != "signal":
                continue
            if not _has_disclosure(_item_text(item)):
                violations[(ai, qi)].append("missing_disclosure")
                disclosure_hits += 1

    # --- link rule (per-account: base AND the account's tier) -----------------
    link_re = re.compile(r"https?://|\bt\.co/", re.IGNORECASE)
    link_hits = 0
    for acc_id, item, ai, qi in all_items:
        if _caps_for(acc_id)["links_allowed"]:
            continue
        if link_re.search(_item_text(item)):
            violations[(ai, qi)].append("link_not_allowed")
            link_hits += 1

    # --- cashtag breadth (per post) ------------------------------------------
    # Distinct $TICKER tokens in headline+body (case-sensitive: real cashtags are
    # uppercase; "$oil" is prose, "$200" is a price — neither matches).
    # theme_list is exempt from the COUNT: validate_copy requires ≥4 member
    # cashtags there by format, so counting them would quarantine the format
    # itself. The tension memo §2 R3 names (multi-cashtag lists ARE the
    # piggybacking heuristic) is resolved one block down: on a cold account the
    # theme_list format is quarantined outright rather than exempted.
    # The cap itself is per-account — a ramping desk uses its tier's value.
    cashtag_re = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")
    cashtag_breadth_hits = 0
    for acc_id, item, ai, qi in all_items:
        if item.get("type") == "theme_list":
            continue
        distinct = set(cashtag_re.findall(_item_text(item)))
        if len(distinct) > _caps_for(acc_id)["max_cashtags_per_post"]:
            violations[(ai, qi)].append("cashtag_breadth")
            cashtag_breadth_hits += 1

    # --- ramp: theme_list quarantine on a cold account ------------------------
    # A ≥4-cashtag list post is the documented cashtag-piggybacking fingerprint
    # (D08 R3), and a young account has no posting history to be read against —
    # so while `theme_list_allowed` is false for the account's tier, the format
    # does not ship at all. week_5_plus and graduated accounts keep the ordinary
    # exemption above. Reads the tier key rather than the tier NAME so the
    # operator can move the line in config without a code change.
    ramp_theme_list_hits = 0
    for acc_id, item, ai, qi in all_items:
        if item.get("type") != "theme_list":
            continue
        if not _caps_for(acc_id)["theme_list_allowed"]:
            violations[(ai, qi)].append("ramp_theme_list")
            ramp_theme_list_hits += 1

    # =========================================================================
    # STEP 2: Always-enforced classes (never exception-overridable)
    # =========================================================================

    for acc_id, _item, ai, qi in all_items:
        if acc_id in disabled_accounts:
            violations[(ai, qi)].append("account_disabled")

    plan_refused = False
    receipts_age_check: dict[str, Any] = {
        "age_days": None if receipts_age_days is None else int(receipts_age_days),
        "max": max_receipt_age,
    }
    if receipts_age_days is None:
        # Unknown age → we cannot back receipts; quarantine receipt items only.
        for _acc_id, item, ai, qi in all_items:
            if item.get("type") in _RECEIPT_TYPES:
                violations[(ai, qi)].append("receipts_age_unknown")
        notes.append("receipts ledger age unknown — receipt items quarantined")
    elif receipts_age_days > max_receipt_age:
        plan_refused = True
        for _acc_id, _item, ai, qi in all_items:
            violations[(ai, qi)].append("stale_receipts_ledger")
        notes.append(
            f"plan refused: graded-receipts ledger stale "
            f"({int(receipts_age_days)}d > {max_receipt_age}d)"
        )

    # =========================================================================
    # STEP 3 / STEP 6: exceptions passes
    # =========================================================================

    exception_restored_ids: set[str] = set()

    def _apply_exceptions() -> None:
        """Restore items with an operator allow-exception.

        Never restores an item carrying an always-enforced reason. Restored
        item ids are tracked in a set so the report counts each item once even
        if it is restored in both passes.
        """
        for _acc_id, item, ai, qi in all_items:
            key = (ai, qi)
            if not violations[key]:
                continue
            iid = str(item.get("id") or "")
            row = exceptions.get(iid)
            if row is None:
                continue
            if any(r in _ALWAYS_ENFORCED for r in violations[key]):
                continue
            violations[key] = []
            item["exception_applied"] = row.get("reason", "human override")
            exception_restored_ids.add(iid)

    _apply_exceptions()  # step 3: content-level restorations before structural checks

    # =========================================================================
    # STEP 4: Near-dup + shared-media across accounts (alive items only)
    # =========================================================================

    near_dup_pairs_checked = 0
    near_dup_hits = 0
    shared_media_hits = 0

    # Alive survivors so far: (account_id, item_id, token_set)
    surviving_cross: list[tuple[str, str, frozenset[str]]] = []
    chart_id_seen: dict[str, str] = {}  # chart_id → first alive account_id

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        if violations[key]:
            continue  # dead items are not coordinated posting

        chart_id = item.get("chart_id")
        if chart_id:
            first_acc = chart_id_seen.get(chart_id)
            if first_acc is not None and first_acc != acc_id:
                violations[key].append(f"shared_media:{chart_id}")
                shared_media_hits += 1
                continue
            chart_id_seen.setdefault(chart_id, acc_id)

        item_id = str(item.get("id") or f"{acc_id}/{qi}")
        tokens = _token_set(_item_text(item))
        dup_of: str | None = None
        for prev_acc, prev_id, prev_tokens in surviving_cross:
            if prev_acc == acc_id:
                continue  # same-account dups are copywriter's job
            near_dup_pairs_checked += 1
            if _jaccard_sets(tokens, prev_tokens) >= near_dup_thresh:
                dup_of = prev_id
                break
        if dup_of is not None:
            violations[key].append(f"near_dup:{dup_of}")
            near_dup_hits += 1
        else:
            surviving_cross.append((acc_id, item_id, tokens))

    # =========================================================================
    # STEP 5: Caps — check-then-commit over alive items, in queue order
    # =========================================================================

    # The *_per_day caps are PER (account, day) — the plan spans 7 days (slots
    # D1-AM..D7-EOD) plus non-day publish-time slots (MOVER-/THEME-/CONF-). Keying
    # these counters on account alone applied a 2-a-day cap across the whole 7-day
    # plan, falsely quarantining ~85 of 111 items nightly as cadence_cap_daily.
    # The day bucket is _slot_day_bucket(slot): the D<n> day for a D-slot, the
    # publish-time family (MOVER/THEME/CONF) as its own bucket, and "" for any
    # unrecognized/absent slot (those share one bucket per account).
    posts_by_account: dict[tuple[str, str], int] = defaultdict(int)
    cashtag_by_account: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    slot_by_account: dict[str, set[str]] = defaultdict(set)
    replies_by_account: dict[tuple[str, str], int] = defaultdict(int)
    media_by_account: dict[tuple[str, str], int] = defaultdict(int)

    cadence_stats: dict[str, int] = {
        "cadence_cap_daily_hits": 0,
        "cashtag_cap_hits": 0,
        "slot_collision_hits": 0,
        "reply_cap_hits": 0,
    }
    media_cap_hits = 0

    for acc_id, item, ai, qi in all_items:
        key = (ai, qi)
        if violations[key]:
            continue  # dead items consume no slots

        cashtag = str(item.get("cashtag") or "").strip()
        slot = str(item.get("slot") or "").strip()
        is_reply = is_reply_item(item)
        has_media = bool(item.get("chart_id"))
        dk = (acc_id, _slot_day_bucket(slot))  # per-(account, day) cap key

        # Caps are per-ACCOUNT once the ramp is enforced: two desks in one plan
        # can sit on different tiers (a week-1 desk next to a graduated one).
        _c = _caps_for(acc_id)
        max_media_posts_day = _c["max_media_posts_per_account_per_day"]
        max_replies_day = _c["max_replies_per_account_per_day"]
        max_posts_day = _c["max_posts_per_account_per_day"]
        max_same_cashtag = _c["max_same_cashtag_per_account_per_day"]

        # Decide every cap first; commit counters only if the item survives —
        # a killed item must never waste a slot a clean sibling needed.
        reason: str | None = None
        if has_media and max_media_posts_day is not None and media_by_account[dk] >= max_media_posts_day:
            reason = "media_cap_daily"
            media_cap_hits += 1
        elif is_reply and replies_by_account[dk] >= max_replies_day:
            reason = "reply_cap_daily"
            cadence_stats["reply_cap_hits"] += 1
        elif max_posts_day is not None and posts_by_account[dk] >= max_posts_day:
            reason = "cadence_cap_daily"
            cadence_stats["cadence_cap_daily_hits"] += 1
        elif cashtag and cashtag_by_account[dk][cashtag] >= max_same_cashtag:
            reason = f"cashtag_cap:{cashtag}"
            cadence_stats["cashtag_cap_hits"] += 1
        elif slot and slot in slot_by_account[acc_id]:
            reason = f"slot_collision:{slot}"
            cadence_stats["slot_collision_hits"] += 1

        if reason is not None:
            violations[key].append(reason)
            continue

        if has_media:
            media_by_account[dk] += 1
        if is_reply:
            replies_by_account[dk] += 1
        posts_by_account[dk] += 1
        if cashtag:
            cashtag_by_account[dk][cashtag] += 1
        if slot:
            slot_by_account[acc_id].add(slot)

    # =========================================================================
    # STEP 5b: Cherry-pick detector (alive receipt items vs graded window)
    # =========================================================================
    # PARTIAL detector (W1, documented in the docket status line): fires only
    # when the window has losses and the plan shows win receipts with ZERO of
    # the loss tickers. A plan showing some losers passes.

    cherry_pick: dict[str, Any] = {}
    if graded_window is None:
        cherry_pick["status"] = "skipped"
        notes.append("cherry-pick check skipped — graded window unavailable")
    else:
        cherry_pick["status"] = "run"
        loss_tickers = {
            str(gw.get("ticker") or "").upper()
            for gw in graded_window
            if gw.get("outcome") in {"loss", "mixed"} and gw.get("ticker")
        }
        cherry_pick["loss_tickers_in_window"] = sorted(loss_tickers)
        cherry_pick["cherry_pick_detected"] = False

        if loss_tickers:
            receipt_keys: list[tuple[int, int]] = []
            shown_tickers: set[str] = set()
            for _acc_id, item, ai, qi in all_items:
                if violations[(ai, qi)] or item.get("type") not in _RECEIPT_TYPES:
                    continue
                t = (str(item.get("ticker") or "") or
                     str(item.get("cashtag") or "").lstrip("$")).upper()
                if t:
                    shown_tickers.add(t)
                    receipt_keys.append((ai, qi))
            wins_shown = shown_tickers - loss_tickers
            if wins_shown and not (shown_tickers & loss_tickers):
                for key in receipt_keys:
                    violations[key].append("cherry_pick_suspected")
                cherry_pick["cherry_pick_detected"] = True
                cherry_pick["loss_tickers_missing"] = sorted(loss_tickers)

    _apply_exceptions()  # step 6: operator allow may exceed a cap / clear structural flags

    # =========================================================================
    # Annotate items + build report
    # =========================================================================

    reasons_histogram: dict[str, int] = defaultdict(int)
    quarantined_entries: list[dict] = []
    passed_entries: list[dict] = []
    passed_count = 0
    quarantined_count = 0
    quarantined_policy = 0
    quarantined_overflow = 0
    warnings_items_count = 0  # number of ITEMS carrying warnings (not violation strings)

    def _passed(item: dict, acc_id: str, warnings: list[str] | None = None) -> None:
        # Same field set the operator sees for quarantined rows, so the admin can
        # render a "12 cleared" list next to the quarantine list (report emitted
        # only a passed COUNT before — nothing to enumerate).
        entry = {
            "id": item.get("id", ""),
            "account": acc_id,
            "slot": item.get("slot", ""),
            "type": item.get("type", ""),
            "cashtag": item.get("cashtag", ""),
            "headline": (item.get("headline") or "")[:120],
        }
        if warnings:
            entry["warnings"] = warnings
        passed_entries.append(entry)

    def _quarantine(item: dict, acc_id: str, reasons: list[str]) -> None:
        nonlocal quarantined_count, quarantined_policy, quarantined_overflow
        cls = ("policy" if any(reason_class(r) == "policy" for r in reasons)
               else "overflow")
        item["sentinel_ok"] = False
        item["status"] = "quarantined"
        item["sentinel_reasons"] = reasons
        quarantined_count += 1
        if cls == "policy":
            quarantined_policy += 1
        else:
            quarantined_overflow += 1
        for r in reasons:
            reasons_histogram[r.split(":", 1)[0]] += 1
        quarantined_entries.append({
            "id": item.get("id", ""),
            "account": acc_id,
            "slot": item.get("slot", ""),
            "type": item.get("type", ""),
            "cashtag": item.get("cashtag", ""),
            "headline": (item.get("headline") or "")[:120],
            "class": cls,
            "reasons": reasons,
        })

    for acc_id, item, ai, qi in all_items:
        item_violations = violations[(ai, qi)]

        if not item_violations:
            item["sentinel_ok"] = True
            passed_count += 1
            _passed(item, acc_id)
            continue

        if strict or plan_refused:
            _quarantine(item, acc_id, item_violations)
            continue

        # Non-strict: always-enforced reasons still quarantine; the rest are warnings.
        hard = [v for v in item_violations if v in _ALWAYS_ENFORCED]
        soft = [v for v in item_violations if v not in _ALWAYS_ENFORCED]
        if hard:
            if soft:
                item["sentinel_warnings"] = soft
            _quarantine(item, acc_id, hard)
        else:
            item["sentinel_ok"] = True
            item["sentinel_warnings"] = soft
            passed_count += 1
            warnings_items_count += 1
            _passed(item, acc_id, warnings=soft)
            for r in soft:
                reasons_histogram[r.split(":", 1)[0] + "_warning"] += 1

    if plan_refused:
        plan_status = "refused"
    elif not strict and (warnings_items_count > 0 or quarantined_count > 0):
        plan_status = "pass_with_warnings"
    else:
        plan_status = "pass"

    report: dict = {
        "schema_version": _SCHEMA_VERSION,
        "produced_by": "sentinel",
        "produced_at": _now_utc(),
        "as_of": as_of,
        "plan_status": plan_status,
        "publish_enabled": publish_enabled(),
        "auditor_strict": strict,
        "counts": {
            "items": len(all_items),
            "passed": passed_count,
            "quarantined": quarantined_count,
            "quarantined_policy": quarantined_policy,
            "quarantined_overflow": quarantined_overflow,
            "warnings": warnings_items_count,
            "exceptions_applied": len(exception_restored_ids),
        },
        "reasons_histogram": dict(reasons_histogram),
        "quarantined": quarantined_entries,
        "passed": passed_entries,
        "checks": {
            "near_dup": {
                "pairs_checked": near_dup_pairs_checked,
                "hits": near_dup_hits,
                "shared_media_hits": shared_media_hits,
            },
            "cadence": cadence_stats,
            "lexicon": {"hits": lexicon_hits},
            "disclosure": {"hits": disclosure_hits, "required": require_signal_disclosure},
            "cherry_pick": cherry_pick,
            "stale_receipts": receipts_age_check,
            "kill_switch": {
                "env": publish_enabled(),
                "accounts_disabled": disabled_accounts,
            },
            # The *_cap / *_rule blocks report the BASE contract; the per-account
            # values that actually governed are under "ramp" below.
            "media_cap": {
                "max_media_posts_per_account_per_day":
                    base_caps["max_media_posts_per_account_per_day"],
                "hits": media_cap_hits,
            },
            "cashtag_breadth": {
                "max_cashtags_per_post": base_caps["max_cashtags_per_post"],
                "hits": cashtag_breadth_hits,
            },
            "link_rule": {
                "links_allowed": base_caps["links_allowed"],
                "hits": link_hits,
            },
            "ramp": {
                "enforced": ramp["enforced"],
                # The RESOLVED value — clamped to >= the resolved weeks_3_4
                # boundary, which is what actually governed, not necessarily the
                # number written in config.
                "graduate_after_days": ramp["graduate_after_days"],
                # The resolved ladder geometry. Same reason: a config that named
                # an incoherent pair fell back to 14/28, and the report has to
                # say which schedule actually ran.
                "weeks_1_2_days": ramp["weeks_1_2_days"],
                "weeks_3_4_days": ramp["weeks_3_4_days"],
                "as_of": ramp["as_of"],
                # False ⇒ account age was uncomputable and EVERY account fell
                # closed to weeks_1_2. Without this the report is indistinguishable
                # from a genuinely all-cold network.
                "as_of_usable": ramp["as_of_usable"],
                "base": base_caps,
                "accounts": ramp["accounts"],
                "missing_created": ramp["missing_created"],
                "theme_list_hits": ramp_theme_list_hits,
            },
        },
        "notes": notes,
    }

    return plan, report


# ---------------------------------------------------------------------------
# run_gate: disk I/O wrapper
# ---------------------------------------------------------------------------

def run_gate(
    root: Path | str | None = None,
    *,
    plan: dict | None = None,
    cfg: dict | None = None,
    receipts_age_days: int | float | None = None,
    graded_window: list[dict] | None = None,
) -> dict:
    """Load plan+cfg+exceptions from disk if not given, gate, atomically write
    the annotated plan back to data/marketing/content_plan.json and the report
    to data/marketing/sentinel_report.json.

    Returns the report. Callable from the governor AND from the D01 fastlane.

    FAIL CLOSED: if the plan is unreadable or gate_plan raises, an error report
    is written and the exception re-raised. content_plan.json is never
    overwritten with a fabricated plan.
    """
    r = _repo_root(root)

    if cfg is None:
        try:
            import yaml  # noqa: PLC0415
            with open(r / _CONFIG_REL, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            # Missing config degrades to the (conservative) in-code defaults.
            log.warning("sentinel.run_gate: could not load cfg: %s", exc)
            cfg = {}

    if plan is None:
        try:
            plan = json.loads((r / _CONTENT_PLAN_REL).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("sentinel.run_gate: content plan unreadable: %s", exc)
            write_report(r, error_report(exc=f"content plan unreadable: {exc}"))
            raise

    try:
        annotated_plan, report = gate_plan(
            plan,
            cfg,
            receipts_age_days=receipts_age_days,
            graded_window=graded_window,
            exceptions=load_exceptions(r),
            root=str(r),
        )
    except Exception as exc:  # noqa: BLE001
        write_report(r, error_report(as_of=plan.get("as_of", ""), exc=exc))
        raise

    _write_json_atomic(r / _CONTENT_PLAN_REL, annotated_plan)
    write_report(r, report)
    return report
