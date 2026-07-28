"""engine/marketing/franchises.py — the franchise register + slot scheduler (XG-W3).

A FRANCHISE is a recurring format a reader can expect from one account: Cici's
"Before New York Wakes", Kelly's "Confirmation Check", the flagship's "What
Changed Since Yesterday". The editorial constitution §12 names them; the four
employee specs (`config/personas/<id>.yml` `franchises:`) carry them as PROSE.
This module is the STRUCTURED register those prose lines describe — the thing an
engine can actually schedule against.

WHY A CODE REGISTER AND NOT THE YAML.  The spec's `franchises:` entries are
human sentences ("Tea and Tickers — lighter roundup, ≤1/week and parked while
the canon is dark"). They carry no kind, no window, no cap a scheduler can read.
Rather than re-shape a frozen XG-W1 schema, the register lives here as a
declarative table and `spec_drift()` cross-checks it against the committed specs,
so the two can never silently diverge. Adding a franchise is an edit to _REGISTER
plus (for an employee) a matching prose line in the spec.

NO NEW KINDS (charter §4 / XG-W3 brief).  Every franchise maps onto a kind that
`content_studio.CONTENT_TYPES` and `outbox.KINDS` already admit. The franchise id
travels in item metadata (`item["source"]["franchise"]`), never as a kind. This is
deliberate: a new kind would need a tilt weight on every persona spec, a dial
level, a template pool and a sentinel cap — a franchise needs none of that,
because it IS one of those kinds with a house format.

SLOTS ARE WINDOWS, NOT QUOTAS (constitution Law 1 — value before activity).
`open_slots()` answers "which franchise windows are open for this account right
now". It never manufactures an obligation to post. An open slot with nothing
worth saying ABSTAINS, and `abstain()` records why (§16.5's reason taxonomy) so
the bottleneck is visible: if every Mood-vs-Money slot dies on
`no_measured_input`, the fix is a sentiment source (XG-W5), not a looser bar.

CALENDAR SCOPE — A WEEKDAY CLOCK, NOT A TRADING CALENDAR (review F4).
`sessions_only=True` keeps a session-clocked franchise (Cici's pre-open read,
Kelly's "Confirmation Check") from opening on a Saturday, because a franchise
whose whole premise is "what the session did" has nothing to say when there was
no session. It is a WEEKDAY test and nothing more: it does not know about
exchange holidays, half-days, Golden Week, Thanksgiving, or an unscheduled
close. A HOLIDAY CALENDAR IS EXPLICITLY OUT OF SCOPE for XG-W3 — wiring one
means picking a per-exchange source and a staleness policy, which is its own
build. Until then a holiday Monday opens a slot the desk should decline, and
declining it is an editorial abstention (`facts_too_stale` / `no_unique_edge`),
not a scheduler guarantee.

DISPLAY NAMES ARE METADATA, NOT COPY.  Sophia's "Narrative Shift" contains
"narrative", which is on the copywriter's `_BANNED_WORD_BOUNDARY` list — a post
that used the franchise's own name verbatim would be rejected by the house
vocab guard. `copy_safe_name` records this per franchise and the prompt contract
never instructs verbatim use of an unsafe name. The register is greppable
internal structure; the reader sees the FORMAT, not the label.

Public API:
    register(*, root=None)                      -> tuple[Franchise, ...]
    for_account(account, *, root=None)          -> tuple[Franchise, ...]
    by_id(franchise_id, *, root=None)           -> Franchise | None
    open_slots(account, *, now, ...)            -> list[FranchiseSlot]
    history_from_items(items, *, account)       -> [(when, franchise_id), ...]
    item_franchise_id(item)                     -> str
    abstain(slot, reason, *, now, detail=None)  -> Abstention
    measured_input_violations(headline, body, *, franchise, sources=()) -> list[str]
    spec_drift(*, root=None)                    -> list[str]
    ABSTAIN_REASONS                             -> frozenset[str]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "Franchise",
    "FranchiseSlot",
    "Abstention",
    "ABSTAIN_REASONS",
    "CADENCES",
    "register",
    "for_account",
    "by_id",
    "open_slots",
    "history_from_items",
    "item_franchise_id",
    "abstain",
    "measured_input_violations",
    "spec_drift",
]

# ─────────────────────────────────────────────────────────────────────────────
# Abstention reasons — constitution §16.5 ("Learn from abstentions"), verbatim
# taxonomy plus the four mechanical ones this scheduler can produce itself.
#
# The §16.5 point is diagnostic: "If almost everything is rejected for the same
# reason, the bottleneck may be discovery, data, profile readiness, or persona
# design — not the quality threshold." That only works if the reason is a closed
# vocabulary, so an unknown reason is a hard ValueError, never a free-text log.
# ─────────────────────────────────────────────────────────────────────────────
_EDITORIAL_REASONS: frozenset[str] = frozenset(
    {
        "no_unique_edge",
        "saturated_conversation",
        "weak_persona_fit",
        "facts_too_stale",
        "topic_overused",
        "cross_account_collision",
        "sensitive_context",
        "low_conversion_coherence",
    }
)
#: Mechanical reasons the scheduler itself produces (window/cap/arming), as
#: opposed to the editorial judgments above that a caller supplies.
_MECHANICAL_REASONS: frozenset[str] = frozenset(
    {
        "outside_window",
        "franchise_disabled",
        "franchise_cap_reached",
        "no_measured_input",
        # Review F2 — the account owns no wire_routing class. Silence is the
        # correct output; the alternative (skip the filter) is the firehose.
        "no_wire_routing",
        # Review F3 — the one-owner lock could not be consulted. A lock you
        # cannot read is a lock that failed, so the candidate is withheld.
        "cross_account_collision_check_failed",
        # Review F5 — the account does not run a market-hours lane.
        "no_market_hours_lane",
        # Review F4 — the franchise's clock does not cover this weekday.
        "outside_calendar",
    }
)
ABSTAIN_REASONS: frozenset[str] = _EDITORIAL_REASONS | _MECHANICAL_REASONS

#: Recognised cadence shapes. `daily` = at most one emission per local day inside
#: the window; `weekly` = at most `max_per_week` per rolling 7 days; `sessional`
#: = the window may open more than once a day (a market-hours franchise) and the
#: per-day ceiling comes from `max_per_day`.
CADENCES: frozenset[str] = frozenset({"daily", "weekly", "sessional"})

#: Franchise classification -> expression-dial intent (charter §2 amendment 3:
#: wire/news = 0, analysis = 1, charts/watchlist = 2). The register declares the
#: CLASS; `expression_dial.dial_for(kind, profile=...)` remains the authority on
#: the actual ceiling — this is the editorial intent, recorded so a reviewer can
#: see that e.g. "Before New York Wakes" is ANALYSIS and not a wire post
#: (charter §2 amendment 2 sub-ruling).
_CLASSES: frozenset[str] = frozenset({"news", "analysis", "chart"})


@dataclass(frozen=True)
class Franchise:
    """One recurring format owned by one account."""

    id: str
    account: str
    display_name: str
    #: An EXISTING content kind (content_studio.CONTENT_TYPES / outbox.KINDS).
    kind: str
    #: Editorial class for the dial — see _CLASSES.
    classification: str
    cadence: str
    #: The prompt/template contract: what this format must contain to BE this
    #: franchise. Consumed by the copywriter voice pass (item 5) and by the
    #: Gift-Grip-Proof gate as the franchise's own definition of its gift.
    contract: tuple[str, ...]
    #: Local window(s) "HH:MM-HH:MM" in `tz`. Empty = no clock constraint (the
    #: franchise is eligible whenever the account's own cadence allows).
    tz: str = ""
    windows: tuple[str, ...] = ()
    max_per_day: int = 1
    max_per_week: int = 0  # 0 = unbounded by the weekly rule
    #: Weekday numbers (Mon=0 … Sun=6) on which this franchise's window opens.
    #: Empty = every day. A SESSION-CLOCKED franchise ("Before New York Wakes",
    #: "Confirmation Check") must set `sessions_only=True` rather than listing
    #: days by hand.
    days: tuple[int, ...] = ()
    #: True = weekdays only (Mon-Fri). See the CALENDAR SCOPE note in the module
    #: docstring: this is a WEEKDAY CLOCK, NOT A TRADING CALENDAR.
    sessions_only: bool = False
    enabled: bool = True
    #: False when the display name trips the house banned-vocab guard, so the
    #: prompt contract must not ask for it verbatim. Computed at import.
    copy_safe_name: bool = True
    #: Why a franchise ships dark, when it does.
    note: str = ""
    #: Charter §2 amendment 10 — a crowd-state claim requires a measured input.
    #: True means the franchise MUST carry an attributed source (headline/post)
    #: for its crowd/mood side; `engine.marketing.desk_feed` and the Meagan
    #: validator enforce it.
    requires_measured_input: bool = False

    @property
    def is_windowed(self) -> bool:
        return bool(self.windows)


@dataclass(frozen=True)
class FranchiseSlot:
    """An OPEN window — an invitation to consider posting, never an obligation."""

    franchise: Franchise
    account: str
    #: The local day the slot belongs to (YYYY-MM-DD in the franchise tz).
    day: str
    opens_at: datetime
    closes_at: datetime
    now: datetime

    @property
    def franchise_id(self) -> str:
        return self.franchise.id

    @property
    def kind(self) -> str:
        return self.franchise.kind


@dataclass(frozen=True)
class Abstention:
    """A logged silence. Constitution Law 8: silence is an editorial action."""

    account: str
    franchise_id: str
    reason: str
    at: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "franchise": self.franchise_id,
            "reason": self.reason,
            "at": self.at,
            "detail": dict(self.detail),
        }


# ─────────────────────────────────────────────────────────────────────────────
# THE REGISTER
#
# Sources: editorial constitution §5.3-§5.7 "Recurring franchises" + §12
# "High-Leverage Creative Concepts", reconciled with the committed XG-W1 specs.
# Charter §4 names the anchor examples (Cici pre-open daily; Meagan "Mood vs
# Money"; Kelly "Confirmation Check"; Sophia "The Story the Market Believes";
# flagship "What Changed Since Yesterday").
#
# Cici's windows come from her spec's `cadence.session` (Asia/Hong_Kong,
# 08:00-17:00 + 20:00-23:00) so the franchise clock and the resolver clock
# cannot disagree. The US desks declare no session in their specs, so their
# franchises carry US/Eastern windows HERE ONLY — a franchise window narrows a
# format's slot, it never widens the account's cadence, which the resolver still
# bounds independently.
# ─────────────────────────────────────────────────────────────────────────────
_ET = "America/New_York"
_HK = "Asia/Hong_Kong"

_RAW_REGISTER: tuple[dict[str, Any], ...] = (
    # ── Cici — cross-border correspondent ────────────────────────────────────
    {
        "id": "cici_before_new_york_wakes",
        "account": "cici",
        "display_name": "Before New York Wakes",
        # Charter §2 amendment 2 sub-ruling: classified ANALYSIS (dial 1), NOT a
        # wire/news post. It lands on macro (her spec's second-heaviest tilt).
        "kind": "macro",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _HK,
        # Her HK cash-session window — the pre-open read through the close.
        "windows": ("08:00-17:00",),
        "contract": (
            "what moved in Asia while New York slept",
            "what local markets believed it meant",
            "what did NOT confirm",
            "the one US exposure New York should watch at the open",
        ),
    },
    {
        "id": "cici_asia_close_readthrough",
        "account": "cici",
        "display_name": "Asia Close, Global Read-Through",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _HK,
        # The evening leg that lands while New York is still trading.
        "windows": ("20:00-23:00",),
        "contract": (
            "where the Asia session closed",
            "the transmission path into the US tape",
            "one asset that should care next",
        ),
    },
    {
        "id": "cici_lost_in_translation",
        "account": "cici",
        "display_name": "Lost in Translation",
        "kind": "education",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _HK,
        "windows": ("08:00-23:00",),
        "max_per_week": 2,
        "contract": (
            "the local-language phrasing, glossed on the spot",
            "what the Western rendering loses",
            "why the difference changes the market read",
        ),
    },
    {
        "id": "cici_three_things_missed",
        "account": "cici",
        "display_name": "Three Things the Western Headline Missed",
        "kind": "theme_list",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _HK,
        "windows": ("08:00-23:00",),
        "max_per_week": 2,
        "contract": (
            "the headline as filed in the West",
            "three specifics it omitted, each with its own evidence",
            "the conclusion the omissions change",
        ),
    },
    {
        "id": "cici_tea_and_tickers",
        "account": "cici",
        "display_name": "Tea and Tickers",
        "kind": "theme_list",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _HK,
        "windows": ("08:00-23:00",),
        "max_per_week": 1,
        # Charter §2 amendment 2 caps it ≤1/week, and amendment 8 keeps the
        # canon DARK until the real Cici confirms her texture list. The spec's
        # `lifestyle_tea_travel` marker is enabled:false, so this franchise is
        # PARKED — arming it is the same one-word change as the marker.
        "enabled": False,
        "note": (
            "parked while voice_codex.quirk_markers.lifestyle_tea_travel is dark "
            "(charter §2 amendment 8 — employee canon confirmation); spends the "
            "same ≤1/week tea lexicon budget"
        ),
    },
    # ── Meagan — crowd translator ────────────────────────────────────────────
    {
        "id": "meagan_mood_vs_money",
        "account": "meagan",
        "display_name": "Mood vs Money",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("09:00-16:30",),
        # Charter §2 amendment 10: the crowd side is the whole point of this
        # franchise, and we have no sanctioned sentiment source until XG-W5.
        "requires_measured_input": True,
        "contract": (
            "the mood side, quoted from an ATTRIBUTED headline or post",
            "the money side from our own tape: positioning, breadth, flows or price",
            "the mismatch, stated plainly",
            "one market fact that makes the social reaction more useful",
        ),
        "note": (
            "interim tape-only form until XG-W5 lands a sanctioned sentiment "
            "source (charter §2 amendment 10)"
        ),
    },
    {
        "id": "meagan_market_group_chat",
        "account": "meagan",
        "display_name": "Market Group Chat",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("09:00-16:30",),
        "max_per_week": 3,
        "requires_measured_input": True,
        "contract": (
            "what everyone is saying, quoted and attributed",
            "what actually matters, from the tape",
            "the one useful sentence that survives the joke",
        ),
        "note": "same measured-input rule as Mood vs Money (charter §2 amendment 10)",
    },
    {
        "id": "meagan_open_tabs",
        "account": "meagan",
        "display_name": "Open Tabs",
        "kind": "theme_list",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("09:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "three connected developments",
            "the thread that connects them",
            "one conclusion",
        ),
    },
    {
        "id": "meagan_the_awkward_part",
        "account": "meagan",
        "display_name": "The Awkward Part",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("09:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "the popular narrative, named without adopting it",
            "the fact it is avoiding, with evidence",
            "what would make the avoidance defensible",
        ),
    },
    # ── Sophia — narrative architect ─────────────────────────────────────────
    {
        "id": "sophia_story_market_believes",
        "account": "sophia",
        "display_name": "The Story the Market Believes",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "contract": (
            "the organising story, stated in one sentence",
            "who is acting as if it were true",
            "the evidence that still supports it",
            "the condition that would end it",
        ),
    },
    {
        "id": "sophia_narrative_shift",
        "account": "sophia",
        # NOTE: this display name trips the house banned-vocab guard
        # (copywriter._BANNED_WORD_BOUNDARY contains "narrative"). copy_safe_name
        # is computed False at import and the contract below deliberately
        # describes the FORMAT without asking for the label.
        "display_name": "Narrative Shift",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 3,
        "contract": (
            "the story that was holding, and what it explained",
            "the moment it stopped holding",
            "which market registered the change first",
        ),
    },
    {
        "id": "sophia_one_chart_two_stories",
        "account": "sophia",
        "display_name": "One Chart, Two Stories",
        "kind": "chart",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "one chart",
            "two plausible readings, both stated fairly",
            "the variable that decides between them",
        ),
    },
    {
        "id": "sophia_who_needs_this_true",
        "account": "sophia",
        "display_name": "Who Needs This Story to Be True?",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 1,
        "contract": (
            "the claim and who is repeating it",
            "whose position depends on it",
            "what that incentive does and does not prove",
        ),
    },
    # ── Kelly — mechanism detective ──────────────────────────────────────────
    {
        "id": "kelly_confirmation_check",
        "account": "kelly",
        "display_name": "Confirmation Check",
        "kind": "signal",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("09:30-16:00",),
        "contract": (
            "the move everyone is reacting to",
            "the market that would have to confirm it",
            "whether it is confirming, with the number",
        ),
    },
    {
        "id": "kelly_chart_detective",
        "account": "kelly",
        "display_name": "Chart Detective",
        "kind": "chart",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("09:30-16:00",),
        "max_per_week": 3,
        "contract": (
            "the chart and the anomaly in it",
            "the mechanism that would produce it",
            "the second chart that tests the mechanism",
        ),
    },
    {
        "id": "kelly_what_is_already_priced",
        "account": "kelly",
        "display_name": "What Is Already Priced",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "the expectation as the market has it",
            "where that expectation is visible as a number",
            "what an outcome has to beat to matter",
        ),
    },
    {
        "id": "kelly_what_would_prove_this_wrong",
        "account": "kelly",
        "display_name": "What Would Prove This Wrong?",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        # Charter §2 amendment 4: X-legal. The #3821 ruling bans
        # falsifier/refutation language on SITE CYCLE SURFACES; it does not
        # reach X, where this is Kelly's intellectual method.
        "contract": (
            "the claim, stated so it can fail",
            "the best evidence for it",
            "what would prove it wrong",
            "the first market likely to signal the change",
        ),
        "note": "X-legal per charter §2 amendment 4; site cycle surfaces stay under #3821",
    },
    {
        "id": "kelly_risk_radar_note",
        "account": "kelly",
        "display_name": "Risk Radar Note",
        "kind": "watchlist",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "the risk, named specifically",
            "the level or condition that would activate it",
            "what we are watching to know",
        ),
    },
    # ── Flagship — the evidence desk (constitution §5.7) ─────────────────────
    {
        "id": "flagship_what_changed_since_yesterday",
        "account": "flagship",
        "display_name": "What Changed Since Yesterday",
        "kind": "signal",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("07:00-09:30",),
        "contract": (
            "the state that changed, with its timestamp",
            "what did not change",
            "what the change does to the read",
        ),
    },
    {
        "id": "flagship_signal_of_the_day",
        "account": "flagship",
        "display_name": "Signal of the Day",
        "kind": "signal",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("09:30-16:00",),
        # Charter §2 amendment 11: display-tier language posture. Plain-word
        # stance, "what we're watching" framing, no calibrated-authority claim
        # until a signal passes the gauntlet at promotion.
        "contract": (
            "the signal state in plain words",
            "its timestamp and evidence object",
            "what we are watching next — a window, not a certainty",
        ),
        "note": "display-tier language posture (charter §2 amendment 11)",
    },
    {
        "id": "flagship_market_map",
        "account": "flagship",
        "display_name": "Market Map",
        "kind": "theme_list",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "the event or state at the centre",
            "the affected assets, ordered by directness",
            "the second-order consequence worth naming",
        ),
    },
    {
        "id": "flagship_sector_rotation",
        "account": "flagship",
        "display_name": "Sector Rotation",
        "kind": "theme_list",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("09:30-16:00",),
        "max_per_week": 2,
        "contract": (
            "what led and what lagged, with the numbers",
            "whether breadth confirms the rotation",
            "the read that changes if it does not",
        ),
    },
    {
        "id": "flagship_research_in_one_chart",
        "account": "flagship",
        "display_name": "Institutional Research in One Chart",
        "kind": "chart",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 2,
        "contract": (
            "one clean chart",
            "one interpretation",
            "one condition",
        ),
    },
    {
        "id": "flagship_risk_radar",
        "account": "flagship",
        "display_name": "Risk Radar",
        "kind": "watchlist",
        "classification": "chart",
        "cadence": "weekly",
        "tz": _ET,
        "windows": ("08:00-16:30",),
        "max_per_week": 1,
        "contract": (
            "the risks on the board, ranked",
            "the level or date that activates each",
            "what would take one off the board",
        ),
    },
    # ── Founder — his own read (constitution has no franchise list for him;
    # charter §1 gives the identity: first-person, dry, never pitches). One
    # franchise only, deliberately: a founder account running a format schedule
    # reads as a publication, which is exactly what it must not be.
    {
        "id": "founder_the_days_tape",
        "account": "founder",
        "display_name": "The Day's Tape",
        "kind": "macro",
        "classification": "analysis",
        "cadence": "daily",
        "sessions_only": True,   # session-premise: "what the session did"
        "tz": _ET,
        "windows": ("09:30-16:30",),
        "contract": (
            "what he actually watched today",
            "the one thing that changed his read, or that nothing did",
            "no pitch, no CTA",
        ),
        "note": (
            "founder identity is first-person and dry (charter §1); AM-R1 binds "
            "hardest here — the engine never invents a trade, meeting or "
            "first-person experience"
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Window parsing. Deliberately a local copy of the "HH:MM-HH:MM" shape rather
# than an import of cadence_resolver.parse_windows: that function returns
# SessionWindow objects tied to the RESOLVER's semantics (a whole-account
# territory clock with an outside-window allowance). A franchise window is a
# narrower thing — a format's slot inside a day — and conflating them would make
# a franchise edit silently change an account's cadence bound. The two clocks
# stay separate on purpose; `spec_drift()` checks they do not contradict.
# ─────────────────────────────────────────────────────────────────────────────
_WINDOW_RE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _parse_window(raw: str) -> tuple[int, int] | None:
    """"HH:MM-HH:MM" -> (start_minute, end_minute) from local midnight."""
    m = _WINDOW_RE.match(str(raw).strip())
    if not m:
        return None
    sh, sm, eh, em = (int(g) for g in m.groups())
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 24 and 0 <= em <= 59):
        return None
    return sh * 60 + sm, eh * 60 + em


def _zone(tz: str):
    """Resolve a tz name, fail-soft to UTC.

    A bad tz must not crash the scheduler for six healthy accounts; it degrades
    that franchise to UTC and `spec_drift()` reports it.
    """
    if not tz:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz)
    except Exception:
        return None


def _name_is_copy_safe(name: str) -> bool:
    """Does this display name survive the house banned-vocab guard?

    Lazy import: `copywriter` pulls a large template table and this module is
    imported by the scheduler on every slot query. The guard is the SAME one
    every drafter uses (charter §2 amendment 12 — one vocab guard, every
    drafter); we never re-implement the word list here.
    """
    try:
        from engine.marketing.copywriter import banned_language

        return not banned_language(str(name))
    except Exception:
        # Fail SAFE, not open: if the guard cannot be consulted we assume the
        # name is unsafe, so the prompt contract withholds it rather than
        # smuggling a banned token into copy.
        return False


_CACHE: dict[str, tuple[Franchise, ...]] = {}


def _build() -> tuple[Franchise, ...]:
    out: list[Franchise] = []
    for raw in _RAW_REGISTER:
        d = dict(raw)
        d["contract"] = tuple(d.get("contract", ()))
        d["windows"] = tuple(d.get("windows", ()))
        d["copy_safe_name"] = _name_is_copy_safe(d["display_name"])
        out.append(Franchise(**d))
    return tuple(out)


def register(*, root: Path | str | None = None) -> tuple[Franchise, ...]:
    """The full franchise register, ordered as declared.

    `root` is accepted for signature symmetry with the rest of the marketing
    package (and for `spec_drift`); the register itself is code, not data.
    """
    del root
    if "all" not in _CACHE:
        _CACHE["all"] = _build()
    return _CACHE["all"]


def clear_cache() -> None:
    """Drop the memoised register — tests that monkeypatch the vocab guard."""
    _CACHE.clear()


def for_account(account: str, *, root: Path | str | None = None) -> tuple[Franchise, ...]:
    """Every franchise owned by `account`, including disabled ones.

    Disabled franchises are RETURNED, not filtered: a caller asking "what does
    this desk run" deserves to see the parked ones, and `open_slots()` is where
    the enabled check actually bites (with a logged abstention).
    """
    acct = str(account or "").strip()
    return tuple(f for f in register(root=root) if f.account == acct)


def by_id(franchise_id: str, *, root: Path | str | None = None) -> Franchise | None:
    fid = str(franchise_id or "").strip()
    for f in register(root=root):
        if f.id == fid:
            return f
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling
# ─────────────────────────────────────────────────────────────────────────────
def _require_aware(now: datetime) -> datetime:
    """Reject a naive clock (review F6).

    Every window in this register is declared in a named tz, so a naive `now`
    silently means "whatever tz this process happens to run in" — the Mac Studio
    renders in local time and CI runs in UTC, which is an 8-hour swing on Cici's
    windows. That is not a degradation worth failing soft on: a franchise that
    opens on the runner but not on the VPS is a bug that only ever reproduces
    somewhere else. Raise instead.
    """
    if not isinstance(now, datetime):
        raise TypeError(f"now must be a datetime, got {type(now).__name__}")
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError(
            "now must be timezone-aware — franchise windows are declared in named "
            "timezones, and a naive clock resolves to the host's local zone "
            "(UTC in CI, local on the render host). Pass e.g. "
            "datetime.now(timezone.utc)."
        )
    return now


def _local(now: datetime, tz: str) -> datetime:
    _require_aware(now)
    zone = _zone(tz)
    if zone is None:
        return now
    try:
        return now.astimezone(zone)
    except Exception:
        return now


def _recent_franchise_uses(
    history: Iterable[tuple[datetime, str]],
    franchise_id: str,
) -> list[datetime]:
    """Timestamps at which `franchise_id` was emitted, newest-first.

    `history` is the same (when, franchise_id) shape the caller keeps for an
    account. It is passed in rather than read here so this module does no I/O —
    the desk feed owns the outbox read, and a fixture can drive the scheduler
    with a literal list.
    """
    out = [w for (w, fid) in history if fid == franchise_id and w is not None]
    out.sort(reverse=True)
    return out


def is_enabled(f: Franchise, cfg: dict | None = None) -> bool:
    """Config may force a franchise dark, or ARM a parked one.

    `franchises.disabled` is a kill list; `franchises.enabled_overrides` can
    flip a register-parked franchise on. Both exist so arming "Tea and Tickers"
    (once the real Cici confirms her canon) is a config flip rather than a code
    change — the same posture as `wire_routing`.
    """
    block = (cfg or {}).get("franchises") or {}
    if f.id in set(block.get("disabled") or ()):
        return False
    override = (block.get("enabled_overrides") or {}).get(f.id)
    if override is not None:
        return bool(override)
    return f.enabled


def open_slots(
    account: str,
    *,
    now: datetime,
    history: Sequence[tuple[datetime, str]] = (),
    root: Path | str | None = None,
    cfg: dict | None = None,
    include_disabled: bool = False,
) -> list[FranchiseSlot]:
    """Which franchise windows are OPEN for `account` at `now`.

    Windows, not quotas (constitution Law 1). A returned slot means "this format
    is eligible right now" — the caller still has to have something worth
    saying, and abstains via `abstain()` when it does not.

    `history` is [(emitted_at, franchise_id), ...] for this account; it drives
    the per-day and per-week ceilings. An empty history means every enabled,
    in-window franchise is open — correct for a cold start.

    The clock is fully injected: `now` is the only time source, so a fixture
    clock is a literal datetime — but it MUST be timezone-aware (review F6).
    Windows are declared in named timezones, so a naive datetime would resolve
    against the host zone and open different slots in CI than on the render
    host; `_require_aware` raises rather than failing soft on that.
    """
    _require_aware(now)
    slots: list[FranchiseSlot] = []
    for f in for_account(account, root=root):
        if not is_enabled(f, cfg) and not include_disabled:
            continue
        local = _local(now, f.tz)
        day = local.strftime("%Y-%m-%d")
        minute = local.hour * 60 + local.minute

        # ── calendar check (review F4) — WEEKDAY CLOCK, NOT A TRADING CALENDAR
        weekday = local.weekday()  # Mon=0 … Sun=6
        if f.days and weekday not in f.days:
            continue
        if f.sessions_only and weekday >= 5:
            continue

        # ── window check ────────────────────────────────────────────────────
        opens_at = closes_at = None
        if f.is_windowed:
            for raw in f.windows:
                parsed = _parse_window(raw)
                if parsed is None:
                    continue
                start, end = parsed
                inside = (start <= minute < end) if end > start else (minute >= start or minute < end)
                if inside:
                    # TODO(xg-w3-review): F21 — a WRAPPED window (end <= start,
                    # e.g. "22:00-02:00") spans a local-midnight DAY FLIP, but
                    # `day` above is taken from `now` alone. An emission at
                    # 00:30 inside such a window is charged to the new local
                    # day, so a `daily` wrapped franchise could open twice
                    # across one continuous overnight session. No franchise in
                    # the register wraps today (every window has end > start),
                    # so this is latent rather than live — but the first wrapped
                    # window added here MUST come with a session-anchored day
                    # key, not the calendar day.
                    opens_at = local.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
                    # An end of exactly 24:00 is the end of the local day.
                    end_h, end_m = divmod(min(end, 24 * 60 - 1), 60)
                    closes_at = local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
                    if end <= start:  # wrapped past midnight
                        closes_at = closes_at + timedelta(days=1)
                    break
            if opens_at is None:
                continue
        else:
            opens_at = local.replace(hour=0, minute=0, second=0, microsecond=0)
            closes_at = opens_at + timedelta(days=1)

        # ── cadence ceilings ────────────────────────────────────────────────
        uses = _recent_franchise_uses(history, f.id)
        today = [w for w in uses if _local(w, f.tz).strftime("%Y-%m-%d") == day]
        if f.max_per_day > 0 and len(today) >= f.max_per_day:
            continue
        if f.cadence == "weekly" and f.max_per_week > 0:
            cutoff = now - timedelta(days=7)
            if len([w for w in uses if w >= cutoff]) >= f.max_per_week:
                continue

        slots.append(
            FranchiseSlot(
                franchise=f,
                account=f.account,
                day=day,
                opens_at=opens_at,
                closes_at=closes_at,
                now=now,
            )
        )
    return slots


def item_franchise_id(item: dict) -> str:
    """The franchise an outbox item belongs to, or "".

    The franchise id travels in `item["source"]["franchise"]` — the same
    metadata slot `story_lock.item_story_key` reads for the story key. Kept as a
    named accessor so the key is written once, not spelled out at every reader.
    """
    src = item.get("source")
    if not isinstance(src, dict):
        return ""
    return str(src.get("franchise") or "")


def history_from_items(
    items: Iterable[dict],
    *,
    account: str,
) -> list[tuple[datetime, str]]:
    """Derive `open_slots(history=...)` from outbox items.

    THE PRODUCER for the scheduler's cadence ceilings. Without it
    `franchise_history` has no in-repo source and every daily slot would look
    permanently unspent — the franchise would re-open on every tick and the
    "windows, not quotas" discipline would silently become "unlimited".

    Reads `created_at`, falling back to `as_of`. An item with neither is SKIPPED
    rather than treated as now: counting an undateable item as today's use would
    close a slot the desk never actually spent.
    """
    out: list[tuple[datetime, str]] = []
    acct = str(account or "")
    for item in items or ():
        if str(item.get("account") or "") != acct:
            continue
        fid = item_franchise_id(item)
        if not fid:
            continue
        stamp = str(item.get("created_at") or item.get("as_of") or "").strip()
        if not stamp:
            continue
        when: datetime | None = None
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            try:
                when = datetime.strptime(stamp[:10], "%Y-%m-%d")
            except ValueError:
                when = None
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        out.append((when, fid))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def abstain(
    slot: FranchiseSlot | None,
    reason: str,
    *,
    now: datetime,
    account: str = "",
    franchise_id: str = "",
    detail: dict[str, Any] | None = None,
) -> Abstention:
    """Record a silence with its reason (constitution §16.5).

    An unrecognised reason raises: the taxonomy is the whole diagnostic value,
    and a free-text reason would make "almost everything is rejected for the
    same reason" unanswerable. Callers that genuinely need a new reason add it
    to ABSTAIN_REASONS with a line explaining what it diagnoses.
    """
    r = str(reason or "").strip()
    if r not in ABSTAIN_REASONS:
        raise ValueError(
            f"unknown abstention reason {r!r}; allowed: {sorted(ABSTAIN_REASONS)}"
        )
    acct = slot.account if slot is not None else str(account or "")
    fid = slot.franchise_id if slot is not None else str(franchise_id or "")
    return Abstention(
        account=acct,
        franchise_id=fid,
        reason=r,
        at=now.isoformat(),
        detail=dict(detail or {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Measured-input rule — charter §2 amendment 10
#
# "A crowd-state claim requires a measured input." Meagan's Mood-vs-Money /
# crowd-emotion beat has NO sanctioned sentiment source until XG-W5 (GDELT tone;
# observed x_follow engagement). Her interim form quotes ATTRIBUTED headlines or
# posts; it never asserts an unmeasured crowd state, and the LLM never
# originates the crowd reading.
#
# This is the house epistemics law applied to copy: the engine may report what a
# named source said, and may report our own tape, but "everyone is panicking" is
# a measurement nobody took.
# ─────────────────────────────────────────────────────────────────────────────

#: Assertions ABOUT a crowd's internal state. Deliberately about the SUBJECT
#: ("everyone", "the crowd", "retail", "sentiment") rather than about emotion
#: words alone — "fear gauge" is an instrument, "everyone is afraid" is a claim.
_CROWD_SUBJECT_RE = re.compile(
    r"\b(everyone|everybody|nobody|no one|the crowd|the street|retail|"
    r"traders?|investors?|the market|people|the tape'?s mood|sentiment|"
    r"consensus|the group chat|twitter|x)\b",
    re.I,
)
#: The state predicate that turns a subject into a crowd-state CLAIM.
_CROWD_STATE_RE = re.compile(
    r"\b(is|are|feels?|felt|thinks?|believes?|wants?|fears?|panick\w+|"
    r"euphoric|terrified|scared|afraid|bullish|bearish|convinced|certain|"
    r"complacent|nervous|excited|desperate|giddy|numb|bored|"
    r"has (?:decided|given up)|seems? to)\b",
    re.I,
)
#: Attribution that makes a crowd reading REPORTED rather than asserted: a
#: quotation, a named source, a handle, a link, or an explicit hedge to a
#: measurable proxy.
_ATTRIBUTION_RE = re.compile(
    r"(\"[^\"]{4,}\"|“[^”]{4,}”|https?://\S+|@\w+|"
    r"\b(per|according to|via|reports?|reported|said|says|wrote|posted|"
    r"headline|the piece|the story|survey|poll|reading|gauge|index)\b)",
    re.I,
)


def measured_input_violations(
    headline: str,
    body: str,
    *,
    franchise: "Franchise | None" = None,
    sources: Sequence[Any] = (),
) -> list[str]:
    """Reject an UNMEASURED crowd-state claim (charter §2 amendment 10).

    Returns a list of violation strings ([] = clean), matching the shape every
    other validator in this package uses so a caller can concatenate them.

    Applies only when the franchise declares `requires_measured_input` — the
    rule is about crowd-state FRANCHISES, not about every sentence Meagan
    writes. `sources` is any attributed evidence the caller already holds (a
    press item, a quoted post); a non-empty source list satisfies attribution
    even when the copy itself carries no visible marker, because the citation
    travels in item metadata.
    """
    if franchise is None or not franchise.requires_measured_input:
        return []
    text = f"{headline or ''} {body or ''}".strip()
    if not text:
        return []
    if sources:
        return []
    if _ATTRIBUTION_RE.search(text):
        return []

    out: list[str] = []
    # Sentence-level: a subject and a state predicate must co-occur in ONE
    # sentence to be a claim. Across two sentences ("Everyone has a view. The
    # tape is flat.") they are two separate, honest statements.
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if _CROWD_SUBJECT_RE.search(sentence) and _CROWD_STATE_RE.search(sentence):
            out.append(
                "crowd-state claim without a measured input or attribution: "
                f"{sentence.strip()[:90]!r}"
            )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Drift guard
# ─────────────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def spec_drift(*, root: Path | str | None = None) -> list[str]:
    """Cross-check the register against the committed persona specs.

    Returns a list of human-readable drift strings ([] = clean). Checks:

      1. every register entry names a real account with a committed spec;
      2. every EMPLOYEE spec `franchises:` prose line has a register entry
         whose display name is a prefix of it (the prose lines are written
         "Name — gloss", so prefix-match is the honest join);
      3. every register kind is an admitted content kind;
      4. classification/cadence are in their closed vocabularies;
      5. windows parse and tz resolves;
      6. a franchise window does not fall wholly outside its account's own
         `cadence.session` windows, when the spec declares one — a format that
         can never open under the resolver's clock is dead config.

    This is what keeps a code register honest against a YAML source of record.
    """
    out: list[str] = []
    try:
        from engine.marketing.personas import load_all

        # dict[str, PersonaSpec] — a MAPPING of dataclasses. Iterating it yields
        # id strings, so a list-shaped reading of this API makes every check
        # below vacuously pass. Normalise to plain dicts once, here.
        loaded = load_all(root) if root is not None else load_all()
        specs = {sid: s.as_dict() for sid, s in loaded.items()}
    except Exception as exc:  # pragma: no cover - defensive
        return [f"could not load persona specs: {exc}"]

    try:
        from engine.marketing.content_studio import CONTENT_TYPES

        valid_kinds = {t["id"] for t in CONTENT_TYPES}
    except Exception:
        valid_kinds = set()

    by_account: dict[str, list[Franchise]] = {}
    for f in register(root=root):
        by_account.setdefault(f.account, []).append(f)

        if valid_kinds and f.kind not in valid_kinds:
            out.append(f"{f.id}: kind {f.kind!r} is not an admitted content kind")
        if f.classification not in _CLASSES:
            out.append(f"{f.id}: classification {f.classification!r} not in {sorted(_CLASSES)}")
        if f.cadence not in CADENCES:
            out.append(f"{f.id}: cadence {f.cadence!r} not in {sorted(CADENCES)}")
        for raw in f.windows:
            if _parse_window(raw) is None:
                out.append(f"{f.id}: unparseable window {raw!r}")
        if f.tz and _zone(f.tz) is None:
            out.append(f"{f.id}: unresolvable tz {f.tz!r}")
        if f.cadence == "weekly" and f.max_per_week <= 0:
            out.append(f"{f.id}: weekly cadence needs a positive max_per_week")

    spec_ids = set(specs)
    for account in by_account:
        if spec_ids and account not in spec_ids:
            out.append(f"{account}: register names an account with no committed spec")

    for sid, raw in specs.items():
        if raw.get("persona_kind") != "employee":
            continue
        declared = raw.get("franchises") or []
        names = [_norm(f.display_name) for f in by_account.get(sid, [])]
        for line in declared:
            head = _norm(str(line).split("—")[0])
            if not head:
                continue
            if not any(n == head or head.startswith(n) or n.startswith(head) for n in names):
                out.append(
                    f"{sid}: spec franchise {str(line)[:48]!r} has no register entry"
                )

        # 6. franchise windows vs the account's own territory clock.
        session = (raw.get("cadence") or {}).get("session") or {}
        sess_windows = [w for w in (_parse_window(x) for x in session.get("windows", [])) if w]
        if not sess_windows:
            continue
        for f in by_account.get(sid, []):
            if not f.is_windowed or f.tz != session.get("tz"):
                continue
            fw = [w for w in (_parse_window(x) for x in f.windows) if w]
            if fw and not any(
                fs < se and ss < fe for (fs, fe) in fw for (ss, se) in sess_windows
            ):
                out.append(
                    f"{f.id}: window {f.windows} never overlaps {sid}'s session windows"
                )
    return out
